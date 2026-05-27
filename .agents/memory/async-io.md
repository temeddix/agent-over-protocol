# Async I/O

The user explicitly wants nonblocking async I/O everywhere practical.

- Use async end to end for request handling, A2A execution, model calls, file
  I/O, network I/O, subprocess work, and other I/O-heavy code paths.
- Use async network clients such as `openai.AsyncOpenAI` or `httpx.AsyncClient`.
- Use async file I/O libraries or async framework helpers when reading or
  writing files from application code.
- If a blocking API is unavoidable, isolate it with `asyncio.to_thread` or a
  dedicated worker boundary instead of calling it directly in async code.
- Tests should cover async paths with async test helpers rather than forcing
  synchronous wrappers around async application code.
