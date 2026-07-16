# Copyright (c) 2026 Danny Kim
"""Model-callable tools for the A2A agent."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from agent_over_protocol.documents import DocumentReader, JsonObject
from agent_over_protocol.web import WebFetcher, WebFetchError
from agent_over_protocol.workspace import Workspace, WorkspaceError

if TYPE_CHECKING:
    from openai.types.chat import ChatCompletionToolParam

    from agent_over_protocol.settings import Settings


ToolHandler = Callable[[Mapping[str, object]], Awaitable[JsonObject]]


class ToolCallError(RuntimeError):
    """Raised when a model tool call cannot be executed."""


@dataclass(frozen=True)
class AgentTool:
    """A function tool available to the model backend."""

    name: str
    description: str
    parameters: dict[str, object]
    handler: ToolHandler

    async def call(self, arguments: Mapping[str, object]) -> str:
        """Execute the tool with validated arguments."""
        try:
            result = await self.handler(arguments)
        except (WebFetchError, WorkspaceError) as exc:
            raise ToolCallError(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False)

    def as_openai_tool(self) -> ChatCompletionToolParam:
        """Return this tool as an OpenAI-compatible function definition."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def build_workspace_tools(settings: Settings) -> list[AgentTool]:
    """Build read-only file workspace tools from settings."""
    document_reader = DocumentReader(
        tika_url=settings.tika_url,
        tika_timeout_seconds=settings.tika_timeout_seconds,
        max_spreadsheet_rows=settings.agent_spreadsheet_max_rows,
        max_spreadsheet_columns=settings.agent_spreadsheet_max_columns,
    )
    workspace = Workspace(
        root=Path(settings.agent_workspace_root),
        max_read_chars=settings.agent_workspace_max_read_chars,
        max_list_entries=settings.agent_workspace_max_list_entries,
        max_search_results=settings.agent_workspace_max_search_results,
        max_search_file_bytes=settings.agent_workspace_max_search_file_bytes,
        document_reader=document_reader,
    )
    web = WebFetcher(
        timeout_seconds=settings.agent_web_timeout_seconds,
        max_chars=settings.agent_web_max_chars,
        max_bytes=settings.agent_web_max_bytes,
        max_grep_results=settings.agent_web_max_grep_results,
    )

    async def list_files(arguments: Mapping[str, object]) -> JsonObject:
        return await workspace.list_directory(_string_argument(arguments, "path", "."))

    async def read_file(arguments: Mapping[str, object]) -> JsonObject:
        return await workspace.read_file(
            _string_argument(arguments, "path", "."),
            max_chars=_int_argument(arguments, "max_chars", None),
        )

    async def search_files(arguments: Mapping[str, object]) -> JsonObject:
        return await workspace.search_files(
            _string_argument(arguments, "query", ""),
            _string_argument(arguments, "path", "."),
        )

    async def fetch_url(arguments: Mapping[str, object]) -> JsonObject:
        return await web.fetch(
            _string_argument(arguments, "url", ""),
            max_chars=_int_argument(arguments, "max_chars", None),
        )

    async def grep(arguments: Mapping[str, object]) -> JsonObject:
        return await web.grep(
            _string_argument(arguments, "url", ""),
            _string_argument(arguments, "query", ""),
        )

    return [
        AgentTool(
            name="list_files",
            description=(
                "List files and folders under the read-only workspace root. "
                "Use this before reading when the exact path is unknown."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Workspace-relative folder path. Use '.' for the root."
                        ),
                    },
                },
                "required": [],
                "additionalProperties": False,
            },
            handler=list_files,
        ),
        AgentTool(
            name="read_file",
            description=(
                "Read a supported file or document from the read-only workspace. "
                "Returns structured JSON. Excel files include sheets, rows, "
                "and cell addresses; other documents use Tika text and metadata."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative file path to read.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Optional maximum characters to return.",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=read_file,
        ),
        AgentTool(
            name="search_files",
            description=(
                "Search supported files and documents under the read-only "
                "workspace for text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Text to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Workspace-relative folder or file path. "
                            "Use '.' for the root."
                        ),
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=search_files,
        ),
        AgentTool(
            name="fetch_url",
            description=(
                "Fetch a public HTTP or HTTPS URL and return readable page text. "
                "Use this whenever the user provides a URL or asks about a web page."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute public HTTP(S) URL to fetch.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Optional maximum characters to return.",
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
            handler=fetch_url,
        ),
        AgentTool(
            name="grep",
            description=(
                "Fetch a public web page and return lines containing a "
                "case-insensitive text query."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Absolute public HTTP(S) URL to search.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Literal text to find in the page.",
                    },
                },
                "required": ["url", "query"],
                "additionalProperties": False,
            },
            handler=grep,
        ),
    ]


def _string_argument(arguments: Mapping[str, object], name: str, default: str) -> str:
    value = arguments.get(name, default)
    if isinstance(value, str):
        return value
    message = f"Tool argument {name!r} must be a string."
    raise ToolCallError(message)


def _int_argument(
    arguments: Mapping[str, object],
    name: str,
    default: int | None,
) -> int | None:
    value = arguments.get(name, default)
    if value is None or isinstance(value, int):
        return value
    message = f"Tool argument {name!r} must be an integer."
    raise ToolCallError(message)
