---
name: aop-deployment
description: Project-local workflow for agent-over-protocol deployment and runtime verification. Use when editing Containerfile, compose.yaml, .dockerignore, health checks, Portainer or Podman setup, File Browser, Tika, runtime environment variables, or container-facing agent context volume behavior.
---

# AOP Deployment

## Start Here

Use this skill for production deployment, local container debugging, and runtime wiring that touches Compose, Portainer, Podman, File Browser, Tika, health checks, or the mounted agent context.

Before substantial deployment work, scan:

- `.agents/memory/project-direction.md`
- `.agents/memory/deployment.md`
- `.agents/memory/code-quality.md`

## Runtime Contract

- Production deployment is expected to run through Compose or Portainer.
- Runtime hosting uses `Containerfile` and `compose.yaml`.
- Base the container image on the official uv Python 3.14 slim image.
- Install locked runtime dependencies with `uv sync --frozen --no-dev --no-install-project`.
- Run the ASGI server on container port `8000`.
- Map `${AOP_HOST_PORT}` to container port `8000`.
- Use `/healthz` for container health checks.
- Keep `.dockerignore` current for Portainer and the local Podman Compose provider.

## Environment And Secrets

- Supply real server environment variables through `compose.yaml` or Portainer environment configuration.
- Do not commit real provider keys, production secrets, or local ignored credentials.
- Keep `tests/.env.template` test-only with dummy values.
- Keep local ignored test credentials in `tests/.env`.
- Read `OPENROUTER_API_KEY` from the environment.
- Expose only required runtime values such as `AGENT_BASE_URL`, `OPENROUTER_API_KEY`, `AOP_HOST_PORT`, and `FILEBROWSER_PORT`.
- Do not add optional Compose environment passthroughs or implicit interpolation defaults unless the user explicitly asks.

## Context Volume And Sidecars

- Mount the `agent-context` named volume read-only into the A2A agent at `/context`.
- Mount the same `agent-context` named volume read-write into File Browser at `/srv`.
- Read runtime agent instructions from `/context/AGENTS.md`.
- Let File Browser edit the same mounted directory through `/srv`.
- Let the A2A agent browse the same context volume through read-only model tools rooted at `/context`.
- Run an internal `tika` sidecar with `apache/tika:latest-full`.
- Do not expose Tika on a host port.
- Reach Tika from AOP at `http://tika:9998`.
- Map `${FILEBROWSER_PORT}` to File Browser container port `80`.
- Store the File Browser database in the `filebrowser-database` named volume.

## Change Workflow

- Inspect `Containerfile`, `compose.yaml`, `.dockerignore`, `src/agent_over_protocol/settings.py`, and README deployment notes before changing deployment behavior.
- Preserve the split between public A2A HTTP surfaces and private provider configuration.
- Avoid leaking provider keys, model routing, or internal environment values in agent cards, logs, public responses, or examples.
- Keep Compose minimal unless the user asks for richer deployment features.
- When simplifying environment interpolation, verify local Podman behavior if practical.

## Verification

Use the relevant subset of these checks:

```powershell
uv lock --check
podman compose -f compose.yaml build
```

After starting a container locally, verify:

- `/healthz`
- `/.well-known/agent.json`
- `/.well-known/agent-card.json`
- an A2A v1 `/a2a` JSON-RPC request with `A2A-Version: 1.0`

Local notes from earlier debugging:

- Host port `18080` was already in use.
- The built image was verified on host ports `19180` and `19181`.
- A generated `.pytest_cache` directory had inaccessible ACLs and blocked local top-level Podman build context scanning; a clean checkout or temporary clean context avoids that local issue.
