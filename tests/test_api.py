"""HTTP API behaviour: the summary endpoint, error responses and configuration."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from device_summary.api import PROBLEM_JSON, SOURCE_UNAVAILABLE_TYPE, create_app
from device_summary.settings import DEFAULT_SOURCE, SOURCE_ENV, Settings
from tests.helpers import SAMPLE_PATH, error_codes, record


def _client(source: Path, cors_origins: tuple[str, ...] = ()) -> TestClient:
    return TestClient(create_app(Settings(source=source, cors_origins=cors_origins)))


def test_summary_returns_the_sample_result() -> None:
    response = _client(SAMPLE_PATH).get("/summary")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    assert body["accepted"] == 3
    assert body["duplicates"] == 1
    assert error_codes(body) == [(4, "BAD_JSON")]
    assert body["devices"] == [
        {"device_id": "D01", "ok": 1, "error": 1, "last_sequence": 3, "last_status": "error"},
        {"device_id": "D02", "ok": 0, "error": 1, "last_sequence": 2, "last_status": "error"},
    ]


def test_empty_file_is_a_successful_empty_summary(tmp_path: Path) -> None:
    source = tmp_path / "empty.jsonl"
    source.write_bytes(b"")

    response = _client(source).get("/summary")

    assert response.status_code == 200
    assert response.json() == {"accepted": 0, "duplicates": 0, "errors": [], "devices": []}


def test_file_is_read_again_on_every_request(tmp_path: Path) -> None:
    source = tmp_path / "live.jsonl"
    source.write_text(record("D01", 1, "ok") + "\n", encoding="utf-8")
    client = _client(source)
    assert client.get("/summary").json()["accepted"] == 1

    source.write_text(record("D01", 1, "ok") + "\n" + record("D01", 2, "ok") + "\n", "utf-8")

    assert client.get("/summary").json()["accepted"] == 2


def test_missing_file_returns_problem_details_not_an_empty_result(tmp_path: Path) -> None:
    response = _client(tmp_path / "missing.jsonl").get("/summary")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": SOURCE_UNAVAILABLE_TYPE,
        "title": "Summary source unavailable",
        "status": 500,
        "detail": "The input file 'missing.jsonl' could not be read.",
        "instance": "/summary",
    }


def test_directory_instead_of_file_returns_problem_details(tmp_path: Path) -> None:
    response = _client(tmp_path).get("/summary")

    assert response.status_code == 500
    assert response.json()["type"] == SOURCE_UNAVAILABLE_TYPE


def test_unreadable_file_is_logged_with_full_path_but_path_is_not_exposed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "missing.jsonl"

    with caplog.at_level(logging.ERROR, logger="device_summary.api"):
        response = _client(missing).get("/summary")

    assert str(missing) in caplog.text
    assert str(tmp_path) not in response.text


def test_unknown_route_returns_problem_details_404() -> None:
    response = _client(SAMPLE_PATH).get("/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "instance": "/does-not-exist",
    }


def test_wrong_method_returns_problem_details_405_with_allow_header() -> None:
    response = _client(SAMPLE_PATH).post("/summary")

    assert response.status_code == 405
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["allow"] == "GET"
    assert response.json()["title"] == "Method Not Allowed"


def test_http_exception_with_custom_detail_keeps_the_detail() -> None:
    app = create_app(Settings(source=SAMPLE_PATH))

    @app.get("/teapot")
    def teapot() -> None:
        raise HTTPException(status_code=418, detail="Short and stout.")

    response = TestClient(app).get("/teapot")

    assert response.status_code == 418
    assert response.json()["detail"] == "Short and stout."


@pytest.mark.parametrize(
    ("status_code", "detail", "title", "expected_detail"),
    [
        pytest.param(499, "Client closed request", "Error", "Client closed request", id="499"),
        pytest.param(400, {"field": "x"}, "Bad Request", '{"field": "x"}', id="dict-detail"),
    ],
)
def test_unusual_http_exceptions_still_return_problem_details(
    status_code: int, detail: object, title: str, expected_detail: str
) -> None:
    # Regression test: a status code the standard library does not name, or a non-string
    # detail, used to crash the error handler itself.
    app = create_app(Settings(source=SAMPLE_PATH))

    @app.get("/unusual")
    def unusual() -> None:
        raise HTTPException(status_code=status_code, detail=detail)

    response = TestClient(app, raise_server_exceptions=False).get("/unusual")

    assert response.status_code == status_code
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["title"] == title
    assert response.json()["detail"] == expected_detail


def test_unexpected_error_returns_generic_problem_without_internal_details() -> None:
    app = create_app(Settings(source=SAMPLE_PATH))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json() == {
        "type": "about:blank",
        "title": "Internal Server Error",
        "status": 500,
        "instance": "/boom",
    }
    assert "secret" not in response.text


def test_health_does_not_depend_on_the_input_file(tmp_path: Path) -> None:
    response = _client(tmp_path / "missing.jsonl").get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_is_off_by_default() -> None:
    response = _client(SAMPLE_PATH).get("/summary", headers={"Origin": "http://localhost:5173"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_a_configured_origin() -> None:
    client = _client(SAMPLE_PATH, cors_origins=("http://localhost:5173",))

    response = client.get("/summary", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_openapi_documents_summary_and_its_error_response() -> None:
    schema = _client(SAMPLE_PATH).get("/openapi.json").json()

    responses = schema["paths"]["/summary"]["get"]["responses"]
    assert "200" in responses
    assert PROBLEM_JSON in responses["500"]["content"]


def test_settings_are_read_from_the_environment() -> None:
    settings = Settings.from_env(
        {
            "DEVICE_SUMMARY_FILE": " other.jsonl ",
            "DEVICE_SUMMARY_CORS_ORIGINS": "http://a.test, http://b.test,,",
        }
    )

    assert settings == Settings(
        source=Path("other.jsonl"), cors_origins=("http://a.test", "http://b.test")
    )


def test_settings_default_to_the_bundled_sample_with_cors_off() -> None:
    assert Settings.from_env({}) == Settings(source=DEFAULT_SOURCE, cors_origins=())
    assert DEFAULT_SOURCE.resolve() == SAMPLE_PATH.resolve()


def test_create_app_without_settings_reads_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(SOURCE_ENV, str(tmp_path / "from-env.jsonl"))

    response = TestClient(create_app()).get("/summary")

    assert response.status_code == 500
    assert "from-env.jsonl" in response.json()["detail"]
