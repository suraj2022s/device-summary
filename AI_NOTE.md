# AI and Reuse Note

## Tools and Collaboration

- **Claude Code** (Anthropic's coding agent, running Claude Opus 5.5) acted as my pair-programming partner in VS Code. Together, we drafted the project plan, wrote the code and tests, authored the documentation, and executed commands on my machine.
- **Web research through the agent** allowed us to verify behaviors against primary sources rather than relying on memory: RFC 9110, RFC 9457, the JSON Lines spec, Python's `json` documentation, the FastAPI, Starlette, and uv docs, and MDN on `fetch`.
- **No code was copied** from other projects or from any employer. The stack relies on FastAPI, Starlette, Pydantic, and Uvicorn. For development, we used pytest, pytest-cov, Hypothesis, httpx2, ruff, and mypy, all securely pinned in `uv.lock`. The Dockerfile and CI pipelines were implemented following the official uv [Docker](https://docs.astral.sh/uv/guides/integration/docker/) and [GitHub Actions](https://docs.astral.sh/uv/guides/integration/github/) guides.

## Architecture and Decision Making

While Claude assisted with code generation and boilerplate, I drove the project's direction, architecture, and quality control. I did not edit files by hand; instead, I directed our collaboration:

- **Approach:** I required a thoroughly researched plan before any code was written, halting the agent to iterate on the design until the architecture aligned with my goals.
- **Decisions:** I made the core technical choices, including selecting FastAPI over Flask, defining a flat response shape to match the brief's exact wording, and determining the scope of optional extras (CI, property-based testing, a CLI, and Docker containerization).
- **Verification beyond CI:** I independently tested the Docker image on my local machine, executed full end-to-end pipeline runs prior to submission, and performed rigorous manual code reviews on our combined output—which allowed me to catch a crash that the automated tests initially missed.

## Testing and Verification Strategy

- The suite includes the brief's three core tests alongside edge-case, API, CLI, and property-based tests, enforcing 100% line and branch coverage. I also utilized a mutation script that plants 16 distinct bugs; the test suite successfully catches all of them.
- Validation included real-world runs of the server and Docker image (verifying 200s for sample requests and 500 problem details for missing files), fresh clone testing on both Windows and Linux, and CI validation on Ubuntu and Windows across Python 3.11 through 3.14.
- Working with Claude was highly productive, but my checks caught several AI-generated mistakes: an inaccurate commit message, the removal of "redundant" code that inadvertently degraded error messages, a platform-specific test failure, and a crash on unusual `status` values (all documented in [docs/DEFECTS.md](docs/DEFECTS.md)). My core takeaway from this collaboration: an AI agent is an excellent junior partner, but its output must be treated as unverified until strict tests and real-world runs confirm it.
