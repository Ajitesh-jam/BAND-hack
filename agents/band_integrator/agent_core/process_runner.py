"""
Process manager: spawns and tracks deployed Band agent scripts as persistent
asyncio subprocesses.

Each spawned process is stored by a stable key derived from the script path so
callers can check status, list active agents, or terminate them.

Thread safety: this module is intended to be used exclusively from the main
asyncio event loop (FastAPI + agent.run() both run on the same loop), so no
additional locking is needed.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ManagedProcess:
    script_path: str
    process: asyncio.subprocess.Process
    pid: int


class ProcessManager:
    """Registry and launcher for deployed Band agent subprocesses."""

    def __init__(self) -> None:
        self._agents: dict[str, ManagedProcess] = {}

    async def spawn(self, script_path: str) -> dict:
        """
        Launch the script at `script_path` as a persistent asyncio subprocess.

        Credentials are already hardcoded inside the generated script so no
        environment variable injection is needed here.

        Returns a dict suitable for JSON serialisation:
          {"status": "deployed", "pid": int, "message": str}
          {"status": "error",    "pid": None, "message": str}
        """
        key = Path(script_path).name

        if key in self._agents:
            existing = self._agents[key]
            if existing.process.returncode is None:
                logger.info("Agent %s already running as pid %d", key, existing.pid)
                return {
                    "status": "deployed",
                    "pid": existing.pid,
                    "message": f"Agent '{key}' already running (pid {existing.pid}).",
                }
            del self._agents[key]

        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception as exc:
            logger.error("Failed to spawn %s: %s", script_path, exc)
            return {
                "status": "error",
                "pid": None,
                "message": f"Failed to spawn agent: {exc}",
            }

        managed = ManagedProcess(
            script_path=script_path,
            process=proc,
            pid=proc.pid,
        )
        self._agents[key] = managed
        logger.info("Spawned agent %s as pid %d", key, proc.pid)

        # Fire-and-forget monitor to clean up when the process exits
        asyncio.create_task(self._monitor(key, proc), name=f"monitor-{key}")

        return {
            "status": "deployed",
            "pid": proc.pid,
            "message": f"Agent '{key}' deployed successfully (pid {proc.pid}).",
        }

    async def _monitor(self, key: str, proc: asyncio.subprocess.Process) -> None:
        """Wait for the process to exit and log the outcome."""
        returncode = await proc.wait()
        logger.info("Agent %s (pid %d) exited with code %d", key, proc.pid, returncode)
        self._agents.pop(key, None)

    def list_agents(self) -> list[dict]:
        """Return a snapshot of currently tracked agents."""
        return [
            {
                "key": key,
                "pid": mp.pid,
                "script_path": mp.script_path,
                "running": mp.process.returncode is None,
            }
            for key, mp in self._agents.items()
        ]

    async def terminate(self, key: str) -> bool:
        """Send SIGTERM to the agent identified by `key`. Returns True if found."""
        mp = self._agents.get(key)
        if mp is None:
            return False
        mp.process.terminate()
        return True


# Module-level singleton used by both graph.py and main.py
process_manager = ProcessManager()