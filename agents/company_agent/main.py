"""Company Agent — serves graphify code graph + docs RAG for demo-app."""

from __future__ import annotations

import json
import logging

from thenvoi.runtime.custom_tools import CustomToolDef

from agents.band_orchestrator.agent_core.context_engine import build_context, query_docs
from agents.company_agent.agent_core.schema import (
    BuildContextInput,
    FileDependenciesInput,
    GraphOverviewInput,
    QueryContextInput,
)
from band.agents.base import adapter_sdk, create_and_run
from band.config import get_settings
from band.prompts import COMPANY_AGENT_PROMPT
from band.tools import graphify_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s [company-agent] %(message)s")


def _custom_tools() -> list[CustomToolDef]:
    return [
        (BuildContextInput, lambda inp: json.dumps(build_context(inp.target_path))),
        (QueryContextInput, lambda inp: json.dumps(_query_context(inp.question))),
        (GraphOverviewInput, lambda inp: json.dumps(graphify_ops.graph_overview(inp.target_path))),
        (
            FileDependenciesInput,
            lambda inp: json.dumps(
                graphify_ops.file_dependencies(inp.relative_path, inp.target_path)
            ),
        ),
    ]


def _query_context(question: str) -> dict:
    docs = query_docs(question)
    graph = graphify_ops.query_graph(question)
    return {"docs": docs, "graph": graph}


def build_adapter():
    settings = get_settings()
    return adapter_sdk(
        COMPANY_AGENT_PROMPT,
        adapter_type=settings.company_agent_adapter,
        model=settings.company_agent_model,
        additional_tools=_custom_tools(),
    )


def cli() -> None:
    create_and_run(build_adapter(), "company_agent", "Company Agent")


if __name__ == "__main__":
    cli()
