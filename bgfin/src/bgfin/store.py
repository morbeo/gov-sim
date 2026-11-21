"""PostgreSQL access: migrations, config sync, run log and versioned writes."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from importlib import resources

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .config import Config, SeriesSpec
from .model import Obs, SeriesData
from .periods import parse_period

log = logging.getLogger(__name__)

DEFAULT_DSN = "postgresql://bgfin:bgfin@localhost:5432/bgfin"
FREQS = {"D", "B", "W", "M", "Q", "S", "A"}


def dsn_from_env() -> str:
    return os.environ.get("BGFIN_DSN", DEFAULT_DSN)


def connect(dsn: str | None = None) -> psycopg.Connection:
    conn = psycopg.connect(dsn or dsn_from_env(), row_factory=dict_row)
    conn.execute("SET search_path = bgfin, public")
    return conn


def migrate(conn: psycopg.Connection) -> list[str]:
    applied = []
    sql_dir = resources.files("bgfin") / "sql"
    for item in sorted(sql_dir.iterdir(), key=lambda p: p.name):
        if item.name.endswith(".sql"):
            conn.execute(item.read_text(encoding="utf-8"))
            applied.append(item.name)
    conn.execute("SET search_path = bgfin, public")
    conn.commit()
    return applied


def sync_config(conn: psycopg.Connection, cfg: Config) -> dict:
    with conn.cursor() as cur:
        for s in cfg.sources.values():
            cur.execute(
                """INSERT INTO source (code, name, institution, homepage, api_base, formats, notes, enabled,
                                      interval_hours, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, institution = EXCLUDED.institution,
                     homepage = EXCLUDED.homepage, api_base = EXCLUDED.api_base, formats = EXCLUDED.formats,
                     notes = EXCLUDED.notes, enabled = EXCLUDED.enabled, interval_hours = EXCLUDED.interval_hours,
                     updated_at = now()""",
                (s.code, s.name, s.institution, s.homepage, s.api_base, s.formats, s.notes, s.enabled,
                 s.interval_hours))
        for i in cfg.indicators.values():
            cur.execute(
                """INSERT INTO indicator (code, name, category, description, unit, frequency, priority, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                   ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category,
                     description = EXCLUDED.description, unit = EXCLUDED.unit, frequency = EXCLUDED.frequency,
                     priority = EXCLUDED.priority, updated_at = now()""",
                (i.code, i.name, i.category, (i.description or "").strip(), i.unit, i.frequency, i.priority))
        cur.execute("DELETE FROM alert_threshold")
        for t in cfg.thresholds:
            cur.execute(
                """INSERT INTO alert_threshold (name, indicator_code, geo, frequency, measure, operator,
                                                threshold, severity, description)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (t["name"], t["indicator"], t.get("geo", "BG"), t.get("frequency"), t.get("measure", "level"),
                 t["operator"], float(t["threshold"]), t.get("severity", "warning"), t.get("description")))
    conn.commit()
    return {"sources": len(cfg.sources), "indicators": len(cfg.indicators), "thresholds": len(cfg.thresholds)}


# ---------------------------------------------------------------- run log

def start_run(conn, source: str, mode: str) -> tuple[int, datetime]:
    row = conn.execute(
        "INSERT INTO collection_run (source_code, mode) VALUES (%s, %s) RETURNING id, started_at",
        (source, mode)).fetchone()
    conn.commit()
    return row["id"], row["started_at"]


def finish_run(conn, run_id: int, status: str, counts: dict, errors: list[dict], message: str = "") -> None:
    conn.execute(
        """UPDATE collection_run SET finished_at = now(), status = %s, requests = %s, series_seen = %s,
              obs_new = %s, obs_revised = %s, obs_unchanged = %s, errors = %s, message = %s
           WHERE id = %s""",
        (status, counts.get("requests", 0), counts.get("series", 0), counts.get("new", 0),
         counts.get("revised", 0), counts.get("unchanged", 0), Jsonb(errors), message[:2000], run_id))
    conn.commit()


def last_success(conn, source: str, mode: str | None = None,
                 statuses: tuple[str, ...] = ("ok", "partial", "skipped")) -> datetime | None:
    q = "SELECT max(started_at) AS t FROM collection_run WHERE source_code = %s AND status = ANY(%s)"
    args: tuple = (source, list(statuses))
    if mode:
        q += " AND mode = %s"
        args += (mode,)
    return conn.execute(q, args).fetchone()["t"]


def load_state(conn, source: str) -> dict:
    rows = conn.execute("SELECT * FROM dataset_state WHERE source_code = %s", (source,)).fetchall()
    return {r["dataset"]: r for r in rows}


def save_state(conn, source: str, state: dict[str, dict], checked_at: datetime) -> None:
    for dataset, st in state.items():
        conn.execute(
            """INSERT INTO dataset_state (source_code, dataset, etag, last_modified, source_updated, checked_at)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (source_code, dataset) DO UPDATE SET etag = EXCLUDED.etag,
                 last_modified = EXCLUDED.last_modified, source_updated = EXCLUDED.source_updated,
                 checked_at = EXCLUDED.checked_at""",
            (source, dataset, st.get("etag"), st.get("last_modified"), st.get("source_updated"), checked_at))


# ---------------------------------------------------------------- series and observations

def upsert_series(conn, spec: SeriesSpec, sd: SeriesData) -> int:
    freq = spec.frequency if spec.frequency in FREQS else None
    if sd.frequency in FREQS:
        freq = sd.frequency
    if spec.frequency == "B" and freq == "D":
        freq = "B"
    attrs = dict(sd.attrs)
    if spec.max_lag_days:
        attrs["max_lag_days"] = spec.max_lag_days
    row = conn.execute(
        """INSERT INTO series (source_code, source_key, dataset, indicator_code, role, geo, geo_scope, label,
                               unit, frequency, adjustment, is_forecast, attrs, last_checked_at, source_updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), %s)
           ON CONFLICT (source_code, source_key) DO UPDATE SET
             dataset = EXCLUDED.dataset, indicator_code = EXCLUDED.indicator_code, role = EXCLUDED.role,
             geo = EXCLUDED.geo, geo_scope = EXCLUDED.geo_scope, label = EXCLUDED.label, unit = EXCLUDED.unit,
             frequency = EXCLUDED.frequency, adjustment = EXCLUDED.adjustment,
             is_forecast = EXCLUDED.is_forecast, attrs = EXCLUDED.attrs, last_checked_at = now(),
             source_updated_at = coalesce(EXCLUDED.source_updated_at, series.source_updated_at)
           RETURNING id""",
        (spec.source, sd.source_key, sd.dataset, spec.indicator, spec.role, sd.geo, spec.geo_scope,
         sd.label[:500], spec.unit or sd.unit or "", freq or "A", spec.adjustment or sd.adjustment or "NSA",
         spec.is_forecast or any(o.obs_type == "forecast" for o in sd.observations),
         Jsonb(attrs), sd.published_at)).fetchone()
    return row["id"]


def same_value(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def save_observations(conn, series_id: int, observations: list[Obs], run_id: int | None,
                      published_at: datetime | None, full_history: bool = False) -> dict:
    """Write observations without overwriting history.

    New (period, vintage) -> revision 0. Changed value, status or type ->
    current row is superseded and a new row with revision + 1 is added.
    Unchanged -> nothing is written.
    """
    now = datetime.now(timezone.utc)
    current = {
        (r["period"], r["vintage"]): r
        for r in conn.execute(
            """SELECT id, period, vintage, value, status, obs_type, revision FROM observation
               WHERE series_id = %s AND superseded_at IS NULL""", (series_id,)).fetchall()
    }
    incoming: dict = {}
    for o in observations:
        try:
            period, _ = parse_period(o.period_label)
        except ValueError:
            log.warning("series %s: skipping unparseable period %r", series_id, o.period_label)
            continue
        incoming[(period, o.vintage)] = o

    inserts, supersede = [], []
    counts = {"new": 0, "revised": 0, "unchanged": 0, "vanished": 0}
    for key, o in incoming.items():
        cur = current.get(key)
        if cur is None:
            inserts.append((series_id, key[0], o.period_label, o.vintage, o.value, o.status, o.obs_type, 0,
                            now, published_at, run_id))
            counts["new"] += 1
        elif (same_value(cur["value"], o.value) and (cur["status"] or None) == (o.status or None)
              and cur["obs_type"] == o.obs_type):
            counts["unchanged"] += 1
        else:
            supersede.append(cur["id"])
            inserts.append((series_id, key[0], o.period_label, o.vintage, o.value, o.status, o.obs_type,
                            cur["revision"] + 1, now, published_at, run_id))
            counts["revised"] += 1

    vanished = []
    if full_history:
        vintages = {k[1] for k in incoming}
        vanished = [(k, r) for k, r in current.items() if k not in incoming and k[1] in vintages]
        counts["vanished"] = len(vanished)

    with conn.cursor() as cur:
        if supersede:
            cur.execute("UPDATE observation SET superseded_at = %s WHERE id = ANY(%s)", (now, supersede))
        if inserts:
            cur.executemany(
                """INSERT INTO observation (series_id, period, period_label, vintage, value, status, obs_type,
                                            revision, retrieved_at, published_at, run_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""", inserts)
            cur.execute("UPDATE series SET last_changed_at = %s WHERE id = %s", (now, series_id))
        for (period, vintage), r in vanished:
            # Not deleted: the source dropped a value we hold. Flag it for review.
            cur.execute(
                """INSERT INTO quality_issue (check_name, severity, series_id, period, detail)
                   VALUES ('vanished_observation', 'warning', %s, %s, %s)
                   ON CONFLICT (check_name, coalesce(source_code, ''), coalesce(series_id, 0),
                                coalesce(period, '1900-01-01'::date))
                     WHERE resolved_at IS NULL DO UPDATE SET last_detected_at = now()""",
                (series_id, period, Jsonb({"vintage": vintage, "value": r["value"], "obs_id": r["id"]})))
    return counts


def dumps(obj) -> str:
    return json.dumps(obj, default=str)
