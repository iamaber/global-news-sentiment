import asyncio
import collections
import logging
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from newsent import gdelt, history
from newsent.feeds import fetch_headlines
from newsent.model import get_pipeline, is_loaded, score
from newsent.pipeline import Snapshot, summarize, take_snapshot
from newsent.regions import REGIONS, REGIONS_BY_KEY
from newsent.scores import LABELS
from newsent.store import Store

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_CONCURRENT_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 2.0
SNAPSHOT_TTL_SECONDS = 300
PUBLIC_PATHS = {"/health", "/ready"}
INFERENCE_PATHS = {"/headlines", "/regions"}

_request_times: dict[str, collections.deque[float]] = {}
_next_prune_at = 0.0
_inference_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

_snapshot_lock = threading.Lock()
_snapshot: tuple[float, Snapshot] | None = None
_gdelt_lock = threading.Lock()


def warm_up_model() -> None:
    get_pipeline()


@lru_cache(maxsize=1)
def get_store() -> Store:
    return Store()


def _prune_idle_clients(now: float) -> None:
    global _next_prune_at
    if now < _next_prune_at:
        return
    _next_prune_at = now + RATE_LIMIT_WINDOW_SECONDS
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    idle = [
        client
        for client, events in _request_times.items()
        if not events or events[-1] < window_start
    ]
    for client in idle:
        del _request_times[client]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        await asyncio.to_thread(warm_up_model)
        logger.info("Sentiment model loaded")
    except Exception:
        logger.exception("Could not warm up the sentiment model")
    yield


app = FastAPI(title="News Sentiment API", version="2.0.0", lifespan=lifespan)


@app.middleware("http")
async def protect_expensive_endpoints(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    _prune_idle_clients(now)
    events = _request_times.setdefault(client, collections.deque())
    while events and events[0] < window_start:
        events.popleft()
    if len(events) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            {"detail": "Rate limit exceeded"},
            status_code=429,
            headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)},
        )
    events.append(now)

    if request.url.path not in INFERENCE_PATHS:
        return await call_next(request)

    try:
        await asyncio.wait_for(
            _inference_semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS
        )
    except TimeoutError:
        return JSONResponse({"detail": "Server busy, try again later"}, status_code=503)

    try:
        return await call_next(request)
    finally:
        _inference_semaphore.release()


@contextmanager
def _hide_internal_errors():
    try:
        yield
    except Exception:
        logger.exception("Sentiment service unavailable")
        raise HTTPException(
            status_code=503, detail="Sentiment service unavailable"
        ) from None


def latest_snapshot() -> Snapshot:
    global _snapshot
    with _snapshot_lock:
        if _snapshot and time.monotonic() - _snapshot[0] < SNAPSHOT_TTL_SECONDS:
            return _snapshot[1]
        with _hide_internal_errors():
            snapshot = take_snapshot(get_store(), fetch=fetch_headlines, score=score)
        if not snapshot.items:
            raise HTTPException(
                status_code=503, detail="No headlines available from news sources"
            )
        _snapshot = (time.monotonic(), snapshot)
        return snapshot


def _index(net: float) -> float:
    return round(net * 100, 1)


@app.get("/headlines")
def get_headlines():
    """Latest scored headlines from every regional feed, plus per-feed status."""
    snapshot = latest_snapshot()
    return {
        "taken_at": snapshot.taken_at.isoformat(),
        "headlines": [
            {
                "id": item.headline.id,
                "title": item.headline.title,
                "link": item.headline.link,
                "source": item.headline.source,
                "region": item.headline.region,
                "published": item.headline.published.isoformat()
                if item.headline.published
                else None,
                "label": item.scores.label,
                "scores": {label: getattr(item.scores, label) for label in LABELS},
                "index": _index(item.scores.net),
            }
            for item in snapshot.items
        ],
        "sources": [
            {
                "source": status.source,
                "region": status.region,
                "headlines": status.headlines,
                "seconds": status.seconds,
                "error": status.error,
            }
            for status in snapshot.statuses
        ],
    }


@app.get("/regions")
def get_regions():
    """Per-region headline count, sentiment index and label shares."""
    snapshot = latest_snapshot()
    return {
        "taken_at": snapshot.taken_at.isoformat(),
        "regions": [
            {
                "key": summary.region,
                "name": REGIONS_BY_KEY[summary.region].name,
                "headlines": summary.headlines,
                "index": _index(summary.net),
                "shares": summary.shares,
            }
            for summary in summarize(snapshot.items)
        ],
    }


@app.get("/trends")
def get_trends(
    days: int = Query(30, ge=1, le=90),
    source: Literal["model", "gdelt"] = "model",
):
    """Daily per-region series: our model's index, or GDELT's tone."""
    store = get_store()
    if source == "model":
        with _hide_internal_errors():
            points, origin = history.model_trend(store, days)
        return {
            "source": source,
            "days": days,
            "origin": origin,
            "points": [
                {
                    "day": p.day.isoformat(),
                    "region": p.region,
                    "value": _index(p.value),
                    "headlines": p.headlines,
                }
                for p in points
            ],
        }

    with _hide_internal_errors():
        with _gdelt_lock:
            errors = gdelt.refresh(store, REGIONS)
        points = store.gdelt_trend(days)
    return {
        "source": source,
        "days": days,
        "points": [
            {
                "day": p.day.isoformat(),
                "region": p.region,
                "value": p.value,
                "headlines": p.headlines,
            }
            for p in points
        ],
        "errors": errors,
    }


@app.get("/health")
def health_check():
    """Liveness check: the process is serving requests"""
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check():
    """Readiness check: the sentiment model is loaded"""
    if not is_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready"}
