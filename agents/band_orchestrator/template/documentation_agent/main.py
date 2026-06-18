"""Company documentation Band agent — graph RAG + docs RAG + commit graph."""

from __future__ import annotations

import logging

from band.prompts import DOCUMENTATION_PROMPT
from base import run_generated
from agent_core.tools import get_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [documentation-agent] %(message)s")


def cli() -> None:
    run_generated(DOCUMENTATION_PROMPT, tools=get_tools(), enable_memory=True)


if __name__ == "__main__":
    cli()
