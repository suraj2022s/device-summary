# AI and reuse note

## Tools used

- **Claude Code** (Anthropic's coding agent) in VS Code, running the Claude Opus 5.5
  model. It drafted the plan, the code, the tests and these documents, and ran the
  commands (tests, linters, the server) on my machine.
- **Web research through the agent**, to check behaviour against primary sources instead
  of memory: RFC 9110 (status codes), RFC 9457 (problem details), the JSON Lines spec,
  Python's `json` documentation, the FastAPI, Starlette and uv docs, and MDN on `fetch`.

## Existing code reused

- No code was copied from other projects or from any employer.
- Runtime libraries: FastAPI, Starlette, Pydantic, Uvicorn. Development tools: pytest,
  pytest-cov, Hypothesis, httpx2, ruff, mypy. All versions are pinned in `uv.lock`.
- The Dockerfile and the CI workflow follow the patterns in the
  [uv Docker guide](https://docs.astral.sh/uv/guides/integration/docker/) and
  [uv GitHub Actions guide](https://docs.astral.sh/uv/guides/integration/github/).

## What the AI produced

A plan (researched and revised before any code), then the implementation in small
commits: the core rules and the brief's three tests first, then edge-case and
property-based tests, the HTTP API and CLI, CI and Docker, and the documentation.

## What I decided and changed

- I asked for a written plan before any code and approved it before implementation.
- I chose FastAPI, the flat response shape, the extras (CI, property-based tests, CLI,
  Docker) and delivery as a public repository, and I chose to go past the suggested
  2-hour cap to harden the solution.
- <!-- TODO before submitting: list your own review changes, or state that you made none. -->

## How it was verified

- **Tests:** the brief's three tests plus edge-case, API, CLI and property-based tests;
  100% line and branch coverage is enforced; warnings fail the build.
- **Tests of the tests:** `scripts/check_mutations.py` plants 15 bugs, one at a time; the
  suite catches all 15.
- **Real runs:** the server was started with Uvicorn and called with `curl` for the
  sample (200), a missing file (500 problem details) and a wrong method (405).
- **Reproducibility:** a fresh clone installed with `uv sync --locked` passes every check
  on Windows and on Ubuntu (WSL); CI runs Ubuntu and Windows with Python 3.11–3.14 and
  builds the Docker image.
- **Mistakes the AI made, and how they were caught:** it once claimed in a commit message
  that a fix was done when it was not, and it removed code as "redundant" that affected
  error messages. A byte scan and a check of the real output caught these; both are
  written up in [docs/DEFECTS.md](docs/DEFECTS.md) with the regression tests that now
  guard them. My takeaway: AI output counts as unverified until a test or a real run
  confirms it.
