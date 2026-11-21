"""World Bank Indicators API v2. https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from ..model import Obs, SeriesData, SourceError
from .base import Connector


class WorldBankConnector(Connector):
    code = "worldbank"

    def fetch(self, specs, mode):
        groups = defaultdict(list)
        for spec in specs:
            groups[spec.code].append(spec)
        for code, group in groups.items():
            countries = ";".join(dict.fromkeys(s.geo for s in group))
            params = {"format": "json", "per_page": 20000}
            if mode == "incremental":
                n = self.cfg.incremental_periods.get("A", 10)
                params["date"] = f"{date.today().year - n}:{date.today().year}"
            series: dict[str, SeriesData] = {}
            page, pages = 1, 1
            try:
                while page <= pages:
                    params["page"] = page
                    resp = self.http.get(f"{self.cfg.api_base}/country/{countries}/indicator/{code}", params=params)
                    body = resp.json()
                    if not isinstance(body, list) or len(body) < 2:
                        msg = body[0].get("message") if isinstance(body, list) and body else body
                        raise SourceError(f"unexpected response: {str(msg)[:300]}")
                    meta, rows = body[0], body[1] or []
                    pages = int(meta.get("pages") or 1)
                    updated = meta.get("lastupdated")
                    for r in rows:
                        geo = r["country"]["id"]
                        s = series.get(geo)
                        if s is None:
                            s = series[geo] = SeriesData(
                                source_key=f"{code}.{geo}", dataset="WDI", geo=geo,
                                unit=r.get("unit") or "", frequency="A",
                                label=r["indicator"]["value"],
                                attrs={"indicator": code, "iso3": r.get("countryiso3code")},
                                published_at=datetime.fromisoformat(updated).replace(tzinfo=timezone.utc) if updated else None)
                        if r.get("value") is None:
                            continue
                        status = r.get("obs_status") or None
                        s.observations.append(Obs(r["date"], float(r["value"]), status,
                                                  "estimate" if status == "E" else "actual"))
                    page += 1
            except (SourceError, ValueError, KeyError, TypeError) as exc:
                self.error(f"{code}?{countries}", exc)
                continue
            for spec in group:
                s = series.get(spec.geo)
                if s and s.observations:
                    if spec.unit:
                        s.unit = spec.unit
                    yield spec, s
