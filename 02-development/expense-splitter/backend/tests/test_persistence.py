"""Tests specific to the SQLAlchemy-backed store — the properties the old
in-memory mock could never have: data survives a process restart, and the
schema itself (not just app code) enforces integrity."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.models import ExpenseModel, ItemizedLineModel, MembershipModel, PayerModel, UserModel
from app.db.session import make_session_factory
from app.main import create_app

from .conftest import auth_headers, create_group, signup


@pytest.fixture
def file_db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'even-test.db'}"


class TestSurvivesARestart:
    def test_data_written_by_one_app_instance_is_visible_from_a_fresh_one(self, file_db_url: str) -> None:
        first_run = TestClient(create_app(database_url=file_db_url))
        token, user = signup(first_run, email="durable@even.app")
        group = create_group(first_run, token, name="Durable trip")

        # A brand-new app instance — same file, no shared Python state —
        # stands in for restarting the backend process.
        second_run = TestClient(create_app(database_url=file_db_url))
        res = second_run.get("/api/groups", headers=auth_headers(token))
        assert res.status_code == 200
        assert [g["id"] for g in res.json()] == [group["id"]]

        res = second_run.get("/api/me", headers=auth_headers(token))
        assert res.json()["email"] == "durable@even.app"
        assert res.json()["id"] == user["id"]


class TestForeignKeyCascade:
    def test_deleting_a_group_removes_its_expenses_payers_and_memberships_at_the_db_level(
        self, client: TestClient
    ) -> None:
        token, user_a = signup(client, email="a@even.app")
        _, user_b = signup(client, email="b@even.app")
        group = create_group(client, token)
        client.post(
            f"/api/groups/{group['id']}/members", json={"email": "b@even.app"}, headers=auth_headers(token)
        )
        client.post(
            f"/api/groups/{group['id']}/expenses",
            json={
                "groupId": group["id"],
                "description": "Cascade check",
                "amountCents": 1000,
                "date": "2026-01-01",
                "category": None,
                "splitType": "itemized",
                "payers": [{"userId": user_a["id"], "amountCents": 1000}],
                "participantIds": [user_a["id"], user_b["id"]],
                "items": [
                    {
                        "id": "li_1",
                        "label": "Shared item",
                        "amountCents": 1000,
                        "participantIds": [user_a["id"], user_b["id"]],
                    }
                ],
            },
            headers=auth_headers(token),
        )

        res = client.delete(f"/api/groups/{group['id']}", headers=auth_headers(token))
        assert res.status_code == 204

        # Reach past the API into the same DB this test client's app is
        # using, to prove the child rows are actually gone — not just
        # unreachable through the (now-404) group endpoints.
        session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
        db = session_factory()
        try:
            assert db.query(ExpenseModel).filter_by(group_id=group["id"]).count() == 0
            assert db.query(PayerModel).count() == 0
            assert db.query(ItemizedLineModel).count() == 0
            assert db.query(MembershipModel).filter_by(group_id=group["id"]).count() == 0
            # Users themselves are untouched by a group deletion.
            assert db.query(UserModel).filter_by(id=user_a["id"]).count() == 1
        finally:
            db.close()


class TestSchemaLevelConstraints:
    def test_duplicate_email_is_rejected_by_the_database_itself(self, file_db_url: str) -> None:
        """Belt-and-suspenders check: even bypassing Store's own uniqueness
        check (app/store.py's ConflictError), the unique index on
        users.email — not just app code — refuses a second row."""
        session_factory = make_session_factory(file_db_url)
        db = session_factory()
        try:
            db.add(
                UserModel(
                    id=f"u_{uuid.uuid4().hex[:12]}",
                    name="First",
                    email="dupe@even.app",
                    avatar_initials="FI",
                    password_hash="irrelevant",
                )
            )
            db.commit()

            db.add(
                UserModel(
                    id=f"u_{uuid.uuid4().hex[:12]}",
                    name="Second",
                    email="dupe@even.app",
                    avatar_initials="SE",
                    password_hash="irrelevant",
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
        finally:
            db.rollback()
            db.close()
