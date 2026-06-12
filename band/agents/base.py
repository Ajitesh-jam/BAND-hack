"""Shared agent bootstrap utilities."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from dotenv import load_dotenv
from thenvoi import Agent

from band.config import get_settings
from band.registry import AgentCredentials, load_agent_config

logger = logging.getLogger(__name__)


def bootstrap_env() -> None:
    load_dotenv()
    settings = get_settings()
    os.environ.setdefault("THENVOI_REST_URL", settings.band_rest_url)
    os.environ.setdefault("THENVOI_WS_URL", settings.band_ws_url)


def load_creds(agent_name: str) -> AgentCredentials:
    bootstrap_env()
    return load_agent_config(agent_name)


async def run_agent(agent: Agent, label: str) -> None:
    logger.info("Starting %s (%s)", label, agent.agent_name)
    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Shutting down %s", label)
        await agent.stop()


def create_and_run(adapter: Any, agent_name: str, label: str | None = None) -> None:
    creds = load_creds(agent_name)
    settings = get_settings()
    agent = Agent.create(
        adapter=adapter,
        agent_id=creds.agent_id,
        api_key=creds.api_key,
        ws_url=settings.band_ws_url,
        rest_url=settings.band_rest_url,
    )
    asyncio.run(run_agent(agent, label or agent_name))
