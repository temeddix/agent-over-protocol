# Project Direction

Build a Python A2A agent using `a2a-sdk`.

- The project requires Python 3.14 or newer.
- The A2A protocol/server layer should be separate from the LLM backend.
- The backend uses Brain's OpenAI-compatible async API at
  `https://brain.temeddix.me/v1` with model `toddler` by default. Configure it
  through `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`.
- Match the user's language in user-facing conversation.
- Prefer async end to end across request handling, A2A execution, and provider
  calls.
- Nonblocking async I/O is a project-wide requirement, including file I/O and
  network I/O.
- FastAPI is optional; use it only when custom routes, middleware, auth,
  OpenAPI docs, admin endpoints, or richer app composition become useful.
- The project uses `uv` with `pyproject.toml` dependency metadata.
  `tool.uv.package = false` keeps the project in application mode until a build
  backend is deliberately introduced.
- A minimal `src/agent_over_protocol` package and `tests` directory now exist so
  Ruff and ty can run against stable project roots.
- `uv.lock` is generated and should be kept for application reproducibility.
- Test-only environment templates live at `tests/.env.template`, and local
  ignored test credentials live at `tests/.env`; production environment
  variables are provided through Compose/Portainer.
- The A2A server should be invitable by exposing a public agent card at
  `/.well-known/agent.json`, with the SDK standard `/.well-known/agent-card.json`
  path also available.
