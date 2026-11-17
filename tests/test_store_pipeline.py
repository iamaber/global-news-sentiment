import http.client
import io
import json
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta

import pytest

from newsent import gdelt
from newsent.feeds import Headline, headline_id
from newsent.pipeline import Scored, summarize, take_snapshot
from newsent.regions import REGIONS, REGIONS_BY_KEY
from newsent.scores import Scores
from newsent.store import RETENTION_DAYS, Store

POSITIVE = Scores(negative=0.1, neutral=0.2, positive=0.7)
NEGATIVE = Scores(negative=0.6, neutral=0.3, positive=0.1)
NEUTRAL = Scores(negative=0.2, neutral=0.6, positive=0.2)


def headline(title, region="americas", published=None):
    return Headline(headline_id(title), title, None, "NPR", region, published)


class FakeModel:
    def __init__(self, by_title):
        self.by_title = by_title
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return [self.by_title[text] for text in texts]


def test_take_snapshot_scores_only_unseen_headlines_and_persists_them(isolated_db):
    store = Store(isolated_db)
    model = FakeModel({"A": POSITIVE, "B": NEGATIVE, "C": NEUTRAL})
    first = [headline("A"), headline("B", "europe")]
    second = [headline("A"), headline("B", "europe"), headline("C", "mea")]

    take_snapshot(store, fetch=lambda: (first, []), score=model)
    snapshot = take_snapshot(store, fetch=lambda: (second, []), score=model)

    assert model.calls == [["A", "B"], ["C"]]
    assert snapshot.newly_scored == 1
    assert [(i.headline.title, i.scores) for i in snapshot.items] == [
        ("A", POSITIVE),
        ("B", NEGATIVE),
        ("C", NEUTRAL),
    ]
    reopened = Store(isolated_db)
    assert reopened.known_scores([h.id for h in second]) == {
        h.id: s for h, s in zip(second, [POSITIVE, NEGATIVE, NEUTRAL])
    }


def test_take_snapshot_rejects_incomplete_scores(isolated_db):
    with pytest.raises(RuntimeError):
        take_snapshot(
            Store(isolated_db),
            fetch=lambda: ([headline("A"), headline("B")], []),
            score=lambda texts: [POSITIVE],
        )


def test_model_trend_is_daily_mean_net_and_count_by_first_seen_day(isolated_db):
    store = Store(isolated_db)
    today = date(2026, 11, 17)
    noon = datetime(2026, 11, 17, 12, tzinfo=UTC)
    yesterday = noon - timedelta(days=1)
    seen_yesterday = headline("D")
    store.save([(seen_yesterday, NEGATIVE)], yesterday)
    store.save(
        [
            (headline("A", published=yesterday), POSITIVE),
            (headline("B"), NEGATIVE),
            (headline("C", "europe"), NEUTRAL),
            (seen_yesterday, NEGATIVE),
        ],
        noon,
    )

    points = store.model_trend(30, until=today)

    assert [(p.day, p.region, p.headlines) for p in points] == [
        (date(2026, 11, 16), "americas", 1),
        (today, "americas", 2),
        (today, "europe", 1),
    ]
    assert [p.value for p in points] == pytest.approx([-0.5, 0.05, 0.0])
    assert [p.day for p in store.model_trend(1, until=today)] == [today, today]
    yesterday_only = store.model_trend(7, until=today - timedelta(days=1))
    assert [(p.day, p.headlines) for p in yesterday_only] == [(date(2026, 11, 16), 1)]


def test_rows_older_than_retention_are_pruned_on_save(isolated_db):
    store = Store(isolated_db)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    old = headline("Old")
    store.save([(old, POSITIVE)], start)

    later = start + timedelta(days=RETENTION_DAYS + 1)
    new = headline("New")
    store.save([(new, NEGATIVE)], later)

    assert store.known_scores([old.id, new.id]) == {new.id: NEGATIVE}


def test_summarize_reports_every_region_with_shares():
    items = [
        Scored(headline("A"), POSITIVE),
        Scored(headline("B"), POSITIVE),
        Scored(headline("C"), NEGATIVE),
        Scored(headline("D", "europe"), NEUTRAL),
    ]

    summaries = {s.region: s for s in summarize(items)}

    assert set(summaries) == set(REGIONS_BY_KEY)
    americas = summaries["americas"]
    assert americas.headlines == 3
    assert americas.net == pytest.approx((0.6 + 0.6 - 0.5) / 3)
    assert americas.shares == pytest.approx(
        {"negative": 1 / 3, "neutral": 0.0, "positive": 2 / 3}
    )
    assert sum(summaries["europe"].shares.values()) == pytest.approx(1.0)
    empty = summaries["asia_pacific"]
    assert (empty.headlines, empty.net) == (0, 0.0)
    assert set(empty.shares.values()) == {0.0}


def test_parse_timeline_reads_daily_tone():
    payload = json.dumps(
        {
            "timeline": [
                {
                    "series": "Average Tone",
                    "data": [
                        {"date": "20261115T000000Z", "value": -1.25},
                        {"date": "20261116T000000Z", "value": 0.5},
                    ],
                }
            ]
        }
    )

    assert gdelt.parse_timeline(payload) == {
        date(2026, 11, 15): -1.25,
        date(2026, 11, 16): 0.5,
    }


@pytest.mark.parametrize("payload", ["{}", '{"timeline": [{"data": []}]}'])
def test_parse_timeline_raises_when_gdelt_has_no_data(payload):
    with pytest.raises(gdelt.GdeltError, match="no data"):
        gdelt.parse_timeline(payload)


def test_parse_timeline_raises_on_rate_limit_body():
    with pytest.raises(gdelt.GdeltError, match="Please limit"):
        gdelt.parse_timeline("Please limit requests to one every 5 seconds.")


def http_429(request, timeout):
    raise urllib.error.HTTPError(
        request.full_url, 429, "Too Many Requests", http.client.HTTPMessage(), None
    )


@pytest.mark.parametrize(
    "urlopen",
    [
        lambda request, timeout: io.BytesIO(
            b"Please limit requests to one every 5 seconds."
        ),
        http_429,
    ],
    ids=["throttle-body", "http-429"],
)
def test_fetch_region_tone_flags_rate_limit_and_backs_off(monkeypatch, urlopen):
    monkeypatch.setattr(gdelt, "MIN_INTERVAL_SECONDS", 0)
    calls = []
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda request, timeout: calls.append(1) or urlopen(request, timeout),
    )

    for _ in range(2):
        with pytest.raises(gdelt.GdeltRateLimited):
            gdelt.fetch_region_tone(REGIONS[0])

    assert len(calls) == 1


def test_refresh_fetches_only_stale_regions_and_keeps_going_on_errors(isolated_db):
    store = Store(isolated_db)
    now = datetime.now(UTC)
    americas, europe, asia, mea = REGIONS
    store.save_gdelt(americas.key, {now.date(): 9.0}, now)
    store.save_gdelt(europe.key, {}, now - timedelta(hours=7))
    fetched = []

    def fetch(region):
        fetched.append(region.key)
        if region is asia:
            raise gdelt.GdeltError("GDELT returned no data")
        return {now.date(): 1.5}

    errors = gdelt.refresh(store, REGIONS, fetch=fetch)

    assert fetched == [europe.key, asia.key, mea.key]
    assert errors == {asia.key: "GDELT returned no data"}
    assert [(p.region, p.value) for p in store.gdelt_trend(1)] == [
        (americas.key, 9.0),
        (europe.key, 1.5),
        (mea.key, 1.5),
    ]
    assert gdelt.stale_regions(store, REGIONS, now) == [asia]
