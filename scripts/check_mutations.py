"""Check that the test suite catches deliberately planted bugs (a small mutation test).

Each mutation below changes one rule in summary.py. The script applies them one at a
time, runs the tests, and restores the original file byte for byte afterwards. A
mutation that the tests do not catch means a rule is not really protected by a test.

Usage:  uv run python scripts/check_mutations.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "device_summary" / "summary.py"

# name -> (exact text in summary.py, replacement)
MUTATIONS = {
    "booleans accepted as sequence": (
        "isinstance(sequence, bool) or not isinstance(sequence, int)",
        "not isinstance(sequence, int)",
    ),
    "last status taken from last line, not highest sequence": (
        "elif record.sequence > state.last_sequence:",
        "else:",
    ),
    "duplicate keys not rejected": (
        "if isinstance(value, _ObjectWithDuplicateKeys):",
        "if False:",
    ),
    "duplicates never recorded": (
        "        seen.add(key)\n        accepted += 1",
        "        accepted += 1",
    ),
    "later duplicate replaces the first occurrence": (
        "            duplicates += 1\n            continue\n",
        "            duplicates += 1\n",
    ),
    "whitespace-only device_id accepted": (
        "not isinstance(device_id, str) or not device_id.strip()",
        "not isinstance(device_id, str) or not device_id",
    ),
    "extra fields allowed": ("if missing or unexpected:", "if missing:"),
    "NaN and Infinity accepted": (
        "object_pairs_hook=_build_object, parse_constant=_reject_constant",
        "object_pairs_hook=_build_object",
    ),
    "blank lines passed to the JSON parser": (
        '        raise _RejectedError(ErrorCode.BAD_JSON, "blank line")\n',
        "        pass\n",
    ),
    "BOM on line 1 not tolerated": ("        text = text.removeprefix(UTF8_BOM)\n", ""),
    "BOM stripped on every line": ("if line_number == 1:", "if True:"),
    "line ending passed to the parser": (
        'return text.removesuffix("\\n").removesuffix("\\r")',
        "return text",
    ),
    "invalid UTF-8 crashes": ("except UnicodeDecodeError:", "except KeyError:"),
    "deep nesting crashes": ("except RecursionError:", "except KeyError:"),
    "devices not sorted": (
        "for device_id, state in sorted(devices.items())",
        "for device_id, state in devices.items()",
    ),
}


def main() -> int:
    original_bytes = TARGET.read_bytes()
    original = original_bytes.decode("utf-8")
    for name, (before, _) in MUTATIONS.items():
        if original.count(before) != 1:
            print(f"mutation anchor not found exactly once: {name}")
            return 2

    missed = []
    try:
        for name, (before, after) in MUTATIONS.items():
            TARGET.write_bytes(original.replace(before, after).encode("utf-8"))
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--no-cov", "-q", "-x", "-p", "no:cacheprovider"],
                cwd=ROOT,
                capture_output=True,
                check=False,
            )
            caught = result.returncode != 0
            print(f"{'caught' if caught else 'MISSED'}  {name}")
            if not caught:
                missed.append(name)
    finally:
        TARGET.write_bytes(original_bytes)

    print(f"\n{len(MUTATIONS) - len(missed)}/{len(MUTATIONS)} planted bugs caught")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
