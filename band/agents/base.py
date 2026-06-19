"""Shared agent bootstrap utilities."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Optional

from dotenv import load_dotenv
from thenvoi import Agent
from thenvoi.runtime.custom_tools import CustomToolDef
from band.agents.sdk.claude_sdk import claude_agent
from band.agents.sdk.codex_sdk import codex_agent
from band.agents.sdk.gemini_sdk import gemini_agent
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

def adapter_sdk(
    prompt: str,
    adapter_type: Optional[str] = None,
    model: Optional[str] = None,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
    startup_message: Optional[str] = None,
    known_rooms_path: Optional[str] = None,
):
    settings = get_settings()
    if adapter_type is None:
        adapter_type = settings.default_adapter_type
    if adapter_type == "claude":
        if model is None:
            model = settings.claude_code_model
        return claude_agent(
            prompt,
            model,
            additional_tools=additional_tools,
            enable_memory=enable_memory,
            permission_mode=permission_mode,
        )
    if adapter_type == "codex":
        if model is None:
            model = settings.codex_code_model
        return codex_agent(
            prompt,
            model,
            additional_tools=additional_tools,
            enable_memory=enable_memory,
            permission_mode=permission_mode,
        )
    if adapter_type == "gemini":
        if model is None:
            model = settings.gemini_code_model
        return gemini_agent(
            prompt,
            model,
            additional_tools=additional_tools,
            enable_memory=enable_memory,
            permission_mode=permission_mode,
            startup_message=startup_message,
            known_rooms_path=known_rooms_path,
        )
    raise ValueError(f"Invalid adapter type: {adapter_type!r}")


def create_and_run(adapter: Any, agent_name: str, label: str | None = None) -> None:
    creds = load_creds(agent_name)
    settings = get_settings()
    set_self_id = getattr(adapter, "set_self_id", None)
    if callable(set_self_id):
        set_self_id(creds.agent_id)
    set_pipeline_role = getattr(adapter, "set_pipeline_role", None)
    if callable(set_pipeline_role):
        set_pipeline_role(agent_name)
    agent = Agent.create(
        adapter=adapter,
        agent_id=creds.agent_id,
        api_key=creds.api_key,
        ws_url=settings.band_ws_url,
        rest_url=settings.band_rest_url,
    )
    asyncio.run(run_agent(agent, label or agent_name))
