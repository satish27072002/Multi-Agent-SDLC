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

### Install from PyPI

```bash
pip install multi-agent-sdlc
```

### Install from source

```bash
git clone https://github.com/satish27072002/multi-agent-sdlc.git
cd multi-agent-sdlc
pip install -e ".[all,dev]"
```

### Set up your API key

```bash
export GROQ_API_KEY=your_key_here  # Free at https://console.groq.com/keys
```

### Run

```bash
# Interactive mode (Rich REPL)
sdlc-agent

# TUI mode (Textual terminal UI)
sdlc-agent --tui

# Single task (non-interactive)
sdlc-agent --task "Add user authentication with JWT tokens"

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

For GitOps deployment, the `devops-k8s-platform` repo has ArgoCD configured to auto-deploy from this repo's container images.

## API Endpoints

When running in server mode (`docker compose up` or K8s):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + uptime |
| GET | `/agents` | List available agents and models |
| POST | `/tasks` | Submit a task (async) |
| POST | `/tasks/stream` | Submit a task with SSE streaming |
| GET | `/tasks/{id}` | Get task status |
| GET | `/tasks` | List recent tasks |

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
