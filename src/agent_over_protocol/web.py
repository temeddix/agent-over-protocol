# Copyright (c) 2026 Danny Kim
"""Async web-page fetching for model-callable tools."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

if TYPE_CHECKING:
    from agent_over_protocol.documents import JsonObject, JsonValue

USER_AGENT = "agent-over-protocol/0.1 (+https://github.com/temeddix)"


class WebFetchError(RuntimeError):
    """Raised when a public web page cannot be fetched."""


@dataclass(frozen=True)
class WebFetcher:
    """Fetch public HTTP(S) pages and expose readable text."""

    timeout_seconds: float
    max_chars: int
    max_bytes: int
    max_grep_results: int

    async def fetch(self, url: str, *, max_chars: int | None = None) -> JsonObject:
        """Fetch a URL and return its readable text and response metadata."""
        _validate_public_url(url)
        limit = self.max_chars if max_chars is None else max_chars
        if limit <= 0:
            message = "max_chars must be greater than zero."
            raise WebFetchError(message)

        try:
            async with (
                httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                ) as client,
                client.stream("GET", url) as response,
            ):
                response.raise_for_status()
                _validate_public_url(str(response.url))
                content_type = response.headers.get("content-type", "")
                chunks: list[bytes] = []
                size = 0
                truncated_bytes = False
                async for chunk in response.aiter_bytes():
                    remaining = self.max_bytes - size
                    if remaining <= 0:
                        truncated_bytes = True
                        break
                    chunks.append(chunk[:remaining])
                    size += min(len(chunk), remaining)
                    if len(chunk) > remaining:
                        truncated_bytes = True
                        break
        except httpx.HTTPError as exc:
            message = f"URL fetch failed: {exc}"
            raise WebFetchError(message) from exc

        raw_text = b"".join(chunks).decode(
            response.encoding or "utf-8", errors="replace"
        )
        text = _readable_text(raw_text, content_type)
        truncated = truncated_bytes or len(text) > limit
        return {
            "kind": "web_page",
            "url": str(response.url),
            "status_code": response.status_code,
            "content_type": content_type,
            "text": text[:limit].strip(),
            "truncated": truncated,
        }

    async def grep(self, url: str, query: str) -> JsonObject:
        """Return page lines containing a case-insensitive text query."""
        normalized_query = query.strip()
        if not normalized_query:
            message = "grep query cannot be empty."
            raise WebFetchError(message)
        page = await self.fetch(url)
        text = page.get("text")
        if not isinstance(text, str):
            text = ""
        folded_query = normalized_query.casefold()
        matches: list[JsonValue] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if folded_query not in line.casefold():
                continue
            matches.append({"line": line_number, "text": line.strip()[:500]})
            if len(matches) >= self.max_grep_results:
                break
        return {
            "kind": "web_grep_results",
            "url": page["url"],
            "query": normalized_query,
            "matches": matches,
            "truncated": len(matches) >= self.max_grep_results,
        }


def _validate_public_url(url: str) -> None:
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        message = "Only absolute HTTP(S) URLs are allowed."
        raise WebFetchError(message)
    if parsed.username or parsed.password:
        message = "URLs containing credentials are not allowed."
        raise WebFetchError(message)
    hostname = parsed.hostname.casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        message = "Local URLs are not allowed."
        raise WebFetchError(message)
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        message = "Private or local IP addresses are not allowed."
        raise WebFetchError(message)


def _readable_text(content: str, content_type: str) -> str:
    if "html" not in content_type.casefold():
        return content.strip()
    parser = _ReadableHTMLParser()
    parser.feed(content)
    return parser.text


class _ReadableHTMLParser(HTMLParser):
    """Extract visible-ish text from HTML without another dependency."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._ignored_depth = 0

    @property
    def text(self) -> str:
        """Return extracted text with one non-empty fragment per line."""
        return "\n".join(self._parts)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        """Ignore script and style contents."""
        del attrs
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        """Resume text collection after ignored elements."""
        if tag.casefold() in {"script", "style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        """Collect normalized visible text fragments."""
        if self._ignored_depth:
            return
        normalized = " ".join(data.split())
        if normalized:
            self._parts.append(normalized)
