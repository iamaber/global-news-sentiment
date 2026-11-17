from datetime import UTC, date, datetime, timedelta

import pytest

from newsent import history
from newsent.countries import COUNTRIES, NON_COUNTRY_ORIGINS, IndexDay, daily_index
from newsent.feeds import Headline, headline_id
from newsent.regions import ALL_FEEDS, REGIONS
from newsent.scores import Scores
from newsent.store import SourceDay, Store

DAY = date(2026, 11, 17)


def rounded(days):
    return [IndexDay(d.day, round(d.value, 9), d.headlines) for d in days]


def test_every_feed_is_based_in_a_country_of_its_region_or_names_no_country():
    regions_by_country = {
        country.name: region.key
        for region in REGIONS
        for country in region.source_countries
    }
    unmatched = set()
    for region, feed in ALL_FEEDS:
        if feed.country in regions_by_country:
            assert regions_by_country[feed.country] == region.key, feed.name
        else:
            unmatched.add(feed.country)

    assert unmatched == NON_COUNTRY_ORIGINS


def test_countries_are_unique_by_iso3_and_name():
    countries = [c for region in REGIONS for c in region.source_countries]

    assert len({c.iso3 for c in countries}) == len(countries)
    assert len({c.name for c in countries}) == len(countries)
    assert len(COUNTRIES) == len(countries)


@pytest.mark.parametrize(
    ("iso3", "region", "sources"),
    [
        ("USA", "americas", {"NPR", "New York Times", "CNBC"}),
        ("HKG", "asia_pacific", {"South China Morning Post"}),
        ("MEX", "americas", set()),
    ],
)
def test_country_lists_the_outlets_based_there(iso3, region, sources):
    entry = COUNTRIES[iso3]

    assert entry.region.key == region
    assert {feed.name for feed in entry.feeds} == sources


def test_daily_index_is_the_mean_over_headlines_from_the_given_sources():
    points = [
        SourceDay(DAY, "NPR", 0.6, 1),
        SourceDay(DAY, "CNBC", -0.2, 3),
        SourceDay(DAY, "BBC News", 0.9, 5),
        SourceDay(DAY - timedelta(days=1), "CNBC", 0.4, 2),
    ]

    assert rounded(daily_index(points, {"NPR", "CNBC"})) == [
        IndexDay(DAY - timedelta(days=1), 0.4, 2),
        IndexDay(DAY, 0.0, 4),
    ]
    assert daily_index(points, set()) == []


def test_country_trend_from_this_instance_averages_its_outlets_headlines(isolated_db):
    store = Store(isolated_db)
    noon = datetime(2026, 11, 17, 12, tzinfo=UTC)

    def scored(title, source, net):
        headline = Headline(headline_id(title), title, None, source, "americas", None)
        positive = (1 + net) / 2
        return headline, Scores(negative=1 - positive, neutral=0.0, positive=positive)

    store.save(
        [
            scored("A", "NPR", 0.5),
            scored("B", "CNBC", -0.1),
            scored("C", "CNBC", 0.2),
            scored("D", "CBC News", -0.9),
        ],
        noon,
    )
    store.save([scored("E", "New York Times", 0.3)], noon - timedelta(days=1))

    points, origin = history.source_trend(store, 7, until=noon.date())

    assert origin == "recorded by this instance"
    usa = {feed.name for feed in COUNTRIES["USA"].feeds}
    assert rounded(daily_index(points, usa)) == [
        IndexDay(date(2026, 11, 16), 0.3, 1),
        IndexDay(date(2026, 11, 17), 0.2, 3),
    ]
