"""Command line entry point: print the summary of a JSON Lines file as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from device_summary.summary import summarise_file


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI. Returns 0 on success and 1 if the file cannot be read."""
    parser = argparse.ArgumentParser(
        prog="device-summary",
        description="Summarise a JSON Lines file of device messages and print it as JSON.",
    )
    parser.add_argument("path", help="path to the .jsonl input file")
    args = parser.parse_args(argv)

    try:
        summary = summarise_file(args.path)
    except OSError as exc:
        print(f"error: cannot read {args.path}: {exc.strerror or exc}", file=sys.stderr)
        return 1

    # ensure_ascii (the default) keeps output printable on any console encoding.
    print(json.dumps(summary.to_dict(), indent=2))
    return 0
