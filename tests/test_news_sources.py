import time

import pytest

import news_sources


class FakeFeed:
    def __init__(self, source, titles):
        self.feed = {"title": source}
        self.entries = [{"title": title} for title in titles]

    def get(self, key, default=None):
        return self.entries if key == "entries" else default


def test_all_feed_urls_use_https():
    assert news_sources.FEED_URLS
    for url in news_sources.FEED_URLS:
        assert url.startswith("https://")


def test_fetch_headlines_dedupes_in_feed_order_and_respects_limit(monkeypatch):
    feeds = {
        "https://feeds.npr.org/1001/rss.xml": FakeFeed("NPR", [" Alpha ", "Beta"]),
        "https://feeds.bbci.co.uk/news/world/rss.xml": FakeFeed(
            "BBC", ["beta", "Gamma"]
        ),
    }
    monkeypatch.setattr(news_sources, "load_feed", lambda url: feeds[url])

    headlines, sources, errors = news_sources.fetch_headlines(
        urls=list(feeds), limit=2
    )

    assert headlines == ["Alpha", "Beta"]
    assert sources == ["NPR", "NPR"]
    assert errors == []


def test_fetch_headlines_reports_failures_and_continues(monkeypatch):
    failures = {
        "https://feeds.npr.org/1001/rss.xml": FakeFeed("NPR", ["Good"]),
        "https://feeds.bbci.co.uk/news/world/rss.xml": RuntimeError("boom"),
    }

    def fake_load(url):
        result = failures[url]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(news_sources, "load_feed", fake_load)

    headlines, sources, errors = news_sources.fetch_headlines(urls=list(failures))

    assert headlines == ["Good"]
    assert sources == ["NPR"]
    assert len(errors) == 1
    assert "boom" in errors[0]


def test_fetch_headlines_marks_empty_feeds(monkeypatch):
    monkeypatch.setattr(
        news_sources, "load_feed", lambda url: FakeFeed("Empty", [])
    )

    headlines, sources, errors = news_sources.fetch_headlines(
        urls=["https://feeds.npr.org/1001/rss.xml"]
    )

    assert (headlines, sources) == ([], [])
    assert errors == ["Empty: no headlines returned"]


def test_fetch_headlines_applies_overall_deadline(monkeypatch):
    monkeypatch.setattr(news_sources, "load_feed", lambda url: time.sleep(0.5))
    monkeypatch.setattr(news_sources, "TOTAL_TIMEOUT_SECONDS", 0.05)

    headlines, sources, errors = news_sources.fetch_headlines(
        urls=["https://feeds.npr.org/1001/rss.xml"]
    )

    assert (headlines, sources) == ([], [])
    assert len(errors) == 1
    assert "timed out" in errors[0]


def test_validate_feed_url_rejects_http_and_unknown_hosts():
    with pytest.raises(ValueError, match="https"):
        news_sources.validate_feed_url("http://feeds.npr.org/1001/rss.xml")
    with pytest.raises(ValueError, match="allowlisted"):
        news_sources.validate_feed_url("https://evil.example/rss")
    assert news_sources.validate_feed_url(news_sources.FEED_URLS[0])
