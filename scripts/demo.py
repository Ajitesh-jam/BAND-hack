#!/usr/bin/env python3
"""BandAid demo scenarios — inject faults and walk through incident flows."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from band.tools import demo_app

SCENARIOS = {
    "outage": {
        "fault": "pool_exhaustion",
        "description": "Database connection pool exhaustion → API downtime",
    },
    "pii": {
        "fault": "pii_leak",
        "description": "Error storm leaking PII into logs → triggers Compliance Officer",
    },
    "deploy": {
        "fault": "bad_config",
        "description": "Bad config deploy → elevated error rate",
    },
}


def run_scenario(name: str, wait_s: float) -> None:
    scenario = SCENARIOS[name]
    print(f"\n=== Scenario: {name} ===")
    print(scenario["description"])
    print("Clearing any active faults...")
    demo_app.clear_chaos()
    time.sleep(1)
    print(f"Injecting fault: {scenario['fault']}")
    result = demo_app.trigger_chaos(scenario["fault"])
    print(f"Result: {result}")
    print("\nWatchdog should open an incident room within ~5s.")
    print("Open Band UI to observe agent collaboration.")
    print(f"Waiting {wait_s}s for demo...")
    time.sleep(wait_s)
    status = demo_app.fetch_chaos_status()
    health = demo_app.fetch_health()
    print(f"Chaos status: {status.get('body')}")
    print(f"Health: {health.get('body')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run BandAid demo scenarios")
    parser.add_argument(
        "scenario",
        nargs="?",
        choices=[*SCENARIOS.keys(), "all"],
        default="outage",
        help="Which scenario to run",
    )
    parser.add_argument("--wait", type=float, default=30.0, help="Seconds to wait after fault injection")
    parser.add_argument("--clear", action="store_true", help="Clear faults and exit")
    args = parser.parse_args()

    load_dotenv()

    if args.clear:
        print(demo_app.clear_chaos())
        return 0

    if args.scenario == "all":
        for name in SCENARIOS:
            run_scenario(name, args.wait)
        return 0

    run_scenario(args.scenario, args.wait)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
