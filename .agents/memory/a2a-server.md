# A2A Server

The server is built as a Starlette ASGI app using `a2a-sdk` route helpers.

- `create_app()` lives in `agent_over_protocol.server`.
- The invite-friendly public card path is `/.well-known/agent.json`.
- The SDK standard public card path is also served at
  `/.well-known/agent-card.json`.
- The JSON-RPC A2A endpoint is `/a2a`.
- Invite dialogs that ask for an Agent A2A URL should use
  `https://public-host/.well-known/agent.json`; the card then advertises
  `https://public-host/a2a` for JSON-RPC.
- Agent cards include both v0.3-compatible and v1.0 JSON-RPC interfaces so
  older invite flows can read legacy `url`/`preferredTransport` fields while
  modern clients can read `supportedInterfaces`.
- The executor publishes an initial `Task` before status updates because the
  current `a2a-sdk` default request handler expects task-mode streams to create
  the task first.
- Run the ASGI app with an explicit app dir, for example:
  `uvicorn --app-dir src agent_over_protocol.server:create_app --factory`.
- A2A v1 JSON-RPC requests should send the `A2A-Version: 1.0` header; the SDK
  treats missing version headers as v0.3.
