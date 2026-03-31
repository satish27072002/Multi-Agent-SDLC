# Release Checklist

## Server-first validation

- Confirm hosted server health: `curl "$SDLC_SERVER_URL/health"`
- Confirm auth behavior: protected endpoints reject missing token when server auth is enabled
- Export token before smoke run when auth is enabled: `export SDLC_API_TOKEN=...`
- Run hosted smoke flow: `sdlc-smoke --server-url "$SDLC_SERVER_URL"`
- Verify task completion and artifacts endpoint: `GET /tasks/{id}` and `GET /tasks/{id}/artifacts`

## Local fallback validation

- Ensure `GROQ_API_KEY` is set
- Run: `sdlc-agent --local --task "Create a hello world module with tests"`

## Quality gates

- `ruff check src/ tests/`
- `mypy src`
- `pytest tests/ -q`

## Deployment sanity

- `kubectl get applications.argoproj.io -n argocd`
- `kubectl get pods -n multi-agent`
- Public health endpoint returns `status=ok`
