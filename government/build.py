#!/usr/bin/env python3
"""Build the interactive model of the Bulgarian system of government.

Reads the institutions, powers and scenarios (data/government.json) and the
cited articles of the Constitution (data/constitution.json), checks that every
reference resolves, and writes a self-contained page (index.html).

Examples:
  ./build.py              # build index.html
  ./build.py --check      # validate only, write nothing
  ./build.py -o out.html  # write elsewhere
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART_RE = re.compile(r"чл\.\s*(\d+[а-я]?)")
PLACEHOLDER = "/*__DATA__*/null"


def articles_in(ref: str | None) -> list[str]:
    """Article keys cited in a reference string such as 'чл. 99, ал. 5; чл. 102'."""
    return ART_RE.findall(ref or "")


def validate(gov: dict, const: dict) -> list[str]:
    errors: list[str] = []
    arts = const["articles"]
    branches, etypes = gov["branches"], gov["edgeTypes"]
    levels = gov["publicityLevels"]
    node_ids: set[str] = set()
    edge_ids: set[str] = set()

    def check_ref(where: str, ref: str | None) -> None:
        for a in articles_in(ref):
            if a not in arts:
                errors.append(f"{where}: чл. {a} липсва в constitution.json")

    for n in gov["nodes"]:
        where = f"възел {n.get('id')}"
        if n["id"] in node_ids:
            errors.append(f"{where}: повторен id")
        node_ids.add(n["id"])
        if n.get("branch") not in branches:
            errors.append(f"{where}: непознат клон {n.get('branch')!r}")
        if n.get("pub", {}).get("level") not in levels:
            errors.append(f"{where}: непознато ниво на публичност")
        check_ref(where, n.get("refs"))
        check_ref(where, n.get("pub", {}).get("ref"))
        for p in n.get("powers", []):
            if not p.get("ref") and not p.get("law"):
                errors.append(f"{where}: правомощие без източник: {p['t']}")
            check_ref(where, p.get("ref"))

    for e in gov["edges"]:
        where = f"връзка {e.get('id')}"
        if e["id"] in edge_ids:
            errors.append(f"{where}: повторен id")
        edge_ids.add(e["id"])
        for end in ("from", "to"):
            if e.get(end) not in node_ids:
                errors.append(f"{where}: непознат възел {e.get(end)!r}")
        if e.get("type") not in etypes:
            errors.append(f"{where}: непознат вид {e.get('type')!r}")
        if not e.get("ref") and not e.get("law"):
            errors.append(f"{where}: без източник")
        check_ref(where, e.get("ref"))

    for s in gov["scenarios"]:
        for i, st in enumerate(s["steps"], 1):
            where = f"сценарий {s['id']}, стъпка {i}"
            check_ref(where, st.get("ref"))
            errors += [f"{where}: непознат възел {x!r}" for x in st["nodes"] if x not in node_ids]
            errors += [f"{where}: непозната връзка {x!r}" for x in st["edges"] if x not in edge_ids]
            errors += [f"{where}: преход към несъществуваща стъпка {n['to']}" for n in st.get("next", [])
                       if not 0 <= n["to"] < len(s["steps"])]

    for m in gov["majorities"]:
        check_ref(f"мнозинство {m['n']}", m.get("ref"))
    return errors


def build(gov: dict, const: dict, template: str) -> str:
    if PLACEHOLDER not in template:
        raise ValueError(f"шаблонът няма {PLACEHOLDER}")
    blob = json.dumps({"gov": gov, "const": const}, ensure_ascii=False, separators=(",", ":"))
    return template.replace(PLACEHOLDER, blob.replace("</", "<\\/"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=HERE / "data/government.json", help="институции и връзки (%(default)s)")
    ap.add_argument("--const", type=Path, default=HERE / "data/constitution.json", help="текст на членовете (%(default)s)")
    ap.add_argument("--template", type=Path, default=HERE / "template.html", help="шаблон (%(default)s)")
    ap.add_argument("-o", "--out", type=Path, default=HERE / "index.html", help="изход (%(default)s)")
    ap.add_argument("--check", action="store_true", help="само проверка, без запис")
    args = ap.parse_args(argv)

    gov = json.loads(args.data.read_text(encoding="utf-8"))
    const = json.loads(args.const.read_text(encoding="utf-8"))
    errors = validate(gov, const)
    for e in errors:
        print(f"грешка: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"{len(gov['nodes'])} институции, {len(gov['edges'])} връзки, "
          f"{len(const['articles'])} члена: наред", file=sys.stderr)
    if args.check:
        return 0
    args.out.write_text(build(gov, const, args.template.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"записан {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
