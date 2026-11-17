from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

from newsent.regions import ALL_FEEDS, REGIONS, Country, Feed, Region
from newsent.store import SourceDay

NON_COUNTRY_ORIGINS = frozenset({"Pan-African"})


@dataclass(frozen=True, slots=True)
class CountryOutlets:
    country: Country
    region: Region
    feeds: tuple[Feed, ...]


@dataclass(frozen=True, slots=True)
class IndexDay:
    day: date
    value: float
    headlines: int


COUNTRIES: dict[str, CountryOutlets] = {
    country.iso3: CountryOutlets(
        country,
        region,
        tuple(feed for _, feed in ALL_FEEDS if feed.country == country.name),
    )
    for region in REGIONS
    for country in region.source_countries
}


def daily_index(
    points: Iterable[SourceDay], sources: Collection[str]
) -> list[IndexDay]:
    net: dict[date, float] = defaultdict(float)
    count: dict[date, int] = defaultdict(int)
    for point in points:
        if point.source in sources:
            net[point.day] += point.value * point.headlines
            count[point.day] += point.headlines
    return [IndexDay(day, net[day] / count[day], count[day]) for day in sorted(count)]
