"""Property-based tests: rules that must hold for any input, checked with Hypothesis.

Inputs mix valid records drawn from small pools (so duplicates and out-of-order sequences
are common) with known-bad lines. The expected result is computed by a deliberately
simple reference model and compared with the real implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from device_summary import summarise_lines
from tests.helpers import record

BAD_LINES = [
    "",
    "   ",
    "{",
    "not json",
    '{"device_id": "D01", "sequence": NaN, "status": "ok"}',
]
INVALID_LINES = [
    "[]",
    "null",
    record("", 1, "ok"),
    record("D01", -1, "ok"),
    record("D01", True, "ok"),
    record("D01", 1, "OK"),
]
DEVICE_IDS = ["D01", "D02", " D01", "d01", "设备"]


@dataclass(frozen=True)
class Valid:
    device_id: str
    sequence: int
    status: str

    def line(self) -> str:
        return record(self.device_id, self.sequence, self.status)


@dataclass(frozen=True)
class Bad:
    line: str
    code: str


valid_records = st.builds(
    Valid,
    device_id=st.sampled_from(DEVICE_IDS),
    sequence=st.integers(min_value=0, max_value=6),
    status=st.sampled_from(["ok", "error"]),
)
bad_lines = st.one_of(
    st.sampled_from(BAD_LINES).map(lambda line: Bad(line, "BAD_JSON")),
    st.sampled_from(INVALID_LINES).map(lambda line: Bad(line, "INVALID_RECORD")),
)
inputs = st.lists(st.one_of(valid_records, valid_records, bad_lines), max_size=40)


def _as_lines(items: list[Valid | Bad]) -> list[str]:
    return [item.line() if isinstance(item, Valid) else item.line for item in items]


def _reference_model(items: list[Valid | Bad]) -> dict[str, Any]:
    """Straightforward restatement of the brief, used as the expected result."""
    first_seen: dict[tuple[str, int], Valid] = {}
    duplicates = 0
    errors = []
    for line_number, item in enumerate(items, start=1):
        if isinstance(item, Bad):
            errors.append((line_number, item.code))
        elif (item.device_id, item.sequence) in first_seen:
            duplicates += 1
        else:
            first_seen[(item.device_id, item.sequence)] = item

    devices = []
    for device_id in sorted({item.device_id for item in first_seen.values()}):
        accepted = [item for item in first_seen.values() if item.device_id == device_id]
        latest = max(accepted, key=lambda item: item.sequence)
        devices.append(
            {
                "device_id": device_id,
                "ok": sum(item.status == "ok" for item in accepted),
                "error": sum(item.status == "error" for item in accepted),
                "last_sequence": latest.sequence,
                "last_status": latest.status,
            }
        )
    return {
        "accepted": len(first_seen),
        "duplicates": duplicates,
        "errors": errors,
        "devices": devices,
    }


@given(inputs)
def test_summary_matches_reference_model(items: list[Valid | Bad]) -> None:
    result = summarise_lines(_as_lines(items)).to_dict()
    result["errors"] = [(error["line"], error["code"]) for error in result["errors"]]

    assert result == _reference_model(items)


@given(inputs)
def test_every_line_is_counted_exactly_once(items: list[Valid | Bad]) -> None:
    result = summarise_lines(_as_lines(items)).to_dict()

    assert result["accepted"] + result["duplicates"] + len(result["errors"]) == len(items)
    assert sum(device["ok"] + device["error"] for device in result["devices"]) == (
        result["accepted"]
    )


@given(inputs)
def test_errors_are_in_strictly_increasing_line_order(items: list[Valid | Bad]) -> None:
    lines = [error["line"] for error in summarise_lines(_as_lines(items)).to_dict()["errors"]]

    assert lines == sorted(set(lines))
    assert all(1 <= line <= len(items) for line in lines)


@given(st.lists(valid_records, unique_by=lambda item: (item.device_id, item.sequence)), st.data())
def test_input_order_does_not_change_device_summaries(
    items: list[Valid], data: st.DataObject
) -> None:
    shuffled = data.draw(st.permutations(items))

    original = summarise_lines([item.line() for item in items]).to_dict()
    reordered = summarise_lines([item.line() for item in shuffled]).to_dict()

    assert reordered == original
