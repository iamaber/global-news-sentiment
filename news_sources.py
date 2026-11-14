"""Bounded RSS fetching for the dashboard."""

import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait

import feedparser

from sentiment_utils import dedupe_and_limit, extract_titles

FEED_URLS = [
    "https://news.google.com/rss",
    "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://moxie.foxnews.com/google-publisher/latest.xml",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.npr.org/1001/rss.xml",
]

MAX_HEADLINES = 50
TIMEOUT_SECONDS = 10
TOTAL_TIMEOUT_SECONDS = 15
MAX_WORKERS = 8
MAX_FEED_BYTES = 2_000_000
USER_AGENT = (
    "realtime-news-sentiment/0.2 "
    "(+https://huggingface.co/spaces/iamaber/Real-time-News-Sentiment-Analysis)"
)

ALLOWED_FEED_HOSTS = frozenset(
    urllib.parse.urlsplit(url).hostname for url in FEED_URLS
)


def validate_feed_url(url: str) -> str:
    """Reject feed URLs that are not HTTPS or not on the allowlisted hosts."""
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https":
        raise ValueError(f"Feed URL must use https: {url}")
    if parsed.hostname not in ALLOWED_FEED_HOSTS:
        raise ValueError(f"Feed host is not allowlisted: {parsed.hostname}")
    return url


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Apply the feed URL rules to every redirect hop, not just the first URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_feed_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_ValidatingRedirectHandler)


def load_feed(url: str, timeout: int = TIMEOUT_SECONDS, max_bytes: int = MAX_FEED_BYTES):
    """Fetch and parse a single feed with a bounded timeout and payload size."""
    validate_feed_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _opener.open(request, timeout=timeout) as response:
        payload = response.read(max_bytes)
    return feedparser.parse(payload)


def fetch_headlines(
    urls: list[str] | None = None, limit: int = MAX_HEADLINES
) -> tuple[list[str], list[str], list[str]]:
    """Fetch headlines from all feeds and return (headlines, sources, errors).

    Feeds are fetched concurrently with a per-feed timeout and one overall
    deadline. Results are still assembled in feed order so the output is
    deterministic.
    """
    feed_urls = list(urls or FEED_URLS)
    headlines: list[str] = []
    sources: list[str] = []
    errors: list[str] = []

    if limit <= 0 or not feed_urls:
        return headlines, sources, errors

    executor = ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(feed_urls)))
    futures = {url: executor.submit(load_feed, url) for url in feed_urls}
    try:
        done, _ = wait(futures.values(), timeout=TOTAL_TIMEOUT_SECONDS)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    for url, future in futures.items():
        if future not in done:
            errors.append(f"{url}: timed out after {TOTAL_TIMEOUT_SECONDS}s")
            continue

        try:
            feed = future.result()
            source = feed.feed.get("title") or url
            titles = extract_titles(feed.get("entries", []))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue

        if not titles:
            errors.append(f"{source}: no headlines returned")
            continue

        headlines.extend(titles)
        sources.extend([source] * len(titles))

    limited_headlines, limited_sources = dedupe_and_limit(headlines, sources, limit)
    return limited_headlines, limited_sources, errors
