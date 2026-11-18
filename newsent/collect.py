"""Scheduled collector for the model-sentiment and GDELT tone history."""

import argparse
import json
import sys
import tempfile
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path

from newsent import feeds, gdelt, history, model
from newsent.feeds import FeedStatus, Headline
from newsent.pipeline import Snapshot, take_snapshot
from newsent.scores import Scores
from newsent.store import DailyPoint, Store, retention_cutoff

GDELT_DAYS_PER_RUN = 15


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


def collect_gdelt(
    directory: Path,
    today: date,
    fetch_day: Callable[[date], list[DailyPoint]] = gdelt.fetch_day,
) -> list[date]:
    path = directory / history.GDELT_FILE
    mapping_path = directory / history.GDELT_COUNTRIES_FILE
    mapping = history.format_gdelt_countries(gdelt.REGION_BY_CAMEO)
    try:
        points = history.parse_gdelt(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        points = []
    except Exception as exc:
        print(f"GDELT: rebuilding unreadable {path.name}: {exc}", file=sys.stderr)
        points = []
    try:
        recorded_mapping = mapping_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        recorded_mapping = None
    if points and recorded_mapping != mapping:
        print(
            f"GDELT: rebuilding {path.name}: {mapping_path.name} does not match "
            "the current country mapping",
            file=sys.stderr,
        )
        points = []
    window = [today - timedelta(days=n) for n in range(1, history.TREND_DAYS + 1)]
    points = [p for p in points if p.day >= window[-1]]
    have = {p.day for p in points}
    added = []
    for day in [day for day in window if day not in have][:GDELT_DAYS_PER_RUN]:
        try:
            points += fetch_day(day)
        except gdelt.DayNotPublished:
            continue
        except Exception as exc:
            print(f"GDELT: stopped at {day}: {exc}", file=sys.stderr)
            break
        added.append(day)
    points.sort(key=lambda p: (p.day, p.region))
    path.write_text(history.format_gdelt(points), encoding="utf-8")
    mapping_path.write_text(mapping, encoding="utf-8")
    return added


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
    added = collect_gdelt(args.directory, snapshot.taken_at.date())
    print(f"GDELT tone added for {len(added)} day(s)")
    if ok == 0:
        sys.exit("no news feed responded")


if __name__ == "__main__":
    main()
