"""Compliance Officer agent (LangGraph + AI/ML API, or Claude CLI fallback)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from thenvoi.adapters import LangGraphAdapter

from band.agents.base import create_and_run
from band.agents.claude_sdk import claude_agent
from band.config import get_settings
from band.prompts import COMPLIANCE_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [compliance] %(message)s")


def _aiml_configured() -> bool:
    key = get_settings().aiml_api_key
    return bool(key) and not key.startswith("your-") and key != "your-aiml-api-key"


def build_adapter() -> Any:
    if _aiml_configured():
        settings = get_settings()
        logging.info("Compliance Officer using LangGraph + AI/ML API")
        llm = ChatOpenAI(
            model=settings.aiml_model,
            api_key=settings.aiml_api_key,
            base_url=settings.aiml_base_url,
            temperature=0.1,
        )
        return LangGraphAdapter(
            llm=llm,
            checkpointer=InMemorySaver(),
            custom_section=COMPLIANCE_PROMPT,
        )

    logging.info(
        "Compliance Officer using Claude Code CLI fallback (set AIML_API_KEY after kickoff)"
    )
    return claude_agent(COMPLIANCE_PROMPT)


def cli() -> None:
    create_and_run(build_adapter(), "compliance_officer", "Compliance Officer")


if __name__ == "__main__":
    cli()
