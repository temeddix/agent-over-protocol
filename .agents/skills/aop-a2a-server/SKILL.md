---
name: aop-a2a-server
description: Project-local workflow for modifying or debugging agent-over-protocol's A2A server, agent cards, executor, runtime instructions, OpenRouter tool calling, and read-only workspace or document tools. Use when changing files such as server.py, executor.py, agent_card.py, llm.py, tools.py, workspace.py, documents.py, context.py, settings.py, or tests that exercise A2A protocol behavior.
---

# AOP A2A Server

## Start Here

Before A2A protocol or runtime work, scan the relevant memory files:

- `.agents/memory/project-direction.md`
- `.agents/memory/async-io.md`
- `.agents/memory/code-quality.md`

Keep the A2A protocol/server layer separate from the model backend. Treat OpenRouter as the LLM provider behind an OpenAI-compatible async client, not as the A2A transport.

## Current Contract

- Build the server as a Starlette ASGI app using `a2a-sdk` route helpers.
- Keep `create_app()` in `agent_over_protocol.server`.
- Serve the invite-friendly public card at `/.well-known/agent.json`.
- Also serve the SDK standard public card at `/.well-known/agent-card.json`.
- Serve JSON-RPC A2A requests at `/a2a`.
- Agent invite URLs should point at `https://public-host/.well-known/agent.json`; the card should advertise `https://public-host/a2a` for JSON-RPC.
- Include both v0.3-compatible legacy fields and v1.0 `supportedInterfaces` in agent cards.
- Publish an initial `Task` before status updates in task-mode streams because the current `a2a-sdk` request handler expects the task to exist first.
- A2A v1 JSON-RPC requests should send the `A2A-Version: 1.0` header; the SDK treats missing version headers as v0.3.
- `OpenRouterAgentExecutor` should pass prior conversational context to the model:
  - consume incoming `RequestContext.current_task.history` when the SDK provides it;
  - keep ordinary chat turns in an in-memory history keyed by A2A `context_id`;
  - alias chat history by task IDs, `referenceTaskIds`, related tasks, safe conversation/thread metadata or headers, and a process-local fallback scope for clients that omit A2A context IDs;
  - merge stored context history with incoming task history before calling `ChatBackend.complete(..., history=...)`.
- A2A history controls protocol task state/history. Do not treat `historyLength` as model-side compact history or summarization. Compact summaries belong in the application/backend conversation layer if added later.

## Runtime Instructions And Tools

- Provide runtime model instructions through `agent_over_protocol.context.FileInstructionProvider`.
- Combine optional `AGENT_CONTEXT_COMMAND` output with optional `AGENT_CONTEXT_FILE` contents.
- Load runtime instructions once per non-empty A2A request and pass them to `ChatBackend.complete(..., instructions=...)`.
- Pass prior chat context to `ChatBackend.complete(..., history=...)`; the backend converts it into OpenAI-compatible chat messages before the current user prompt.
- In the OpenRouter backend, send runtime instructions as a system message before the user prompt.
- Build read-only workspace tools with `agent_over_protocol.tools.build_workspace_tools`.
- Expose `list_files`, `read_file`, and `search_files` to the model through OpenRouter chat-completions tool calling.
- Execute model tool calls server-side and feed results back to the model as JSON strings before returning the final A2A answer.
- Root workspace access at `Settings.agent_workspace_root`, currently `/context`.
- Reject parent-directory traversal and drive-qualified paths.
- Use `agent_over_protocol.documents.DocumentReader` for document extraction.
- Read Excel `.xlsx` and `.xlsm` files with openpyxl into structured sheets, rows, and cells.
- Extract other broad document formats through Tika at `Settings.tika_url`, currently `http://tika:9998`.

## Change Workflow

- For protocol changes, inspect `server.py`, `executor.py`, `agent_card.py`, and `tests/test_server.py`.
- For runtime instruction changes, inspect `context.py`, `executor.py`, `llm.py`, and related tests.
- For model tool changes, inspect `llm.py`, `tools.py`, `workspace.py`, `documents.py`, `settings.py`, and `tests/test_workspace.py`.
- Use async APIs end to end; isolate unavoidable blocking work with `asyncio.to_thread`.
- Keep provider secrets, model routing internals, and raw API keys out of agent cards and public responses.
- Keep public functions, protocol boundaries, and provider interfaces typed.
- Add focused tests for protocol behavior, provider adapters, tool execution, and error paths.

## Verification

Prefer these checks after relevant changes:

```powershell
uv run ruff check .
uv run ty check .
uv run pytest
```

On local Windows runs with restrictive temp or cache ACLs, use:

```powershell
uv run pytest --basetemp .cache\pytest-tmp -p no:cacheprovider
```

For manual ASGI debugging, run:

```powershell
uvicorn --app-dir src agent_over_protocol.server:create_app --factory
```
