"""bgfin command line interface.

Common use:
  bgfin init                      create/upgrade the schema and load config
  bgfin backfill                  read full history from every enabled source
  bgfin collect                   incremental update (full refresh when due)
  bgfin collect eurostat ecb      only some sources
  bgfin run                       scheduler loop (what the container runs)
  bgfin status                    source health, freshness, open issues
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from . import __version__, config, store
from .collect import collect
from .derive import derive
from .validate import validate

log = logging.getLogger("bgfin")


def _post(conn, cfg, args) -> None:
    if not getattr(args, "no_post", False):
        derive(conn, cfg)
        validate(conn, cfg)


def cmd_init(conn, cfg, args):
    applied = store.migrate(conn)
    synced = store.sync_config(conn, cfg)
    return {"migrations": applied, **synced}


def cmd_sync(conn, cfg, args):
    return store.sync_config(conn, cfg)


def cmd_collect(conn, cfg, args):
    mode = "backfill" if args.command == "backfill" or getattr(args, "backfill", False) else (
        "incremental" if getattr(args, "incremental", False) else None)
    _check_names(args.sources, cfg.sources, "source")
    _check_names(args.indicator, cfg.indicators, "indicator")
    store.sync_config(conn, cfg)
    results = collect(conn, cfg, args.sources or None, mode, args.indicator or None, args.dry_run)
    if not args.dry_run:
        _post(conn, cfg, args)
    return results


def cmd_derive(conn, cfg, args):
    return derive(conn, cfg, args.metric or None)


def cmd_validate(conn, cfg, args):
    return validate(conn, cfg)


def cmd_run(conn, cfg, args):
    """Collect every source whose interval has elapsed; loop unless --once."""
    store.migrate(conn)
    store.sync_config(conn, cfg)
    while True:
        due = []
        now = datetime.now(timezone.utc)
        for code, src in cfg.sources.items():
            if not src.enabled or not cfg.specs(code):
                continue
            last = store.last_success(conn, code)
            if last is None or now - last >= timedelta(hours=src.interval_hours):
                due.append(code)
        if due:
            log.info("due: %s", ", ".join(due))
            collect(conn, cfg, due)
            _post(conn, cfg, args)
        else:
            log.info("nothing due")
        if args.once:
            return {"collected": due}
        time.sleep(args.tick * 60)


def cmd_status(conn, cfg, args):
    health = conn.execute("SELECT * FROM v_source_health ORDER BY source_code").fetchall()
    fresh = conn.execute(
        """SELECT s.source_code, count(*) AS series, count(*) FILTER (WHERE f.is_stale) AS stale,
                  max(f.latest_period) AS newest_period
           FROM series s LEFT JOIN v_freshness f ON f.series_id = s.id
           GROUP BY s.source_code ORDER BY s.source_code""").fetchall()
    issues = conn.execute(
        """SELECT check_name, severity, count(*) AS open FROM quality_issue WHERE resolved_at IS NULL
           GROUP BY 1, 2 ORDER BY 1""").fetchall()
    obs = conn.execute(
        """SELECT count(*) AS total, count(*) FILTER (WHERE superseded_at IS NULL) AS current,
                  count(*) FILTER (WHERE revision > 0) AS revisions FROM observation""").fetchone()
    if args.json:
        return {"sources": health, "freshness": fresh, "issues": issues, "observations": obs}
    f = {r["source_code"]: r for r in fresh}
    print(f"{'source':<10} {'last run':<17} {'status':<8} {'series':>6} {'stale':>5} {'newest':<11} fails/7d")
    for h in health:
        r = f.get(h["source_code"], {})
        last = h["last_run_at"].strftime("%Y-%m-%d %H:%M") if h["last_run_at"] else "never"
        print(f"{h['source_code']:<10} {last:<17} {h['last_status'] or '-':<8} {r.get('series', 0):>6} "
              f"{r.get('stale', 0):>5} {str(r.get('newest_period') or '-'):<11} {h['failures_7d']}")
    print(f"\nobservations: {obs['current']} current, {obs['revisions']} revisions, {obs['total']} rows stored")
    if issues:
        print("open issues: " + ", ".join(f"{i['check_name']} ({i['severity']}): {i['open']}" for i in issues))
    return None


def cmd_issues(conn, cfg, args):
    if args.resolve:
        conn.execute("UPDATE quality_issue SET resolved_at = now() WHERE id = ANY(%s) AND resolved_at IS NULL",
                     (args.resolve,))
        conn.commit()
        return {"resolved": args.resolve}
    rows = conn.execute(
        """SELECT q.id, q.check_name, q.severity, coalesce(s.source_code, q.source_code) AS source,
                  s.indicator_code, s.geo, q.period, q.detail, q.last_detected_at
           FROM quality_issue q LEFT JOIN series s ON s.id = q.series_id
           WHERE q.resolved_at IS NULL ORDER BY q.severity, q.check_name, q.id LIMIT %s""",
        (args.limit,)).fetchall()
    if args.json:
        return rows
    for r in rows:
        print(f"{r['id']:>6} {r['severity']:<8} {r['check_name']:<20} {r['source'] or '':<9} "
              f"{r['indicator_code'] or '':<24} {r['geo'] or '':<9} {r['period'] or '':<10} {json.dumps(r['detail'])}")
    return None


def cmd_as_of(conn, cfg, args):
    rows = conn.execute(
        """SELECT s.source_code, s.geo, s.source_key, a.period_label, a.vintage, a.value, a.status,
                  a.obs_type, a.revision, a.retrieved_at
           FROM obs_as_of(%s) a JOIN series s ON s.id = a.series_id
           WHERE s.indicator_code = %s AND s.geo = %s
             AND (%s::text IS NULL OR s.source_code = %s)
           ORDER BY s.source_code, s.source_key, a.period DESC, a.vintage LIMIT %s""",
        (args.timestamp, args.indicator, args.geo, args.source, args.source, args.limit)).fetchall()
    if args.json:
        return rows
    for r in rows:
        print(f"{r['source_code']:<9} {r['period_label']:<10} {r['vintage'] or '-':<16} {r['value']!s:<12} "
              f"{r['obs_type']:<12} rev {r['revision']}  retrieved {r['retrieved_at']:%Y-%m-%d %H:%M}")
    return None


def cmd_catalogue(conn, cfg, args):
    from .catalogue import render
    text = render(cfg)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"wrote {args.output}", file=sys.stderr)
    return None


def _check_names(given, known, what):
    unknown = [g for g in (given or []) if g not in known]
    if unknown:
        raise SystemExit(f"unknown {what}: {', '.join(unknown)} (known: {', '.join(known)})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bgfin", description="Bulgarian economic data collector.",
                                epilog="Database: --dsn or BGFIN_DSN (default %s)." % store.DEFAULT_DSN)
    p.add_argument("--version", action="version", version=f"bgfin {__version__}")
    p.add_argument("--dsn", help="PostgreSQL connection string")
    p.add_argument("--config-dir", help="directory with sources.yaml, indicators.yaml (default: ./config)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings and errors only")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    sub = p.add_subparsers(dest="command", required=True, metavar="COMMAND")

    sub.add_parser("init", help="create or upgrade the schema and load config").set_defaults(func=cmd_init)
    sub.add_parser("sync-config", help="load config/*.yaml into the database").set_defaults(func=cmd_sync)

    for name, help_ in (("collect", "collect sources (incremental; full refresh when due)"),
                        ("backfill", "collect full history")):
        c = sub.add_parser(name, help=help_)
        c.add_argument("sources", nargs="*", metavar="SOURCE", help="sources to collect (default: all enabled)")
        c.add_argument("-i", "--indicator", action="append", metavar="CODE", help="limit to an indicator (repeatable)")
        c.add_argument("-n", "--dry-run", action="store_true", help="fetch and parse, write nothing")
        c.add_argument("--no-post", action="store_true", help="skip derive and validate afterwards")
        if name == "collect":
            g = c.add_mutually_exclusive_group()
            g.add_argument("--backfill", action="store_true", help="force full history")
            g.add_argument("--incremental", action="store_true", help="force incremental, even if a refresh is due")
        c.set_defaults(func=cmd_collect)

    d = sub.add_parser("derive", help="recompute derived metrics")
    d.add_argument("-m", "--metric", action="append", help="only this metric (repeatable)")
    d.set_defaults(func=cmd_derive)
    sub.add_parser("validate", help="run data checks and anomaly detection").set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="scheduler: collect sources when their interval is due")
    r.add_argument("--once", action="store_true", help="run due sources once and exit (for cron/systemd)")
    r.add_argument("--tick", type=float, default=15, metavar="MIN", help="minutes between checks (default 15)")
    r.set_defaults(func=cmd_run)

    sub.add_parser("status", help="source health, freshness and open issues").set_defaults(func=cmd_status)

    i = sub.add_parser("issues", help="list or resolve open data-quality issues")
    i.add_argument("--resolve", type=int, nargs="+", metavar="ID", help="mark issues as reviewed")
    i.add_argument("--limit", type=int, default=100)
    i.set_defaults(func=cmd_issues)

    a = sub.add_parser("as-of", help="show an indicator as the database knew it at a point in time")
    a.add_argument("timestamp", help="ISO timestamp, e.g. 2026-11-01T00:00Z")
    a.add_argument("indicator")
    a.add_argument("--geo", default="BG")
    a.add_argument("--source")
    a.add_argument("--limit", type=int, default=40)
    a.set_defaults(func=cmd_as_of)

    k = sub.add_parser("catalogue", help="write the indicator catalogue as Markdown")
    k.add_argument("-o", "--output", default="docs/indicator-catalogue.md", help="file, or - for stdout")
    k.set_defaults(func=cmd_catalogue, no_db=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.WARNING if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        cfg = config.load(args.config_dir)
    except config.ConfigError as exc:
        print(f"bgfin: config error: {exc}", file=sys.stderr)
        return 2
    if getattr(args, "no_db", False):
        args.func(None, cfg, args)
        return 0
    try:
        conn = store.connect(args.dsn)
    except Exception as exc:
        print(f"bgfin: cannot connect to database: {exc}", file=sys.stderr)
        return 2
    try:
        result = args.func(conn, cfg, args)
    except KeyboardInterrupt:
        return 130
    finally:
        conn.close()
    if result is not None:
        if args.json or not isinstance(result, list):
            print(json.dumps(result, default=str, indent=2))
        else:
            for r in result:
                print(json.dumps(r, default=str))
    if isinstance(result, list) and any(r.get("status") == "failed" for r in result if isinstance(r, dict)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
