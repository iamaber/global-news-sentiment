import json
from datetime import UTC, date, datetime, timedelta

from newsent import history
from newsent.collect import collect
from newsent.feeds import FeedStatus, Headline, headline_id
from newsent.scores import Scores
from newsent.store import COLUMNS, RETENTION_DAYS, DailyPoint, Store

POSITIVE = Scores(negative=0.1, neutral=0.2, positive=0.7)
NEGATIVE = Scores(negative=0.6, neutral=0.3, positive=0.1)
NEUTRAL = Scores(negative=0.2, neutral=0.6, positive=0.2)
STATUSES = [FeedStatus("NPR", "americas", "https://feeds.npr.org/", 1, 0.1, None)]


def headline(title, region="americas"):
    return Headline(headline_id(title), title, None, "NPR", region, None)


class FakeModel:
    def __init__(self, by_title):
        self.by_title = by_title
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return [self.by_title[text] for text in texts]


def day_rows(directory):
    return [
        json.loads(line)
        for path in sorted((directory / "days").glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def test_collect_scores_and_records_only_headlines_new_since_the_last_run(tmp_path):
    model = FakeModel({"A": POSITIVE, "B": NEGATIVE, "C": NEUTRAL})
    first = [headline("A"), headline("B", "europe")]
    second = [*first, headline("C", "europe")]

    collect(tmp_path, score=model, fetch=lambda: (first, STATUSES))
    snapshot = collect(tmp_path, score=model, fetch=lambda: (second, STATUSES))

    assert model.calls == [["A", "B"], ["C"]]
    assert snapshot.newly_scored == 1
    rows = day_rows(tmp_path)
    assert [row["title"] for row in rows] == ["A", "B", "C"]
    assert all(tuple(row) == COLUMNS for row in rows)
    today = datetime.now(UTC).date()
    assert history.parse_trend((tmp_path / "trend.csv").read_text()) == [
        DailyPoint(today, "americas", 0.6, 1),
        DailyPoint(today, "europe", -0.25, 2),
    ]


def test_collect_deletes_day_files_past_retention(tmp_path):
    today = datetime.now(UTC).date()
    days_dir = tmp_path / "days"
    days_dir.mkdir()
    expired = today - timedelta(days=RETENTION_DAYS + 1)
    kept = today - timedelta(days=RETENTION_DAYS - 1)
    for day, title in ((expired, "Old"), (kept, "Kept")):
        row = {
            "id": headline_id(title),
            "title": title,
            "link": None,
            "source": "NPR",
            "region": "americas",
            "published": None,
            "first_seen": f"{day.isoformat()}T12:00:00+00:00",
            "day": day.isoformat(),
            "negative": 0.1,
            "neutral": 0.2,
            "positive": 0.7,
        }
        (days_dir / f"{day.isoformat()}.jsonl").write_text(json.dumps(row) + "\n")

    collect(
        tmp_path,
        score=FakeModel({"New": NEGATIVE}),
        fetch=lambda: ([headline("New"), headline("Kept")], STATUSES),
    )

    assert sorted(path.stem for path in days_dir.glob("*.jsonl")) == [
        kept.isoformat(),
        today.isoformat(),
    ]
    assert [row["title"] for row in day_rows(tmp_path)] == ["Kept", "New"]


def test_model_trend_uses_collected_points_inside_the_window(isolated_db, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_SOURCE", history.DEFAULT_SOURCE)
    until = date(2026, 11, 17)
    collected = [
        DailyPoint(until - timedelta(days=offset), "europe", 0.1, 3)
        for offset in (-1, 0, 6, 7)
    ]
    sources = []

    points, origin = history.model_trend(
        Store(isolated_db),
        7,
        until=until,
        load=lambda source: sources.append(source) or collected,
    )

    assert sources == [history.DEFAULT_SOURCE]
    assert points == collected[1:3]
    assert origin == "collected hourly by GitHub Actions"


def test_model_trend_says_why_it_falls_back_to_this_instance(isolated_db, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_SOURCE", "https://example.test/trend.csv")
    store = Store(isolated_db)
    noon = datetime(2026, 11, 17, 12, tzinfo=UTC)
    store.save([(headline("A"), POSITIVE)], noon)
    local = store.model_trend(7, until=noon.date())

    def unreachable(source):
        raise OSError("network is unreachable")

    assert history.model_trend(store, 7, until=noon.date(), load=unreachable) == (
        local,
        "collected history unavailable: network is unreachable; "
        "showing this instance's recordings",
    )
    stale = [DailyPoint(date(2026, 1, 1), "europe", 0.1, 3)]
    assert history.model_trend(
        store, 7, until=noon.date(), load=lambda source: stale
    ) == (
        local,
        "collected history unavailable: no collected days in the last 7; "
        "showing this instance's recordings",
    )


def test_load_trend_refuses_plain_http_before_connecting(isolated_db, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_SOURCE", "http://example.test/trend.csv")

    points, origin = history.model_trend(Store(isolated_db), 7)

    assert points == []
    assert "history URL must use https" in origin


def test_model_trend_without_a_source_is_this_instance_only(isolated_db):
    def must_not_load(source):
        raise AssertionError("loader called with history disabled")

    assert history.model_trend(Store(isolated_db), 7, load=must_not_load) == (
        [],
        "recorded by this instance",
    )


def test_cached_loader_remembers_failures_until_the_period_ends(monkeypatch):
    calls = []

    def load(source):
        calls.append(source)
        raise TimeoutError("host hangs")

    clock = [1000.0]
    monkeypatch.setattr(history.time, "monotonic", lambda: clock[0])
    cached = history.CachedLoader(load, seconds=60)

    for _ in range(3):
        try:
            cached("https://example.org/trend.csv")
        except TimeoutError:
            pass
    clock[0] += 61
    try:
        cached("https://example.org/trend.csv")
    except TimeoutError:
        pass

    assert len(calls) == 2
