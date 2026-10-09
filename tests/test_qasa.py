import pytest

from bostad.sources import qasa
from tests.fakes import FakeHttp

URL = "https://api.qasa.se/graphql"


def _node(home_id, **overrides):
    node = {
        "id": home_id, "rent": 9900, "tenantBaseFee": 0, "roomCount": 3.0, "squareMeters": 70,
        "firstHand": True, "shared": False, "startDate": "2026-11-01T00:00:00+00:00", "endDate": None,
        "location": {"locality": "Varberg ", "route": "Magasinsgatan", "streetNumber": "4"},
    }
    node.update(overrides)
    return node


def _pages(*pages):
    def respond(payload):
        index = payload["variables"]["offset"] // 100
        nodes, has_next = pages[index]
        return {"data": {"homeIndexSearch": {"documents": {"hasNextPage": has_next, "nodes": nodes}}}}
    return respond


def test_qasa_maps_fields_and_pages():
    http = FakeHttp({URL: _pages(
        ([_node("1", endDate="2027-05-31T00:00:00+00:00", firstHand=False)], True),
        ([_node("2"), _node("3", shared=True)], False),
    )})

    listings = qasa.fetch(http)

    assert [l.id for l in listings] == ["1", "2"]
    first, second = listings
    assert first.end_date == "2027-05-31"
    assert first.first_hand is False
    assert second.key == "qasa:2"
    assert second.url == "https://qasa.se/sv/home/2"
    assert second.address == "Magasinsgatan 4"
    assert second.area == "Varberg"
    assert second.rooms == 3.0
    assert second.size_sqm == 70.0
    assert second.available_from == "2026-11-01"
    assert second.end_date is None
    assert second.first_hand is True


def test_qasa_rent_includes_fee():
    http = FakeHttp({URL: _pages(([_node("1", rent=10800, tenantBaseFee=589)], False))})
    assert qasa.fetch(http)[0].rent == 11389


def test_qasa_graphql_error_raises():
    http = FakeHttp({URL: lambda payload: {"errors": [{"message": "boom"}]}})
    with pytest.raises(RuntimeError, match="boom"):
        qasa.fetch(http)
