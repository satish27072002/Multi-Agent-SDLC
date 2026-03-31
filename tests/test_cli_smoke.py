import pytest

from src.cli import smoke


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"status={self.status_code}")

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, url, headers=None):
        return self._responses.pop(0)

    async def post(self, url, json=None, headers=None):
        return self._responses.pop(0)


def test_build_parser_defaults(monkeypatch):
    parser = smoke.build_parser()
    args = parser.parse_args([])
    assert args.timeout == 180
    assert args.workspace == "/tmp/sdlc-smoke"


def test_headers_with_token():
    headers = smoke._headers("abc")
    assert headers["Authorization"] == "Bearer abc"


@pytest.mark.asyncio
async def test_run_smoke_success(monkeypatch):
    responses = [
        _FakeResponse(payload={"status": "ok"}),
        _FakeResponse(payload={"task_id": "t1"}),
        _FakeResponse(payload={"status": "running", "current_stage": "coding"}),
        _FakeResponse(payload={"status": "completed", "current_stage": "done"}),
        _FakeResponse(payload={"files": [{"path": "main.py"}]}),
    ]

    monkeypatch.setattr(smoke.httpx, "AsyncClient", lambda **kwargs: _FakeClient(responses))
    code = await smoke.run_smoke("http://server", "", "task", "/tmp/w", 5)
    assert code == 0


@pytest.mark.asyncio
async def test_run_smoke_failure(monkeypatch):
    responses = [
        _FakeResponse(payload={"status": "ok"}),
        _FakeResponse(payload={"task_id": "t1"}),
        _FakeResponse(payload={"status": "failed", "errors": ["boom"], "current_stage": "review"}),
    ]

    monkeypatch.setattr(smoke.httpx, "AsyncClient", lambda **kwargs: _FakeClient(responses))
    code = await smoke.run_smoke("http://server", "", "task", "/tmp/w", 5)
    assert code == 1
