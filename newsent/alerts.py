import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from newsent.store import DailyPoint


@dataclass(frozen=True, slots=True)
class Alert:
    region: str
    today: float
    mean: float
    std: float
    z: float


def detect(
    today: Mapping[str, float],
    history: Sequence[DailyPoint],
    threshold: float = 2.0,
    min_days: int = 5,
) -> list[Alert]:
    by_region: dict[str, list[float]] = {}
    for point in history:
        by_region.setdefault(point.region, []).append(point.value)

    alerts = []
    for region, value in today.items():
        days = by_region.get(region, [])
        if len(days) < max(min_days, 2):
            continue
        mean = statistics.fmean(days)
        std = statistics.stdev(days, mean)
        if std == 0:
            continue
        z = (value - mean) / std
        if abs(z) > threshold:
            alerts.append(Alert(region, value, mean, std, z))
    return sorted(alerts, key=lambda alert: abs(alert.z), reverse=True)
