"""Log Analyst agent (LangGraph + Featherless, or Claude CLI fallback)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel, Field
from thenvoi.adapters import LangGraphAdapter
from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.base import create_and_run
from band.agents.claude_sdk import claude_agent
from band.config import get_settings
from band.prompts import LOG_ANALYST_PROMPT
from band.tools import demo_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [log-analyst] %(message)s")


def _featherless_configured() -> bool:
    key = get_settings().featherless_api_key
    return bool(key) and not key.startswith("fn-xxx") and key != "your-featherless-key"


def _make_langchain_tools() -> list[StructuredTool]:
    return [
        StructuredTool.from_function(
            func=demo_app.fetch_logs,
            name="fetch_logs",
            description="Fetch recent structured JSON logs from checkout-api",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_metrics,
            name="fetch_metrics",
            description="Fetch Prometheus metrics from checkout-api",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_chaos_status,
            name="fetch_chaos_status",
            description="Get active fault injection state",
        ),
        StructuredTool.from_function(
            func=demo_app.fetch_health,
            name="fetch_health",
            description="Get current health check response",
        ),
    ]


class FetchLogsInput(BaseModel):
    limit: int = Field(default=100, description="Max log lines")
    level: str | None = Field(default=None, description="Filter by level e.g. ERROR")


class FetchMetricsInput(BaseModel):
    pass


class FetchChaosStatusInput(BaseModel):
    pass


class FetchHealthInput(BaseModel):
    pass


def _make_claude_tools() -> list[CustomToolDef]:
    return [
        (FetchLogsInput, lambda inp: demo_app.fetch_logs(limit=inp.limit, level=inp.level)),
        (FetchMetricsInput, lambda _: demo_app.fetch_metrics()),
        (FetchChaosStatusInput, lambda _: demo_app.fetch_chaos_status()),
        (FetchHealthInput, lambda _: demo_app.fetch_health()),
    ]


def build_adapter() -> Any:
    if _featherless_configured():
        settings = get_settings()
        logging.info("Log Analyst using LangGraph + Featherless")
        llm = ChatOpenAI(
            model=settings.featherless_model,
            api_key=settings.featherless_api_key,
            base_url=settings.featherless_base_url,
            temperature=0.1,
        )
        return LangGraphAdapter(
            llm=llm,
            checkpointer=InMemorySaver(),
            additional_tools=_make_langchain_tools(),
            custom_section=LOG_ANALYST_PROMPT,
        )

    logging.info("Log Analyst using Claude Code CLI fallback (set FEATHERLESS_API_KEY for LangGraph)")
    return claude_agent(LOG_ANALYST_PROMPT, additional_tools=_make_claude_tools())


def cli() -> None:
    create_and_run(build_adapter(), "log_analyst", "Log Analyst")


if __name__ == "__main__":
    cli()
