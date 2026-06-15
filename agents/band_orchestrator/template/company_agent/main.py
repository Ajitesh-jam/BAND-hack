"""Company code-context Band agent — graph RAG + docs RAG for your codebase."""

from __future__ import annotations

import logging

from base import run_generated
from agent_core.prompt import AGENT_PROMPT
from agent_core.tools import get_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [company-context] %(message)s")


def cli() -> None:
    run_generated(AGENT_PROMPT, tools=get_tools(), enable_memory=True)


if __name__ == "__main__":
    cli()
