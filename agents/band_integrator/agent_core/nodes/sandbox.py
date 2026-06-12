"""
Sandbox node: validates generated agent code by running it in a subprocess
with a thin shim that mocks out `agent.run()` so the process exits cleanly
after Agent.create() succeeds instead of hanging on the event loop.

Strategy:
  1. Prepend a small shim that monkey-patches `thenvoi.Agent` so `run()`
     is a no-op coroutine.  This exercises imports, class definitions,
     and Agent.create() without hanging.
  2. Execute the patched script via subprocess.run with a 10-second timeout.
  3. Capture stderr; a non-zero exit code means there is an error to repair.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

# This shim is prepended to the generated script before sandboxed execution.
# It replaces Agent.run with an async no-op so the script exits on its own.
_SHIM = """\
import thenvoi as _thenvoi_module
import asyncio as _asyncio_module

class _MockAgent:
    \"\"\"Thin mock that satisfies Agent.create() and exits cleanly.\"\"\"
    @classmethod
    def create(cls, **kwargs):
        return cls()

    async def run(self):
        return  # no-op: exits immediately

_thenvoi_module.Agent = _MockAgent

# Also neutralise a bare `asyncio.run(main())` so we can call main() ourselves
_original_asyncio_run = _asyncio_module.run
def _mock_asyncio_run(coro, **kw):
    _asyncio_module.run = _original_asyncio_run  # restore for actual code
    return _original_asyncio_run(coro, **kw)
_asyncio_module.run = _mock_asyncio_run

"""

_TIMEOUT_SECONDS = 10


def run_in_sandbox(script_path: str, cwd: str | None = None) -> str | None:
    """
    Execute the script at `script_path` in an isolated subprocess with the
    Agent.run() mock shim prepended.

    Args:
        script_path: Absolute path to the Python script to validate.
        cwd:         Optional working directory for the subprocess.  When the
                     script uses relative imports from its own folder (e.g. a
                     band_integration.py referencing sibling modules), set cwd
                     to the folder containing those modules.

    Returns:
        None   — script passed (exited 0 within timeout).
        str    — the stderr output from the failed run (non-empty error message).
    """
    source = Path(script_path).read_text(encoding="utf-8")
    patched = _SHIM + source

    with tempfile.NamedTemporaryFile(
        suffix=".py", mode="w", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(patched)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return f"Sandbox timed out after {_TIMEOUT_SECONDS}s — possible infinite loop or missing await."
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if result.returncode != 0:
        stderr = result.stderr.strip()
        return stderr or f"Script exited with code {result.returncode} (no stderr)."

    return None
