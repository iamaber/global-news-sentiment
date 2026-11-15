import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

import collections
import os
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend import api as api_module

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("cwd", "module"),
    [(REPO_ROOT / "backend", "api"), (REPO_ROOT, "backend.api")],
)
def test_api_module_imports_without_pythonpath(cwd, module):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(api_module, "warm_up_model", lambda: None)
    api_module._request_times.clear()
    with TestClient(api_module.app) as test_client:
        yield test_client


def test_root_returns_headlines_and_sentiment(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A", "B"], ["src", "src"], [])
    )
    monkeypatch.setattr(
        api_module,
        "analyze_sentiment",
        lambda texts: [{"label": "POSITIVE", "score": 0.9} for _ in texts],
    )

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == [
        {"headline": "A", "sentiment": {"label": "POSITIVE", "score": 0.9}},
        {"headline": "B", "sentiment": {"label": "POSITIVE", "score": 0.9}},
    ]


def test_root_returns_503_when_no_headlines(client, monkeypatch):
    monkeypatch.setattr(api_module, "fetch_headlines", lambda: ([], [], ["feed down"]))

    response = client.get("/")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "No headlines available from news sources"
    }


def test_root_hides_internal_exception(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A"], ["src"], [])
    )

    def boom(texts):
        raise RuntimeError("secret /tmp/internal-path")

    monkeypatch.setattr(api_module, "analyze_sentiment", boom)

    response = client.get("/")

    assert response.status_code == 503
    assert response.json() == {"detail": "Sentiment service unavailable"}
    assert "secret" not in response.text
    assert "internal-path" not in response.text


def test_root_rejects_count_mismatch(client, monkeypatch):
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A", "B"], ["src", "src"], [])
    )
    monkeypatch.setattr(
        api_module,
        "analyze_sentiment",
        lambda texts: [{"label": "POSITIVE", "score": 0.9}],
    )

    response = client.get("/")

    assert response.status_code == 502
    assert response.json() == {"detail": "Sentiment results were incomplete"}


def test_health_is_shallow_liveness(client, monkeypatch):
    monkeypatch.setattr(api_module, "is_model_loaded", lambda: False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ready_reports_model_state(client, monkeypatch):
    monkeypatch.setattr(api_module, "is_model_loaded", lambda: False)
    assert client.get("/ready").status_code == 503

    monkeypatch.setattr(api_module, "is_model_loaded", lambda: True)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_root_rate_limits(client, monkeypatch):
    monkeypatch.setattr(api_module, "RATE_LIMIT_REQUESTS", 1)
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A"], ["src"], [])
    )
    monkeypatch.setattr(
        api_module,
        "analyze_sentiment",
        lambda texts: [{"label": "POSITIVE", "score": 0.9} for _ in texts],
    )

    assert client.get("/").status_code == 200
    response = client.get("/")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "60"


def test_rate_limiter_forgets_idle_clients(client, monkeypatch):
    monkeypatch.setattr(api_module, "_next_prune_at", 0.0)
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A"], ["src"], [])
    )
    monkeypatch.setattr(
        api_module,
        "analyze_sentiment",
        lambda texts: [{"label": "POSITIVE", "score": 0.9} for _ in texts],
    )
    stale = time.monotonic() - 2 * api_module.RATE_LIMIT_WINDOW_SECONDS
    api_module._request_times["idle-client"] = collections.deque([stale])
    api_module._request_times["empty-client"] = collections.deque()

    assert client.get("/").status_code == 200

    assert list(api_module._request_times) == ["testclient"]


def test_root_works_when_lifespan_never_ran(monkeypatch):
    monkeypatch.setattr(
        api_module, "fetch_headlines", lambda: (["A"], ["src"], [])
    )
    monkeypatch.setattr(
        api_module,
        "analyze_sentiment",
        lambda texts: [{"label": "POSITIVE", "score": 0.9} for _ in texts],
    )
    api_module._request_times.clear()
    monkeypatch.delattr(
        api_module.app.state._state, "inference_semaphore", raising=False
    )

    response = TestClient(api_module.app).get("/")

    assert response.status_code == 200
