"""Core logic: validate device messages line by line and build a summary.

Nothing here depends on the web framework, so the rules can be tested on their own.
Each line goes through three steps, and the first step that fails decides its error code:

1. decode  - bytes to text; invalid UTF-8 is BAD_JSON
2. parse   - text to a JSON value; blank lines and malformed JSON are BAD_JSON
3. validate - JSON value to a record; anything that is not a valid record is INVALID_RECORD

Valid records are then deduplicated on (device_id, sequence) and aggregated per device.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from os import PathLike
from typing import Any, Literal

Status = Literal["ok", "error"]

REQUIRED_FIELDS = frozenset({"device_id", "sequence", "status"})
VALID_STATUSES = frozenset({"ok", "error"})
UTF8_BOM = "﻿"


class ErrorCode(StrEnum):
    """Why a line was rejected."""

    BAD_JSON = "BAD_JSON"
    INVALID_RECORD = "INVALID_RECORD"


@dataclass(frozen=True, slots=True)
class LineError:
    """A rejected input line. ``line`` is 1-based."""

    line: int
    code: ErrorCode
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "code": self.code.value, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class DeviceSummary:
    """Totals for one device, computed from accepted records only."""

    device_id: str
    ok: int
    error: int
    last_sequence: int
    last_status: Status

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "ok": self.ok,
            "error": self.error,
            "last_sequence": self.last_sequence,
            "last_status": self.last_status,
        }


@dataclass(frozen=True, slots=True)
class Summary:
    """The result of processing one input."""

    accepted: int = 0
    duplicates: int = 0
    errors: tuple[LineError, ...] = ()
    devices: tuple[DeviceSummary, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "errors": [error.to_dict() for error in self.errors],
            "devices": [device.to_dict() for device in self.devices],
        }


@dataclass(frozen=True, slots=True)
class _Record:
    device_id: str
    sequence: int
    status: Status


@dataclass(slots=True)
class _DeviceState:
    last_sequence: int
    last_status: Status
    ok: int = 0
    error: int = 0


class _RejectedError(Exception):
    """Internal signal that a line failed a step; carries the error code and reason."""

    def __init__(self, code: ErrorCode, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class _ObjectWithDuplicateKeys(dict[str, Any]):
    """A parsed JSON object that repeated a key.

    Python's json module keeps the last value of a repeated key without telling us. We
    flag the object instead of raising during parsing, so that a line which is also
    syntactically broken is still reported as BAD_JSON rather than INVALID_RECORD.
    """

    def __init__(self, pairs: list[tuple[str, Any]], duplicate_key: str) -> None:
        super().__init__(pairs)
        self.duplicate_key = duplicate_key


def _build_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    for key, _ in pairs:
        if key in seen:
            return _ObjectWithDuplicateKeys(pairs, duplicate_key=key)
        seen.add(key)
    return dict(pairs)


def _reject_constant(name: str) -> Any:
    raise _RejectedError(ErrorCode.BAD_JSON, f"non-standard JSON constant {name}")


def _decode(raw: str | bytes, line_number: int) -> str:
    """Step 1: return the line as text.

    The trailing "\\n" or "\\r\\n" is left in place: JSON ignores surrounding whitespace,
    and the blank-line check below strips it.
    """
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise _RejectedError(ErrorCode.BAD_JSON, "line is not valid UTF-8") from None
    else:
        text = raw
    if line_number == 1:
        # JSON Lines forbids a byte order mark, but some Windows editors add one.
        text = text.removeprefix(UTF8_BOM)
    return text


def _parse(text: str) -> Any:
    """Step 2: parse one line of strict JSON (RFC 8259, no NaN or Infinity)."""
    if not text.strip():
        raise _RejectedError(ErrorCode.BAD_JSON, "blank line")
    try:
        return json.loads(text, object_pairs_hook=_build_object, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        reason = f"malformed JSON: {exc.msg} at column {exc.colno}"
        raise _RejectedError(ErrorCode.BAD_JSON, reason) from None
    except RecursionError:
        raise _RejectedError(ErrorCode.BAD_JSON, "JSON is nested too deeply") from None
    except ValueError:
        # Syntactically valid JSON that Python cannot convert, such as an integer longer
        # than the interpreter's integer string conversion limit (4300 digits by default).
        raise _RejectedError(ErrorCode.BAD_JSON, "JSON number is too long to convert") from None


def _validate(value: Any) -> _Record:
    """Step 3: check the parsed value is a record with exactly the required fields."""

    def invalid(reason: str) -> _RejectedError:
        return _RejectedError(ErrorCode.INVALID_RECORD, reason)

    if not isinstance(value, dict):
        raise invalid(f"expected a JSON object, got {_json_type_name(value)}")
    if isinstance(value, _ObjectWithDuplicateKeys):
        raise invalid(f"duplicate key {value.duplicate_key!r}")

    missing = REQUIRED_FIELDS - value.keys()
    unexpected = value.keys() - REQUIRED_FIELDS
    if missing or unexpected:
        problems = []
        if missing:
            problems.append(f"missing fields {sorted(missing)}")
        if unexpected:
            problems.append(f"unexpected fields {sorted(unexpected)}")
        raise invalid("; ".join(problems))

    device_id = value["device_id"]
    if not isinstance(device_id, str) or not device_id.strip():
        raise invalid("device_id must be a non-empty string that is not only whitespace")

    sequence = value["sequence"]
    # bool is a subclass of int in Python, so it has to be excluded explicitly.
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
        raise invalid("sequence must be an integer greater than or equal to 0")

    status = value["status"]
    if status not in VALID_STATUSES:
        raise invalid("status must be 'ok' or 'error'")

    return _Record(device_id=device_id, sequence=sequence, status=status)


def _json_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "number"


def summarise_lines(lines: Iterable[str | bytes]) -> Summary:
    """Build a summary from JSON Lines input.

    Each item is one line, with or without its trailing line ending; bytes are decoded as
    UTF-8. Lines are processed independently and processing always continues after an
    error. For each (device_id, sequence) pair only the first valid record is accepted;
    later ones count as duplicates even if their status differs. A device's last status
    comes from its highest accepted sequence, regardless of input order.
    """
    errors: list[LineError] = []
    seen: set[tuple[str, int]] = set()
    devices: dict[str, _DeviceState] = {}
    accepted = 0
    duplicates = 0

    for line_number, raw in enumerate(lines, start=1):
        try:
            record = _validate(_parse(_decode(raw, line_number)))
        except _RejectedError as rejected:
            errors.append(LineError(line_number, rejected.code, rejected.reason))
            continue

        key = (record.device_id, record.sequence)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        accepted += 1

        state = devices.get(record.device_id)
        if state is None:
            state = devices[record.device_id] = _DeviceState(record.sequence, record.status)
        elif record.sequence > state.last_sequence:
            # Accepted sequences are unique per device, so there are never ties.
            state.last_sequence = record.sequence
            state.last_status = record.status
        if record.status == "ok":
            state.ok += 1
        else:
            state.error += 1

    return Summary(
        accepted=accepted,
        duplicates=duplicates,
        errors=tuple(errors),
        devices=tuple(
            DeviceSummary(
                device_id=device_id,
                ok=state.ok,
                error=state.error,
                last_sequence=state.last_sequence,
                last_status=state.last_status,
            )
            for device_id, state in sorted(devices.items())
        ),
    )


def summarise_file(path: str | PathLike[str]) -> Summary:
    """Summarise a JSON Lines file.

    The file is read as a binary stream and split on ``\\n`` only, so a line separator
    character inside a JSON string (such as U+2028) does not split a record, and memory
    use does not grow with line count beyond the per-device and duplicate-tracking state.
    Raises OSError if the file cannot be opened or read.
    """
    with open(path, "rb") as handle:
        return summarise_lines(handle)
