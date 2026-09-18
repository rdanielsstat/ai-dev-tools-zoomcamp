"""Integration test for SPEC.md acceptance scenario 1.

Unlike test_agent_relay.py (which drives the app in-process through
FastAPI's TestClient), this test talks to a real running server over a real
TCP socket with `httpx`.

By default it launches its own `uvicorn` process against a scratch SQLite
file. Set LIVE_API_BASE_URL to point it at an already-running instance
instead (e.g. a `docker compose up` stack backed by PostgreSQL) -- the test
body is identical either way, since it only speaks the HTTP protocol.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).parent
SCENARIO_DB = "/tmp/agent-relay-live-integration-test.db"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def live_base_url():
    external_url = os.getenv("LIVE_API_BASE_URL")
    if external_url:
        external_url = external_url.rstrip("/")
        response = httpx.get(f"{external_url}/health", timeout=5)
        if response.status_code != 200:
            raise RuntimeError(f"{external_url}/health returned {response.status_code}, expected 200")
        yield external_url
        return

    for suffix in ("", "-wal", "-shm"):
        Path(SCENARIO_DB + suffix).unlink(missing_ok=True)

    port = _free_port()
    env = {
        **os.environ,
        "RELAY_DATABASE_URL": f"sqlite:///{SCENARIO_DB}",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 15
        ready = False
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise RuntimeError(f"server process exited early:\n{output}")
            try:
                response = httpx.get(f"{base_url}/health", timeout=1)
                if response.status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        if not ready:
            raise RuntimeError("server did not become healthy in time")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        for suffix in ("", "-wal", "-shm"):
            Path(SCENARIO_DB + suffix).unlink(missing_ok=True)


def test_acceptance_scenario_1_register_send_claim_complete_read(live_base_url):
    """SPEC.md acceptance scenario 1: register two agents, one sends a task,
    the other claims and completes it, and the sender reads the result."""

    with httpx.Client(base_url=live_base_url, timeout=10) as client:
        sender = client.post("/api/v1/agents", json={"name": "alice-reviewer"})
        assert sender.status_code == 201
        sender_data = sender.json()
        sender_headers = {"Authorization": f"Bearer {sender_data['token']}"}

        recipient = client.post("/api/v1/agents", json={"name": "uppercase-worker"})
        assert recipient.status_code == 201
        recipient_data = recipient.json()
        recipient_headers = {"Authorization": f"Bearer {recipient_data['token']}"}

        sent = client.post(
            "/api/v1/tasks",
            headers=sender_headers,
            json={"to": recipient_data["agent_id"], "input": "hello relay"},
        )
        assert sent.status_code == 201
        task_id = sent.json()["task_id"]
        assert sent.json()["status"] == "queued"

        claim = client.post(
            "/api/v1/tasks/claim",
            headers=recipient_headers,
            json={"worker_id": "bob-laptop-1", "wait_seconds": 0},
        )
        assert claim.status_code == 200
        claim_data = claim.json()
        assert claim_data["input"] == "hello relay"

        complete = client.post(
            f"/api/v1/tasks/{task_id}/complete",
            headers=recipient_headers,
            json={"claim_token": claim_data["claim_token"], "output": "HELLO RELAY"},
        )
        assert complete.status_code == 200
        assert complete.json()["status"] == "completed"

        result = client.get(f"/api/v1/tasks/{task_id}", headers=sender_headers)
        assert result.status_code == 200
        result_data = result.json()
        assert result_data["status"] == "completed"
        assert result_data["output"] == "HELLO RELAY"
        assert result_data["error"] is None
