import re
from datetime import datetime
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
_ROOMS = re.compile(r"(\d+(?:[.,]\d+)?)\s*rum", re.IGNORECASE)
_MOMENTUM_DATE = re.compile(r"/Date\((-?\d+)\)/")


def parse_rooms(text: str | None) -> float | None:
    match = _ROOMS.search(text or "")
    return float(match.group(1).replace(",", ".")) if match else None


def parse_int(text: str | None) -> int | None:
    digits = re.sub(r"\D", "", (text or "").split(",")[0])
    return int(digits) if digits else None


def parse_momentum_date(value: str | None) -> str | None:
    match = _MOMENTUM_DATE.search(value or "")
    if not match:
        return None
    moment = datetime.fromtimestamp(int(match.group(1)) / 1000, tz=STOCKHOLM)
    return moment.date().isoformat()
