import http.client
import io
import urllib.error
import zipfile
from datetime import date

import pytest

from newsent import gdelt
from newsent.feeds import USER_AGENT
from newsent.store import DailyPoint

DAY = date(2026, 11, 16)


def event(actor1="USA", articles="10", tone="-2.5"):
    fields = [""] * 58
    fields[gdelt.ACTOR1_COUNTRY] = actor1
    fields[gdelt.NUM_ARTICLES] = articles
    fields[gdelt.AVG_TONE] = tone
    return "\t".join(fields)


def events_zip(*lines):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("20261116.export.CSV", "\n".join(lines) + "\n")
    return buffer.getvalue()


def test_read_events_weights_tone_by_articles_per_region():
    data = events_zip(
        event("USA", "10", "-2.0"),
        event("CAN", "30", "2.0"),
        event("GBR", "5", "-3.5"),
        event("XYZ", "100", "9.0"),
        event("", "100", "9.0"),
        event("GBR", "7", "not-a-number"),
        event("GBR", "", "1.0"),
        "USA\t10\t-2.0",
    )

    points = gdelt.read_events(DAY, io.BytesIO(data))

    assert points == [
        DailyPoint(DAY, "americas", 1.0, 40),
        DailyPoint(DAY, "europe", -3.5, 5),
    ]


class FakeOpener:
    def __init__(self, respond):
        self.respond = respond
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        return self.respond(request)


def test_fetch_day_downloads_the_days_event_file_over_https(monkeypatch):
    opener = FakeOpener(lambda request: io.BytesIO(events_zip(event("HKG"))))
    monkeypatch.setattr(gdelt, "https_opener", opener)

    points = gdelt.fetch_day(DAY)

    assert points == [DailyPoint(DAY, "asia_pacific", -2.5, 10)]
    (request,) = opener.requests
    assert request.full_url == (
        "https://data.gdeltproject.org/events/20261116.export.CSV.zip"
    )
    assert request.get_header("User-agent") == USER_AGENT


def test_fetch_day_reports_an_unpublished_day(monkeypatch):
    def not_found(request):
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", http.client.HTTPMessage(), None
        )

    monkeypatch.setattr(gdelt, "https_opener", FakeOpener(not_found))

    with pytest.raises(gdelt.DayNotPublished):
        gdelt.fetch_day(DAY)


def test_fetch_day_refuses_a_file_over_the_size_cap(monkeypatch):
    monkeypatch.setattr(gdelt, "MAX_ZIP_BYTES", 100)
    monkeypatch.setattr(
        gdelt, "https_opener", FakeOpener(lambda request: io.BytesIO(b"x" * 101))
    )

    with pytest.raises(ValueError, match="larger than 100 bytes"):
        gdelt.fetch_day(DAY)
