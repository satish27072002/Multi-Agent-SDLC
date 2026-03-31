# Multi-Agent SDLC System — Project Context

**Created:** March 29, 2026  
**Updated:** March 29, 2026  
**Student:** Satish Somarouthu  
**Purpose:** Architecture plan for multi-agent SDLC automation CLI tool

---

## Project overview

A CLI-based multi-agent coding tool that automates the software development lifecycle. Unlike single-agent tools (Claude Code, OpenCode, Aider), this system uses 6 specialized AI agents that collaborate via industry-standard protocols (A2A and MCP) to generate code, write tests, review quality, generate documentation, and manage Git operations.

**Primary mode:** Client-server architecture. CLI runs on user's machine, agents run on a Kubernetes cluster (DigitalOcean). This makes the devops-k8s-platform repo the production backend.

**Local mode:** Everything runs on the user's machine. Documented in README as self-hosted alternative. User provides their own Groq API key.

---

## How it works

```
User's terminal                        K8s cluster (DigitalOcean)
┌─────────────────┐                    ┌────────────────────────────┐
│  sdlc-agent CLI │   sends task       │  Orchestrator pod          │
│  (thin client)  │ ────────────────→  │  Coding agent pod          │
│                 │                    │  Review agent pod           │
│  - Takes input  │ ← streams back    │  Testing agent pod          │
│  - Shows TUI    │   progress         │  GitOps agent pod           │
│  - Shows diffs  │                    │  Docs agent pod             │
│  - Writes files │                    │  Redis pod (state)          │
│    to disk      │                    │  Prometheus + Grafana       │
└─────────────────┘                    └────────────────────────────┘
```

### User experience

```bash
# Install
pip install multi-agent-sdlc

# Navigate to project (existing or empty folder)
cd my-project

# Run (uses hosted backend by default)
sdlc-agent

# Or run with local agents (self-hosted mode)
sdlc-agent --local    # requires GROQ_API_KEY env variable
```

### Example session

```
┌──────────────────────────────────────────────────────┐
│  SDLC Agent System              agents: 6 active     │
├──────────────────────────────────────────────────────┤
│                                                       │
│  > Add user authentication with JWT tokens            │
│                                                       │
│  [Orchestrator] Planning task...                      │
│  [Orchestrator] Breaking into 3 subtasks              │
│  [Coding]       Generating auth middleware... done     │
│  [Coding]       Creating user model... done            │
│  [Testing]      Writing unit tests... done             │
│  [Testing]      Running tests... 4/4 passed            │
│  [Review]       Checking code quality... approved      │
│                                                       │
│  Files modified:                                      │
│    + src/auth/middleware.py                            │
│    + src/models/user.py                               │
│    + tests/test_auth.py                               │
│    ~ src/app.py (modified)                            │
│                                                       │
│  [A]pprove  [R]eject  [D]iff  [E]dit                 │
│                                                       │
├──────────────────────────────────────────────────────┤
│  Type your task or press ? for help                   │
└──────────────────────────────────────────────────────┘
```

User presses A to approve. Files are written to disk. User opens folder in VS Code to review and test.

---

## What makes this different from existing tools

| Feature | OpenCode / Claude Code | This tool |
|---|---|---|
| Architecture | Single agent | 6 specialized agents collaborating |
| Code review | Manual (user reviews) | Automated review agent checks first |
| Testing | Manual | Testing agent auto-generates and runs tests |
| Documentation | Manual | Docs agent generates docs automatically |
| Deployment | Manual | GitOps agent can create PRs |
| Agent communication | N/A | A2A protocol (industry standard) |
| Tool access | Built-in tools | MCP protocol (industry standard) |
| Cost to user | API costs ($$$) | Free (hosted on Groq free tier) |
| Backend | Local or proprietary | Kubernetes microservices (open infrastructure) |

---

## Architecture

### Communication protocols

- **A2A (Agent-to-Agent):** Agents discover each other and delegate tasks. Each agent runs as an A2A server. Orchestrator coordinates via A2A client.
- **MCP (Model Context Protocol):** Agents connect to tools (GitHub, file system, terminal, linters). Each tool is an MCP server.

### Agent details

| Agent | LLM (Groq free tier) | Purpose | MCP tools |
|-------|---------------------|---------|-----------|
| Orchestrator | Llama 3.1 8B | Plans tasks, delegates, coordinates | None |
| Coding | Qwen3 32B | Generates and modifies code | File system, GitHub |
| Testing | Llama 4 Scout 17B | Writes and runs tests | Terminal, test runner |
| Review | Llama 3.3 70B | Reviews code quality and style | Linters, GitHub |
| GitOps | Llama 3.1 8B | Commits code, creates PRs | GitHub, ArgoCD |
| Docs | Llama 4 Scout 17B | Generates documentation | File system |

### Tech stack

| Component | Technology | Status |
|-----------|-----------|--------|
| Agent framework | Pydantic AI (agents + A2A via FastA2A) | CONFIRMED BY TESTING |
| Orchestration logic | Plain Python (async functions with loops) | CONFIRMED — ADK routing broken with Groq |
| Agent-to-agent | A2A protocol (FastA2A / python-a2a) | Decided |
| Agent-to-tool | MCP protocol | Decided |
| LLM inference | Groq free tier (all 4 models tested working) | CONFIRMED BY TESTING |
| CLI / TUI | Textual or Rich (Python TUI libraries) | To decide |
| Backend API | FastAPI (connects CLI to agents) | Decided |
| Task state | Redis | Decided |
| Monitoring | Prometheus + Grafana | Already built |
| Containerization | Docker (each agent = one container) | Decided |
| Deployment | Kubernetes + ArgoCD | Already built |
| Infrastructure | DigitalOcean DOKS via Terraform | Ready to deploy |

---

## Groq free tier rate limits

| Model | Requests/day | Tokens/day | Used by |
|-------|-------------|-----------|---------|
| Llama 3.1 8B | 14,400 | 500,000 | Orchestrator, GitOps |
| Llama 3.3 70B | 1,000 | 100,000 | Review agent |
| Llama 4 Scout 17B | 1,000 | 500,000 | Testing, Docs agents |
| Qwen3 32B | 1,000 | 500,000 | Coding agent |

30 requests per minute max. No credit card required.

---

## Repository structure

### multi-agent-sdlc (application repo)

```
multi-agent-sdlc/
├── src/
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── main.py              (CLI entry point)
│   │   └── tui.py               (terminal UI)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── coding.py
│   │   ├── review.py
│   │   ├── testing.py
│   │   ├── gitops.py
│   │   └── docs.py
│   ├── protocols/
│   │   ├── a2a_server.py        (A2A setup for each agent)
│   │   └── mcp_client.py        (MCP connections to tools)
│   ├── server/
│   │   ├── api.py               (FastAPI — connects CLI to agents)
│   │   └── routes/
│   └── core/
│       ├── workspace.py         (file operations on user's project)
│       ├── config.py            (user settings, API keys)
│       └── state.py             (task state management)
├── pyproject.toml               (pip-installable, CLI entry point)
├── Dockerfile                   (for K8s deployment)
├── docker-compose.yaml          (local multi-agent mode)
├── tests/
└── README.md
```

### devops-k8s-platform (infrastructure repo — already built)

```
devops-k8s-platform/
├── kubernetes/
│   ├── apps/
│   │   ├── hello-app/           (test app — completed)
│   │   └── multi-agent/         (K8s manifests for agent system)
│   │       ├── orchestrator-deployment.yaml
│   │       ├── coding-agent-deployment.yaml
│   │       ├── review-agent-deployment.yaml
│   │       ├── testing-agent-deployment.yaml
│   │       ├── gitops-agent-deployment.yaml
│   │       ├── docs-agent-deployment.yaml
│   │       ├── api-deployment.yaml
│   │       └── redis-deployment.yaml
│   ├── argocd/                  (GitOps — completed)
│   └── monitoring/              (Prometheus + Grafana — completed)
├── helm-charts/                 (completed)
├── terraform/                   (DigitalOcean config — ready)
└── README.md                   (completed)
```

### How the repos connect

```
multi-agent-sdlc                    devops-k8s-platform
├── Agent source code          →    ├── K8s manifests deploy agents
├── Dockerfiles build images   →    ├── ArgoCD auto-deploys from Git
├── Push new code to GitHub    →    ├── ArgoCD detects and updates
└── README links to infra repo      └── README links to app repo
```

---

## Distribution

### Primary: pip install (PyPI)

```bash
pip install multi-agent-sdlc
sdlc-agent                          # uses hosted K8s backend
```

### Alternative: install from GitHub

```bash
pip install git+https://github.com/satish27072002/multi-agent-sdlc.git
```

### Local/self-hosted mode (documented in README)

```bash
# Clone the repo
git clone https://github.com/satish27072002/multi-agent-sdlc.git
cd multi-agent-sdlc

# Set up Groq API key
export GROQ_API_KEY=your_key_here

# Option A: Run with docker-compose (recommended for local)
docker-compose up

# Option B: Run agents as Python processes
pip install -e .
sdlc-agent --local
```

---

## Development plan

### Phase 1: Foundation (Week 1-2)
- [ ] Set up multi-agent-sdlc repo with pyproject.toml
- [ ] Decide on agent framework (complete research)
- [ ] Build coding agent: takes prompt, generates code via Groq
- [ ] Build basic CLI that sends task and displays result
- [ ] Test: give it a task, see generated code written to disk

### Phase 2: Multi-agent system (Week 2-3)
- [ ] Add all 6 agents
- [ ] Implement A2A communication between agents
- [ ] Connect MCP tools (file system, terminal)
- [ ] Build orchestration workflow (state graph with human approval)
- [ ] Test: full workflow — code, test, review, approve, write files

### Phase 3: TUI and polish (Week 3-4)
- [ ] Build terminal UI (live progress, diff view, file list)
- [ ] Add GitHub MCP integration (clone repos, create PRs)
- [ ] Support both "existing repo" and "from scratch" modes
- [ ] Error handling, retry logic, edge cases

### Phase 4: Dockerize and deploy (Week 4-5)
- [ ] Dockerize each agent
- [ ] Write K8s manifests in devops-k8s-platform repo
- [ ] Run terraform apply to create DigitalOcean cluster
- [ ] Deploy agents via ArgoCD
- [ ] Set up monitoring dashboards for agent performance
- [ ] Build FastAPI server that CLI connects to (hosted mode)

### Phase 5: Publish and document (Week 5-6)
- [ ] Publish to PyPI
- [ ] Write comprehensive README with demos
- [ ] Record demo video / GIFs
- [ ] Document local setup in README
- [ ] Polish both repo READMEs

---

## Portfolio story

"I built a multi-agent CLI coding tool that automates the software development lifecycle. Unlike single-agent tools, my system uses 6 specialized agents that collaborate using industry-standard A2A and MCP protocols — a coding agent generates code, a testing agent writes and runs tests, a review agent checks quality, and a docs agent generates documentation. The agents run as independent microservices on a Kubernetes cluster I built with GitOps automation, Terraform infrastructure-as-code, and real-time monitoring with Prometheus and Grafana. Users install the CLI with pip and use it for free — the backend runs on open-source LLMs via Groq."

### Skills demonstrated
- Multi-agent AI systems (A2A, MCP protocols)
- LLM integration (Groq, multiple models)
- CLI tool development (Python, TUI)
- Kubernetes deployment and orchestration
- GitOps automation (ArgoCD)
- Infrastructure as Code (Terraform)
- Monitoring and observability (Prometheus, Grafana)
- Docker containerization
- API design (FastAPI)
- Package publishing (PyPI)
- Production-grade microservices architecture

---

## Research completed

- [x] Agent framework: Pydantic AI chosen — CONFIRMED BY TESTING
  - Pydantic AI docs: https://ai.pydantic.dev/
  - FastA2A docs: https://ai.pydantic.dev/a2a/
- [x] Groq API: key obtained, all 4 models tested and working
- [ ] A2A protocol: complete Python quickstart
  - Tutorial: https://a2a-protocol.org/latest/tutorials/python/1-introduction/
- [ ] Python TUI libraries: Textual vs Rich vs custom
- [ ] MCP: identify GitHub MCP server to use

## Framework decision rationale

### ADK was tested and rejected (March 30, 2026)

Tested Google ADK v1.28.0 with Groq. Full results in ADK_GROQ_TEST_RESULTS.md.

What worked:
- Single agents with all 4 Groq models (8B, 17B, 32B, 70B)
- SequentialAgent (fixed pipeline, no decisions)
- Dev UI for debugging

What failed (dealbreaker):
- Dynamic multi-agent routing — ADK uses an internal `transfer_to_agent` tool that Groq models cannot call correctly. The 8B model hallucinated non-existent functions. The 70B model generated schema-invalid tool calls. This is a fundamental incompatibility between ADK's orchestration mechanism and Groq's tool-calling implementation.
- LoopAgent — feedback loops (write → review → fix) fail because they depend on the same broken transfer mechanism.
- Without dynamic routing and loops, ADK reduces to a fixed pipeline — no different from running scripts in order.

### Why Pydantic AI wins

1. First-class Groq support — works out of the box, no LiteLLM wrapper
2. Orchestration is plain Python — no hidden `transfer_to_agent` tool calls. You control routing with if/else and loops. Groq's tool-calling limitations don't matter.
3. Built-in FastA2A — each agent becomes an A2A server with one line of code
4. Type-safe outputs with auto-retry — catches LLM errors at the framework level
5. pydantic-graph available if orchestration needs grow beyond simple Python
6. Tested and confirmed working with Groq on March 30, 2026

---

## Cost estimate

| Resource | Cost | Duration | Source |
|----------|------|----------|--------|
| DigitalOcean K8s | $24-36/month | 5-8 months | $200 credits (free) |
| Groq API | $0 | Unlimited | Free tier |
| PyPI publishing | $0 | Permanent | Free |
| Domain (optional) | $10/year | Optional | Personal |
| **Total** | **$0** | | **Covered by credits** |

---

**END OF PROJECT CONTEXT**

Give this file to a new Claude chat alongside PORTFOLIO_STRATEGY.md and DEVOPS_K8S_PROJECT_CONTEXT.md when starting work on this project.
