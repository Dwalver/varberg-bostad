from bostad.sources import fortinova, varbergs_bostad
from tests.fakes import FakeHttp

VB = "https://varberg-fastighet.momentum.se/Prod/Varberg/PmApi/"
FN = "https://fortinova-fastighet.momentum.se/Prod/Fortinova/PmApi/"


def _detail(obj_id, area_path, city, rooms_text, price, rooms=None):
    size = {"roomsDisplayName": rooms_text, "area": 72.5}
    if rooms is not None:
        size["rooms"] = rooms
    return {
        "id": obj_id,
        "displayName": "Köpstadsvägen 58 ",
        "queueType": "residential",
        "pricing": {"price": price},
        "location": {
            "area": {"displayName": "Sörsedammen"},
            "areaPath": [{"displayName": p} for p in area_path],
            "address": {"address": "Köpstadsvägen 58", "postcode": "432 50", "city": city},
        },
        "availability": {"availableFrom": "/Date(1798758000000)/"},
        "application": {"openTo": "/Date(1791755940000)/"},
        "size": size,
    }


def test_varbergs_bostad_keeps_only_residential_and_reads_details():
    listing_page = {
        "count": 3,
        "items": [
            {"id": "A", "queueType": "residential", "location": {"areaPath": [{"displayName": "Sörse"}]}},
            {"id": "P", "queueType": "parking", "location": {"areaPath": [{"displayName": "Sörse"}]}},
            {"id": "S", "queueType": "sheltered", "location": {"areaPath": [{"displayName": "Bua"}]}},
        ],
    }
    http = FakeHttp({
        VB + "v2/market/objects?offset=0&limit=500": listing_page,
        VB + "v2/market/objects/A": _detail("A", ["Sörse"], "VARBERG", "3 rum och kök", 10618.4),
    })

    listings = varbergs_bostad.fetch(http)

    assert len(listings) == 1
    listing = listings[0]
    assert listing.key == "varbergsbostad:A"
    assert listing.url == "https://minasidor.varbergsbostad.se/market/residential/A"
    assert listing.address == "Köpstadsvägen 58"
    assert listing.area == "Sörse"
    assert listing.city == "VARBERG"
    assert listing.rooms == 3.0
    assert listing.size_sqm == 72.5
    assert listing.rent == 10618
    assert listing.available_from == "2027-01-01"
    assert listing.apply_by is not None
    assert listing.first_hand is True
    assert listing.end_date is None


def test_momentum_pages_until_count_reached():
    first = {"count": 2, "items": [{"id": "A", "queueType": "parking", "location": {}}]}
    second = {"count": 2, "items": [{"id": "B", "queueType": "residential", "location": {}}]}
    http = FakeHttp({
        VB + "v2/market/objects?offset=0&limit=500": first,
        VB + "v2/market/objects?offset=1&limit=500": second,
        VB + "v2/market/objects/B": _detail("B", ["Håsten"], "VARBERG", "4 rum och kök", 9000),
    })

    assert [l.id for l in varbergs_bostad.fetch(http)] == ["B"]


def test_fortinova_keeps_only_varberg_municipality_and_uses_district():
    page = {
        "count": 2,
        "items": [
            {"id": "T", "queueType": "residential",
             "location": {"areaPath": [{"displayName": "Varberg"}, {"displayName": "Tvååker"}]}},
            {"id": "G", "queueType": "residential",
             "location": {"areaPath": [{"displayName": "Göteborg"}, {"displayName": "Angered"}]}},
        ],
    }
    http = FakeHttp({
        FN + "v2/market/objects?offset=0&limit=500": page,
        FN + "v2/market/objects/T": _detail("T", ["Varberg", "Tvååker"], "Tvååker", "2 rum och kök", 7758.64, rooms=2.0),
    })

    listings = fortinova.fetch(http)

    assert [l.key for l in listings] == ["fortinova:T"]
    assert listings[0].area == "Tvååker"
    assert listings[0].rooms == 2.0
    assert listings[0].url == "https://minasidor.fortinova.se/market/residential/T"
    assert FN + "v2/market/objects/G" not in http.calls
