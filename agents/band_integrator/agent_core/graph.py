"""
LangGraph fabrication state machine.

State flow:
    retrieve_docs → generate_code → run_sandbox
                          ↑               |
                          |  (error, iter < MAX_DEBUG_ITERATIONS)
                          └───────────────┘
                                          |
                   (iter >= MAX) → fail → END
                   (success)     ──────→ END

Both tools are exposed as LangChain @tool instances for the Orchestrator.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

from langchain_core.tools import tool
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agents.band_integrator.agent_core.nodes.coder import generate_code
from agents.band_integrator.agent_core.nodes.retriever import retrieve_context
from agents.band_integrator.agent_core.nodes.sandbox import run_in_sandbox

logger = logging.getLogger(__name__)

MAX_DEBUG_ITERATIONS = 3


class FabricationState(TypedDict):
    user_request: str
    agent_id: str       # new agent's Band UUID  — hardcoded into generated script
    agent_key: str      # new agent's Band API key — hardcoded into generated script
    retrieved_context: str
    generated_code: str
    script_path: str
    compilation_error: str
    debug_iterations: int
    status: str         # "coding" | "testing" | "success" | "failed"


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def node_retrieve_docs(state: FabricationState) -> dict:
    logger.info("[fabricate] Retrieving SDK context for: %s", state["user_request"])
    context = retrieve_context(state["user_request"])
    return {"retrieved_context": context, "status": "coding"}


def node_generate_code(state: FabricationState) -> dict:
    iteration = state.get("debug_iterations", 0)
    if iteration > 0:
        logger.info("[fabricate] Repair attempt %d/%d", iteration, MAX_DEBUG_ITERATIONS)
    else:
        logger.info("[fabricate] Generating agent script…")

    code, path = generate_code(
        user_request=state["user_request"],
        retrieved_context=state["retrieved_context"],
        agent_id=state["agent_id"],
        agent_key=state["agent_key"],
        compilation_error=state.get("compilation_error", ""),
    )
    return {
        "generated_code": code,
        "script_path": path,
        "compilation_error": "",  # clear so sandbox result is fresh
        "status": "testing",
    }


def node_run_sandbox(state: FabricationState) -> dict:
    logger.info("[fabricate] Running sandbox check on %s", state["script_path"])
    error = run_in_sandbox(state["script_path"])
    if error:
        iteration = state.get("debug_iterations", 0) + 1
        logger.warning(
            "[fabricate] Sandbox FAILED (attempt %d/%d): %s",
            iteration, MAX_DEBUG_ITERATIONS, error[:200],
        )
        return {
            "compilation_error": error,
            "debug_iterations": iteration,
            "status": "coding",
        }
    logger.info("[fabricate] Sandbox PASSED ✓")
    return {"compilation_error": "", "status": "success"}


def node_fail(state: FabricationState) -> dict:
    logger.error(
        "[fabricate] Giving up after %d failed attempts. Last error: %s",
        state.get("debug_iterations", 0),
        state.get("compilation_error", "")[:300],
    )
    return {"status": "failed"}


# ---------------------------------------------------------------------------
# Conditional routing
# ---------------------------------------------------------------------------

def route_after_sandbox(
    state: FabricationState,
) -> Literal["generate_code", "fail", "__end__"]:
    if state["status"] == "success":
        return "__end__"
    if state.get("debug_iterations", 0) >= MAX_DEBUG_ITERATIONS:
        return "fail"
    return "generate_code"


# ---------------------------------------------------------------------------
# Graph compilation
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    graph = StateGraph(FabricationState)

    graph.add_node("retrieve_docs", node_retrieve_docs)
    graph.add_node("generate_code", node_generate_code)
    graph.add_node("run_sandbox", node_run_sandbox)
    graph.add_node("fail", node_fail)

    graph.set_entry_point("retrieve_docs")
    graph.add_edge("retrieve_docs", "generate_code")
    graph.add_edge("generate_code", "run_sandbox")
    graph.add_conditional_edges(
        "run_sandbox",
        route_after_sandbox,
        {
            "generate_code": "generate_code",   # retry loop
            "fail": "fail",
            "__end__": END,
        },
    )
    graph.add_edge("fail", END)

    return graph.compile()


_fabrication_graph = _build_graph()


# ---------------------------------------------------------------------------
# LangChain tool wrappers for the Orchestrator
# ---------------------------------------------------------------------------

@tool
def fabricate_agent_tool(user_request: str, agent_id: str, agent_key: str) -> str:
    """
    Design, code, and sandbox-test a new Band remote agent.

    The agent's credentials (agent_id, agent_key) are burned as literal strings
    into the generated script so it always connects with its own identity.

    Args:
        user_request: Natural language description of what the new agent should do.
        agent_id:     Band agent UUID for the NEW agent (from Band dashboard).
        agent_key:    Band API key for the NEW agent (from Band dashboard).

    Returns JSON:
      - status: "success" or "failed"
      - script_path: absolute path to the generated .py file (on success)
      - error: last compilation error (on failure)
    """
    initial_state: FabricationState = {
        "user_request": user_request,
        "agent_id": agent_id,
        "agent_key": agent_key,
        "retrieved_context": "",
        "generated_code": "",
        "script_path": "",
        "compilation_error": "",
        "debug_iterations": 0,
        "status": "coding",
    }

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            asyncio.run, _fabrication_graph.ainvoke(initial_state)
        )
        final_state = future.result()

    if final_state["status"] == "success":
        return json.dumps({
            "status": "success",
            "script_path": final_state["script_path"],
        })

    return json.dumps({
        "status": "failed",
        "error": final_state.get("compilation_error", "Unknown error after max retries."),
    })


@tool
def deploy_agent_tool(script_path: str, agent_id: str, agent_key: str) -> str:
    """
    Launch a fabricated Band agent script as a persistent background process.

    The credentials are already hardcoded inside the script; agent_id and
    agent_key are accepted here so the orchestrator can pass them for logging
    and so it can later call thenvoi_add_participant with the correct identity.

    Args:
        script_path: Path returned by fabricate_agent_tool.
        agent_id:    Band agent UUID of the new agent.
        agent_key:   Band API key of the new agent.

    Returns JSON:
      - status: "deployed" or "error"
      - pid: process ID of the spawned agent
      - message: human-readable result
    """
    from src.manager.process import process_manager  # late import avoids cycles

    import concurrent.futures

    async def _spawn():
        return await process_manager.spawn(script_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, _spawn())
        result = future.result()

    logger.info("[deploy] Spawned agent_id=%s pid=%s", agent_id, result.get("pid"))
    return json.dumps(result)
