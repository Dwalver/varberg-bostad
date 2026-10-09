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
