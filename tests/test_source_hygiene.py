"""Guard against invisible characters in source files.

A byte order mark (U+FEFF) written as a literal character once slipped into summary.py,
where it looks exactly like an empty string on screen. This test keeps invisible and
formatting characters out of the code; visible non-ASCII test data is fine.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = sorted([*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/**/*.py")])
ALLOWED_CONTROL_CHARACTERS = {"\n", "\t"}
# Control, format, line/paragraph separator, private-use, surrogate and unassigned.
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"}


def _describe(text: str, index: int) -> str:
    char = text[index]
    line = text.count("\n", 0, index) + 1
    return f"line {line}: U+{ord(char):04X} {unicodedata.name(char, 'UNNAMED')}"


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_source_file_has_no_invisible_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    found = [
        _describe(text, index)
        for index, char in enumerate(text)
        if char not in ALLOWED_CONTROL_CHARACTERS
        and unicodedata.category(char) in INVISIBLE_CATEGORIES
    ]

    assert found == []
