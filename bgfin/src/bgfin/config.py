"""Load the YAML configuration in config/."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

def default_config_dir() -> Path:
    """BGFIN_CONFIG_DIR, else ./config, else the config/ folder of a source checkout."""
    if os.environ.get("BGFIN_CONFIG_DIR"):
        return Path(os.environ["BGFIN_CONFIG_DIR"])
    if Path("config/sources.yaml").exists():
        return Path("config")
    return Path(__file__).resolve().parents[2] / "config"

ROLES = {"primary", "secondary", "benchmark", "forecast", "input"}
FREQS = {"D", "B", "W", "M", "Q", "S", "A"}
AGGREGATES = {"EU27_2020", "EA21", "EA20", "EA", "EU"}


@dataclass
class SourceConfig:
    code: str
    name: str
    institution: str
    homepage: str = ""
    api_base: str = ""
    formats: list[str] = field(default_factory=list)
    enabled: bool = True
    interval_hours: float = 24
    min_interval_s: float = 1.0
    timeout_s: float = 60
    retries: int = 4
    full_refresh_days: int = 30
    incremental_periods: dict[str, int] = field(default_factory=dict)
    notes: str = ""


@dataclass
class SeriesSpec:
    """One source mapping of an indicator, expanded to a single geography."""

    indicator: str
    source: str
    geo: str
    role: str = "primary"
    dataset: str = ""
    filters: dict[str, str] = field(default_factory=dict)
    key: str = ""
    variable: str = ""
    code: str = ""
    frequency: str | None = None
    unit: str | None = None
    adjustment: str | None = None
    max_lag_days: int | None = None

    @property
    def is_forecast(self) -> bool:
        return self.role == "forecast"

    @property
    def geo_scope(self) -> str:
        return "aggregate" if self.geo in AGGREGATES or self.geo == "U2" else "country"


@dataclass
class Indicator:
    code: str
    name: str
    category: str
    unit: str
    frequency: str
    description: str = ""
    priority: bool = False
    series: list[SeriesSpec] = field(default_factory=list)


@dataclass
class Config:
    sources: dict[str, SourceConfig]
    indicators: dict[str, Indicator]
    derived: list[dict]
    thresholds: list[dict]
    validation: dict

    def specs(self, source: str | None = None, indicators: list[str] | None = None) -> list[SeriesSpec]:
        out = []
        for ind in self.indicators.values():
            if indicators and ind.code not in indicators:
                continue
            for spec in ind.series:
                if source is None or spec.source == source:
                    out.append(spec)
        return out


class ConfigError(ValueError):
    pass


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load(config_dir: Path | str | None = None) -> Config:
    base = Path(config_dir) if config_dir else default_config_dir()
    src_raw = _read(base / "sources.yaml")
    if not src_raw:
        raise ConfigError(f"no sources.yaml in {base}")
    defaults = src_raw.get("defaults", {})
    sources = {}
    for code, raw in (src_raw.get("sources") or {}).items():
        merged = {**defaults, **(raw or {})}
        merged["incremental_periods"] = {**defaults.get("incremental_periods", {}),
                                         **(raw or {}).get("incremental_periods", {})}
        merged.setdefault("name", code)
        merged.setdefault("institution", code)
        sources[code] = SourceConfig(code=code, **merged)

    ind_raw = _read(base / "indicators.yaml")
    indicators: dict[str, Indicator] = {}
    for raw in ind_raw.get("indicators") or []:
        series_raw = raw.pop("series", None) or []
        ind = Indicator(**raw)
        if ind.frequency not in FREQS:
            raise ConfigError(f"{ind.code}: bad frequency {ind.frequency}")
        for s in series_raw:
            s = dict(s)
            if s.get("source") not in sources:
                raise ConfigError(f"{ind.code}: unknown source {s.get('source')!r}")
            if s.get("role", "primary") not in ROLES:
                raise ConfigError(f"{ind.code}: bad role {s.get('role')!r}")
            geos = s.pop("geo", None) or ["BG"]
            if isinstance(geos, str):
                geos = [geos]
            s["filters"] = {k: str(v) for k, v in (s.get("filters") or {}).items()}
            if s["source"] in ("worldbank", "ameco"):
                s.setdefault("frequency", "A")              # annual-only sources
            elif s["source"] == "imf" and s.get("key"):
                s.setdefault("frequency", s["key"].rsplit(".", 1)[-1])
            s.setdefault("frequency", ind.frequency)
            for geo in geos:
                ind.series.append(SeriesSpec(indicator=ind.code, geo=geo, **s))
        if ind.code in indicators:
            raise ConfigError(f"duplicate indicator {ind.code}")
        indicators[ind.code] = ind

    derived = (_read(base / "derived.yaml").get("derived")) or []
    alerts = _read(base / "alerts.yaml")
    for d in derived:
        if d.get("indicator") and d["indicator"] not in indicators:
            raise ConfigError(f"derived {d.get('metric')}: unknown indicator {d['indicator']}")
    for t in alerts.get("thresholds") or []:
        if t.get("indicator") not in indicators:
            raise ConfigError(f"threshold {t.get('name')}: unknown indicator {t.get('indicator')}")
    return Config(sources=sources, indicators=indicators, derived=derived,
                  thresholds=alerts.get("thresholds") or [],
                  validation=alerts.get("validation") or {})
