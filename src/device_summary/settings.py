"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

SOURCE_ENV = "DEVICE_SUMMARY_FILE"
CORS_ORIGINS_ENV = "DEVICE_SUMMARY_CORS_ORIGINS"

# The sample shipped in the repository (src/device_summary/ -> repository root -> data/).
# This only resolves from a source checkout or an editable install (what uv, the README's
# pip instructions and the Dockerfile use); data/ is not packaged into a wheel, so a
# regular `pip install .` must set DEVICE_SUMMARY_FILE.
DEFAULT_SOURCE = Path(__file__).resolve().parents[2] / "data" / "sample.jsonl"


@dataclass(frozen=True)
class Settings:
    """Where to read input from, and which browser origins may call the API."""

    source: Path = DEFAULT_SOURCE
    cors_origins: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``environ`` (defaults to the process environment).

        DEVICE_SUMMARY_FILE: path of the JSON Lines file; defaults to the bundled sample.
        DEVICE_SUMMARY_CORS_ORIGINS: comma-separated origins allowed to call the API from a
        browser, e.g. "http://localhost:5173". Empty (the default) disables CORS.
        """
        env = os.environ if environ is None else environ
        source = env.get(SOURCE_ENV, "").strip()
        origins = tuple(
            origin.strip() for origin in env.get(CORS_ORIGINS_ENV, "").split(",") if origin.strip()
        )
        return cls(source=Path(source) if source else DEFAULT_SOURCE, cors_origins=origins)
