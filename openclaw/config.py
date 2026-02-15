"""Configuration loading from YAML + environment variables + Doppler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class LLMRouteConfig(BaseSettings):
    primary: str = "groq"
    fallbacks: list[str] = Field(default_factory=lambda: ["openai"])


class OpenClawConfig(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8340
    log_level: str = "INFO"

    # API keys (from env / Doppler)
    telegram_bot_token: str = ""
    groq_api_key: str = ""
    nvidia_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    openclaw_api_key: str = ""

    # Connector URLs
    matrix_url: str = "http://localhost:8000"
    jarvis_hosts: dict[str, str] = Field(default_factory=dict)
    cmms_url: str = ""
    cmms_email: str = ""
    cmms_password: str = ""
    plc_host: str = ""
    plc_port: int = 502

    # Channel settings
    telegram_enabled: bool = True
    telegram_allowed_users: list[int] = Field(default_factory=list)
    telegram_rate_limit_per_hour: int = 60
    whatsapp_enabled: bool = False
    http_api_enabled: bool = True
    http_api_require_auth: bool = True
    websocket_enabled: bool = True

    # LLM routing
    default_llm_provider: str = "groq"
    groq_model: str = "llama-3.3-70b-versatile"
    groq_daily_request_limit: int = 14000
    nvidia_model: str = "nvidia/cosmos-reason2-8b"
    nvidia_fallback_model: str = "meta/llama-3.1-70b-instruct"
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.5-flash"

    # LLM routes (populated from YAML)
    llm_routes: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Skills
    plugin_dirs: list[str] = Field(default_factory=list)
    disabled_skills: list[str] = Field(default_factory=list)

    # Security
    tailscale_only: bool = False

    @classmethod
    def from_yaml(cls, path: str | Path = "openclaw.yaml") -> OpenClawConfig:
        """Load config from YAML file, with env vars taking precedence."""
        yaml_path = Path(path)
        yaml_data: dict[str, Any] = {}

        if yaml_path.exists():
            with yaml_path.open("r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            yaml_data = _flatten_yaml(raw.get("openclaw", {}))

        return cls(**yaml_data)


def _flatten_yaml(data: dict, prefix: str = "") -> dict:
    """Flatten nested YAML into flat key-value pairs for Pydantic."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}" if not prefix else f"{prefix}_{key}"
        if isinstance(value, dict) and key not in ("jarvis_hosts", "llm_routes"):
            flat.update(_flatten_yaml(value, full_key))
        else:
            flat[full_key if prefix else key] = value
    return flat
