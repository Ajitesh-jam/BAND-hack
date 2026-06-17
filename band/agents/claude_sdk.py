"""Shared Claude Code CLI adapter helpers (no Anthropic API credits required)."""

from __future__ import annotations

from thenvoi.adapters import ClaudeSDKAdapter
from thenvoi.runtime.custom_tools import CustomToolDef

from band.config import get_settings


def claude_agent(
    prompt: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
) -> ClaudeSDKAdapter:
    """Build a ClaudeSDKAdapter using local `claude` CLI auth (subscription), not API billing."""
    settings = get_settings()
    return ClaudeSDKAdapter(
        model=settings.claude_code_model,
        custom_section=prompt,
        additional_tools=additional_tools,
        enable_memory_tools=enable_memory,
        permission_mode=permission_mode,  # type: ignore[arg-type]
    )
