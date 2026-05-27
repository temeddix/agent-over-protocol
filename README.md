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

- `http://127.0.0.1:8000/.well-known/agent.json`
- `http://127.0.0.1:8000/.well-known/agent-card.json`
- `http://127.0.0.1:8000/a2a`

Use `/.well-known/agent.json` as the Agent A2A URL in invite dialogs. The card
advertises `/a2a` as the JSON-RPC endpoint.

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
