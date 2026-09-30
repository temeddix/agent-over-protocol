# Deployment

Detailed deployment workflow guidance now lives in
`.agents/skills/aop-deployment/SKILL.md`.

Use that skill before changing:

- `Containerfile`
- `compose.yaml`
- `.dockerignore`
- Portainer or Podman behavior
- File Browser
- Tika
- health checks
- runtime environment wiring
- mounted agent context volumes

Keep this memory file as an index. Move stable reusable deployment procedures
into the skill instead of duplicating them here.

The deployment skill also documents File Browser's health-check port setting
and the Podman Docker-compatible API's handling of Python health-check commands.
Check deployed container arguments and health state when diagnosing failures.

The September 2026 Brain migration audit found the AOP Portainer stack still
supplied only `OPENROUTER_API_KEY`; Compose injected an empty `LLM_API_KEY`,
causing startup failure (`LLM_API_KEY is required`), repeated container restarts,
and public HTTP 502 responses. Migrating source and Compose does not migrate
Portainer's stored environment. Set AOP's `LLM_API_KEY` from the Brain stack's
`BRAIN_API_KEY` before recreating the service. After the user authorized repair,
the stack environment was migrated and redeployed with its Git reference and
named volumes preserved. Public health/card routes returned HTTP 200, and a live
A2A request completed through Brain. No credential values belong in memory.
