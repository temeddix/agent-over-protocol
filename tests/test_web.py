# Copyright (c) 2026 Danny Kim
"""Tests for public web fetching tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest

from agent_over_protocol.web import WebFetcher, WebFetchError

if TYPE_CHECKING:
    from pytest_httpx import HTTPXMock


async def test_fetch_url_extracts_readable_html(httpx_mock: HTTPXMock) -> None:
    """HTML scripts are removed while visible page text is returned."""
    httpx_mock.add_response(
        url="https://example.com/profile",
        headers={"content-type": "text/html; charset=utf-8"},
        text="<html><script>ignore()</script><h1>Kim Donghyun</h1></html>",
    )
    result = await _fetcher().fetch("https://example.com/profile")

    assert result["text"] == "Kim Donghyun"
    assert result["status_code"] == httpx.codes.OK


async def test_grep_returns_matching_page_lines(httpx_mock: HTTPXMock) -> None:
    """Grep returns case-insensitive matching lines from a fetched page."""
    httpx_mock.add_response(
        url="https://example.com/profile",
        headers={"content-type": "text/plain"},
        text="Engineer\nOpen Source Maintainer\nSpeaker",
    )
    result = await _fetcher().grep("https://example.com/profile", "open source")

    assert result["matches"] == [{"line": 2, "text": "Open Source Maintainer"}]


async def test_fetch_url_rejects_private_addresses() -> None:
    """Model-controlled URLs cannot directly target private network addresses."""
    with pytest.raises(WebFetchError, match="Private or local"):
        await _fetcher().fetch("http://127.0.0.1/admin")


def _fetcher() -> WebFetcher:
    return WebFetcher(
        timeout_seconds=5.0,
        max_chars=10_000,
        max_bytes=100_000,
        max_grep_results=10,
    )
