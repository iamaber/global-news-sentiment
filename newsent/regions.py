from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Feed:
    name: str
    url: str
    country: str


@dataclass(frozen=True, slots=True)
class Country:
    name: str
    iso3: str


@dataclass(frozen=True, slots=True)
class Region:
    key: str
    name: str
    feeds: tuple[Feed, ...]
    source_countries: tuple[Country, ...]


REGIONS: tuple[Region, ...] = (
    Region(
        key="americas",
        name="Americas",
        feeds=(
            Feed("NPR", "https://feeds.npr.org/1001/rss.xml", "United States"),
            Feed(
                "New York Times",
                "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
                "United States",
            ),
            Feed(
                "CNBC",
                "https://www.cnbc.com/id/100003114/device/rss/rss.html",
                "United States",
            ),
            Feed("CBC News", "https://www.cbc.ca/webfeed/rss/rss-world", "Canada"),
            Feed("Buenos Aires Times", "https://www.batimes.com.ar/feed", "Argentina"),
        ),
        source_countries=(
            Country("United States", "USA"),
            Country("Canada", "CAN"),
            Country("Mexico", "MEX"),
            Country("Brazil", "BRA"),
            Country("Argentina", "ARG"),
            Country("Colombia", "COL"),
            Country("Chile", "CHL"),
            Country("Peru", "PER"),
        ),
    ),
    Region(
        key="europe",
        name="Europe",
        feeds=(
            Feed(
                "BBC News",
                "https://feeds.bbci.co.uk/news/world/rss.xml",
                "United Kingdom",
            ),
            Feed(
                "The Guardian",
                "https://www.theguardian.com/world/rss",
                "United Kingdom",
            ),
            Feed("Deutsche Welle", "https://rss.dw.com/rdf/rss-en-all", "Germany"),
            Feed("France 24", "https://www.france24.com/en/rss", "France"),
            Feed("RTÉ News", "https://www.rte.ie/feeds/rss/?index=/news/", "Ireland"),
        ),
        source_countries=(
            Country("United Kingdom", "GBR"),
            Country("Germany", "DEU"),
            Country("France", "FRA"),
            Country("Ireland", "IRL"),
            Country("Italy", "ITA"),
            Country("Spain", "ESP"),
            Country("Netherlands", "NLD"),
            Country("Poland", "POL"),
        ),
    ),
    Region(
        key="asia_pacific",
        name="Asia-Pacific",
        feeds=(
            Feed(
                "South China Morning Post",
                "https://www.scmp.com/rss/91/feed/",
                "Hong Kong",
            ),
            Feed(
                "Times of India",
                "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
                "India",
            ),
            Feed(
                "CNA", "https://www.channelnewsasia.com/rssfeeds/8395986", "Singapore"
            ),
            Feed("The Japan Times", "https://www.japantimes.co.jp/feed/", "Japan"),
            Feed(
                "ABC News Australia",
                "https://www.abc.net.au/news/feed/2942460/rss.xml",
                "Australia",
            ),
        ),
        source_countries=(
            Country("India", "IND"),
            Country("China", "CHN"),
            Country("Hong Kong", "HKG"),
            Country("Japan", "JPN"),
            Country("South Korea", "KOR"),
            Country("Singapore", "SGP"),
            Country("Australia", "AUS"),
            Country("Indonesia", "IDN"),
            Country("Philippines", "PHL"),
            Country("Pakistan", "PAK"),
        ),
    ),
    Region(
        key="mea",
        name="Middle East & Africa",
        feeds=(
            Feed("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml", "Qatar"),
            Feed(
                "The Times of Israel", "https://www.timesofisrael.com/feed/", "Israel"
            ),
            Feed(
                "AllAfrica",
                "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
                "Pan-African",
            ),
            Feed(
                "Daily Maverick",
                "https://www.dailymaverick.co.za/dmrss/",
                "South Africa",
            ),
            Feed("Nation", "https://nation.africa/kenya/rss.xml", "Kenya"),
        ),
        source_countries=(
            Country("Qatar", "QAT"),
            Country("Israel", "ISR"),
            Country("United Arab Emirates", "ARE"),
            Country("Saudi Arabia", "SAU"),
            Country("Turkey", "TUR"),
            Country("Egypt", "EGY"),
            Country("Nigeria", "NGA"),
            Country("South Africa", "ZAF"),
            Country("Kenya", "KEN"),
        ),
    ),
)

REGIONS_BY_KEY = {region.key: region for region in REGIONS}
ALL_FEEDS: tuple[tuple[Region, Feed], ...] = tuple(
    (region, feed) for region in REGIONS for feed in region.feeds
)
