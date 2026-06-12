#!/usr/bin/env python3
"""Start all BandAid agent processes."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

AGENTS = [
    ("commander", [sys.executable, "-m", "agents.commander.main"]),
    ("log_analyst", [sys.executable, "-m", "agents.log_analyst.main"]),
    ("fix_engineer", [sys.executable, "-m", "agents.fix_engineer.main"]),
    ("reviewer", [sys.executable, "-m", "agents.reviewer.main"]),
    ("compliance", [sys.executable, "-m", "agents.compliance.main"]),
    ("scribe", [sys.executable, "-m", "agents.scribe.main"]),
    ("watchdog", [sys.executable, "-m", "agents.watchdog.main"]),
]

# Core agents — if one exits, shut down the rest
REQUIRED_AGENTS = {"commander", "log_analyst", "fix_engineer", "reviewer", "scribe", "watchdog"}


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
        help="Do not start Compliance Officer (only needed for PII scenarios)",
    )
    args = parser.parse_args()

    procs: list[tuple[str, subprocess.Popen]] = []
    agents = [a for a in AGENTS if not (args.skip_watchdog and a[0] == "watchdog")]
    agents = [a for a in agents if not (args.skip_compliance and a[0] == "compliance")]

    try:
        for name, cmd in agents:
            proc = subprocess.Popen(
                cmd,
                cwd=ROOT,
                env={**dict(**__import__("os").environ), "PYTHONPATH": str(ROOT)},
            )
            procs.append((name, proc))
            print(f"Started {name} (pid={proc.pid})")
            time.sleep(0.5)

        print("\nAll agents running. Ctrl+C to stop.\n")
        while True:
            for name, proc in procs:
                if proc.poll() is not None:
                    code = proc.returncode or 1
                    if name in REQUIRED_AGENTS:
                        print(f"Required agent {name} exited with code {code}")
                        raise SystemExit(code)
                    print(f"Optional agent {name} exited with code {code} (continuing)")
                    procs = [(n, p) for n, p in procs if p.poll() is None]
            time.sleep(2)
    except KeyboardInterrupt:
        print("\nStopping agents...")
        for name, proc in procs:
            proc.terminate()
        for name, proc in procs:
            proc.wait(timeout=5)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
