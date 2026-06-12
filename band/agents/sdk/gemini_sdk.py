"""Shared Gemini Code CLI adapter helpers (no Anthropic API credits required)."""

from __future__ import annotations

from thenvoi.adapters import GoogleADKAdapter
from thenvoi.runtime.custom_tools import CustomToolDef

def gemini_agent(
    prompt: str,
    model: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
) -> GoogleADKAdapter:
    """Build a GoogleADKAdapter using local `google` CLI auth (subscription), not API billing."""
    return GoogleADKAdapter(
        model=model,
        custom_section=prompt,
        additional_tools=additional_tools,
        enable_memory_tools=enable_memory,
    )
