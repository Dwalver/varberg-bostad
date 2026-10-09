import re
from dataclasses import dataclass
from typing import Literal

import yaml

from bostad.model import Listing


@dataclass(frozen=True)
class Criteria:
    max_rent: int
    min_rooms: float
    allowed_areas: list[str]
    excluded_areas: list[str]


@dataclass(frozen=True)
class Match:
    listing: Listing
    unknown_area: bool


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _mentions(text: str, names: list[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(_normalize(n))}(?!\w)", text) for n in names)


def area_status(listing: Listing, criteria: Criteria) -> Literal["ok", "excluded", "unknown"]:
    texts = [t for t in (_normalize(listing.area), _normalize(listing.city)) if t]
    if any(_mentions(t, criteria.excluded_areas) for t in texts):
        return "excluded"
    if any(_mentions(t, criteria.allowed_areas) for t in texts):
        return "ok"
    return "unknown"


def _passes(listing: Listing, criteria: Criteria) -> bool:
    if listing.rent is not None and listing.rent > criteria.max_rent:
        return False
    if listing.rooms is not None and listing.rooms < criteria.min_rooms:
        return False
    return listing.first_hand and not listing.end_date


def filter_listings(listings: list[Listing], criteria: Criteria) -> list[Match]:
    matches = []
    for listing in listings:
        status = area_status(listing, criteria)
        if status != "excluded" and _passes(listing, criteria):
            matches.append(Match(listing, unknown_area=status == "unknown"))
    return matches


def load_config(path: str) -> tuple[Criteria, str]:
    with open(path, encoding="utf-8") as file:
        raw = yaml.safe_load(file)
    criteria = Criteria(
        max_rent=int(raw["max_rent"]),
        min_rooms=float(raw["min_rooms"]),
        allowed_areas=list(raw["allowed_areas"]),
        excluded_areas=list(raw["excluded_areas"]),
    )
    return criteria, raw.get("ntfy_server", "https://ntfy.sh")
