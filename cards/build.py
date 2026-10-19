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
                       "spells": spells, "offices": offices,
                       "bills": p.get("bills"), "attendance": p.get("attendance"),
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
RARITY = [(24, "legendary", "Легендарна"), (18, "rare", "Рядка"),
          (12, "uncommon", "Необичайна"), (0, "common", "Обикновена")]


def score(p: dict) -> dict:
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

    # Влияние: leadership and office; Стаж: time served; Лоялност: party switches.
    influence = 2 + 3 * ("pm" in kw) + 3 * ("president" in kw) + 2 * ("founder" in kw) \
        + 2 * ("leader" in kw) + 0.5 * terms + (p.get("bills") or 0) / 20
    experience = max(years / 3.5, terms * 1.5)
    loyalty = 10 - 2.5 * switches - 1.5 * ("indep" in kw)
    stats = {"influence": clamp(influence), "experience": clamp(experience), "loyalty": clamp(loyalty)}

    total = sum(stats.values())
    rarity = next((r, label) for floor, r, label in RARITY if total >= floor)
    cost = clamp(total / 4 - ("rookie" in kw), 1, 7)

    current = next((s for s in reversed(p["spells"]) if s["party"]), None)
    flavor = next((s["note"] for s in reversed(p["spells"]) if s["note"]), "")
    return {"stats": stats, "cost": cost, "rarity": rarity[0], "rarityLabel": rarity[1],
            "keywords": [{"id": k, "name": KEYWORDS[k][0], "text": KEYWORDS[k][1]} for k in kw[:3]],
            "party": current["party"] if current else None, "parties": distinct,
            "years": round(years, 1), "terms": terms, "switches": switches, "flavor": flavor}


def build_cards(people: list[dict], register: dict) -> list[dict]:
    pinfo = {p["id"]: {"short": p["short"], "name": p["name"], "color": p["color"]}
             for p in register.get("parties", [])}
    cards = []
    for p in people:
        c = {"id": p["id"], "name": p["name"], "born": p["born"], "region": p["region"],
             "source": p["source"], "termList": p["terms"], **score(p)}
        cards.append(c)
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

    cards, parties = build_cards(people, register)
    payload = {"generated": TODAY, "cards": cards, "parties": parties}
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")
    page = args.template.read_text("utf-8").replace(
        "/*CARDS*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    args.out.write_text(page, "utf-8")
    print(f"{len(cards)} cards -> {args.out}, {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
