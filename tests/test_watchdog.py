"""Tests for watchdog health checking."""

from __future__ import annotations

from agents.watchdog.main import _find_peer_id, classify_failure


def test_find_peer_id_by_handle():
    peers = [
        {"id": "abc", "handle": "@owner/incident-commander"},
        {"id": "def", "handle": "@owner/log-analyst"},
    ]
    assert _find_peer_id(peers, "incident-commander") == "abc"
    assert _find_peer_id(peers, "log-analyst") == "def"
    assert _find_peer_id(peers, "missing") is None


def test_classify_failure_timeout():
    assert classify_failure({"error": "timed out"}) == "probe_timeout"


def test_classify_failure_chaos_fault():
    assert (
        classify_failure({"body": {"status": "unhealthy", "active_fault": "pool_exhaustion"}})
        == "pool_exhaustion"
    )
