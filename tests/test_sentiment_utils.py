from sentiment_utils import (
    aggregate_sentiment,
    dedupe_and_limit,
    extract_titles,
    normalize_sentiment,
)


def test_extract_titles_skips_blank_and_non_string_values():
    entries = [
        {"title": "  First headline  "},
        {"title": ""},
        {"title": None},
        {"summary": "no title here"},
        {"title": "Second headline"},
    ]

    assert extract_titles(entries) == ["First headline", "Second headline"]


def test_dedupe_preserves_order_and_respects_limit():
    headlines = ["Alpha", "beta", "ALPHA", "Gamma", "Delta"]
    sources = ["A", "B", "C", "D"]

    deduped, deduped_sources = dedupe_and_limit(headlines, sources, limit=3)

    assert deduped == ["Alpha", "beta", "Gamma"]
    assert deduped_sources == ["A", "B", "D"]


def test_dedupe_with_non_positive_limit_returns_empty():
    assert dedupe_and_limit(["a"], ["b"], limit=0) == ([], [])


def test_normalize_sentiment_uppercases_clamps_and_handles_bad_input():
    assert normalize_sentiment({"label": "positive", "score": 1.4}) == {
        "label": "POSITIVE",
        "score": 1.0,
    }
    assert normalize_sentiment({"label": "negative", "score": "0.25"}) == {
        "label": "NEGATIVE",
        "score": 0.25,
    }
    assert normalize_sentiment(None) == {"label": "UNKNOWN", "score": 0.0}


def test_aggregate_sentiment_reports_counts_percentages_and_confidence():
    results = [
        {"label": "POSITIVE", "score": 0.9},
        {"label": "POSITIVE", "score": 0.7},
        {"label": "NEGATIVE", "score": 0.6},
        {"label": "NEGATIVE", "score": 1.0},
    ]

    summary = aggregate_sentiment(results)

    assert summary["total"] == 4
    assert summary["counts"] == {"POSITIVE": 2, "NEGATIVE": 2}
    assert summary["percentages"] == {"POSITIVE": 50.0, "NEGATIVE": 50.0}
    assert summary["average_confidence"] == 0.8


def test_aggregate_sentiment_empty_input():
    summary = aggregate_sentiment([])

    assert summary == {
        "total": 0,
        "counts": {},
        "percentages": {},
        "average_confidence": 0.0,
    }
