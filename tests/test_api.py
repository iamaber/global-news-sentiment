import asyncio
import collections
import math
import os
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import api as api_module
from newsent import history
from newsent.feeds import FeedStatus, Headline, headline_id
from newsent.scores import Scores
from newsent.store import DailyPoint, SourceDay

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
TODAY = datetime.now(UTC).date()
SCORES = {
    "Markets rally": Scores(negative=0.1, neutral=0.2, positive=0.7),
    "Storm hits coast": Scores(negative=0.8, neutral=0.15, positive=0.05),
    "Talks resume": Scores(negative=0.2, neutral=0.6, positive=0.2),
    "Markets rally in Europe": Scores(negative=0.1, neutral=0.3, positive=0.6),
}
HEADLINES = [
    Headline(
        headline_id("Markets rally"),
        "Markets rally",
        "https://example.com/rally",
        "NPR",
        "americas",
        PUBLISHED,
    ),
    Headline(
        headline_id("Storm hits coast"),
        "Storm hits coast",
        None,
        "NPR",
        "americas",
        None,
    ),
    Headline(
        headline_id("Talks resume"), "Talks resume", None, "BBC News", "europe", None
    ),
]
STATUSES = [
    FeedStatus("NPR", "americas", "https://feeds.npr.org/1001/rss.xml", 2, 0.42, None),
    FeedStatus(
        "BBC News",
        "europe",
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        1,
        0.3,
        None,
    ),
    FeedStatus("Nation", "mea", "https://nation.africa/kenya/rss.xml", 0, None, "boom"),
]
SOURCES = [
    {
        "source": "NPR",
        "region": "americas",
        "headlines": 2,
        "seconds": 0.42,
        "error": None,
    },
    {
        "source": "BBC News",
        "region": "europe",
        "headlines": 1,
        "seconds": 0.3,
        "error": None,
    },
    {
        "source": "Nation",
        "region": "mea",
        "headlines": 0,
        "seconds": None,
        "error": "boom",
    },
]


class FakeNews:
    def __init__(self, headlines=HEADLINES):
        self.headlines = headlines
        self.fetches = 0
        self.scored: list[str] = []

    def fetch(self):
        self.fetches += 1
        return list(self.headlines), list(STATUSES)

    def score(self, texts):
        self.scored.extend(texts)
        return [SCORES[text] for text in texts]


def test_api_module_imports_without_pythonpath_or_side_effects(tmp_path):
    db = tmp_path / "import.db"
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["NEWS_SENTIMENT_DB"] = str(db)

    result = subprocess.run(
        [sys.executable, "-c", "import backend.api"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert not db.exists()


@pytest.fixture
def news(monkeypatch):
    fake = FakeNews()
    monkeypatch.setattr(api_module, "fetch_headlines", fake.fetch)
    monkeypatch.setattr(api_module, "score", fake.score)
    monkeypatch.setattr(api_module, "warm_up_model", lambda: None)
    monkeypatch.setattr(api_module, "_snapshot", None)
    api_module._request_times.clear()
    api_module.get_store.cache_clear()
    yield fake
    api_module.get_store.cache_clear()


@pytest.fixture
def client(news):
    with TestClient(api_module.app) as test_client:
        yield test_client


def collected(monkeypatch, tmp_path, trend=(), sources=()):
    (tmp_path / "trend.csv").write_text(history.format_trend(trend))
    (tmp_path / "sources.csv").write_text(history.format_sources(sources))
    monkeypatch.setattr(history, "HISTORY_SOURCE", str(tmp_path / "trend.csv"))


def test_registry_lists_regions_outlets_countries_topics_and_model(client):
    response = client.get("/api/registry")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=3600"
    body = response.json()
    assert body["model"] == {
        "name": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "revision": "3216a57f2a0d9c45a2e6c20157c20c49fb4bf9c7",
    }
    regions = body["regions"]
    assert [r["key"] for r in regions] == ["americas", "europe", "asia_pacific", "mea"]
    assert regions[0]["name"] == "Americas"
    assert regions[0]["feeds"][0] == {"name": "NPR", "country": "United States"}
    assert {"iso3": "BGD", "name": "Bangladesh"} in regions[2]["countries"]
    assert sum(len(r["countries"]) for r in regions) == 202
    topics = {t["key"]: t for t in body["topics"]}
    assert list(topics) == ["economy", "conflict", "politics", "climate", "tech"]
    assert topics["economy"]["name"] == "Economy"
    assert {"econom…", "inflation", "IMF"} <= set(topics["economy"]["keywords"])
    assert not any("*" in k for t in body["topics"] for k in t["keywords"])
    assert body["windows"] == [7, 30, 90]
    assert body["baseline_days"] == 7


def test_snapshot_returns_scored_headlines_with_topics_and_feed_status(client):
    response = client.get("/api/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["taken_at"]).tzinfo is not None
    assert body["newly_scored"] == 3
    assert body["headlines"][0] == {
        "id": headline_id("Markets rally"),
        "title": "Markets rally",
        "link": "https://example.com/rally",
        "source": "NPR",
        "region": "americas",
        "published": PUBLISHED.isoformat(),
        "label": "positive",
        "scores": {"negative": 0.1, "neutral": 0.2, "positive": 0.7},
        "index": 60.0,
        "topics": ["economy"],
    }
    assert [
        (h["title"], h["label"], h["index"], h["topics"], h["published"])
        for h in body["headlines"]
    ] == [
        ("Markets rally", "positive", 60.0, ["economy"], PUBLISHED.isoformat()),
        ("Storm hits coast", "negative", -75.0, ["climate"], None),
        ("Talks resume", "neutral", 0.0, [], None),
    ]
    assert body["sources"] == SOURCES
    assert body["alerts"] == []
    assert body["stories"] == []


def test_snapshot_summarises_every_region_in_registry_order(client):
    regions = client.get("/api/snapshot").json()["regions"]

    assert [r["key"] for r in regions] == ["americas", "europe", "asia_pacific", "mea"]
    americas, europe, _, mea = regions
    assert americas["name"] == "Americas"
    assert americas["headlines"] == 2
    assert americas["index"] == -7.5
    assert americas["shares"] == pytest.approx(
        {"negative": 0.5, "neutral": 0.0, "positive": 0.5}
    )
    assert europe["shares"] == pytest.approx(
        {"negative": 0.0, "neutral": 1.0, "positive": 0.0}
    )
    assert mea == {
        "key": "mea",
        "name": "Middle East & Africa",
        "headlines": 0,
        "index": 0.0,
        "shares": {"negative": 0.0, "neutral": 0.0, "positive": 0.0},
        "baseline": None,
    }


def test_snapshot_compares_regions_with_the_seven_days_before_today(
    client, monkeypatch, tmp_path
):
    americas = [30, 32, 28, 31, 29, 30, 30]
    collected(
        monkeypatch,
        tmp_path,
        trend=[
            *(
                DailyPoint(TODAY - timedelta(days=7 - i), "americas", value / 100, 5)
                for i, value in enumerate(americas)
            ),
            DailyPoint(TODAY - timedelta(days=8), "europe", 0.9, 5),
            DailyPoint(TODAY - timedelta(days=3), "europe", 0.1, 5),
            DailyPoint(TODAY - timedelta(days=2), "europe", 0.2, 5),
            DailyPoint(TODAY - timedelta(days=1), "europe", 0.3, 5),
            DailyPoint(TODAY, "europe", 0.9, 5),
        ],
    )

    body = client.get("/api/snapshot").json()

    baselines = {r["key"]: r["baseline"] for r in body["regions"]}
    assert baselines == {
        "americas": 30.0,
        "europe": 20.0,
        "asia_pacific": None,
        "mea": None,
    }
    assert body["alerts"] == [
        {
            "region": "americas",
            "today": -7.5,
            "mean": 30.0,
            "z": round((-7.5 - 30) / math.sqrt(10 / 6), 1),
        }
    ]


def test_snapshot_groups_one_story_told_in_several_regions(client, news):
    europe = Headline(
        headline_id("Markets rally in Europe"),
        "Markets rally in Europe",
        None,
        "BBC News",
        "europe",
        None,
    )
    news.headlines = [*HEADLINES, europe]

    body = client.get("/api/snapshot").json()

    assert body["stories"] == [
        {
            "lead": headline_id("Markets rally"),
            "regions": ["americas", "europe"],
            "headlines": [headline_id("Markets rally"), europe.id],
        }
    ]


def test_snapshot_is_reused_between_requests(client, news):
    first = client.get("/api/snapshot").json()["taken_at"]
    second = client.get("/api/snapshot").json()["taken_at"]

    assert first == second
    assert news.fetches == 1
    assert sorted(news.scored) == sorted(h.title for h in HEADLINES)


def test_expired_snapshot_refetches_without_rescoring(client, news, monkeypatch):
    monkeypatch.setattr(api_module, "SNAPSHOT_TTL_SECONDS", 0)

    assert client.get("/api/snapshot").status_code == 200
    second = client.get("/api/snapshot").json()

    assert news.fetches == 2
    assert sorted(news.scored) == sorted(h.title for h in HEADLINES)
    assert second["newly_scored"] == 0


def test_concurrent_callers_take_one_snapshot(news, monkeypatch):
    def slow_fetch():
        time.sleep(0.2)
        return FakeNews.fetch(news)

    monkeypatch.setattr(api_module, "fetch_headlines", slow_fetch)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(api_module.latest_snapshot()))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert news.fetches == 1
    assert len({id(snapshot) for snapshot in results}) == 1


def test_snapshot_returns_503_with_feed_status_when_no_headlines(client, news):
    news.headlines = []

    response = client.get("/api/snapshot")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "No headlines available from news sources",
        "sources": SOURCES,
    }


def test_empty_fetch_is_not_cached(client, news):
    news.headlines = []
    assert client.get("/api/snapshot").status_code == 503

    news.headlines = HEADLINES

    assert client.get("/api/snapshot").status_code == 200


def test_internal_errors_are_hidden(client, monkeypatch):
    def boom(texts):
        raise RuntimeError("secret /tmp/internal-path")

    monkeypatch.setattr(api_module, "score", boom)

    response = client.get("/api/snapshot")

    assert response.status_code == 503
    assert response.json() == {"detail": "Sentiment service unavailable"}
    assert "secret" not in response.text
    assert "internal-path" not in response.text


def test_trends_reports_model_index_per_day_and_region(client):
    assert client.get("/api/snapshot").status_code == 200

    response = client.get("/api/trends", params={"days": 30})

    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["days"], body["origin"]) == (
        "model",
        30,
        "recorded by this instance",
    )
    assert body["points"] == [
        {"day": TODAY.isoformat(), "region": "americas", "value": -7.5, "headlines": 2},
        {"day": TODAY.isoformat(), "region": "europe", "value": 0.0, "headlines": 1},
    ]


def test_trends_reads_collected_history_from_a_local_file(
    client, monkeypatch, tmp_path
):
    collected(
        monkeypatch,
        tmp_path,
        trend=[
            DailyPoint(TODAY - timedelta(days=30), "mea", 0.5, 4),
            DailyPoint(TODAY - timedelta(days=1), "europe", -0.1234, 9),
        ],
    )

    body = client.get("/api/trends", params={"days": 7}).json()

    assert body["origin"] == f"collected history from {tmp_path / 'trend.csv'}"
    assert body["points"] == [
        {
            "day": (TODAY - timedelta(days=1)).isoformat(),
            "region": "europe",
            "value": -12.3,
            "headlines": 9,
        }
    ]


def test_trends_gdelt_serves_the_collected_tone_next_to_trend_csv(
    client, monkeypatch, tmp_path
):
    yesterday = TODAY - timedelta(days=1)
    (tmp_path / "gdelt.csv").write_text(
        history.format_gdelt(
            [
                DailyPoint(TODAY - timedelta(days=30), "mea", -1.98, 31000),
                DailyPoint(yesterday, "europe", -2.4321, 88000),
            ]
        )
    )
    monkeypatch.setattr(history, "HISTORY_SOURCE", str(tmp_path / "trend.csv"))

    response = client.get("/api/trends", params={"source": "gdelt", "days": 7})

    assert response.status_code == 200
    assert response.json() == {
        "source": "gdelt",
        "days": 7,
        "origin": f"collected history from {tmp_path / 'gdelt.csv'}",
        "points": [
            {
                "day": yesterday.isoformat(),
                "region": "europe",
                "value": -2.4321,
                "articles": 88000,
            }
        ],
    }


@pytest.mark.parametrize(
    "path, params",
    [
        ("/api/trends", {"days": 0}),
        ("/api/trends", {"days": 91}),
        ("/api/trends", {"source": "twitter"}),
        ("/api/countries/BGD", {"days": 0}),
        ("/api/countries/BGD", {"days": 91}),
    ],
)
def test_history_endpoints_reject_invalid_parameters(client, path, params):
    assert client.get(path, params=params).status_code == 422


def test_country_reports_its_own_outlets_daily_index(client, monkeypatch, tmp_path):
    collected(
        monkeypatch,
        tmp_path,
        sources=[
            SourceDay(TODAY - timedelta(days=40), "Prothom Alo", 0.9, 3),
            SourceDay(TODAY - timedelta(days=2), "Prothom Alo", 0.1, 4),
            SourceDay(TODAY - timedelta(days=1), "Prothom Alo", -0.158, 14),
            SourceDay(TODAY - timedelta(days=1), "NPR", 0.5, 10),
        ],
    )

    response = client.get("/api/countries/BGD")

    assert response.status_code == 200
    assert response.json() == {
        "iso3": "BGD",
        "name": "Bangladesh",
        "region": "asia_pacific",
        "outlets": ["Prothom Alo"],
        "fallback": False,
        "origin": f"collected history from {tmp_path / 'sources.csv'}",
        "points": [
            {
                "day": (TODAY - timedelta(days=2)).isoformat(),
                "value": 10.0,
                "headlines": 4,
            },
            {
                "day": (TODAY - timedelta(days=1)).isoformat(),
                "value": -15.8,
                "headlines": 14,
            },
        ],
    }


def test_country_without_outlets_falls_back_to_its_region(
    client, monkeypatch, tmp_path
):
    collected(
        monkeypatch,
        tmp_path,
        sources=[
            SourceDay(TODAY - timedelta(days=1), "NPR", 0.5, 10),
            SourceDay(TODAY - timedelta(days=1), "Prothom Alo", -0.9, 14),
        ],
    )

    body = client.get("/api/countries/MEX", params={"days": 7}).json()

    assert (body["name"], body["region"], body["fallback"]) == (
        "Mexico",
        "americas",
        True,
    )
    assert body["outlets"] == [
        "NPR",
        "New York Times",
        "CNBC",
        "CBC News",
        "Buenos Aires Times",
    ]
    assert body["points"] == [
        {"day": (TODAY - timedelta(days=1)).isoformat(), "value": 50.0, "headlines": 10}
    ]


def test_unknown_country_is_404(client):
    assert client.get("/api/countries/XYZ").status_code == 404


def test_health_is_shallow_liveness(client, monkeypatch):
    monkeypatch.setattr(api_module, "is_loaded", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ready_reports_model_state(client, monkeypatch):
    monkeypatch.setattr(api_module, "is_loaded", lambda: False)
    assert client.get("/ready").status_code == 503

    monkeypatch.setattr(api_module, "is_loaded", lambda: True)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_rate_limit_allows_60_api_requests_a_minute(client, monkeypatch):
    monkeypatch.setattr(api_module, "is_loaded", lambda: True)

    for _ in range(60):
        assert client.get("/api/registry").status_code == 200
    response = client.get("/api/trends")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200


def test_rate_limiter_forgets_idle_clients(client, monkeypatch):
    monkeypatch.setattr(api_module, "_next_prune_at", 0.0)
    stale = time.monotonic() - 2 * api_module.RATE_LIMIT_WINDOW_SECONDS
    api_module._request_times["idle-client"] = collections.deque([stale])
    api_module._request_times["empty-client"] = collections.deque()

    assert client.get("/api/registry").status_code == 200

    assert list(api_module._request_times) == ["testclient"]


def test_only_the_snapshot_waits_for_the_inference_slots(client, monkeypatch):
    monkeypatch.setattr(api_module, "_inference_semaphore", asyncio.Semaphore(0))
    monkeypatch.setattr(api_module, "QUEUE_TIMEOUT_SECONDS", 0.01)

    response = client.get("/api/snapshot")

    assert response.status_code == 503
    assert response.json() == {"detail": "Server busy, try again later"}
    assert client.get("/api/registry").status_code == 200
    assert client.get("/api/trends").status_code == 200
    assert client.get("/api/countries/BGD").status_code == 200
