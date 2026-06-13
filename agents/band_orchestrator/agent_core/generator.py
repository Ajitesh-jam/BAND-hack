"""Create a brand-new Band agent from a natural-language description.

The generator scaffolds an agent that mirrors the repo's own agent layout and is
guaranteed to run. Every agent goes into its own uniquely-named folder so new
agents never clash with existing ones:

    generated_agents/<slug>_<uuid8>/
        main.py            # cli entry point
        base.py            # local bootstrap (loads creds, builds adapter, runs)
        agent_config.yaml  # the new agent's own Band credentials
        agent_core/
            __init__.py
            prompt.py      # the role/capabilities prompt (custom_section)
            tools.py       # get_tools() -> list[CustomToolDef] for the agent

The capabilities the user asks for become the agent's ``custom_section`` prompt
and a set of custom tools generated into ``agent_core/tools.py``.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import yaml

from band.config import ROOT_DIR

logger = logging.getLogger(__name__)

GENERATED_DIR = ROOT_DIR / "generated_agents"
_MODEL = "gemini-2.5-flash"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "agent"


def _unique_dir(slug: str) -> Path:
    """Always-unique folder: <slug>_<uuid8>, so agents never clash."""
    return GENERATED_DIR / f"{slug}_{uuid.uuid4().hex[:8]}"


_BASE_TEMPLATE = '''\
"""Local bootstrap for generated Band agent: {name}."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv
from thenvoi import Agent

from band.agents.base import adapter_sdk
from band.config import get_settings

logger = logging.getLogger(__name__)


def load_local_creds() -> dict:
    cfg_path = Path(__file__).resolve().parent / "agent_config.yaml"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {{}}
    return data["agent"]


def run_generated(prompt: str, *, tools=None, enable_memory: bool = True) -> None:
    load_dotenv()
    creds = load_local_creds()
    settings = get_settings()
    adapter = adapter_sdk(
        prompt,
        additional_tools=tools or None,
        enable_memory=enable_memory,
    )
    agent = Agent.create(
        adapter=adapter,
        agent_id=creds["agent_id"],
        api_key=creds["api_key"],
        ws_url=settings.band_ws_url,
        rest_url=settings.band_rest_url,
    )
    asyncio.run(agent.run())
'''


_MAIN_TEMPLATE = '''\
"""Generated Band agent: {name}."""

from __future__ import annotations

import logging

from base import run_generated
from agent_core.prompt import AGENT_PROMPT
from agent_core.tools import get_tools

logging.basicConfig(level=logging.INFO, format="%(asctime)s [{name}] %(message)s")


def cli() -> None:
    run_generated(AGENT_PROMPT, tools=get_tools(), enable_memory=True)


if __name__ == "__main__":
    cli()
'''


_PROMPT_TEMPLATE = 'AGENT_PROMPT = """{prompt_body}"""\n'


_EMPTY_TOOLS = '''\
"""Custom tools for the {name} agent."""

from __future__ import annotations

from thenvoi.runtime.custom_tools import CustomToolDef


def get_tools() -> list[CustomToolDef]:
    """Return the agent's custom tools as (PydanticInputModel, handler) tuples."""
    return []
'''


_TOOLS_SYSTEM_PROMPT = """\
You write a single Python module named tools.py for a Band (thenvoi) agent.

It must expose: def get_tools() -> list[CustomToolDef]
where each item is a tuple (PydanticInputModel, handler_callable).

RULES:
- Output RAW Python ONLY (no markdown fences, no prose).
- Imports allowed: pydantic (BaseModel, Field), typing, stdlib modules,
  and `from thenvoi.runtime.custom_tools import CustomToolDef`.
- Each tool = a pydantic BaseModel whose class name ends in "Input"
  (e.g. AddNumbersInput) and a handler function that takes ONE argument
  (an instance of that model) and returns a JSON-serialisable result.
- The tool name is derived from the model class name minus "Input",
  lowercased. Keep handlers pure and self-contained (no network, no secrets).
- Implement 1-4 small, relevant tools for the described agent. If no concrete
  tools make sense, return an empty list from get_tools().
- get_tools() MUST return the list of (Model, handler) tuples.

Example:

    from __future__ import annotations
    from pydantic import BaseModel, Field
    from thenvoi.runtime.custom_tools import CustomToolDef

    class AddNumbersInput(BaseModel):
        a: float = Field(..., description="first number")
        b: float = Field(..., description="second number")

    def _add(inp: AddNumbersInput) -> float:
        return inp.a + inp.b

    def get_tools() -> list[CustomToolDef]:
        return [(AddNumbersInput, _add)]
"""


def create_agent(
    description: str,
    agent_id: str,
    api_key: str,
    name: str | None = None,
) -> dict:
    """Scaffold a new Band agent folder and return metadata.

    Returns dict: {name, folder, main_path, agent_id, tools_generated}.
    """
    slug = _slugify(name or _derive_name(description))
    folder = _unique_dir(slug)
    final_name = folder.name

    (folder / "agent_core").mkdir(parents=True, exist_ok=True)

    prompt_body = _build_prompt(final_name, description)

    (folder / "base.py").write_text(_BASE_TEMPLATE.format(name=final_name), encoding="utf-8")
    (folder / "main.py").write_text(_MAIN_TEMPLATE.format(name=final_name), encoding="utf-8")
    (folder / "agent_core" / "__init__.py").write_text("", encoding="utf-8")
    (folder / "agent_core" / "prompt.py").write_text(
        _PROMPT_TEMPLATE.format(prompt_body=_escape(prompt_body)), encoding="utf-8"
    )

    tools_generated = _write_tools(folder, final_name, description)

    config = {
        "agent": {
            "name": final_name,
            "agent_id": agent_id,
            "api_key": api_key,
        }
    }
    (folder / "agent_config.yaml").write_text(
        yaml.safe_dump(config, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    logger.info("Generated agent '%s' at %s (tools_generated=%s)", final_name, folder, tools_generated)
    return {
        "name": final_name,
        "folder": str(folder),
        "main_path": str(folder / "main.py"),
        "agent_id": agent_id,
        "tools_generated": tools_generated,
    }


def _write_tools(folder: Path, name: str, description: str) -> bool:
    """Generate agent_core/tools.py via the LLM, validating it can import and
    return a list. Falls back to an empty (but valid) tools module on failure."""
    tools_path = folder / "agent_core" / "tools.py"
    fallback = _EMPTY_TOOLS.format(name=name)

    try:
        code = _strip_fences(_gemini(_TOOLS_SYSTEM_PROMPT, f"Agent description: {description}"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("tools.py generation failed (%s) — using empty fallback", exc)
        tools_path.write_text(fallback, encoding="utf-8")
        return False

    if "def get_tools" not in code:
        tools_path.write_text(fallback, encoding="utf-8")
        return False

    tools_path.write_text(code, encoding="utf-8")
    if _tools_import_ok(folder):
        return True

    logger.warning("Generated tools.py failed validation — using empty fallback")
    tools_path.write_text(fallback, encoding="utf-8")
    return False


def _tools_import_ok(folder: Path) -> bool:
    """Import agent_core.tools and call get_tools() in a subprocess."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(folder), env.get("PYTHONPATH", "")]))
    check = (
        "from agent_core.tools import get_tools; "
        "t = get_tools(); "
        "assert isinstance(t, list)"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", check],
            cwd=str(folder),
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        logger.warning("tools.py validation error: %s", result.stderr.strip()[:300])
        return False
    return True


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
            max_output_tokens=4096,
            temperature=0.1,
        ),
    )
    return response.text or ""


def _strip_fences(code: str) -> str:
    code = re.sub(r"^```(?:python)?\s*\n", "", code, flags=re.MULTILINE)
    code = re.sub(r"\n```\s*$", "", code, flags=re.MULTILINE)
    return code.strip()


def _derive_name(description: str) -> str:
    words = re.findall(r"[a-zA-Z]+", description)[:3]
    return "_".join(words) if words else "agent"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def _build_prompt(name: str, description: str) -> str:
    return (
        f"You are {name}, an autonomous Band agent.\n\n"
        f"Your role and capabilities:\n{description.strip()}\n\n"
        "Operating guidelines:\n"
        "- Collaborate in the shared Band room. Read the conversation and act on requests directed at you.\n"
        "- Use your custom tools when they fit the request.\n"
        "- Use @mentions to hand off to other participants when their expertise is needed.\n"
        "- Use thenvoi_send_event to log meaningful progress for the audit trail.\n"
        "- Be concise, helpful, and stay within your stated role."
    )
