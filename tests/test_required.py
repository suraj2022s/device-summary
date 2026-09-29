"""The three tests the brief asks for, kept together so they are easy to find.

Error ``reason`` text is not part of the brief, so these tests compare line numbers and
codes only; the reasons are covered in test_lines.py and test_validation.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from device_summary import summarise_file, summarise_lines
from tests.helpers import SAMPLE_PATH, error_codes, record

# The brief's sample: D01/1 ok, the same record again, D02/2 error, one malformed line,
# then D01/3 error. The malformed line is a record with its closing brace missing.
SAMPLE_LINES = [
    record("D01", 1, "ok"),
    record("D01", 1, "ok"),
    record("D02", 2, "error"),
    '{"device_id": "D03", "sequence": 1, "status": "ok"',
    record("D01", 3, "error"),
]

EXPECTED_DEVICES = [
    {"device_id": "D01", "ok": 1, "error": 1, "last_sequence": 3, "last_status": "error"},
    {"device_id": "D02", "ok": 0, "error": 1, "last_sequence": 2, "last_status": "error"},
]


def _summarise_sample_lines() -> dict[str, Any]:
    return summarise_lines(SAMPLE_LINES).to_dict()


def _summarise_sample_file() -> dict[str, Any]:
    return summarise_file(SAMPLE_PATH).to_dict()


@pytest.mark.parametrize(
    "summarise",
    [_summarise_sample_lines, _summarise_sample_file],
    ids=["inline-lines", "shipped-sample-file"],
)
def test_sample_matches_expected_summary(summarise: Any) -> None:
    result = summarise()

    assert result["accepted"] == 3
    assert result["duplicates"] == 1
    assert error_codes(result) == [(4, "BAD_JSON")]
    assert result["devices"] == EXPECTED_DEVICES


def test_lower_sequence_arriving_later_does_not_replace_latest_status() -> None:
    result = summarise_lines(
        [
            record("D01", 5, "error"),
            record("D01", 2, "ok"),
        ]
    ).to_dict()

    assert result["accepted"] == 2
    assert result["devices"] == [
        {"device_id": "D01", "ok": 1, "error": 1, "last_sequence": 5, "last_status": "error"}
    ]


@pytest.mark.parametrize("source", ["no-lines", "empty-file"])
def test_empty_input_returns_zero_totals_and_empty_lists(source: str, tmp_path: Path) -> None:
    if source == "no-lines":
        result = summarise_lines([]).to_dict()
    else:
        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_bytes(b"")
        result = summarise_file(empty_file).to_dict()

    assert result == {"accepted": 0, "duplicates": 0, "errors": [], "devices": []}
