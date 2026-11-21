"""NSI (National Statistical Institute of Bulgaria) open data portal, JSON-stat 2.0.

https://www.nsi.bg/opendata lists ~140 datasets (mostly labour market and
social statistics). Core macro series (GDP, CPI, industry) are only in the
interactive Infostat system, which has no public API; Eurostat carries the
same NSI-produced data for those.
"""

from __future__ import annotations

import itertools
from datetime import datetime

from ..model import Obs, SeriesData, SourceError
from .base import Connector, parse_number


def parse_nsi(doc: dict, dataset: str) -> list[SeriesData]:
    ids, sizes = doc["id"], doc["size"]
    dims = doc["dimension"]
    values = doc["value"]
    status = doc.get("status") or {}
    role = doc.get("role") or {}
    time_dim = (role.get("time") or ["periods"])[0]
    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    def codes(d):
        category = dims[d]["category"]
        index = category.get("index")
        if index is None:                  # NSI omits index; label order is the value order
            return list(category.get("label", {}))
        return index if isinstance(index, list) else [c for c, _ in sorted(index.items(), key=lambda kv: kv[1])]

    cat = {d: codes(d) for d in ids}
    other = [d for d in ids if d != time_dim]
    t_pos = ids.index(time_dim)
    updated = doc.get("updated")
    published = datetime.fromisoformat(updated) if updated else None
    out = []
    for combo in itertools.product(*[range(sizes[ids.index(d)]) for d in other]):
        base = sum(ix * strides[ids.index(d)] for d, ix in zip(other, combo))
        obs = []
        for t, label in enumerate(cat[time_dim]):
            k = base + t * strides[t_pos]
            raw = values[k] if isinstance(values, list) else values.get(str(k))
            value, flag = parse_number(raw)
            flag = flag or (status.get(str(k)) if isinstance(status, dict) else None)
            if value is None and not flag:
                continue
            obs.append(Obs(label, value, flag, "missing" if value is None else "actual"))
        dim_codes = {d: cat[d][ix] for d, ix in zip(other, combo)}
        labels = {d: dims[d]["category"].get("label", {}).get(dim_codes[d], dim_codes[d]) for d in other}
        unit_dim = (role.get("metric") or [None])[0]
        out.append(SeriesData(
            source_key=f"{dataset}:" + ".".join(f"{d}={dim_codes[d]}" for d in other),
            dataset=dataset, geo="BG",
            unit=labels.get(unit_dim, "") if unit_dim else "",
            frequency="",
            label=doc.get("label", "") + " | " + " | ".join(v for d, v in labels.items() if d != unit_dim),
            attrs={"dimensions": dim_codes, "revision_column": doc.get("extension", {}).get("revision")},
            published_at=published, observations=obs))
    return out


class NsiConnector(Connector):
    code = "nsi"

    def fetch(self, specs, mode):
        by_dataset = {}
        for spec in specs:
            by_dataset.setdefault(spec.dataset, []).append(spec)
        for dataset, group in by_dataset.items():
            try:
                resp = self.http.get(f"{self.cfg.api_base}/getopendata_json.php", params={"l": "en", "id": dataset})
                parsed = parse_nsi(resp.json(), dataset)
            except (SourceError, ValueError, KeyError) as exc:
                self.error(f"opendata {dataset}", exc)
                continue
            for spec in group:
                match = [s for s in parsed
                         if all(s.attrs["dimensions"].get(k) == v for k, v in spec.filters.items())]
                if len(match) != 1:
                    self.error(f"opendata {dataset} {spec.filters}",
                               SourceError(f"filters match {len(match)} series"))
                    continue
                s = match[0]
                s.frequency = spec.frequency or s.frequency
                yield spec, s
