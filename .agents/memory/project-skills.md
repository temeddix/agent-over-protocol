# Project Skills

Project-local Codex skills live under `.agents/skills`.

- `.agents/skills/aop-a2a-server` covers A2A server, executor, agent cards,
  runtime instructions, OpenRouter tool calling, workspace tools, and document
  extraction.
- `.agents/skills/aop-deployment` covers Containerfile, Compose, Portainer,
  Podman, health checks, File Browser, Tika, runtime environment variables, and
  mounted context volumes.
- Prefer moving stable reusable workflows into skills and keeping memory files
  as concise topic indexes.
- Do not store secrets, tokens, private credentials, or sensitive user data in
  skills.
