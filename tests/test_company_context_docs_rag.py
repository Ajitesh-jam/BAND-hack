"""Tests for company context docs RAG."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

TEMPLATE_ROOT = (
    Path(__file__).resolve().parent.parent
    / "agents"
    / "band_orchestrator"
    / "template"
    / "company_agent"
)
sys.path.insert(0, str(TEMPLATE_ROOT))

from agent_core.docs_rag import build_docs_index, retrieve_docs  # noqa: noqa: E402


def _has_sentence_transformers() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


@pytest.mark.skipif(not _has_sentence_transformers(), reason="sentence-transformers not installed")
def test_build_and_retrieve_docs_rag(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text(
        "The incident commander recruits log analyst first. "
        "Fix engineer uses github_ops for pull requests.",
        encoding="utf-8",
    )
    (docs / "other.md").write_text("Unrelated content about cooking recipes.", encoding="utf-8")
    (tmp_path / "embedding_config.yaml").write_text(
        "model: sentence-transformers/all-MiniLM-L6-v2\n"
        "chunk_size: 200\n"
        "chunk_overlap: 20\n"
        "docs_dir: docs\n"
        "index_path: data/docs_index.json\n"
        "top_k: 2\n",
        encoding="utf-8",
    )

    result = build_docs_index(agent_root=tmp_path)
    assert result["ok"] is True
    assert result["chunk_count"] >= 1

    retrieved = retrieve_docs("github pull request fix engineer", agent_root=tmp_path)
    assert retrieved["ok"] is True
    assert retrieved["chunks"]
    combined = " ".join(c["text"] for c in retrieved["chunks"]).lower()
    assert "github" in combined or "fix engineer" in combined


def test_retrieve_docs_keyword_fallback_without_index(tmp_path):
    retrieved = retrieve_docs("anything", agent_root=tmp_path)
    assert retrieved["ok"] is False
    assert retrieved["mode"] == "none"
