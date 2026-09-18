"""Pydantic models mirroring openapi.yaml. Field names are snake_case in
Python but (de)serialize as camelCase, matching the frontend's types.ts
without a translation layer."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, EmailStr, Field
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Role(str, Enum):
    admin = "admin"
    member = "member"


class SplitType(str, Enum):
    equal = "equal"
    exact = "exact"
    percent = "percent"
    shares = "shares"
    itemized = "itemized"


class ActivityKind(str, Enum):
    expense_added = "expense_added"
    expense_edited = "expense_edited"
    expense_deleted = "expense_deleted"
    payment_recorded = "payment_recorded"
    member_joined = "member_joined"
    member_left = "member_left"
    group_created = "group_created"


class User(CamelModel):
    id: str
    name: str
    email: EmailStr
    avatar_initials: str


class Member(CamelModel):
    user_id: str
    name: str
    avatar_initials: str
    role: Role
    joined_at: date


class Group(CamelModel):
    id: str
    name: str
    description: str
    created_by: str
    created_at: date
    members: list[Member]


class Payer(CamelModel):
    user_id: str
    amount_cents: int


class ItemizedLine(CamelModel):
    id: str
    label: str
    amount_cents: int
    participant_ids: list[str]


class Expense(CamelModel):
    id: str
    group_id: str
    description: str
    amount_cents: int
    date: date
    category: str | None
    split_type: SplitType
    payers: list[Payer]
    shares: dict[str, int]
    items: list[ItemizedLine] | None = None
    split_values: dict[str, float] | None = None
    created_by: str


class NewExpenseInput(CamelModel):
    group_id: str
    description: str
    amount_cents: int
    date: date
    category: str | None
    split_type: SplitType
    payers: list[Payer]
    participant_ids: list[str]
    values: dict[str, float] | None = None
    items: list[ItemizedLine] | None = None
    extra_cents: int = 0


class Payment(CamelModel):
    id: str
    group_id: str
    from_user_id: str
    to_user_id: str
    amount_cents: int
    date: date
    note: str | None = None


class NewPaymentInput(CamelModel):
    group_id: str
    from_user_id: str
    to_user_id: str
    amount_cents: int
    date: date
    note: str | None = None


class ActivityEvent(CamelModel):
    id: str
    group_id: str
    kind: ActivityKind
    actor_user_id: str
    summary: str
    amount_cents: int | None = None
    at: datetime


class Transfer(CamelModel):
    from_user_id: str
    to_user_id: str
    amount_cents: int


class GroupBalances(CamelModel):
    net: dict[str, int]
    pairwise: list[Transfer]
    settlement: list[Transfer]


# ---- auth request/response bodies ----


class SignupRequest(CamelModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=8)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(CamelModel):
    name: str | None = None
    email: EmailStr | None = None


class AuthResponse(CamelModel):
    token: str
    user: User


class CreateGroupRequest(CamelModel):
    name: str
    description: str


class RenameGroupRequest(CamelModel):
    name: str


class AddMemberRequest(CamelModel):
    email: EmailStr
