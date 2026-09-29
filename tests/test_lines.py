"""Line handling: encodings, line endings, blank lines and malformed JSON (BAD_JSON)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from device_summary import summarise_file, summarise_lines
from tests.helpers import error_codes, record

VALID = record("D01", 1, "ok")


def _too_long_number() -> str:
    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("integer string conversion limit is disabled in this interpreter")
    return "1" * (limit + 1)


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        pytest.param("", "blank line", id="empty"),
        pytest.param("  \t ", "blank line", id="whitespace-only"),
        pytest.param(b"\n", "blank line", id="newline-only"),
        pytest.param(b"\r\n", "blank line", id="crlf-only"),
        pytest.param(b'{"device_id": "\xff"}', "line is not valid UTF-8", id="invalid-utf8"),
        pytest.param("not json", "malformed JSON: Expecting value at column 1", id="not-json"),
        pytest.param(
            '{"device_id": "D01", "sequence": 1, "status": "ok"',
            "malformed JSON",
            id="truncated-object",
        ),
        pytest.param(VALID + " trailing", "malformed JSON", id="trailing-garbage"),
        pytest.param(VALID + VALID, "malformed JSON", id="two-records-on-one-line"),
        pytest.param("{'device_id': 'D01'}", "malformed JSON", id="single-quotes"),
        pytest.param(
            '{"device_id": "D01", "sequence": NaN, "status": "ok"}',
            "non-standard JSON constant NaN",
            id="nan",
        ),
        pytest.param(
            '{"device_id": "D01", "sequence": Infinity, "status": "ok"}',
            "non-standard JSON constant Infinity",
            id="infinity",
        ),
        pytest.param("-Infinity", "non-standard JSON constant -Infinity", id="negative-infinity"),
        pytest.param("[" * 100_000 + "]" * 100_000, "JSON is nested too deeply", id="deep-nesting"),
        pytest.param(
            # The object repeats a key, but the line as a whole is not valid JSON, so the
            # syntax error wins: BAD_JSON, not INVALID_RECORD.
            '{"sequence": 1, "sequence": 2} trailing',
            "malformed JSON",
            id="duplicate-key-and-broken-syntax",
        ),
    ],
)
def test_bad_json_is_reported_and_processing_continues(line: str | bytes, reason: str) -> None:
    result = summarise_lines([line, VALID]).to_dict()

    assert error_codes(result) == [(1, "BAD_JSON")]
    assert result["errors"][0]["reason"].startswith(reason)
    assert result["accepted"] == 1


def test_number_too_long_to_convert_is_bad_json() -> None:
    line = f'{{"device_id": "D01", "sequence": {_too_long_number()}, "status": "ok"}}'

    result = summarise_lines([line, VALID]).to_dict()

    assert error_codes(result) == [(1, "BAD_JSON")]
    assert result["errors"][0]["reason"] == "JSON number is too long to convert"
    assert result["accepted"] == 1


def test_byte_order_mark_is_accepted_on_the_first_line_only(tmp_path: Path) -> None:
    path = tmp_path / "bom.jsonl"
    path.write_bytes(
        b"\xef\xbb\xbf" + record("D01", 1, "ok").encode() + b"\n"
        b"\xef\xbb\xbf" + record("D01", 2, "ok").encode() + b"\n"
    )

    result = summarise_file(path).to_dict()

    assert result["accepted"] == 1
    assert error_codes(result) == [(2, "BAD_JSON")]


def test_crlf_line_endings_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "crlf.jsonl"
    path.write_bytes(
        (record("D01", 1, "ok") + "\r\n" + record("D01", 2, "error") + "\r\n").encode()
    )

    result = summarise_file(path).to_dict()

    assert result["accepted"] == 2
    assert result["errors"] == []


def test_last_line_without_newline_is_processed(tmp_path: Path) -> None:
    path = tmp_path / "no-final-newline.jsonl"
    path.write_text(record("D01", 1, "ok") + "\n" + record("D01", 2, "error"), encoding="utf-8")

    result = summarise_file(path).to_dict()

    assert result["accepted"] == 2


def test_extra_blank_line_at_end_of_file_is_bad_json(tmp_path: Path) -> None:
    path = tmp_path / "extra-newline.jsonl"
    path.write_text(record("D01", 1, "ok") + "\n\n", encoding="utf-8")

    result = summarise_file(path).to_dict()

    assert result["accepted"] == 1
    assert error_codes(result) == [(2, "BAD_JSON")]


def test_unicode_line_separator_inside_a_string_does_not_split_the_line(tmp_path: Path) -> None:
    # str.splitlines() would split on U+2028; JSON Lines only splits on "\n".
    device_id = "D 01"
    line = json.dumps({"device_id": device_id, "sequence": 1, "status": "ok"}, ensure_ascii=False)
    path = tmp_path / "separator.jsonl"
    path.write_text(line + "\n", encoding="utf-8")

    result = summarise_file(path).to_dict()

    assert result["errors"] == []
    assert [device["device_id"] for device in result["devices"]] == [device_id]


def test_every_error_is_recorded_with_its_line_number_in_order() -> None:
    result = summarise_lines(
        [
            "",
            VALID,
            "{",
            record("D01", -1, "ok"),
            record("D01", 1, "ok"),
            "[]",
        ]
    ).to_dict()

    assert error_codes(result) == [
        (1, "BAD_JSON"),
        (3, "BAD_JSON"),
        (4, "INVALID_RECORD"),
        (6, "INVALID_RECORD"),
    ]
    assert result["accepted"] == 1
    assert result["duplicates"] == 1
