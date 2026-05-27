# Agent Over Protocol

Async Python A2A agent backed by OpenRouter.

## Setup

```powershell
uv sync
```

For local test credentials, create `tests/.env` from `tests/.env.template`.
Production secrets should be supplied by Compose or Portainer environment
configuration.

## Run Locally

```powershell
$env:AGENT_BASE_URL = "http://127.0.0.1:8000"
$env:OPENROUTER_API_KEY = "your-openrouter-key"
uv run uvicorn --app-dir src agent_over_protocol.server:create_app --factory --host 0.0.0.0 --port 8000
```

Invite/discovery URLs:

- Danny: `http://127.0.0.1:8000/.well-known/danny.json`
- Raymond: `http://127.0.0.1:8000/.well-known/raymond.json`
- Danny JSON-RPC: `http://127.0.0.1:8000/danny/a2a`
- Raymond JSON-RPC: `http://127.0.0.1:8000/raymond/a2a`

Use `/.well-known/danny.json` or `/.well-known/raymond.json` as the Agent A2A
URL in invite dialogs.

## Test

```powershell
uv run ruff check .
uv run ty check .
uv run pytest
uv lock --check
```

## Podman Compose

```powershell
$env:AGENT_BASE_URL = "https://agent.example.com"
$env:OPENROUTER_API_KEY = "your-openrouter-key"
podman compose -f compose.yaml config
podman compose -f compose.yaml build
podman compose -f compose.yaml up -d
```

For Portainer, provide real `AGENT_BASE_URL` and `OPENROUTER_API_KEY` values in
the stack environment.

## Container Build Context

Portainer and the current local Podman Compose provider use `.dockerignore` for
the build context.
