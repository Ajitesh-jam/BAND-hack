"""Spawn and track generated/converted Band agents as OS subprocesses.

Each managed agent runs as its own ``subprocess.Popen`` process so it has a real
PID and lifecycle independent of the orchestrator. Stopping the orchestrator or
an individual agent terminates the process only — generated agent folders under
``generated_agents/`` are kept on disk so they can be restarted or rebuilt.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from band.config import ROOT_DIR

logger = logging.getLogger(__name__)


@dataclass
class ManagedAgent:
    name: str
    process: subprocess.Popen
    pid: int
    cwd: str
    log_path: str | None = None


class ProcessManager:
    """Registry and launcher for spawned Band agent subprocesses."""

    def __init__(self) -> None:
        self._agents: dict[str, ManagedAgent] = {}
        self._lock = threading.Lock()
        self._hooks_installed = False

    def spawn(
        self,
        name: str,
        script_path: str,
        cwd: str,
        log_path: str | None = None,
    ) -> dict:
        """Launch ``python script_path`` (from ``cwd``) as a tracked subprocess."""
        self._install_hooks()

        with self._lock:
            existing = self._agents.get(name)
            if existing and existing.process.poll() is None:
                return {
                    "status": "already_running",
                    "name": name,
                    "pid": existing.pid,
                    "message": f"Agent '{name}' already running (pid {existing.pid}).",
                }

        env = dict(os.environ)
        # Ensure the child can import sibling modules plus shared repo packages.
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [cwd, str(ROOT_DIR), env.get("PYTHONPATH", "")])
        )

        log_handle = open(log_path, "w", encoding="utf-8") if log_path else None
        try:
            proc = subprocess.Popen(
                [sys.executable, script_path],
                cwd=cwd,
                env=env,
                stdout=log_handle or subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to spawn %s: %s", name, exc)
            return {"status": "error", "name": name, "pid": None, "message": str(exc)}
        finally:
            # Popen dup'd the fd; we can close our copy of the handle.
            if log_handle is not None:
                try:
                    log_handle.close()
                except Exception:  # noqa: BLE001
                    pass

        managed = ManagedAgent(
            name=name,
            process=proc,
            pid=proc.pid,
            cwd=cwd,
            log_path=log_path,
        )
        with self._lock:
            self._agents[name] = managed

        threading.Thread(target=self._monitor, args=(name, proc), daemon=True).start()
        logger.info("Spawned agent '%s' (pid %d)", name, proc.pid)
        return {
            "status": "deployed",
            "name": name,
            "pid": proc.pid,
            "log_path": log_path,
            "message": f"Agent '{name}' deployed (pid {proc.pid}).",
        }

    def _monitor(self, name: str, proc: subprocess.Popen) -> None:
        returncode = proc.wait()
        logger.info("Agent '%s' (pid %d) exited with code %s", name, proc.pid, returncode)
        with self._lock:
            self._agents.pop(name, None)

    def folder_for(self, name: str) -> str | None:
        """Return the working directory of a tracked agent, if known."""
        with self._lock:
            managed = self._agents.get(name)
            return managed.cwd if managed else None

    def list_agents(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "name": a.name,
                    "pid": a.pid,
                    "running": a.process.poll() is None,
                    "cwd": a.cwd,
                    "log_path": a.log_path,
                }
                for a in self._agents.values()
            ]

    def stop(self, name: str) -> dict:
        with self._lock:
            managed = self._agents.pop(name, None)
        if managed is None:
            return {"status": "not_found", "name": name}

        _terminate(managed.process)
        logger.info("Stopped agent '%s' (pid %d); files kept at %s", name, managed.pid, managed.cwd)
        return {"status": "stopped", "name": name, "pid": managed.pid, "folder": managed.cwd}

    def stop_all(self) -> None:
        with self._lock:
            agents = list(self._agents.values())
            self._agents.clear()
        for managed in agents:
            _terminate(managed.process)
            logger.info(
                "Stopped agent '%s' (pid %d) on shutdown; files kept at %s",
                managed.name,
                managed.pid,
                managed.cwd,
            )

    def _install_hooks(self) -> None:
        if self._hooks_installed:
            return
        self._hooks_installed = True
        atexit.register(self.stop_all)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                prev = signal.getsignal(sig)

                def _handler(signum, frame, _prev=prev):
                    self.stop_all()
                    if callable(_prev):
                        _prev(signum, frame)
                    else:
                        raise KeyboardInterrupt

                signal.signal(sig, _handler)
            except (ValueError, OSError):
                # Not in main thread — atexit still covers cleanup.
                pass


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Error terminating pid %s: %s", proc.pid, exc)


# Module-level singleton shared across the orchestrator's tools.
process_manager = ProcessManager()
