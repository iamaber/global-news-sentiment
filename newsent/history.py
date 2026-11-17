"""Daily model-sentiment history recorded outside this process.

`newsent.collect` runs hourly in GitHub Actions and commits `trend.csv` to the
`history` branch, so the trend survives hosts whose disk is wiped on restart.
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

from newsent.store import DailyPoint, Store, window

DEFAULT_SOURCE = "https://raw.githubusercontent.com/iamaber/realtime-news-sentiment/history/trend.csv"
HISTORY_SOURCE = os.environ.get("NEWS_HISTORY", DEFAULT_SOURCE)
TREND_DAYS = 90
FIELDS = ["day", "region", "net", "headlines"]
TIMEOUT_SECONDS = 10
MAX_BYTES = 2_000_000
CACHE_SECONDS = 900
LOCAL_LABEL = "recorded by this instance"


def format_trend(points: Iterable[DailyPoint]) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(
        (p.day.isoformat(), p.region, round(p.value, 4), p.headlines) for p in points
    )
    return out.getvalue()


def parse_trend(text: str) -> list[DailyPoint]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames != FIELDS:
        raise ValueError(f"unexpected trend.csv header: {reader.fieldnames}")
    return [
        DailyPoint(
            date.fromisoformat(row["day"]),
            row["region"],
            float(row["net"]),
            int(row["headlines"]),
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


def load_trend(source: str) -> list[DailyPoint]:
    if "://" in source:
        _require_https(source)
        with _opener.open(source, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read(MAX_BYTES + 1)
    else:
        with open(source, "rb") as file:
            payload = file.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError(f"history file is larger than {MAX_BYTES} bytes")
    return parse_trend(payload.decode("utf-8"))


class CachedLoader:
    """Remember each source's result or failure, so a dead host costs one timeout per period."""

    def __init__(self, load: Callable[[str], list[DailyPoint]], seconds: float):
        self._load = load
        self._seconds = seconds
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[DailyPoint] | Exception]] = {}

    def __call__(self, source: str) -> list[DailyPoint]:
        with self._lock:
            entry = self._entries.get(source)
            if entry is None or time.monotonic() - entry[0] >= self._seconds:
                try:
                    outcome: list[DailyPoint] | Exception = self._load(source)
                except Exception as exc:
                    outcome = exc
                entry = self._entries[source] = (time.monotonic(), outcome)
        if isinstance(entry[1], Exception):
            raise entry[1]
        return entry[1]


cached_load_trend = CachedLoader(load_trend, CACHE_SECONDS)


def model_trend(
    store: Store,
    days: int,
    until: date | None = None,
    load: Callable[[str], list[DailyPoint]] = cached_load_trend,
) -> tuple[list[DailyPoint], str]:
    if not HISTORY_SOURCE:
        return store.model_trend(days, until), LOCAL_LABEL
    start, end = window(days, until)
    try:
        points = [p for p in load(HISTORY_SOURCE) if start <= p.day <= end]
    except Exception as exc:
        reason = str(exc) or type(exc).__name__
    else:
        if points:
            return points, _collected_label(HISTORY_SOURCE)
        reason = f"no collected days in the last {days}"
    return (
        store.model_trend(days, until),
        f"collected history unavailable: {reason}; showing this instance's recordings",
    )


def _collected_label(source: str) -> str:
    if source == DEFAULT_SOURCE:
        return "collected hourly by GitHub Actions"
    return f"collected history from {source}"
