from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth_headers, create_group, signup


def _duo_with_expense(client: TestClient, amount_cents: int = 4000) -> tuple[str, dict, str, dict, dict]:
    token_a, user_a = signup(client, email="a@even.app")
    token_b, user_b = signup(client, email="b@even.app")
    group = create_group(client, token_a, name="Duo balances")
    client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_a))
    client.post(
        f"/api/groups/{group['id']}/expenses",
        json={
            "groupId": group["id"],
            "description": "Dinner",
            "amountCents": amount_cents,
            "date": "2026-01-01",
            "category": None,
            "splitType": "equal",
            "payers": [{"userId": user_a["id"], "amountCents": amount_cents}],
            "participantIds": [user_a["id"], user_b["id"]],
        },
        headers=auth_headers(token_a),
    )
    return token_a, user_a, token_b, user_b, group


class TestGetBalances:
    def test_computes_net_balances_and_a_settlement_plan(self, client: TestClient) -> None:
        token_a, user_a, _, user_b, group = _duo_with_expense(client, amount_cents=4000)
        res = client.get(f"/api/groups/{group['id']}/balances", headers=auth_headers(token_a))
        assert res.status_code == 200
        body = res.json()
        assert body["net"][user_a["id"]] == 2000
        assert body["net"][user_b["id"]] == -2000
        assert body["settlement"] == [{"fromUserId": user_b["id"], "toUserId": user_a["id"], "amountCents": 2000}]

    def test_non_member_cannot_view_balances(self, client: TestClient) -> None:
        _, _, _, _, group = _duo_with_expense(client)
        token_outsider, _ = signup(client, email="outsider@even.app")
        res = client.get(f"/api/groups/{group['id']}/balances", headers=auth_headers(token_outsider))
        assert res.status_code == 404


class TestRecordPayment:
    def test_recording_a_payment_zeroes_the_balance(self, client: TestClient) -> None:
        token_a, user_a, token_b, user_b, group = _duo_with_expense(client, amount_cents=2000)

        res = client.post(
            f"/api/groups/{group['id']}/payments",
            json={
                "groupId": group["id"],
                "fromUserId": user_b["id"],
                "toUserId": user_a["id"],
                "amountCents": 1000,
                "date": "2026-01-02",
            },
            headers=auth_headers(token_b),
        )
        assert res.status_code == 201

        balances = client.get(f"/api/groups/{group['id']}/balances", headers=auth_headers(token_a)).json()
        assert balances["net"][user_a["id"]] == 0
        assert balances["net"][user_b["id"]] == 0
        assert balances["settlement"] == []

    def test_appears_in_payments_list(self, client: TestClient) -> None:
        token_a, user_a, token_b, user_b, group = _duo_with_expense(client)
        client.post(
            f"/api/groups/{group['id']}/payments",
            json={
                "groupId": group["id"],
                "fromUserId": user_b["id"],
                "toUserId": user_a["id"],
                "amountCents": 500,
                "date": "2026-01-02",
            },
            headers=auth_headers(token_b),
        )
        res = client.get(f"/api/groups/{group['id']}/payments", headers=auth_headers(token_a))
        assert res.status_code == 200
        assert len(res.json()) == 1
        assert res.json()[0]["amountCents"] == 500

    def test_non_member_cannot_record_a_payment(self, client: TestClient) -> None:
        _, user_a, _, user_b, group = _duo_with_expense(client)
        token_outsider, _ = signup(client, email="outsider@even.app")
        res = client.post(
            f"/api/groups/{group['id']}/payments",
            json={
                "groupId": group["id"],
                "fromUserId": user_b["id"],
                "toUserId": user_a["id"],
                "amountCents": 500,
                "date": "2026-01-02",
            },
            headers=auth_headers(token_outsider),
        )
        assert res.status_code == 404
