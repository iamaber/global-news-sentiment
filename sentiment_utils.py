"""Pure helpers for headline deduplication and sentiment aggregation.

This module intentionally depends only on the standard library so it can be
tested without installing torch, transformers or streamlit.
"""

from collections import Counter
from typing import Iterable, Mapping, Sequence

UNKNOWN_SOURCE = "Unknown Source"


def extract_titles(entries: Iterable[Mapping]) -> list[str]:
    """Return the non-empty, stripped titles from feed entries."""
    titles = []
    for entry in entries:
        title = entry.get("title")
        if isinstance(title, str) and title.strip():
            titles.append(title.strip())
    return titles


def dedupe_and_limit(
    headlines: Sequence[str], sources: Sequence[str], limit: int
) -> tuple[list[str], list[str]]:
    """Remove duplicates while preserving order and cap the result."""
    if limit <= 0:
        return [], []

    seen: set[str] = set()
    unique_headlines: list[str] = []
    unique_sources: list[str] = []

    for index, headline in enumerate(headlines):
        if not isinstance(headline, str):
            continue
        key = headline.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique_headlines.append(headline.strip())
        source = sources[index] if index < len(sources) else UNKNOWN_SOURCE
        unique_sources.append(source)
        if len(unique_headlines) >= limit:
            break

    return unique_headlines, unique_sources


def normalize_sentiment(result: Mapping | None) -> dict:
    """Normalize a transformers pipeline result into a label/score dict."""
    label = "UNKNOWN"
    score = 0.0

    if isinstance(result, Mapping):
        raw_label = result.get("label")
        if raw_label:
            label = str(raw_label).upper()
        try:
            score = float(result.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0

    return {"label": label, "score": max(0.0, min(1.0, score))}


def aggregate_sentiment(results: Iterable[Mapping | None]) -> dict:
    """Aggregate sentiment results into counts, percentages and confidence."""
    normalized = [normalize_sentiment(result) for result in results]
    counts = Counter(item["label"] for item in normalized)
    total = len(normalized)

    percentages = {
        label: (count / total * 100.0 if total else 0.0)
        for label, count in counts.items()
    }
    average_confidence = (
        sum(item["score"] for item in normalized) / total if total else 0.0
    )

    return {
        "total": total,
        "counts": dict(counts),
        "percentages": percentages,
        "average_confidence": average_confidence,
    }
