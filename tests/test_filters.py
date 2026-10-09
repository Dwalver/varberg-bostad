from dataclasses import replace

from bostad.filters import Criteria, area_status, filter_listings, load_config
from bostad.model import Listing

CRITERIA = Criteria(
    max_rent=11000, min_rooms=3,
    allowed_areas=["Varberg", "Veddige", "Trönninge", "Åskloster", "Sörse", "Centrala Varberg"],
    excluded_areas=["Bua", "Tvååker", "Träslövsläge", "Karl Gustav"],
)
BASE = Listing(
    source="qasa", id="1", url="u", address="a", area="Varberg", city="",
    rooms=3.0, size_sqm=70.0, rent=10000, available_from=None, apply_by=None,
    first_hand=True, end_date=None,
)


def test_area_normalization():
    assert area_status(replace(BASE, area="Varberg "), CRITERIA) == "ok"
    assert area_status(replace(BASE, area="", city="VARBERG"), CRITERIA) == "ok"
    assert area_status(replace(BASE, area="Tvååker  "), CRITERIA) == "excluded"
    assert area_status(replace(BASE, area="centrala  varberg"), CRITERIA) == "ok"


def test_excluded_wins_over_allowed_city():
    assert area_status(replace(BASE, area="Bua", city="VARBERG"), CRITERIA) == "excluded"


def test_whole_word_match_only():
    # "Träslövsläge" must not count as Varberg/Träslöv just by substring
    assert area_status(replace(BASE, area="Träslövsläge"), CRITERIA) == "excluded"
    assert area_status(replace(BASE, area="Veddigeby"), CRITERIA) == "unknown"


def test_unknown_area_is_kept_and_flagged():
    matches = filter_listings([replace(BASE, area="med fantastisk havsutsikt")], CRITERIA)
    assert len(matches) == 1 and matches[0].unknown_area is True


def test_rent_rooms_and_contract_rules():
    keep = [
        BASE,
        replace(BASE, id="2", rent=11000),
        replace(BASE, id="3", rooms=None),      # unknown rooms -> keep
        replace(BASE, id="4", rent=None),       # unknown rent -> keep
    ]
    drop = [
        replace(BASE, id="5", rent=11001),
        replace(BASE, id="6", rooms=2.5),
        replace(BASE, id="7", first_hand=False),
        replace(BASE, id="8", end_date="2027-05-31"),
        replace(BASE, id="9", area="Bua"),
    ]
    matches = filter_listings(keep + drop, CRITERIA)
    assert [m.listing.id for m in matches] == ["1", "2", "3", "4"]
    assert all(m.unknown_area is False for m in matches)


def test_load_config_reads_repo_config():
    criteria, server = load_config("config.yaml")
    assert criteria.max_rent == 11000
    assert criteria.min_rooms == 3
    assert "Veddige" in criteria.allowed_areas
    assert "Tvååker" in criteria.excluded_areas
    assert server == "https://ntfy.sh"
