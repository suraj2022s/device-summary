# AI and reuse note

## Tools and reuse

- **Claude Code** (Anthropic's coding agent, running Claude Opus 5.5) in VS Code drafted
  the plan, the code, the tests and these documents, and ran the commands on my machine.
- **Web research through the agent** checked behaviour against primary sources instead
  of memory: RFC 9110, RFC 9457, the JSON Lines spec, Python's `json` documentation, the
  FastAPI, Starlette and uv docs, and MDN on `fetch`.
- **No code was copied** from other projects or from any employer. Libraries: FastAPI,
  Starlette, Pydantic and Uvicorn; for development pytest, pytest-cov, Hypothesis,
  httpx2, ruff and mypy, all pinned in `uv.lock`. The Dockerfile and CI follow the uv
  [Docker](https://docs.astral.sh/uv/guides/integration/docker/) and
  [GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/) guides.

## What I changed and decided

I did not edit files by hand; my changes came from directing the assistant:

- **Approach:** I asked for a researched plan before any code, and stopped the assistant
  when it started coding before the plan was approved.
- **Decisions:** FastAPI over Flask, a flat response shape that matches the brief's
  wording, and which optional extras were worth adding (CI, property-based tests, a CLI,
  Docker).
- **Verification beyond CI:** I had the Docker image tested on my own machine, the whole
  pipeline re-run end to end before submitting, and a full code review, which found a
  crash that the tests had missed.

## How it was verified

- The brief's three tests plus edge-case, API, CLI and property-based tests, with 100%
  line and branch coverage enforced. A mutation script plants 16 bugs, one at a time,
  and the suite catches all of them.
- Real runs of the server and of the Docker image (200 for the sample, 500 problem
  details for a missing file), fresh clones on Windows and Linux, and CI on Ubuntu and
  Windows with Python 3.11 to 3.14.
- The AI made mistakes that these checks caught: a commit message that claimed a fix that
  had not happened, code removed as "redundant" that changed error messages, a test that
  only passed on some platforms, and a crash on unusual `status` values. All are in
  [docs/DEFECTS.md](docs/DEFECTS.md). My takeaway: AI output counts as unverified until a
  test or a real run confirms it.
