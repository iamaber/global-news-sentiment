import asyncio
import collections
import logging
import statistics
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from newsent import history
from newsent.alerts import detect
from newsent.countries import COUNTRIES, daily_index
from newsent.feeds import FeedStatus, fetch_headlines
from newsent.model import MODEL_NAME, MODEL_REVISION, get_pipeline, is_loaded, score
from newsent.pipeline import Scored, Snapshot, summarize, take_snapshot
from newsent.regions import REGIONS, REGIONS_BY_KEY
from newsent.scores import LABELS
from newsent.store import DailyPoint, Store
from newsent.stories import group_stories
from newsent.topics import TOPICS, topics_of

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_CONCURRENT_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 2.0
SNAPSHOT_TTL_SECONDS = 300
API_PREFIX = "/api/"
INFERENCE_PATHS = {"/api/snapshot"}
WINDOWS = (7, 30, 90)
BASELINE_DAYS = 7
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
NO_HEADLINES = "No headlines available from news sources"

Days = Annotated[int, Query(ge=1, le=90)]

REGISTRY = {
    "model": {"name": MODEL_NAME, "revision": MODEL_REVISION},
    "regions": [
        {
            "key": region.key,
            "name": region.name,
            "feeds": [
                {"name": feed.name, "country": feed.country} for feed in region.feeds
            ],
            "countries": [
                {"iso3": country.iso3, "name": country.name}
                for country in region.source_countries
            ],
        }
        for region in REGIONS
    ],
    "topics": [
        {
            "key": topic.key,
            "name": topic.name,
            "keywords": [
                word.replace("*", "…") for word in (*topic.keywords, *topic.exact)
            ],
        }
        for topic in TOPICS
    ],
    "windows": list(WINDOWS),
    "baseline_days": BASELINE_DAYS,
}

_request_times: dict[str, collections.deque[float]] = {}
_next_prune_at = 0.0
_inference_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

_snapshot_lock = threading.Lock()
_snapshot: tuple[float, Snapshot] | None = None


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


app = FastAPI(title="News Sentiment API", version="3.0.0", lifespan=lifespan)


@app.middleware("http")
async def protect_api(request: Request, call_next):
    if not request.url.path.startswith(API_PREFIX):
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
    """The cached snapshot, or a fresh one. A snapshot with no headlines is not cached."""
    global _snapshot
    with _snapshot_lock:
        if _snapshot and time.monotonic() - _snapshot[0] < SNAPSHOT_TTL_SECONDS:
            return _snapshot[1]
        with _hide_internal_errors():
            snapshot = take_snapshot(get_store(), fetch=fetch_headlines, score=score)
        if snapshot.items:
            _snapshot = (time.monotonic(), snapshot)
        return snapshot


def _index(net: float) -> float:
    return round(net * 100, 1)


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _headline(item: Scored) -> dict:
    headline, scores = item.headline, item.scores
    return {
        "id": headline.id,
        "title": headline.title,
        "link": headline.link,
        "source": headline.source,
        "region": headline.region,
        "published": _iso(headline.published),
        "label": scores.label,
        "scores": {label: getattr(scores, label) for label in LABELS},
        "index": _index(scores.net),
        "topics": list(topics_of(headline.title)),
    }


def _source(status: FeedStatus) -> dict:
    return {
        "source": status.source,
        "region": status.region,
        "headlines": status.headlines,
        "seconds": status.seconds,
        "error": status.error,
    }


def _baseline_days() -> list[DailyPoint]:
    """Daily model index per region over the BASELINE_DAYS days ending yesterday."""
    yesterday = datetime.now(UTC).date() - timedelta(days=1)
    with _hide_internal_errors():
        points, _ = history.model_trend(get_store(), BASELINE_DAYS, until=yesterday)
    return [DailyPoint(p.day, p.region, p.value * 100, p.headlines) for p in points]


def _stories(items: list[Scored]) -> list[dict]:
    stories = group_stories([(i.headline.title, i.headline.region) for i in items])
    return [
        {
            "lead": items[story.lead].headline.id,
            "regions": [r.key for r in REGIONS if r.key in story.regions],
            "headlines": [items[member].headline.id for member in story.members],
        }
        for story in stories
    ]


@app.get("/api/registry")
def get_registry(response: Response):
    """Regions with their outlets and countries, topics, and the model."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return REGISTRY


@app.get("/api/snapshot")
def get_snapshot():
    """Scored headlines, feed status, region summaries, alerts and stories."""
    snapshot = latest_snapshot()
    sources = [_source(status) for status in snapshot.statuses]
    if not snapshot.items:
        return JSONResponse(
            {"detail": NO_HEADLINES, "sources": sources}, status_code=503
        )

    summaries = summarize(snapshot.items)
    baseline_days = _baseline_days()
    by_region: dict[str, list[float]] = {}
    for point in baseline_days:
        by_region.setdefault(point.region, []).append(point.value)
    baseline = {key: statistics.fmean(values) for key, values in by_region.items()}
    today = {s.region: s.net * 100 for s in summaries if s.headlines}

    return {
        "taken_at": snapshot.taken_at.isoformat(),
        "newly_scored": snapshot.newly_scored,
        "headlines": [_headline(item) for item in snapshot.items],
        "sources": sources,
        "regions": [
            {
                "key": summary.region,
                "name": REGIONS_BY_KEY[summary.region].name,
                "headlines": summary.headlines,
                "index": _index(summary.net),
                "shares": summary.shares,
                "baseline": round(baseline[summary.region], 1)
                if summary.region in baseline
                else None,
            }
            for summary in summaries
        ],
        "alerts": [
            {
                "region": alert.region,
                "today": round(alert.today, 1),
                "mean": round(alert.mean, 1),
                "z": round(alert.z, 1),
            }
            for alert in detect(today, baseline_days)
        ],
        "stories": _stories(snapshot.items),
    }


@app.get("/api/trends")
def get_trends(days: Days = 30, source: Literal["model", "gdelt"] = "model"):
    """Daily per-region series: our model's index, or GDELT's tone."""
    if source == "model":
        with _hide_internal_errors():
            points, origin = history.model_trend(get_store(), days)
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

    points, origin = history.gdelt_trend(days)
    return {
        "source": source,
        "days": days,
        "origin": origin,
        "points": [
            {
                "day": p.day.isoformat(),
                "region": p.region,
                "value": p.value,
                "articles": p.headlines,
            }
            for p in points
        ],
    }


@app.get("/api/countries/{iso3}")
def get_country(iso3: str, days: Days = 30):
    """A country's outlets, or its region's when it has none, and their daily index."""
    entry = COUNTRIES.get(iso3)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Unknown country: {iso3}")
    feeds = entry.feeds or entry.region.feeds
    with _hide_internal_errors():
        points, origin = history.source_trend(get_store(), days)
    series = daily_index(points, {feed.name for feed in feeds})
    return {
        "iso3": iso3,
        "name": entry.country.name,
        "region": entry.region.key,
        "outlets": [feed.name for feed in feeds],
        "fallback": not entry.feeds,
        "origin": origin,
        "points": [
            {
                "day": p.day.isoformat(),
                "value": _index(p.value),
                "headlines": p.headlines,
            }
            for p in series
        ],
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


app.mount(
    "/",
    StaticFiles(directory=FRONTEND_DIR, html=True, check_dir=False),
    name="frontend",
)
