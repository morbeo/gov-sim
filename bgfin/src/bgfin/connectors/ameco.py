"""AMECO bulk download (European Commission annual macro-economic database).

The database has no query API; the complete data set is published as one ZIP
of semicolon-separated text files, refreshed with each Commission forecast.
Codes look like BGR.1.0.319.0.UBLGE: country, transformation, aggregation,
unit, reference, variable.
"""

from __future__ import annotations

import io
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from ..model import NotModified, Obs, SeriesData, SourceError
from .base import ISO2_TO_ISO3, Connector, forecast_cutoff_type

AMECO_GEO = {"EU27_2020": "EU27", "EA21": "EA21", "EA20": "EA20", "RO": "ROM"}   # AMECO keeps legacy ROM


def ameco_country(geo: str) -> str:
    return AMECO_GEO.get(geo) or ISO2_TO_ISO3.get(geo, geo)


def parse_ameco(zip_bytes: bytes, wanted: dict[str, set[str]], release: datetime) -> dict[tuple[str, str], SeriesData]:
    """wanted maps AMECO country code -> set of variable codes (without country)."""
    vintage = f"AMECO-{release.year}-{release.month:02d}"
    out = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.upper().endswith(".TXT"):
                continue
            with zf.open(name) as fh:
                lines = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                header = next(lines).rstrip("\r\n").split(";")
                years = [h.strip() for h in header[5:]]
                for line in lines:
                    parts = line.rstrip("\r\n").split(";")
                    code = parts[0].strip()
                    country, _, variable = code.partition(".")
                    if variable not in wanted.get(country, ()):
                        continue
                    obs = []
                    for year, raw in zip(years, parts[5:]):
                        if not year.isdigit():
                            continue
                        raw = raw.strip()
                        if raw in ("", "NA"):
                            continue
                        obs.append(Obs(year, float(raw), None,
                                       forecast_cutoff_type(int(year), release.year), vintage))
                    out[(country, variable)] = SeriesData(
                        source_key=code, dataset="AMECO", geo=country,
                        unit=parts[4].strip().strip("()"), frequency="A",
                        label=parts[3].strip(),
                        attrs={"country_name": parts[1], "sub_chapter": parts[2], "file": name,
                               "vintage": vintage},
                        published_at=release, observations=obs)
    return out


class AmecoConnector(Connector):
    code = "ameco"

    def fetch(self, specs, mode):
        st = self.state.get("AMECO") or {}
        try:
            resp = self.http.get(self.cfg.api_base,
                                 etag=st.get("etag") if mode == "incremental" else None,
                                 last_modified=st.get("last_modified") if mode == "incremental" else None)
        except NotModified:
            self.not_modified.append("AMECO")
            return
        except SourceError as exc:
            self.error("AMECO zip", exc)
            return
        release = None
        if resp.headers.get("Last-Modified"):
            try:
                release = parsedate_to_datetime(resp.headers["Last-Modified"])
            except (TypeError, ValueError):
                release = None
        try:
            if release is None:
                with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                    release = datetime(*max(i.date_time for i in zf.infolist()), tzinfo=timezone.utc)
            wanted = defaultdict(set)
            for s in specs:
                wanted[ameco_country(s.geo)].add(s.variable)
            parsed = parse_ameco(resp.content, wanted, release)
        except (zipfile.BadZipFile, ValueError, StopIteration) as exc:
            self.error("AMECO zip", exc)
            return
        self.new_state["AMECO"] = {"etag": resp.headers.get("ETag"),
                                   "last_modified": resp.headers.get("Last-Modified"),
                                   "source_updated": release.isoformat()}
        for spec in specs:
            s = parsed.get((ameco_country(spec.geo), spec.variable))
            if s is None:
                self.error(f"AMECO {ameco_country(spec.geo)}.{spec.variable}", SourceError("series not in file"))
                continue
            s.geo = spec.geo
            yield spec, s
