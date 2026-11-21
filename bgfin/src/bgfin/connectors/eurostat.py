"""Eurostat dissemination API, JSON-stat 2.0.

https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-detailed-guidelines/api-statistics
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from datetime import datetime

from ..model import Obs, SeriesData, SourceError
from .base import EUROSTAT_GEO, EUROSTAT_GEO_BACK, Connector


def status_type(flag: str | None) -> str:
    f = (flag or "").lower()
    if "f" in f:
        return "forecast"
    if "p" in f:
        return "preliminary"
    if "e" in f:
        return "estimate"
    return "actual"


def parse_jsonstat(doc: dict, dataset: str) -> list[SeriesData]:
    """Split a Eurostat JSON-stat dataset into one SeriesData per dimension combination."""
    if "error" in doc:
        raise SourceError(f"{dataset}: {doc['error']}")
    ids: list[str] = doc["id"]
    sizes: list[int] = doc["size"]
    dims = doc["dimension"]
    values = doc.get("value") or {}
    status = doc.get("status") or {}
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    if isinstance(status, list):
        status = {str(i): v for i, v in enumerate(status) if v}

    strides = [1] * len(ids)
    for i in range(len(ids) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]

    def codes(dim: str) -> list[str]:
        index = dims[dim]["category"]["index"]
        if isinstance(index, list):
            return index
        return [c for c, _ in sorted(index.items(), key=lambda kv: kv[1])]

    cat_codes = {d: codes(d) for d in ids}
    time_dim = "time" if "time" in ids else ids[-1]
    t_pos = ids.index(time_dim)
    other = [d for d in ids if d != time_dim]
    updated = doc.get("updated")
    published = datetime.fromisoformat(updated) if updated else None

    out = []
    for combo in itertools.product(*[range(sizes[ids.index(d)]) for d in other]):
        base = sum(ix * strides[ids.index(d)] for d, ix in zip(other, combo))
        obs = []
        for t, label in enumerate(cat_codes[time_dim]):
            k = str(base + t * strides[t_pos])
            flag = status.get(k)
            if k in values:
                obs.append(Obs(label, float(values[k]), flag, status_type(flag)))
            elif flag and flag.strip() not in (":", ""):
                obs.append(Obs(label, None, flag, "missing"))
        if not obs:
            continue
        dim_codes = {d: cat_codes[d][ix] for d, ix in zip(other, combo)}
        dim_labels = {d: dims[d]["category"].get("label", {}).get(dim_codes[d], dim_codes[d]) for d in other}
        geo = EUROSTAT_GEO_BACK.get(dim_codes.get("geo", ""), dim_codes.get("geo", ""))
        unit_code = dim_codes.get("unit", "")
        out.append(SeriesData(
            source_key=dataset + ":" + ".".join(f"{d}={dim_codes[d]}" for d in other),
            dataset=dataset,
            geo=geo,
            unit=dim_labels.get("unit", unit_code) or unit_code,
            frequency=dim_codes.get("freq", ""),
            label=" | ".join(v for d, v in dim_labels.items() if d not in ("geo", "freq")),
            adjustment=dim_codes.get("s_adj", "NSA"),
            attrs={"dimensions": dim_codes, "dataset_label": doc.get("label", "")},
            published_at=published,
            observations=obs,
        ))
    return out


class EurostatConnector(Connector):
    code = "eurostat"

    def fetch(self, specs, mode):
        groups = defaultdict(list)
        for spec in specs:
            groups[(spec.dataset, tuple(sorted(spec.filters.items())))].append(spec)
        for (dataset, filters), group in groups.items():
            params = [("format", "JSON"), ("lang", "EN")]
            params += list(filters)
            params += [("geo", EUROSTAT_GEO.get(s.geo, s.geo)) for s in group]
            freq = group[0].frequency or "A"
            since = self.start_period(freq, mode)
            if since:
                params.append(("sinceTimePeriod", since))
            what = f"{dataset}?{'&'.join(f'{k}={v}' for k, v in filters)}"
            try:
                resp = self.http.get(f"{self.cfg.api_base}/{dataset}", params=params)
                series = parse_jsonstat(resp.json(), dataset)
            except (SourceError, ValueError, KeyError) as exc:
                self.error(what, exc)
                continue
            by_geo = defaultdict(list)
            for s in series:
                by_geo[s.geo].append(s)
            for spec in group:
                found = by_geo.get(spec.geo, [])
                if len(found) > 1:
                    self.error(what, SourceError(
                        f"filters match {len(found)} series for {spec.geo}; add filters for "
                        + ", ".join(sorted({k for s in found for k, v in s.attrs['dimensions'].items()
                                            if v != found[0].attrs['dimensions'].get(k)}))))
                    continue
                if found:
                    yield spec, found[0]

