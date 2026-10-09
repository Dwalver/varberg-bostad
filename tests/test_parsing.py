from bostad.model import Listing
from bostad.parsing import parse_int, parse_momentum_date, parse_rooms


def test_parse_rooms():
    assert parse_rooms("3 rum och kök") == 3.0
    assert parse_rooms("1 rum och kokvrå") == 1.0
    assert parse_rooms("3,5 rum") == 3.5
    assert parse_rooms("Parkeringsplats") is None
    assert parse_rooms(None) is None
    assert parse_rooms("") is None


def test_parse_int():
    assert parse_int("  10 540 kr") == 10540
    assert parse_int("73 kvm") == 73
    assert parse_int("10 540 kr") == 10540
    assert parse_int("saknas") is None
    assert parse_int(None) is None


def test_parse_momentum_date_uses_stockholm_time():
    # 2026-12-31T23:00:00Z == 2027-01-01 00:00 in Stockholm
    assert parse_momentum_date("/Date(1798758000000)/") == "2027-01-01"
    assert parse_momentum_date(None) is None
    assert parse_momentum_date("garbage") is None


def test_listing_key():
    listing = Listing(
        source="qasa", id="123", url="u", address="a", area="Varberg", city="",
        rooms=3.0, size_sqm=70.0, rent=9000, available_from=None, apply_by=None,
        first_hand=True, end_date=None,
    )
    assert listing.key == "qasa:123"
