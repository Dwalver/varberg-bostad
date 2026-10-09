from bostad.state import State, load_state, save_state


def test_missing_file_gives_empty_state(tmp_path):
    state = load_state(str(tmp_path / "nope.json"))
    assert state == State(seen={}, failures={})


def test_round_trip(tmp_path):
    path = str(tmp_path / "state" / "seen.json")
    save_state(State(seen={"qasa:1": "2026-10-09T10:00:00+00:00"}, failures={"derome": 2}), path)
    assert load_state(path) == State(seen={"qasa:1": "2026-10-09T10:00:00+00:00"}, failures={"derome": 2})
