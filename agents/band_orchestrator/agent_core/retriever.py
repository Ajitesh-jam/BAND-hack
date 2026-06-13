"""Lightweight Band SDK documentation retriever.

A dependency-free replacement for the old FAISS/LangChain RAG pipeline. The
bundled ``docs/band_sdk.md`` is split into heading-delimited sections and scored
against the query with a simple token-overlap heuristic. This keeps the
orchestrator self-contained (no vector store, no embeddings API) while still
giving the code generator relevant SDK context.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_PATH = Path(__file__).resolve().parent / "docs" / "band_sdk.md"

_TOP_K = 6
_MAX_SECTION_CHARS = 2_000
_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "with", "is", "are",
    "band", "agent", "agents", "sdk", "using", "use", "via", "your", "you",
}


@lru_cache(maxsize=1)
def _sections() -> list[tuple[str, str]]:
    """Return [(heading, body)] parsed from the markdown docs."""
    if not DOCS_PATH.exists():
        logger.warning("Band SDK docs not found at %s", DOCS_PATH)
        return []

    text = DOCS_PATH.read_text(encoding="utf-8", errors="replace")
    # Split on markdown headings while keeping the heading line with its body.
    parts = re.split(r"(?m)^(#{1,4}\s+.*)$", text)
    sections: list[tuple[str, str]] = []

    # parts = [pre, heading1, body1, heading2, body2, ...]
    preamble = parts[0].strip()
    if preamble:
        sections.append(("Overview", preamble))
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i].lstrip("# ").strip()
        body = parts[i + 1].strip()
        if body:
            sections.append((heading, body))
    return sections


def _tokens(text: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", text.lower())
        if t not in _STOPWORDS and len(t) > 2
    }


def retrieve_context(query: str, top_k: int = _TOP_K) -> str:
    """Return the most relevant Band SDK doc sections for ``query``."""
    sections = _sections()
    if not sections:
        return ""

    query_tokens = _tokens(query)
    if not query_tokens:
        scored = list(enumerate(sections))[:top_k]
    else:
        ranked = sorted(
            enumerate(sections),
            key=lambda item: _score(query_tokens, item[1]),
            reverse=True,
        )
        scored = [item for item in ranked if _score(query_tokens, item[1]) > 0][:top_k]
        if not scored:
            scored = ranked[:top_k]

    chunks: list[str] = []
    for _, (heading, body) in scored:
        snippet = body[:_MAX_SECTION_CHARS]
        chunks.append(f"## {heading}\n{snippet}")
    return "\n\n---\n\n".join(chunks)


def _score(query_tokens: set[str], section: tuple[str, str]) -> int:
    heading, body = section
    body_tokens = _tokens(heading + " " + body)
    # Heading matches count double — they're strong topical signals.
    heading_tokens = _tokens(heading)
    return len(query_tokens & body_tokens) + len(query_tokens & heading_tokens)
