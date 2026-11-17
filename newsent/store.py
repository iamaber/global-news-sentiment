import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from newsent.feeds import Headline
from newsent.scores import Scores

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news_sentiment.db"
RETENTION_DAYS = 120
SQLITE_MAX_VARIABLES = 900

SCHEMA = """
CREATE TABLE IF NOT EXISTS headlines (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT,
    source TEXT NOT NULL,
    region TEXT NOT NULL,
    published TEXT,
    first_seen TEXT NOT NULL,
    day TEXT NOT NULL,
    negative REAL NOT NULL,
    neutral REAL NOT NULL,
    positive REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS headlines_day_region ON headlines (day, region);
CREATE TABLE IF NOT EXISTS gdelt_tone (
    region TEXT NOT NULL,
    day TEXT NOT NULL,
    tone REAL NOT NULL,
    PRIMARY KEY (region, day)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS gdelt_fetch (
    region TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class DailyPoint:
    day: date
    region: str
    value: float
    headlines: int = 0


class Store:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path or os.environ.get("NEWS_SENTIMENT_DB") or DEFAULT_DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            with db:
                yield db

    def known_scores(self, ids: Sequence[str]) -> dict[str, Scores]:
        found: dict[str, Scores] = {}
        with self._connect() as db:
            for start in range(0, len(ids), SQLITE_MAX_VARIABLES):
                chunk = ids[start : start + SQLITE_MAX_VARIABLES]
                rows = db.execute(
                    "SELECT id, negative, neutral, positive FROM headlines "
                    f"WHERE id IN ({','.join('?' * len(chunk))})",
                    chunk,
                )
                found.update((row[0], Scores(*row[1:])) for row in rows)
        return found

    def save(
        self, scored: Iterable[tuple[Headline, Scores]], seen_at: datetime
    ) -> None:
        rows = [
            (
                h.id,
                h.title,
                h.link,
                h.source,
                h.region,
                h.published.isoformat() if h.published else None,
                seen_at.isoformat(),
                seen_at.astimezone(UTC).date().isoformat(),
                s.negative,
                s.neutral,
                s.positive,
            )
            for h, s in scored
        ]
        cutoff = (seen_at - timedelta(days=RETENTION_DAYS)).date().isoformat()
        with self._connect() as db:
            db.executemany(
                "INSERT OR IGNORE INTO headlines VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
            )
            db.execute("DELETE FROM headlines WHERE day < ?", (cutoff,))

    def model_trend(self, days: int, until: date | None = None) -> list[DailyPoint]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT day, region, AVG(positive - negative), COUNT(*) FROM headlines "
                "WHERE day BETWEEN ? AND ? GROUP BY day, region ORDER BY day, region",
                _window(days, until),
            ).fetchall()
        return [DailyPoint(date.fromisoformat(d), r, v, n) for d, r, v, n in rows]

    def gdelt_fetched_at(self, region: str) -> datetime | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT fetched_at FROM gdelt_fetch WHERE region = ?", (region,)
            ).fetchone()
        return datetime.fromisoformat(row[0]) if row else None

    def save_gdelt(
        self, region: str, tone_by_day: Mapping[date, float], fetched_at: datetime
    ) -> None:
        with self._connect() as db:
            db.executemany(
                "INSERT OR REPLACE INTO gdelt_tone VALUES (?,?,?)",
                [(region, day.isoformat(), tone) for day, tone in tone_by_day.items()],
            )
            db.execute(
                "INSERT OR REPLACE INTO gdelt_fetch VALUES (?,?)",
                (region, fetched_at.isoformat()),
            )

    def gdelt_trend(self, days: int, until: date | None = None) -> list[DailyPoint]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT day, region, tone FROM gdelt_tone WHERE day BETWEEN ? AND ? "
                "ORDER BY day, region",
                _window(days, until),
            ).fetchall()
        return [DailyPoint(date.fromisoformat(d), r, v) for d, r, v in rows]


def _window(days: int, until: date | None) -> tuple[str, str]:
    end = until or datetime.now(UTC).date()
    return (end - timedelta(days=days - 1)).isoformat(), end.isoformat()
