"""Render the indicator catalogue (docs/indicator-catalogue.md) from config."""

from __future__ import annotations

from collections import defaultdict

from .config import Config

CATEGORY_TITLES = {
    "activity": "Economic activity", "inflation": "Inflation and purchasing power", "labour": "Labour market",
    "government": "Government finances", "monetary": "Monetary and financial conditions",
    "external": "External sector", "real_estate": "Real estate and household debt",
    "forecasts": "Forecasts and international comparisons",
}


def _source_line(specs) -> str:
    s = specs[0]
    ident = s.dataset or ""
    if s.filters:
        ident += " " + ", ".join(f"{k}={v}" for k, v in s.filters.items())
    if s.key:
        ident += f" key {s.key}"
    if s.variable:
        ident += f"AMECO {s.variable}"
    if s.code:
        ident += f"WDI {s.code}"
    geos = ", ".join(x.geo for x in specs)
    return f"{s.source} ({s.role}, {s.frequency}): `{ident.strip()}`; {geos}"


def render(cfg: Config) -> str:
    out = ["# Indicator catalogue", "",
           "Generated from `config/indicators.yaml` and `config/derived.yaml` by `bgfin catalogue`. "
           "Do not edit by hand.", "",
           "Roles: **primary** feeds dashboards and alerts; **secondary** is the same concept from another "
           "source for cross-checks; **benchmark** is the actual outcome used to score forecasts; "
           "**forecast** is stored per vintage; **input** only feeds derived metrics.", ""]
    derived_by_ind = defaultdict(list)
    for d in cfg.derived:
        derived_by_ind[d.get("indicator")].append(d)
    by_cat = defaultdict(list)
    for ind in cfg.indicators.values():
        by_cat[ind.category].append(ind)
    for cat in list(CATEGORY_TITLES) + sorted(set(by_cat) - set(CATEGORY_TITLES)):
        if cat not in by_cat:
            continue
        out += [f"## {CATEGORY_TITLES.get(cat, cat)}", ""]
        for ind in by_cat[cat]:
            star = " (priority)" if ind.priority else ""
            out += [f"### `{ind.code}`: {ind.name}{star}", "",
                    f"- Unit: {ind.unit}", f"- Canonical frequency: {ind.frequency}"]
            if ind.description:
                out.append(f"- Definition: {' '.join(ind.description.split())}")
            groups = defaultdict(list)
            for s in ind.series:
                groups[(s.source, s.dataset, s.key, s.variable, s.code, s.role, tuple(s.filters.items()))].append(s)
            if groups:
                out.append("- Sources:")
                out += [f"  - {_source_line(g)}" for g in groups.values()]
            for d in derived_by_ind.get(ind.code, []):
                ins = "; ".join(f"{k} = {v['source']}:{v['indicator']}" for k, v in d["inputs"].items())
                out.append(f"  - derived `{d['metric']}` ({d['function']}): {ins}")
            out.append("")
    return "\n".join(out)
