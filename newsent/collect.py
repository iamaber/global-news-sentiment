"""Scheduled collector for the model-sentiment history."""

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from newsent import feeds, history, model
from newsent.feeds import FeedStatus, Headline
from newsent.pipeline import Snapshot, take_snapshot
from newsent.scores import Scores
from newsent.store import Store, retention_cutoff


def collect(
    directory: Path,
    score: Callable[[Sequence[str]], list[Scores]],
    fetch: Callable[
        [], tuple[list[Headline], list[FeedStatus]]
    ] = feeds.fetch_headlines,
) -> Snapshot:
    days_dir = directory / "days"
    days_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "history.db")
        for path in sorted(days_dir.glob("*.jsonl")):
            with path.open(encoding="utf-8") as file:
                store.import_rows(json.loads(line) for line in file if line.strip())

        snapshot = take_snapshot(store, score=score, fetch=fetch)

        new_by_day: dict[str, list[dict]] = defaultdict(list)
        for row in store.rows_seen_at(snapshot.taken_at):
            new_by_day[row["day"]].append(row)
        for day, rows in new_by_day.items():
            with (days_dir / f"{day}.jsonl").open("a", encoding="utf-8") as file:
                file.writelines(
                    json.dumps(row, ensure_ascii=False) + "\n" for row in rows
                )

        cutoff = retention_cutoff(snapshot.taken_at)
        for path in days_dir.glob("*.jsonl"):
            if date.fromisoformat(path.stem) < cutoff:
                path.unlink()

        until = snapshot.taken_at.date()
        (directory / "trend.csv").write_text(
            history.format_trend(store.model_trend(history.TREND_DAYS, until)),
            encoding="utf-8",
        )
        (directory / history.SOURCES_FILE).write_text(
            history.format_sources(store.source_trend(history.TREND_DAYS, until)),
            encoding="utf-8",
        )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    snapshot = collect(args.directory, score=model.score)
    ok = sum(status.error is None for status in snapshot.statuses)
    print(
        f"{len(snapshot.items)} headlines fetched, {snapshot.newly_scored} newly "
        f"scored, {ok}/{len(snapshot.statuses)} feeds ok"
    )
    if ok == 0:
        sys.exit("no news feed responded")


if __name__ == "__main__":
    main()
