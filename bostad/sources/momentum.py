import logging

from bostad.model import Listing
from bostad.parsing import parse_momentum_date, parse_rooms

API_KEY = "pJnKrR6B3FzRNFsF33xL8LhSs55KPJrm"
PAGE_SIZE = 500
log = logging.getLogger(__name__)


def _area_path(item) -> list[str]:
    path = (item.get("location") or {}).get("areaPath") or []
    return [p.get("displayName", "").strip() for p in path]


def _list_objects(http, base_url, headers) -> list[dict]:
    items: list[dict] = []
    while True:
        url = f"{base_url}v2/market/objects?offset={len(items)}&limit={PAGE_SIZE}"
        page = http.get_json(url, headers)
        batch = page.get("items") or []
        items.extend(batch)
        if not batch or len(items) >= page.get("count", 0):
            return items


def _to_listing(source, link_base, detail) -> Listing:
    location = detail.get("location") or {}
    address = location.get("address") or {}
    size = detail.get("size") or {}
    path = _area_path(detail)
    price = (detail.get("pricing") or {}).get("price")
    return Listing(
        source=source,
        id=detail["id"],
        url=f"{link_base}{detail['id']}",
        address=(address.get("address") or detail.get("displayName") or "").strip(),
        area=path[-1] if path else ((location.get("area") or {}).get("displayName") or "").strip(),
        city=(address.get("city") or "").strip(),
        rooms=size.get("rooms") or parse_rooms(size.get("roomsDisplayName")),
        size_sqm=size.get("area"),
        rent=round(price) if price else None,
        available_from=parse_momentum_date((detail.get("availability") or {}).get("availableFrom")),
        apply_by=parse_momentum_date((detail.get("application") or {}).get("openTo")),
        first_hand=True,
        end_date=None,
    )


def fetch_momentum(http, *, source, base_url, app_instance, link_base, include=lambda item: True) -> list[Listing]:
    headers = {
        "Accept": "application/json",
        "X-Api-Key": API_KEY,
        "X-Momentum-Api-App-Instance": app_instance,
    }
    wanted = [
        item for item in _list_objects(http, base_url, headers)
        if item.get("queueType") == "residential" and include(item)
    ]
    listings = []
    for item in wanted:
        try:
            detail = http.get_json(f"{base_url}v2/market/objects/{item['id']}", headers)
            listings.append(_to_listing(source, link_base, detail))
        except Exception as error:  # one broken listing must not hide the others
            log.warning("%s: hoppar över %s: %s", source, item.get("id"), error)
    return listings
