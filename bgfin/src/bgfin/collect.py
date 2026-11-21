"""Run connectors and store their output, one collection_run per source."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import store
from .config import Config
from .connectors import REGISTRY
from .model import SourceError

log = logging.getLogger(__name__)


def choose_mode(conn, cfg: Config, source: str, requested: str | None) -> str:
    """Incremental by default; backfill when the source has never been fully
    read or its full_refresh_days have passed."""
    if requested:
        return requested
    last_full = store.last_success(conn, source, "backfill", statuses=("ok",))
    days = cfg.sources[source].full_refresh_days
    if last_full is None or datetime.now(timezone.utc) - last_full > timedelta(days=days):
        return "backfill"
    return "incremental"


def collect_source(conn, cfg: Config, source: str, mode: str | None = None,
                   indicators: list[str] | None = None, dry_run: bool = False) -> dict:
    src = cfg.sources[source]
    if source not in REGISTRY:
        raise SourceError(f"no connector for source {source!r}")
    specs = cfg.specs(source, indicators)
    mode = choose_mode(conn, cfg, source, mode)
    run_id, started = (None, datetime.now(timezone.utc)) if dry_run else store.start_run(conn, source, mode)
    connector = REGISTRY[source](src, state=store.load_state(conn, source))
    counts = {"series": 0, "new": 0, "revised": 0, "unchanged": 0, "vanished": 0}
    status, message = "ok", ""
    try:
        for spec, sd in connector.fetch(specs, mode):
            counts["series"] += 1
            if dry_run:
                log.info("%s %s %s: %d observations", source, spec.indicator, sd.source_key, len(sd.observations))
                continue
            series_id = store.upsert_series(conn, spec, sd)
            c = store.save_observations(conn, series_id, sd.observations, run_id, sd.published_at,
                                        full_history=(mode == "backfill"))
            for k, v in c.items():
                counts[k] += v
            conn.commit()
        if not dry_run:
            store.save_state(conn, source, connector.new_state, started)
            conn.commit()
    except Exception as exc:          # keep the run log truthful, then re-raise
        conn.rollback()
        connector.errors.append({"request": "collector", "error": f"{type(exc).__name__}: {exc}"})
        status, message = "failed", str(exc)
        if not dry_run:
            store.finish_run(conn, run_id, status, {**counts, "requests": connector.http.requests},
                             connector.errors, message)
        raise
    if connector.errors:
        status = "partial" if counts["series"] else "failed"
        message = f"{len(connector.errors)} request(s) failed"
    elif counts["series"] == 0 and connector.not_modified:
        status, message = "skipped", "source reports no change"
    if indicators and mode == "backfill" and status == "ok":
        status = "partial"
        message = "backfill limited to " + ", ".join(indicators)
    counts["requests"] = connector.http.requests
    if not dry_run:
        store.finish_run(conn, run_id, status, counts, connector.errors, message)
    log.info("%s %s: %s %s", source, mode, status, counts)
    return {"source": source, "mode": mode, "status": status, **counts, "errors": connector.errors}


def collect(conn, cfg: Config, sources: list[str] | None = None, mode: str | None = None,
            indicators: list[str] | None = None, dry_run: bool = False) -> list[dict]:
    results = []
    for code, src in cfg.sources.items():
        if sources and code not in sources:
            continue
        if not src.enabled:
            if sources:
                log.warning("%s is disabled in sources.yaml", code)
            continue
        if not cfg.specs(code, indicators):
            continue
        try:
            results.append(collect_source(conn, cfg, code, mode, indicators, dry_run))
        except Exception as exc:
            log.exception("%s failed", code)
            results.append({"source": code, "status": "failed", "errors": [{"error": str(exc)}]})
    return results
