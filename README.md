# Multi-Agent SDLC System

A CLI-based multi-agent coding tool that automates the software development lifecycle. Unlike single-agent tools (Claude Code, Aider), this system uses **6 specialized AI agents** that collaborate via industry-standard protocols (A2A and MCP) to generate code, write tests, review quality, generate documentation, and manage Git operations.

## Architecture

```
User's terminal                        K8s cluster (DigitalOcean)
+-----------------+                    +----------------------------+
|  sdlc-agent CLI |   sends task       |  Orchestrator pod          |
|  (thin client)  | -----------------> |  Coding agent pod          |
|                 |                    |  Review agent pod          |
|  - Takes input  | <-- streams back   |  Testing agent pod         |
|  - Shows TUI    |    progress        |  GitOps agent pod          |
|  - Shows diffs  |                    |  Docs agent pod            |
|  - Writes files |                    |  Redis pod (state)         |
|    to disk      |                    |  Prometheus + Grafana      |
+-----------------+                    +----------------------------+
```

### Agent Pipeline

```
User Task
    |
    v
[Orchestrator] -- plans and coordinates
    |
    v
[Coding Agent] -- generates code (Qwen3 32B)
    |
    v
[Testing Agent] -- writes + runs tests (Llama 4 Scout 17B)
    |
    v
[Review Agent] -- code review (Llama 3.3 70B)
    |
    v
[Docs Agent] -- generates documentation (Llama 4 Scout 17B)
    |
    v
[GitOps Agent] -- git branch + commit (Llama 3.1 8B)
    |
    v
User Approval --> Files written to disk
```

### Communication Protocols

- **A2A (Agent-to-Agent):** Agents discover each other and delegate tasks. Each agent runs as an A2A server. The orchestrator coordinates via A2A client.
- **MCP (Model Context Protocol):** Agents connect to tools (GitHub, file system, terminal, linters). Each tool is an MCP server.

## Quick Start

### Another laptop (hosted mode, 3-minute setup)

```bash
# 1) Install CLI
python3 -m pip install --upgrade pip
pip install "git+https://github.com/satish27072002/multi-agent-sdlc.git"

# 2) Point to hosted backend
export SDLC_SERVER_URL=http://64.225.83.94
# Optional (only if server auth is enabled)
export SDLC_API_TOKEN='<token_if_required>'

# 3) Verify connectivity + run first task
sdlc-smoke --server-url "$SDLC_SERVER_URL"
sdlc-agent --task "Create a FastAPI health endpoint with tests"
```

If hosted mode is unavailable, use local fallback mode with `GROQ_API_KEY`.

### Install from GitHub (recommended)

```bash
pip install "git+https://github.com/satish27072002/multi-agent-sdlc.git"
```

### Install from source

```bash
git clone https://github.com/satish27072002/multi-agent-sdlc.git
cd multi-agent-sdlc
pip install -e ".[all,dev]"
```

### Server mode (default)

```bash
export SDLC_SERVER_URL=http://64.225.83.94
# Optional when server auth is enabled
export SDLC_API_TOKEN=your_server_token

sdlc-agent --task "Build a FastAPI endpoint with tests"
sdlc-smoke --server-url "$SDLC_SERVER_URL"

# If the server enforces auth and SDLC_API_TOKEN is missing/invalid,
# hosted requests return 401 and the CLI exits non-zero.
```

### Local fallback mode

```bash
export GROQ_API_KEY=your_key_here  # Free at https://console.groq.com/keys
sdlc-agent --local --task "Build a FastAPI endpoint with tests"
```

### Run

```bash
# Interactive mode (server mode by default)
sdlc-agent

# TUI mode (Textual terminal UI)
sdlc-agent --tui

# Force local mode
sdlc-agent --local

# Initialize a new project
sdlc-agent --init --workspace ./my-new-project

# Skip optional stages
sdlc-agent --skip-tests --skip-docs --skip-git
```

## Features

| Feature | Description |
|---------|-------------|
| 6 Specialized Agents | Coding, Testing, Review, Docs, GitOps, Orchestrator |
| A2A Protocol | Industry-standard agent-to-agent communication |
| MCP Protocol | Tool access via Model Context Protocol |
| Textual TUI | Rich terminal UI with live progress, file tree, diff view |
| Rich REPL | Lightweight interactive mode with syntax highlighting |
| FastAPI Server | HTTP API for hosted/remote mode with SSE streaming |
| Docker Support | Multi-stage Dockerfile, docker-compose for all agents |
| K8s Ready | Kubernetes manifests for production deployment |
| Retry Logic | Exponential backoff on LLM failures with fallback responses |
| Free LLMs | Runs on Groq free tier (no API costs) |

## Agents

| Agent | Model (Groq Free Tier) | Purpose |
|-------|----------------------|---------|
| Orchestrator | Llama 3.1 8B | Plans tasks, coordinates pipeline |
| Coding | Qwen3 32B | Generates and modifies code |
| Testing | Llama 4 Scout 17B | Writes and runs pytest tests |
| Review | Llama 3.3 70B | Reviews code quality and style |
| Docs | Llama 4 Scout 17B | Generates documentation |
| GitOps | Llama 3.1 8B | Git branch names and commit messages |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Agent Framework | Pydantic AI (with FastA2A for A2A) |
| LLM Inference | Groq free tier (4 models) |
| CLI / TUI | Rich + Textual |
| Server API | FastAPI + SSE |
| Task State | Redis (server mode) / In-memory (local) |
| Containerization | Docker (multi-stage) |
| Orchestration | Kubernetes + ArgoCD |
| Infrastructure | DigitalOcean DOKS via Terraform |
| Monitoring | Prometheus + Grafana |

## Project Structure

```
multi-agent-sdlc/
+-- src/
|   +-- cli/
|   |   +-- main.py              CLI entry point + Rich REPL
|   |   +-- tui.py               Textual TUI application
|   +-- agents/
|   |   +-- orchestrator.py      Pipeline coordinator
|   |   +-- coding.py            Code generation agent
|   |   +-- testing.py           Test generation + runner
|   |   +-- review.py            Code review agent
|   |   +-- docs.py              Documentation agent
|   |   +-- gitops.py            Git operations agent
|   +-- protocols/
|   |   +-- a2a_server.py        A2A protocol server wrapper
|   |   +-- mcp_client.py        MCP protocol client + tools
|   +-- server/
|   |   +-- api.py               FastAPI server (hosted mode)
|   +-- core/
|       +-- config.py            Settings and configuration
|       +-- workspace.py         File operations
|       +-- state.py             Task state management
|       +-- retry.py             Retry logic with backoff
+-- tests/                       Pytest test suite
+-- docs/                        Runbooks and release checklists
+-- k8s/                         Kubernetes manifests
+-- Dockerfile                   Multi-stage Docker build
+-- docker-compose.yaml          Local multi-agent setup
+-- pyproject.toml               Package configuration
```

## Running with Docker

### Local multi-agent mode

```bash
# Set your API key
echo "GROQ_API_KEY=your_key_here" > .env

# Start all agents + API server
docker compose up -d

# Check health
curl http://localhost:8080/health

# Submit a task via API
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"task": "Create a Python calculator module"}'
```

### Server mode (hosted)

```bash
# Build and run just the API server
docker build --target server -t sdlc-server .
docker run -p 8080:8080 -e GROQ_API_KEY=your_key sdlc-server
```

### Hosted smoke test

```bash
export SDLC_SERVER_URL=http://localhost:8080
sdlc-smoke --server-url "$SDLC_SERVER_URL"
```

## Kubernetes Deployment

Manifests are in the `k8s/` directory. To deploy:

```bash
# Create namespace
kubectl apply -f k8s/namespace.yaml

# Create secrets (edit secrets.yaml first with base64-encoded keys)
kubectl apply -f k8s/secrets.yaml

# Deploy Redis
kubectl apply -f k8s/redis-deployment.yaml

# Deploy agents
kubectl apply -f k8s/agents-deployment.yaml

# Deploy API server
kubectl apply -f k8s/api-deployment.yaml

# Set up ingress
kubectl apply -f k8s/ingress.yaml
```

For GitOps deployment, the [devops-k8s-platform repository](https://github.com/satish27072002/devops-k8s-platform) has ArgoCD configured to auto-deploy from this repo's container images.

## CI/CD

This repo ships with a production-oriented GitHub Actions pipeline:

- `.github/workflows/ci.yml`
  - Lint and type checks (Ruff + mypy)
  - Test suite on Python 3.11 + 3.12
  - Package build smoke (`python -m build`)
  - Docker target build smoke (`agent` + `server`)
- `.github/workflows/cd-gitops.yml`
  - Triggered automatically after CI succeeds on `main` pushes
  - Builds and pushes `linux/amd64` images to Docker Hub with commit-SHA tags
  - Updates `devops-k8s-platform/kubernetes/apps/multi-agent/*.yaml`
  - ArgoCD auto-sync applies the manifest change to production
- `.github/workflows/e2e-hosted-smoke.yml`
  - Manual or scheduled hosted smoke test against deployed backend

Required repository secrets (`Settings -> Secrets and variables -> Actions`):

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`
- `DEVOPS_REPO_PUSH_TOKEN`
- `HOSTED_SDLC_SERVER_URL` (for hosted smoke workflow)
- `HOSTED_SDLC_API_TOKEN` (optional if server auth is disabled)

## API Endpoints

When running in server mode (`docker compose up` or K8s):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + uptime |
| GET | `/agents` | List available agents and models |
| POST | `/tasks` | Submit a task (async) |
| POST | `/tasks/stream` | Submit a task with SSE streaming |
| GET | `/tasks/{id}` | Get task status |
| GET | `/tasks/{id}/artifacts` | List generated files for a task workspace |
| DELETE | `/tasks/{id}/workspace` | Delete task workspace directory |
| GET | `/tasks` | List recent tasks |
| GET | `/workspaces` | List workspace usage/stats by task |

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest -v

# Run with coverage
pytest --cov=src --cov-report=term-missing

# Run specific test file
pytest tests/test_retry.py -v
```

## Configuration

All settings are loaded from environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GROQ_API_KEY` | Yes (local mode) | — | Groq API key |
| `SDLC_SERVER_URL` | No | `http://localhost:8080` | Server URL for hosted mode |
| `SDLC_API_TOKEN` | No | — | Bearer token required by protected server endpoints |
| `SDLC_WORKSPACE_TTL_SECONDS` | No | `86400` | Server workspace retention in seconds |
| `GITHUB_TOKEN` | No | — | GitHub token for MCP integration |

## Groq Free Tier Rate Limits

| Model | Requests/day | Tokens/day | Used By |
|-------|-------------|-----------|---------|
| Llama 3.1 8B | 14,400 | 500,000 | Orchestrator, GitOps |
| Llama 3.3 70B | 1,000 | 100,000 | Review |
| Llama 4 Scout 17B | 1,000 | 500,000 | Testing, Docs |
| Qwen3 32B | 1,000 | 500,000 | Coding |

30 requests per minute max. No credit card required.

## How It Differs From Existing Tools

| Feature | Claude Code / Aider | This Tool |
|---------|-------------------|-----------|
| Architecture | Single agent | 6 specialized agents |
| Code review | Manual | Automated review agent |
| Testing | Manual | Auto-generates and runs tests |
| Documentation | Manual | Auto-generated |
| Git operations | Manual | GitOps agent creates branches |
| Agent communication | N/A | A2A protocol |
| Tool access | Built-in | MCP protocol |
| Cost | API costs ($$$) | Free (Groq free tier) |
| Backend | Local/proprietary | K8s microservices |

## License

MIT
