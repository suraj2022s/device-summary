"""Record validation (INVALID_RECORD), duplicates, ordering and sorting rules."""

from __future__ import annotations

import json
from typing import Any

import pytest

from device_summary import summarise_lines
from tests.helpers import error_codes, record

VALID = record("D01", 1, "ok")


def _fields(**overrides: Any) -> str:
    fields: dict[str, Any] = {"device_id": "D01", "sequence": 1, "status": "ok"}
    fields.update(overrides)
    return json.dumps(fields)


def _without(field: str) -> str:
    fields: dict[str, Any] = {"device_id": "D01", "sequence": 1, "status": "ok"}
    del fields[field]
    return json.dumps(fields)


@pytest.mark.parametrize(
    ("line", "reason"),
    [
        pytest.param("[1, 2]", "expected a JSON object, got array", id="array"),
        pytest.param('"D01"', "expected a JSON object, got string", id="string"),
        pytest.param("42", "expected a JSON object, got number", id="number"),
        pytest.param("null", "expected a JSON object, got null", id="null"),
        pytest.param("true", "expected a JSON object, got boolean", id="boolean"),
        pytest.param("{}", "missing fields ['device_id', 'sequence', 'status']", id="empty-object"),
        pytest.param(_without("status"), "missing fields ['status']", id="missing-status"),
        pytest.param(_fields(note="x"), "unexpected fields ['note']", id="extra-field"),
        pytest.param(
            json.dumps({"device_id": "D01", "sequence": 1, "extra": 1}),
            "missing fields ['status']; unexpected fields ['extra']",
            id="missing-and-extra",
        ),
        pytest.param(
            '{"device_id": "D01", "sequence": 1, "sequence": 2, "status": "ok"}',
            "duplicate key 'sequence'",
            id="duplicate-key",
        ),
        pytest.param(_fields(device_id=""), "device_id must be", id="device-id-empty"),
        pytest.param(_fields(device_id="   "), "device_id must be", id="device-id-spaces"),
        pytest.param(_fields(device_id="\t\n"), "device_id must be", id="device-id-tab-newline"),
        pytest.param(_fields(device_id=7), "device_id must be", id="device-id-number"),
        pytest.param(_fields(device_id=None), "device_id must be", id="device-id-null"),
        pytest.param(_fields(device_id=["D01"]), "device_id must be", id="device-id-array"),
        pytest.param(_fields(sequence=True), "sequence must be", id="sequence-true"),
        pytest.param(_fields(sequence=False), "sequence must be", id="sequence-false"),
        pytest.param(_fields(sequence=-1), "sequence must be", id="sequence-negative"),
        pytest.param(_fields(sequence=1.0), "sequence must be", id="sequence-float-whole"),
        pytest.param(_fields(sequence=1.5), "sequence must be", id="sequence-float"),
        pytest.param(_fields(sequence="1"), "sequence must be", id="sequence-string"),
        pytest.param(_fields(sequence=None), "sequence must be", id="sequence-null"),
        pytest.param(
            '{"device_id": "D01", "sequence": 1e2, "status": "ok"}',
            "sequence must be",
            id="sequence-exponent",
        ),
        pytest.param(_fields(status="OK"), "status must be", id="status-uppercase"),
        pytest.param(_fields(status=" ok"), "status must be", id="status-padded"),
        pytest.param(_fields(status="failed"), "status must be", id="status-unknown"),
        pytest.param(_fields(status=""), "status must be", id="status-empty"),
        pytest.param(_fields(status=None), "status must be", id="status-null"),
        pytest.param(_fields(status=1), "status must be", id="status-number"),
    ],
)
def test_invalid_record_is_reported_and_processing_continues(line: str, reason: str) -> None:
    result = summarise_lines([line, VALID]).to_dict()

    assert error_codes(result) == [(1, "INVALID_RECORD")]
    assert result["errors"][0]["reason"].startswith(reason)
    assert result["accepted"] == 1


@pytest.mark.parametrize(
    ("line", "device_id", "sequence"),
    [
        pytest.param(record("D01", 0, "ok"), "D01", 0, id="sequence-zero"),
        pytest.param('{"device_id": "D01", "sequence": -0, "status": "ok"}', "D01", 0, id="minus-0"),
        pytest.param(record("D01", 2**70, "ok"), "D01", 2**70, id="sequence-huge"),
        pytest.param(record(" D01 ", 1, "ok"), " D01 ", 1, id="device-id-kept-with-spaces"),
        pytest.param(record("设备-1", 1, "ok"), "设备-1", 1, id="device-id-unicode"),
        pytest.param(
            '{"status": "ok", "sequence": 1, "device_id": "D01"}', "D01", 1, id="field-order"
        ),
    ],
)
def test_valid_edge_cases_are_accepted_as_supplied(
    line: str, device_id: str, sequence: int
) -> None:
    result = summarise_lines([line]).to_dict()

    assert result["errors"] == []
    assert result["accepted"] == 1
    assert result["devices"] == [
        {
            "device_id": device_id,
            "ok": 1,
            "error": 0,
            "last_sequence": sequence,
            "last_status": "ok",
        }
    ]


def test_duplicate_with_different_status_is_counted_and_first_occurrence_wins() -> None:
    result = summarise_lines([record("D01", 1, "ok"), record("D01", 1, "error")]).to_dict()

    assert result["accepted"] == 1
    assert result["duplicates"] == 1
    assert result["devices"] == [
        {"device_id": "D01", "ok": 1, "error": 0, "last_sequence": 1, "last_status": "ok"}
    ]


def test_validation_happens_before_duplicate_checking() -> None:
    # The invalid first line must not claim the (D01, 1) pair.
    result = summarise_lines([record("D01", 1, "OK"), record("D01", 1, "error")]).to_dict()

    assert error_codes(result) == [(1, "INVALID_RECORD")]
    assert result["accepted"] == 1
    assert result["duplicates"] == 0


def test_invalid_repeat_of_an_accepted_record_is_an_error_not_a_duplicate() -> None:
    result = summarise_lines([record("D01", 1, "ok"), record("D01", 1, "OK")]).to_dict()

    assert error_codes(result) == [(2, "INVALID_RECORD")]
    assert result["duplicates"] == 0


def test_device_ids_are_compared_exactly_as_supplied() -> None:
    result = summarise_lines([record("D01", 1, "ok"), record(" D01", 1, "ok")]).to_dict()

    assert result["accepted"] == 2
    assert result["duplicates"] == 0
    assert [device["device_id"] for device in result["devices"]] == [" D01", "D01"]


def test_same_sequence_on_different_devices_is_not_a_duplicate() -> None:
    result = summarise_lines([record("D01", 1, "ok"), record("D02", 1, "ok")]).to_dict()

    assert result["accepted"] == 2
    assert result["duplicates"] == 0


def test_devices_are_sorted_by_device_id() -> None:
    result = summarise_lines(
        [record("D10", 1, "ok"), record("d01", 1, "ok"), record("D02", 1, "ok")]
    ).to_dict()

    # Plain code point order: uppercase letters sort before lowercase ones.
    assert [device["device_id"] for device in result["devices"]] == ["D02", "D10", "d01"]


def test_latest_status_follows_highest_sequence_across_out_of_order_input() -> None:
    result = summarise_lines(
        [
            record("D01", 2, "ok"),
            record("D01", 7, "error"),
            record("D01", 3, "ok"),
            record("D01", 9, "ok"),
            record("D01", 8, "error"),
        ]
    ).to_dict()

    assert result["devices"] == [
        {"device_id": "D01", "ok": 3, "error": 2, "last_sequence": 9, "last_status": "ok"}
    ]
