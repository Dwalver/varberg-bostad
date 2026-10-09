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
