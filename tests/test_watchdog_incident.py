"""Tests for watchdog incident room creation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.watchdog.agent_core.helper import open_incident_room


def test_incident_alert_mentions_only_commander():
    client = MagicMock()
    client.create_chat.return_value = {"id": "room-1"}
    client.list_peers.return_value = [
        {"id": "cmd-1", "handle": "@owner/incident-commander", "name": "incident-commander"},
        {"id": "plan-1", "handle": "@owner/log-analyst", "name": "log-analyst"},
        {"id": "doc-1", "handle": "@owner/scribe", "name": "scribe"},
        {"id": "cod-1", "handle": "@owner/fix-engineer", "name": "fix-engineer"},
        {"id": "rev-1", "handle": "@owner/reviewer", "name": "reviewer"},
    ]
    client.add_participant.return_value = None

    health = {
        "healthy": False,
        "error": "[Errno 61] Connection refused",
        "url": "http://localhost:3000/health",
        "failure_reason": "probe_error",
        "body": {"severity": "critical"},
    }

    with patch("agents.watchdog.agent_core.helper._fetch_chaos_status", return_value=None):
        open_incident_room(client, health)

    client.send_message.assert_called_once()
    args, kwargs = client.send_message.call_args
    content = args[1]
    mentions = kwargs.get("mentions") or (args[2] if len(args) > 2 else [])

    assert len(mentions) == 1
    assert mentions[0]["id"] == "cmd-1"
    assert "@log-analyst" not in content
    assert "@scribe" not in content
    assert "@fix-engineer" not in content
    assert "@reviewer" not in content
    assert "incident-commander" in content
