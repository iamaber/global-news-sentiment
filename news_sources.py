"""Bounded RSS fetching for the dashboard."""

import urllib.request

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
    "http://rss.cnn.com/rss/edition.rss",
]

MAX_HEADLINES = 50
TIMEOUT_SECONDS = 10
MAX_FEED_BYTES = 2_000_000
USER_AGENT = (
    "realtime-news-sentiment/0.2 "
    "(+https://huggingface.co/spaces/iamaber/Real-time-News-Sentiment-Analysis)"
)


def load_feed(url: str, timeout: int = TIMEOUT_SECONDS, max_bytes: int = MAX_FEED_BYTES):
    """Fetch and parse a single feed with a bounded timeout and payload size."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read(max_bytes)
    return feedparser.parse(payload)


def fetch_headlines(
    urls: list[str] | None = None, limit: int = MAX_HEADLINES
) -> tuple[list[str], list[str], list[str]]:
    """Fetch headlines from all feeds and return (headlines, sources, errors)."""
    feed_urls = list(urls or FEED_URLS)
    headlines: list[str] = []
    sources: list[str] = []
    errors: list[str] = []

    for url in feed_urls:
        try:
            feed = load_feed(url)
            source = feed.feed.get("title") or url
            titles = extract_titles(feed.get("entries", []))
            if not titles:
                errors.append(f"{source}: no headlines returned")
                continue
            headlines.extend(titles)
            sources.extend([source] * len(titles))
        except Exception as exc:
            errors.append(f"{url}: {exc}")
            continue

    limited_headlines, limited_sources = dedupe_and_limit(headlines, sources, limit)
    return limited_headlines, limited_sources, errors
