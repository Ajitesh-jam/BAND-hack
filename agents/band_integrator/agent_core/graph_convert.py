"""
Conversion pipeline: reads an existing agent codebase from disk, fetches Band
SDK context via RAG, generates a `band_integration.py` wrapper using Gemini,
validates it in a sandbox, and — on success — returns the path so the
Orchestrator can deploy it.

State flow:
    read_folder → fetch_sdk_context → generate_integration → run_sandbox
                                               ↑                   |
                                               |  (error, iter < 3)
                                               └───────────────────┘
                                                                   |
                                   (iter >= 3) → fail → END
                                   (success)   ────────→ END
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
from typing import Literal

from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.nodes.integrator import generate_integration
from src.nodes.reader import read_folder
from src.nodes.retriever import retrieve_context
from src.nodes.sandbox import run_in_sandbox

logger = logging.getLogger(__name__)

MAX_DEBUG_ITERATIONS = 3


# ---------------------------------------------------------------------------
# State schema
# ---------------------------------------------------------------------------

class ConversionState(TypedDict):
    folder_path: str
    agent_id: str
    agent_key: str
    file_contents: dict          # {rel_path: source}
    sdk_context: str
    generated_wrapper: str
    integration_path: str        # <folder>/band_integration.py
    compilation_error: str
    debug_iterations: int
    status: str                  # "reading" | "fetching" | "generating" | "testing" | "success" | "failed"


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def node_read_folder(state: ConversionState) -> dict:
    logger.info("[convert] Reading source files from: %s", state["folder_path"])
    try:
        files = read_folder(state["folder_path"])
    except ValueError as exc:
        logger.error("[convert] Failed to read folder: %s", exc)
        return {"file_contents": {}, "status": "failed", "compilation_error": str(exc)}

    if not files:
        msg = f"No Python files found in {state['folder_path']}"
        logger.warning("[convert] %s", msg)
        return {"file_contents": {}, "status": "failed", "compilation_error": msg}

    logger.info("[convert] Found %d files.", len(files))
    return {"file_contents": files, "status": "fetching"}


def node_fetch_sdk_context(state: ConversionState) -> dict:
    if state["status"] == "failed":
        return {}
    logger.info("[convert] Fetching Band SDK context via RAG…")
    context = retrieve_context(
        "Band SDK integration custom adapter event loop SimpleAdapter LangGraphAdapter"
    )
    return {"sdk_context": context, "status": "generating"}


def node_generate_integration(state: ConversionState) -> dict:
    if state["status"] == "failed":
        return {}
    iteration = state.get("debug_iterations", 0)
    if iteration > 0:
        logger.info("[convert] Repair attempt %d/%d…", iteration, MAX_DEBUG_ITERATIONS)
    else:
        logger.info("[convert] Generating band_integration.py…")

    try:
        code, path = generate_integration(
            file_contents=state["file_contents"],
            sdk_context=state["sdk_context"],
            agent_id=state["agent_id"],
            agent_key=state["agent_key"],
            folder_path=state["folder_path"],
            compilation_error=state.get("compilation_error", ""),
        )
    except Exception as exc:
        logger.error("[convert] Integration generation failed: %s", exc)
        return {
            "compilation_error": str(exc),
            "debug_iterations": state.get("debug_iterations", 0) + 1,
            "status": "generating",
        }

    return {
        "generated_wrapper": code,
        "integration_path": path,
        "compilation_error": "",
        "status": "testing",
    }


def node_run_sandbox(state: ConversionState) -> dict:
    if state["status"] == "failed":
        return {}
    logger.info("[convert] Sandbox check: %s", state.get("integration_path", ""))
    error = run_in_sandbox(state["integration_path"], cwd=state["folder_path"])
    if error:
        iteration = state.get("debug_iterations", 0) + 1
        logger.warning(
            "[convert] Sandbox FAILED (attempt %d/%d): %s",
            iteration, MAX_DEBUG_ITERATIONS, error[:200],
        )
        return {
            "compilation_error": error,
            "debug_iterations": iteration,
            "status": "generating",
        }
    logger.info("[convert] Sandbox PASSED ✓")
    return {"compilation_error": "", "status": "success"}


def node_fail(state: ConversionState) -> dict:
    logger.error(
        "[convert] Giving up after %d failed attempts. Last error: %s",
        state.get("debug_iterations", 0),
        state.get("compilation_error", "")[:300],
    )
    return {"status": "failed"}


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

def _route_after_sandbox(
    state: ConversionState,
) -> Literal["generate_integration", "fail", "__end__"]:
    if state["status"] == "success":
        return "__end__"
    if state["status"] == "failed":
        return "fail"
    if state.get("debug_iterations", 0) >= MAX_DEBUG_ITERATIONS:
        return "fail"
    return "generate_integration"


def _route_after_read(state: ConversionState) -> Literal["fetch_sdk_context", "fail"]:
    if state["status"] == "failed":
        return "fail"
    return "fetch_sdk_context"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

def _build_convert_graph() -> StateGraph:
    graph = StateGraph(ConversionState)

    graph.add_node("read_folder", node_read_folder)
    graph.add_node("fetch_sdk_context", node_fetch_sdk_context)
    graph.add_node("generate_integration", node_generate_integration)
    graph.add_node("run_sandbox", node_run_sandbox)
    graph.add_node("fail", node_fail)

    graph.set_entry_point("read_folder")
    graph.add_conditional_edges(
        "read_folder",
        _route_after_read,
        {"fetch_sdk_context": "fetch_sdk_context", "fail": "fail"},
    )
    graph.add_edge("fetch_sdk_context", "generate_integration")
    graph.add_edge("generate_integration", "run_sandbox")
    graph.add_conditional_edges(
        "run_sandbox",
        _route_after_sandbox,
        {
            "generate_integration": "generate_integration",
            "fail": "fail",
            "__end__": END,
        },
    )
    graph.add_edge("fail", END)

    return graph.compile()


_conversion_graph = _build_convert_graph()


# ---------------------------------------------------------------------------
# LangChain tool wrapper for the Orchestrator
# ---------------------------------------------------------------------------

@tool
def convert_agent_tool(folder_path: str, agent_id: str, agent_key: str) -> str:
    """
    Read an existing agent codebase at folder_path, understand its framework,
    generate a band_integration.py wrapper with Band event-loop reporting,
    sandbox-validate it (with up to 3 auto-repair attempts), and return the
    path to the integration file on success.

    The wrapper is written to <folder_path>/band_integration.py.
    After this tool succeeds, call deploy_agent_tool with the returned
    integration_path to spawn the agent live in the chat room.

    Args:
        folder_path: Absolute (or expandable) path to the user's agent folder.
        agent_id:    Band agent UUID for the converted agent (from Band dashboard).
        agent_key:   Band API key for the converted agent (from Band dashboard).

    Returns JSON:
      - status: "success" or "failed"
      - integration_path: absolute path to band_integration.py (on success)
      - error: last compilation error message (on failure)
    """
    initial_state: ConversionState = {
        "folder_path": folder_path,
        "agent_id": agent_id,
        "agent_key": agent_key,
        "file_contents": {},
        "sdk_context": "",
        "generated_wrapper": "",
        "integration_path": "",
        "compilation_error": "",
        "debug_iterations": 0,
        "status": "reading",
    }

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            asyncio.run, _conversion_graph.ainvoke(initial_state)
        )
        final_state = future.result()

    if final_state["status"] == "success":
        return json.dumps({
            "status": "success",
            "integration_path": final_state["integration_path"],
        })

    return json.dumps({
        "status": "failed",
        "error": final_state.get("compilation_error", "Conversion failed after max retries."),
    })
