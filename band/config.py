"""Application configuration loaded from environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_adapter_type: str = "opencode"
    claude_code_model: str = "sonnet"
    codex_code_model: str = "codex-3.5-sonnet"
    gemini_code_model: str = "gemini-2.5-flash"
    opencode_provider_id: str = "opencode"
    opencode_model: str = "north-mini-code-free"
    opencode_url: str = "http://127.0.0.1:4096"
    opencode_workdir: Path = ROOT_DIR
    opencode_turn_timeout_s: float = 600.0

    # Per-role models / adapters (OpenCode free fast models — north-mini-code-free)
    orchestrator_model: str = "north-mini-code-free"
    planner_model: str = "north-mini-code-free"
    coder_model: str = "north-mini-code-free"
    reviewer_model: str = "north-mini-code-free"
    company_agent_model: str = "north-mini-code-free"
    merger_model: str = "north-mini-code-free"
    reviewer_adapter: str = "opencode"
    coder_adapter: str = "opencode"
    planner_adapter: str = "opencode"
    orchestrator_adapter: str = "opencode"
    company_agent_adapter: str = "opencode"
    merger_adapter: str = "opencode"
    big_repo_file_threshold: int = 150
    review_max_rounds: int = 3

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
    orchestrator_handle: str = "band-orchestrator"
    company_agent_handle: str = "company-agent"
    planner_handle: str = "planner"
    coder_handle: str = "coder"
    reviewer_handle: str = "reviewer"
    merger_handle: str = "merger"
    watchdog_handle: str = "watchdog"
    band_owner_handle: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
