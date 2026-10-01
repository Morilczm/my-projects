import pytest

from scripts.formal_document_alignment_api_e2e_support import (
    PollingTimeout,
    poll_until_terminal,
)


def test_polling_accepts_fast_terminal_and_stops_immediately():
    calls = []

    def fetch():
        calls.append("fetch")
        return {"data": {"status": "ready_for_review"}}

    result = poll_until_terminal(fetch, timeout_seconds=1, poll_interval_seconds=0)

    assert result.terminal_status == "ready_for_review"
    assert result.timeline == ("ready_for_review",)
    assert calls == ["fetch"]


def test_polling_records_monotonic_status_timeline():
    states = iter(("queued", "validating", "processing", "completed_with_warnings"))

    result = poll_until_terminal(
        lambda: {"data": {"status": next(states)}},
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert result.timeline == (
        "queued",
        "validating",
        "processing",
        "completed_with_warnings",
    )


def test_polling_rejects_status_regression():
    states = iter(("processing", "validating"))

    with pytest.raises(AssertionError, match="regressed"):
        poll_until_terminal(
            lambda: {"data": {"status": next(states)}},
            timeout_seconds=1,
            poll_interval_seconds=0,
        )


def test_polling_times_out_instead_of_looping_forever():
    with pytest.raises(PollingTimeout):
        poll_until_terminal(
            lambda: {"data": {"status": "processing"}},
            timeout_seconds=0,
            poll_interval_seconds=0,
        )
