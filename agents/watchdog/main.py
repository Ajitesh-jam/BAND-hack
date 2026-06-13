"""Watchdog: monitors demo-app health and opens Band incident rooms (no LLM)."""

from __future__ import annotations

import logging
import sys

from agents.watchdog.agent_core.helper import monitor_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [watchdog] %(message)s")
logger = logging.getLogger(__name__)


def cli() -> None:
    try:
        monitor_loop()
    except KeyboardInterrupt:
        logger.info("Watchdog stopped")
        sys.exit(0)


if __name__ == "__main__":
    cli()
