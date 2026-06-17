"""Tests for watchdog health checking."""

from __future__ import annotations

from agents.watchdog.agent_core.helper import _find_peer_id, classify_failure


def test_find_peer_id_by_handle():
    peers = [
        {"id": "abc", "handle": "@owner/band-orchestrator"},
        {"id": "def", "handle": "@owner/watchdog"},
    ]
    assert _find_peer_id(peers, "band-orchestrator") == "abc"
    assert _find_peer_id(peers, "watchdog") == "def"
    assert _find_peer_id(peers, "missing") is None


def test_classify_failure_timeout():
    assert classify_failure({"error": "timed out"}) == "probe_timeout"


def test_classify_failure_chaos_fault():
    assert (
        classify_failure({"body": {"status": "unhealthy", "active_fault": "pool_exhaustion"}})
        == "pool_exhaustion"
    )
