"""Command line interface."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest

from device_summary.cli import main
from tests.helpers import SAMPLE_PATH


def test_cli_prints_the_summary_as_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(SAMPLE_PATH)])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["accepted"] == 3
    assert output["duplicates"] == 1


def test_cli_reports_an_unreadable_file_and_exits_with_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(tmp_path / "missing.jsonl")])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "cannot read" in captured.err


def test_python_dash_m_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["device_summary", str(SAMPLE_PATH)])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("device_summary", run_name="__main__")

    assert exit_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["accepted"] == 3
