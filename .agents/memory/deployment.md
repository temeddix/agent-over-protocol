# Deployment

Production deployment is expected to run through Compose/Portainer.

- Real server environment variables should be supplied by `compose.yaml` or
  Portainer environment configuration.
- Do not commit real provider keys or production secrets.
- `tests/.env.template` is test-only and should contain dummy values.
- Local ignored test credentials live in `tests/.env`; never commit this file.
- Runtime hosting uses `Containerfile` and `compose.yaml`.
- The container image is based on the official uv Python 3.14 slim image and
  installs only locked runtime dependencies with
  `uv sync --frozen --no-dev --no-install-project`.
- The ASGI server listens on container port `8000`.
- Compose maps `${AOP_HOST_PORT}` to container port `8000`.
- Compose environment interpolation should not add implicit defaults unless the
  user explicitly asks for them.
- Compose exposes only required runtime values such as `AGENT_BASE_URL`,
  `OPENROUTER_API_KEY`, and host ports; avoid adding optional env passthroughs
  unless requested.
- Compose mounts the `agent-context` named volume read-only into the A2A agent
  at `/context` and read-write into File Browser at `/srv`.
- The A2A agent reads runtime context from `/context/AGENTS.md`; File Browser
  edits the same mounted directory through `/srv`.
- File Browser maps `${FILEBROWSER_PORT}` to container port `80` and stores
  its database in the `filebrowser-database` named volume.
- `/healthz` is used for container health checks.
- Keep `.dockerignore` updated for Portainer and the current local Podman
  Compose provider.
- Local Podman debugging verified that the image builds successfully with
  `podman compose build`.
- Local Podman debugging after env simplification verified
  `podman compose -f compose.yaml build`.
- Local Podman debugging verified the container on host port `19180`, including
  `/healthz`, `/.well-known/agent.json`, `/.well-known/agent-card.json`, and an
  A2A v1 `/a2a` empty-message request.
- Local Podman debugging verified the built image on host port `19181`,
  including `/healthz`, `/.well-known/agent.json`, and
  `/.well-known/agent-card.json`.
- Host port `18080` was already in use during local debugging.
- A generated `.pytest_cache` directory had inaccessible ACLs and blocked
  top-level Podman build context scanning locally. Real Portainer builds from a
  clean checkout should not hit this; local debug used a temporary clean context.
