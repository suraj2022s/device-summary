"""Line handling: encodings, line endings, blank lines and malformed JSON (BAD_JSON)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

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


def test_malformed_json_reason_does_not_repeat_at() -> None:
    # Regression test: Python's message "Unterminated string starting at" used to be
    # followed by " at column 21", giving "starting at at column 21".
    result = summarise_lines(['{"device_id": "P1", "sequen']).to_dict()

    assert result["errors"][0]["reason"] == (
        "malformed JSON: Unterminated string starting at column 21"
    )


@pytest.mark.parametrize("line_ending", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_malformed_json_reason_points_at_the_real_column(
    line_ending: bytes, tmp_path: Path
) -> None:
    # Regression test: the line ending used to be passed to the parser, which then
    # reported an error at the end of the line as "column 1" (of an imaginary line 2).
    truncated = '{"device_id": "D03", "sequence": 1, "status": "ok"'
    path = tmp_path / "truncated.jsonl"
    path.write_bytes(truncated.encode() + line_ending)

    result = summarise_file(path).to_dict()

    assert result["errors"][0]["reason"] == (
        f"malformed JSON: Expecting ',' delimiter at column {len(truncated) + 1}"
    )


def test_parser_recursion_error_is_bad_json_and_processing_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulated, because whether a given depth really exhausts the parser depends on the
    # Python version and the platform's stack size (see the next test).
    real_loads = json.loads

    def loads(text: str, **kwargs: Any) -> Any:
        if text.startswith("["):
            raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")
        return real_loads(text, **kwargs)

    monkeypatch.setattr(json, "loads", loads)

    result = summarise_lines(["[[[]]]", VALID]).to_dict()

    assert error_codes(result) == [(1, "BAD_JSON")]
    assert result["errors"][0]["reason"] == "JSON is nested too deeply"
    assert result["accepted"] == 1


def test_deeply_nested_json_is_rejected_without_stopping_processing() -> None:
    # CPython raises RecursionError for this depth on some platforms (-> BAD_JSON) and
    # parses it on others, e.g. Python 3.14 on Linux, where the array is then rejected
    # because it is not an object (-> INVALID_RECORD). Either way it is rejected and the
    # next line is still processed.
    deep = "[" * 100_000 + "]" * 100_000

    result = summarise_lines([deep, VALID]).to_dict()

    assert [line for line, _ in error_codes(result)] == [1]
    assert error_codes(result)[0][1] in {"BAD_JSON", "INVALID_RECORD"}
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
    device_id = "D\N{LINE SEPARATOR}01"
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
