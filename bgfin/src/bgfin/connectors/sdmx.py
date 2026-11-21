"""Shared SDMX 2.1 REST handling for the ECB and BIS (CSV output)."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from email.utils import parsedate_to_datetime

from ..model import NotModified, Obs, SeriesData, SourceError
from .base import Connector, sdmx_obs_type

UNIT_COLUMNS = ("UNIT", "UNIT_MEASURE")


def parse_sdmx_csv(text: str, dataset: str, n_dims: int | None = None,
                   geo_column: str = "REF_AREA", geo_map: dict | None = None) -> list[SeriesData]:
    """Group SDMX-CSV rows into series.

    The ECB adds a KEY column; for other providers the first n_dims columns
    (or the columns before TIME_PERIOD) are the series dimensions.
    """
    reader = csv.DictReader(io.StringIO(text))
    cols = reader.fieldnames or []
    if "TIME_PERIOD" not in cols:
        raise SourceError(f"{dataset}: unexpected CSV header {cols[:8]}")
    if "KEY" in cols:
        def key_of(row):
            return row["KEY"]
        dim_cols = []
    else:
        stop = cols.index("TIME_PERIOD") if n_dims is None else n_dims
        dim_cols = [c for c in cols[:stop] if c not in ("DATAFLOW", "STRUCTURE", "STRUCTURE_ID", "ACTION")]

        def key_of(row):
            return dataset + "." + ".".join(row[c] for c in dim_cols)
    geo_map = geo_map or {}
    series: dict[str, SeriesData] = {}
    rows_by_key = defaultdict(list)
    for row in reader:
        key = key_of(row)
        rows_by_key[key].append(row)
        if key in series:
            continue
        unit = next((row[c] for c in UNIT_COLUMNS if row.get(c)), "")
        if row.get("UNIT_MULT") not in (None, "", "0"):
            unit = f"{unit} (x10^{row['UNIT_MULT']})"
        raw_geo = row.get(geo_column, "")
        series[key] = SeriesData(
            source_key=key,
            dataset=dataset,
            geo=geo_map.get(raw_geo, raw_geo),
            unit=unit,
            frequency=row.get("FREQ", ""),
            label=row.get("TITLE") or row.get("TITLE_TS") or "",
            adjustment=_adjustment(row),
            attrs={"dimensions": {c: row[c] for c in dim_cols} if dim_cols else {"KEY": key},
                   "raw_geo": raw_geo,
                   **({"title_compl": row["TITLE_COMPL"]} if row.get("TITLE_COMPL") else {})},
        )
    for key, rows in rows_by_key.items():
        for row in rows:
            raw = row.get("OBS_VALUE", "")
            status = row.get("OBS_STATUS") or None
            if raw in ("", "NaN"):
                if status:
                    series[key].observations.append(Obs(row["TIME_PERIOD"], None, status, "missing"))
                continue
            series[key].observations.append(Obs(row["TIME_PERIOD"], float(raw), status, sdmx_obs_type(status)))
    return list(series.values())


def _adjustment(row: dict) -> str:
    for col in ("ADJUSTMENT", "TC_ADJUST", "ADJUST"):
        v = row.get(col)
        if v:
            return {"N": "NSA", "S": "SA", "Y": "SCA", "W": "SCA", "C": "CA", "A": "NSA"}.get(v, v)
    return "NSA"


class SdmxConnector(Connector):
    """Generic SDMX connector; subclasses set the URL layout and geo mapping."""

    geo_map: dict[str, str] = {}
    flow_prefix = ""

    def url(self, dataset: str, key: str) -> str:
        raise NotImplementedError

    def group(self, specs):
        groups = defaultdict(list)
        for spec in specs:
            groups[(spec.dataset, spec.key)].append(spec)
        for (dataset, template), group in groups.items():
            if "{geo}" in template:
                key = template.replace("{geo}", "+".join(dict.fromkeys(s.geo for s in group)))
            else:
                key = template
            yield dataset, template, key, group

    def params(self, freq: str, mode: str, state_key: str) -> dict:
        params = {"format": "csvdata"}
        since = self.start_period(freq, mode)
        if since:
            params["startPeriod"] = since
        return params

    def fetch(self, specs, mode):
        for dataset, template, key, group in self.group(specs):
            state_key = f"{dataset}/{key}"
            what = state_key
            try:
                resp = self.http.get(self.url(dataset, key),
                                     params=self.params(group[0].frequency or "A", mode, state_key),
                                     ok_status=(200, 404))
            except NotModified:
                self.not_modified.append(what)
                continue
            except SourceError as exc:
                self.error(what, exc)
                continue
            if resp.status_code == 404 or not resp.text.strip():
                continue       # SDMX: no observations for this query / window
            try:
                parsed = parse_sdmx_csv(resp.text, dataset, n_dims=len(key.split(".")),
                                        geo_map=self.geo_map)
            except (SourceError, ValueError, KeyError) as exc:
                self.error(what, exc)
                continue
            published = None
            if resp.headers.get("Last-Modified"):
                try:
                    published = parsedate_to_datetime(resp.headers["Last-Modified"])
                except (TypeError, ValueError):
                    pass
            self.new_state[state_key] = {"last_modified": resp.headers.get("Last-Modified")}
            by_geo = defaultdict(list)
            for s in parsed:
                s.published_at = published
                by_geo[s.attrs["raw_geo"]].append(s)
            for spec in group:
                for s in by_geo.get(spec.geo, []):
                    yield spec, s
