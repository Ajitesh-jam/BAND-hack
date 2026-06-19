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
    # documentation_agent uses script-style local imports (base/agent_core), so it
    # must be launched by path: Python adds the script's dir to sys.path, while the
    # PYTHONPATH=ROOT below keeps shared band.* packages importable.
    (
        "documentation_agent",
        [sys.executable, str(ROOT / "agents" / "documentation_agent" / "main.py")],
    ),
    ("coder", [sys.executable, "-m", "agents.coder.main"]),
    ("reviewer", [sys.executable, "-m", "agents.reviewer.main"]),
    ("watchdog", [sys.executable, "-m", "agents.watchdog.main"]),
]

BAND_ORCHESTRATOR = (
    "band_orchestrator",
    [sys.executable, "-m", "agents.band_orchestrator.main"],
)

# Core agents — if one exits, shut down the rest
REQUIRED_AGENTS = {"commander", "planner", "documentation_agent", "coder", "reviewer", "watchdog"}


def _select_agents(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    if args.run_only_band_orc:
        return [BAND_ORCHESTRATOR]

    agents = list(AGENTS)
    if args.skip_watchdog:
        agents = [a for a in agents if a[0] != "watchdog"]
    if args.skip_compliance:
        # Legacy flag retained for compatibility; compliance is no longer in the default roster.
        pass
    if args.skip_reviewer:
        agents = [a for a in agents if a[0] != "reviewer"]
    if args.run_band_orchestrator:
        agents.append(BAND_ORCHESTRATOR)
    return agents


def _stop_procs(procs: list[tuple[str, subprocess.Popen]], *, quiet: bool = False) -> None:
    alive = [(name, proc) for name, proc in procs if proc.poll() is None]
    if not alive:
        return
    if not quiet:
        print("\nStopping agents...")
    for _, proc in alive:
        try:
            if hasattr(os, "getpgid"):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.monotonic() + 5.0
    for name, proc in alive:
        if proc.poll() is not None:
            continue
        remaining = max(0.0, deadline - time.monotonic())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            if not quiet:
                print(f"  force-killing {name} (pid={proc.pid})")
            try:
                if hasattr(os, "getpgid"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
            proc.wait(timeout=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all BandAid agents")
    parser.add_argument(
        "--skip-watchdog",
        action="store_true",
        help="Start only LLM agents (useful when testing manually)",
    )
    parser.add_argument(
        "--skip-compliance",
        action="store_true",
        help="Legacy no-op; compliance is not part of the default company roster",
    )
    parser.add_argument(
        "--skip-reviewer",
        action="store_true",
        help="Do not start Reviewer (only needed for PR scenarios)",
    )
    parser.add_argument(
        "--run-band-orchestrator",
        action="store_true",
        help="Also start Band Orchestrator (for company code-context agent creation)",
    )
    parser.add_argument(
        "--run-only-band-orc",
        action="store_true",
        help="Start only Band Orchestrator",
    )
    args = parser.parse_args()

    if args.run_only_band_orc and (
        args.skip_watchdog
        or args.skip_compliance
        or args.skip_reviewer
        or args.run_band_orchestrator
    ):
        parser.error("--run-only-band-orc cannot be combined with other agent flags")

    agents = _select_agents(args)
    required = {"band_orchestrator"} if args.run_only_band_orc else REQUIRED_AGENTS

    procs: list[tuple[str, subprocess.Popen]] = []
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    exit_code = 0
    shutdown = False

    def _request_shutdown(signum: int | None = None, _frame=None) -> None:
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

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

        print("\nAll agents running. Ctrl+C to stop.\n")
        while not shutdown:
            for name, proc in procs:
                if proc.poll() is not None:
                    code = proc.returncode or 1
                    if name in required:
                        print(f"Required agent {name} exited with code {code}")
                        exit_code = code
                        shutdown = True
                        break
                    print(f"Optional agent {name} exited with code {code} (continuing)")
                    procs = [(n, p) for n, p in procs if p.poll() is None]
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown = True
    finally:
        _stop_procs(procs)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
