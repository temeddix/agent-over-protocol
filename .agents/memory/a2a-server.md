# A2A Server

Detailed A2A server workflow guidance now lives in
`.agents/skills/aop-a2a-server/SKILL.md`.

Use that skill before changing:

- A2A protocol behavior
- agent cards
- executor behavior
- runtime instructions
- OpenRouter tool calling
- workspace tools
- document extraction
- context/chat history handling

Keep this memory file as an index. Move stable reusable A2A procedures into the
skill instead of duplicating them here.

Current history direction: consume any SDK-provided task history, keep ordinary
chat history in SQLite via `SQLiteConversationStore`, alias it by A2A
`context_id`, task/reference IDs, safe conversation/thread metadata or headers,
and a process-local fallback scope for clients that omit context IDs. Compose
mounts the `agent-data` named volume at `/data`, and the default SQLite file is
`/data/conversations.sqlite`. Treat compact summaries as an application/backend
concern rather than an A2A protocol feature.

Current card routes: serve `/.well-known/agent.json`,
`/.well-known/agent-card.json`, and compatibility
`/a2a/.well-known/agent-card.json`; JSON-RPC remains at `/a2a`.

Document extraction note: Tika requests must keep `Content-Disposition` ASCII
safe by using an ASCII fallback filename and RFC 5987 `filename*` for non-ASCII
workspace filenames.

Current model tools also include async `fetch_url` and `grep` for public HTTP(S)
pages. They return readable text, reject obvious local/private targets, and must
report fetch failures instead of inventing page contents. LinkedIn currently
returns HTTP 999 to direct unauthenticated fetches in the local environment.
