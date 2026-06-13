"""Convert an existing agent codebase into a live Band agent.

Reads the user's folder, retrieves Band SDK context, and asks Gemini to write a
single ``band_integration.py`` wrapper directly into that folder (modifying the
user's directory in place, as requested). The wrapper is syntax-checked and
given one auto-repair attempt before it is returned for deployment.

No LangGraph / FAISS — the LLM call goes straight through ``google.genai``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from agents.band_orchestrator.agent_core.retriever import retrieve_context

logger = logging.getLogger(__name__)

_SKIP_DIRS = {
    "__pycache__", ".venv", "venv", "env", "node_modules", ".git",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox", "site-packages",
}
_MAX_FILE_CHARS = 8_000
_MAX_TOTAL_CHARS = 40_000
_MODEL = "gemini-2.5-flash"

INTEGRATION_FILENAME = "band_integration.py"


_SYSTEM_PROMPT = """\
You are an expert Python developer specialising in the Band (thenvoi) SDK.
You are given the source code of an existing AI agent. Produce a SINGLE
self-contained file named band_integration.py that wraps it as a live Band
remote agent that joins a chat room and responds to messages.

USE EXACTLY THIS SKELETON (adapt the custom_section and, if useful, import the
user's own logic/tools from their modules):

    import asyncio
    import logging
    from dotenv import load_dotenv
    from thenvoi import Agent
    from band.agents.base import adapter_sdk

    logging.basicConfig(level=logging.INFO)

    AGENT_ID = "{agent_id}"
    API_KEY = "{api_key}"

    CUSTOM_SECTION = \"\"\"<describe the agent's role/capabilities inferred from the code>\"\"\"

    async def main():
        load_dotenv()
        adapter = adapter_sdk(CUSTOM_SECTION, enable_memory=True)
        agent = Agent.create(
            adapter=adapter,
            agent_id=AGENT_ID,
            api_key=API_KEY,
        )
        await agent.run()

    if __name__ == "__main__":
        asyncio.run(main())

STRICT RULES:
- Output RAW Python ONLY — no markdown fences, no prose.
- AGENT_ID = "{agent_id}" and API_KEY = "{api_key}" MUST be hardcoded string
  literals exactly as shown. Do NOT read them from env vars.
- Derive CUSTOM_SECTION from analysing the user's code (its purpose, tools,
  domain). Keep it a single triple-quoted string.
- ONLY import these from thenvoi: ``from thenvoi import Agent``. There is NO
  ``tool`` export in thenvoi — never write ``from thenvoi import tool``.
- Do NOT pass ``additional_tools`` to adapter_sdk unless you build proper
  thenvoi CustomToolDef tuples ``(PydanticInputModel, handler)``. When in
  doubt, OMIT additional_tools entirely and describe the capabilities in
  CUSTOM_SECTION instead — a clean, runnable agent is the priority.
- Keep imports at the top. The file must IMPORT CLEANLY and run from the
  user's folder. Prefer the minimal skeleton above; only import the user's
  modules if you are confident they import with no side effects.

BAND SDK REFERENCE:
{context}
"""

_REPAIR_SUFFIX = """

--- ERROR FROM PREVIOUS ATTEMPT (fix this) ---
{error}
----------------------------------------------
Return ONLY the corrected band_integration.py. No markdown fences.
"""


def convert_agent(folder_path: str, agent_id: str, api_key: str) -> dict:
    """Read ``folder_path``, write band_integration.py into it, return metadata.

    Returns dict: {status, integration_path, folder, agent_id} or
    {status: "failed", error}.
    """
    root = Path(folder_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return {"status": "failed", "error": f"Folder not found: {folder_path}"}

    files = _read_folder(root)
    if not files:
        return {"status": "failed", "error": f"No Python files found in {root}"}

    context = retrieve_context(
        "custom adapter SimpleAdapter LangGraphAdapter Agent.create remote agent integration"
    )
    system_prompt = _SYSTEM_PROMPT.format(agent_id=agent_id, api_key=api_key, context=context)
    user_block = _format_files(files)

    error = ""
    integration_path = root / INTEGRATION_FILENAME
    for attempt in range(2):
        user_content = (
            f"Existing agent codebase at: {root}\n\n{user_block}\n\n"
            "Generate band_integration.py that connects this agent to Band."
        )
        if error:
            user_content += _REPAIR_SUFFIX.format(error=error)
            logger.info("[convert] repair attempt %d", attempt)

        code = _strip_fences(_gemini(system_prompt, user_content))
        integration_path.write_text(code, encoding="utf-8")

        error = _sandbox_check(integration_path, cwd=str(root))
        if not error:
            logger.info("[convert] band_integration.py written -> %s", integration_path)
            return {
                "status": "success",
                "integration_path": str(integration_path),
                "folder": str(root),
                "agent_id": agent_id,
            }

    return {"status": "failed", "error": error or "conversion failed"}


def _gemini(system_prompt: str, user_content: str) -> str:
    os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    response = client.models.generate_content(
        model=_MODEL,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=8192,
            temperature=0.1,
        ),
    )
    return response.text or ""


# Prepended before sandbox execution: mocks Agent.run so the script exits
# cleanly after imports + Agent.create() succeed instead of connecting/hanging.
_SANDBOX_SHIM = '''\
import thenvoi as _t
import asyncio as _a

class _MockAgent:
    @classmethod
    def create(cls, **kwargs):
        return cls()
    async def run(self):
        return

_t.Agent = _MockAgent
'''

_SANDBOX_TIMEOUT = 25


def _sandbox_check(path: Path, cwd: str) -> str:
    """Run the integration file with Agent.run mocked to validate imports and
    adapter construction. Returns "" on success, else the captured error."""
    source = path.read_text(encoding="utf-8")
    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", encoding="utf-8", delete=False, dir=cwd
    ) as tmp:
        tmp.write(_SANDBOX_SHIM + source)
        tmp_path = tmp.name

    env = dict(os.environ)
    env.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=_SANDBOX_TIMEOUT,
            cwd=cwd,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return f"Sandbox timed out after {_SANDBOX_TIMEOUT}s (possible hang)."
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        return result.stderr.strip() or f"exited with code {result.returncode}"
    return ""


def _read_folder(root: Path) -> dict[str, str]:
    collected: dict[str, str] = {}
    total = 0
    py_files = sorted(
        (p for p in root.rglob("*.py") if _include(p, root) and p.name != INTEGRATION_FILENAME),
        key=lambda p: (len(p.parts), str(p)),
    )
    for path in py_files:
        if total >= _MAX_TOTAL_CHARS:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > _MAX_FILE_CHARS:
            text = text[:_MAX_FILE_CHARS] + "\n# ... [truncated] ..."
        collected[str(path.relative_to(root))] = text
        total += len(text)
    return collected


def _include(path: Path, root: Path) -> bool:
    return not any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1])


def _format_files(file_contents: dict[str, str]) -> str:
    return "\n\n".join(
        f"### FILE: {name}\n{content}\n### END: {name}"
        for name, content in file_contents.items()
    )


def _strip_fences(code: str) -> str:
    code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
    code = re.sub(r"\n```\s*$", "", code, flags=re.MULTILINE)
    return code.strip()
