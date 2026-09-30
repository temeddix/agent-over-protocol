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
