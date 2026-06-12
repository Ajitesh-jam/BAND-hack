# AI Founding Team Engine – Sprint Plan & Execution Roadmap

## Goal
Create a **production‑ready** AI‑first platform that dynamically assembles a virtual founding team, **starting with a solid wireframe and app flow** and iteratively layering expert agents, quick‑start agents, governance, and CI/CD. Each sprint delivers a shippable increment, with automated tests, linting, and deployment pipelines.

---

## High‑Level Timeline (9 months, 6 sprints)
| Sprint | Duration | Core Deliverable | Wireframe / Flow Milestone |
|-------|----------|------------------|----------------------------|
| **Sprint 1** | 2 weeks | **Foundations & Wireframe** – UI mock‑ups, base API, authentication, CI pipeline scaffold. | Low‑fidelity wireframes for Founder onboarding, quick‑start palette, and dashboard layout. |
| **Sprint 2** | 2 weeks | **Dynamic Agent Orchestrator (MVP)** – intent parser, meta‑orchestrator, CTO & Product agents. | End‑to‑end flow: Founder prompt → Orchestrator → Product & CTO agents → Draft Lean Canvas & Architecture (first iteration). |
| **Sprint 3** | 2 weeks | **Quick‑Start Proprietary Agents** – Repo‑Scaffolder, Pitch‑Deck Builder, Legal Boilerplate, Growth‑Plan. | UI integration of Quick‑Start palette; dashboard shows real‑time agent status. |
| **Sprint 4** | 2 weeks | **Expert‑Layered Agents** – LoRA fine‑tuning, RAG pipelines, domain tools (C4 diagram, cost estimator, legal‑risk scorer). | Updated flow where each core role calls its RAG + tool chain; confidence score displayed in dashboard. |
| **Sprint 5** | 2 weeks | **Governance, Approval Gates & Ensemble Verification** – dual‑LLM check, human‑approval UI, compliance logging. | Full approval loop added to the flow; compliance tab appears in dashboard. |
| **Sprint 6** | 2 weeks | **Polish, Scaling & CI/CD Hardened** – autoscaling, load testing, full test coverage, CI pipelines for every component, production‑ready release. | Final app flow diagram showing all agents, orchestrator, fallback, monitoring, and deployment pipeline. |

---

## Sprint Details

### Sprint 1 – Foundations & Wireframe
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **Kick‑off & Requirements Review** | PM + PO | Updated PRD (already in `PRD.md`) |
| **Low‑fidelity Wireframes** (Figma/Sketch) | UX Designer | Screens: Welcome, Prompt Wizard, Quick‑Start Palette, Dashboard (empty state). |
| **User‑Flow Diagram** (Lucidchart) | UX Designer | Flow: `Home → Prompt Wizard → Orchestrator → Agent Status → Review/Approve → Final Report`. |
| **Project Scaffold** (GitHub repo) | Dev Lead | `main` branch with `frontend/`, `backend/`, `ci/` directories; GitHub Actions workflow stub. |
| **CI Pipeline Boilerplate** | DevOps | GitHub Actions: lint (markdown, yaml, python), unit test placeholder, build Docker images (frontend & backend). |
| **Authentication** (OAuth via GitHub) | Backend | Minimal API token exchange, stored in `.env.example`. |
| **Documentation** | All | Update `README.md` with sprint goal and contribution guidelines. |
| **Definition of Done** | Team | Wireframes approved, repo scaffold merged to `dev‑sprint‑1`, CI pipeline passes lint. |

**Key Acceptance Tests** (automated via GitHub Actions):
- `npm run lint` for frontend, `flake8` for backend, `markdownlint` for docs.
- Build Docker images and push to GitHub Packages (dry‑run).
- Verify OAuth flow works locally with a mock client.

---

### Sprint 2 – Dynamic Agent Orchestrator (MVP)
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **Intent Parser** (LLM‑driven) | NLP Engineer | `backend/intent_parser.py` – uses Claude‑3.5 via `hermes` SDK. |
| **Meta‑Orchestrator** | Backend Lead | `backend/orchestrator.py` – receives parsed intent, decides which roles to spin up, registers them on Band. |
| **CTO Agent (basic)** | Backend Engineer | Prompt template `agents/cto_system_prompt.md`, minimal toolset (cloud‑service lookup, cost estimator stub). |
| **Product Manager Agent (basic)** | Backend Engineer | Prompt template `agents/product_system_prompt.md`, lean‑canvas generator tool. |
| **Band Integration Stub** | Integration Engineer | Minimal SDK wrapper that posts messages to a local Band mock server. |
| **Frontend Flow** | Frontend Engineer | Add UI screens: Prompt Wizard → “Generating Team…” spinner → Agent list (CTO, Product) with simple status badges. |
| **Unit Tests** | QA | Tests for `intent_parser`, `orchestrator` decision matrix, mock Band calls (`pytest`). |
| **CI Enhancements** | DevOps | Add lint for new Python files, run unit tests on push. |
| **Definition of Done** | Team | Founder prompt `"I want to build an AI health‑tracker"` produces CTO & Product agents, both return mock artefacts; UI shows them; CI passes. |

**Acceptance Criteria**
- Intent parser extracts domain, needed roles, milestones with ≥ 90 % precision on a 5‑sample test set.
- Orchestrator creates agent objects, assigns unique IDs, stores them in Redis (in‑memory for dev).
- Frontend displays agents list with live status (e.g., `pending → completed`).
- End‑to‑end test (Cypress) runs a simulated founder flow and asserts final artefacts appear.

---

### Sprint 3 – Quick‑Start Proprietary Agents
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **Repo‑Scaffolder** | Backend Engineer | `agents/repo_scaffolder.py` – generates a cookiecutter repo, runs `git init`, adds CI GitHub Actions file. |
| **Pitch‑Deck Builder** | Backend Engineer | `agents/pitch_deck.py` – creates a markdown deck, runs a locally‑hosted `pandoc` conversion. |
| **Legal Boilerplate Generator** | Backend Engineer | `agents/legal_boilerplate.py` – selects jurisdiction template, fills placeholders. |
| **Growth‑Plan Generator** | Backend Engineer | `agents/growth_plan.py` – outputs a 30‑day acquisition plan in markdown. |
| **Quick‑Start UI Palette** | Frontend Engineer | Add toolbar with icons/buttons for each proprietary agent; clicking sends a command to the orchestrator (bypasses intent parser). |
| **Integration Tests** | QA | End‑to‑end test that each quick‑start button triggers the agent and returns a file download. |
| **CI/CD Add‑ons** | DevOps | Build Docker images for each agent as separate micro‑services; tag with `quick-start/<agent>` and push to GHCR. |
| **Definition of Done** | Team | All four agents callable from UI, produce artefacts, CI runs unit + integration tests, Docker images built. |

**Acceptance Criteria**
- Founder can click “Repo‑Scaffolder”, see a spinner, and receive a zip of the generated repo.
- Each quick‑start agent runs in ≤ 8 seconds (including any external API calls).
- All artefacts are stored in a temporary S3 bucket (mocked locally) and a download link appears in the dashboard.

---

### Sprint 4 – Expert‑Layered Agents (RAG + LoRA)
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **LoRA Fine‑Tuning** (role‑specific) | ML Engineer | LoRA checkpoints stored under `~/.hermes/agents/` (`product.lora`, `cto.lora`, `growth.lora`, `legal.lora`). |
| **RAG Vector Stores** | Data Engineer | Separate Pinecone/Weaviate indexes for each role: `product_playbooks`, `cto_tech_trends`, `legal_regulations`, `growth_cases`. |
| **Domain Tools** | Backend Engineer | `tools/c4_renderer.py` (Mermaid → PNG), `tools/cost_estimator.py` (AWS pricing API), `tools/legal_risk_scorer.py`. |
| **Enhanced Agent Prompts** | Prompt Engineer | System prompts reference the LoRA and include a “retrieve relevant docs before responding” instruction. |
| **Orchestrator Confidence Loop** | Backend Lead | After each agent finishes, it returns `{confidence: 0‑1, issues: []}`; orchestrator decides whether to request a refinement pass. |
| **Frontend Updates** | Frontend Engineer | Dashboard now shows a confidence gauge per agent and a “Refine” button when confidence < 0.85. |
| **Test Suite Expansion** | QA | Add RAG integration tests (mock vector DB), LoRA inference tests (ensure model loads). |
| **Definition of Done** | Team | All four core agents run with LoRA + RAG, produce artefacts with confidence scores, UI reflects them, CI runs full test suite. |

**Acceptance Criteria**
- Product Agent returns a Lean Canvas with a confidence ≥ 0.85 on the test dataset.
- CTO Agent outputs a C4 diagram and cost estimate; confidence ≥ 0.80.\n---

### Sprint 5 – Governance, Approval Gates & Ensemble Verification
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **Dual‑LLM Verification** | ML Engineer | Wrapper `agents/dual_verify.py` that calls Claude‑3.5 and GPT‑4‑Turbo, diffs the outputs. |
| **Human‑Approval UI** | Frontend Engineer | Modal dialog with generated artefact preview + “Approve / Reject” buttons; on approve, orchestrator proceeds to next role. |
| **Compliance Logging** | Backend Engineer | Central audit log (`logs/compliance.log`) with timestamp, agent ID, rule triggered, founder decision. |
| **Policy Engine** | Security Engineer | Simple rule engine that checks legal artefacts for missing clauses, architecture for disallowed services, growth plans for prohibited channels. |
| **End‑to‑End Tests** | QA | Cypress test that simulates a full flow, forces a low confidence (mocked) and verifies the approval modal appears. |
| **CI Enhancements** | DevOps | Add secret scanning (`git‑secret`), lint for policy files, and a step that runs the dual‑LLM verification on a sample artefact. |
| **Definition of Done** | Team | Critical artefacts (legal contract, architecture diagram) go through dual‑LLM verification and require founder approval before being marked final. |

**Acceptance Criteria**
- When confidence < 0.85, orchestrator automatically triggers a refinement pass.
- Founder must click “Approve” to move forward; the decision is persisted in the audit log.
- Dual‑LLM diff shows any discrepancy highlighted in the UI.

---

### Sprint 6 – Polish, Scaling & CI/CD Hardened
| Activity | Owner | Artefacts |
|----------|-------|-----------|
| **Autoscaling on Kubernetes** | DevOps | Helm chart with horizontal pod autoscaler (CPU > 70 % → replica +1). |
| **Load Testing** | QA | Locust scripts simulating 200 concurrent founder sessions; target < 2 s avg response time. |
| **Full Test Coverage** | QA | Unit (≥ 80 %), integration (≥ 70 %), end‑to‑end (≥ 60 %). Coverage report published as PR comment. |
| **Security Hardening** | Security Engineer | Enable secret redaction, scanning for API keys in logs, enforce CSP on frontend. |
| **Production‑Ready CI/CD** | DevOps | GitHub Actions workflow:
  - `build` (Docker multi‑stage for frontend & backend)
  - `test` (run all suites, upload coverage, run security scan)
  - `release` (tag, push images to GHCR, trigger ArgoCD rollout)
| **Monitoring & Alerting** | SRE | Prometheus + Grafana dashboards for agent latency, queue length, confidence scores; alerts on confidence‑fall‑below 0.7. |
| **Documentation & Handoff** | Technical Writer | Updated `docs/` with architecture diagram, deployment guide, operator runbook. |
| **Definition of Done** | Team | System can handle 200 concurrent founders, all tests pass, CI/CD automatically deploys to a staging environment, monitoring dashboards live. |

**Acceptance Criteria**
- Deploy to staging (`hermes‑engine-staging`) with zero‑downtime.
- Load test shows < 2 s average latency under 200 concurrent users.
- All CI stages succeed on every push to `main`.
- Monitoring alerts fire correctly when a confidence drop occurs.

---

## Wireframe & App Flow Overview (Sprint 1 deliverable)
1. **Landing / Home** – Hero with brief value proposition, “Get Started” CTA.
2. **Prompt Wizard** – Single‑page textarea where founder writes a natural‑language prompt; optional checkboxes for “Include quick‑start agents”.
3. **Agent Dashboard (empty state)** – List view showing agents as cards:
   - Icon, Role name, Status badge (Pending, Running, Done, Needs Approval).
   - Confidence gauge (green ≥ 0.85, yellow 0.6‑0.85, red < 0.6).
4. **Quick‑Start Palette** – Horizontal toolbar with icons for Repo‑Scaffolder, Pitch‑Deck, Legal Boilerplate, Growth‑Plan.
5. **Review / Approve Modal** – Shows artefact preview, confidence, diff (if dual‑LLM), and Approve / Reject buttons.
6. **Final Report Page** – Collated PDF/Markdown package download, plus a “Share” link.

**User Flow** (high‑level):
```
[Home] → [Prompt Wizard] → (Orchestrator decides roles) →
    → [Agent Dashboard] (CTO, Product, …) →
        → (Each agent updates its card) →
            → if confidence low → [Refine] button →
            → if legal/arch. → [Approval Modal] →
[Final Report] → Download / Share
```

---

## CI/CD Pipeline Blueprint (to be built across sprints)
```
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install deps
        run: |
          python -m pip install -r backend/requirements.txt
          npm ci --prefix frontend
      - name: Lint markdown
        run: markdownlint '**/*.md'
      - name: Flake8
        run: flake8 backend
      - name: ESLint
        run: npm run lint --prefix frontend

  test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      redis:
        image: redis:7
        ports: [6379:6379]
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
        uses: actions/setup-python@v5
        with: {python-version: '3.11'}
      - name: Install test deps
        run: pip install -r backend/requirements.txt -r backend/test-requirements.txt
      - name: Unit tests
        run: pytest backend/tests --junitxml=reports/unit.xml
      - name: Coverage
        run: coverage xml && bash <(curl -s https://codecov.io/bash)

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build backend image
        run: |
          docker build -t ghcr.io/${{github.repository}}/backend:${{github.sha}} backend
          docker push ghcr.io/${{github.repository}}/backend:${{github.sha}}
      - name: Build frontend image
        run: |
          docker build -t ghcr.io/${{github.repository}}/frontend:${{github.sha}} frontend
          docker push ghcr.io/${{github.repository}}/frontend:${{github.sha}}

  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - name: Trigger ArgoCD sync
        run: |
          curl -X POST ${{ secrets.ARGOCD_WEBHOOK }} -d '{"image":"ghcr.io/${{github.repository}}/backend:${{github.sha}}"}'
```

- **Lint** runs on every push.
- **Unit/Integration tests** run with a Redis service.
- **Coverage** uploaded to Codecov.
- **Docker images** built and pushed.
- **Deploy to staging** via an ArgoCD webhook (or any GitOps tool).

---

## Monitoring & Alerting (Sprint 6)
| Metric | Tool | Alert Threshold |
|--------|------|-----------------|
| Agent latency (ms) | Prometheus + Grafana | > 2000 ms for > 5 min |
| Queue length (pending agents) | Prometheus | > 30 for > 2 min |
| Confidence score (avg) | Prometheus | < 0.70 for > 10 min |
| CI pipeline failures | GitHub Actions | any failure → Slack/Discord webhook |
| Unauthorized API access | Falco / OPA | any `403` → PagerDuty |

---

## How to Run the Sprint Plan Locally
```bash
# Clone repo and checkout the dev branch
git clone https://github.com/yourorg/ai‑founding‑team‑engine.git
cd ai‑founding‑team‑engine
git checkout -b sprint‑plan

# Install backend deps (venv recommended)
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/dev-requirements.txt

# Frontend deps
npm ci --prefix frontend

# Run CI locally (lint + test)
npm run lint --prefix frontend
flake8 backend
pytest backend/tests

# Spin up services (Redis, Band mock) via Docker Compose
docker compose up -d

# Start the backend API (FastAPI example)
uvicorn backend.main:app --reload &

# Start the frontend (React dev server)
npm start --prefix frontend
```

All subsequent sprints will expand on this scaffold; each sprint adds new directories under `agents/`, new Helm charts under `k8s/`, and new test suites under `backend/tests/`.

---

## Conclusion
The sprint plan above gives you:
- A **wireframe‑first** approach ensuring UI/UX is nailed before heavy engineering.
- A **progressive layering** of expertise (quick‑start → dynamic → expert‑layered → governance).
- A **robust CI/CD pipeline** built incrementally, with automated linting, testing, image building, and GitOps deployment.
- **Monitoring, security, and scaling** baked in by Sprint 6.

Follow the sprint schedule, keep the Definition of Done strict, and you’ll have a production‑grade AI Founding Team Engine ready for the hackathon and beyond.
