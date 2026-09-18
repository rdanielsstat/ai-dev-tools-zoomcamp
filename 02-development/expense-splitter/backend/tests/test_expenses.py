from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth_headers, create_group, signup


def _duo(client: TestClient) -> tuple[str, dict, str, dict, dict]:
    """Two signed-up users sharing a group. Returns (token_a, user_a, token_b, user_b, group)."""
    token_a, user_a = signup(client, email="a@even.app")
    token_b, user_b = signup(client, email="b@even.app")
    group = create_group(client, token_a, name="Duo")
    client.post(f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token_a))
    return token_a, user_a, token_b, user_b, group


class TestAddExpense:
    def test_adds_an_equal_split_expense(self, client: TestClient) -> None:
        token_a, user_a, _, user_b, group = _duo(client)
        res = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Coffee",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": "Food",
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 1000}],
                "participantIds": [user_a["id"], user_b["id"]],
            },
            headers=auth_headers(token_a),
        )
        assert res.status_code == 201
        body = res.json()
        assert body["shares"] == {user_a["id"]: 500, user_b["id"]: 500}

    def test_rejects_a_split_that_does_not_reconcile(self, client: TestClient) -> None:
        token_a, user_a, _, user_b, group = _duo(client)
        res = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Bad split",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": None,
                "splitType": "exact",
                "payers": [{"userId": user_a["id"], "amountCents": 1000}],
                "participantIds": [user_a["id"], user_b["id"]],
                "values": {user_a["id"]: 400, user_b["id"]: 550},
            },
            headers=auth_headers(token_a),
        )
        assert res.status_code == 400

    def test_rejects_payers_that_do_not_sum_to_the_total(self, client: TestClient) -> None:
        token_a, user_a, _, _, group = _duo(client)
        res = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Mismatched payers",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 400}],
                "participantIds": [user_a["id"]],
            },
            headers=auth_headers(token_a),
        )
        assert res.status_code == 400

    def test_non_member_cannot_add_an_expense(self, client: TestClient) -> None:
        token_a, user_a, _, _, group = _duo(client)
        token_outsider, _ = signup(client, email="outsider@even.app")
        res = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Sneaky",
                "amountCents": 100,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 100}],
                "participantIds": [user_a["id"]],
            },
            headers=auth_headers(token_outsider),
        )
        assert res.status_code == 404


class TestEditAndDeleteExpense:
    def test_edits_an_expense_preserving_its_id(self, client: TestClient) -> None:
        token_a, user_a, _, user_b, group = _duo(client)
        created = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Coffee",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 1000}],
                "participantIds": [user_a["id"], user_b["id"]],
            },
            headers=auth_headers(token_a),
        ).json()

        res = client.patch(
            f"/api/expenses/{created['id']}",
            json={
                "groupId": group["id"],
                "description": "Coffee and pastries",
                "amountCents": 2000,
                "date": "2026-01-02",
                "category": "Food",
                "splitType": "exact",
                "payers": [{"userId": user_a["id"], "amountCents": 2000}],
                "participantIds": [user_a["id"], user_b["id"]],
                "values": {user_a["id"]: 1200, user_b["id"]: 800},
            },
            headers=auth_headers(token_a),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == created["id"]
        assert body["description"] == "Coffee and pastries"
        assert body["shares"] == {user_a["id"]: 1200, user_b["id"]: 800}

    def test_deletes_an_expense(self, client: TestClient) -> None:
        token_a, user_a, _, _, group = _duo(client)
        created = client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "One-off",
                "amountCents": 500,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user_a["id"], "amountCents": 500}],
                "participantIds": [user_a["id"]],
            },
            headers=auth_headers(token_a),
        ).json()

        res = client.delete(f"/api/expenses/{created['id']}", headers=auth_headers(token_a))
        assert res.status_code == 204
        remaining = client.get(f"/api/groups/{group['id']}/expenses", headers=auth_headers(token_a)).json()
        assert remaining == []

    def test_editing_an_unknown_expense_404s(self, client: TestClient) -> None:
        token, user = signup(client)
        group = create_group(client, token)
        res = client.patch(
            "/api/expenses/nope",
            json={
                "groupId": group["id"],
                "description": "X",
                "amountCents": 100,
                "date": "2026-01-01",
                "category": None,
                "splitType": "equal",
                "payers": [{"userId": user["id"], "amountCents": 100}],
                "participantIds": [user["id"]],
            },
            headers=auth_headers(token),
        )
        assert res.status_code == 404


class TestListExpenses:
    def test_filters_by_category_and_date_range(self, client: TestClient) -> None:
        token_a, user_a, _, _, group = _duo(client)
        for desc, category, day in [("Groceries", "Food", "2026-01-05"), ("Rent", "Housing", "2026-01-01")]:
            client.post(
                f"/api/groups/{group['id']}/expenses",
                json={
                    "groupId": group["id"],
                    "description": desc,
                    "amountCents": 100,
                    "date": day,
                    "category": category,
                    "splitType": "equal",
                    "payers": [{"userId": user_a["id"], "amountCents": 100}],
                    "participantIds": [user_a["id"]],
                },
                headers=auth_headers(token_a),
            )

        res = client.get(f"/api/groups/{group['id']}/expenses?category=Food", headers=auth_headers(token_a))
        assert [e["description"] for e in res.json()] == ["Groceries"]

        res = client.get(
            f"/api/groups/{group['id']}/expenses?dateFrom=2026-01-03", headers=auth_headers(token_a)
        )
        assert [e["description"] for e in res.json()] == ["Groceries"]

    def test_non_member_cannot_list_expenses(self, client: TestClient) -> None:
        token_a, _, _, _, group = _duo(client)
        token_outsider, _ = signup(client, email="outsider@even.app")
        res = client.get(f"/api/groups/{group['id']}/expenses", headers=auth_headers(token_outsider))
        assert res.status_code == 404
