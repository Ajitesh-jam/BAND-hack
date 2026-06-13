"""Application configuration loaded from environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    default_adapter_type: str =os.getenv("DEFAULT_ADAPTER_TYPE", "claude")
    claude_code_model: str = "sonnet"
    codex_code_model: str = "codex-3.5-sonnet"
    gemini_code_model: str = "gemini-2.5-flash"

    # Band platform
    band_rest_url: str = "https://app.band.ai"
    band_ws_url: str = "wss://app.band.ai/api/v1/socket/websocket"
    band_human_api_key: str = ""

    # Demo target
    demo_app_url: str = "http://localhost:8080"
    demo_app_repo: str = ""
    demo_app_github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")

    # Repo where newly generated agents are published via PR (falls back to demo_app_repo)
    agents_repo: str = Field(default="", validation_alias="AGENTS_REPO")

    # LLM providers
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    featherless_api_key: str = Field(default="", validation_alias="FEATHERLESS_API_KEY")
    featherless_base_url: str = "https://api.featherless.ai/v1"
    featherless_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    aiml_api_key: str = Field(default="", validation_alias="AIML_API_KEY")
    aiml_base_url: str = "https://api.aimlapi.com/v1"
    aiml_model: str = "gpt-4o-mini"

    # Watchdog
    watchdog_poll_interval_s: float = 5.0
    watchdog_health_path: str = "/health"
    watchdog_health_timeout_s: float = 5.0
    watchdog_health_retries: int = 1
    watchdog_failure_threshold: int = 2

    # Paths
    agent_config_path: Path = ROOT_DIR / "agent_config.yaml"
    workspace_dir: Path = ROOT_DIR / ".workspace"

    # Agent handles (Band @owner/agent-name)
    commander_handle: str = "incident-commander"
    log_analyst_handle: str = "log-analyst"
    fix_engineer_handle: str = "fix-engineer"
    reviewer_handle: str = "reviewer"
    compliance_handle: str = "compliance-officer"
    scribe_handle: str = "scribe"
    watchdog_handle: str = "watchdog"
    # Band owner handle prefix for @mentions in prompts (e.g. zoro)
    band_owner_handle: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
