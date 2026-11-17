import os
import tempfile
from collections.abc import Sequence
from functools import lru_cache

# huggingface_hub reads these when transformers is imported.
os.environ.setdefault(
    "HF_HOME", os.path.join(tempfile.gettempdir(), "realtime-news-sentiment-hf")
)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from transformers import pipeline

from newsent.scores import Scores, to_scores

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
MODEL_REVISION = "3216a57f2a0d9c45a2e6c20157c20c49fb4bf9c7"
BATCH_SIZE = 32
MAX_TOKENS = 64


@lru_cache(maxsize=1)
def get_pipeline():
    return pipeline(
        "text-classification",
        model=MODEL_NAME,
        revision=MODEL_REVISION,
        top_k=None,
        device="cpu",
    )


def is_loaded() -> bool:
    return get_pipeline.cache_info().currsize > 0


def score(texts: Sequence[str]) -> list[Scores]:
    if not texts:
        return []
    results = get_pipeline()(
        list(texts), batch_size=BATCH_SIZE, truncation=True, max_length=MAX_TOKENS
    )
    if len(results) != len(texts):
        raise RuntimeError(
            f"Model returned {len(results)} results for {len(texts)} headlines"
        )
    return [to_scores(result) for result in results]
