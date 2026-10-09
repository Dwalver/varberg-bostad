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
