"""Log Analyst agent (LangGraph + Featherless, or Claude CLI fallback)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from thenvoi.adapters import LangGraphAdapter

from band.agents.base import adapter_sdk, create_and_run
from band.config import get_settings
from band.prompts import LOG_ANALYST_PROMPT
from band.tools import demo_app
from agents.log_analyst.agent_core.helper import _featherless_configured, _make_langchain_tools, _make_claude_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [log-analyst] %(message)s")


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

    logging.info("Log Analyst using SDK fallback (set FEATHERLESS_API_KEY for LangGraph)")
    return adapter_sdk(LOG_ANALYST_PROMPT, additional_tools=_make_claude_tools())


def cli() -> None:
    create_and_run(build_adapter(), "log_analyst", "Log Analyst")


if __name__ == "__main__":
    cli()
