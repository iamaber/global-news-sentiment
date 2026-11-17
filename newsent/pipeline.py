from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from newsent import feeds
from newsent.feeds import FeedStatus, Headline
from newsent.regions import REGIONS
from newsent.scores import LABELS, Scores
from newsent.store import Store


@dataclass(frozen=True, slots=True)
class Scored:
    headline: Headline
    scores: Scores


@dataclass(frozen=True, slots=True)
class Snapshot:
    taken_at: datetime
    items: list[Scored]
    statuses: list[FeedStatus]
    newly_scored: int


@dataclass(frozen=True, slots=True)
class RegionSummary:
    region: str
    headlines: int
    net: float
    shares: dict[str, float]


def take_snapshot(
    store: Store,
    score: Callable[[Sequence[str]], list[Scores]],
    fetch: Callable[
        [], tuple[list[Headline], list[FeedStatus]]
    ] = feeds.fetch_headlines,
) -> Snapshot:
    taken_at = datetime.now(UTC)
    headlines, statuses = fetch()
    known = store.known_scores([h.id for h in headlines])
    missing = [h for h in headlines if h.id not in known]
    fresh = score([h.title for h in missing])
    if len(fresh) != len(missing):
        raise RuntimeError("Sentiment results were incomplete")
    store.save(zip(missing, fresh, strict=True), taken_at)
    known.update((h.id, s) for h, s in zip(missing, fresh, strict=True))
    items = [Scored(h, known[h.id]) for h in headlines]
    return Snapshot(taken_at, items, statuses, len(missing))


def summarize(items: Iterable[Scored]) -> list[RegionSummary]:
    grouped: dict[str, list[Scores]] = {region.key: [] for region in REGIONS}
    for item in items:
        grouped.setdefault(item.headline.region, []).append(item.scores)

    summaries = []
    for region, scores in grouped.items():
        total = len(scores)
        shares = {label: 0.0 for label in LABELS}
        for s in scores:
            shares[s.label] += 1 / total
        summaries.append(
            RegionSummary(
                region=region,
                headlines=total,
                net=sum(s.net for s in scores) / total if total else 0.0,
                shares=shares,
            )
        )
    return summaries
