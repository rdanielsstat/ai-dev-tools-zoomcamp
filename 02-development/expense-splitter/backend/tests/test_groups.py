from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth_headers, create_group, signup


class TestListAndCreate:
    def test_creates_a_group_with_caller_as_sole_admin(self, client: TestClient) -> None:
        token, user = signup(client)
        group = create_group(client, token, name="Ski trip", description="Feb weekend")
        assert len(group["members"]) == 1
        assert group["members"][0] == {
            "userId": user["id"],
            "name": user["name"],
            "avatarInitials": user["avatarInitials"],
            "role": "admin",
            "joinedAt": group["members"][0]["joinedAt"],
        }

    def test_only_lists_groups_the_caller_belongs_to(self, client: TestClient) -> None:
        token_a, _ = signup(client, email="a@even.app")
        token_b, _ = signup(client, email="b@even.app")
        create_group(client, token_a, name="Solo")

        res = client.get("/api/groups", headers=auth_headers(token_b))
        assert res.status_code == 200
        assert res.json() == []

        res_a = client.get("/api/groups", headers=auth_headers(token_a))
        assert len(res_a.json()) == 1

    def test_requires_authentication(self, client: TestClient) -> None:
        assert client.get("/api/groups").status_code == 401
        assert client.post("/api/groups", json={"name": "X", "description": ""}).status_code == 401


class TestGetGroup:
    def test_returns_the_group_for_a_member(self, client: TestClient) -> None:
        token, _ = signup(client)
        group = create_group(client, token)
        res = client.get(f"/api/groups/{group['id']}", headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["id"] == group["id"]

    def test_404s_for_a_non_member_without_revealing_the_group_exists(self, client: TestClient) -> None:
        token_a, _ = signup(client, email="a@even.app")
        token_b, _ = signup(client, email="b@even.app")
        group = create_group(client, token_a)
        res = client.get(f"/api/groups/{group['id']}", headers=auth_headers(token_b))
        assert res.status_code == 404

    def test_404s_for_an_unknown_id(self, client: TestClient) -> None:
        token, _ = signup(client)
        res = client.get("/api/groups/nope", headers=auth_headers(token))
        assert res.status_code == 404


class TestRenameGroup:
    def test_admin_can_rename(self, client: TestClient) -> None:
        token, _ = signup(client)
        group = create_group(client, token, name="Old name")
        res = client.patch(f"/api/groups/{group['id']}", json={"name": "New name"}, headers=auth_headers(token))
        assert res.status_code == 200
        assert res.json()["name"] == "New name"

    def test_non_admin_member_cannot_rename(self, client: TestClient) -> None:
        token_admin, _ = signup(client, email="admin@even.app")
        token_member, _ = signup(client, email="member@even.app")
        group = create_group(client, token_admin)
        client.post(f"/api/groups/{group['id']}/members", json={"email": "member@even.app"}, headers=auth_headers(token_admin))

        res = client.patch(f"/api/groups/{group['id']}", json={"name": "Hijacked"}, headers=auth_headers(token_member))
        assert res.status_code == 403


class TestAddMember:
    def test_adds_an_existing_user_by_email(self, client: TestClient) -> None:
        token_admin, _ = signup(client, email="admin@even.app")
        _, user_b = signup(client, email="b@even.app")
        group = create_group(client, token_admin)

        res = client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_admin))
        assert res.status_code == 200
        member_ids = [m["userId"] for m in res.json()["members"]]
        assert user_b["id"] in member_ids

    def test_adding_the_same_member_twice_does_not_duplicate(self, client: TestClient) -> None:
        token_admin, _ = signup(client, email="admin@even.app")
        signup(client, email="b@even.app")
        group = create_group(client, token_admin)

        client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_admin))
        res = client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_admin))
        member_ids = [m["userId"] for m in res.json()["members"]]
        assert len(member_ids) == len(set(member_ids))

    def test_creates_a_new_user_when_email_is_unknown(self, client: TestClient) -> None:
        token, _ = signup(client)
        group = create_group(client, token)
        res = client.post(f"/api/groups/{group['id']}/members", json={"email": "wren@even.app"}, headers=auth_headers(token))
        assert res.status_code == 200
        assert any(m["name"] == "Wren" for m in res.json()["members"])

    def test_non_member_cannot_add_to_a_group_they_are_not_in(self, client: TestClient) -> None:
        token_a, _ = signup(client, email="a@even.app")
        token_outsider, _ = signup(client, email="outsider@even.app")
        group = create_group(client, token_a)
        res = client.post(
            f"/api/groups/{group['id']}/members", json={"email": "c@even.app"}, headers=auth_headers(token_outsider)
        )
        assert res.status_code == 404


class TestLeaveGroup:
    def test_refuses_when_balance_is_not_zero(self, client: TestClient) -> None:
        token_a, user_a = signup(client, email="a@even.app")
        token_b, user_b = signup(client, email="b@even.app")
        group = create_group(client, token_a)
        client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_a))
        client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Rent",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 1000}],
                "participantIds": [user_a["id"], user_b["id"]],
            },
            headers=auth_headers(token_a),
        )

        res = client.post(f"/api/groups/{group['id']}/leave", headers=auth_headers(token_b))
        assert res.status_code == 400

    def test_succeeds_once_balance_is_zero(self, client: TestClient) -> None:
        token_a, _ = signup(client, email="a@even.app")
        token_b, _ = signup(client, email="b@even.app")
        group = create_group(client, token_a)
        client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_a))

        res = client.post(f"/api/groups/{group['id']}/leave", headers=auth_headers(token_b))
        assert res.status_code == 204
        remaining = client.get(f"/api/groups/{group['id']}", headers=auth_headers(token_a)).json()
        assert len(remaining["members"]) == 1


class TestDeleteGroup:
    def test_non_admin_cannot_delete(self, client: TestClient) -> None:
        token_admin, _ = signup(client, email="admin@even.app")
        token_member, _ = signup(client, email="member@even.app")
        group = create_group(client, token_admin)
        client.post(f"/api/groups/{group['id']}/members", json={"email": "member@even.app"}, headers=auth_headers(token_admin))

        res = client.delete(f"/api/groups/{group['id']}", headers=auth_headers(token_member))
        assert res.status_code == 403

    def test_admin_can_delete_and_it_cascades(self, client: TestClient) -> None:
        token, user = signup(client)
        group = create_group(client, token)
        client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Something",
                "amountCents": 100,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user["id"], "amountCents": 100}],
                "participantIds": [user["id"]],
            },
            headers=auth_headers(token),
        )

        res = client.delete(f"/api/groups/{group['id']}", headers=auth_headers(token))
        assert res.status_code == 204
        assert client.get(f"/api/groups/{group['id']}", headers=auth_headers(token)).status_code == 404
