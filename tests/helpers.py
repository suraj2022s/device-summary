"""Shared test helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample.jsonl"


def record(device_id: Any, sequence: Any, status: Any) -> str:
    """Return one JSON Lines record with exactly the three required fields."""
    return json.dumps({"device_id": device_id, "sequence": sequence, "status": status})


def error_codes(result: dict[str, Any]) -> list[tuple[int, str]]:
    """Return the (line, code) pairs of a summary's errors, in order."""
    return [(error["line"], error["code"]) for error in result["errors"]]
