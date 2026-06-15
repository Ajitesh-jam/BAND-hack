"""Docs RAG — chunk, embed, and retrieve from the docs/ folder."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from agent_core.embedding import embed_query, load_embedding_config

AGENT_ROOT = Path(__file__).resolve().parent.parent

_STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "in", "for", "with", "is", "are",
    "your", "you", "this", "that", "from", "on", "at", "by", "as", "be",
}

_TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".csv"}


def _agent_path(rel: str) -> Path:
    return AGENT_ROOT / rel


def _read_doc(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if not text.strip():
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - chunk_overlap)
    return chunks


def collect_doc_files(docs_dir: Path) -> list[Path]:
    if not docs_dir.exists():
        return []
    files: list[Path] = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        if path.suffix.lower() in _TEXT_EXTENSIONS or path.suffix == "":
            files.append(path)
    return files


def build_docs_index(*, agent_root: Path | None = None) -> dict[str, Any]:
    root = agent_root or AGENT_ROOT
    cfg = load_embedding_config(root / "embedding_config.yaml")
    docs_dir = root / cfg.get("docs_dir", "docs")
    index_path = root / cfg.get("index_path", "data/docs_index.json")
    chunk_size = int(cfg.get("chunk_size", 800))
    chunk_overlap = int(cfg.get("chunk_overlap", 120))
    model_name = cfg.get("model", "sentence-transformers/all-MiniLM-L6-v2")

    entries: list[dict[str, Any]] = []
    for doc_path in collect_doc_files(docs_dir):
        rel = str(doc_path.relative_to(root))
        text = _read_doc(doc_path)
        for i, chunk in enumerate(chunk_text(text, chunk_size, chunk_overlap)):
            entries.append({"source": rel, "chunk_id": i, "text": chunk})

    warnings: list[str] = []
    vectors: list[list[float]] = []
    if entries:
        try:
            from agent_core.embedding import clear_model_cache, embed_texts

            clear_model_cache()
            vectors = embed_texts(
                [e["text"] for e in entries],
                config_path=root / "embedding_config.yaml",
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"embedding failed ({exc}); index stored without vectors")
    else:
        warnings.append("no documents found in docs/")

    for entry, vector in zip(entries, vectors, strict=False):
        entry["embedding"] = vector

    payload = {
        "model": model_name,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "entries": entries,
        "warnings": warnings,
    }
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "index_path": str(index_path),
        "doc_count": len(collect_doc_files(docs_dir)),
        "chunk_count": len(entries),
        "warnings": warnings,
    }


def _load_index(agent_root: Path | None = None) -> dict[str, Any] | None:
    root = agent_root or AGENT_ROOT
    cfg = load_embedding_config(root / "embedding_config.yaml")
    index_path = root / cfg.get("index_path", "data/docs_index.json")
    if not index_path.exists():
        return None
    return json.loads(index_path.read_text(encoding="utf-8"))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _token_overlap_score(query: str, text: str) -> float:
    q = {
        t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", query.lower())
        if t not in _STOPWORDS and len(t) > 2
    }
    if not q:
        return 0.0
    body = {
        t for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]+", text.lower())
        if t not in _STOPWORDS and len(t) > 2
    }
    return len(q & body) / len(q)


def retrieve_docs(query: str, *, top_k: int | None = None, agent_root: Path | None = None) -> dict[str, Any]:
    root = agent_root or AGENT_ROOT
    cfg = load_embedding_config(root / "embedding_config.yaml")
    k = top_k or int(cfg.get("top_k", 5))
    index = _load_index(root)
    if not index or not index.get("entries"):
        return {"ok": False, "chunks": [], "sources": [], "mode": "none"}

    entries = index["entries"]
    scored: list[tuple[float, dict[str, Any]]] = []

    has_vectors = all(e.get("embedding") for e in entries)
    if has_vectors:
        try:
            q_vec = embed_query(query, config_path=root / "embedding_config.yaml")
            for entry in entries:
                score = _cosine(q_vec, entry.get("embedding", []))
                scored.append((score, entry))
            scored.sort(key=lambda x: x[0], reverse=True)
            mode = "embedding"
        except Exception:  # noqa: BLE001
            scored = []
            mode = "keyword"
    else:
        mode = "keyword"

    if not scored:
        for entry in entries:
            score = _token_overlap_score(query, entry["text"])
            scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        mode = "keyword"

    top = [e for s, e in scored[:k] if s > 0] or [e for _, e in scored[:k]]
    chunks = [{"source": e["source"], "text": e["text"], "chunk_id": e.get("chunk_id", 0)} for e in top]
    sources = sorted({c["source"] for c in chunks})
    return {"ok": True, "chunks": chunks, "sources": sources, "mode": mode}
