"""HTTP API: ``GET /summary`` returns the summary of the configured JSON Lines file.

Run locally with:  uv run uvicorn device_summary.api:app

Errors use RFC 9457 problem details (``application/problem+json``) everywhere, so a
client can tell a failure apart from a successful but empty summary.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from http import HTTPStatus
from importlib.metadata import version
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

from device_summary.settings import Settings
from device_summary.summary import ErrorCode, Status, summarise_file

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
SOURCE_UNAVAILABLE_TYPE = "https://github.com/suraj2022s/device-summary#source-unavailable"


class LineErrorModel(BaseModel):
    line: int
    code: ErrorCode
    reason: str


class DeviceModel(BaseModel):
    device_id: str
    ok: int
    error: int
    last_sequence: int
    last_status: Status


class SummaryModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "accepted": 3,
                    "duplicates": 1,
                    "errors": [
                        {
                            "line": 4,
                            "code": "BAD_JSON",
                            "reason": "malformed JSON: Expecting ',' delimiter at column 51",
                        }
                    ],
                    "devices": [
                        {
                            "device_id": "D01",
                            "ok": 1,
                            "error": 1,
                            "last_sequence": 3,
                            "last_status": "error",
                        },
                        {
                            "device_id": "D02",
                            "ok": 0,
                            "error": 1,
                            "last_sequence": 2,
                            "last_status": "error",
                        },
                    ],
                }
            ]
        }
    )

    accepted: int
    duplicates: int
    errors: list[LineErrorModel]
    devices: list[DeviceModel]


class ProblemModel(BaseModel):
    """RFC 9457 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class SourceUnavailableError(Exception):
    """The configured input file could not be opened or read."""

    def __init__(self, file_name: str) -> None:
        super().__init__(file_name)
        self.file_name = file_name


def problem_response(
    problem: ProblemModel, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    """Send ``problem`` as an ``application/problem+json`` response."""
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type=PROBLEM_JSON,
        headers=headers,
    )


def _problem_schema() -> dict[str, Any]:
    return {PROBLEM_JSON: {"schema": ProblemModel.model_json_schema()}}


def _status_phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:  # a code the standard library does not name, such as 499
        return "Error"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests pass explicit settings; otherwise the environment is read."""
    settings = settings or Settings.from_env()

    app = FastAPI(
        title="Device message summary",
        version=version("device-summary"),
        description="Summarises a JSON Lines file of simulated device messages.",
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET"],
        )

    @app.exception_handler(SourceUnavailableError)
    async def source_unavailable(request: Request, exc: SourceUnavailableError) -> JSONResponse:
        return problem_response(
            ProblemModel(
                type=SOURCE_UNAVAILABLE_TYPE,
                title="Summary source unavailable",
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                detail=f"The input file '{exc.file_name}' could not be read.",
                instance=request.url.path,
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = _status_phrase(exc.status_code)
        # FastAPI allows any JSON-serialisable detail; problem details need a string.
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        return problem_response(
            ProblemModel(
                title=title,
                status=exc.status_code,
                detail=detail if detail != title else None,
                instance=request.url.path,
            ),
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Starlette re-raises the exception after this response is sent, so the server
        # still logs the traceback; the client only gets a generic message.
        status = HTTPStatus.INTERNAL_SERVER_ERROR
        return problem_response(
            ProblemModel(title=status.phrase, status=status, instance=request.url.path)
        )

    @app.get("/health", summary="Liveness check")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/summary",
        response_model=SummaryModel,
        summary="Summarise the configured JSON Lines file",
        responses={
            500: {
                "description": "The input file could not be read (RFC 9457 problem details).",
                "content": _problem_schema(),
            }
        },
    )
    def get_summary() -> dict[str, Any]:
        # A plain (non-async) handler: FastAPI runs it in a worker thread, so the blocking
        # file read does not stall the event loop. The file is read on every request.
        try:
            summary = summarise_file(settings.source)
        except OSError as exc:
            # Full path and cause go to the server log only, never to the client.
            logger.error("Cannot read input file %s: %s", settings.source, exc)
            raise SourceUnavailableError(settings.source.name) from exc
        return summary.to_dict()

    return app


app = create_app()
