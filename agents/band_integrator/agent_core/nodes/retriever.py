"""
RAG retriever: loads docs/band_sdk.md into a FAISS vector store and exposes
retrieve_context(query) for use inside the LangGraph fabrication nodes.

Index persistence:
  - On first call the full docs are embedded and the FAISS index is saved to
    docs/faiss_index/ so subsequent startups load instantly from disk.
  - Run `uv run python -m src.nodes.retriever` to pre-build the index before
    starting the server.

Embedding model: Google gemini-embedding-001 via GOOGLE_API_KEY.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

DOCS_PATH = Path(__file__).parent.parent.parent / "docs" / "band_sdk.md"
INDEX_DIR = Path(__file__).parent.parent.parent / "docs" / "faiss_index"

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100
_TOP_K = 3


def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    # Use gemini-embedding-001 — the new google.genai SDK prepends "models/"
    # internally so we supply the bare name without the prefix.
    return GoogleGenerativeAIEmbeddings(
        model="gemini-embedding-001",
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )


def build_index(force: bool = False) -> FAISS:
    """
    Build (or rebuild) the FAISS index from docs/band_sdk.md and save to disk.

    Call this once before starting the server:
        uv run python -m src.nodes.retriever

    Args:
        force: if True, rebuild even if the index already exists on disk.
    """
    if INDEX_DIR.exists() and not force:
        logger.info("FAISS index already exists at %s — skipping build.", INDEX_DIR)
        return FAISS.load_local(
            str(INDEX_DIR),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )

    logger.info("Building FAISS index from %s …", DOCS_PATH)
    loader = TextLoader(str(DOCS_PATH), encoding="utf-8")
    documents = loader.load()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n#### ", "\n```", "\n\n", "\n", " "],
    )
    chunks = splitter.split_documents(documents)
    logger.info("Split into %d chunks. Embedding… (this takes ~1–2 min)", len(chunks))

    store = FAISS.from_documents(chunks, _get_embeddings())

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    store.save_local(str(INDEX_DIR))
    logger.info("FAISS index saved to %s", INDEX_DIR)
    return store


@lru_cache(maxsize=1)
def _load_vector_store() -> FAISS:
    """Load index from disk if available, otherwise build it first."""
    if INDEX_DIR.exists():
        logger.info("Loading FAISS index from %s", INDEX_DIR)
        return FAISS.load_local(
            str(INDEX_DIR),
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
    logger.warning(
        "FAISS index not found at %s — building now (slow on first run). "
        "Run `uv run python -m src.nodes.retriever` to pre-build.",
        INDEX_DIR,
    )
    return build_index()


def retrieve_context(query: str, top_k: int = _TOP_K) -> str:
    """
    Return the most relevant Band SDK documentation chunks for `query`.
    Chunks are separated by a divider for direct injection into the coder prompt.
    """
    store = _load_vector_store()
    docs = store.similarity_search(query, k=top_k)
    return "\n\n---\n\n".join(doc.page_content for doc in docs)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    from dotenv import load_dotenv
    load_dotenv()
    build_index(force=False)
    print("Index ready.")
