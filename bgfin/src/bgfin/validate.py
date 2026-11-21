"""Data validation and anomaly detection. Findings go to quality_issue.

Checks
  stale             no new period within the series' expected publication lag
  outlier_change    latest period-on-period change is far outside its history
                    (robust z-score: median and MAD of the last 10 years)
  large_revision    a recent revision moved a value by more than the limit
  source_failure    the latest collection run of a source failed
  vanished_observation  (written by the store during full refreshes)

These flag data for a human to look at; they make no economic judgement.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict

from psycopg.types.json import Jsonb

from .config import Config

log = logging.getLogger(__name__)

UPSERT = """
INSERT INTO quality_issue (check_name, severity, series_id, source_code, period, detail)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (check_name, coalesce(source_code, ''), coalesce(series_id, 0), coalesce(period, '1900-01-01'::date))
  WHERE resolved_at IS NULL
DO UPDATE SET last_detected_at = now(), detail = EXCLUDED.detail, severity = EXCLUDED.severity
"""

PERCENT_HINTS = ("%", "percent", "per cent", "rate", "pcch", "pcpa", "pc_", "pch", "rch", "perc")


def is_percent_unit(unit: str) -> bool:
    u = (unit or "").lower()
    return any(h in u for h in PERCENT_HINTS)


def robust_z(history: list[float], x: float) -> float | None:
    if len(history) < 3:
        return None
    med = statistics.median(history)
    mad = statistics.median(abs(h - med) for h in history)
    if mad == 0:
        return None
    return (x - med) / (1.4826 * mad)


def check_stale(conn) -> int:
    rows = conn.execute("SELECT * FROM v_freshness WHERE latest_period IS NOT NULL").fetchall()
    n = 0
    for r in rows:
        if r["is_stale"]:
            conn.execute(UPSERT, ("stale", "warning", r["series_id"], r["source_code"], None,
                                  Jsonb({"latest_period": str(r["latest_period"]),
                                         "days_since_period_end": r["days_since_period_end"],
                                         "max_lag_days": r["max_lag_days"]})))
            n += 1
        else:
            conn.execute("""UPDATE quality_issue SET resolved_at = now()
                            WHERE check_name = 'stale' AND series_id = %s AND resolved_at IS NULL""",
                         (r["series_id"],))
    return n


def check_outliers(conn, z_limit: float, min_history: int) -> int:
    rows = conn.execute(
        """SELECT series_id, source_code, frequency, period, value FROM v_obs_current
           WHERE vintage = '' AND value IS NOT NULL AND obs_type <> 'forecast'
             AND frequency IN ('M', 'Q', 'S', 'A') AND period > current_date - interval '11 years'
           ORDER BY series_id, period""").fetchall()
    by_series = defaultdict(list)
    for r in rows:
        by_series[r["series_id"]].append(r)
    n = 0
    for sid, rs in by_series.items():
        changes = [(b["period"], b["value"] - a["value"]) for a, b in zip(rs, rs[1:])]
        if len(changes) < min_history + 1:
            continue
        latest_period, latest = changes[-1]
        z = robust_z([c for _, c in changes[:-1]], latest)
        if z is not None and abs(z) > z_limit:
            conn.execute(UPSERT, ("outlier_change", "info", sid, rs[0]["source_code"], latest_period,
                                  Jsonb({"change": latest, "robust_z": round(z, 2), "history": len(changes) - 1})))
            n += 1
    return n


def check_revisions(conn, abs_pp: float, rel_pct: float, window_days: int) -> int:
    rows = conn.execute(
        """SELECT r.*, s.unit FROM v_revisions r JOIN series s ON s.id = r.series_id
           WHERE r.retrieved_at > now() - make_interval(days => %s)
             AND r.previous_value IS NOT NULL AND r.new_value IS NOT NULL""", (window_days,)).fetchall()
    n = 0
    for r in rows:
        delta = r["new_value"] - r["previous_value"]
        if is_percent_unit(r["unit"]):
            big = abs(delta) > abs_pp
        else:
            big = r["previous_value"] != 0 and abs(delta / r["previous_value"]) * 100 > rel_pct
        if big:
            conn.execute(UPSERT, ("large_revision", "info", r["series_id"], r["source_code"], r["period"],
                                  Jsonb({"vintage": r["vintage"], "previous": r["previous_value"],
                                         "new": r["new_value"], "revision": r["revision"]})))
            n += 1
    return n


def check_sources(conn) -> int:
    n = 0
    for r in conn.execute("SELECT * FROM v_source_health WHERE last_run_at IS NOT NULL").fetchall():
        if r["last_status"] == "failed":
            conn.execute(UPSERT, ("source_failure", "critical", None, r["source_code"], None,
                                  Jsonb({"message": r["last_message"], "last_run_at": str(r["last_run_at"])})))
            n += 1
        else:
            conn.execute("""UPDATE quality_issue SET resolved_at = now() WHERE check_name = 'source_failure'
                            AND source_code = %s AND resolved_at IS NULL""", (r["source_code"],))
    return n


def validate(conn, cfg: Config) -> dict:
    v = cfg.validation
    result = {
        "stale": check_stale(conn),
        "outlier_change": check_outliers(conn, float(v.get("outlier_z", 5.0)), int(v.get("min_history", 12))),
        "large_revision": check_revisions(conn, float(v.get("revision_abs_pp", 0.5)),
                                          float(v.get("revision_rel_pct", 2.0)),
                                          int(v.get("revision_window_days", 30))),
        "source_failure": check_sources(conn),
    }
    conn.commit()
    log.info("validation: %s", result)
    return result
