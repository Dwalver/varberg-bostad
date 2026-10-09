from bostad.filters import Match

SOURCE_NAMES = {
    "varbergsbostad": "Varbergs Bostad",
    "fortinova": "Fortinova",
    "derome": "Derome",
    "qasa": "Qasa",
}


def _number(value: float | None) -> str:
    if value is None:
        return "?"
    if float(value).is_integer():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:.1f}".replace(".", ",")


def format_message(match: Match) -> dict:
    listing = match.listing
    place = listing.area or listing.city or "?"
    title = f"{_number(listing.rooms)} rok, {_number(listing.size_sqm)} m² – {place}"
    if match.unknown_area:
        title = "⚠️ okänt område · " + title
    details = [f"{_number(listing.rent)} kr/mån"]
    if listing.available_from:
        details.append(f"inflytt {listing.available_from}")
    if listing.apply_by:
        details.append(f"sök senast {listing.apply_by}")
    details.append(SOURCE_NAMES.get(listing.source, listing.source))
    return {
        "title": title,
        "message": f"{listing.address}\n" + " · ".join(details),
        "click": listing.url,
        "tags": ["house"],
    }


def format_alert(source: str, error: str) -> dict:
    name = SOURCE_NAMES.get(source, source)
    return {
        "title": f"Bostadsbevakning: {name} har slutat fungera",
        "message": f"{name} har misslyckats 3 körningar i rad. Senaste fel: {error}",
        "tags": ["warning"],
        "priority": 4,
    }


def send(http, server: str, topic: str, payload: dict) -> None:
    http.post_json(server, {"topic": topic, **payload})
