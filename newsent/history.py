"""Daily model-sentiment history recorded outside this process.

`newsent.collect` runs hourly in GitHub Actions and commits `trend.csv` (per
region) and `sources.csv` (per outlet) to the `history` branch, so the trends
survive hosts whose disk is wiped on restart.
"""

import csv
import io
import os
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date
from typing import Protocol

from newsent.store import DailyPoint, SourceDay, Store, window

DEFAULT_SOURCE = "https://raw.githubusercontent.com/iamaber/realtime-news-sentiment/history/trend.csv"
HISTORY_SOURCE = os.environ.get("NEWS_HISTORY", DEFAULT_SOURCE)
SOURCES_FILE = "sources.csv"
TREND_DAYS = 90
FIELDS = ["day", "region", "net", "headlines"]
SOURCE_FIELDS = ["day", "source", "net", "headlines"]
TIMEOUT_SECONDS = 10
MAX_BYTES = 2_000_000
CACHE_SECONDS = 900
LOCAL_LABEL = "recorded by this instance"


class _Dated(Protocol):
    @property
    def day(self) -> date: ...


def format_trend(points: Iterable[DailyPoint]) -> str:
    return _format(FIELDS, ((p.day, p.region, p.value, p.headlines) for p in points))


def format_sources(points: Iterable[SourceDay]) -> str:
    return _format(
        SOURCE_FIELDS, ((p.day, p.source, p.value, p.headlines) for p in points)
    )


def _format(fields: list[str], rows: Iterable[tuple[date, str, float, int]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(fields)
    writer.writerows(
        (day.isoformat(), key, round(net, 4), n) for day, key, net, n in rows
    )
    return out.getvalue()


def parse_trend(text: str) -> list[DailyPoint]:
    return [DailyPoint(*row) for row in _parse(text, FIELDS)]


def parse_sources(text: str) -> list[SourceDay]:
    return [SourceDay(*row) for row in _parse(text, SOURCE_FIELDS)]


def _parse(text: str, fields: list[str]) -> list[tuple[date, str, float, int]]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != fields:
        raise ValueError(f"unexpected history header: {reader.fieldnames}")
    day, key, net, headlines = fields
    return [
        (
            date.fromisoformat(row[day]),
            row[key],
            float(row[net]),
            int(row[headlines]),
        )
        for row in reader
    ]


def _require_https(url: str) -> None:
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError(f"history URL must use https: {url}")


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_https(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnlyRedirects)


def _read(source: str) -> str:
    if "://" in source:
        _require_https(source)
        with _opener.open(source, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_BYTES + 1)
    else:
        with open(source, "rb") as file:
            payload = file.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"history file is larger than {MAX_BYTES} bytes")
    return payload.decode("utf-8")


def load_trend(source: str) -> list[DailyPoint]:
    return parse_trend(_read(source))


def load_sources(source: str) -> list[SourceDay]:
    return parse_sources(_read(source))


class CachedLoader[P]:
    """Remember each source's result or failure, so a dead host costs one timeout per period."""

    def __init__(self, load: Callable[[str], list[P]], seconds: float):
        self._load = load
        self._seconds = seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[P] | Exception]] = {}

    def __call__(self, source: str) -> list[P]:
        with self._lock:
            entry = self._entries.get(source)
            if entry is None or time.monotonic() - entry[0] >= self._seconds:
                try:
                    outcome: list[P] | Exception = self._load(source)
                except Exception as exc:
                    outcome = exc
                entry = self._entries[source] = (time.monotonic(), outcome)
        if isinstance(entry[1], Exception):
            raise entry[1]
        return entry[1]


cached_load_trend = CachedLoader(load_trend, CACHE_SECONDS)
cached_load_sources = CachedLoader(load_sources, CACHE_SECONDS)


def model_trend(
    store: Store,
    days: int,
    until: date | None = None,
    load: Callable[[str], list[DailyPoint]] = cached_load_trend,
) -> tuple[list[DailyPoint], str]:
    return _collected_or_local(
        HISTORY_SOURCE, load, lambda: store.model_trend(days, until), days, until
    )


def source_trend(
    store: Store,
    days: int,
    until: date | None = None,
    load: Callable[[str], list[SourceDay]] = cached_load_sources,
) -> tuple[list[SourceDay], str]:
    """Daily mean index per outlet; `sources.csv` sits next to `trend.csv`."""
    source = HISTORY_SOURCE and _sibling(HISTORY_SOURCE, SOURCES_FILE)
    return _collected_or_local(
        source, load, lambda: store.source_trend(days, until), days, until
    )


def _sibling(source: str, name: str) -> str:
    if "://" in source:
        return urllib.parse.urljoin(source, name)
    return os.path.join(os.path.dirname(source), name)


def _collected_or_local[P: _Dated](
    source: str,
    load: Callable[[str], list[P]],
    local: Callable[[], list[P]],
    days: int,
    until: date | None,
) -> tuple[list[P], str]:
    if not source:
        return local(), LOCAL_LABEL
    start, end = window(days, until)
    try:
        points = [p for p in load(source) if start <= p.day <= end]
    except Exception as exc:
        reason = str(exc) or type(exc).__name__
    else:
        if points:
            return points, _collected_label(source)
        reason = f"no collected days in the last {days}"
    return (
        local(),
        f"collected history unavailable: {reason}; showing this instance's recordings",
    )


def _collected_label(source: str) -> str:
    if HISTORY_SOURCE == DEFAULT_SOURCE:
        return "collected hourly by GitHub Actions"
    return f"collected history from {source}"
