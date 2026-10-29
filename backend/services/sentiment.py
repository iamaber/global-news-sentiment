from functools import lru_cache

from transformers import pipeline

from model_config import MODEL_NAME, MODEL_REVISION


@lru_cache(maxsize=1)
def get_sentiment_model():
    """Load the model on first use instead of at import time."""
    return pipeline(
        "sentiment-analysis", model=MODEL_NAME, revision=MODEL_REVISION
    )


def analyze_sentiment(texts):
    if not texts:
        return []
    return get_sentiment_model()(texts)
