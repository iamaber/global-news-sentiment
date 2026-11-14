import urllib.request

import feedparser

DEFAULT_FEEDS = [
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
USER_AGENT = "realtime-news-sentiment/0.2"


def _load_feed(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read(MAX_FEED_BYTES)
    return feedparser.parse(payload)


def fetch_headlines(urls=None, limit=MAX_HEADLINES):
    feed_urls = list(urls or DEFAULT_FEEDS)
    headlines = []
    seen = set()

    for url in feed_urls:
        try:
            feed = _load_feed(url)
        except Exception:
            continue

        for entry in feed.get("entries", []):
            title = entry.get("title")
            if not isinstance(title, str):
                continue
            key = title.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            headlines.append(title.strip())
            if len(headlines) >= limit:
                return headlines

    return headlines
