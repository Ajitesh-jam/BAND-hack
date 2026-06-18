"""Local bootstrap for company code-context Band agent."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv
from thenvoi import Agent

from band.agents.base import adapter_sdk
from band.config import get_settings
from band.registry import load_agent_config

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parent


def load_local_creds() -> dict:
    cfg_path = AGENT_ROOT / "agent_config.yaml"
    if cfg_path.exists():
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return data["agent"]
    creds = load_agent_config("documentation_agent")
    return {"agent_id": creds.agent_id, "api_key": creds.api_key}


def run_generated(prompt: str, *, tools=None, enable_memory: bool = True) -> None:
    load_dotenv()
    creds = load_local_creds()
    settings = get_settings()
    adapter = adapter_sdk(
        prompt,
        additional_tools=tools or None,
        enable_memory=enable_memory,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=creds["agent_id"],
        api_key=creds["api_key"],
        ws_url=settings.band_ws_url,
        rest_url=settings.band_rest_url,
    )
    asyncio.run(agent.run())
