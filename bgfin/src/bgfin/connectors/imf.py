"""IMF SDMX 3.0 API (World Economic Outlook and other IMF.RES dataflows).

https://data.imf.org  ->  https://api.imf.org/external/sdmx/3.0
The older DataMapper JSON API (www.imf.org/external/datamapper/api) is behind
bot protection and rate limits and is not used.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import datetime, timezone

from ..model import Obs, SeriesData, SourceError
from .base import ISO2_TO_ISO3, ISO3_TO_ISO2, Connector, forecast_cutoff_type

CSV_ACCEPT = "application/vnd.sdmx.data+csv;version=2.0.0"


def weo_vintage(dataset: str, update: datetime | None) -> tuple[str, int]:
    """WEO is released in April and October. Country data updated in the first
    half of a year belongs to the April round, later updates to October."""
    if update is None:
        update = datetime.now(timezone.utc)
    month = "04" if update.month <= 6 else "10"
    return f"{dataset}-{update.year}-{month}", update.year


def parse_imf_csv(text: str, dataset: str) -> list[SeriesData]:
    rows = list(csv.DictReader(io.StringIO(text)))
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["COUNTRY"], r["INDICATOR"], r["FREQUENCY"])].append(r)
    out = []
    for (country, indicator, freq), rs in grouped.items():
        updates = [_date(r.get("COUNTRY_UPDATE_DATE")) for r in rs]
        updates = [u for u in updates if u]
        update = max(updates) if updates else None
        vintage, vyear = weo_vintage(dataset, update)
        obs = []
        for r in rs:
            if r.get("OBS_VALUE") in (None, "", "NA"):
                continue
            year = int(r["TIME_PERIOD"][:4])
            obs.append(Obs(r["TIME_PERIOD"], float(r["OBS_VALUE"]), None,
                           forecast_cutoff_type(year, vyear), vintage))
        first = rs[0]
        unit = first.get("UNIT") or ""
        if first.get("SCALE") not in (None, "", "0"):
            unit = f"{unit} (x10^{first['SCALE']})"
        out.append(SeriesData(
            source_key=f"{dataset}.{country}.{indicator}.{freq}",
            dataset=dataset,
            geo=ISO3_TO_ISO2.get(country, country),
            unit=unit,
            frequency=freq,
            label=indicator,
            attrs={"structure": first.get("STRUCTURE_ID"), "country_update_date": update.isoformat() if update else None,
                   "vintage": vintage},
            published_at=update,
            observations=obs,
        ))
    return out


def _date(text: str | None) -> datetime | None:
    if not text:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class ImfConnector(Connector):
    code = "imf"
    agency = "IMF.RES"

    def fetch(self, specs, mode):
        groups = defaultdict(list)
        for spec in specs:
            groups[(spec.dataset, spec.key)].append(spec)
        for (dataset, template), group in groups.items():
            countries = "+".join(dict.fromkeys(ISO2_TO_ISO3.get(s.geo, s.geo) for s in group))
            key = template.replace("{geo}", countries)
            url = f"{self.cfg.api_base}/data/dataflow/{self.agency}/{dataset}/+/{key}"
            try:
                resp = self.http.get(url, headers={"Accept": CSV_ACCEPT}, ok_status=(200, 404))
                if resp.status_code == 404:
                    continue
                parsed = parse_imf_csv(resp.text, dataset)
            except (SourceError, ValueError, KeyError) as exc:
                self.error(f"{dataset}/{key}", exc)
                continue
            by_geo = defaultdict(list)
            for s in parsed:
                by_geo[s.geo].append(s)
            for spec in group:
                for s in by_geo.get(spec.geo, []):
                    yield spec, s
