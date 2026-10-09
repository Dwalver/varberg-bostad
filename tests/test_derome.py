from bostad.sources import derome
from tests.fakes import FakeHttp

BASE = "https://www.deromefastighet.se"

LIST_HTML = """
<ul class="product-list ">
  <li class="product-list__item hide" data-filtervalues="rooms=3"
      data-marker="url%3a%2flediga-lagenheter%2flagenhet%2f5023-118-5%7csize%3asmall%7c57.1%2c12.2"></li>
  <li class="product-list__item hide" data-filtervalues="rooms=3"
      data-marker="url%3a%2flediga-lagenheter%2flagenhet%2f3640-107-1%7csize%3asmall%7c57.4%2c12.1"></li>
  <li class="product-list__item hide" data-filtervalues="rooms=2"
      data-marker="url%3a%2flediga-lagenheter%2flagenhet%2f9999-1-1%7csize%3asmall%7c57.1%2c12.2"></li>
</ul>
"""


def _detail(address, rent="10 618 kr", rooms="3 rum och kök"):
    return f"""
    <div class="specifications-item"><span class="title ">Tillg&#xE4;nglig fr&#xE5;n</span><span>2027-01-01</span></div>
    <div class="specifications-item"><span class="title ">Anm&#xE4;l senast</span><span>2026-10-20</span></div>
    <div class="specifications-item"><span class="title ">M&#xE5;nadsavgift</span><span>  {rent}</span></div>
    <div class="specifications-item"><span class="title ">Antal rum</span><span>{rooms}</span></div>
    <div class="specifications-item"><span class="title ">Boyta</span><span>72 kvm</span></div>
    <div class="specifications-item"><span class="title ">Adress</span><span>{address}</span></div>
    """


def test_derome_parses_listings_in_varberg_only():
    http = FakeHttp({
        BASE + "/lediga-lagenheter": LIST_HTML,
        BASE + "/lediga-lagenheter/lagenhet/5023-118-5": _detail("Trönningebjärsvägen 37, 432 54, Varberg"),
        BASE + "/lediga-lagenheter/lagenhet/3640-107-1": _detail("Astrakanvägen 55, 439 73, Fjärås"),
        BASE + "/lediga-lagenheter/lagenhet/9999-1-1": _detail("Okänd väg 1"),
    })

    listings = derome.fetch(http)

    assert [l.id for l in listings] == ["5023-118-5", "9999-1-1"]
    first = listings[0]
    assert first.key == "derome:5023-118-5"
    assert first.url == BASE + "/lediga-lagenheter/lagenhet/5023-118-5"
    assert first.address == "Trönningebjärsvägen 37"
    assert first.area == "Varberg"
    assert first.city == "Varberg"
    assert first.rent == 10618
    assert first.rooms == 3.0
    assert first.size_sqm == 72.0
    assert first.available_from == "2027-01-01"
    assert first.apply_by == "2026-10-20"
    assert first.first_hand is True


def test_derome_skips_broken_detail():
    http = FakeHttp({
        BASE + "/lediga-lagenheter": LIST_HTML,
        BASE + "/lediga-lagenheter/lagenhet/5023-118-5": _detail("Trönningebjärsvägen 37, 432 54, Varberg"),
        BASE + "/lediga-lagenheter/lagenhet/9999-1-1": "<html>ingen fakta</html>",
        # 3640-107-1 missing -> FakeHttp raises like a 404
    })

    assert [l.id for l in derome.fetch(http)] == ["5023-118-5"]


def test_derome_empty_list_is_not_an_error():
    http = FakeHttp({BASE + "/lediga-lagenheter": "<ul class='product-list'></ul>"})
    assert derome.fetch(http) == []
