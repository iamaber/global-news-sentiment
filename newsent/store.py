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
COLUMNS = (
    "id",
    "title",
    "link",
    "source",
    "region",
    "published",
    "first_seen",
    "day",
    "negative",
    "neutral",
    "positive",
)

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
"""


@dataclass(frozen=True, slots=True)
class DailyPoint:
    day: date
    region: str
    value: float
    headlines: int = 0


@dataclass(frozen=True, slots=True)
class SourceDay:
    day: date
    source: str
    value: float
    headlines: int


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
            {
                "id": h.id,
                "title": h.title,
                "link": h.link,
                "source": h.source,
                "region": h.region,
                "published": h.published.isoformat() if h.published else None,
                "first_seen": seen_at.isoformat(),
                "day": seen_at.astimezone(UTC).date().isoformat(),
                "negative": s.negative,
                "neutral": s.neutral,
                "positive": s.positive,
            }
            for h, s in scored
        ]
        with self._connect() as db:
            _insert(db, rows)
            db.execute(
                "DELETE FROM headlines WHERE day < ?",
                (retention_cutoff(seen_at).isoformat(),),
            )

    def import_rows(self, rows: Iterable[Mapping]) -> None:
        with self._connect() as db:
            _insert(db, rows)

    def rows_seen_at(self, seen_at: datetime) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                f"SELECT {', '.join(COLUMNS)} FROM headlines WHERE first_seen = ? "
                "ORDER BY rowid",
                (seen_at.isoformat(),),
            ).fetchall()
        return [dict(zip(COLUMNS, row, strict=True)) for row in rows]

    def model_trend(self, days: int, until: date | None = None) -> list[DailyPoint]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT day, region, AVG(positive - negative), COUNT(*) FROM headlines "
                "WHERE day BETWEEN ? AND ? GROUP BY day, region ORDER BY day, region",
                [day.isoformat() for day in window(days, until)],
            ).fetchall()
        return [DailyPoint(date.fromisoformat(d), r, v, n) for d, r, v, n in rows]

    def source_trend(self, days: int, until: date | None = None) -> list[SourceDay]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT day, source, AVG(positive - negative), COUNT(*) FROM headlines "
                "WHERE day BETWEEN ? AND ? GROUP BY day, source ORDER BY day, source",
                [day.isoformat() for day in window(days, until)],
            ).fetchall()
        return [SourceDay(date.fromisoformat(d), s, v, n) for d, s, v, n in rows]


def window(days: int, until: date | None = None) -> tuple[date, date]:
    end = until or datetime.now(UTC).date()
    return end - timedelta(days=days - 1), end


def retention_cutoff(now: datetime) -> date:
    return (now - timedelta(days=RETENTION_DAYS)).astimezone(UTC).date()


def _insert(db: sqlite3.Connection, rows: Iterable[Mapping]) -> None:
    db.executemany(
        f"INSERT OR IGNORE INTO headlines ({', '.join(COLUMNS)}) "
        f"VALUES ({', '.join('?' * len(COLUMNS))})",
        ([row[column] for column in COLUMNS] for row in rows),
    )
