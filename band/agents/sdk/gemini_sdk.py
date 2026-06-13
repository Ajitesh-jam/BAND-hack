"""Shared Gemini (Google ADK) adapter helpers.

Uses local Gemini auth via GEMINI_API_KEY / GOOGLE_API_KEY (no Anthropic credits).
"""

from __future__ import annotations

import re

from thenvoi.adapters import GoogleADKAdapter
from thenvoi.runtime.custom_tools import CustomToolDef


def _sanitize_adk_name(name: str) -> str:
    """Google ADK requires the agent name to be a valid Python identifier.

    Band display names may contain spaces or hyphens (e.g. "My test Agent"),
    which crash ADK's LlmAgent validation. Coerce to a safe identifier.
    """
    safe = re.sub(r"[^0-9a-zA-Z_]", "_", name or "").strip("_")
    if not safe or not (safe[0].isalpha() or safe[0] == "_"):
        safe = f"agent_{safe}" if safe else "thenvoi_agent"
    return safe


class _SafeGoogleADKAdapter(GoogleADKAdapter):
    """GoogleADKAdapter that sanitizes the agent name to a valid identifier."""

    async def on_started(self, agent_name: str, agent_description: str) -> None:
        await super().on_started(agent_name, agent_description)
        self.agent_name = _sanitize_adk_name(self.agent_name)


def gemini_agent(
    prompt: str,
    model: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
) -> GoogleADKAdapter:
    """Build a GoogleADKAdapter using local Gemini auth (subscription), not API billing."""
    return _SafeGoogleADKAdapter(
        model=model,
        custom_section=prompt,
        additional_tools=additional_tools,
        enable_memory_tools=enable_memory,
    )
