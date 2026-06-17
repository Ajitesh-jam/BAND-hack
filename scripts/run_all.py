#!/usr/bin/env python3
"""Start the Band Orchestrator (it bootstraps company_agent + watchdog)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ORCHESTRATOR = (
    "band_orchestrator",
    [sys.executable, "-m", "agents.band_orchestrator.main"],
)

REQUIRED_AGENTS = {"band_orchestrator"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Band Orchestrator (bootstraps the dev team)")
    parser.add_argument(
        "--run-only-orchestrator",
        action="store_true",
        help="Start only Band Orchestrator (default behavior)",
    )
    args = parser.parse_args()
    _ = args  # reserved for future flags

    procs: list[tuple[str, subprocess.Popen]] = []
    env = {**os.environ, "PYTHONPATH": str(ROOT)}

    try:
        name, cmd = ORCHESTRATOR
        proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
        procs.append((name, proc))
        print(f"Started {name} (pid={proc.pid}) — bootstraps company_agent + watchdog")
        print("\nOrchestrator running. Ctrl+C to stop.\n")

        while True:
            for name, proc in procs:
                if proc.poll() is not None:
                    code = proc.returncode or 1
                    if name in REQUIRED_AGENTS:
                        print(f"Required agent {name} exited with code {code}")
                        raise SystemExit(code)
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping orchestrator...")
        for _, proc in procs:
            proc.terminate()
        for _, proc in procs:
            proc.wait(timeout=5)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
