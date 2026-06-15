"""Configurable local embedding backend for docs RAG."""

from __future__ import annotations

import logging
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

AGENT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = AGENT_ROOT / "embedding_config.yaml"


def load_embedding_config(config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or DEFAULT_CONFIG
    if not path.exists():
        return {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "chunk_size": 800,
            "chunk_overlap": 120,
            "docs_dir": "docs",
            "index_path": "data/docs_index.json",
            "top_k": 5,
        }
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data


def _import_sentence_transformers():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer


def _ensure_sentence_transformers() -> None:
    try:
        _import_sentence_transformers()
        return
    except ImportError:
        logger.warning("sentence-transformers not found — installing into current environment")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "sentence-transformers>=3.0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _load_model.cache_clear()


@lru_cache(maxsize=2)
def _load_model(model_name: str):
    try:
        SentenceTransformer = _import_sentence_transformers()
    except ImportError as exc:
        try:
            _ensure_sentence_transformers()
            SentenceTransformer = _import_sentence_transformers()
        except Exception as install_exc:  # noqa: BLE001
            raise RuntimeError(
                "sentence-transformers is required for embedding. "
                "Run: uv sync   or   pip install sentence-transformers"
            ) from install_exc
    logger.info("Loading embedding model: %s", model_name)
    return SentenceTransformer(model_name)


def embed_texts(texts: list[str], *, config_path: Path | None = None) -> list[list[float]]:
    if not texts:
        return []
    cfg = load_embedding_config(config_path)
    model = _load_model(cfg["model"])
    vectors = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return [v.tolist() for v in vectors]


def embed_query(query: str, *, config_path: Path | None = None) -> list[float]:
    result = embed_texts([query], config_path=config_path)
    return result[0] if result else []


def clear_model_cache() -> None:
    _load_model.cache_clear()
