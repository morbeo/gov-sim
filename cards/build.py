#!/usr/bin/env python3
"""Build politician trading cards from public data.

Reads people from the parliament.bg scraper output (mps.json) or, by default,
from the politicians in the party register, scores them with the stats model
in README.md and writes a card gallery (index.html) plus the card data.

Examples:
  ./build.py                                   # sample cards from ../vote/data/parties.json
  ./build.py --mps ../parliament/out/mps.json  # every MP in the scraper output
  ./build.py --mps mps.json --current          # sitting MPs only
  ./build.py --mps mps.json --name Борисов     # only names containing "Борисов"
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
TODAY = date.today().strftime("%Y-%m")

# ------------------------------------------------------------------ helpers
def months(a: str | None, b: str | None) -> int:
    """Months between two YYYY-MM[-DD] dates; open end means today."""
    if not a:
        return 0
    b = b or TODAY
    ya, ma = int(a[:4]), int(a[5:7] or 1)
    yb, mb = int(b[:4]), int(b[5:7] or 1)
    return max(0, (yb - ya) * 12 + mb - ma)


def clamp(x: float, lo: int = 1, hi: int = 10) -> int:
    return int(max(lo, min(hi, round(x))))


def has(text: str, *words: str) -> bool:
    t = text.lower()
    return any(w in t for w in words)


# ----------------------------------------------------------------- sources
def from_register(register: dict) -> list[dict]:
    """People from parties.json politicians[].path (curated party history)."""
    people = []
    for p in register.get("politicians", []):
        spells, offices = [], []
        for s in p["path"]:
            if "gap" in s:
                offices.append({"title": s["gap"], "from": s["from"], "to": s["to"]})
            else:
                spells.append({"party": s["party"], "from": s["from"], "to": s["to"],
                               "role": "", "note": s.get("note", "")})
        people.append({"id": p["id"], "name": p["name"], "born": None, "region": None,
                       "terms": [], "spells": spells, "offices": offices,
                       "source": "хронология на партиите"})
    return people


def from_mps(mps: list[dict], current: bool) -> list[dict]:
    """People from the parliament.bg scraper's mps.json."""
    latest = max((t["na"] or 0 for p in mps for t in p["terms"]), default=0)
    people = []
    for p in mps:
        terms = [t for t in p["terms"] if t.get("na")]
        if not terms or (current and not any(t["na"] == latest and not t["to"] for t in terms)):
            continue
        spells, offices = [], []
        for t in terms:
            groups = t.get("groups") or [{"party": t.get("party"), "group": t.get("electedList") or "",
                                          "role": "", "from": t.get("from"), "to": t.get("to")}]
            for g in groups:
                party = g.get("party")
                if not party and has(g.get("group") or "", "нечленуващ", "независим"):
                    offices.append({"title": "Независим депутат", "from": g.get("from"), "to": g.get("to")})
                    continue
                spells.append({"party": party or t.get("party"), "from": g.get("from"), "to": g.get("to"),
                               "role": g.get("role") or "", "note": f"{t['na']}-о Народно събрание"})
        last = terms[-1]
        people.append({"id": f"mp{last['mpId']}", "name": p["name"], "born": p.get("born"),
                       "region": last.get("region"), "terms": sorted({t["na"] for t in terms}),
                       "spells": spells, "offices": offices, "regions": [t.get("region") for t in terms],
                       "bills": p.get("bills"), "attendance": p.get("attendance"),
                       "preferences": p.get("preferences"),
                       "source": "parliament.bg"})
    return people


# -------------------------------------------------------------- stats model
KEYWORDS = {
    "founder":  ("Основател", "Щом влезе в игра, създай жетон „Нова партия“."),
    "pm":       ("Премиер", "Веднъж на игра: изтегли 2 карти."),
    "president": ("Държавен глава", "Вето: отмени една карта „Закон“ този ход."),
    "leader":   ("Лидер", "Другите ти карти от същата партия получават +1 Влияние."),
    "nomad":    ("Номад", "Може да се присъедини към всяка коалиция."),
    "veteran":  ("Ветеран", "Не може да бъде отстранен през първия си ход."),
    "indep":    ("Независим", "Не е засегнат от ефекти на коалиции."),
    "rookie":   ("Новобранец", "Струва 1 по-малко."),
    "diligent": ("Прилежен", "Изтегли карта, когато гласуваш."),
    "lawmaker": ("Законотворец", "Картите „Закон“ ти струват 1 по-малко."),
}
# Official public records only (see data/records.json); each adds starting
# "Компромат" tokens and a keyword that is always shown.
# The last number is the Корупция stat; without a record that stat stays empty.
RECORD_KW = {
    "sanction":  ("Под санкции", 2, "Започва с 2 „Компромат“. Схемите ти струват 1 по-малко.", 7),
    "conviction": ("Осъден", 3, "Започва с 3 „Компромат“.", 9),
    "conflict":  ("Конфликт на интереси", 1, "Започва с 1 „Компромат“.", 4),
}
# id: (name, abbreviation, what it is computed from). None = no data for that person.
STATS = {
    "charisma":   ("Харизма", "ХАР", "води листи, основава партии, печели преки избори; преференции"),
    "scheming":   ("Интриги", "ИНТ", "смени на партия, отцепвания, коалиции, периоди като независим"),
    "influence":  ("Влияние", "ВЛИ", "постове: премиер, президент, министър, лидер; мандати"),
    "negotiation": ("Преговори", "ПРГ", "коалиции, общи листи, съпредседателство"),
    "network":    ("Връзки", "ВРЪ", "брой партии, коалиции и държавни постове"),
    "survival":   ("Оцеляване", "ОЦЛ", "завръщания след други постове, още е активен, дължина на кариерата"),
    "experience": ("Опит", "ОПТ", "години в политиката или в парламента, мандати"),
    "loyalty":    ("Лоялност", "ЛОЯ", "10 минус смените на партия и периодите като независим"),
    "corruption": ("Корупция", "КОР", "само официални актове от data/records.json"),
    "lawmaking":  ("Законотворчество", "ЗАК", "внесени законопроекти (поле bills)"),
    "attendance": ("Присъствие", "ПРС", "присъствие на заседания (поле attendance)"),
    "base":       ("Регионална база", "РЕГ", "мандати от един и същи избирателен район"),
}
RARITY = [(26, "legendary", "Легендарна"), (23, "rare", "Рядка"),
          (19, "uncommon", "Необичайна"), (0, "common", "Обикновена")]


def load_records(path: Path | None) -> dict[str, list[dict]]:
    """Records by person name; refuses entries without an official source."""
    if not path or not path.exists():
        return {}
    out: dict[str, list[dict]] = {}
    for r in json.loads(path.read_text("utf-8")).get("records", []):
        if r.get("type") not in RECORD_KW:
            raise SystemExit(f"{path}: unknown record type {r.get('type')!r} for {r.get('name')}")
        if not str(r.get("source", "")).startswith("http"):
            raise SystemExit(f"{path}: record for {r.get('name')} has no source URL")
        out.setdefault(r["name"].lower(), []).append(r)
    return out


def score(p: dict, records: list[dict] | None = None, coalitions: set | None = None) -> dict:
    text = " ".join(s["note"] + " " + s["role"] for s in p["spells"])
    office_text = " ".join(o["title"] for o in p["offices"])
    parties = [s["party"] for s in p["spells"] if s["party"]]
    distinct = list(dict.fromkeys(parties))
    switches = sum(1 for a, b in zip(parties, parties[1:]) if a != b)
    years = sum(months(s["from"], s["to"]) for s in p["spells"] + p["offices"]) / 12
    terms = len(p["terms"])

    kw = []
    if has(text, "основава", "основател", "съосновател"):
        kw.append("founder")
    if has(text, "министър-председател"):
        kw.append("pm")
    if has(office_text, "президент"):
        kw.append("president")
    if has(text, "лидер", "председател", "води ", "оглавява") and "pm" not in kw:
        kw.append("leader")
    if len(distinct) >= 3:
        kw.append("nomad")
    if terms >= 5 or years >= 20:
        kw.append("veteran")
    if has(office_text, "независим"):
        kw.append("indep")
    if p.get("attendance") is not None and p["attendance"] >= 0.95:
        kw.append("diligent")
    if p.get("bills") is not None and p["bills"] >= 20:
        kw.append("lawmaker")
    if terms <= 1 and years < 4 and not kw:
        kw.append("rookie")

    records = sorted(records or [], key=lambda r: r.get("date") or "")
    rec_kw = list(dict.fromkeys(r["type"] for r in records))
    keywords = [{"id": t, "name": RECORD_KW[t][0], "text": RECORD_KW[t][2], "record": True} for t in rec_kw] \
        + [{"id": k, "name": KEYWORDS[k][0], "text": KEYWORDS[k][1]} for k in kw][:max(1, 2 - len(rec_kw))]
    kompromat = sum(RECORD_KW[t][1] for t in rec_kw)

    coalition = sum(1 for s in p["spells"] if s["party"] in (coalitions or ()))
    minister = has(text, "министър", "вицепремиер", "еврокомисар", "зам.-председател на нс")
    active = any(not s["to"] for s in p["spells"])
    starts = [s["from"] for s in p["spells"] + p["offices"] if s["from"]]
    span = months(min(starts), None if active else max(s["to"] or TODAY for s in p["spells"] + p["offices"])) / 12 \
        if starts else 0
    regions = [r for r in p.get("regions") or [] if r]
    posts = [o for o in p["offices"] if not has(o["title"], "независим")]
    raw = {
        "charisma": 2 + 3 * ("president" in kw) + 2 * ("pm" in kw) + 2 * ("founder" in kw)
        + 1.5 * ("leader" in kw) + (p.get("preferences") or 0) / 5000,
        "scheming": 2 + 2 * switches + 2 * ("founder" in kw and switches > 0) + coalition + ("indep" in kw),
        "corruption": max((RECORD_KW[t][3] for t in rec_kw), default=None),
        "influence": 2 + 4 * ("pm" in kw) + 4 * ("president" in kw) + 2 * minister + 1.5 * ("leader" in kw)
        + 0.3 * terms,
        "experience": max(years / 3.5, terms * 1.5),
        "loyalty": 9 - 2.5 * switches - 1.5 * ("indep" in kw),
        "survival": 2 + 3 * active + 2 * len(posts) + span / 8,
        "network": 2 + len(distinct) + coalition + minister + len(posts),
        "negotiation": 2 + 2 * coalition + 2 * has(text, "съпредседател", "съосновател", "обща листа")
        + ("pm" in kw),
        "lawmaking": p["bills"] / 5 if p.get("bills") is not None else None,
        "attendance": p["attendance"] * 10 if p.get("attendance") is not None else None,
        "base": 2 * max(regions.count(r) for r in regions) if regions else None,
    }
    stats = {k: None if v is None else clamp(v) for k, v in raw.items()}
    current = next((s for s in reversed(p["spells"]) if s["party"]), None)
    flavor = next((s["note"] for s in reversed(p["spells"]) if s["note"]), "")
    return {"stats": stats, "rookie": "rookie" in kw,
            "keywords": keywords, "kompromat": kompromat,
            "records": [{k: r.get(k) for k in ("type", "date", "summary", "source")} for r in records],
            "party": current["party"] if current else None, "parties": distinct,
            "years": round(years, 1), "terms": terms, "switches": switches, "flavor": flavor}


def pick_main(cards: list[dict]) -> None:
    """Main stats are the three that stand out most against the deck's median,
    so a card shows what makes the politician distinctive; then cost and rarity."""
    med = {}
    for k in STATS:
        vals = sorted(c["stats"][k] for c in cards if c["stats"][k] is not None)
        med[k] = vals[len(vals) // 2] if vals else 0
    order = list(STATS)
    for c in cards:
        known = [k for k in STATS if c["stats"][k] is not None]
        c["main"] = sorted(known, key=lambda k: (-(c["stats"][k] - med[k]), -c["stats"][k], order.index(k)))[:3]
        total = sum(c["stats"][k] for k in c["main"])
        c["rarity"], c["rarityLabel"] = next((r, label) for floor, r, label in RARITY if total >= floor)
        c["cost"] = clamp(total / 4 - c.pop("rookie"), 1, 7)


def build_cards(people: list[dict], register: dict, records: dict | None = None) -> list[dict]:
    pinfo = {p["id"]: {"short": p["short"], "name": p["name"], "color": p["color"]}
             for p in register.get("parties", [])}
    coalitions = {p["id"] for p in register.get("parties", [])
                  if has(p["name"], "+", "коалиция", "блок", " – ", "обединени")}
    cards = []
    for p in people:
        c = {"id": p["id"], "name": p["name"], "born": p["born"], "region": p["region"],
             "source": p["source"], "termList": p["terms"],
             **score(p, (records or {}).get(p["name"].lower()), coalitions)}
        cards.append(c)
    pick_main(cards)
    cards.sort(key=lambda c: (-c["cost"], c["name"]))
    for i, c in enumerate(cards, 1):
        c["number"] = f"{i:03d}/{len(cards):03d}"
    return cards, pinfo


# --------------------------------------------------------------------- cli
def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 epilog=__doc__.split("\n\n", 2)[2],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mps", type=Path, help="mps.json from parliament_scrape.py (default: sample politicians from --parties)")
    ap.add_argument("--parties", type=Path, default=HERE.parent / "vote" / "data" / "parties.json",
                    help="party register with colours (default ../vote/data/parties.json)")
    ap.add_argument("--records", type=Path, default=HERE / "data" / "records.json",
                    help="sourced public records: sanctions, convictions, conflicts of interest (default ./data/records.json)")
    ap.add_argument("--shadow", type=Path, default=HERE / "data" / "shadow.json",
                    help="scheme and counter cards (default ./data/shadow.json)")
    ap.add_argument("--current", action="store_true", help="with --mps: sitting MPs only")
    ap.add_argument("--name", help="only people whose name contains this text")
    ap.add_argument("--template", type=Path, default=HERE / "template.html", help="gallery template")
    ap.add_argument("-o", "--out", type=Path, default=HERE / "index.html", help="gallery page (default ./index.html)")
    ap.add_argument("--json", type=Path, default=HERE / "data" / "cards.json", help="card data (default ./data/cards.json)")
    args = ap.parse_args(argv)

    register = json.loads(args.parties.read_text("utf-8"))
    if args.mps:
        people = from_mps(json.loads(args.mps.read_text("utf-8")), args.current)
    else:
        people = from_register(register)
    if args.name:
        people = [p for p in people if args.name.lower() in p["name"].lower()]
    if not people:
        raise SystemExit("no people matched; check --mps/--name/--current")

    cards, parties = build_cards(people, register, load_records(args.records))
    shadow = json.loads(args.shadow.read_text("utf-8"))["cards"] if args.shadow.exists() else []
    for i, c in enumerate(shadow, 1):
        c["number"] = f"С{i:02d}/{len(shadow):02d}"
    payload = {"generated": TODAY, "stats": {k: {"name": n, "abbr": a, "from": f} for k, (n, a, f) in STATS.items()},
               "cards": cards, "shadow": shadow, "parties": parties}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")
    page = args.template.read_text("utf-8").replace(
        "/*CARDS*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    args.out.write_text(page, "utf-8")
    print(f"{len(cards)} politician + {len(shadow)} shadow cards -> {args.out}, {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
