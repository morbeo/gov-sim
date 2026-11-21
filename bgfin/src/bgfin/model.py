"""Plain data containers passed from connectors to the store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Obs:
    period_label: str
    value: float | None
    status: str | None = None
    obs_type: str = "actual"       # actual, preliminary, estimate, forecast, missing
    vintage: str = ""


@dataclass
class SeriesData:
    source_key: str
    dataset: str
    geo: str
    unit: str
    frequency: str
    label: str = ""
    adjustment: str = "NSA"
    attrs: dict = field(default_factory=dict)
    published_at: datetime | None = None
    observations: list[Obs] = field(default_factory=list)


class SourceError(Exception):
    """A source could not be read; the message is logged on the collection run."""


class NotModified(Exception):
    """The source reports no change since the last collection."""
