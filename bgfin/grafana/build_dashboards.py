#!/usr/bin/env python3
"""Generate the Grafana dashboard JSON files in grafana/dashboards/.

Dashboards are code: edit this file and run
    python3 grafana/build_dashboards.py
then restart (or wait a minute for) Grafana to pick the files up.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DS = {"type": "grafana-postgresql-datasource", "uid": "bgfin-pg"}
OUT = Path(__file__).resolve().parent / "dashboards"

# (indicator, frequency, role filter, title) for the Bulgaria overview.
PRIORITY = [
    ("gdp_growth", "Q", "primary", "Real GDP growth, y/y"),
    ("gdp_growth_qoq", "Q", "primary", "Real GDP growth, q/q"),
    ("hicp_inflation", "M", "primary", "HICP inflation"),
    ("core_inflation", "M", "primary", "Core inflation"),
    ("real_wage_growth", "Q", "primary", "Real wage growth"),
    ("unemployment_rate", "M", "primary", "Unemployment rate"),
    ("gov_balance", "A", "benchmark", "Government balance, % GDP"),
    ("gov_debt", "A", "benchmark", "Government debt, % GDP"),
    ("household_credit_growth", "M", "primary", "Household credit growth"),
    ("current_account", "Q", "primary", "Current account, % GDP"),
    ("house_price_growth", "Q", "primary", "House price growth"),
]


class Grid:
    """Places panels left to right on Grafana's 24-column grid."""

    def __init__(self):
        self.x = self.y = self.row_h = 0
        self.next_id = 1

    def place(self, panel: dict, w: int, h: int) -> dict:
        if self.x + w > 24:
            self.x, self.y = 0, self.y + self.row_h
            self.row_h = 0
        panel["gridPos"] = {"x": self.x, "y": self.y, "w": w, "h": h}
        panel["id"] = self.next_id
        self.next_id += 1
        self.x += w
        self.row_h = max(self.row_h, h)
        return panel

    def row(self, title: str) -> dict:
        if self.x:
            self.x, self.y = 0, self.y + self.row_h
        p = {"type": "row", "title": title, "collapsed": False, "panels": [],
             "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1}, "id": self.next_id}
        self.next_id += 1
        self.y += 1
        self.row_h = 0
        return p


def target(sql: str, fmt: str = "time_series", ref: str = "A") -> dict:
    return {"refId": ref, "datasource": DS, "rawQuery": True, "editorMode": "code", "format": fmt, "rawSql": sql}


def timeseries(title: str, sqls: list[str], unit: str = "none", desc: str = "", bars: bool = False,
               decimals: int | None = 1) -> dict:
    custom = {"lineWidth": 2, "fillOpacity": 0 if not bars else 80, "showPoints": "never",
              "spanNulls": True, "drawStyle": "bars" if bars else "line", "axisCenteredZero": False}
    defaults = {"unit": unit, "custom": custom}
    if decimals is not None:
        defaults["decimals"] = decimals
    return {"type": "timeseries", "title": title, "description": desc, "datasource": DS,
            "targets": [target(s, ref=chr(65 + i)) for i, s in enumerate(sqls)],
            "fieldConfig": {"defaults": defaults, "overrides": [
                {"matcher": {"id": "byRegexp", "options": "^BG.*"},
                 "properties": [{"id": "custom.lineWidth", "value": 4}]}]},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title: str, sql: str, unit: str = "percent", desc: str = "") -> dict:
    return {"type": "stat", "title": title, "description": desc, "datasource": DS,
            "targets": [target(sql)],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 1, "color": {"mode": "fixed", "fixedColor": "blue"}},
                            "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                        "colorMode": "none", "graphMode": "area", "textMode": "value", "justifyMode": "center"}}


def table(title: str, sql: str, desc: str = "", overrides: list | None = None) -> dict:
    return {"type": "table", "title": title, "description": desc, "datasource": DS,
            "targets": [target(sql, fmt="table")],
            "fieldConfig": {"defaults": {"custom": {"filterable": True, "cellOptions": {"type": "auto"}}},
                            "overrides": overrides or []},
            "options": {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}}


def barchart(title: str, sql: str, unit: str = "none") -> dict:
    return {"type": "barchart", "title": title, "datasource": DS, "targets": [target(sql, fmt="table")],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": 1}, "overrides": []},
            "options": {"orientation": "horizontal", "xField": "geo", "showValue": "always",
                        "legend": {"showLegend": False}}}


def var_query(name: str, label: str, sql: str, multi=False, include_all=False, current=None) -> dict:
    v = {"name": name, "label": label, "type": "query", "datasource": DS, "query": sql, "definition": sql,
         "refresh": 1, "multi": multi, "includeAll": include_all, "sort": 0}
    if current:
        v["current"] = {"text": current, "value": current}
    return v


def dashboard(uid: str, title: str, panels: list, variables: list | None = None, time_from="now-20y",
              time_to="now", desc: str = "") -> dict:
    return {"uid": uid, "title": title, "description": desc, "tags": ["bgfin"], "timezone": "browser",
            "style": "light", "editable": False, "graphTooltip": 1, "schemaVersion": 39,
            "time": {"from": time_from, "to": time_to}, "refresh": "1h",
            "templating": {"list": variables or []}, "panels": panels,
            "links": [{"type": "dashboards", "tags": ["bgfin"], "asDropdown": True, "title": "bgfin dashboards"}]}


def series_sql(indicator: str, freq: str, role: str, geos: list[str]) -> str:
    geo_list = ", ".join(f"'{g}'" for g in geos)
    return (f"SELECT period::timestamptz AS time, value, geo AS metric FROM v_indicator_values "
            f"WHERE indicator_code = '{indicator}' AND frequency = '{freq}' AND role = '{role}' "
            f"AND vintage = '' AND geo IN ({geo_list}) AND $__timeFilter(period) ORDER BY 1")


# ------------------------------------------------------------------ dashboards

def overview() -> dict:
    g = Grid()
    panels = [g.row("Latest values, Bulgaria")]
    for ind, freq, role, title in PRIORITY:
        sql = (f"SELECT period::timestamptz AS time, value FROM v_indicator_values WHERE indicator_code = '{ind}' "
               f"AND geo = 'BG' AND frequency = '{freq}' AND role = '{role}' AND vintage = '' "
               f"AND period > now() - interval '6 years' ORDER BY 1")
        panels.append(g.place(stat(title, sql, desc=f"Indicator {ind}, frequency {freq}. Sparkline: last 6 years."), 4, 4))
    latest = """
SELECT DISTINCT ON (c.indicator_code) i.category, i.name AS indicator, c.period_label AS period,
       round(c.value::numeric, 2) AS value, round(c.pop_diff::numeric, 2) AS "change vs previous",
       round(c.yoy_diff::numeric, 2) AS "change vs year ago", c.unit, c.source_code AS source, c.obs_type AS status
FROM v_changes c JOIN indicator i ON i.code = c.indicator_code
WHERE c.geo = 'BG' AND c.role IN ('primary', 'benchmark') AND c.frequency = i.frequency AND c.value IS NOT NULL
ORDER BY c.indicator_code, c.period DESC, (c.role = 'primary') DESC"""
    panels.append(g.place(table("Latest observations, Bulgaria", latest,
                                "Most recent value of every indicator at its canonical frequency. Changes are "
                                "differences (percentage points for rates)."), 24, 18))
    panels.append(g.row("History: Bulgaria, euro area, EU"))
    for ind, freq, role, title in PRIORITY:
        geos = ["BG", "EA21", "EU27_2020", "EA"]
        panels.append(g.place(timeseries(title, [series_sql(ind, freq, role, geos)], unit="percent"), 12, 8))
    th = """SELECT name, description, period_label AS period, round(observed::numeric, 2) AS observed,
       operator || ' ' || threshold AS rule, breached FROM v_threshold_status ORDER BY breached DESC, name"""
    panels.append(g.row("Alert thresholds"))
    panels.append(g.place(table("Threshold status (config/alerts.yaml)", th,
                                overrides=[{"matcher": {"id": "byName", "options": "breached"},
                                            "properties": [{"id": "custom.cellOptions",
                                                            "value": {"type": "color-background"}},
                                                           {"id": "mappings", "value": [
                                                               {"type": "value", "options": {
                                                                   "true": {"color": "orange", "text": "breached"},
                                                                   "false": {"color": "green", "text": "ok"}}}]}]}]),
                          24, 10))
    return dashboard("bgfin-overview", "Bulgaria economy: overview", panels,
                     desc="Current values and history of the priority indicators.")


def explorer() -> dict:
    g = Grid()
    variables = [
        var_query("indicator", "Indicator",
                  "SELECT code AS __value, name || ' (' || code || ')' AS __text FROM indicator ORDER BY category, code",
                  current="hicp_inflation"),
        var_query("freq", "Frequency",
                  "SELECT DISTINCT frequency FROM series WHERE indicator_code = '$indicator' "
                  "UNION SELECT DISTINCT frequency FROM derived_observation WHERE indicator_code = '$indicator'"),
        var_query("geo", "Geography", "SELECT DISTINCT geo FROM v_indicator_values WHERE indicator_code = '$indicator' "
                  "ORDER BY 1", multi=True, current="BG"),
        var_query("role", "Role", "SELECT DISTINCT role FROM v_indicator_values WHERE indicator_code = '$indicator' "
                  "AND vintage = ''", multi=True, include_all=True),
    ]
    base = ("FROM v_indicator_values WHERE indicator_code = '$indicator' AND frequency = '$freq' "
            "AND geo IN ($geo) AND role IN ($role) AND vintage = ''")
    panels = [
        g.place(timeseries("$indicator: values", [
            f"SELECT period::timestamptz AS time, value, geo || ' ' || source_code || ' (' || role || ')' AS metric "
            f"{base} AND $__timeFilter(period) ORDER BY 1"]), 24, 10),
        g.place(timeseries("Change on a year earlier (difference)", [
            "SELECT period::timestamptz AS time, yoy_diff AS value, geo || ' ' || source_code AS metric FROM v_changes "
            "WHERE indicator_code = '$indicator' AND frequency = '$freq' AND geo IN ($geo) AND role IN ($role) "
            "AND $__timeFilter(period) ORDER BY 1"], bars=False), 12, 8),
        g.place(timeseries("Change on a year earlier (%)",
                           ["SELECT period::timestamptz AS time, yoy_pct AS value, geo || ' ' || source_code AS metric "
                            "FROM v_changes WHERE indicator_code = '$indicator' AND frequency = '$freq' "
                            "AND geo IN ($geo) AND role IN ($role) AND $__timeFilter(period) ORDER BY 1"],
                           unit="percent", desc="Relative change; meaningful for levels and indices, not for rates."),
                12, 8),
        g.place(table("Values", "SELECT geo, source_code AS source, role, period_label AS period, "
                      "round(value::numeric, 3) AS value, obs_type AS status, unit, origin "
                      f"{base} ORDER BY period DESC, geo LIMIT 500"), 12, 12),
        g.place(table("Revisions", "SELECT geo, source_code AS source, period_label AS period, vintage, revision, "
                      "previous_value, new_value, round(delta::numeric, 3) AS delta, previous_status, new_status, "
                      "retrieved_at FROM v_revisions WHERE indicator_code = '$indicator' AND geo IN ($geo) "
                      "ORDER BY retrieved_at DESC LIMIT 500",
                      "Every change to a value we had already stored. Old values are kept, never overwritten."),
                12, 12),
    ]
    return dashboard("bgfin-explorer", "Indicator explorer", panels, variables,
                     desc="Any indicator, any source, any geography; values, changes and revisions.")


def peers() -> dict:
    g = Grid()
    variables = [
        var_query("indicator", "Indicator",
                  "SELECT DISTINCT i.code AS __value, i.name AS __text FROM indicator i JOIN series s "
                  "ON s.indicator_code = i.code WHERE s.role = 'primary' AND s.geo <> 'BG' ORDER BY 2",
                  current="hicp_inflation"),
        var_query("freq", "Frequency", "SELECT DISTINCT frequency FROM series WHERE indicator_code = '$indicator' "
                  "AND role IN ('primary', 'benchmark')"),
        var_query("geo", "Compare with", "SELECT DISTINCT geo FROM series WHERE indicator_code = '$indicator' "
                  "AND geo <> 'BG' ORDER BY 1", multi=True, include_all=True),
    ]
    role = "role IN ('primary', 'benchmark')"
    panels = [
        g.place(timeseries("Bulgaria vs peers", [
            "SELECT period::timestamptz AS time, value, geo AS metric FROM v_indicator_values "
            f"WHERE indicator_code = '$indicator' AND frequency = '$freq' AND {role} AND vintage = '' "
            "AND origin = 'raw' AND (geo = 'BG' OR geo IN ($geo)) AND $__timeFilter(period) ORDER BY 1"],
            desc="Bulgaria drawn with a thicker line."), 24, 11),
        g.place(barchart("Latest value by geography", (
            "SELECT geo, value FROM (SELECT DISTINCT ON (geo) geo, value, period FROM v_indicator_values "
            f"WHERE indicator_code = '$indicator' AND frequency = '$freq' AND {role} AND vintage = '' "
            "AND origin = 'raw' AND (geo = 'BG' OR geo IN ($geo)) AND value IS NOT NULL "
            "ORDER BY geo, period DESC) t ORDER BY value DESC")), 12, 12),
        g.place(table("Bulgaria minus peer, latest common period", (
            "WITH v AS (SELECT geo, period, value FROM v_indicator_values WHERE indicator_code = '$indicator' "
            f"AND frequency = '$freq' AND {role} AND vintage = '' AND origin = 'raw' AND value IS NOT NULL), "
            "p AS (SELECT DISTINCT ON (o.geo) o.geo, o.period, o.value AS peer, b.value AS bg FROM v o "
            "JOIN v b ON b.geo = 'BG' AND b.period = o.period WHERE o.geo IN ($geo) ORDER BY o.geo, o.period DESC) "
            "SELECT geo, period, round(bg::numeric, 2) AS bulgaria, round(peer::numeric, 2) AS peer, "
            "round((bg - peer)::numeric, 2) AS difference FROM p ORDER BY difference DESC")), 12, 12),
    ]
    return dashboard("bgfin-peers", "Bulgaria vs EU and peers", panels, variables)


def forecasts() -> dict:
    g = Grid()
    variables = [
        var_query("indicator", "Indicator",
                  "SELECT DISTINCT v.indicator_code AS __value, i.name AS __text FROM v_indicator_values v "
                  "JOIN indicator i ON i.code = v.indicator_code WHERE v.obs_type = 'forecast' ORDER BY 2",
                  current="gdp_growth"),
        var_query("geo", "Geography", "SELECT DISTINCT geo FROM v_indicator_values WHERE indicator_code = '$indicator' "
                  "AND obs_type = 'forecast' ORDER BY 1", current="BG"),
    ]
    panels = [
        g.place(timeseries("Actual outcome and forecasts by vintage", [
            "SELECT period::timestamptz AS time, value, 'actual: ' || source_code AS metric FROM v_indicator_values "
            "WHERE indicator_code = '$indicator' AND geo = '$geo' AND frequency = 'A' AND role IN ('benchmark') "
            "AND vintage = '' AND $__timeFilter(period) ORDER BY 1",
            "SELECT period::timestamptz AS time, value, vintage AS metric FROM v_indicator_values "
            "WHERE indicator_code = '$indicator' AND geo = '$geo' AND frequency = 'A' AND vintage <> '' "
            "AND obs_type = 'forecast' AND $__timeFilter(period) ORDER BY 1"],
            desc="Each forecast round (IMF WEO, European Commission AMECO) is kept as its own line. Forecast "
                 "error appears once the outcome for a forecast year is published."), 24, 11),
        g.place(table("Forecast vs actual", (
            "SELECT period_label AS year, forecaster, vintage, round(forecast_value::numeric, 2) AS forecast, "
            "round(actual_value::numeric, 2) AS actual, round(forecast_error::numeric, 2) AS error, actual_source, "
            "actual_status FROM v_forecast_vs_actual WHERE indicator_code = '$indicator' AND geo = '$geo' "
            "ORDER BY period DESC, forecaster, vintage DESC"),
            "Error = forecast minus actual; positive values mean the forecast was too high."), 12, 12),
        g.place(table("Forecast revisions between vintages", (
            "SELECT period_label AS year, forecaster, previous_vintage, vintage, round(value::numeric, 2) AS forecast, "
            "round(change_vs_previous_vintage::numeric, 2) AS revision FROM v_forecast_revisions "
            "WHERE indicator_code = '$indicator' AND geo = '$geo' AND previous_vintage IS NOT NULL "
            "ORDER BY vintage DESC, period")), 12, 12),
    ]
    return dashboard("bgfin-forecasts", "Forecasts vs actuals", panels, variables,
                     time_from="now-15y", time_to="now+6y")


def health() -> dict:
    g = Grid()
    panels = [
        g.place(stat("Stale series", "SELECT now() AS time, count(*) FILTER (WHERE is_stale) AS value FROM v_freshness",
                     unit="none"), 6, 4),
        g.place(stat("Open data-quality issues",
                     "SELECT now() AS time, count(*) AS value FROM quality_issue WHERE resolved_at IS NULL",
                     unit="none"), 6, 4),
        g.place(stat("Failed runs, 7 days", "SELECT now() AS time, count(*) AS value FROM collection_run "
                     "WHERE status = 'failed' AND started_at > now() - interval '7 days'", unit="none"), 6, 4),
        g.place(stat("Stored observation versions", "SELECT now() AS time, count(*) AS value FROM observation",
                     unit="short"), 6, 4),
        g.place(table("Sources", "SELECT source_code AS source, name, enabled, interval_hours, last_run_at, "
                      "last_status, last_success_at, failures_7d, last_message FROM v_source_health ORDER BY source_code"),
                24, 8),
        g.place(timeseries("Observations written per run", [
            "SELECT date_trunc('hour', started_at) AS time, sum(obs_new) AS value, 'new' AS metric FROM collection_run "
            "WHERE $__timeFilter(started_at) GROUP BY 1 ORDER BY 1",
            "SELECT date_trunc('hour', started_at) AS time, sum(obs_revised) AS value, 'revised' AS metric "
            "FROM collection_run WHERE $__timeFilter(started_at) GROUP BY 1 ORDER BY 1"], bars=True, decimals=0),
            12, 8),
        g.place(table("Recent collection runs", "SELECT id, source_code AS source, mode, started_at, "
                      "finished_at - started_at AS duration, status, requests, series_seen, obs_new, obs_revised, "
                      "message FROM collection_run ORDER BY started_at DESC LIMIT 100"), 12, 8),
        g.place(table("Stale series", "SELECT f.source_code AS source, f.indicator_code, f.geo, f.source_key, "
                      "f.latest_period, f.days_since_period_end, f.max_lag_days FROM v_freshness f WHERE is_stale "
                      "ORDER BY days_since_period_end DESC"), 12, 9),
        g.place(table("Open data-quality issues", "SELECT q.id, q.severity, q.check_name, coalesce(s.source_code, "
                      "q.source_code) AS source, s.indicator_code, s.geo, q.period, q.detail::text AS detail, "
                      "q.first_detected_at FROM quality_issue q LEFT JOIN series s ON s.id = q.series_id "
                      "WHERE q.resolved_at IS NULL ORDER BY q.first_detected_at DESC",
                      "Resolve after review with: bgfin issues --resolve ID"), 12, 9),
        g.place(table("Revisions in the last 30 days", "SELECT retrieved_at, source_code AS source, indicator_code, "
                      "geo, period_label AS period, vintage, previous_value, new_value, round(delta::numeric, 3) AS delta "
                      "FROM v_revisions WHERE retrieved_at > now() - interval '30 days' ORDER BY retrieved_at DESC "
                      "LIMIT 500"), 24, 9),
    ]
    return dashboard("bgfin-health", "Data freshness and collection health", panels, time_from="now-30d")


BUILDERS = {"bgfin-overview": overview, "bgfin-explorer": explorer, "bgfin-peers": peers,
            "bgfin-forecasts": forecasts, "bgfin-health": health}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--out", type=Path, default=OUT, help=f"output directory (default {OUT})")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for uid, build in BUILDERS.items():
        path = args.out / f"{uid}.json"
        path.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
