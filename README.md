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
$env:AOP_HOST_PORT = "8000"
$env:FILEBROWSER_PORT = "8080"
podman compose -f compose.yaml config
podman compose -f compose.yaml build
podman compose -f compose.yaml up -d
```

For Portainer, provide the Compose environment variables explicitly in the stack
environment. Do not rely on Compose interpolation defaults.

File Browser is exposed on `${FILEBROWSER_PORT}` and serves the `agent-context`
named volume. Edit `AGENTS.md` there to change the runtime context used by the
A2A agent. The agent reads `/context/AGENTS.md` on each model request.

## Container Build Context

Portainer and the current local Podman Compose provider use `.dockerignore` for
the build context.
