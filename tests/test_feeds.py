import time
import urllib.request
from datetime import UTC, datetime

import pytest

from newsent import feeds
from newsent.regions import ALL_FEEDS, REGIONS_BY_KEY

AMERICAS = REGIONS_BY_KEY["americas"]
EUROPE = REGIONS_BY_KEY["europe"]
NPR = AMERICAS.feeds[0]
BBC = EUROPE.feeds[0]
TWO_FEEDS = ((AMERICAS, NPR), (EUROPE, BBC))


def entries(*titles):
    return [{"title": title} for title in titles]


def test_every_region_feed_is_https_and_allowlisted():
    assert ALL_FEEDS
    for _, feed in ALL_FEEDS:
        assert feed.url.startswith("https://")
        assert feeds.validate_feed_url(feed.url) == feed.url


def test_fetch_headlines_dedupes_across_feeds_in_feed_order(monkeypatch):
    by_url = {
        NPR.url: entries(" Alpha ", "Beta", "Dropped by per_feed"),
        BBC.url: entries("beta", "Gamma"),
    }
    monkeypatch.setattr(feeds, "load_feed", lambda url: by_url[url])

    headlines, statuses = feeds.fetch_headlines(TWO_FEEDS, per_feed=2)

    assert [(h.title, h.source, h.region) for h in headlines] == [
        ("Alpha", "NPR", "americas"),
        ("Beta", "NPR", "americas"),
        ("Gamma", "BBC News", "europe"),
    ]
    assert [(s.source, s.headlines, s.error) for s in statuses] == [
        ("NPR", 2, None),
        ("BBC News", 1, None),
    ]


def test_failing_feed_is_reported_while_others_continue(monkeypatch):
    def load(url):
        if url == BBC.url:
            raise RuntimeError("boom")
        return entries("Good news")

    monkeypatch.setattr(feeds, "load_feed", load)

    headlines, statuses = feeds.fetch_headlines(TWO_FEEDS)

    assert [h.title for h in headlines] == ["Good news"]
    npr, bbc = statuses
    assert (npr.headlines, npr.error) == (1, None)
    assert (bbc.region, bbc.headlines, bbc.error) == ("europe", 0, "boom")


def test_empty_feed_is_flagged(monkeypatch):
    monkeypatch.setattr(feeds, "load_feed", lambda url: [])

    headlines, statuses = feeds.fetch_headlines(TWO_FEEDS[:1])

    assert headlines == []
    assert statuses[0].error == "no headlines returned"


def test_overall_deadline_marks_slow_feeds_timed_out(monkeypatch):
    monkeypatch.setattr(feeds, "load_feed", lambda url: time.sleep(0.5) or [])
    monkeypatch.setattr(feeds, "TOTAL_TIMEOUT_SECONDS", 0.05)

    headlines, statuses = feeds.fetch_headlines(TWO_FEEDS[:1])

    assert headlines == []
    assert statuses[0].headlines == 0
    assert "timed out" in statuses[0].error


def test_validate_feed_url_rejects_http_and_unknown_hosts():
    with pytest.raises(ValueError, match="https"):
        feeds.validate_feed_url("http://feeds.npr.org/1001/rss.xml")
    with pytest.raises(ValueError, match="allowlisted"):
        feeds.validate_feed_url("https://evil.example/rss")


def test_redirects_are_validated_like_the_initial_url():
    handler = feeds._ValidatingRedirectHandler()
    request = urllib.request.Request(NPR.url)

    def redirect(newurl):
        return handler.redirect_request(request, None, 302, "Found", {}, newurl)

    with pytest.raises(ValueError, match="https"):
        redirect("http://feeds.npr.org/1001/rss.xml")
    with pytest.raises(ValueError, match="allowlisted"):
        redirect("https://evil.example/rss")
    assert redirect(BBC.url).full_url == BBC.url
    assert any(
        isinstance(h, feeds._ValidatingRedirectHandler) for h in feeds._opener.handlers
    )


def test_parse_entries_cleans_titles_links_and_dates():
    raw = [
        {"title": "   "},
        {"title": None},
        {"summary": "no title"},
        {
            "title": "  Rates   held\n steady ",
            "link": "https://example.com/a",
            "published_parsed": time.struct_time((2026, 11, 16, 23, 30, 0, 0, 320, 0)),
        },
        {"title": "Plain link", "link": "http://example.com/b"},
    ]

    headlines = feeds.parse_entries(raw, NPR, AMERICAS, limit=10)

    assert [(h.title, h.link, h.published) for h in headlines] == [
        (
            "Rates held steady",
            "https://example.com/a",
            datetime(2026, 11, 16, 23, 30, tzinfo=UTC),
        ),
        ("Plain link", None, None),
    ]
    assert {(h.source, h.region) for h in headlines} == {("NPR", "americas")}
    assert headlines[0].id == feeds.headline_id("rates HELD steady")
