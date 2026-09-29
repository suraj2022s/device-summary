"""Guard against invisible characters in the repository's text files.

A byte order mark (U+FEFF) written as a raw character once slipped into summary.py,
where it looks exactly like an empty string on screen, and the same thing later happened
in the documentation. This test keeps invisible and formatting characters out of every
text file; visible non-ASCII characters (test data, typography) are fine.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TEXT_FILE_PATTERNS = [
    "src/**/*.py",
    "tests/**/*.py",
    "scripts/**/*.py",
    "*.md",
    "docs/**/*.md",
    "*.toml",
    "data/**/*.jsonl",
    ".github/**/*.yml",
    "Dockerfile",
    ".dockerignore",
    ".gitattributes",
    ".gitignore",
    ".python-version",
]
TEXT_FILES = sorted({path for pattern in TEXT_FILE_PATTERNS for path in ROOT.glob(pattern)})
ALLOWED_CONTROL_CHARACTERS = {"\n", "\t"}
# Control, format, line/paragraph separator, private-use, surrogate and unassigned.
INVISIBLE_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Co", "Cs", "Cn"}


def _describe(text: str, index: int) -> str:
    char = text[index]
    line = text.count("\n", 0, index) + 1
    return f"line {line}: U+{ord(char):04X} {unicodedata.name(char, 'UNNAMED')}"


def test_text_files_are_found() -> None:
    names = {path.name for path in TEXT_FILES}
    assert {"summary.py", "README.md", "pyproject.toml", "sample.jsonl", "ci.yml"} <= names


@pytest.mark.parametrize("path", TEXT_FILES, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_text_file_has_no_invisible_characters(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    found = [
        _describe(text, index)
        for index, char in enumerate(text)
        if char not in ALLOWED_CONTROL_CHARACTERS
        and unicodedata.category(char) in INVISIBLE_CATEGORIES
    ]

    assert found == []
