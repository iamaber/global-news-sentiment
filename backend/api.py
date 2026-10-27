from fastapi import FastAPI, HTTPException

from news_sources import fetch_headlines
from services.sentiment import analyze_sentiment

app = FastAPI(title="News Sentiment Analysis API", version="1.0.0")


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
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Sentiment service unavailable: {exc}"
        ) from exc

    return [{"headline": h, "sentiment": s} for h, s in zip(headlines, sentiments)]


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
