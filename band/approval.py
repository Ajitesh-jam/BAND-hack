"""Human-in-the-loop approval gate helpers.

Two approval channels are supported:
1. Text-based: SRE types "approve" / "LGTM" / "ship it" in the Band chat room.
2. GitHub PR review: SRE approves the PR on GitHub's native PR review UI.
   Detected via check_pr_review_status tool (gh api repos/{repo}/pulls/{n}/reviews).
"""

from __future__ import annotations

import re

APPROVAL_PATTERNS = [
    r"\bapprove[d]?\b",
    r"\blgtm\b",
    r"\bship\s*it\b",
    r"\bgo\s+ahead\b",
    r"\byes\b.*\bdeploy\b",
]

REJECTION_PATTERNS = [
    r"\breject(ed)?\b",
    r"\bdeny\b",
    r"\bhold\b",
    r"\bstop\b",
    r"\bno\b.*\bdeploy\b",
]


def is_approval_message(content: str) -> bool:
    text = content.lower().strip()
    return any(re.search(p, text) for p in APPROVAL_PATTERNS)


def is_rejection_message(content: str) -> bool:
    text = content.lower().strip()
    return any(re.search(p, text) for p in REJECTION_PATTERNS)


def is_github_pr_approved(review_status: dict) -> bool:
    """Check whether a GitHub PR review status dict indicates approval.

    review_status is the return value of github_ops.check_pr_review_status().
    Returns True if is_approved is True and review_state is 'APPROVED'.
    """
    if not review_status.get("ok"):
        return False
    return review_status.get("is_approved", False) and review_status.get("review_state") == "APPROVED"


def is_github_pr_changes_requested(review_status: dict) -> bool:
    """Check whether a GitHub PR review status dict indicates changes requested."""
    if not review_status.get("ok"):
        return False
    return review_status.get("review_state") == "CHANGES_REQUESTED"


SRE_APPROVAL_PROMPT = (
    "Human SRE approval required before merge/deploy. "
    "The SRE can approve by either:\n"
    "  1. Replying in this chat with 'approve' or 'LGTM', OR\n"
    "  2. Approving the PR directly on GitHub's PR review UI.\n"
    "Or reply 'reject' to halt."
)
