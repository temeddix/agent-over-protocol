# Agent Instructions

## Project Direction

Build a Python agent that serves the Agent2Agent (A2A) protocol with `a2a-sdk`.
The A2A protocol/server layer should stay separate from the model backend. The
initial model backend may call OpenRouter through an OpenAI-compatible async
client.

Use Korean for user-facing conversation unless the user asks otherwise.

## Architecture Preferences

- Prefer async end to end.
- Use `async def` for request handlers, A2A executor methods, model calls, and
  I/O-heavy code paths.
- Use async clients such as `openai.AsyncOpenAI` or `httpx.AsyncClient`.
- Treat nonblocking async I/O as mandatory for application code. Network I/O,
  file I/O, subprocess work, and other I/O-heavy paths should use async APIs
  wherever available.
- Do not perform blocking network, filesystem, subprocess, or CPU-heavy work in
  async execution paths. If no practical async API exists, isolate the blocking
  call behind `asyncio.to_thread` or a dedicated worker boundary.
- Keep protocol objects, application services, model-provider clients, and
  configuration in separate modules once the codebase grows beyond a minimal
  scaffold.
- Do not expose provider secrets, internal model routing, or raw API keys in
  A2A agent cards or public responses.

## OpenRouter Backend

- Treat OpenRouter as the LLM backend, not as the A2A transport.
- Read `OPENROUTER_API_KEY` from the environment.
- Read the model from `OPENROUTER_MODEL`, with a conservative default only in
  code intended for local development.
- Configure OpenRouter with the OpenAI-compatible base URL:
  `https://openrouter.ai/api/v1`.
- Prefer structured error handling around provider failures, timeouts, and
  empty responses.

## FastAPI Guidance

FastAPI is optional. Prefer the smallest viable A2A HTTP server path supported by
`a2a-sdk` unless the project needs non-A2A routes, custom middleware, auth
integration, OpenAPI docs, admin endpoints, or richer app composition. If those
needs appear, FastAPI is a reasonable host for the A2A server.

## Code Quality

- Configure Ruff aggressively, aiming for all rules enabled and explicit local
  exceptions only when a rule conflicts with practical project needs.
- Configure Astral `ty` with diagnostics treated as errors where supported.
- Keep type annotations complete on public functions, protocol boundaries, and
  provider interfaces.
- Prefer typed configuration objects over unstructured dictionaries.
- Avoid broad `except Exception` blocks unless they translate failures at a
  boundary and preserve useful context.
- Add tests for protocol behavior, provider adapters, and error paths as soon as
  the first runnable agent exists.

## Project Skills

Store reusable project workflows under `.agents/skills`.

- Before work that matches a project-local skill, read that skill's `SKILL.md`
  after scanning the relevant memory files.
- Use `.agents/skills/aop-a2a-server` for A2A server, executor, agent card,
  runtime instruction, OpenRouter tool-calling, workspace tool, and document
  extraction work.
- Use `.agents/skills/aop-deployment` for Containerfile, Compose, Portainer,
  Podman, health check, File Browser, Tika, runtime environment, and mounted
  context volume work.
- Move reusable task procedures into skills instead of bloating always-loaded
  instructions or duplicating long details in memory.
- Never store secrets, tokens, private credentials, or sensitive user data in
  skill files.

## Memory

Store agent memory under `.agents/memory`.

- Update memory frequently when project direction, architecture decisions,
  conventions, commands, or user preferences change.
- Organize memory by topic, not by date.
- Use concise Markdown files with kebab-case names, for example
  `.agents/memory/a2a-architecture.md` or
  `.agents/memory/code-quality.md`.
- Before substantial work, scan the relevant topic memories.
- After substantial work, update the relevant topic memories before the final
  response.
- When substantial work changes a reusable workflow, update the relevant
  `.agents/skills/*/SKILL.md` as well.
- Never store secrets, tokens, private credentials, or sensitive user data in
  memory files.

## Git And Workspace Safety

- The worktree may contain user changes. Do not revert changes unless the user
  explicitly asks.
- Keep edits scoped to the current request.
- Use `rg`/`rg --files` for searches when available.
