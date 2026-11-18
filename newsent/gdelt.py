"""Daily GDELT tone per region, from GDELT's daily event files.

Each event row carries the mean tone of the articles that reported it, GDELT's
own lexicon score (roughly -10..+10, usually -5..+2), not our model's output.
A region's tone for a day is the article-weighted mean over the events whose
main actor (Actor1) is from one of the region's countries.
"""

import io
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import date
from typing import BinaryIO

from newsent.feeds import USER_AGENT
from newsent.history import https_opener
from newsent.regions import REGIONS
from newsent.store import DailyPoint

EVENTS_URL = "https://data.gdeltproject.org/events/{day:%Y%m%d}.export.CSV.zip"
MAX_ZIP_BYTES = 50_000_000
CHUNK_BYTES = 1 << 16
TIMEOUT_SECONDS = 60
ACTOR1_COUNTRY = 7
NUM_ARTICLES = 33
AVG_TONE = 34
REGION_BY_CAMEO = {
    country.iso3: region.key
    for region in REGIONS
    for country in region.source_countries
}


class DayNotPublished(LookupError):
    pass


def fetch_day(day: date) -> list[DailyPoint]:
    with tempfile.TemporaryFile() as file:
        _download(EVENTS_URL.format(day=day), file)
        file.seek(0)
        return read_events(day, file)


def _download(url: str, file: BinaryIO) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = https_opener.open(request, timeout=TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DayNotPublished(url) from exc
        raise
    with response:
        size = 0
        while chunk := response.read(CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_ZIP_BYTES:
                raise ValueError(f"{url} is larger than {MAX_ZIP_BYTES} bytes")
            file.write(chunk)


def read_events(day: date, file: BinaryIO) -> list[DailyPoint]:
    weighted: dict[str, float] = {}
    articles: dict[str, int] = {}
    with zipfile.ZipFile(file) as archive:
        (name,) = archive.namelist()
        with archive.open(name) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
                fields = line.split("\t")
                if len(fields) <= AVG_TONE:
                    continue
                region = REGION_BY_CAMEO.get(fields[ACTOR1_COUNTRY])
                if region is None:
                    continue
                try:
                    count = int(fields[NUM_ARTICLES])
                    tone = float(fields[AVG_TONE])
                except ValueError:
                    continue
                if count <= 0:
                    continue
                weighted[region] = weighted.get(region, 0.0) + count * tone
                articles[region] = articles.get(region, 0) + count
    return [
        DailyPoint(day, key, weighted[key] / articles[key], articles[key])
        for key in sorted(articles)
    ]
