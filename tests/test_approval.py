"""Tests for human approval gate."""

from __future__ import annotations

from band.approval import is_approval_message, is_rejection_message


def test_approval_detection():
    assert is_approval_message("LGTM, ship it")
    assert is_approval_message("I approve the deploy")
    assert not is_approval_message("still investigating")


def test_rejection_detection():
    assert is_rejection_message("reject this fix")
    assert not is_rejection_message("approve")
