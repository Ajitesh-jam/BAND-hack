"""Tests for strict pipeline turn-taking."""

from __future__ import annotations

from dataclasses import dataclass

from band.pipeline_guard import next_actor, pipeline_state, should_respond, should_send


def _hist(*messages: str) -> list[dict[str, str]]:
    return [{"content": m} for m in messages]


def test_commander_responds_when_alert_mentions_plan_revision():
    """Watchdog instructions must not count as commander kickoff."""
    alert = {
        "content": (
            "ALERT INC-0618-001 - hosted app health failed\n"
            "kick off planner for PLAN_REVISION=0"
        )
    }
    assert should_respond("commander", [], alert)
    assert not should_respond("planner", [], alert)


def test_initial_alert_only_commander_responds():
    history = _hist(
        "ALERT INC-0618-001 - hosted app health failed\nFailure reason: probe_error"
    )
    state = pipeline_state(history)
    assert state["alert"]
    assert not state["commander_kickoff"]
    assert next_actor(state) == "commander"

    alert = history[0]
    assert should_respond("commander", [], alert)
    assert not should_respond("planner", [], alert)
    assert not should_respond("coder", [], alert)
    assert not should_respond("reviewer", [], alert)
    assert not should_respond("documentation_agent", [], alert)


def test_coder_silent_on_alert():
    alert = {"content": "ALERT INC-0618-001 - hosted app health failed"}
    assert not should_respond("coder", [], alert)


def test_planner_responds_to_commander_kickoff():
    history = _hist(
        "ALERT INC-0618-001 - hosted app health failed",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
    )
    kickoff = history[-1]
    assert should_respond("planner", history[:-1], kickoff)
    assert not should_respond("coder", history[:-1], kickoff)
    assert not should_respond("reviewer", history[:-1], kickoff)


def test_planner_responds_to_band_uuid_doc_handback():
    """Band serializes @planner as @[[uuid]] in message bodies."""
    msg = {
        "content": (
            "@[[59305a2e-a60e-40fa-b870-79c07e7f2a16]] I was unable to find any "
            "specific file paths, code-graph impact, or recent commit context."
        ),
        "sender_name": "scribe",
    }
    assert should_respond("planner", [], msg)


def test_planner_responds_to_documentation_agent_reply():
    doc_reply = {
        "content": (
            "@planner Regarding INC-0618-001, Codebase Overview: Python app in docker-compose. "
            "app/main.py co-changed with docker-compose.yml"
        )
    }
    assert should_respond("planner", [], doc_reply)


def test_planner_plan_to_commander_is_blocked():
    plan = (
        "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\nBLOCKED: no doc context\n"
        "@commander please help"
    )
    allowed, reason = should_send("planner", plan, _hist("Relevant file paths: app/main.py"))
    assert not allowed
    assert "commander" in reason or "coder" in reason


def test_plan_posted_requires_coder_mention():
    history = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
        "Relevant file paths: app/main.py",
    )
    plan_to_commander = {
        "content": (
            "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\nGOAL: restore\n@commander blocked"
        )
    }
    assert not pipeline_state(history + [plan_to_commander])["plan_posted"]

    plan_to_coder = {
        "content": (
            "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\nGOAL: restore\n@coder implement"
        )
    }
    assert pipeline_state(history + [plan_to_coder])["plan_posted"]


def test_planner_can_post_plan_with_empty_history():
    plan = (
        "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\nGOAL: restore health\n"
        "FILES_TO_TOUCH: app/main.py\n@coder implement"
    )
    allowed, reason = should_send("planner", plan, [])
    assert allowed, reason


def test_documentation_agent_responds_when_content_empty():
    """Some Band deliveries have empty content but still @mention the agent."""

    @dataclass
    class _EmptyMsg:
        content: str = ""
        id: str = "m1"

        def format_for_llm(self) -> str:
            return "[planner]: @documentation agent file paths for INC-0618-001?"

    assert should_respond("documentation_agent", [], _EmptyMsg())


def test_documentation_agent_responds_when_history_empty():
    """Band often syncs with Got 0 messages — @mention must still trigger doc."""
    question = {
        "content": (
            "@documentation agent What are the real file paths for the health check "
            "endpoint and recent commits?"
        )
    }
    assert should_respond("documentation_agent", [], question)
    allowed, _ = should_send(
        "documentation_agent",
        "Relevant file paths: app/main.py, docker-compose.yml",
        [],
    )
    assert allowed


def test_documentation_agent_responds_to_planner_question():
    history = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
    )
    question = {
        "content": (
            "@documentation agent What are the real file paths for the health check "
            "endpoint and recent commits?"
        )
    }
    assert should_respond("documentation_agent", history, question)
    assert not should_respond("coder", history, question)
    assert not should_respond("reviewer", history, question)


def test_coder_waits_for_plan():
    history = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
        "@documentation agent file paths?",
        "Relevant file paths: app/main.py docker-compose.yml",
    )
    plan = {
        "content": (
            "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\nGOAL: restore health\n"
            "FILES_TO_TOUCH: app/main.py\n@coder implement"
        )
    }
    assert should_respond("coder", history, plan)
    assert not should_respond("reviewer", history, plan)


def test_coder_responds_to_band_uuid_plan():
    msg = {
        "content": (
            "@[[7c955435-6a22-42b5-a3e9-07d11d7d0dc3]] PLAN_TYPE: INCIDENT\n"
            "PLAN_REVISION: 0\nGOAL: restore health\nFILES_TO_TOUCH: app/main.py"
        )
    }
    assert should_respond("coder", [], msg)


def test_reviewer_responds_to_band_uuid_coder_report():
    msg = {
        "content": (
            "@[[83c8eb8d-d6fa-4aad-9fcd-4e04d879f76f]] The incident has been resolved. "
            "Root cause was pool_exhaustion. VERIFICATION: fetch_health status healthy."
        )
    }
    assert should_respond("reviewer", [], msg)


def test_coder_report_detected_without_verification_prefix():
    history = _hist(
        "@[[83c8eb8d-d6fa-4aad-9fcd-4e04d879f76f]] Root cause pool_exhaustion. Health is healthy."
    )
    assert pipeline_state(history)["coder_reported"]


def test_reviewer_waits_for_coder_report():
    history = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
        "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0\n@coder implement",
    )
    early = {"content": "@coder Acknowledged alert. Waiting for commander."}
    assert not should_respond("reviewer", history, early)
    assert not should_send("reviewer", "Could you paste changed files?", history)[0]

    report = {
        "content": (
            "@reviewer Changed files: app/main.py\nVERIFICATION: fetch_health healthy"
        )
    }
    assert should_respond("reviewer", history, report)


def test_commander_approval_after_reviewer_verdict():
    history = _hist(
        "ALERT INC-0618-001",
        "PLAN_TYPE: INCIDENT\nPLAN_REVISION: 0",
        "@reviewer fix done VERIFICATION: healthy",
        "VERDICT: APPROVE @commander human please review critical DB pool change",
    )
    verdict = history[-1]
    assert should_respond("commander", history[:-1], verdict)
    allowed, _ = should_send(
        "commander",
        "Please approve via the notification — INC-0618-001 ready to merge.",
        history,
    )
    assert allowed


def test_suppress_acknowledgements():
    history = _hist("ALERT INC-0618-001")
    allowed, reason = should_send("coder", "@commander Acknowledged alert. Waiting.", history)
    assert not allowed
    assert reason == "acknowledgement"


def test_planner_only_one_doc_question_before_plan():
    history = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
    )
    allowed, _ = should_send(
        "planner",
        "@documentation agent What file paths relate to /health?",
        history,
    )
    assert allowed

    history2 = _hist(
        "ALERT INC-0618-001",
        "@planner produce PLAN_REVISION=0 for INC-0618-001",
        "@documentation agent What file paths relate to /health?",
        "Relevant file paths: app/main.py",
    )
    allowed2, reason2 = should_send(
        "planner",
        "@documentation agent Please provide file paths again?",
        history2,
    )
    assert not allowed2
    assert reason2 == "planner_doc_already_answered"
