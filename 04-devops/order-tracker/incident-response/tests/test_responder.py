import json
import time
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import responder


TEST_ALERT = {
    "status": "firing",
    "labels": {"alertname": "ResponderTest", "test": "true"},
    "annotations": {"summary": "Test notification; no incident to fix"},
}
GRAFANA_ALERT = {
    "status": "firing",
    "labels": {
        "alertname": "Order Tracker 5xx responses",
        "endpoint": "GET /api/orders/{order_id}",
        "http_request_method": "GET",
        "http_route": "/api/orders/{order_id}",
    },
    "annotations": {"time_window": "5m", "summary": "5xx responses on GET /api/orders/{order_id}"},
    "startsAt": "2026-10-04T18:20:00.123456789Z",
    "dashboardURL": "http://localhost:3000/d/order-tracker",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(responder, "INCIDENTS_DIR", tmp_path / "incidents")
    with TestClient(responder.app) as test_client:
        yield test_client


def wait_for_agent(incident_dir, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = json.loads((incident_dir / "status.json").read_text())
        if status["agent"] not in ("pending", "running"):
            return status
        time.sleep(0.05)
    raise AssertionError("agent did not finish")


def test_describe_grafana_alert():
    now = datetime(2026, 10, 4, 18, 30, tzinfo=timezone.utc)
    info = responder.describe(GRAFANA_ALERT, now)
    assert info["endpoint"] == "GET /api/orders/{order_id}"
    assert info["http_route"] == "/api/orders/{order_id}"
    assert info["from"] == "2026-10-04T18:15:00.123456+00:00"
    assert info["to"] == now.isoformat()
    assert info["dashboard_url"] == "http://localhost:3000/d/order-tracker"
    assert not info["is_test"]


def test_test_alert_saves_context_and_runs_agent(client):
    response = client.post("/alerts", json={"alerts": [TEST_ALERT]})
    assert response.status_code == 202
    [incident] = response.json()["incidents"]
    assert incident["agent"] == "started"

    incident_dir = responder.INCIDENTS_DIR / incident["incident"]
    for name in ("alert.json", "metrics.json", "logs.json", "traces.json", "incident.md"):
        assert (incident_dir / name).exists()
    alert = json.loads((incident_dir / "alert.json").read_text())
    assert alert["parsed"]["is_test"] is True
    # Unreachable backends are recorded, not fatal.
    assert "error" in json.loads((incident_dir / "logs.json").read_text())

    status = wait_for_agent(incident_dir)
    assert status["agent"] == "done"
    assert status["last_line"] == "RESULT: TEST - fake agent ran."
    details = client.get(f"/incidents/{incident['incident']}").json()
    assert details["response"].endswith("RESULT: TEST - fake agent ran.\n")


def test_prompt_points_agent_at_incident(tmp_path):
    prompt = responder.agent_prompt(tmp_path)
    assert str(tmp_path) in prompt
    assert "{{" not in prompt


def test_duplicate_alert_does_not_start_second_agent(client, monkeypatch):
    monkeypatch.setenv("FAKE_AGENT_SLEEP", "1")
    first = client.post("/alerts", json={"alerts": [GRAFANA_ALERT]}).json()["incidents"][0]
    second = client.post("/alerts", json={"alerts": [GRAFANA_ALERT]}).json()["incidents"][0]
    assert first["agent"] == "started"
    assert second["agent"] == f"already running for incident {first['incident']}"
    wait_for_agent(responder.INCIDENTS_DIR / first["incident"])


def test_resolved_and_empty_payloads(client):
    resolved = client.post("/alerts", json={"alerts": [{**TEST_ALERT, "status": "resolved"}]})
    assert resolved.status_code == 202
    assert resolved.json() == {"incidents": [], "ignored_resolved": 1}
    assert client.post("/alerts", json={"alerts": []}).status_code == 400


def test_unknown_incident(client):
    assert client.get("/incidents/nope").status_code == 404
    assert client.get("/incidents/..").status_code == 404
