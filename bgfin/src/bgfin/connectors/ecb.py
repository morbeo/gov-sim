"""ECB Data Portal, SDMX 2.1 REST. https://data.ecb.europa.eu/help/api/data"""

from __future__ import annotations

from datetime import timedelta, timezone

from .sdmx import SdmxConnector


class EcbConnector(SdmxConnector):
    code = "ecb"
    geo_map = {"U2": "EA"}          # euro area, changing composition

    def url(self, dataset, key):
        return f"{self.cfg.api_base}/data/{dataset}/{key}"

    def params(self, freq, mode, state_key):
        params = {"format": "csvdata"}
        last = (self.state.get(state_key) or {}).get("checked_at")
        if mode == "incremental" and last:
            # updatedAfter returns every observation changed since then, any
            # period, so revisions to old data are included. A one-day overlap
            # covers clock differences and partly stored runs.
            since = last - timedelta(days=1)
            params["updatedAfter"] = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
            return params
        since = self.start_period(freq, mode)
        if since:
            params["startPeriod"] = since
        return params

