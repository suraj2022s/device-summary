# Device message summary

[![CI](https://github.com/suraj2022s/device-summary/actions/workflows/ci.yml/badge.svg)](https://github.com/suraj2022s/device-summary/actions/workflows/ci.yml)

Reads a JSON Lines file of simulated device messages, validates every line, removes
duplicates and returns a per-device summary as JSON, from `GET /summary` or the command
line. Built with Python and FastAPI; no database or hosting needed.

## Quick start

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs the
right Python version by itself.

```
uv sync --locked
uv run pytest
uv run uvicorn device_summary.api:app
```

Then open <http://127.0.0.1:8000/summary>. For the bundled sample it returns:

```json
{
  "accepted": 3,
  "duplicates": 1,
  "errors": [
    {"line": 4, "code": "BAD_JSON", "reason": "malformed JSON: Expecting ',' delimiter at column 51"}
  ],
  "devices": [
    {"device_id": "D01", "ok": 1, "error": 1, "last_sequence": 3, "last_status": "error"},
    {"device_id": "D02", "ok": 0, "error": 1, "last_sequence": 2, "last_status": "error"}
  ]
}
```

Interactive API docs are at <http://127.0.0.1:8000/docs>.

## Where to look

| Path | What it is |
|---|---|
| [src/device_summary/summary.py](src/device_summary/summary.py) | All the rules: decode, parse, validate, deduplicate, aggregate. No web code. |
| [src/device_summary/api.py](src/device_summary/api.py) | FastAPI app: `GET /summary`, `GET /health`, error responses. |
| [src/device_summary/settings.py](src/device_summary/settings.py) | Configuration from environment variables. |
| [src/device_summary/cli.py](src/device_summary/cli.py) | `device-summary FILE` prints the same JSON. |
| [data/sample.jsonl](data/sample.jsonl) | The sample described in the brief. |
| [tests/test_required.py](tests/test_required.py) | **The brief's three required tests.** |
| [tests/](tests/) | Edge cases, API, CLI and property-based tests. |
| [WALKTHROUGH.md](WALKTHROUGH.md) · [AI_NOTE.md](AI_NOTE.md) · [docs/DEFECTS.md](docs/DEFECTS.md) | Walkthrough, AI and reuse note, defects found and fixed. |

## Brief requirements and where they are tested

| Requirement | Implementation | Tests |
|---|---|---|
| Exactly `device_id`, `sequence`, `status` | `_validate` | `test_validation.py`: missing, extra, duplicate keys |
| `device_id` non-empty, not whitespace-only, kept as supplied | `_validate` | `device-id-*` cases, `test_device_ids_are_compared_exactly_as_supplied` |
| `sequence` integer ≥ 0, not a boolean | `_validate` | `sequence-*` cases (`true`, `-1`, `1.0`, `"1"`, …) |
| `status` is `ok` or `error` | `_validate` | `status-*` cases |
| Malformed JSON and blank lines are `BAD_JSON` with 1-based line number | `_decode`, `_parse` | `test_lines.py` |
| Invalid records are `INVALID_RECORD`; processing continues after every error | `summarise_lines` | every error test checks the next line is still accepted |
| Validate before checking duplicates | `summarise_lines` | `test_validation_happens_before_duplicate_checking` |
| First occurrence of a (device_id, sequence) pair wins, even if status differs | `summarise_lines` | `test_duplicate_with_different_status_is_counted_and_first_occurrence_wins` |
| Latest status from the highest accepted sequence, even out of order | `summarise_lines` | required test 2, `test_input_order_does_not_change_device_summaries` |
| Devices sorted by `device_id` | `summarise_lines` | `test_devices_are_sorted_by_device_id` |
| `GET /summary` for the sample file | `api.get_summary` | `test_summary_returns_the_sample_result` |
| Unreadable file is an error, not an empty success | `SourceUnavailableError` handler | `test_missing_file_returns_problem_details_not_an_empty_result` |
| Sample file with the listed records | `data/sample.jsonl` | required test 1 (`shipped-sample-file`) |
| The three required tests | | [tests/test_required.py](tests/test_required.py) |

## Prerequisites

- **uv 0.12 or newer** (recommended). It reads `.python-version` and installs Python 3.13
  if needed, and `uv.lock` pins every dependency version.
- **Or** Python 3.11+ with pip 25.1+ (needed for `--group`). This path is not locked.
- Tested in CI on Ubuntu and Windows with Python 3.11, 3.12, 3.13 and 3.14.

## Setup, run and test

Commands are one per line, so they work in Windows PowerShell 5.1 as well as bash.

**With uv**

```
uv sync --locked
uv run pytest
uv run uvicorn device_summary.api:app
uv run device-summary data/sample.jsonl
```

`uv run pytest` also enforces 100% line and branch coverage. The other checks CI runs:

```
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/check_mutations.py
```

The last one plants 16 deliberate bugs in `summary.py`, one at a time, and confirms the
tests catch every one; the file is restored afterwards.

**With pip**

```
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade "pip>=25.1"
python -m pip install -e . --group dev
pytest
uvicorn device_summary.api:app
```

On macOS or Linux, activate with `source .venv/bin/activate` instead.

**With Docker** (tested locally with Docker Engine 29 and in CI)

```
docker build --tag device-summary .
docker run --rm --publish 8000:8000 device-summary
```

The container runs as a non-root user and has a health check on `/health`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DEVICE_SUMMARY_FILE` | `data/sample.jsonl` in this repository (when run from a checkout, as in every command above) | JSON Lines file to summarise. Read on every request. |
| `DEVICE_SUMMARY_CORS_ORIGINS` | empty (CORS off) | Comma-separated browser origins allowed to call the API, e.g. `http://localhost:5173`. |

## API

`GET /summary` returns `200` and `application/json` in the shape shown above.

- `errors` are in line order. Each has `line` (1-based), `code` (`BAD_JSON` or
  `INVALID_RECORD`) and a human-readable `reason`. The number of errors is
  `len(errors)`.
- `devices` are sorted by `device_id`. Counts include accepted records only.

`GET /health` returns `{"status": "ok"}` without touching the input file.

### Errors

Every error response uses [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457) problem
details with content type `application/problem+json`, so a client never mistakes a
failure for an empty summary. Unknown routes return `404`, wrong methods `405` (with an
`Allow` header), and unexpected errors a generic `500` with no internal details.

### Source unavailable

If the input file is missing or cannot be read, `GET /summary` returns:

```
HTTP/1.1 500 Internal Server Error
content-type: application/problem+json

{"type": "https://github.com/suraj2022s/device-summary#source-unavailable",
 "title": "Summary source unavailable", "status": 500,
 "detail": "The input file 'missing.jsonl' could not be read.", "instance": "/summary"}
```

Only the file name is returned; the full path and OS error go to the server log. The
status is 500, not 503: RFC 9110 reserves 503 for temporary overload or maintenance,
while an unreadable data file is an unexpected server-side condition.

## Behaviour and assumptions

Where the brief leaves room for interpretation, these are the choices made (each has a test):

- A line is split on `\n` only; `\r\n` is accepted. A line separator character such as
  U+2028 inside a JSON string does not split a record, as it would with `str.splitlines()`.
- Blank means empty or whitespace-only; blank lines are `BAD_JSON`, including a trailing
  empty line at the end of the file.
- Input is UTF-8. Invalid UTF-8 is `BAD_JSON`. A byte order mark is tolerated on line 1
  only, since some Windows editors add one.
- `NaN`, `Infinity` and integers too long for Python to convert are `BAD_JSON`. The first
  two are not JSON (RFC 8259), even though Python accepts them by default.
- JSON nested too deeply for the parser is `BAD_JSON`. How deep that is depends on the
  Python version and platform: 100,000 levels exhausts it on Windows but parses on Linux
  with Python 3.14, where the result is then `INVALID_RECORD` because it is not an
  object. Either way the line is rejected and processing continues.
- Valid JSON that is not an object (`[]`, `"x"`, `null`) is `INVALID_RECORD`: it is JSON,
  just not a record.
- A repeated key (`{"sequence": 1, "sequence": 2, ...}`) is `INVALID_RECORD`. Python's
  parser would otherwise keep the last value silently. If the line is also malformed,
  `BAD_JSON` wins.
- `sequence` must be a JSON integer: `1.0` and `1e2` are rejected. `-0` parses as `0` and
  is accepted.
- "Whitespace-only" uses Python's definition (`str.isspace`), which includes Unicode
  spaces. Valid IDs are kept byte for byte: `" D01"` and `"D01"` are different devices.
- `status` is case-sensitive: `"OK"` is invalid.
- Devices are sorted by Unicode code point (Python's default), so `"D10"` sorts before
  `"d01"`.

## Design notes

- **One pipeline per line: decode → parse → validate.** The first step that fails decides
  the error code, which makes the precedence rules explicit: bad bytes or bad syntax is
  `BAD_JSON`; anything that parses but is not a valid record is `INVALID_RECORD`. Only
  valid records reach duplicate checking, which is how "validate before duplicates" is
  enforced by the structure of the code rather than by a check.
- **Rules live in a pure module.** `summary.py` has no web code, so every rule is tested
  directly; the API and CLI are thin layers on top.
- **Streaming read.** The file is read line by line in binary mode and never held in
  memory as a whole; memory grows with the number of devices, unique
  `(device_id, sequence)` pairs and rejected lines (every error is reported).
- **Fresh data per request.** `/summary` re-reads the file each time, so edits show up
  immediately without restarting the server.
- **Tests that prove the tests.** A reference-model property test (Hypothesis) compares
  the implementation with a plain restatement of the brief on random inputs, and the
  mutation script shows each rule is guarded by at least one failing test.

## React client

How a React page could fetch `/summary` and tell loading, empty data and an API failure apart:

- **Three explicit states.** Keep `status: "loading" | "success" | "error"` (or use
  TanStack Query's `isPending` / `isSuccess` / `isError`); start in `loading` and call
  `fetch("/summary", { signal })` in a `useEffect`, aborting with an `AbortController` on
  unmount.
- **Treat non-2xx as failure.** `fetch` only rejects on network errors, so check
  `response.ok`; for a `500`, read the `application/problem+json` body and show its
  `title` and `detail`. A rejected promise (network down) is also `error`; ignore
  `AbortError`.
- **Empty is a kind of success.** A `200` with `accepted === 0`, `devices: []` and
  `errors: []` renders "No messages yet". A failed request can never look like this,
  because failures are never `200`.
- **Rejected lines are not "empty".** If every line was invalid, `devices` is empty but
  `errors` is not; show the error list rather than the empty-state message.
- **Same origin in development.** Proxy `/summary` through the Vite dev server
  (`server.proxy`), or allow the page's origin with `DEVICE_SUMMARY_CORS_ORIGINS`.

## Time spent

<!-- TODO before submitting: replace with your own figures. -->
- Core brief (validation, summary, endpoint, the three tests, README): _X h_
- Optional hardening beyond the brief (edge-case and property tests, mutation check, CI,
  Docker, walkthrough): _Y h_

The brief suggests a 2-hour cap. The core was prioritised first; the hardening was a
deliberate choice to go further, and is listed separately so it can be judged on its own.

## Unfinished work

- The Docker image is single-stage, so it also carries the uv binaries (282 MB in
  total); a multi-stage build would copy only the virtual environment into the final
  image.
- No authentication, rate limiting or TLS: this is a local tool behind no network edge.
- Logging is plain text from the standard library; no structured logs or metrics.
- The CLI does not exit quietly when its output pipe closes early (for example
  `device-summary big.jsonl | head`); it prints a `BrokenPipeError` traceback.
- Error `reason` text includes messages from Python's `json` module, which could be
  worded differently in a future Python version (tests pin one message).

## Known limitation

The whole file is re-read and re-validated on every request, and duplicate detection
keeps every accepted `(device_id, sequence)` pair in memory, so response time and memory
grow with the size of the file. That is fine for this sample; for large or continuously
growing files I would process incrementally (remember the last byte offset) or
recompute the summary only when the file changes.

## AI use

See [AI_NOTE.md](AI_NOTE.md).
