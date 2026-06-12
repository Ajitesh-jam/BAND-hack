"""Human-in-the-loop approval gate helpers."""

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


SRE_APPROVAL_PROMPT = (
    "Human SRE approval required before merge/deploy. "
    "Reply with 'approve' or 'LGTM' to proceed, or 'reject' to halt."
)
