from functools import lru_cache

from transformers import pipeline

MODEL_NAME = "distilbert-base-uncased-finetuned-sst-2-english"


@lru_cache(maxsize=1)
def get_sentiment_model():
    """Load the model on first use instead of at import time."""
    return pipeline("sentiment-analysis", model=MODEL_NAME)


def analyze_sentiment(texts):
    if not texts:
        return []
    return get_sentiment_model()(texts)
