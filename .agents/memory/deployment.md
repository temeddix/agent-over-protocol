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
