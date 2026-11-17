from datetime import date, timedelta

from newsent.alerts import Alert, detect
from newsent.store import DailyPoint

YESTERDAY = date(2026, 11, 16)


def days(region, values):
    return [
        DailyPoint(YESTERDAY - timedelta(days=offset), region, value)
        for offset, value in enumerate(values)
    ]


def test_flags_regions_beyond_two_deviations_strongest_first():
    history = [
        *days("americas", [-1, 1, -1, 1, 0]),
        *days("europe", [9, 11, 9, 11, 10]),
        *days("asia_pacific", [9, 11, 9, 11, 10]),
    ]
    today = {"americas": -3.0, "europe": 14.0, "asia_pacific": 11.5}

    assert detect(today, history) == [
        Alert("europe", today=14.0, mean=10.0, std=1.0, z=4.0),
        Alert("americas", today=-3.0, mean=0.0, std=1.0, z=-3.0),
    ]


def test_threshold_sets_how_far_today_must_move():
    history = days("europe", [9, 11, 9, 11, 10])

    assert detect({"europe": 11.5}, history, threshold=1.0) == [
        Alert("europe", today=11.5, mean=10.0, std=1.0, z=1.5)
    ]
    assert detect({"europe": 11.5}, history, threshold=2.0) == []


def test_regions_without_enough_days_or_spread_are_not_judged():
    history = [
        *days("europe", [9, 11, 9, 11]),
        *days("mea", [5, 5, 5, 5, 5, 5, 5]),
    ]
    today = {"europe": 100.0, "mea": 100.0, "americas": 100.0}

    assert detect(today, history) == []
    assert [alert.region for alert in detect(today, history, min_days=4)] == ["europe"]
