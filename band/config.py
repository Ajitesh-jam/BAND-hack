"""Application configuration loaded from environment."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent

# Default when HOSTED_APP_URL is unset — local Next.js dev server
LOCAL_HOSTED_APP_URL = "http://localhost:3000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_adapter_type: str = Field(default="gemini", validation_alias="DEFAULT_ADAPTER_TYPE")
    claude_code_model: str = "sonnet"
    codex_code_model: str = "codex-3.5-sonnet"
    gemini_code_model: str = "gemini-2.5-flash"

    # Band platform
    band_rest_url: str = "https://app.band.ai"
    band_ws_url: str = "wss://app.band.ai/api/v1/socket/websocket"
    band_human_api_key: str = ""

    # Demo repo (coder/docs clone target)
    demo_app_repo: str = Field(default="", validation_alias="DEMO_APP_REPO")
    company_repo_url: str = Field(default="", validation_alias="COMPANY_REPO_URL")
    demo_app_github_token: str = Field(default="", validation_alias="GITHUB_TOKEN")

    # Hosted app URL — health + logs are polled ONLY from HOSTED_APP_URL in .env
    hosted_app_url: str = Field(default="", validation_alias="HOSTED_APP_URL")

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
    watchdog_health_path: str = "/api/health.json"
    watchdog_health_timeout_s: float = 5.0
    watchdog_health_retries: int = 1
    watchdog_failure_threshold: int = 2

    # Paths
    agent_config_path: Path = ROOT_DIR / "agent_config.yaml"
    workspace_dir: Path = ROOT_DIR / ".workspace"

    # Agent handles (Band @owner/agent-name)
    commander_handle: str = "commander"
    planner_handle: str = "planner"
    coder_handle: str = "coder"
    documentation_handle: str = "documentation-agent"
    log_analyst_handle: str = "log-analyst"
    fix_engineer_handle: str = "fix-engineer"
    reviewer_handle: str = "reviewer"
    github_handle: str = "github-agent"
    compliance_handle: str = "compliance-officer"
    scribe_handle: str = "scribe"
    watchdog_handle: str = "watchdog"
    # Band owner handle prefix for @mentions in prompts (e.g. zoro)
    band_owner_handle: str = ""


def get_working_repo_url(settings: Settings | None = None) -> str:
    """Canonical GitHub URL for planner/coder/docs shared workspace."""
    settings = settings or get_settings()
    return (settings.demo_app_repo or settings.company_repo_url or "").strip()


def get_hosted_app_url(settings: Settings | None = None) -> str:
    """Return HOSTED_APP_URL from .env (required for health/log polling).

    When unset, falls back to http://localhost:3000 for local ``npm run dev``.
    """
    settings = settings or get_settings()
    url = (settings.hosted_app_url or "").strip()
    if not url:
        url = LOCAL_HOSTED_APP_URL
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    return url.rstrip("/")


def get_health_path(settings: Settings | None = None) -> str:
    """Health endpoint path — dynamic /api/health locally, static /api/health.json when hosted."""
    settings = settings or get_settings()
    base = get_hosted_app_url(settings).lower()
    if "localhost" in base or "127.0.0.1" in base:
        return "/api/health"
    return settings.watchdog_health_path or "/api/health.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
