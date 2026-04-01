from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdlc-smoke",
        description="Hosted smoke test for SDLC server mode",
    )
    parser.add_argument(
        "--server-url",
        default=os.environ.get("SDLC_SERVER_URL", "http://localhost:8080"),
    )
    parser.add_argument("--api-token", default=os.environ.get("SDLC_API_TOKEN", ""))
    parser.add_argument(
        "--task",
        default="Create a Python module with one pure function and pytest tests",
    )
    parser.add_argument("--workspace", default="/tmp/sdlc-smoke")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-docs", action="store_true")
    parser.add_argument("--skip-git", action="store_true")
    return parser


def _headers(api_token: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    return headers


async def run_smoke(
    server_url: str,
    api_token: str,
    task: str,
    workspace: str,
    timeout_seconds: int,
    skip_tests: bool = False,
    skip_docs: bool = False,
    skip_git: bool = False,
) -> int:
    base_url = server_url.rstrip("/")
    headers = _headers(api_token)
    request_timeout = httpx.Timeout(30.0, connect=10.0)

    async with httpx.AsyncClient(timeout=request_timeout) as client:
        health = await client.get(f"{base_url}/health", headers=headers)
        health.raise_for_status()
        console.print(Panel(health.text, title="Health", border_style="green"))

        create_payload = {
            "task": task,
            "workspace": workspace,
            "skip_tests": skip_tests,
            "skip_docs": skip_docs,
            "skip_git": skip_git,
            "auto_approve": True,
        }
        created = await client.post(
            f"{base_url}/tasks",
            json=create_payload,
            headers=headers,
        )
        created.raise_for_status()
        task_id = created.json()["task_id"]
        console.print(f"[cyan]Submitted task:[/] {task_id}")

        deadline = time.monotonic() + timeout_seconds
        last_stage = ""
        while time.monotonic() < deadline:
            status_resp = await client.get(f"{base_url}/tasks/{task_id}", headers=headers)
            status_resp.raise_for_status()
            status = status_resp.json()

            stage = status.get("current_stage") or "unknown"
            if stage != last_stage:
                console.print(f"[blue]Stage:[/] {stage}")
                last_stage = stage

            state = status.get("status", "").lower()
            if state == "completed":
                artifacts = await client.get(
                    f"{base_url}/tasks/{task_id}/artifacts",
                    headers=headers,
                )
                if artifacts.status_code == 200:
                    payload = artifacts.json()
                    console.print(f"[green]Artifacts:[/] {len(payload.get('files', []))} file(s)")
                console.print("[bold green]Smoke test passed[/bold green]")
                return 0

            if state == "failed":
                errors = status.get("errors") or []
                message = "\n".join(errors) if errors else "task failed"
                console.print(Panel(message, title="Failure", border_style="red"))
                return 1

            await asyncio.sleep(1.0)

    console.print("[red]Smoke test timed out[/red]")
    return 1


def main() -> None:
    args = build_parser().parse_args()
    try:
        code = asyncio.run(
            run_smoke(
                server_url=args.server_url,
                api_token=args.api_token,
                task=args.task,
                workspace=args.workspace,
                timeout_seconds=args.timeout,
                skip_tests=args.skip_tests,
                skip_docs=args.skip_docs,
                skip_git=args.skip_git,
            )
        )
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        if status_code in {401, 403}:
            console.print("[red]Hosted auth failed.[/] Set SDLC_API_TOKEN to a valid bearer token.")
        else:
            console.print(f"[red]Smoke test request failed ({status_code}).[/] {exc}")
        sys.exit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]Smoke test network failure:[/] {exc}")
        sys.exit(1)

    sys.exit(code)


if __name__ == "__main__":
    main()
