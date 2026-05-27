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
- Compose maps `${AOP_HOST_PORT:-8000}` to container port `8000`.
- Compose exposes only `AGENT_BASE_URL` and `OPENROUTER_API_KEY`; Portainer
  should provide their real values.
- One deployed server exposes Danny at `/.well-known/danny.json` and
  `/danny/a2a`, plus Raymond at `/.well-known/raymond.json` and `/raymond/a2a`.
- `/healthz` is used for container health checks.
- Keep `.dockerignore` updated for Portainer and the current local Podman
  Compose provider.
- Local Podman debugging verified that the image builds successfully with
  `podman compose build`.
- Local Podman debugging after env simplification verified
  `podman compose -f compose.yaml build`.
- Local Podman debugging previously verified container health checks and A2A
  card/RPC routes; rerun after route changes when deployment behavior matters.
- Host port `18080` was already in use during local debugging.
- A generated `.pytest_cache` directory had inaccessible ACLs and blocked
  top-level Podman build context scanning locally. Real Portainer builds from a
  clean checkout should not hit this; local debug used a temporary clean context.
