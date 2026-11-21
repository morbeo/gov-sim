"""Connector base class and shared helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date, datetime, timedelta, timezone

from ..config import SeriesSpec, SourceConfig
from ..http import Http
from ..model import SeriesData
from ..periods import period_label, shift

log = logging.getLogger(__name__)

ISO2_TO_ISO3 = {
    "AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK",
    "EE": "EST", "EL": "GRC", "GR": "GRC", "ES": "ESP", "FI": "FIN", "FR": "FRA", "HR": "HRV",
    "HU": "HUN", "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT",
    "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK",
    "RS": "SRB", "MK": "MKD", "TR": "TUR", "AL": "ALB", "ME": "MNE", "BA": "BIH", "UA": "UKR",
    "MD": "MDA", "US": "USA", "GB": "GBR", "UK": "GBR", "NO": "NOR", "CH": "CHE", "JP": "JPN",
}
ISO3_TO_ISO2 = {v: k for k, v in ISO2_TO_ISO3.items() if k not in ("EL", "UK")}

# Eurostat writes Greece as EL; everything else here uses ISO 3166 GR.
EUROSTAT_GEO = {"GR": "EL"}
EUROSTAT_GEO_BACK = {v: k for k, v in EUROSTAT_GEO.items()}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def forecast_cutoff_type(period_year: int, vintage_year: int) -> str:
    """Forecast datasets mix history and projections without a per-value flag.

    Rule: values for the vintage year and later are projections. For both the
    IMF WEO (April/October) and the Commission forecasts (spring/autumn) the
    current year is still a projection at release time.
    """
    return "forecast" if period_year >= vintage_year else "actual"


def sdmx_obs_type(status: str | None) -> str:
    """Map SDMX OBS_STATUS codes (ECB, BIS) to observation types."""
    s = (status or "").strip().upper()
    if s == "F":
        return "forecast"
    if s == "P":
        return "preliminary"
    if s in ("E", "T"):
        return "estimate"
    if s in ("M", "L", "Q", "O"):
        return "missing"
    return "actual"


class Connector:
    """Fetch the series described by a list of specs.

    Subclasses implement fetch(), yielding (spec, SeriesData) pairs. Failures
    of one request are appended to self.errors so the rest of the source still
    gets collected.
    """

    code = ""

    def __init__(self, cfg: SourceConfig, http: Http | None = None, state: dict | None = None):
        self.cfg = cfg
        self.http = http or Http(cfg.timeout_s, cfg.retries, cfg.min_interval_s)
        self.state = state if state is not None else {}   # dataset -> {etag, last_modified, ...}
        self.new_state: dict[str, dict] = {}
        self.errors: list[dict] = []
        self.not_modified: list[str] = []

    def fetch(self, specs: list[SeriesSpec], mode: str) -> Iterator[tuple[SeriesSpec, SeriesData]]:
        raise NotImplementedError

    def start_period(self, freq: str, mode: str, today: date | None = None) -> str | None:
        """First period an incremental run asks for; None means full history."""
        if mode == "backfill":
            return None
        today = today or date.today()
        n = self.cfg.incremental_periods.get(freq, 12)
        if freq in ("M", "Q", "S", "A"):
            start = shift(_align(date(today.year, today.month, 1), freq), freq, -n)
            return period_label(start, freq)
        return (today - timedelta(days=n)).isoformat()

    def error(self, what: str, exc: Exception) -> None:
        log.error("%s: %s failed: %s", self.code, what, exc)
        self.errors.append({"request": what, "error": str(exc)[:1000]})


def _align(d: date, freq: str) -> date:
    if freq == "Q":
        return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)
    if freq == "S":
        return date(d.year, 1 if d.month <= 6 else 7, 1)
    if freq == "A":
        return date(d.year, 1, 1)
    return d


def parse_number(raw) -> tuple[float | None, str | None]:
    """Parse a value that may carry flags, e.g. "(2.2)" or "12.3 p"."""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    text = str(raw).strip()
    if text in ("", ":", "..", "-", "NA", "n/a", "x"):
        return None, None
    flag = None
    if text.startswith("(") and text.endswith(")"):
        text, flag = text[1:-1], "low_reliability"
    parts = text.split()
    if len(parts) == 2:
        text, flag = parts[0], parts[1]
    try:
        return float(text.replace(",", "")), flag
    except ValueError:
        return None, text
