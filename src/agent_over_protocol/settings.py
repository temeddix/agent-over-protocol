# Copyright (c) 2026 Danny Kim
"""Runtime settings for the A2A server."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file="tests/.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agent_name: str = "Agent Over Protocol"
    agent_description: str = "An async A2A agent backed by OpenRouter."
    agent_version: str = "0.1.0"
    agent_base_url: str = "http://localhost:8000"
    agent_rpc_path: str = "/a2a"
    agent_card_path: str = "/.well-known/agent.json"
    agent_standard_card_path: str = "/.well-known/agent-card.json"
    openrouter_api_key: str | None = None
    openrouter_model: str = "openai/gpt-4.1-mini"
    agent_context_file: str | None = "/context/AGENTS.md"
    agent_context_command: str | None = None
    agent_context_max_chars: int = 20_000
    agent_workspace_root: str = "/context"
    agent_workspace_max_read_chars: int = 60_000
    agent_workspace_max_list_entries: int = 200
    agent_workspace_max_search_results: int = 20
    agent_workspace_max_search_file_bytes: int = 5_000_000
    agent_tool_max_rounds: int = 6
    agent_spreadsheet_max_rows: int = 500
    agent_spreadsheet_max_columns: int = 100
    tika_url: str = "http://tika:9998"
    tika_timeout_seconds: float = 30.0

    @property
    def rpc_url(self) -> str:
        """Return the absolute A2A JSON-RPC endpoint URL."""
        return join_url(self.agent_base_url, self.agent_rpc_path)


def normalize_path(path: str) -> str:
    """Return a URL path with exactly one leading slash."""
    stripped = path.strip()
    if stripped.startswith("/"):
        return stripped
    return f"/{stripped}"


def join_url(base_url: str, path: str) -> str:
    """Join a base URL and path without duplicate slashes."""
    return f"{base_url.rstrip('/')}{normalize_path(path)}"
