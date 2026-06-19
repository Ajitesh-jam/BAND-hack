#!/usr/bin/env python3
"""Force-stop all Band company agent processes."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

# Match any process whose command line contains one of these fragments.
AGENT_PATTERNS = (
    "scripts/run_all.py",
    "agents.commander.main",
    "agents.planner.main",
    "agents.coder.main",
    "agents.reviewer.main",
    "agents.github_agent.main",
    "agents.watchdog.main",
    "agents.band_orchestrator.main",
    "documentation_agent/main.py",
)


def _own_pid() -> int:
    return os.getpid()


def find_pids() -> list[tuple[int, str]]:
    """Return (pid, command) for matching agent processes (excluding this script)."""
    me = _own_pid()
    try:
        out = subprocess.check_output(["ps", "-ax", "-o", "pid=,command="], text=True)
    except subprocess.CalledProcessError:
        return []

    hits: list[tuple[int, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == me:
            continue
        cmd = parts[1]
        if "stop_all.py" in cmd:
            continue
        if any(p in cmd for p in AGENT_PATTERNS):
            hits.append((pid, cmd))
    return hits


def _signal_pids(pids: list[int], sig: signal.Signals) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  permission denied for pid {pid}", file=sys.stderr)


def stop_all(*, force: bool = False, quiet: bool = False) -> int:
    hits = find_pids()
    if not hits:
        if not quiet:
            print("No agent processes found.")
        return 0

    if not quiet:
        print(f"Stopping {len(hits)} process(es)...")
        for pid, cmd in hits:
            print(f"  pid {pid}: {cmd[:100]}")

    pids = [pid for pid, _ in hits]
    _signal_pids(pids, signal.SIGTERM)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        alive = [pid for pid in pids if _is_alive(pid)]
        if not alive:
            break
        time.sleep(0.2)

    alive = [pid for pid in pids if _is_alive(pid)]
    if alive and force:
        if not quiet:
            print(f"Force-killing {len(alive)} stubborn process(es)...")
        _signal_pids(alive, signal.SIGKILL)
        time.sleep(0.3)

    remaining = find_pids()
    if remaining:
        if not quiet:
            print(f"Warning: {len(remaining)} process(es) still running.", file=sys.stderr)
        return 1

    if not quiet:
        print("All agents stopped.")
    return 0


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Force-stop all Band company agents")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="SIGKILL any process that ignores SIGTERM after 5s",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="Minimal output")
    args = parser.parse_args()
    return stop_all(force=args.force, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
