#!/usr/bin/env python3
"""Build the relationship map of Bulgarian parties, people and informal influence.

Reads the party register (parties, splits, politicians' party paths) and the
hand-made nodes and edges in data/relations.json, checks them, and writes a
self-contained page (index.html) with the data inlined.

Examples:
  ./build.py                                  # defaults below
  ./build.py --parties /mnt/project-files/timeline/bg-parties.json
  ./build.py --check                          # validate only, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

NODE_TYPES = {
    "party": "Партия",
    "person": "Политик",
    "oligarch": "Бизнесмен / олигарх",
    "company": "Фирма",
    "media": "Медия",
    "institution": "Институция",
    "government": "Правителство",
    "network": "Неформален кръг",
}

# category: formal (публични роли), informal (задкулисие), acts (официални актове)
EDGE_TYPES = {
    "member": {"label": "Член на", "cat": "formal", "directed": True},
    "leader": {"label": "Води / председател", "cat": "formal", "directed": True},
    "founder": {"label": "Основател", "cat": "formal", "directed": True},
    "split": {"label": "Отцепване", "cat": "formal", "directed": True},
    "joins": {"label": "Влиза в / обща листа", "cat": "formal", "directed": True},
    "coalition": {"label": "Коалиция", "cat": "formal", "directed": False},
    "government": {"label": "Участва в управлението", "cat": "formal", "directed": True},
    "influence": {"label": "Влияние / контрол", "cat": "informal", "directed": True},
    "funding": {"label": "Финансиране", "cat": "informal", "directed": True},
    "business": {"label": "Бизнес връзка", "cat": "informal", "directed": False},
    "family": {"label": "Лична / роднинска връзка", "cat": "informal", "directed": False},
    "media": {"label": "Медийна подкрепа", "cat": "informal", "directed": True},
    "conflict": {"label": "Противопоставяне", "cat": "informal", "directed": False},
    "sanction": {"label": "Санкция", "cat": "acts", "directed": True},
    "investigation": {"label": "Разследване", "cat": "acts", "directed": True},
    "conviction": {"label": "Присъда", "cat": "acts", "directed": True},
}

CATEGORIES = {"formal": "Публични роли", "informal": "Задкулисие", "acts": "Официални актове"}

STATUSES = {
    "documented": "Документирано",
    "claim": "Твърдение",
    "rumor": "Слух",
}

REGISTER_SOURCE = "Хронология на партиите"


class DataError(ValueError):
    pass


def derive(register: dict) -> tuple[list[dict], list[dict]]:
    """Nodes and edges that follow from the party register."""
    parties = {p["id"]: p for p in register["parties"]}
    nodes, edges = [], []
    for p in register["parties"]:
        nodes.append({
            "id": f"p:{p['id']}", "type": "party", "label": p["short"], "name": p["name"],
            "party": p["id"], "seats": max(p.get("seats", {}).values(), default=0),
            "start": p.get("start"), "end": p.get("end"),
        })
    for i, link in enumerate(register.get("links", [])):
        edges.append({
            "id": f"r:link{i}", "from": f"p:{link['from']}", "to": f"p:{link['to']}",
            "type": link["type"] if link["type"] in EDGE_TYPES else "joins",
            "status": "documented", "date": link.get("date"), "source": REGISTER_SOURCE,
            "note": link.get("note", ""),
        })
    for pol in register.get("politicians", []):
        steps = [s for s in pol.get("path", []) if s.get("party") in parties]
        nodes.append({
            "id": f"pol:{pol['id']}", "type": "person", "label": pol["name"],
            "party": steps[-1]["party"] if steps else None,
        })
        for j, s in enumerate(steps):
            note = s.get("note", "")
            edges.append({
                "id": f"r:{pol['id']}{j}", "from": f"pol:{pol['id']}", "to": f"p:{s['party']}",
                "type": "founder" if "снова" in note else "member",
                "status": "documented", "date": s.get("from"), "end": s.get("to"),
                "source": REGISTER_SOURCE, "note": note,
            })
    return nodes, edges


def validate(manual: dict, derived_nodes: list[dict], parties: set[str]) -> list[str]:
    """Return a list of problems in the hand-made data (empty when it is fine)."""
    errors = []
    ids = {n["id"] for n in derived_nodes}
    for n in manual.get("nodes", []):
        nid = n.get("id")
        if not nid:
            errors.append(f"възел без id: {n}")
            continue
        if nid in ids and not nid.startswith(("p:", "pol:")):
            errors.append(f"повторен id: {nid}")
        ids.add(nid)
        if n.get("type") not in NODE_TYPES:
            errors.append(f"{nid}: непознат тип {n.get('type')!r}")
        if not n.get("label"):
            errors.append(f"{nid}: липсва label")
        if n.get("party") and n["party"] not in parties:
            errors.append(f"{nid}: непозната партия {n['party']!r}")
    for i, e in enumerate(manual.get("edges", [])):
        where = f"връзка {i + 1} ({e.get('from')} → {e.get('to')})"
        for end in ("from", "to"):
            if e.get(end) not in ids:
                errors.append(f"{where}: непознат възел {e.get(end)!r}")
        if e.get("type") not in EDGE_TYPES:
            errors.append(f"{where}: непознат вид {e.get('type')!r}")
        if e.get("status") not in STATUSES:
            errors.append(f"{where}: статусът трябва да е един от {', '.join(STATUSES)}")
    return errors


def payload(register: dict, manual: dict) -> dict:
    nodes, edges = derive(register)
    problems = validate(manual, nodes, {p["id"] for p in register["parties"]})
    if problems:
        raise DataError("\n".join(problems))
    base = {"nodes": manual.get("nodes", []), "edges": []}
    for i, e in enumerate(manual.get("edges", [])):
        base["edges"].append({"id": e.get("id") or f"m{i}", **e})
    version = hashlib.sha1(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:10]
    return {
        "schema": {"nodeTypes": NODE_TYPES, "edgeTypes": EDGE_TYPES, "categories": CATEGORIES, "statuses": STATUSES},
        "parties": [{"id": p["id"], "short": p["short"], "name": p["name"], "color": p["color"]} for p in register["parties"]],
        "derived": {"nodes": nodes, "edges": edges},
        "base": base,
        "notes": manual.get("notes", []),
        "version": version,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parties", type=Path, default=HERE.parent / "vote/data/parties.json",
                    help="регистър на партиите (по подразбиране: %(default)s)")
    ap.add_argument("--data", type=Path, default=HERE / "data/relations.json",
                    help="ръчните възли и връзки (по подразбиране: %(default)s)")
    ap.add_argument("--template", type=Path, default=HERE / "template.html", help=argparse.SUPPRESS)
    ap.add_argument("-o", "--out", type=Path, default=HERE / "index.html", help="изходна страница (по подразбиране: %(default)s)")
    ap.add_argument("--check", action="store_true", help="само провери данните")
    args = ap.parse_args(argv)

    try:
        register = json.loads(args.parties.read_text(encoding="utf-8"))
        manual = json.loads(args.data.read_text(encoding="utf-8"))
        data = payload(register, manual)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"грешка: {exc}", file=sys.stderr)
        return 1
    except DataError as exc:
        print(f"грешки в {args.data}:\n{exc}", file=sys.stderr)
        return 1

    n = len(data["derived"]["nodes"]) + len(data["base"]["nodes"])
    m = len(data["derived"]["edges"]) + len(data["base"]["edges"])
    if args.check:
        print(f"наред: {n} възела, {m} връзки")
        return 0
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = args.template.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    args.out.write_text(html, encoding="utf-8")
    print(f"{args.out}: {n} възела, {m} връзки")
    return 0


if __name__ == "__main__":
    sys.exit(main())
