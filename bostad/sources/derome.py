import logging
import re
from urllib.parse import unquote

from bs4 import BeautifulSoup

from bostad.model import Listing
from bostad.parsing import parse_int, parse_rooms

BASE = "https://www.deromefastighet.se"
LIST_URL = BASE + "/lediga-lagenheter"
VARBERG_POSTCODE_PREFIX = "432"
log = logging.getLogger(__name__)


def _listing_paths(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    paths = []
    for item in soup.select("li.product-list__item[data-marker]"):
        match = re.match(r"url:([^|]+)", unquote(item["data-marker"]))
        if match and match.group(1) not in paths:
            paths.append(match.group(1))
    return paths


def _facts(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    facts = {}
    for item in soup.select(".specifications-item"):
        spans = item.find_all("span")
        if len(spans) >= 2:
            facts[spans[0].get_text(strip=True)] = spans[-1].get_text(" ", strip=True)
    return facts


def _to_listing(path: str, facts: dict[str, str]) -> Listing | None:
    if "Adress" not in facts:
        return None
    parts = [p.strip() for p in facts["Adress"].split(",")]
    postcode = parts[1] if len(parts) >= 3 else ""
    if postcode and not postcode.replace(" ", "").startswith(VARBERG_POSTCODE_PREFIX):
        return None
    city = parts[-1] if len(parts) >= 2 else ""
    size = parse_int(facts.get("Boyta"))
    return Listing(
        source="derome",
        id=path.rstrip("/").rsplit("/", 1)[-1],
        url=BASE + path,
        address=parts[0],
        area=city,
        city=city,
        rooms=parse_rooms(facts.get("Antal rum")),
        size_sqm=float(size) if size is not None else None,
        rent=parse_int(facts.get("Månadsavgift")),
        available_from=facts.get("Tillgänglig från") or facts.get("Inflyttningsdatum"),
        apply_by=facts.get("Anmäl senast"),
        first_hand=True,
        end_date=None,
    )


def fetch(http) -> list[Listing]:
    listings = []
    for path in _listing_paths(http.get_text(LIST_URL)):
        try:
            listing = _to_listing(path, _facts(http.get_text(BASE + path)))
        except Exception as error:  # one broken listing must not hide the others
            log.warning("Derome: hoppar över %s: %s", path, error)
            continue
        if listing:
            listings.append(listing)
    return listings
