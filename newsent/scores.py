from collections.abc import Mapping, Sequence
from dataclasses import dataclass

LABELS = ("negative", "neutral", "positive")


@dataclass(frozen=True, slots=True)
class Scores:
    negative: float
    neutral: float
    positive: float

    @property
    def label(self) -> str:
        return max(LABELS, key=lambda name: getattr(self, name))

    @property
    def net(self) -> float:
        return self.positive - self.negative


def to_scores(result: Sequence[Mapping]) -> Scores:
    probabilities = {name: 0.0 for name in LABELS}
    for item in result:
        name = str(item.get("label", "")).lower()
        if name in probabilities:
            probabilities[name] = min(1.0, max(0.0, float(item.get("score", 0.0))))
    return Scores(**probabilities)
