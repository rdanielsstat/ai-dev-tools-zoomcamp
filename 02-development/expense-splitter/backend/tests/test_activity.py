from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth_headers, create_group, signup


class TestActivityFeed:
    def test_logs_group_creation_and_expense_events_newest_first(self, client: TestClient) -> None:
        token, user = signup(client)
        group = create_group(client, token, name="Trip")

        client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Coffee",
                "amountCents": 500,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user["id"], "amountCents": 500}],
                "participantIds": [user["id"]],
            },
            headers=auth_headers(token),
        )

        res = client.get(f"/api/groups/{group['id']}/activity", headers=auth_headers(token))
        assert res.status_code == 200
        kinds = [e["kind"] for e in res.json()]
        assert kinds == ["expense_added", "group_created"]

    def test_logs_payments_and_membership_changes(self, client: TestClient) -> None:
        token_a, _ = signup(client, email="a@even.app")
        token_b, _ = signup(client, email="b@even.app")
        group = create_group(client, token_a)
        client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_a))
        client.post(f"/api/groups/{group['id']}/leave", headers=auth_headers(token_b))

        res = client.get(f"/api/groups/{group['id']}/activity", headers=auth_headers(token_a))
        kinds = [e["kind"] for e in res.json()]
        assert kinds == ["member_left", "member_joined", "group_created"]

    def test_non_member_cannot_view_activity(self, client: TestClient) -> None:
        token, _ = signup(client)
        group = create_group(client, token)
        token_outsider, _ = signup(client, email="outsider@even.app")
        res = client.get(f"/api/groups/{group['id']}/activity", headers=auth_headers(token_outsider))
        assert res.status_code == 404
