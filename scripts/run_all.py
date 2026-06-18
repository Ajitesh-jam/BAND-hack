#!/usr/bin/env python3
"""Start all BandAid agent processes."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AGENTS = [
    ("commander", [sys.executable, "-m", "agents.commander.main"]),
    ("planner", [sys.executable, "-m", "agents.planner.main"]),
    (
        "documentation_agent",
        [sys.executable, str(ROOT / "agents" / "documentation_agent" / "main.py")],
    ),
    ("coder", [sys.executable, "-m", "agents.coder.main"]),
    ("github_agent", [sys.executable, "-m", "agents.github_agent.main"]),
    ("reviewer", [sys.executable, "-m", "agents.reviewer.main"]),
    ("watchdog", [sys.executable, "-m", "agents.watchdog.main"]),
]

BAND_ORCHESTRATOR = (
    "band_orchestrator",
    [sys.executable, "-m", "agents.band_orchestrator.main"],
)

REQUIRED_AGENTS = {
    "commander",
    "planner",
    "documentation_agent",
    "coder",
    "github_agent",
    "reviewer",
    "watchdog",
}

_shutdown = False


def _select_agents(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    if args.run_only_band_orc:
        return [BAND_ORCHESTRATOR]

    agents = list(AGENTS)
    if args.skip_watchdog:
        agents = [a for a in agents if a[0] != "watchdog"]
    if args.skip_compliance:
        pass
    if args.skip_reviewer:
        agents = [a for a in agents if a[0] != "reviewer"]
    if args.run_band_orchestrator:
        agents.append(BAND_ORCHESTRATOR)
    return agents


def _kill_proc(proc: subprocess.Popen, sig: signal.Signals = signal.SIGTERM) -> None:
    if proc.poll() is not None:
        return
    try:
        # Each agent was started in its own session — kill the whole group.
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError):
        try:
            proc.send_signal(sig)
        except ProcessLookupError:
            pass


def _stop_all(procs: list[tuple[str, subprocess.Popen]], *, force: bool = False) -> None:
    if not procs:
        return
    print("\nStopping agents...")
    for _, proc in procs:
        _kill_proc(proc, signal.SIGTERM)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if all(p.poll() is not None for _, p in procs):
            return
        time.sleep(0.2)

    alive = [(name, p) for name, p in procs if p.poll() is None]
    if not alive:
        return

    if force:
        print(f"Force-killing {len(alive)} agent(s)...")
        for _, proc in alive:
            _kill_proc(proc, signal.SIGKILL)
        for _, proc in alive:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
    else:
        for name, proc in alive:
            print(f"  {name} (pid={proc.pid}) still running — run scripts/stop_all.py --force")


def main() -> int:
    global _shutdown

    parser = argparse.ArgumentParser(description="Run all BandAid agents")
    parser.add_argument("--skip-watchdog", action="store_true")
    parser.add_argument("--skip-compliance", action="store_true")
    parser.add_argument("--skip-reviewer", action="store_true")
    parser.add_argument("--run-band-orchestrator", action="store_true")
    parser.add_argument("--run-only-band-orc", action="store_true")
    args = parser.parse_args()

    if args.run_only_band_orc and (
        args.skip_watchdog or args.skip_compliance or args.skip_reviewer or args.run_band_orchestrator
    ):
        parser.error("--run-only-band-orc cannot be combined with other agent flags")

    agents = _select_agents(args)
    required = {"band_orchestrator"} if args.run_only_band_orc else REQUIRED_AGENTS

    procs: list[tuple[str, subprocess.Popen]] = []
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    def _handle_signal(signum: int, _frame: object) -> None:
        global _shutdown
        _shutdown = True
        _stop_all(procs, force=True)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        for name, cmd in agents:
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                env=env,
                start_new_session=True,
            )
            procs.append((name, proc))
            print(f"Started {name} (pid={proc.pid})")
            time.sleep(0.5)

        print("\nAll agents running. Ctrl+C to stop all.\n")

        while not _shutdown:
            for name, proc in procs:
                if proc.poll() is not None:
                    code = proc.returncode or 1
                    if name in required:
                        print(f"Required agent {name} exited with code {code}")
                        _stop_all(procs, force=True)
                        return code
                    print(f"Optional agent {name} exited with code {code} (continuing)")
            procs = [(n, p) for n, p in procs if p.poll() is None]
            time.sleep(2)
    except KeyboardInterrupt:
        _stop_all(procs, force=True)
        return 0

    _stop_all(procs, force=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
