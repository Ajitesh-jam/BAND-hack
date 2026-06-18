#!/usr/bin/env python3
"""Build docs RAG index from docs/ using embedding_config.yaml."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))

from agent_core.docs_rag import build_docs_index  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build docs RAG embeddings index.")
    parser.add_argument(
        "--agent-root",
        type=Path,
        default=AGENT_ROOT,
        help="Root folder of the company context agent.",
    )
    args = parser.parse_args()
    result = build_docs_index(agent_root=args.agent_root.resolve())
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
