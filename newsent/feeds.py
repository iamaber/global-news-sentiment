import calendar
import hashlib
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import UTC, datetime

import feedparser

from newsent.regions import ALL_FEEDS, Feed, Region

PER_FEED_LIMIT = 15
TIMEOUT_SECONDS = 10
TOTAL_TIMEOUT_SECONDS = 15
MAX_FEED_BYTES = 2_000_000
# CBC's firewall drops requests whose User-Agent contains a URL.
USER_AGENT = "global-news-sentiment/0.3"

ALLOWED_FEED_HOSTS = frozenset(
    urllib.parse.urlsplit(feed.url).hostname for _, feed in ALL_FEEDS
)


@dataclass(frozen=True, slots=True)
class Headline:
    id: str
    title: str
    link: str | None
    source: str
    region: str
    published: datetime | None


@dataclass(frozen=True, slots=True)
class FeedStatus:
    source: str
    region: str
    url: str
    headlines: int
    seconds: float | None
    error: str | None


def headline_id(title: str) -> str:
    key = " ".join(title.split()).casefold()
    return hashlib.blake2b(key.encode(), digest_size=8).hexdigest()


def validate_feed_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError(f"Feed URL must use https: {url}")
    if parsed.hostname not in ALLOWED_FEED_HOSTS:
        raise ValueError(f"Feed host is not allowlisted: {parsed.hostname}")
    return url


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_feed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_ValidatingRedirectHandler)


def load_feed(url: str) -> list[Mapping]:
    validate_feed_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read(MAX_FEED_BYTES)
    return feedparser.parse(payload).entries


def _published(entry: Mapping) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), UTC)


def parse_entries(
    entries: Iterable[Mapping], feed: Feed, region: Region, limit: int
) -> list[Headline]:
    headlines = []
    for entry in entries:
        title = entry.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        title = " ".join(title.split())
        link = entry.get("link")
        headlines.append(
            Headline(
                id=headline_id(title),
                title=title,
                link=link
                if isinstance(link, str) and link.startswith("https://")
                else None,
                source=feed.name,
                region=region.key,
                published=_published(entry),
            )
        )
        if len(headlines) >= limit:
            break
    return headlines


def _timed_load(url: str) -> tuple[list[Mapping], float]:
    started = time.perf_counter()
    entries = load_feed(url)
    return entries, time.perf_counter() - started


def fetch_headlines(
    feeds: Sequence[tuple[Region, Feed]] = ALL_FEEDS,
    per_feed: int = PER_FEED_LIMIT,
) -> tuple[list[Headline], list[FeedStatus]]:
    if not feeds or per_feed <= 0:
        return [], []

    executor = ThreadPoolExecutor(max_workers=len(feeds))
    futures = [executor.submit(_timed_load, feed.url) for _, feed in feeds]
    try:
        done, _ = wait(futures, timeout=TOTAL_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    headlines: list[Headline] = []
    statuses: list[FeedStatus] = []
    seen: set[str] = set()
    for (region, feed), future in zip(feeds, futures, strict=True):
        if future not in done:
            statuses.append(
                FeedStatus(
                    feed.name,
                    region.key,
                    feed.url,
                    0,
                    None,
                    f"timed out after {TOTAL_TIMEOUT_SECONDS}s",
                )
            )
            continue
        try:
            entries, seconds = future.result()
            parsed = parse_entries(entries, feed, region, per_feed)
        except Exception as exc:
            statuses.append(
                FeedStatus(feed.name, region.key, feed.url, 0, None, str(exc))
            )
            continue

        fresh = [h for h in parsed if h.id not in seen]
        seen.update(h.id for h in fresh)
        headlines.extend(fresh)
        statuses.append(
            FeedStatus(
                feed.name,
                region.key,
                feed.url,
                len(fresh),
                round(seconds, 2),
                None if parsed else "no headlines returned",
            )
        )

    return headlines, statuses
