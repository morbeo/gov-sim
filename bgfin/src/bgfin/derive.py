"""Derived metrics computed from current raw observations (config/derived.yaml)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timezone

from psycopg.types.json import Jsonb

from .config import Config
from .periods import period_label
from .store import same_value

log = logging.getLogger(__name__)


def _load(conn, selector: dict) -> dict:
    """{(geo, vintage): {period: row}} for the selected indicator/source."""
    rows = conn.execute(
        """SELECT obs_id, geo, period, vintage, value, obs_type, frequency
           FROM v_obs_current WHERE indicator_code = %s AND source_code = %s AND value IS NOT NULL
           ORDER BY geo, vintage, period""",
        (selector["indicator"], selector["source"])).fetchall()
    out = defaultdict(dict)
    for r in rows:
        out[(r["geo"], r["vintage"])][r["period"]] = r
    return out


def _quarter(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _to_quarterly(series: dict) -> dict:
    """Average complete quarters of a monthly series."""
    buckets = defaultdict(list)
    for p, r in series.items():
        buckets[_quarter(p)].append(r)
    return {q: {"value": sum(r["value"] for r in rs) / 3, "obs_ids": [r["obs_id"] for r in rs],
                "obs_type": _worst(r["obs_type"] for r in rs)}
            for q, rs in buckets.items() if len(rs) == 3}


def _worst(types) -> str:
    order = ["forecast", "preliminary", "estimate", "actual"]
    types = list(types)
    for t in order:
        if t in types:
            return t
    return "actual"


def real_growth(conn, d: dict) -> list[dict]:
    nominal = _load(conn, d["inputs"]["nominal"])
    prices = _load(conn, d["inputs"]["price_index"])
    out = []
    for (geo, vintage), nom in nominal.items():
        px = prices.get((geo, ""))
        if not px:
            continue
        sample = next(iter(px.values()))
        if sample["frequency"] == "M":
            pq = _to_quarterly(px)
        else:
            pq = {p: {"value": r["value"], "obs_ids": [r["obs_id"]], "obs_type": r["obs_type"]} for p, r in px.items()}
        for p, n in nom.items():
            cur, prev = pq.get(p), pq.get(date(p.year - 1, p.month, 1))
            if not cur or not prev or prev["value"] == 0:
                continue
            inflation = 100 * (cur["value"] / prev["value"] - 1)
            value = 100 * ((1 + n["value"] / 100) / (1 + inflation / 100) - 1)
            out.append({
                "geo": geo, "frequency": n["frequency"], "period": p, "vintage": vintage, "value": value,
                "obs_type": _worst([n["obs_type"], cur["obs_type"], prev["obs_type"]]),
                "method": "(1 + nominal/100) / (1 + yoy(quarterly avg price index)/100) - 1, x100",
                "inputs": {"nominal_obs_id": n["obs_id"], "nominal": n["value"],
                           "price_obs_ids": cur["obs_ids"] + prev["obs_ids"],
                           "price_yoy": round(inflation, 6)},
            })
    return out


def yoy_pct(conn, d: dict) -> list[dict]:
    levels = _load(conn, d["inputs"]["level"])
    out = []
    for (geo, vintage), lv in levels.items():
        for p, r in lv.items():
            prev = lv.get(date(p.year - 1, p.month, 1))
            if not prev or prev["value"] == 0:
                continue
            out.append({
                "geo": geo, "frequency": r["frequency"], "period": p, "vintage": vintage,
                "value": 100 * (r["value"] / prev["value"] - 1),
                "obs_type": _worst([r["obs_type"], prev["obs_type"]]),
                "method": "100 * (level / level previous year - 1)",
                "inputs": {"obs_id": r["obs_id"], "value": r["value"],
                           "previous_obs_id": prev["obs_id"], "previous_value": prev["value"]},
            })
    return out


FUNCTIONS = {"real_growth": real_growth, "yoy_pct": yoy_pct}


def save(conn, d: dict, source: str, rows: list[dict]) -> dict:
    now = datetime.now(timezone.utc)
    current = {
        (r["geo"], r["period"], r["vintage"]): r
        for r in conn.execute(
            """SELECT id, geo, period, vintage, value, obs_type, revision FROM derived_observation
               WHERE metric = %s AND source_code = %s AND superseded_at IS NULL""",
            (d["metric"], source)).fetchall()
    }
    counts = {"new": 0, "revised": 0, "unchanged": 0}
    with conn.cursor() as cur:
        for r in rows:
            key = (r["geo"], r["period"], r["vintage"])
            old = current.get(key)
            if old and same_value(old["value"], r["value"]) and old["obs_type"] == r["obs_type"]:
                counts["unchanged"] += 1
                continue
            revision = 0
            if old:
                cur.execute("UPDATE derived_observation SET superseded_at = %s WHERE id = %s", (now, old["id"]))
                revision = old["revision"] + 1
                counts["revised"] += 1
            else:
                counts["new"] += 1
            cur.execute(
                """INSERT INTO derived_observation (metric, indicator_code, source_code, geo, frequency, period,
                     period_label, vintage, value, unit, obs_type, method, inputs, revision, computed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (d["metric"], d.get("indicator"), source, r["geo"], r["frequency"], r["period"],
                 period_label(r["period"], r["frequency"]), r["vintage"], r["value"], d.get("unit", ""),
                 r["obs_type"], r["method"], Jsonb(r["inputs"]), revision, now))
    conn.commit()
    return counts


def derive(conn, cfg: Config, metrics: list[str] | None = None) -> list[dict]:
    results = []
    for d in cfg.derived:
        if metrics and d["metric"] not in metrics:
            continue
        fn = FUNCTIONS.get(d["function"])
        if fn is None:
            log.error("derived %s: unknown function %s", d["metric"], d["function"])
            continue
        rows = fn(conn, d)
        source = next(iter(d["inputs"].values()))["source"]
        counts = save(conn, d, source, rows)
        log.info("derived %s: %s", d["metric"], counts)
        results.append({"metric": d["metric"], **counts})
    return results
