import pytest

from newsent.scores import Scores, to_scores


def test_to_scores_matches_labels_case_insensitively_and_clamps():
    result = [
        {"label": "Positive", "score": 1.4},
        {"label": "NEGATIVE", "score": -0.2},
        {"label": "mixed", "score": 0.9},
    ]

    assert to_scores(result) == Scores(negative=0.0, neutral=0.0, positive=1.0)


def test_to_scores_reads_all_three_classes():
    result = [
        {"label": "negative", "score": 0.1},
        {"label": "neutral", "score": 0.3},
        {"label": "positive", "score": 0.6},
    ]

    assert to_scores(result) == Scores(negative=0.1, neutral=0.3, positive=0.6)


def test_missing_labels_score_zero():
    assert to_scores([]) == Scores(0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("scores", "label"),
    [
        (Scores(negative=0.7, neutral=0.2, positive=0.1), "negative"),
        (Scores(negative=0.2, neutral=0.5, positive=0.3), "neutral"),
        (Scores(negative=0.1, neutral=0.2, positive=0.7), "positive"),
    ],
)
def test_label_is_the_most_probable_class(scores, label):
    assert scores.label == label


def test_net_is_positive_minus_negative():
    assert Scores(negative=0.6, neutral=0.3, positive=0.1).net == pytest.approx(-0.5)
