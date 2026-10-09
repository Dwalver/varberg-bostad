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
