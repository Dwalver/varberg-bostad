# Bostadsbevakning Varberg Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python job, run by GitHub Actions every 15 minutes, that collects rental listings from Varbergs Bostad, Fortinova, Derome Fastighet and Qasa, filters them, and sends one ntfy push per new matching listing.

**Architecture:** One module per source returns `list[Listing]` via a small injectable `Http` wrapper (tests use a fake). Pure filter, notification-formatting and state modules sit behind the sources; `main.run()` orchestrates and is tested end-to-end with fakes. State (`state/seen.json`) is committed back to the repo by the workflow.

**Tech Stack:** Python 3.12 (CI) / 3.13 (local), requests, beautifulsoup4, PyYAML, tzdata, pytest, GitHub Actions, ntfy.sh, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-10-09-varberg-bostad-design.md`

## Global Constraints

- Areas: Varberg (town incl. districts), Veddige, Trönninge, Derome, Åskloster. Other places in the municipality (e.g. Tvååker, Bua, Träslövsläge) are filtered out.
- Rent ≤ 11 000 kr/month; rooms ≥ 3; first-hand only; no short-term rentals.
- Unknown area name → still notify, marked "⚠️ okänt område".
- Missing rent/rooms value → still notify (shown as "?").
- One ntfy notification per listing; mark as seen only after a successful send.
- First run sends every current match; later runs only new ones.
- A source failing must not stop other sources; 3 consecutive failures → one warning notification.
- A source returning 0 listings is not a failure.
- Public GitHub repo, cron `*/15 * * * *` + `workflow_dispatch`, ntfy topic in secret `NTFY_TOPIC`, server `https://ntfy.sh`.
- Momentum public client key: `pJnKrR6B3FzRNFsF33xL8LhSs55KPJrm`; app instances: Varbergs Bostad `EAP-13681`, Fortinova `EAP-51033`.
- All commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Area names with odd casing/whitespace (`"Varberg "`, `"VARBERG"`, `"Tvååker  "`) — must be matched after normalization (Task 5 test `test_area_normalization`).
2. Room strings that are not "N rum…" (`"Parkeringsplats"`, `"1 rum och kokvrå"`, `"3,5 rum"`) — must parse to number or `None` without crashing (Task 2 test `test_parse_rooms`).
3. ntfy send failing mid-batch — failed listing must not be marked seen, so it is retried next run (Task 7 test `test_failed_send_is_retried`).
4. A Derome detail page that 404s or lacks fields — skip that listing, keep the rest (Task 3 test `test_derome_skips_broken_detail`).
5. Qasa: rent must include `tenantBaseFee` when checking max rent (Task 4 test `test_qasa_rent_includes_fee`).

---

## File Structure

```
varberg-bostad/
  requirements.txt
  config.yaml                    filter criteria + area lists + ntfy server
  bostad/__init__.py
  bostad/http.py                 Http wrapper (requests) – get_json/get_text/post_json
  bostad/model.py                Listing dataclass
  bostad/parsing.py              parse_rooms, parse_int, parse_momentum_date
  bostad/sources/__init__.py
  bostad/sources/momentum.py     shared Momentum client
  bostad/sources/varbergs_bostad.py
  bostad/sources/fortinova.py
  bostad/sources/derome.py
  bostad/sources/qasa.py
  bostad/filters.py              Criteria, Match, filter_listings, load_config
  bostad/notify.py               format_message, format_alert, send
  bostad/state.py                State, load_state, save_state
  bostad/main.py                 run(), main() with --dry-run
  state/seen.json
  tests/fakes.py                 FakeHttp
  tests/test_*.py
  .github/workflows/check.yml
```

---

### Task 1: Scaffold, Listing model and parsing helpers

**Files:**
- Create: `requirements.txt`, `.gitignore`, `bostad/__init__.py`, `bostad/sources/__init__.py`, `bostad/model.py`, `bostad/parsing.py`, `bostad/http.py`, `tests/__init__.py`, `tests/fakes.py`
- Test: `tests/test_parsing.py`

**Interfaces:**
- Produces:
  - `Listing(source: str, id: str, url: str, address: str, area: str, city: str, rooms: float|None, size_sqm: float|None, rent: int|None, available_from: str|None, apply_by: str|None, first_hand: bool, end_date: str|None)` with property `key -> str` = `f"{source}:{id}"`.
  - `parse_rooms(text: str|None) -> float|None`, `parse_int(text: str|None) -> int|None`, `parse_momentum_date(value: str|None) -> str|None` (ISO date in Europe/Stockholm).
  - `Http(timeout=30)` with `get_json(url, headers=None)`, `get_text(url, headers=None)`, `post_json(url, payload, headers=None)`; all raise on HTTP error.
  - `tests.fakes.FakeHttp(routes: dict[str, object])` – same three methods; looks up `url` (for `post_json`, the key is `url` and the value may be a callable `payload -> response`); missing route raises `RuntimeError("404 " + url)`; records calls in `.calls`.

- [ ] **Step 1: Create venv and requirements**

`requirements.txt`:
```
requests==2.32.3
beautifulsoup4==4.12.3
PyYAML==6.0.2
tzdata==2025.2
pytest==8.3.4
```

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
```

Run:
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```
Expected: installs without errors.

- [ ] **Step 2: Write the failing test**

`tests/test_parsing.py`:
```python
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
    assert parse_int("10\u00a0540 kr") == 10540
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_parsing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bostad'`

- [ ] **Step 4: Write implementation**

`bostad/__init__.py`, `bostad/sources/__init__.py`, `tests/__init__.py`: empty files.

`bostad/model.py`:
```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Listing:
    source: str
    id: str
    url: str
    address: str
    area: str
    city: str
    rooms: float | None
    size_sqm: float | None
    rent: int | None
    available_from: str | None
    apply_by: str | None
    first_hand: bool
    end_date: str | None

    @property
    def key(self) -> str:
        return f"{self.source}:{self.id}"
```

`bostad/parsing.py`:
```python
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
```

`bostad/http.py`:
```python
import requests

USER_AGENT = "Mozilla/5.0 (bostadsbevakning-varberg; +https://github.com)"


class Http:
    def __init__(self, timeout: float = 30):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get_json(self, url, headers=None):
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get_text(self, url, headers=None):
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        response.encoding = response.encoding or "utf-8"
        return response.text

    def post_json(self, url, payload, headers=None):
        response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json() if response.content else None
```

`tests/fakes.py`:
```python
class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def _lookup(self, url, payload=None):
        self.calls.append(url)
        if url not in self.routes:
            raise RuntimeError("404 " + url)
        value = self.routes[url]
        if isinstance(value, Exception):
            raise value
        return value(payload) if callable(value) else value

    def get_json(self, url, headers=None):
        return self._lookup(url)

    def get_text(self, url, headers=None):
        return self._lookup(url)

    def post_json(self, url, payload, headers=None):
        return self._lookup(url, payload)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_parsing.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add requirements.txt .gitignore bostad tests
git commit -m "feat: scaffold project with Listing model and parsing helpers"
```

---

### Task 2: Momentum sources (Varbergs Bostad, Fortinova)

**Files:**
- Create: `bostad/sources/momentum.py`, `bostad/sources/varbergs_bostad.py`, `bostad/sources/fortinova.py`
- Test: `tests/test_momentum.py`

**Interfaces:**
- Consumes: `Listing`, `parse_rooms`, `parse_momentum_date`, `FakeHttp`.
- Produces:
  - `momentum.fetch_momentum(http, *, source: str, base_url: str, app_instance: str, link_base: str, include=lambda item: True) -> list[Listing]`
  - `varbergs_bostad.fetch(http) -> list[Listing]` (source `"varbergsbostad"`)
  - `fortinova.fetch(http) -> list[Listing]` (source `"fortinova"`, only items whose `areaPath[0].displayName == "Varberg"`)

- [ ] **Step 1: Write the failing test**

`tests/test_momentum.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_momentum.py -v`
Expected: FAIL with `ImportError: cannot import name 'fortinova'`

- [ ] **Step 3: Write implementation**

`bostad/sources/momentum.py`:
```python
from bostad.model import Listing
from bostad.parsing import parse_momentum_date, parse_rooms

API_KEY = "pJnKrR6B3FzRNFsF33xL8LhSs55KPJrm"
PAGE_SIZE = 500


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
    return [
        _to_listing(source, link_base, http.get_json(f"{base_url}v2/market/objects/{item['id']}", headers))
        for item in wanted
    ]
```

`bostad/sources/varbergs_bostad.py`:
```python
from bostad.sources.momentum import fetch_momentum


def fetch(http):
    return fetch_momentum(
        http,
        source="varbergsbostad",
        base_url="https://varberg-fastighet.momentum.se/Prod/Varberg/PmApi/",
        app_instance="EAP-13681",
        link_base="https://minasidor.varbergsbostad.se/market/residential/",
    )
```

`bostad/sources/fortinova.py`:
```python
from bostad.sources.momentum import _area_path, fetch_momentum


def _in_varberg(item) -> bool:
    path = _area_path(item)
    return bool(path) and path[0] == "Varberg"


def fetch(http):
    return fetch_momentum(
        http,
        source="fortinova",
        base_url="https://fortinova-fastighet.momentum.se/Prod/Fortinova/PmApi/",
        app_instance="EAP-51033",
        link_base="https://minasidor.fortinova.se/market/residential/",
        include=_in_varberg,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_momentum.py -v`
Expected: 3 passed

- [ ] **Step 5: Live smoke check**

Run:
```bash
.venv/Scripts/python -c "from bostad.http import Http; from bostad.sources import varbergs_bostad, fortinova; h=Http(); [print(l) for l in varbergs_bostad.fetch(h)+fortinova.fetch(h)]"
```
Expected: several `Listing(...)` lines with Varberg-area addresses, numeric rent and rooms; no exception.

- [ ] **Step 6: Commit**

```bash
git add bostad/sources tests/test_momentum.py
git commit -m "feat: add Momentum sources for Varbergs Bostad and Fortinova"
```

---

### Task 3: Derome source

**Files:**
- Create: `bostad/sources/derome.py`
- Test: `tests/test_derome.py`

**Interfaces:**
- Consumes: `Listing`, `parse_rooms`, `parse_int`, `FakeHttp`.
- Produces: `derome.fetch(http) -> list[Listing]` (source `"derome"`, id = last path segment e.g. `"3902-104-2"`; only postcodes starting `432` (Varberg municipality) or with no postcode).

- [ ] **Step 1: Write the failing test**

`tests/test_derome.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_derome.py -v`
Expected: FAIL with `ImportError: cannot import name 'derome'`

- [ ] **Step 3: Write implementation**

`bostad/sources/derome.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_derome.py -v`
Expected: 3 passed

- [ ] **Step 5: Live smoke check**

Run:
```bash
.venv/Scripts/python -c "from bostad.http import Http; from bostad.sources import derome; [print(l) for l in derome.fetch(Http())]"
```
Expected: no exception; prints only Varberg-municipality listings (may be zero lines today — all current Derome vacancies are outside Varberg).

- [ ] **Step 6: Commit**

```bash
git add bostad/sources/derome.py tests/test_derome.py
git commit -m "feat: add Derome Fastighet source"
```

---

### Task 4: Qasa source

**Files:**
- Create: `bostad/sources/qasa.py`
- Test: `tests/test_qasa.py`

**Interfaces:**
- Consumes: `Listing`, `FakeHttp` (its `post_json` route value is a callable receiving the payload).
- Produces: `qasa.fetch(http) -> list[Listing]` (source `"qasa"`; shared rooms excluded; `rent = rent + tenantBaseFee`).

- [ ] **Step 1: Write the failing test**

`tests/test_qasa.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_qasa.py -v`
Expected: FAIL with `ImportError: cannot import name 'qasa'`

- [ ] **Step 3: Write implementation**

`bostad/sources/qasa.py`:
```python
from bostad.model import Listing

URL = "https://api.qasa.se/graphql"
PAGE_SIZE = 100
MAX_PAGES = 10
QUERY = """
query Search($offset: Int) {
  homeIndexSearch(params: {areaIdentifier: ["se/varberg"]}) {
    documents(limit: 100, offset: $offset) {
      hasNextPage
      nodes {
        id rent tenantBaseFee roomCount squareMeters firstHand shared startDate endDate
        location { locality route streetNumber }
      }
    }
  }
}
"""


def _to_listing(node) -> Listing:
    location = node.get("location") or {}
    rent = node.get("rent")
    address = " ".join(p for p in (location.get("route"), location.get("streetNumber")) if p)
    return Listing(
        source="qasa",
        id=str(node["id"]),
        url=f"https://qasa.se/sv/home/{node['id']}",
        address=address,
        area=(location.get("locality") or "").strip(),
        city="",
        rooms=node.get("roomCount"),
        size_sqm=float(node["squareMeters"]) if node.get("squareMeters") is not None else None,
        rent=rent + (node.get("tenantBaseFee") or 0) if rent is not None else None,
        available_from=(node.get("startDate") or "")[:10] or None,
        apply_by=None,
        first_hand=bool(node.get("firstHand")),
        end_date=(node.get("endDate") or "")[:10] or None,
    )


def fetch(http) -> list[Listing]:
    listings = []
    for page in range(MAX_PAGES):
        response = http.post_json(URL, {"query": QUERY, "variables": {"offset": page * PAGE_SIZE}})
        if response.get("errors"):
            raise RuntimeError("Qasa: " + "; ".join(e.get("message", "?") for e in response["errors"]))
        documents = response["data"]["homeIndexSearch"]["documents"]
        listings.extend(_to_listing(n) for n in documents["nodes"] if not n.get("shared"))
        if not documents.get("hasNextPage"):
            break
    return listings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_qasa.py -v`
Expected: 3 passed

- [ ] **Step 5: Live smoke check**

Run:
```bash
.venv/Scripts/python -c "from bostad.http import Http; from bostad.sources import qasa; r=qasa.fetch(Http()); print(len(r)); print(r[0])"
```
Expected: a count around 40–45 and one `Listing(source='qasa', ...)`.

- [ ] **Step 6: Commit**

```bash
git add bostad/sources/qasa.py tests/test_qasa.py
git commit -m "feat: add Qasa source"
```

---

### Task 5: Config and filters

**Files:**
- Create: `config.yaml`, `bostad/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Consumes: `Listing`.
- Produces:
  - `Criteria(max_rent: int, min_rooms: float, allowed_areas: list[str], excluded_areas: list[str])`
  - `Match(listing: Listing, unknown_area: bool)`
  - `area_status(listing, criteria) -> Literal["ok", "excluded", "unknown"]`
  - `filter_listings(listings: list[Listing], criteria) -> list[Match]`
  - `load_config(path: str) -> tuple[Criteria, str]` (second value: ntfy server URL)

- [ ] **Step 1: Write config.yaml**

```yaml
# Filter för bostadsbevakningen. Ändra här – ingen kod behöver röras.
max_rent: 11000        # kr/mån, inkl. ev. avgifter
min_rooms: 3
ntfy_server: https://ntfy.sh

# Orter och stadsdelar som räknas som "ditt område".
allowed_areas:
  - Varberg
  - Veddige
  - Trönninge
  - Trönningenäs
  - Derome
  - Åskloster
  # Stadsdelar i Varberg
  - Centralt
  - Centrum
  - Centrum Norr
  - Centrala Varberg
  - Håsten
  - Sörse
  - Brunnsberg
  - Apelviken
  - Apelvikshöjd
  - Breared
  - Göingegården
  - Lassabacka
  - Hästhagen
  - Kvarnakulle
  - Marmorlyckan
  - Träslöv
  - Bläshammar
  - Getakärr
  - Sörsedammen

# Orter i kommunen som INTE ska bevakas.
excluded_areas:
  - Bua
  - Tvååker
  - Träslövsläge
  - Kungsäter
  - Rolfstorp
  - Himle
  - Skällinge
  - Grimeton
  - Kärradal
  - Tofta
  - Valinge
  - Lindberg
  - Sibbarp
  - Dagsås
  - Nösslinge
  - Spannarp
  - Stamnared
  - Gunnarsjö
  - Karl Gustav
  - Torpa
  - Stråvalla
  - Åkulla
```

Note: `Väröbacka` is deliberately in neither list — it is the postal town for both Bua (excluded) and Åskloster (wanted), so it falls through to "okänt område".

- [ ] **Step 2: Write the failing test**

`tests/test_filters.py`:
```python
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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_filters.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bostad.filters'`

- [ ] **Step 4: Write implementation**

`bostad/filters.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_filters.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add config.yaml bostad/filters.py tests/test_filters.py
git commit -m "feat: add configurable area, rent, room and contract filters"
```

---

### Task 6: Notification formatting, ntfy sending and state

**Files:**
- Create: `bostad/notify.py`, `bostad/state.py`, `state/seen.json`
- Test: `tests/test_notify.py`, `tests/test_state.py`

**Interfaces:**
- Consumes: `Listing`, `Match`, `FakeHttp`.
- Produces:
  - `notify.format_message(match: Match) -> dict` with keys `title`, `message`, `click`, `tags`
  - `notify.format_alert(source: str, error: str) -> dict` with keys `title`, `message`, `tags`, `priority`
  - `notify.send(http, server: str, topic: str, payload: dict) -> None` (POSTs `{"topic": topic, **payload}` to `server`)
  - `notify.SOURCE_NAMES: dict[str, str]`
  - `State(seen: dict[str, str], failures: dict[str, int])`; `load_state(path) -> State` (missing file → empty); `save_state(state, path) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_notify.py`:
```python
from dataclasses import replace

from bostad.filters import Match
from bostad.model import Listing
from bostad.notify import format_alert, format_message, send
from tests.fakes import FakeHttp

LISTING = Listing(
    source="derome", id="5023-118-5", url="https://example/5023", address="Trönningebjärsvägen 37",
    area="Trönninge", city="Varberg", rooms=3.0, size_sqm=72.0, rent=10618,
    available_from="2027-01-01", apply_by="2026-10-20", first_hand=True, end_date=None,
)


def test_format_message_full():
    payload = format_message(Match(LISTING, unknown_area=False))
    assert payload["title"] == "3 rok, 72 m² – Trönninge"
    assert payload["message"] == (
        "Trönningebjärsvägen 37\n10 618 kr/mån · inflytt 2027-01-01 · sök senast 2026-10-20 · Derome"
    )
    assert payload["click"] == "https://example/5023"
    assert payload["tags"] == ["house"]


def test_format_message_missing_values_and_unknown_area():
    listing = replace(LISTING, rooms=None, size_sqm=None, rent=None, apply_by=None,
                      available_from=None, area="", city="Väröbacka", source="qasa")
    payload = format_message(Match(listing, unknown_area=True))
    assert payload["title"] == "⚠️ okänt område · ? rok, ? m² – Väröbacka"
    assert payload["message"] == "Trönningebjärsvägen 37\n? kr/mån · Qasa"


def test_format_message_half_rooms():
    payload = format_message(Match(replace(LISTING, rooms=3.5), unknown_area=False))
    assert payload["title"].startswith("3,5 rok")


def test_format_alert():
    payload = format_alert("qasa", "429 Too Many Requests")
    assert payload["title"] == "Bostadsbevakning: Qasa har slutat fungera"
    assert "429 Too Many Requests" in payload["message"]
    assert payload["priority"] == 4


def test_send_posts_topic_and_payload():
    received = []
    http = FakeHttp({"https://ntfy.sh": lambda p: received.append(p)})
    send(http, "https://ntfy.sh", "mitt-amne", {"title": "t", "message": "m"})
    assert received == [{"topic": "mitt-amne", "title": "t", "message": "m"}]
```

`tests/test_state.py`:
```python
from bostad.state import State, load_state, save_state


def test_missing_file_gives_empty_state(tmp_path):
    state = load_state(str(tmp_path / "nope.json"))
    assert state == State(seen={}, failures={})


def test_round_trip(tmp_path):
    path = str(tmp_path / "state" / "seen.json")
    save_state(State(seen={"qasa:1": "2026-10-09T10:00:00+00:00"}, failures={"derome": 2}), path)
    assert load_state(path) == State(seen={"qasa:1": "2026-10-09T10:00:00+00:00"}, failures={"derome": 2})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_notify.py tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bostad.notify'`

- [ ] **Step 3: Write implementation**

`bostad/notify.py`:
```python
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
```

`bostad/state.py`:
```python
import json
import os
from dataclasses import asdict, dataclass, field


@dataclass
class State:
    seen: dict[str, str] = field(default_factory=dict)
    failures: dict[str, int] = field(default_factory=dict)


def load_state(path: str) -> State:
    if not os.path.exists(path):
        return State()
    with open(path, encoding="utf-8") as file:
        raw = json.load(file)
    return State(seen=raw.get("seen", {}), failures=raw.get("failures", {}))


def save_state(state: State, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as file:
        json.dump(asdict(state), file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
```

`state/seen.json`:
```json
{
  "failures": {},
  "seen": {}
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python -m pytest tests/test_notify.py tests/test_state.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add bostad/notify.py bostad/state.py state/seen.json tests/test_notify.py tests/test_state.py
git commit -m "feat: add ntfy formatting/sending and persistent state"
```

---

### Task 7: Orchestration and CLI

**Files:**
- Create: `bostad/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: all of the above.
- Produces:
  - `run(http, criteria, state, sender, sources, now: str) -> int` — returns number of listing notifications sent; mutates `state`.
    `sender(payload: dict) -> None` raises on failure. `sources: dict[str, Callable[[Http], list[Listing]]]`.
  - `ALERT_AFTER = 3`
  - `main(argv=None) -> int` — CLI: `python -m bostad.main [--dry-run]`; reads `config.yaml`, `state/seen.json`, env `NTFY_TOPIC`.

- [ ] **Step 1: Write the failing test**

`tests/test_main.py`:
```python
from dataclasses import replace

from bostad.filters import Criteria
from bostad.main import ALERT_AFTER, run
from bostad.model import Listing
from bostad.state import State

CRITERIA = Criteria(max_rent=11000, min_rooms=3, allowed_areas=["Varberg"], excluded_areas=["Bua"])
GOOD = Listing(
    source="qasa", id="1", url="u1", address="a", area="Varberg", city="",
    rooms=3.0, size_sqm=70.0, rent=10000, available_from=None, apply_by=None,
    first_hand=True, end_date=None,
)
NOW = "2026-10-09T10:00:00+00:00"


def _run(state, sources, sender):
    return run(http=None, criteria=CRITERIA, state=state, sender=sender, sources=sources, now=NOW)


def test_first_run_sends_all_matches_then_only_new():
    sent = []
    state = State()
    sources = {"qasa": lambda http: [GOOD, replace(GOOD, id="2", area="Bua")]}

    assert _run(state, sources, sent.append) == 1
    assert state.seen == {"qasa:1": NOW}

    sources = {"qasa": lambda http: [GOOD, replace(GOOD, id="3", url="u3")]}
    assert _run(state, sources, sent.append) == 1
    assert [p["click"] for p in sent] == ["u1", "u3"]
    assert set(state.seen) == {"qasa:1", "qasa:3"}


def test_failed_send_is_retried():
    calls = []

    def flaky(payload):
        calls.append(payload)
        if len(calls) == 1:
            raise RuntimeError("ntfy nere")

    state = State()
    sources = {"qasa": lambda http: [GOOD]}
    assert _run(state, sources, flaky) == 0
    assert state.seen == {}
    assert _run(state, sources, flaky) == 1
    assert "qasa:1" in state.seen


def test_failing_source_does_not_stop_others_and_alerts_once():
    sent = []

    def broken(http):
        raise RuntimeError("429")

    sources = {"derome": broken, "qasa": lambda http: [GOOD]}
    state = State()
    for _ in range(ALERT_AFTER + 1):
        _run(state, sources, sent.append)

    alerts = [p for p in sent if p.get("tags") == ["warning"]]
    assert len(alerts) == 1
    assert "Derome" in alerts[0]["title"]
    assert state.failures["derome"] == ALERT_AFTER + 1
    assert "qasa:1" in state.seen


def test_success_resets_failure_counter():
    state = State(failures={"qasa": 2})
    _run(state, {"qasa": lambda http: []}, lambda p: None)
    assert state.failures["qasa"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bostad.main'`

- [ ] **Step 3: Write implementation**

`bostad/main.py`:
```python
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

from bostad import notify
from bostad.filters import filter_listings, load_config
from bostad.http import Http
from bostad.sources import derome, fortinova, qasa, varbergs_bostad
from bostad.state import load_state, save_state

ALERT_AFTER = 3
CONFIG_PATH = "config.yaml"
STATE_PATH = "state/seen.json"
SOURCES = {
    "varbergsbostad": varbergs_bostad.fetch,
    "fortinova": fortinova.fetch,
    "derome": derome.fetch,
    "qasa": qasa.fetch,
}
log = logging.getLogger("bostad")


def run(http, criteria, state, sender, sources, now) -> int:
    listings = []
    for name, fetch in sources.items():
        try:
            found = fetch(http)
        except Exception as error:
            count = state.failures.get(name, 0) + 1
            state.failures[name] = count
            log.error("%s misslyckades (%d i rad): %s", name, count, error)
            if count == ALERT_AFTER:
                try:
                    sender(notify.format_alert(name, str(error)))
                except Exception as send_error:
                    log.error("Kunde inte skicka varning: %s", send_error)
            continue
        state.failures[name] = 0
        log.info("%s: %d annonser", name, len(found))
        listings.extend(found)

    sent = 0
    for match in filter_listings(listings, criteria):
        key = match.listing.key
        if key in state.seen:
            continue
        try:
            sender(notify.format_message(match))
        except Exception as error:
            log.error("Kunde inte skicka %s: %s", key, error)
            continue
        state.seen[key] = now
        sent += 1
    return sent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bevaka lediga lägenheter i Varbergsområdet")
    parser.add_argument("--dry-run", action="store_true", help="skriv ut notiser i stället för att skicka")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    criteria, server = load_config(CONFIG_PATH)
    state = load_state(STATE_PATH)
    http = Http()

    if args.dry_run:
        def sender(payload):
            print(json.dumps(payload, ensure_ascii=False))
    else:
        topic = os.environ.get("NTFY_TOPIC")
        if not topic:
            log.error("NTFY_TOPIC saknas")
            return 2

        def sender(payload):
            notify.send(http, server, topic, payload)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sent = run(http, criteria, state, sender, SOURCES, now)
    log.info("Skickade %d nya annonser", sent)
    if not args.dry_run:
        save_state(state, STATE_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass (30 total).

- [ ] **Step 5: Live dry run**

Run: `.venv/Scripts/python -m bostad.main --dry-run`
Expected: INFO lines with a count per source (varbergsbostad, fortinova, derome, qasa), zero or more JSON payload lines, `Skickade N nya annonser`; `state/seen.json` unchanged (`git status` clean for it).

- [ ] **Step 6: Commit**

```bash
git add bostad/main.py tests/test_main.py
git commit -m "feat: orchestrate sources, filters, notifications and state"
```

---

### Task 8: ntfy topic, GitHub repo and scheduled workflow

**Files:**
- Create: `.github/workflows/check.yml`, `README.md`

**Interfaces:**
- Consumes: `python -m bostad.main`, secret `NTFY_TOPIC`.

- [ ] **Step 1: Open the user's ntfy topic in the browser**

The user chose the topic `moC8kGjMcWPkScGI`. It is NOT committed anywhere (only stored as a GitHub secret).

Run (PowerShell):
```powershell
"moC8kGjMcWPkScGI" | Set-Content -NoNewline "$env:TEMP\ntfy-topic.txt"
Start-Process "https://ntfy.sh/moC8kGjMcWPkScGI"
```
Expected: browser opens `https://ntfy.sh/moC8kGjMcWPkScGI`. Tell the user to press "Subscribe"/allow notifications in the web app and/or add the topic in the ntfy phone app.

- [ ] **Step 2: Send a test notification**

Run:
```powershell
$topic = Get-Content "$env:TEMP\ntfy-topic.txt"
Invoke-RestMethod -Method Post -Uri "https://ntfy.sh" -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes((@{topic=$topic; title="Bostadsbevakning är igång"; message="Testnotis från Varberg-bevakningen"; tags=@("house")} | ConvertTo-Json)))
```
Expected: JSON response with an `id`; the notification appears in the open browser tab. Confirm with the user.

- [ ] **Step 3: Write the workflow**

`.github/workflows/check.yml`:
```yaml
name: Bevaka lägenheter

on:
  schedule:
    - cron: "*/15 * * * *"
  workflow_dispatch:

permissions:
  contents: write

concurrency:
  group: bevakning
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Sök efter nya lägenheter
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: python -m bostad.main

      - name: Håll schemat vid liv (GitHub pausar efter 60 dagar utan commits)
        run: |
          last=$(git log -1 --format=%ct)
          if [ $(( $(date +%s) - last )) -gt 2592000 ]; then date -u +%FT%TZ > state/heartbeat.txt; fi

      - name: Spara tillstånd
        run: |
          git config user.name "bostadsbevakning[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add state/
          if git diff --cached --quiet; then exit 0; fi
          git commit -m "Uppdatera sedda annonser"
          git pull --rebase
          git push
```

- [ ] **Step 4: Write README.md**

```markdown
# Bostadsbevakning Varberg

Söker var 15:e minut efter lediga hyreslägenheter i Varberg, Veddige, Trönninge, Derome och
Åskloster hos Varbergs Bostad, Fortinova, Derome Fastighet och Qasa, och skickar en ntfy-notis
per ny annons.

- Filter (maxhyra, minsta antal rum, orter): `config.yaml`
- Redan skickade annonser: `state/seen.json` (töm `seen` för att få alla igen)
- ntfy-ämne: GitHub-secret `NTFY_TOPIC`
- Kör manuellt: fliken Actions → "Bevaka lägenheter" → Run workflow

Lokalt:

    python -m venv .venv
    .venv/Scripts/python -m pip install -r requirements.txt
    .venv/Scripts/python -m pytest
    .venv/Scripts/python -m bostad.main --dry-run
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/check.yml README.md
git commit -m "ci: run watcher every 15 minutes on GitHub Actions"
```

- [ ] **Step 6: Install and authenticate GitHub CLI**

Run: `winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements`
Expected: "Successfully installed". Then ask the user to run `! gh auth login` (interactive: GitHub.com → HTTPS → login with browser). Verify with `gh auth status` (new shell may be needed; full path `"C:\Program Files\GitHub CLI\gh.exe"`).

- [ ] **Step 7: Create public repo, set secret, push**

Confirm with the user before running (publishes code publicly):
```powershell
gh repo create varberg-bostad --public --source . --remote origin --push
Get-Content "$env:TEMP\ntfy-topic.txt" | gh secret set NTFY_TOPIC
```
Expected: repo URL printed; `gh secret list` shows `NTFY_TOPIC`.

- [ ] **Step 8: Trigger first run and verify**

```powershell
gh workflow run check.yml
gh run watch (gh run list --workflow check.yml --limit 1 --json databaseId -q ".[0].databaseId")
gh run view --log (gh run list --workflow check.yml --limit 1 --json databaseId -q ".[0].databaseId") | Select-String "annonser|misslyckades|Skickade"
git pull
```
Expected: run succeeds; log shows a count for each of the four sources and `Skickade N nya annonser`; matching notifications (if any) appear in ntfy; `state/seen.json` on GitHub contains N keys. If Qasa logs a 429 from GitHub's IP, report it to the user (spec risk).

- [ ] **Step 9: Verify a Qasa link opens**

Open one `https://qasa.se/sv/home/<id>` from the dry-run/live output in the browser and confirm it shows the listing. If it 404s, fix the URL format in `bostad/sources/qasa.py` and its test, rerun tests, commit, push.
