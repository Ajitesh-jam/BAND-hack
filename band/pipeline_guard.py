"""Strict turn-based guard for the company-agent incident pipeline.

Ensures only the agent whose step is active may respond or send messages.
This is the programmatic backstop on top of band/prompts.py.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Canonical roles used by run_all / agent_config (legacy aliases resolved elsewhere).
ROLES = frozenset(
    {"commander", "planner", "documentation_agent", "coder", "reviewer", "watchdog"}
)

_ACK_PHRASES = (
    "acknowledged",
    "understood",
    "will do",
    "waiting for",
    "thanks",
    "thank you",
    "got it",
    "noted",
)
_ACK_EXACT = frozenset({"ready", "ok", "okay"})


def _is_acknowledgement(text: str) -> bool:
    norm = _normalize(text)
    if norm in _ACK_EXACT:
        return True
    return any(p in norm for p in _ACK_PHRASES)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _msg_text(msg: Any) -> str:
    if isinstance(msg, dict):
        for key in ("content", "text", "body", "message"):
            val = msg.get(key)
            if val:
                return str(val)
        return ""

    for attr in ("content", "text", "body"):
        val = getattr(msg, attr, None)
        if val:
            return str(val)

    fmt = getattr(msg, "format_for_llm", None)
    if callable(fmt):
        formatted = str(fmt())
        if "]: " in formatted:
            return formatted.split("]: ", 1)[-1]
        return formatted
    return ""


def _history_texts(history: Iterable[Any] | None) -> list[str]:
    return [_normalize(_msg_text(m)) for m in (history or [])]


def _has(texts: list[str], *patterns: str) -> bool:
    return any(p in t for t in texts for p in patterns)


def _non_alert_texts(texts: list[str]) -> list[str]:
    """Watchdog alerts mention PLAN_REVISION=0 as instruction — not an actual kickoff."""
    return [t for t in texts if "alert inc-" not in t]


def pipeline_state(history: Iterable[Any] | None) -> dict[str, bool]:
    """Derive which pipeline milestones have already happened in the room."""
    texts = _history_texts(history)
    actionable = _non_alert_texts(texts)
    return {
        "alert": _has(texts, "alert inc-"),
        "commander_kickoff": _has(
            actionable,
            "plan_revision=0",
            "plan_revision: 0",
            "plan_revision:0",
        ),
        "planner_asked_doc": _has(
            texts,
            "documentation agent",
            "documentation_agent",
            "@scribe",
        )
        and _has(texts, "file path", "code-graph", "code graph", "commit context", "recent commit"),
        "doc_answered": _doc_answered_in(texts),
        "plan_posted": _plan_posted_in(actionable),
        "coder_reported": _coder_reported_in(texts),
        "reviewer_verdict": _has(texts, "verdict:", "review_round")
        or (_has(texts, "approve", "request_changes", "escalate") and _has(texts, "commander")),
        "commander_approval_asked": _has(
            texts,
            "approval needed",
            "desktop notification",
            "one-click",
            "request_approval",
        ),
        "human_approved": _has(texts, "human approved"),
        "human_rejected": _has(texts, "human rejected"),
        "coder_pr_done": _has(
            texts,
            "pr url",
            "pull request",
            "compare url",
            "openpr",
            "pr skipped",
        ),
        "resolved": _has(texts, "incident_resolved", "feature_done"),
        "request_changes": _has(texts, "request_changes"),
    }


def next_actor(state: dict[str, bool]) -> str | None:
    """Return the role that should act next, or None if the workflow is finished."""
    if state["resolved"] or state["human_rejected"]:
        return None
    if state["human_approved"] and not state["coder_pr_done"]:
        return "coder"
    if state["reviewer_verdict"] and not state["commander_approval_asked"]:
        if state["request_changes"] and not state.get("_coder_revised"):
            return "coder"
        return "commander"
    if state["coder_reported"] and not state["reviewer_verdict"]:
        return "reviewer"
    if state["plan_posted"] and not state["coder_reported"]:
        return "coder"
    if state["doc_answered"] and not state["plan_posted"]:
        return "planner"
    if state["planner_asked_doc"] and not state["doc_answered"]:
        return "documentation_agent"
    if state["commander_kickoff"] and not state["planner_asked_doc"]:
        return "planner"
    if state["alert"] and not state["commander_kickoff"]:
        return "commander"
    if state["coder_pr_done"] and not state["resolved"]:
        return "commander"
    return None


def _msg_sender(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("sender_name") or msg.get("sender_type") or msg.get("sender_id") or "")
    return str(
        getattr(msg, "sender_name", None)
        or getattr(msg, "sender_type", None)
        or getattr(msg, "sender_id", None)
        or ""
    )


def _is_structured_plan(text: str) -> bool:
    norm = _normalize(text)
    return "plan_type:" in norm and "plan_revision:" in norm


def _plan_targets_coder(text: str) -> bool:
    """A posted plan must hand off to coder, not commander or others."""
    return _is_structured_plan(text) and (
        _mentions_role(text, "coder") or _has_band_uuid_mention(text)
    )


def _planner_blocked_to_commander(text: str) -> bool:
    norm = _normalize(text)
    return "blocked:" in norm and _mentions_role(text, "commander")


def _has_band_uuid_mention(text: str) -> bool:
    """Band encodes @mentions as @[[agent-uuid]] in message bodies."""
    return "@[[ " in text or "@[[" in text


def _plan_posted_in(texts: list[str]) -> bool:
    """Plan is posted only when structured AND handed to coder."""
    return any(_plan_targets_coder(t) for t in texts)


def _is_documentation_sender(msg: Any) -> bool:
    sender = _normalize(_msg_sender(msg))
    return any(
        token in sender
        for token in ("scribe", "documentation agent", "documentation-agent", "documentation_agent")
    )


def _is_documentation_handback(incoming_msg: Any, incoming: str) -> bool:
    """Documentation agent reply that should trigger planner to draft the plan."""
    if _is_documentation_sender(incoming_msg):
        return True
    if not incoming:
        return False
    doc_reply = _has(
        [incoming],
        "file paths",
        "code-graph",
        "code graph",
        "codebase overview",
        "co-changed",
        "unable to find",
        "recent commit",
        "regarding inc-",
        "commit context",
    )
    return doc_reply and (_mentions_role(incoming, "planner") or _has_band_uuid_mention(incoming))


def _mentions_role(text: str, role: str) -> bool:
    norm = _normalize(text)
    aliases = {
        "commander": ("commander", "incident-commander", "incident commander"),
        "planner": ("planner", "log-analyst", "log analyst"),
        "documentation_agent": (
            "documentation agent",
            "documentation-agent",
            "documentation_agent",
            "scribe",
        ),
        "coder": ("coder", "fix-engineer", "fix engineer"),
        "reviewer": ("reviewer",),
    }
    return any(a in norm for a in aliases.get(role, (role,)))


def _is_plan_handoff(text: str) -> bool:
    """Planner plan delivered to coder — Band may serialize @coder as @[[uuid]]."""
    return _is_structured_plan(text) and (
        _mentions_role(text, "coder") or _has_band_uuid_mention(text)
    )


def _is_coder_fix_report(text: str) -> bool:
    """Coder handoff to reviewer — Band may serialize @reviewer as @[[uuid]]."""
    norm = _normalize(text)
    if not (_mentions_role(text, "reviewer") or _has_band_uuid_mention(text)):
        return False
    return _has(
        [norm],
        "verification:",
        "changed files",
        "changed_files:",
        "fetch_health",
        "health status",
        "chaos fault",
        "pool_exhaustion",
        "restore_service",
        "has been resolved",
        "root cause",
        "status\":\"healthy",
        "status: healthy",
        "healthy",
    )


def _coder_reported_in(texts: list[str]) -> bool:
    return any(_is_coder_fix_report(t) for t in texts)


def _doc_answered_in(texts: list[str]) -> bool:
    return _has(
        texts,
        "relevant_file_paths:",
        "relevant file paths",
        "context_used:",
        "codebase overview",
        "co-changed",
        "regarding inc-",
        "unable to find",
        "commit context",
        "code_graph_impact:",
    ) or (
        _has(texts, "app/main.py")
        and _has(texts, "docker-compose", "commit", "docker-compose.yml", "app/chaos")
    )


def _direct_respond(role: str, incoming: str, history: Iterable[Any] | None) -> bool | None:
    """Fast path when Band delivers a message with empty/incomplete history.

    Returns True/False to short-circuit, or None to fall through to full pipeline state.
    """
    hist_texts = _history_texts(history)
    actionable = _non_alert_texts(hist_texts)

    if role == "documentation_agent":
        if _mentions_role(incoming, "documentation_agent"):
            return not _doc_answered_in(hist_texts)
        return None

    if role == "commander":
        if "alert inc-" in incoming and not _has(
            actionable, "plan_revision=0", "plan_revision: 0", "plan_revision:0"
        ):
            return True
        return None

    if role == "planner":
        if "alert inc-" in incoming:
            return None
        if _mentions_role(incoming, "planner") or "plan_revision=0" in incoming:
            if not _has(actionable, "plan_type:", "plan_revision:"):
                return True
        return None

    if role == "coder":
        if _is_plan_handoff(incoming):
            return not _has(hist_texts, "verification:", "changed files", "changed_files:")
        return None

    if role == "reviewer":
        if _mentions_role(incoming, "reviewer") or _has_band_uuid_mention(incoming):
            if _is_coder_fix_report(incoming):
                return not _has(hist_texts, "verdict:", "review_round")
        return None

    return None


def should_respond(role: str, history: Iterable[Any] | None, incoming_msg: Any) -> bool:
    """Return True if this role may process/respond to the incoming message."""
    if role not in ROLES or role == "watchdog":
        return False

    incoming = _normalize(_msg_text(incoming_msg))

    # Documentation agent is only invoked for @mentions; never block on empty ADK history.
    if role == "documentation_agent":
        if incoming and "alert inc-" in incoming:
            return False
        if incoming and not _mentions_role(incoming, "documentation_agent"):
            return False
        return not _doc_answered_in(_history_texts(history))

    # Planner is @mentioned for kickoff and again when documentation_agent replies.
    if role == "planner":
        if not incoming or "alert inc-" in incoming:
            return False
        hist_texts = _history_texts(history)
        actionable = _non_alert_texts(hist_texts)
        if _has(actionable, "plan_type:", "plan_revision:"):
            return _has(hist_texts, "request_changes") and (
                _mentions_role(incoming, "planner") or _is_documentation_handback(incoming_msg, incoming)
            )
        if _mentions_role(incoming, "planner") or "plan_revision=0" in incoming:
            return True
        if _is_documentation_handback(incoming_msg, incoming):
            return True
        return False

    # Coder is @mentioned when planner posts the plan; history is often empty.
    if role == "coder":
        if not incoming or "alert inc-" in incoming:
            return False
        if _is_plan_handoff(incoming):
            return not _has(
                _history_texts(history),
                "verification:",
                "changed files",
                "changed_files:",
            )
        return False

    # Reviewer is @mentioned for coder fix reports; history is often empty.
    if role == "reviewer":
        if not incoming:
            return False
        if _mentions_role(incoming, "reviewer") or _has_band_uuid_mention(incoming):
            if _is_coder_fix_report(incoming):
                return not _has(_history_texts(history), "verdict:", "review_round")
        return False

    if not incoming:
        return False

    direct = _direct_respond(role, incoming, history)
    if direct is not None:
        return direct

    combined = list(history or []) + [incoming_msg]
    state = pipeline_state(combined)
    actor = next_actor(state)
    if actor is None:
        return False
    if role != actor:
        return False

    # Role-specific triggers: must match the message that advances their step.
    if role == "commander":
        if not state["commander_kickoff"]:
            return "alert inc-" in incoming
        if state["reviewer_verdict"] and not state["commander_approval_asked"]:
            return _mentions_role(incoming, "commander") or "verdict" in incoming
        if state["coder_pr_done"] and not state["resolved"]:
            return state["human_approved"] or "human approved" in incoming
        return False

    if role == "planner":
        if not state["planner_asked_doc"]:
            return _mentions_role(incoming, "planner") or "plan_revision=0" in incoming
        if not state["plan_posted"]:
            return state["doc_answered"] or _mentions_role(incoming, "planner")
        return state["request_changes"] and _mentions_role(incoming, "planner")

    if role == "documentation_agent":
        return _mentions_role(incoming, "documentation_agent") or (
            state["planner_asked_doc"] and not state["doc_answered"]
        )

    if role == "coder":
        if not state["coder_reported"]:
            return state["plan_posted"] and (
                _mentions_role(incoming, "coder")
                or "plan_revision" in incoming
                or _is_plan_handoff(incoming)
            )
        if state["human_approved"] and not state["coder_pr_done"]:
            return "human approved" in incoming or _mentions_role(incoming, "coder")
        if state["request_changes"]:
            return _mentions_role(incoming, "coder") or "request_changes" in incoming
        return False

    if role == "reviewer":
        return state["coder_reported"] and (
            _mentions_role(incoming, "reviewer")
            or "verification" in incoming
            or _is_coder_fix_report(incoming)
        )

    return False


def should_send(role: str, content: str, history: Iterable[Any] | None) -> tuple[bool, str]:
    """Return (allowed, reason) for an outbound message from role."""
    norm = _normalize(content)
    if not norm:
        return False, "empty"

    if _is_acknowledgement(norm):
        return False, "acknowledgement"

    # Documentation answers are always allowed once engaged — history is often empty.
    if role == "documentation_agent":
        return True, "ok"

    # Structured pipeline messages must not depend on ADK history being complete.
    if role == "planner":
        if "plan_type:" in norm and "plan_revision:" in norm:
            if not _plan_targets_coder(norm):
                return False, "planner_plan_must_mention_coder"
            return True, "ok"
        if _planner_blocked_to_commander(norm):
            return False, "planner_must_not_block_to_commander"
        if _mentions_role(norm, "documentation_agent"):
            if _doc_answered_in(_history_texts(history)):
                return False, "planner_doc_already_answered"
            return True, "ok"

    if role == "commander":
        if "plan_revision=0" in norm.replace(" ", ""):
            return True, "ok"
        if "incident_resolved" in norm or "feature_done" in norm:
            return True, "ok"

    if role == "coder" and (_mentions_role(norm, "reviewer") or _has_band_uuid_mention(norm)):
        return True, "ok"

    if role == "reviewer" and _mentions_role(norm, "commander") and (
        "verdict" in norm or "approve" in norm or "request_changes" in norm
    ):
        return True, "ok"

    state = pipeline_state(history)
    actor = next_actor(state)
    if actor is None:
        return False, "workflow_complete"
    if role != actor:
        return False, f"not_your_turn (next={actor})"

    if role == "commander":
        if not state["commander_kickoff"]:
            if "plan_revision=0" in norm.replace(" ", "") or "plan_revision=0" in norm:
                return True, "ok"
            return False, "commander_must_kickoff_planner"
        if state["reviewer_verdict"] and not state["commander_approval_asked"]:
            return True, "ok"
        if state["coder_pr_done"]:
            return "incident_resolved" in norm or "feature_done" in norm, "commander_close"
        return False, "commander_no_step"

    if role == "planner":
        if not state["plan_posted"]:
            if state["planner_asked_doc"] and not state["doc_answered"]:
                return False, "planner_wait_for_doc"
            if _is_structured_plan(norm):
                if not _plan_targets_coder(norm):
                    return False, "planner_plan_must_mention_coder"
                return True, "ok"
            if _planner_blocked_to_commander(norm):
                return False, "planner_must_not_block_to_commander"
            if _mentions_role(norm, "documentation_agent"):
                return True, "ok"
            return False, "planner_must_post_plan"
        if state["request_changes"]:
            return "plan_revision:" in norm, "planner_revision_only"
        return False, "planner_done"

    if role == "coder":
        if state["human_approved"]:
            return True, "ok"
        if not state["coder_reported"]:
            return _mentions_role(norm, "reviewer"), "coder_must_hand_to_reviewer"
        return True, "ok"

    if role == "reviewer":
        return (
            "verdict" in norm or "approve" in norm or "request_changes" in norm
        ) and _mentions_role(norm, "commander"), "reviewer_verdict_to_commander"

    return False, "unknown_role"
