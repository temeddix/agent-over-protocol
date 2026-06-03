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
chat history in the executor, alias it by A2A `context_id`, task/reference IDs,
safe conversation/thread metadata or headers, and a process-local fallback scope
for clients that omit context IDs. Treat compact summaries as an
application/backend concern rather than an A2A protocol feature.
