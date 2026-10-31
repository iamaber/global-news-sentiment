from functools import lru_cache

from model_config import MODEL_NAME, MODEL_REVISION


@lru_cache(maxsize=1)
def get_sentiment_model():
    """Load the model on first use instead of at import time."""
    from transformers import pipeline

    return pipeline(
        "sentiment-analysis", model=MODEL_NAME, revision=MODEL_REVISION
    )


def warm_up_model():
    """Load the model eagerly so startup failures surface in the logs."""
    get_sentiment_model()


def is_model_loaded():
    """Return True once the model pipeline has been loaded successfully."""
    return get_sentiment_model.cache_info().currsize > 0


def analyze_sentiment(texts):
    if not texts:
        return []
    return get_sentiment_model()(texts)
