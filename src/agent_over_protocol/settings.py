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

    agent_name: str = "Danny"
    agent_description: str = "Danny's async A2A agent backed by OpenRouter."
    agent_version: str = "0.1.0"
    agent_base_url: str = "http://localhost:8000"
    agent_rpc_path: str = "/danny/a2a"
    agent_card_path: str = "/.well-known/danny.json"
    agent_standard_card_path: str = "/.well-known/danny-agent-card.json"
    openrouter_api_key: str | None = None

    @property
    def rpc_url(self) -> str:
        """Return the absolute A2A JSON-RPC endpoint URL."""
        return self.join(self.agent_rpc_path)

    def join(self, path: str) -> str:
        """Return an absolute URL for a local path."""
        return join_url(self.agent_base_url, path)


def normalize_path(path: str) -> str:
    """Return a URL path with exactly one leading slash."""
    stripped = path.strip()
    if stripped.startswith("/"):
        return stripped
    return f"/{stripped}"


def join_url(base_url: str, path: str) -> str:
    """Join a base URL and path without duplicate slashes."""
    return f"{base_url.rstrip('/')}{normalize_path(path)}"
