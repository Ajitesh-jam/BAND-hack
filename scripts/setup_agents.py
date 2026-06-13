#!/usr/bin/env python3
"""Register BandAid agents on Band via Human API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

from band.client import BandHumanClient
from band.registry import AGENT_DEFINITIONS, save_agent_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Register BandAid agents on Band")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print agents that would be registered without calling API",
    )
    args = parser.parse_args()

    load_dotenv()

    if args.dry_run:
        for key, spec in AGENT_DEFINITIONS.items():
            print(f"Would register: {key} -> {spec['name']}")
        return 0

    import yaml

    from band.config import get_settings

    config_path = get_settings().agent_config_path
    existing_config: dict[str, dict[str, str]] = {}
    if config_path.exists():
        with config_path.open() as f:
            existing_config = yaml.safe_load(f) or {}

    registered: dict[str, dict[str, str]] = dict(existing_config)
    new_count = 0

    with BandHumanClient() as client:
        existing_agents = {a.get("name", ""): a for a in client.list_agents()}
        placeholders = {"your-watchdog-api-key", "your-commander-api-key", "<your-api-key>"}

        def _is_placeholder(entry: dict[str, str]) -> bool:
            api_key = entry.get("api_key", "")
            agent_id = entry.get("agent_id", "")
            return (
                not api_key
                or api_key.startswith("your-")
                or agent_id.startswith("00000000-0000-0000-0000-")
            )

        for key, spec in AGENT_DEFINITIONS.items():
            if key in existing_config and not _is_placeholder(existing_config[key]):
                print(f"SKIP {spec['name']}: already in {config_path.name}")
                continue
            if spec["name"] in existing_agents:
                agent = existing_agents[spec["name"]]
                print(f"SKIP {spec['name']}: already on Band (id={agent.get('id')})")
                print("  Add credentials to agent_config.yaml manually from Band UI.")
                continue
            result = client.register_agent(spec["name"], spec["description"])
            # Response shape: {"agent": {"id": ...}, "credentials": {"api_key": ...}}
            agent_info = result.get("agent") or {}
            credentials = result.get("credentials") or {}
            agent_id = agent_info.get("id") or result.get("id")
            api_key = credentials.get("api_key") or result.get("api_key")
            if not agent_id or not api_key:
                print(f"ERROR registering {spec['name']}: unexpected response {result}")
                return 1
            registered[key] = {
                "agent_id": agent_id,
                "api_key": api_key,
                "handle": spec["name"],
            }
            new_count += 1
            print(f"OK {spec['name']}: id={agent_id}")

    if new_count == 0:
        print("No new agents registered.")
        return 0

    path = save_agent_config(registered)
    print(f"\nUpdated {path} ({new_count} new agent(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
