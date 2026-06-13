# BAND-hack

# BandAid — Self-Assembling Incident War Rooms

> When production breaks at 3 AM, engineers shouldn't have to play human router.

BandAid is an autonomous incident response system built on [Band](https://band.ai). When the demo checkout API fails, a Watchdog opens an incident room and recruits an Incident Commander, who dynamically assembles specialists — Log Analyst, Fix Engineer, Reviewer, Compliance Officer, and Scribe — to investigate, patch, review, approve, and document the incident.

Built for the **Band of Agents Hackathon** (lablab.ai, June 12–19 2026).

## Architecture

```
Alert → Watchdog → Band Incident Room → Incident Commander
                                              ↓
                         Dynamic recruitment of specialists
                                              ↓
                    Log Analyst → Fix Engineer → Reviewer
                                              ↓
                         Human SRE approval gate
                                              ↓
                         Scribe → Postmortem + Memory
```

## Agents

| Agent              | Framework               | Role                                  |
| ------------------ | ----------------------- | ------------------------------------- |
| Watchdog           | Python SDK (no LLM)     | Monitors health, opens incident rooms |
| Incident Commander | Anthropic               | Classifies, recruits, coordinates     |
| Log Analyst        | LangGraph + Featherless | Root-cause analysis from logs/metrics |
| Fix Engineer       | Claude SDK              | Patches code, opens GitHub PRs        |
| Reviewer           | Codex                   | Cross-model PR review                 |
| Compliance Officer | PydanticAI + AI/ML API  | GDPR/DPDP assessment (conditional)    |
| Scribe             | Anthropic               | Postmortem + Band Memory API          |

## Band features used

- Runtime agent recruitment (`thenvoi_add_participant`, `GET /agent/peers`)
- @mention routing for task handoffs
- Human-in-the-loop approval gates
- Full audit trail (`thenvoi_send_event`)
- Memory API for institutional learning
- Multi-framework orchestration in one room

## Quick start

### 1. Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Docker & Docker Compose
- Band account + Human API key
- API keys: Anthropic, Featherless, AI/ML API (kickoff codes)
- GitHub CLI (`gh`) for real PR flow (optional)

### 2. Install

```bash
git clone <your-repo>
cd Band
cp .env.example .env
cp agent_config.yaml.example agent_config.yaml
uv sync
```

### 3. Start demo app

```bash
cd demo-app
docker compose up --build -d
curl http://localhost:8080/health
```

### 4. Register agents on Band

```bash
# Set BAND_HUMAN_API_KEY in .env first
uv run python scripts/setup_agents.py
# Merge output into agent_config.yaml
```

### 5. Start all agents

```bash
uv run python scripts/run_all.py
```

### 6. Run a demo scenario

```bash
# Pool exhaustion (simple outage)
uv run python scripts/demo.py outage

# PII leak (triggers Compliance Officer)
uv run python scripts/demo.py pii

# Bad config deploy
uv run python scripts/demo.py deploy

# Clear faults
uv run python scripts/demo.py --clear
```

Open the Band UI to watch the war room assemble in real time.

## Demo flow

1. `scripts/demo.py` injects a fault into checkout-api
2. Watchdog detects unhealthy `/health` and creates `INC-*` room
3. Incident Commander classifies and recruits Log Analyst
4. Log Analyst fetches logs/metrics, posts root-cause hypothesis
5. Commander recruits Fix Engineer → opens PR
6. Reviewer critiques PR (cross-model)
7. Commander @mentions human SRE — type **approve** in Band UI
8. Fix Engineer merges and clears chaos (service recovers)
9. Scribe generates postmortem and stores memory

## Project structure

```
band/           Shared config, Band REST client, tools, prompts
agents/         One process per agent (7 total)
demo-app/       FastAPI + Postgres target with /chaos endpoints
scripts/        setup_agents.py, run_all.py, demo.py
tests/          Unit tests
```

## Environment variables

See [`.env.example`](.env.example) for all configuration.

## Hackathon submission

- **Track**: Regulated & High-Stakes Workflows (Track 3) + Software Development (Track 2)
- **Partner tech**: Featherless (Log Analyst), AI/ML API (Compliance Officer)
- **License**: MIT

### Submission checklist

- [ ] Public GitHub repo (this repo)
- [ ] Cover image + slide deck
- [ ] 3–5 min demo video showing Band room collaboration
- [ ] Application URL: demo-app on localhost or deployed instance
- [ ] lablab.ai submission form

## Development

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

## License

MIT — see [LICENSE](LICENSE).
