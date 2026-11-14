import asyncio
import collections
import logging
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# The API imports `services` from this directory and the shared modules
# (`news_sources`, `model_config`) from the repo root. Put both on sys.path here
# so `uvicorn api:app` (from backend/) and `uvicorn backend.api:app` (from the
# repo root) work without PYTHONPATH.
_BACKEND_DIR = Path(__file__).resolve().parent
for _path in (str(_BACKEND_DIR.parent), str(_BACKEND_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from news_sources import fetch_headlines  # noqa: E402
from services.sentiment import (  # noqa: E402
    analyze_sentiment,
    is_model_loaded,
    warm_up_model,
)

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
MAX_CONCURRENT_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 2.0
PUBLIC_PATHS = {"/health", "/ready"}

_request_times: dict[str, collections.deque[float]] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm the model at startup so the first request does not pay for it."""
    app.state.inference_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    try:
        await asyncio.to_thread(warm_up_model)
        logger.info("Sentiment model loaded")
    except Exception:
        logger.exception("Could not warm up the sentiment model")
    yield


app = FastAPI(
    title="News Sentiment Analysis API", version="1.0.0", lifespan=lifespan
)


@app.middleware("http")
async def protect_expensive_endpoint(request: Request, call_next):
    """Bound request rate and concurrent inference before reaching the model."""
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    client = request.client.host if request.client else "unknown"
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
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

    semaphore = request.app.state.inference_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=QUEUE_TIMEOUT_SECONDS)
    except TimeoutError:
        return JSONResponse(
            {"detail": "Server busy, try again later"}, status_code=503
        )

    try:
        return await call_next(request)
    finally:
        semaphore.release()


@app.get("/")
def get_news_sentiment():
    """Fetch latest news headlines and analyze their sentiment"""
    try:
        headlines, _sources, _errors = fetch_headlines()
        if not headlines:
            raise HTTPException(
                status_code=503, detail="No headlines available from news sources"
            )
        sentiments = analyze_sentiment(headlines)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Sentiment service unavailable")
        raise HTTPException(status_code=503, detail="Sentiment service unavailable")

    if len(sentiments) != len(headlines):
        logger.error(
            "Sentiment result count %d does not match headline count %d",
            len(sentiments),
            len(headlines),
        )
        raise HTTPException(status_code=502, detail="Sentiment results were incomplete")

    return [
        {"headline": headline, "sentiment": sentiment}
        for headline, sentiment in zip(headlines, sentiments, strict=True)
    ]


@app.get("/health")
def health_check():
    """Liveness check: the process is serving requests"""
    return {"status": "healthy"}


@app.get("/ready")
def readiness_check():
    """Readiness check: the sentiment model is loaded"""
    if not is_model_loaded():
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready"}
