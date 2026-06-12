"""
Coder node: calls Gemini 2.5 Flash to generate a complete, runnable Band
agent Python script.

The new agent's Band credentials (agent_id, agent_key) are burned as literal
strings directly into the generated source so the script never reads from env
vars and always connects with the correct identity regardless of what
environment it inherits.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

GENERATED_DIR = Path(__file__).parent.parent.parent / "generated_agents"

# {agent_id} and {agent_key} are substituted by generate_code() at call time.
# {context} is the RAG-retrieved SDK documentation.
_SYSTEM_PROMPT = """\
You are an expert Python developer. Output ONE complete, runnable Python script \
for a Band (thenvoi) remote agent.

MANDATORY SKELETON — adapt only the adapter/tools/custom_section sections:

    import asyncio
    import os
    import logging
    from dotenv import load_dotenv
    from thenvoi import Agent
    from thenvoi.adapters import LangGraphAdapter
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.checkpoint.memory import InMemorySaver

    logging.basicConfig(level=logging.INFO)

    async def main():
        load_dotenv()
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        adapter = LangGraphAdapter(
            llm=llm,
            checkpointer=InMemorySaver(),
            additional_tools=[...],        # replace with actual tools or []
            custom_section="...",          # replace with role description
        )
        agent = Agent.create(
            adapter=adapter,
            agent_id="{agent_id}",
            api_key="{agent_key}",
        )
        await agent.run()

    if __name__ == "__main__":
        asyncio.run(main())

STRICT RULES:
- Output RAW Python only — zero markdown fences, zero explanatory prose.
- All imports at the top of the file. Single self-contained file.
- agent_id="{agent_id}" and api_key="{agent_key}" MUST appear as shown — \
hardcoded string literals. Do NOT change them to os.getenv().
- For the LLM key ONLY use os.getenv("GOOGLE_API_KEY").
- Add @tool functions (langchain_core.tools) for any custom capabilities.

Band SDK reference:
{context}
"""

_REPAIR_SUFFIX = """

--- ERROR FROM PREVIOUS ATTEMPT (fix this) ---
{error}
----------------------------------------------

Return only the corrected Python script. No markdown fences.
"""


def _strip_fences(code: str) -> str:
    """Remove any accidental ```python / ``` wrappers Claude/Gemini might emit."""
    code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
    code = re.sub(r"\n```\s*$", "", code, flags=re.MULTILINE)
    return code.strip()


def generate_code(
    user_request: str,
    retrieved_context: str,
    agent_id: str,
    agent_key: str,
    compilation_error: str = "",
) -> tuple[str, str]:
    """
    Ask Gemini 2.5 Flash to write the agent script with hardcoded credentials.

    Returns (generated_code_str, saved_script_path).
    When `compilation_error` is non-empty this is a self-repair attempt.
    """
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=os.environ["GOOGLE_API_KEY"],
        max_output_tokens=4096,
    )

    system_content = _SYSTEM_PROMPT.format(
        agent_id=agent_id,
        agent_key=agent_key,
        context=retrieved_context,
    )

    user_content = f"Build this agent: {user_request}"
    if compilation_error:
        user_content += _REPAIR_SUFFIX.format(error=compilation_error)
        logger.info("Repair attempt — injecting error into prompt.")

    response = llm.invoke([
        SystemMessage(content=system_content),
        HumanMessage(content=user_content),
    ])

    clean_code = _strip_fences(response.content)

    script_path = GENERATED_DIR / f"agent_{uuid.uuid4().hex[:8]}.py"
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    script_path.write_text(clean_code, encoding="utf-8")
    logger.info("Script saved → %s", script_path)

    return clean_code, str(script_path)
