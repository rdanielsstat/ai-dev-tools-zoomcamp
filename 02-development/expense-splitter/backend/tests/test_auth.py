from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth_headers, signup


class TestSignup:
    def test_creates_an_account_and_returns_a_token(self, client: TestClient) -> None:
        res = client.post(
            "/api/auth/signup",
            json={"name": "Mara Silva", "email": "mara@even.app", "password": "hunter22"},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["user"]["name"] == "Mara Silva"
        assert body["user"]["email"] == "mara@even.app"
        assert body["user"]["avatarInitials"] == "MS"
        assert body["token"]

    def test_rejects_a_duplicate_email(self, client: TestClient) -> None:
        signup(client, email="dupe@even.app")
        res = client.post(
            "/api/auth/signup",
            json={"name": "Someone Else", "email": "dupe@even.app", "password": "hunter22"},
        )
        assert res.status_code == 409

    def test_rejects_a_short_password(self, client: TestClient) -> None:
        res = client.post(
            "/api/auth/signup",
            json={"name": "Mara Silva", "email": "mara@even.app", "password": "short"},
        )
        assert res.status_code == 422


class TestLogin:
    def test_logs_in_with_correct_credentials(self, client: TestClient) -> None:
        signup(client, email="mara@even.app", password="hunter22")
        res = client.post("/api/auth/login", json={"email": "mara@even.app", "password": "hunter22"})
        assert res.status_code == 200
        assert res.json()["user"]["email"] == "mara@even.app"

    def test_rejects_wrong_password(self, client: TestClient) -> None:
        signup(client, email="mara@even.app", password="hunter22")
        res = client.post("/api/auth/login", json={"email": "mara@even.app", "password": "wrong"})
        assert res.status_code == 401

    def test_rejects_unknown_email(self, client: TestClient) -> None:
        res = client.post("/api/auth/login", json={"email": "nobody@even.app", "password": "hunter22"})
        assert res.status_code == 401


class TestLogout:
    def test_invalidates_the_token(self, client: TestClient) -> None:
        token, _ = signup(client)
        res = client.post("/api/auth/logout", headers=auth_headers(token))
        assert res.status_code == 204
        res2 = client.get("/api/me", headers=auth_headers(token))
        assert res2.status_code == 401

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.post("/api/auth/logout").status_code == 401


class TestMe:
    def test_returns_the_current_user(self, client: TestClient) -> None:
        token, user = signup(client)
        res = client.get("/api/me", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["id"] == user["id"]

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.get("/api/me").status_code == 401

    def test_rejects_a_garbage_token(self, client: TestClient) -> None:
        res = client.get("/api/me", headers=auth_headers("not-a-real-token"))
        assert res.status_code == 401

    def test_updates_name_and_email(self, client: TestClient) -> None:
        token, _ = signup(client)
        res = client.patch("/api/me", json={"name": "Mara S."}, headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["name"] == "Mara S."

    def test_rejects_email_already_used_by_another_account(self, client: TestClient) -> None:
        signup(client, email="taken@even.app")
        token, _ = signup(client, email="me@even.app")
        res = client.patch("/api/me", json={"email": "taken@even.app"}, headers=auth_headers(token))
        assert res.status_code == 409
