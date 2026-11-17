"""GDELT's tone is its own lexicon score (roughly -10..+10, usually -5..+2), not
our model's output. GDELT throttles clients to one request every five seconds.
"""

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta

from newsent.regions import Region
from newsent.store import Store

API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
HISTORY_DAYS = 90
REFRESH_AFTER = timedelta(hours=6)
MIN_INTERVAL_SECONDS = 6.0
RATE_LIMIT_COOLDOWN_SECONDS = 300.0
TIMEOUT_SECONDS = 45
RATE_LIMIT_MESSAGE = "GDELT rate limit reached; try again later"
USER_AGENT = (
    "realtime-news-sentiment/0.3 (+https://github.com/iamaber/realtime-news-sentiment)"
)

_lock = threading.Lock()
_last_request = 0.0
_blocked_until = 0.0

type RegionErrors = dict[str, str]


class GdeltError(RuntimeError):
    pass


class GdeltRateLimited(GdeltError):
    pass


def region_query(region: Region) -> str:
    terms = " OR ".join(f"sourcecountry:{c.gdelt}" for c in region.source_countries)
    return f"({terms})"


def parse_timeline(payload: str) -> dict[date, float]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise GdeltError(payload.strip()[:200] or "empty response") from exc
    series = data.get("timeline") or []
    points = series[0].get("data", []) if series else []
    if not points:
        raise GdeltError("GDELT returned no data")
    return {
        datetime.strptime(point["date"][:8], "%Y%m%d").date(): float(point["value"])
        for point in points
    }


def _get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read(1_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise GdeltRateLimited(RATE_LIMIT_MESSAGE) from exc
        raise
    if payload.startswith("Please limit requests"):
        raise GdeltRateLimited(RATE_LIMIT_MESSAGE)
    return payload


def fetch_region_tone(region: Region) -> dict[date, float]:
    global _last_request, _blocked_until
    url = (
        API_URL
        + "?"
        + urllib.parse.urlencode(
            {
                "query": region_query(region),
                "mode": "timelinetone",
                "timespan": f"{HISTORY_DAYS}d",
                "format": "json",
            }
        )
    )
    with _lock:
        if time.monotonic() < _blocked_until:
            raise GdeltRateLimited(RATE_LIMIT_MESSAGE)
        wait_for = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request)
        if wait_for > 0:
            time.sleep(wait_for)
        try:
            payload = _get(url)
        except GdeltRateLimited:
            _blocked_until = time.monotonic() + RATE_LIMIT_COOLDOWN_SECONDS
            raise
        finally:
            _last_request = time.monotonic()
    return parse_timeline(payload)


def stale_regions(
    store: Store, regions: Iterable[Region], now: datetime
) -> list[Region]:
    stale = []
    for region in regions:
        fetched_at = store.gdelt_fetched_at(region.key)
        if fetched_at is None or now - fetched_at >= REFRESH_AFTER:
            stale.append(region)
    return stale


def refresh(
    store: Store,
    regions: Iterable[Region],
    fetch: Callable[[Region], dict[date, float]] = fetch_region_tone,
) -> RegionErrors:
    errors: RegionErrors = {}
    now = datetime.now(UTC)
    for region in stale_regions(store, regions, now):
        try:
            store.save_gdelt(region.key, fetch(region), now)
        except Exception as exc:
            errors[region.key] = str(exc)
    return errors
