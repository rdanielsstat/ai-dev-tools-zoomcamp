"""SQLAlchemy ORM models — the real, persistent schema behind app/store.py.

Design notes:
- IDs for the entities the API exposes (User, Group, Expense, Payment,
  ActivityEvent) are opaque strings (uuid4 hex, prefixed), matching what the
  API already returns — no behavior change for clients. Purely internal
  join/child rows (Membership, Payer, ItemizedLineParticipant) use
  autoincrementing integer PKs since nothing outside the DB ever sees them.
- `Expense.shares` / `Expense.split_values` stay as JSON columns rather than
  a child table: they're free-form `{userId: number}` maps with no fixed
  columns, exactly what the API contract (openapi.yaml) already promises,
  and SQLAlchemy's `JSON` type is portable across SQLite/Postgres/MySQL.
- Payers and itemized lines *do* get their own tables — they're genuinely
  a list of records, and normalizing them means a future feature (e.g.
  "total spent per category" or "expenses I paid for") is a query, not a
  Python loop over deserialized JSON.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, DateTime, Enum as SAEnum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..schemas import ActivityKind, Role, SplitType
from .base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    avatar_initials: Mapped[str] = mapped_column(String, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)


class TokenModel(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GroupModel(Base):
    __tablename__ = "groups"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[date] = mapped_column(nullable=False)

    memberships: Mapped[list[MembershipModel]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )
    expenses: Mapped[list[ExpenseModel]] = relationship(cascade="all, delete-orphan")
    payments: Mapped[list[PaymentModel]] = relationship(cascade="all, delete-orphan")
    activity_events: Mapped[list[ActivityEventModel]] = relationship(cascade="all, delete-orphan")


class MembershipModel(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_membership_group_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role), nullable=False)
    joined_at: Mapped[date] = mapped_column(nullable=False)

    group: Mapped[GroupModel] = relationship(back_populates="memberships")
    user: Mapped[UserModel] = relationship()


class ExpenseModel(Base):
    __tablename__ = "expenses"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    split_type: Mapped[SplitType] = mapped_column(SAEnum(SplitType), nullable=False)
    shares: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    split_values: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

    payers: Mapped[list[PayerModel]] = relationship(cascade="all, delete-orphan")
    items: Mapped[list[ItemizedLineModel]] = relationship(cascade="all, delete-orphan")


class PayerModel(Base):
    __tablename__ = "payers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    expense_id: Mapped[str] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class ItemizedLineModel(Base):
    __tablename__ = "itemized_lines"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    expense_id: Mapped[str] = mapped_column(ForeignKey("expenses.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    participants: Mapped[list[ItemizedLineParticipantModel]] = relationship(cascade="all, delete-orphan")


class ItemizedLineParticipantModel(Base):
    __tablename__ = "itemized_line_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("itemized_lines.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    from_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    to_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[date] = mapped_column(nullable=False)
    note: Mapped[str | None] = mapped_column(String, nullable=True)


class ActivityEventModel(Base):
    __tablename__ = "activity_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[ActivityKind] = mapped_column(SAEnum(ActivityKind), nullable=False)
    actor_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
