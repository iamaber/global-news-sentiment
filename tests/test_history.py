import json
from datetime import UTC, date, datetime, timedelta

import pytest

from newsent import gdelt, history
from newsent.collect import collect, collect_gdelt
from newsent.feeds import FeedStatus, Headline, headline_id
from newsent.scores import Scores
from newsent.store import COLUMNS, RETENTION_DAYS, DailyPoint, SourceDay, Store

POSITIVE = Scores(negative=0.1, neutral=0.2, positive=0.7)
NEGATIVE = Scores(negative=0.6, neutral=0.3, positive=0.1)
NEUTRAL = Scores(negative=0.2, neutral=0.6, positive=0.2)
STATUSES = [FeedStatus("NPR", "americas", "https://feeds.npr.org/", 1, 0.1, None)]


def headline(title, region="americas", source="NPR"):
    return Headline(headline_id(title), title, None, source, region, None)


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
    first = [headline("A"), headline("B", "europe", "BBC News")]
    second = [*first, headline("C", "europe", "BBC News")]

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
    assert history.parse_sources((tmp_path / "sources.csv").read_text()) == [
        SourceDay(today, "BBC News", -0.25, 2),
        SourceDay(today, "NPR", 0.6, 1),
    ]


def test_source_trend_reads_the_collectors_sources_csv_next_to_trend_csv(
    tmp_path, isolated_db, monkeypatch
):
    collected = tmp_path / "history"
    fetch = [headline("A"), headline("B", "europe", "BBC News")]
    collect(
        collected,
        score=FakeModel({"A": POSITIVE, "B": NEGATIVE}),
        fetch=lambda: (fetch, STATUSES),
    )
    monkeypatch.setattr(history, "HISTORY_SOURCE", str(collected / "trend.csv"))

    points, origin = history.source_trend(Store(isolated_db), 7)

    today = datetime.now(UTC).date()
    assert points == [
        SourceDay(today, "BBC News", -0.5, 1),
        SourceDay(today, "NPR", 0.6, 1),
    ]
    assert origin == f"collected history from {collected / 'sources.csv'}"


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


def test_source_trend_uses_collected_points_inside_the_window(isolated_db, monkeypatch):
    monkeypatch.setattr(history, "HISTORY_SOURCE", history.DEFAULT_SOURCE)
    until = date(2026, 11, 17)
    collected = [
        SourceDay(until - timedelta(days=offset), "NPR", 0.1, 3)
        for offset in (-1, 0, 6, 7)
    ]
    sources = []

    points, origin = history.source_trend(
        Store(isolated_db),
        7,
        until=until,
        load=lambda source: sources.append(source) or collected,
    )

    assert sources == [
        "https://raw.githubusercontent.com/iamaber/global-news-sentiment/history/sources.csv"
    ]
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
    assert history.source_trend(store, 7, until=noon.date(), load=unreachable) == (
        store.source_trend(7, until=noon.date()),
        "collected history unavailable: network is unreachable; "
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
    cached = history.ResultOrErrorCache(load, seconds=60)

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


TODAY = date(2026, 11, 18)


def europe_tone(day):
    return [DailyPoint(day, "europe", -2.0, 100)]


def days_ago(*offsets):
    return [TODAY - timedelta(days=n) for n in offsets]


def test_collect_gdelt_fills_missing_days_newest_first_up_to_the_cap(tmp_path):
    collected = DailyPoint(TODAY - timedelta(days=1), "mea", -0.5, 9)
    expired = DailyPoint(TODAY - timedelta(days=91), "mea", 1.0, 9)
    (tmp_path / "gdelt.csv").write_text(history.format_gdelt([expired, collected]))
    (tmp_path / "gdelt-countries.csv").write_text(
        history.format_gdelt_countries(gdelt.REGION_BY_CAMEO)
    )
    requested = []

    added = collect_gdelt(
        tmp_path, TODAY, lambda day: requested.append(day) or europe_tone(day)
    )

    assert requested == added == days_ago(*range(2, 17))
    assert history.parse_gdelt((tmp_path / "gdelt.csv").read_text()) == [
        *(DailyPoint(day, "europe", -2.0, 100) for day in days_ago(*range(16, 1, -1))),
        collected,
    ]


@pytest.mark.parametrize(
    "recorded", [None, "code,region\nUSA,europe\n"], ids=["missing", "different"]
)
def test_collect_gdelt_rebuilds_tone_counted_under_another_country_mapping(
    tmp_path, capsys, recorded
):
    collect_gdelt(tmp_path, TODAY, europe_tone)
    countries = tmp_path / "gdelt-countries.csv"
    current = countries.read_text()
    if recorded is None:
        countries.unlink()
    else:
        countries.write_text(recorded)
    requested = []

    def mea_tone(day):
        requested.append(day)
        return [DailyPoint(day, "mea", 1.5, 20)]

    added = collect_gdelt(tmp_path, TODAY, mea_tone)

    assert requested == added == days_ago(*range(1, 16))
    assert history.parse_gdelt((tmp_path / "gdelt.csv").read_text()) == [
        DailyPoint(day, "mea", 1.5, 20) for day in days_ago(*range(15, 0, -1))
    ]
    assert countries.read_text() == current
    assert "gdelt-countries.csv" in capsys.readouterr().err


def test_collect_gdelt_backfills_90_days_then_fetches_one_day_per_day(tmp_path):
    requested = []

    def fetch(day):
        requested.append(day)
        return europe_tone(day)

    runs = 0
    while collect_gdelt(tmp_path, TODAY, fetch):
        runs += 1

    assert runs == 6
    assert sorted(requested) == days_ago(*range(90, 0, -1))
    requested.clear()
    assert collect_gdelt(tmp_path, TODAY + timedelta(days=1), fetch) == [TODAY]
    assert requested == [TODAY]


def test_collect_gdelt_skips_an_unpublished_day_and_retries_it_next_run(tmp_path):
    yesterday = TODAY - timedelta(days=1)

    def fetch(day):
        if day == yesterday:
            raise gdelt.DayNotPublished(day)
        return europe_tone(day)

    assert collect_gdelt(tmp_path, TODAY, fetch) == days_ago(*range(2, 16))
    assert collect_gdelt(tmp_path, TODAY, europe_tone)[0] == yesterday


def test_collect_gdelt_failure_keeps_earlier_tone_and_does_not_raise(tmp_path, capsys):
    collect(
        tmp_path,
        score=FakeModel({"A": POSITIVE}),
        fetch=lambda: ([headline("A")], STATUSES),
    )
    trend = (tmp_path / "trend.csv").read_text()
    (tmp_path / "gdelt.csv").write_text("not a gdelt file\n")

    def fetch(day):
        if day == TODAY - timedelta(days=2):
            raise RuntimeError("connection reset")
        return europe_tone(day)

    assert collect_gdelt(tmp_path, TODAY, fetch) == days_ago(1)
    assert history.parse_gdelt((tmp_path / "gdelt.csv").read_text()) == europe_tone(
        TODAY - timedelta(days=1)
    )
    assert (tmp_path / "trend.csv").read_text() == trend
    assert "connection reset" in capsys.readouterr().err


def test_gdelt_trend_reads_the_collectors_gdelt_csv_next_to_trend_csv(
    tmp_path, monkeypatch
):
    collect_gdelt(tmp_path, TODAY, europe_tone)
    monkeypatch.setattr(history, "HISTORY_SOURCE", str(tmp_path / "trend.csv"))

    points, origin = history.gdelt_trend(7, until=TODAY)

    assert points == [p for day in days_ago(6, 5, 4, 3, 2, 1) for p in europe_tone(day)]
    assert origin == f"collected history from {tmp_path / 'gdelt.csv'}"


def test_gdelt_trend_loads_from_github_and_explains_an_empty_chart(monkeypatch):
    monkeypatch.setattr(history, "HISTORY_SOURCE", history.DEFAULT_SOURCE)
    sources = []

    def unreachable(source):
        raise OSError("network is unreachable")

    points, origin = history.gdelt_trend(
        7, until=TODAY, load=lambda source: sources.append(source) or europe_tone(TODAY)
    )

    assert sources == [
        "https://raw.githubusercontent.com/iamaber/global-news-sentiment/history/gdelt.csv"
    ]
    assert (points, origin) == (
        europe_tone(TODAY),
        "collected hourly by GitHub Actions",
    )
    assert history.gdelt_trend(7, until=TODAY, load=unreachable) == (
        [],
        "collected GDELT history unavailable: network is unreachable",
    )
    monkeypatch.setattr(history, "HISTORY_SOURCE", "")
    assert history.gdelt_trend(7, until=TODAY, load=unreachable) == (
        [],
        "collected history is turned off (NEWS_HISTORY is empty)",
    )
