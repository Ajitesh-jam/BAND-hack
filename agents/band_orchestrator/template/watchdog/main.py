"""Watchdog process — monitors hosted app health and opens incident rooms."""

from __future__ import annotations

import logging

from agents.watchdog.agent_core.helper import _find_peer_id, classify_failure, monitor_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s [watchdog] %(message)s")


def cli() -> None:
    monitor_loop()


if __name__ == "__main__":
    cli()
