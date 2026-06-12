"""
Integration code generator: takes an existing agent codebase (as a dict of
filename → source), understands its framework, and produces a single
`band_integration.py` file that wraps the user's logic with the Band (thenvoi)
SDK.

Key responsibilities:
- Framework detection (LangGraph, CrewAI, Anthropic, raw Python, etc.)
- Selecting the correct Band adapter pattern
- Injecting thenvoi_send_event calls around every tool execution
- Hardcoding Band agent credentials as literal strings
- Self-repair on compilation errors (up to MAX_DEBUG_ITERATIONS)
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert Python developer specialising in the Band (thenvoi) SDK.
You are given the source code of an existing AI agent and your job is to
produce a SINGLE file called `band_integration.py` that wraps it as a live
Band remote agent.

━━━ STEP 1 — ANALYSE THE USER'S CODE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Read all the provided source files and identify:
• Framework: LangGraph | CrewAI | Anthropic | OpenAI | raw Python | other
• Entry point: the function/class/coroutine that drives the agent
• Tools: any functions decorated with @tool, or tool lists passed to an LLM
• LLM client: which model and provider are used

━━━ STEP 2 — CHOOSE THE RIGHT BAND ADAPTER ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• LangGraph agent   → use LangGraphAdapter wrapping the existing compiled graph
• CrewAI agent      → use SimpleAdapter + manual tool loop (see Pattern 2 below)
• Anthropic / raw   → use SimpleAdapter + manual tool loop (Pattern 2)
• Any other         → use SimpleAdapter + manual tool loop (Pattern 2)

━━━ STEP 3 — GENERATE band_integration.py ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The output file MUST:

1. Import from the user's code using relative imports (e.g. `from .agent import ...`
   or `from agent import ...` depending on folder structure — use the simpler
   direct import since we run from the same directory).

2. Use EXACTLY this skeleton (adapt adapter/tools/custom_section):

    import asyncio, os, sys, logging
    from dotenv import load_dotenv
    from thenvoi import Agent
    from thenvoi.adapters import LangGraphAdapter   # or SimpleAdapter for non-LangGraph

    logging.basicConfig(level=logging.INFO)

    async def main():
        load_dotenv()
        # --- import user's agent logic here ---
        agent = Agent.create(
            adapter=<adapter>,
            agent_id="{agent_id}",
            api_key="{agent_key}",
        )
        await agent.run()

    if __name__ == "__main__":
        asyncio.run(main())

3. Inject event reporting around EVERY tool call using Pattern 2 (manual tool loop):

    MAX_TOOL_ITERS = 10

    async def _execute_tools(tool_calls, messages, tools):
        for tc in tool_calls:
            name = tc["name"] if isinstance(tc, dict) else tc.function.name
            args = tc.get("arguments", {{}}) if isinstance(tc, dict) else tc.function.arguments
            await tools.send_event(
                content=f"Calling {{name}}",
                message_type="tool_call",
                metadata={{"tool": name, "input": args}},
            )
            try:
                result = await tools.execute_tool_call(name, args)
                await tools.send_event(
                    content=f"{{name}} OK",
                    message_type="tool_result",
                    metadata={{"tool": name, "is_error": False}},
                )
            except Exception as e:
                await tools.send_event(
                    content=f"{{name}} error: {{e}}",
                    message_type="error",
                    metadata={{"tool": name, "is_error": True}},
                )
                raise

4. For LangGraph agents, use the streaming pattern instead:

    async for event in graph.astream_events(inputs, config=config, version="v2"):
        if event["event"] == "on_tool_start":
            await tools.send_event(content=f"Calling {{event['name']}}", message_type="tool_call")
        elif event["event"] == "on_tool_end":
            await tools.send_event(content=f"{{event['name']}} done", message_type="tool_result")

5. Wrap the entire on_message body in try/except:
    except Exception as e:
        await tools.send_event(content=f"Error: {{e}}", message_type="error")
        raise

6. agent_id="{agent_id}" and api_key="{agent_key}" MUST be hardcoded string
   literals — do NOT change them to os.getenv().

7. For the LLM key: os.getenv("GOOGLE_API_KEY") or keep the user's original
   API key env var name if they used a different one.

━━━ BAND SDK REFERENCE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{context}

━━━ STRICT OUTPUT RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Output RAW Python ONLY — zero markdown fences, zero prose.
- The file must be completely self-contained and runnable from the user's folder.
- All imports at the top. No wildcard imports.
- The file is named band_integration.py (you don't need to write the filename).
"""

_REPAIR_SUFFIX = """

━━━ ERROR FROM PREVIOUS ATTEMPT — FIX THIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{error}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return ONLY the corrected band_integration.py. No markdown fences.
"""


def _strip_fences(code: str) -> str:
    code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
    code = re.sub(r"\n```\s*$", "", code, flags=re.MULTILINE)
    return code.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_integration(
    file_contents: dict[str, str],
    sdk_context: str,
    agent_id: str,
    agent_key: str,
    folder_path: str,
    compilation_error: str = "",
) -> tuple[str, str]:
    """
    Generate `band_integration.py` for the user's agent codebase.

    Args:
        file_contents:     {relative_filename: source} from reader.read_folder()
        sdk_context:       RAG-retrieved Band SDK documentation
        agent_id:          Band agent UUID (hardcoded into generated file)
        agent_key:         Band API key (hardcoded into generated file)
        folder_path:       Absolute path to the user's agent folder
        compilation_error: Non-empty on repair attempts

    Returns:
        (generated_code_str, absolute_path_to_integration_file)
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GOOGLE_API_KEY"],
        max_output_tokens=8192,
    )

    system_content = _SYSTEM_PROMPT.format(
        agent_id=agent_id,
        agent_key=agent_key,
        context=sdk_context,
    )

    # Build the user message: all source files + request
    file_block = _format_files(file_contents)
    user_content = (
        f"Here is the existing agent codebase located at: {folder_path}\n\n"
        f"{file_block}\n\n"
        "Generate band_integration.py that integrates this agent with Band."
    )
    if compilation_error:
        user_content += _REPAIR_SUFFIX.format(error=compilation_error)
        logger.info("[integrator] Repair attempt — injecting error into prompt.")

    response = llm.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ])

    clean_code = _strip_fences(response.content)

    integration_path = Path(folder_path) / "band_integration.py"
    integration_path.write_text(clean_code, encoding="utf-8")
    logger.info("[integrator] band_integration.py written → %s", integration_path)

    return clean_code, str(integration_path)


def _format_files(file_contents: dict[str, str]) -> str:
    """Render file dict as labelled sections for the prompt."""
    parts: list[str] = []
    for filename, content in file_contents.items():
        parts.append(f"### FILE: {filename}\n{content}\n### END: {filename}")
    return "\n\n".join(parts)
