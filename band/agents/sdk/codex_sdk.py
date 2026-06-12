"""Shared Codex Code CLI adapter helpers (no Anthropic API credits required)."""

from __future__ import annotations

from thenvoi.adapters import CodexAdapter, CodexAdapterConfig
from thenvoi.runtime.custom_tools import CustomToolDef


def codex_agent(
    prompt: str,
    model: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
) -> CodexAdapter:
    """Build a CodexAdapter using local `codex` CLI auth (subscription), not API billing."""
    approval_policy = "never" if permission_mode == "bypassPermissions" else "on-request"
    return CodexAdapter(
        config=CodexAdapterConfig(
            model=model,
            custom_section=prompt,
            approval_policy=approval_policy,
        ),
        additional_tools=additional_tools,
    )
