"""HTTP client with politeness delay, retries and conditional requests."""

from __future__ import annotations

import logging
import time
from email.utils import parsedate_to_datetime

import requests

from . import __version__
from .model import NotModified, SourceError

log = logging.getLogger(__name__)

USER_AGENT = f"bgfin/{__version__} (economic statistics collector; python-requests)"
RETRY_STATUS = {429, 500, 502, 503, 504}


class Http:
    def __init__(self, timeout_s: float = 60, retries: int = 4, min_interval_s: float = 1.0):
        self.timeout_s = timeout_s
        self.retries = retries
        self.min_interval_s = min_interval_s
        self.requests = 0
        self._last = 0.0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})

    def _wait(self) -> None:
        delay = self.min_interval_s - (time.monotonic() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()

    def get(self, url: str, params: dict | list | None = None, headers: dict | None = None,
            etag: str | None = None, last_modified: str | None = None,
            ok_status: tuple[int, ...] = (200,)) -> requests.Response:
        """GET with retries. Raises NotModified on 304 and SourceError on failure.

        Statuses in ok_status are returned to the caller (e.g. 404 meaning
        "no data for this key" in SDMX APIs).
        """
        hdrs = dict(headers or {})
        if etag:
            hdrs["If-None-Match"] = etag
        if last_modified:
            hdrs["If-Modified-Since"] = last_modified
        last_error = ""
        for attempt in range(self.retries + 1):
            self._wait()
            self.requests += 1
            try:
                resp = self.session.get(url, params=params, headers=hdrs, timeout=self.timeout_s)
            except requests.RequestException as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                log.warning("GET %s failed (%s), attempt %d", url, last_error, attempt + 1)
            else:
                if resp.status_code == 304:
                    raise NotModified(url)
                if resp.status_code in ok_status:
                    return resp
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if resp.status_code not in RETRY_STATUS:
                    break
                log.warning("GET %s returned %s, attempt %d", resp.url, resp.status_code, attempt + 1)
                retry_after = _retry_after(resp)
                if retry_after is not None and attempt < self.retries:
                    time.sleep(min(retry_after, 300))
                    continue
            if attempt < self.retries:
                time.sleep(min(2 ** attempt * 2, 120))
        raise SourceError(f"{url}: {last_error}")


def _retry_after(resp: requests.Response) -> float | None:
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None
