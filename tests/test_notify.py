from dataclasses import replace

from bostad.filters import Match
from bostad.model import Listing
from bostad.notify import format_alert, format_message, send
from tests.fakes import FakeHttp

LISTING = Listing(
    source="derome", id="5023-118-5", url="https://example/5023", address="Trönningebjärsvägen 37",
    area="Trönninge", city="Varberg", rooms=3.0, size_sqm=72.0, rent=10618,
    available_from="2027-01-01", apply_by="2026-10-20", first_hand=True, end_date=None,
)


def test_format_message_full():
    payload = format_message(Match(LISTING, unknown_area=False))
    assert payload["title"] == "3 rok, 72 m² – Trönninge"
    assert payload["message"] == (
        "Trönningebjärsvägen 37\n10 618 kr/mån · inflytt 2027-01-01 · sök senast 2026-10-20 · Derome"
    )
    assert payload["click"] == "https://example/5023"
    assert payload["tags"] == ["house"]


def test_format_message_missing_values_and_unknown_area():
    listing = replace(LISTING, rooms=None, size_sqm=None, rent=None, apply_by=None,
                      available_from=None, area="", city="Väröbacka", source="qasa")
    payload = format_message(Match(listing, unknown_area=True))
    assert payload["title"] == "⚠️ okänt område · ? rok, ? m² – Väröbacka"
    assert payload["message"] == "Trönningebjärsvägen 37\n? kr/mån · Qasa"


def test_format_message_half_rooms():
    payload = format_message(Match(replace(LISTING, rooms=3.5), unknown_area=False))
    assert payload["title"].startswith("3,5 rok")


def test_format_alert():
    payload = format_alert("qasa", "429 Too Many Requests")
    assert payload["title"] == "Bostadsbevakning: Qasa har slutat fungera"
    assert "429 Too Many Requests" in payload["message"]
    assert payload["priority"] == 4


def test_send_posts_topic_and_payload():
    received = []
    http = FakeHttp({"https://ntfy.sh": lambda p: received.append(p)})
    send(http, "https://ntfy.sh", "mitt-amne", {"title": "t", "message": "m"})
    assert received == [{"topic": "mitt-amne", "title": "t", "message": "m"}]
