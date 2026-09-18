from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """A fresh app + a fresh in-memory SQLite DB per test — no state leaks
    between tests. Each create_app() call makes its own engine/connection
    (see make_engine's StaticPool), so distinct instances never share data
    even though they use the same ":memory:" URL string."""
    return TestClient(create_app(database_url="sqlite:///:memory:"))


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def signup(client: TestClient, name: str = "Mara Silva", email: str = "mara@even.app", password: str = "hunter22") -> tuple[str, dict]:
    """Sign up a fresh user and return (token, user_dict)."""
    res = client.post("/api/auth/signup", json={"name": name, "email": email, "password": password})
    assert res.status_code == 201, res.text
    body = res.json()
    return body["token"], body["user"]


def create_group(client: TestClient, token: str, name: str = "Trip", description: str = "") -> dict:
    res = client.post("/api/groups", json={"name": name, "description": description}, headers=auth_headers(token))
    assert res.status_code == 201, res.text
    return res.json()
