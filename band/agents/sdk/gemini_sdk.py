"""Shared Gemini (Google ADK) adapter helpers.

Uses local Gemini auth via GEMINI_API_KEY / GOOGLE_API_KEY (no Anthropic credits).
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from thenvoi.adapters import GoogleADKAdapter
from thenvoi.runtime.custom_tools import CustomToolDef

from band.agents.context import set_current_room
from band.pipeline_guard import (
    _is_coder_fix_report,
    _is_documentation_handback,
    _is_plan_handoff,
    _msg_text,
    should_respond,
    should_send,
)

logger = logging.getLogger(__name__)

# Rooms that bootstrap within this many seconds of process start are treated as
# pre-existing (synced on connect) and seeded silently. Rooms that appear later
# are genuinely new (e.g. a user just opened a chat) and get the startup brief.
_STARTUP_GRACE_SECONDS = 15.0

# Hard loop-breaker limits, enforced regardless of what the LLM decides to say.
# These stop agents from echo-storming / re-tagging each other indefinitely.
_MAX_SENDS_PER_ROOM = 8          # total messages one agent may post in a room
_DUP_PREFIX_CHARS = 140          # near-duplicate detection on a normalized prefix
# Messages containing these markers are always allowed (terminal/verdict states),
# even past the per-room cap — they END the workflow rather than extend it.
_TERMINAL_MARKERS = (
    "incident_resolved",
    "feature_done",
    "escalate",
    "request_changes",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _artifact_key(norm: str) -> str | None:
    """Identify a structured artifact so re-wording it doesn't bypass dedup.

    The planner kept posting the SAME plan twice with slightly different prose; the
    reviewer could post the same verdict twice. We key these by their logical identity
    (plan + revision number, verdict + round) and allow each to be sent only once.
    """
    if "plan_revision" in norm or "plan_type" in norm:
        m = re.search(r"plan_revision[:=\s]*([0-9]+)", norm)
        rev = m.group(1) if m else "0"
        return f"plan:{rev}"
    if "verdict" in norm or "request_changes" in norm or "approve" in norm:
        m = re.search(r"review_round[^0-9]*([0-9]+)", norm)
        rnd = m.group(1) if m else "final"
        if "request_changes" in norm:
            verdict = "request_changes"
        elif "escalate" in norm:
            verdict = "escalate"
        elif "approve" in norm:
            verdict = "approve"
        else:
            verdict = "verdict"
        return f"verdict:{verdict}:{rnd}"
    return None


class _GuardedTools:
    """Proxy around the runtime tools that throttles outbound messages.

    Drops exact/near-duplicate messages and caps how many messages a single agent
    may post in one room. This is the programmatic backstop that guarantees the
    team cannot get stuck tagging each other forever, independent of the prompt.
    """

    def __init__(
        self,
        inner: Any,
        state: dict[str, dict[str, Any]],
        room_id: str,
        label: str,
        *,
        pipeline_role: str | None = None,
        history: Any = None,
    ) -> None:
        self._inner = inner
        self._state = state.setdefault(
            room_id, {"count": 0, "prefixes": set(), "full": set(), "artifacts": set()}
        )
        self._room_id = room_id
        self._label = label
        self._pipeline_role = pipeline_role
        self._history = history

    def __getattr__(self, name: str) -> Any:
        # Delegate everything except send_message to the real tools object.
        return getattr(self._inner, name)

    async def send_message(self, content: str, mentions: Any = None) -> Any:
        norm = _normalize(content)
        prefix = norm[:_DUP_PREFIX_CHARS]
        is_terminal = any(m in norm for m in _TERMINAL_MARKERS)

        if self._pipeline_role:
            allowed, reason = should_send(self._pipeline_role, content, self._history)
            if not allowed and not is_terminal:
                logger.info(
                    "[pipeline-guard] %s: suppressed send in room %s (%s)",
                    self._label,
                    self._room_id,
                    reason,
                )
                return {"suppressed": reason}

        if norm and (norm in self._state["full"] or prefix in self._state["prefixes"]):
            logger.info(
                "[loop-guard] %s: suppressed duplicate message in room %s",
                self._label, self._room_id,
            )
            return {"suppressed": "duplicate"}

        artifact = _artifact_key(norm) if norm else None
        if artifact and artifact in self._state["artifacts"]:
            logger.info(
                "[loop-guard] %s: suppressed repeat artifact '%s' in room %s",
                self._label, artifact, self._room_id,
            )
            return {"suppressed": "artifact"}

        if self._state["count"] >= _MAX_SENDS_PER_ROOM and not is_terminal:
            logger.info(
                "[loop-guard] %s: suppressed message in room %s (cap %d reached)",
                self._label, self._room_id, _MAX_SENDS_PER_ROOM,
            )
            return {"suppressed": "cap"}

        self._state["count"] += 1
        if norm:
            self._state["full"].add(norm)
            self._state["prefixes"].add(prefix)
            if artifact:
                self._state["artifacts"].add(artifact)
        return await self._inner.send_message(content, mentions)


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
    """GoogleADKAdapter that sanitizes the agent name and can post a startup brief.

    When ``startup_message`` is set, the agent posts it once per room the first
    time it bootstraps that room (e.g. right after a user opens a chat with it),
    then continues with normal message handling.
    """

    def __init__(
        self,
        *args: Any,
        startup_message: str | None = None,
        self_id: str | None = None,
        known_rooms_path: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._startup_message = startup_message
        self._self_id = self_id
        self._start_ts = time.monotonic()
        self._known_rooms_path = Path(known_rooms_path) if known_rooms_path else None
        self._known_rooms: set[str] = self._load_known_rooms()
        # Per-room outbound message state for the loop-breaker.
        self._send_state: dict[str, dict[str, Any]] = {}
        self._pipeline_role: str | None = None

    def set_self_id(self, self_id: str | None) -> None:
        self._self_id = self_id

    def set_pipeline_role(self, role: str | None) -> None:
        self._pipeline_role = role

    def _load_known_rooms(self) -> set[str]:
        if self._known_rooms_path and self._known_rooms_path.exists():
            try:
                return set(json.loads(self._known_rooms_path.read_text()))
            except Exception:  # noqa: BLE001
                return set()
        return set()

    def _remember_room(self, room_id: str) -> None:
        self._known_rooms.add(room_id)
        if not self._known_rooms_path:
            return
        try:
            self._known_rooms_path.parent.mkdir(parents=True, exist_ok=True)
            self._known_rooms_path.write_text(json.dumps(sorted(self._known_rooms)))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not persist known rooms: %s", exc)

    async def on_started(self, agent_name: str, agent_description: str) -> None:
        await super().on_started(agent_name, agent_description)
        self.agent_name = _sanitize_adk_name(self.agent_name)

    async def _maybe_send_brief(self, tools: Any, room_id: str) -> None:
        """Post the capability brief once, only in genuinely new rooms."""
        if not self._startup_message or room_id in self._known_rooms:
            return
        # Rooms seen during the initial connect/sync window are pre-existing.
        if (time.monotonic() - self._start_ts) < _STARTUP_GRACE_SECONDS:
            self._remember_room(room_id)
            return
        self._remember_room(room_id)
        try:
            participants = await tools.get_participants()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Startup brief: could not list participants in %s: %s", room_id, exc)
            return
        mentions: list[str] = []
        for p in participants or []:
            pid = p.get("id") if isinstance(p, dict) else getattr(p, "id", None)
            if pid and pid != self._self_id:
                mentions.append(pid)
        if not mentions:
            return
        try:
            await tools.send_message(self._startup_message, mentions)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to send startup brief in room %s: %s", room_id, exc)

    async def on_message(
        self,
        msg: Any,
        tools: Any,
        history: Any,
        participants_msg: str | None,
        contacts_msg: str | None,
        *,
        is_session_bootstrap: bool,
        room_id: str,
    ) -> None:
        set_current_room(room_id)
        if is_session_bootstrap:
            await self._maybe_send_brief(tools, room_id)

        incoming_preview = (_msg_text(msg) or "")[:120]
        incoming_norm = _normalize(incoming_preview)
        incoming_full = _normalize(_msg_text(msg) or "")
        if self._pipeline_role == "documentation_agent":
            # Band routes @mentions here; respond guard only blocks alerts/non-mentions.
            if incoming_preview and "alert inc-" in incoming_norm:
                logger.info(
                    "[pipeline-guard] %s: skipping watchdog alert in room %s",
                    self._pipeline_role,
                    room_id,
                )
                return
        elif self._pipeline_role == "planner":
            if incoming_preview and "alert inc-" in incoming_norm:
                logger.info(
                    "[pipeline-guard] %s: skipping watchdog alert in room %s",
                    self._pipeline_role,
                    room_id,
                )
                return
            if _is_documentation_handback(msg, incoming_norm):
                pass  # always process documentation_agent handback (incl. @[[uuid]] mentions)
            elif not should_respond(self._pipeline_role, history, msg):
                logger.info(
                    "[pipeline-guard] %s: skipping out-of-turn message in room %s (incoming=%r)",
                    self._pipeline_role,
                    room_id,
                    incoming_preview,
                )
                return
        elif self._pipeline_role == "coder":
            if _is_plan_handoff(incoming_full):
                pass  # planner plan via @[[uuid]] with empty ADK history
            elif not should_respond(self._pipeline_role, history, msg):
                logger.info(
                    "[pipeline-guard] %s: skipping out-of-turn message in room %s (incoming=%r)",
                    self._pipeline_role,
                    room_id,
                    incoming_preview,
                )
                return
        elif self._pipeline_role == "reviewer":
            if _is_coder_fix_report(incoming_full):
                pass  # coder fix report via @[[uuid]] with empty ADK history
            elif not should_respond(self._pipeline_role, history, msg):
                logger.info(
                    "[pipeline-guard] %s: skipping out-of-turn message in room %s (incoming=%r)",
                    self._pipeline_role,
                    room_id,
                    incoming_preview,
                )
                return
        elif self._pipeline_role and not should_respond(self._pipeline_role, history, msg):
            logger.info(
                "[pipeline-guard] %s: skipping out-of-turn message in room %s (incoming=%r)",
                self._pipeline_role,
                room_id,
                incoming_preview,
            )
            return
        guarded = _GuardedTools(
            tools,
            self._send_state,
            room_id,
            self.agent_name,
            pipeline_role=self._pipeline_role,
            history=history,
        )
        await super().on_message(
            msg,
            guarded,
            history,
            participants_msg,
            contacts_msg,
            is_session_bootstrap=is_session_bootstrap,
            room_id=room_id,
        )


def gemini_agent(
    prompt: str,
    model: str,
    *,
    additional_tools: list[CustomToolDef] | None = None,
    enable_memory: bool = False,
    permission_mode: str = "acceptEdits",
    startup_message: str | None = None,
    known_rooms_path: str | None = None,
) -> GoogleADKAdapter:
    """Build a GoogleADKAdapter using local Gemini auth (subscription), not API billing."""
    return _SafeGoogleADKAdapter(
        model=model,
        custom_section=prompt,
        additional_tools=additional_tools,
        enable_memory_tools=enable_memory,
        startup_message=startup_message,
        known_rooms_path=known_rooms_path,
    )
