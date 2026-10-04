from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DB_PATH", tmp_path / "orders.db")
    with TestClient(main.app) as test_client:
        yield test_client


def test_health_and_seeded_orders(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    orders = client.get("/api/orders").json()
    assert len(orders) == 3
    assert {order["priority"] for order in orders} == {"standard", "express"}


def test_create_and_update_order(client):
    response = client.post(
        "/api/orders",
        json={"customer": "Taylor", "item": "Mug", "priority": "standard"},
    )
    assert response.status_code == 201
    order_id = response.json()["id"]
    assert client.get(f"/api/orders/{order_id}").json()["status"] == "received"
    updated = client.patch(f"/api/orders/{order_id}", json={"status": "shipped"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "shipped"


def test_missing_order(client):
    assert client.get("/api/orders/missing").status_code == 404


def test_express_order_placed_at_month_end(client):
    # Seeded express-1002 was placed on the last day of the previous month.
    response = client.get("/api/orders/express-1002")
    assert response.status_code == 200
    placed_at = datetime.fromisoformat(response.json()["created_at"])
    expected = (placed_at + timedelta(days=2)).date().isoformat()
    assert response.json()["estimated_delivery"] == expected


@pytest.mark.parametrize(
    ("created_at", "estimated_delivery"),
    [
        ("2026-01-31T10:00:00+00:00", "2026-02-02"),
        ("2026-02-27T10:00:00+00:00", "2026-03-01"),
        ("2026-12-31T23:30:00+00:00", "2027-01-02"),
    ],
)
def test_express_delivery_estimate_crosses_month_and_year(created_at, estimated_delivery):
    order = main.order_detail({"priority": "express", "created_at": created_at})
    assert order["estimated_delivery"] == estimated_delivery
