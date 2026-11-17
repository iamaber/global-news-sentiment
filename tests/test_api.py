import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import collections
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from backend import api as api_module
from newsent import gdelt
from newsent.feeds import FeedStatus, Headline, headline_id
from newsent.regions import REGIONS
from newsent.scores import Scores

REPO_ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = datetime.now(UTC).replace(microsecond=0) - timedelta(days=1)
SCORES = {
    "Markets rally": Scores(negative=0.1, neutral=0.2, positive=0.7),
    "Storm hits coast": Scores(negative=0.8, neutral=0.15, positive=0.05),
    "Talks resume": Scores(negative=0.2, neutral=0.6, positive=0.2),
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


def test_headlines_returns_scored_headlines_and_feed_status(client):
    response = client.get("/headlines")

    assert response.status_code == 200
    body = response.json()
    assert datetime.fromisoformat(body["taken_at"]).tzinfo is not None
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
    }
    assert [(h["title"], h["label"], h["index"]) for h in body["headlines"]] == [
        ("Markets rally", "positive", 60.0),
        ("Storm hits coast", "negative", -75.0),
        ("Talks resume", "neutral", 0.0),
    ]
    assert body["headlines"][1]["published"] is None
    assert body["sources"] == [
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


def test_regions_summarises_every_region(client):
    response = client.get("/regions")

    assert response.status_code == 200
    regions = {r["key"]: r for r in response.json()["regions"]}
    assert set(regions) == {r.key for r in REGIONS}
    americas = regions["americas"]
    assert americas["name"] == "Americas"
    assert americas["headlines"] == 2
    assert americas["index"] == pytest.approx(-7.5)
    assert americas["shares"] == pytest.approx(
        {"negative": 0.5, "neutral": 0.0, "positive": 0.5}
    )
    assert sum(regions["europe"]["shares"].values()) == pytest.approx(1.0)
    assert regions["mea"]["headlines"] == 0
    assert regions["mea"]["name"] == "Middle East & Africa"


def test_headlines_and_regions_share_one_snapshot(client, news):
    first = client.get("/headlines").json()["taken_at"]
    second = client.get("/regions").json()["taken_at"]

    assert first == second
    assert news.fetches == 1
    assert sorted(news.scored) == sorted(SCORES)


def test_expired_snapshot_refetches_without_rescoring(client, news, monkeypatch):
    monkeypatch.setattr(api_module, "SNAPSHOT_TTL_SECONDS", 0)

    assert client.get("/headlines").status_code == 200
    assert client.get("/headlines").status_code == 200

    assert news.fetches == 2
    assert sorted(news.scored) == sorted(SCORES)


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


def test_trends_reports_model_index_per_day_and_region(client):
    assert client.get("/headlines").status_code == 200

    response = client.get("/trends", params={"days": 30})

    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["days"]) == ("model", 30)
    today = datetime.now(UTC).date().isoformat()
    assert body["points"] == [
        {"day": today, "region": "americas", "value": -7.5, "headlines": 2},
        {"day": today, "region": "europe", "value": 0.0, "headlines": 1},
    ]


def test_trends_gdelt_refreshes_stale_regions_and_reports_errors(client, monkeypatch):
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    timeline = json.dumps(
        {
            "timeline": [
                {
                    "data": [
                        {"date": yesterday.strftime("%Y%m%dT000000Z"), "value": -1.5},
                        {"date": today.strftime("%Y%m%dT000000Z"), "value": 0.25},
                    ]
                }
            ]
        }
    )

    def fake_get(url):
        if "sourcecountry:qatar" in urllib.parse.unquote_plus(url):
            raise OSError("unreachable")
        return timeline

    monkeypatch.setattr(gdelt, "MIN_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(gdelt, "_get", fake_get)

    response = client.get("/trends", params={"source": "gdelt", "days": 7})

    assert response.status_code == 200
    body = response.json()
    assert (body["source"], body["days"]) == ("gdelt", 7)
    assert body["errors"] == {"mea": "unreachable"}
    assert {(p["day"], p["region"], p["value"]) for p in body["points"]} == {
        (day.isoformat(), region, value)
        for region in ("americas", "europe", "asia_pacific")
        for day, value in ((yesterday, -1.5), (today, 0.25))
    }


@pytest.mark.parametrize(
    "params",
    [{"days": 0}, {"days": 91}, {"source": "twitter"}],
)
def test_trends_rejects_invalid_parameters(client, params):
    assert client.get("/trends", params=params).status_code == 422


def test_headlines_returns_503_when_no_headlines(client, news):
    news.headlines = []

    response = client.get("/headlines")

    assert response.status_code == 503
    assert response.json() == {"detail": "No headlines available from news sources"}


def test_empty_fetch_is_not_cached(client, news):
    news.headlines = []
    assert client.get("/regions").status_code == 503

    news.headlines = HEADLINES

    assert client.get("/regions").status_code == 200


def test_internal_errors_are_hidden(client, monkeypatch):
    def boom(texts):
        raise RuntimeError("secret /tmp/internal-path")

    monkeypatch.setattr(api_module, "score", boom)

    response = client.get("/headlines")

    assert response.status_code == 503
    assert response.json() == {"detail": "Sentiment service unavailable"}
    assert "secret" not in response.text
    assert "internal-path" not in response.text


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


def test_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(api_module, "RATE_LIMIT_REQUESTS", 1)

    assert client.get("/headlines").status_code == 200
    response = client.get("/regions")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_rate_limiter_forgets_idle_clients(client, monkeypatch):
    monkeypatch.setattr(api_module, "_next_prune_at", 0.0)
    stale = time.monotonic() - 2 * api_module.RATE_LIMIT_WINDOW_SECONDS
    api_module._request_times["idle-client"] = collections.deque([stale])
    api_module._request_times["empty-client"] = collections.deque()

    assert client.get("/headlines").status_code == 200

    assert list(api_module._request_times) == ["testclient"]
