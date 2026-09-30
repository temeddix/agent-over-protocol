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
- Read `LLM_API_KEY` from the environment. The application defaults to Brain at
  `https://brain.temeddix.me/v1` with model `toddler`.
- For authorized Brain verification, read `BRAIN_API_KEY` from the `brain` stack
  environment in Portainer and pass it as `LLM_API_KEY`. Load Portainer login
  credentials from `~/.env` inside the access process; never print their values.
  If multiple stacks share the name, select the one with `BRAIN_API_KEY` set.
- Migrate old deployments from `OPENROUTER_API_KEY` to `LLM_API_KEY`; do not
  automatically reuse credentials across providers.
- Expose only required runtime values such as `AGENT_BASE_URL`, `LLM_API_KEY`, `AOP_HOST_PORT`, and `FILEBROWSER_PORT`.
- Do not add optional Compose environment passthroughs or implicit interpolation defaults unless the user explicitly asks.

## Context Volume And Sidecars

- Mount the `agent-context` named volume read-only into the A2A agent at `/context`.
- Mount the same `agent-context` named volume read-write into File Browser at `/srv`.
- Read runtime agent instructions from `/context/SOUL.md`.
- Let File Browser edit the same mounted directory through `/srv`.
- Let the A2A agent browse the same context volume through read-only model tools rooted at `/context`.
- Run an internal `tika` sidecar with `apache/tika:latest-full`.
- Do not expose Tika on a host port.
- Reach Tika from AOP at `http://tika:9998`.
- Run File Browser on unprivileged container port `8080` so its non-root user
  can bind successfully, and map `${FILEBROWSER_PORT}` to that port.
- Set `FB_PORT: "8080"` in File Browser's environment as well as the command:
  its image-provided health check reads `FB_PORT` or `/config/settings.json`,
  not the server's `--port` argument.
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

For Portainer deployments backed by Podman:

- Use `CMD-SHELL` with a quoted `python -c` program for the agent health check.
  Podman's Docker-compatible API can split a Compose `CMD` program into words,
  leaving Python to execute only `from` and fail with `SyntaxError`.
- Inspect the deployed container's `Config.Healthcheck.Test` and
  `State.Health`, rather than assuming valid Compose YAML guarantees correct
  runtime arguments. Verify both the agent and File Browser become `healthy`.
- Preserve the stack's Git reference, environment variables, and named volumes
  when redeploying. Read credentials from `~/.env` only within the process that
  needs them, and never print credentials or include them in repository files.

Local notes from earlier debugging:

- Host port `18080` was already in use.
- The built image was verified on host ports `19180` and `19181`.
- A generated `.pytest_cache` directory had inaccessible ACLs and blocked local top-level Podman build context scanning; a clean checkout or temporary clean context avoids that local issue.
