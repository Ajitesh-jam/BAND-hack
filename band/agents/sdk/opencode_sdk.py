"""OpenCode HTTP server adapter (alternative to Claude Code CLI)."""

from __future__ import annotations

from thenvoi.adapters import OpencodeAdapter, OpencodeAdapterConfig
from thenvoi.runtime.custom_tools import CustomToolDef

from band.config import ROOT_DIR, get_settings


def opencode_agent(
    prompt: str,
    model: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
) -> OpencodeAdapter:
    """Connect to a local OpenCode server (default http://127.0.0.1:4096)."""
    settings = get_settings()
    approval = "auto_accept" if permission_mode == "bypassPermissions" else "manual"
    resolved_model = model or settings.opencode_model
    workdir = str(settings.opencode_workdir or ROOT_DIR)
    config_kwargs: dict = {
        "base_url": settings.opencode_url,
        "directory": workdir,
        "provider_id": settings.opencode_provider_id,
        "model_id": resolved_model,
        "custom_section": prompt,
        "approval_mode": approval,
        "enable_memory_tools": enable_memory,
    }
    return OpencodeAdapter(
        config=OpencodeAdapterConfig(**config_kwargs),
        additional_tools=additional_tools,
    )
