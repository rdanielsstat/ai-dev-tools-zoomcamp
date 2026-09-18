"""Business logic and persistence, backed by SQLAlchemy (see app/db/). This
is the only module that touches the database — routers only ever call
methods on a Store instance and only ever see the Pydantic schemas in
app/schemas.py, never an ORM row, so the concrete database (currently SQLite,
see app/db/session.py) can change without touching a single router."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import Depends
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .db.models import (
    ActivityEventModel,
    ExpenseModel,
    GroupModel,
    ItemizedLineModel,
    ItemizedLineParticipantModel,
    MembershipModel,
    PayerModel,
    PaymentModel,
    TokenModel,
    UserModel,
)
from .errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from .money import compute_split, simplify_debts
from .schemas import (
    ActivityEvent,
    ActivityKind,
    Expense,
    Group,
    GroupBalances,
    ItemizedLine,
    Member,
    NewExpenseInput,
    NewPaymentInput,
    Payer,
    Payment,
    Role,
    Transfer,
    User,
)
from .db.session import get_db
from .security import hash_password, new_token, verify_password


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _user_schema(u: UserModel) -> User:
    return User(id=u.id, name=u.name, email=u.email, avatar_initials=u.avatar_initials)


def _group_schema(g: GroupModel) -> Group:
    return Group(
        id=g.id,
        name=g.name,
        description=g.description,
        created_by=g.created_by,
        created_at=g.created_at,
        members=[
            Member(
                user_id=m.user_id,
                name=m.user.name,
                avatar_initials=m.user.avatar_initials,
                role=m.role,
                joined_at=m.joined_at,
            )
            for m in g.memberships
        ],
    )


def _expense_schema(e: ExpenseModel) -> Expense:
    return Expense(
        id=e.id,
        group_id=e.group_id,
        description=e.description,
        amount_cents=e.amount_cents,
        date=e.date,
        category=e.category,
        split_type=e.split_type,
        payers=[Payer(user_id=p.user_id, amount_cents=p.amount_cents) for p in e.payers],
        shares=e.shares,
        items=[
            ItemizedLine(
                id=item.id,
                label=item.label,
                amount_cents=item.amount_cents,
                participant_ids=[pp.user_id for pp in item.participants],
            )
            for item in e.items
        ]
        or None,
        split_values=e.split_values,
        created_by=e.created_by,
    )


def _payment_schema(p: PaymentModel) -> Payment:
    return Payment(
        id=p.id,
        group_id=p.group_id,
        from_user_id=p.from_user_id,
        to_user_id=p.to_user_id,
        amount_cents=p.amount_cents,
        date=p.date,
        note=p.note,
    )


def _activity_schema(a: ActivityEventModel) -> ActivityEvent:
    return ActivityEvent(
        id=a.id,
        group_id=a.group_id,
        kind=a.kind,
        actor_user_id=a.actor_user_id,
        summary=a.summary,
        amount_cents=a.amount_cents,
        at=a.at,
    )


class Store:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ---- auth ---------------------------------------------------------

    def sign_up(self, name: str, email: str, password: str) -> tuple[User, str]:
        email_lower = email.strip().lower()
        existing = self.db.execute(
            select(UserModel).where(func.lower(UserModel.email) == email_lower)
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError("An account with this email already exists.")

        initials = "".join(p[0] for p in name.split() if p)[:2].upper() or "EV"
        user = UserModel(
            id=_new_id("u"), name=name, email=email, avatar_initials=initials, password_hash=hash_password(password)
        )
        self.db.add(user)
        self.db.flush()  # tokens.user_id FKs to users.id; no relationship links them, so flush first
        token = new_token()
        self.db.add(TokenModel(token=token, user_id=user.id, created_at=datetime.now(timezone.utc)))
        self.db.commit()
        return _user_schema(user), token

    def log_in(self, email: str, password: str) -> tuple[User, str]:
        email_lower = email.strip().lower()
        user = self.db.execute(
            select(UserModel).where(func.lower(UserModel.email) == email_lower)
        ).scalar_one_or_none()
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Invalid email or password.")

        token = new_token()
        self.db.add(TokenModel(token=token, user_id=user.id, created_at=datetime.now(timezone.utc)))
        self.db.commit()
        return _user_schema(user), token

    def log_out(self, token: str) -> None:
        self.db.execute(sa_delete(TokenModel).where(TokenModel.token == token))
        self.db.commit()

    def update_profile(self, user_id: str, name: str | None, email: str | None) -> User:
        user = self.db.get(UserModel, user_id)
        if user is None:
            raise NotFoundError("User not found.")

        if email is not None:
            email_lower = email.strip().lower()
            taken = self.db.execute(
                select(UserModel).where(func.lower(UserModel.email) == email_lower, UserModel.id != user_id)
            ).scalar_one_or_none()
            if taken is not None:
                raise ConflictError("This email is already in use by another account.")
            user.email = email
        if name is not None:
            user.name = name

        self.db.commit()
        return _user_schema(user)

    # ---- groups ---------------------------------------------------------

    def _group_orm_or_404(self, group_id: str, user_id: str) -> GroupModel:
        group = self.db.get(GroupModel, group_id)
        if group is None or not any(m.user_id == user_id for m in group.memberships):
            raise NotFoundError("Group not found.")
        return group

    def groups_for_user(self, user_id: str) -> list[Group]:
        stmt = select(GroupModel).join(MembershipModel).where(MembershipModel.user_id == user_id)
        groups = self.db.execute(stmt).scalars().unique().all()
        return [_group_schema(g) for g in groups]

    def get_group(self, group_id: str) -> Group | None:
        group = self.db.get(GroupModel, group_id)
        return _group_schema(group) if group else None

    def require_membership(self, group_id: str, user_id: str) -> Group:
        return _group_schema(self._group_orm_or_404(group_id, user_id))

    def create_group(self, user_id: str, name: str, description: str) -> Group:
        group = GroupModel(id=_new_id("g"), name=name, description=description, created_by=user_id, created_at=_today())
        group.memberships.append(MembershipModel(user_id=user_id, role=Role.admin, joined_at=_today()))
        self.db.add(group)
        self.db.flush()  # activity_events.group_id FKs to groups.id; no relationship links them
        self._log(group.id, ActivityKind.group_created, user_id, f"created {name}")
        self.db.commit()
        return _group_schema(group)

    def rename_group(self, group_id: str, user_id: str, name: str) -> Group:
        group = self._group_orm_or_404(group_id, user_id)
        self._require_admin(group, user_id)
        group.name = name
        self.db.commit()
        return _group_schema(group)

    def add_member(self, group_id: str, user_id: str, email: str) -> Group:
        group = self._group_orm_or_404(group_id, user_id)
        email_lower = email.strip().lower()
        member_user = self.db.execute(
            select(UserModel).where(func.lower(UserModel.email) == email_lower)
        ).scalar_one_or_none()
        if member_user is None:
            handle = email.split("@")[0] or "guest"
            member_user = UserModel(
                id=_new_id("u"),
                name=handle[:1].upper() + handle[1:],
                email=email,
                avatar_initials=handle[:2].upper(),
                password_hash=hash_password(new_token()),
            )
            self.db.add(member_user)
            self.db.flush()

        if not any(m.user_id == member_user.id for m in group.memberships):
            group.memberships.append(MembershipModel(user_id=member_user.id, role=Role.member, joined_at=_today()))
            self._log(group.id, ActivityKind.member_joined, member_user.id, "joined the group")

        self.db.commit()
        return _group_schema(group)

    def leave_group(self, group_id: str, user_id: str) -> None:
        group = self._group_orm_or_404(group_id, user_id)
        net = self.get_balances(group_id, user_id).net.get(user_id, 0)
        if net != 0:
            raise BadRequestError("Settle up before leaving this group.")
        membership = next(m for m in group.memberships if m.user_id == user_id)
        group.memberships.remove(membership)
        self._log(group_id, ActivityKind.member_left, user_id, "left the group")
        self.db.commit()

    def delete_group(self, group_id: str, user_id: str) -> None:
        group = self._group_orm_or_404(group_id, user_id)
        self._require_admin(group, user_id)
        self.db.delete(group)
        self.db.commit()

    def _require_admin(self, group: GroupModel, user_id: str) -> None:
        member = next((m for m in group.memberships if m.user_id == user_id), None)
        if member is None or member.role != Role.admin:
            raise ForbiddenError("Only an admin can perform this action.")

    # ---- expenses ---------------------------------------------------------

    def list_expenses(
        self,
        group_id: str,
        user_id: str,
        *,
        member_id: str | None = None,
        category: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Expense]:
        self._group_orm_or_404(group_id, user_id)
        stmt = select(ExpenseModel).where(ExpenseModel.group_id == group_id)
        if category:
            stmt = stmt.where(ExpenseModel.category == category)
        if date_from:
            stmt = stmt.where(ExpenseModel.date >= date_from)
        if date_to:
            stmt = stmt.where(ExpenseModel.date <= date_to)
        rows = list(self.db.execute(stmt).scalars().all())

        # Membership filtering reaches into the `shares` JSON map — keeping
        # it in Python avoids relying on JSON query support that differs a
        # lot between SQLite, Postgres, and MySQL.
        if member_id:
            rows = [e for e in rows if any(p.user_id == member_id for p in e.payers) or member_id in e.shares]

        rows.sort(key=lambda e: e.date, reverse=True)
        return [_expense_schema(e) for e in rows]

    def _apply_expense_fields(self, expense: ExpenseModel, input: NewExpenseInput) -> None:
        payers_total = sum(p.amount_cents for p in input.payers)
        if not input.payers or payers_total != input.amount_cents:
            raise BadRequestError(f"Payers must add up to the total amount ({input.amount_cents} cents).")

        shares, error = compute_split(
            input.split_type,
            input.amount_cents,
            input.participant_ids,
            values=input.values,
            items=input.items,
            extra_cents=input.extra_cents,
        )
        if error:
            raise BadRequestError(error)

        expense.group_id = input.group_id
        expense.description = input.description
        expense.amount_cents = input.amount_cents
        expense.date = input.date
        expense.category = input.category
        expense.split_type = input.split_type
        expense.shares = shares
        expense.split_values = input.values
        # Reassigning these relationships lets delete-orphan cascade clean up
        # whatever was there before (relevant on edit; a no-op on create).
        expense.payers = [PayerModel(user_id=p.user_id, amount_cents=p.amount_cents) for p in input.payers]
        expense.items = [
            ItemizedLineModel(
                id=item.id,
                label=item.label,
                amount_cents=item.amount_cents,
                participants=[ItemizedLineParticipantModel(user_id=uid) for uid in item.participant_ids],
            )
            for item in (input.items or [])
        ]

    def add_expense(self, group_id: str, user_id: str, input: NewExpenseInput) -> Expense:
        self._group_orm_or_404(group_id, user_id)
        expense = ExpenseModel(id=_new_id("e"), created_by=user_id)
        self._apply_expense_fields(expense, input)
        self.db.add(expense)
        self._log(group_id, ActivityKind.expense_added, user_id, f"added {expense.description}", expense.amount_cents)
        self.db.commit()
        return _expense_schema(expense)

    def edit_expense(self, expense_id: str, user_id: str, input: NewExpenseInput) -> Expense:
        expense = self.db.get(ExpenseModel, expense_id)
        if expense is None:
            raise NotFoundError("Expense not found.")
        self._group_orm_or_404(expense.group_id, user_id)
        self._apply_expense_fields(expense, input)
        self._log(expense.group_id, ActivityKind.expense_edited, user_id, f"edited {expense.description}", expense.amount_cents)
        self.db.commit()
        return _expense_schema(expense)

    def delete_expense(self, expense_id: str, user_id: str) -> None:
        expense = self.db.get(ExpenseModel, expense_id)
        if expense is None:
            raise NotFoundError("Expense not found.")
        self._group_orm_or_404(expense.group_id, user_id)
        self._log(expense.group_id, ActivityKind.expense_deleted, user_id, f"deleted {expense.description}", expense.amount_cents)
        self.db.delete(expense)
        self.db.commit()

    # ---- balances, payments, settlement ------------------------------------

    def get_balances(self, group_id: str, user_id: str) -> GroupBalances:
        group = self._group_orm_or_404(group_id, user_id)
        net: dict[str, int] = {m.user_id: 0 for m in group.memberships}
        pair: dict[str, int] = {}

        def bump(frm: str, to: str, cents: int) -> None:
            if frm == to or cents == 0:
                return
            key = f"{frm}|{to}" if frm < to else f"{to}|{frm}"
            sign = 1 if frm < to else -1
            pair[key] = pair.get(key, 0) + sign * cents

        expenses = self.db.execute(select(ExpenseModel).where(ExpenseModel.group_id == group_id)).scalars().all()
        for expense in expenses:
            for payer in expense.payers:
                net[payer.user_id] = net.get(payer.user_id, 0) + payer.amount_cents
            for uid, cents in expense.shares.items():
                net[uid] = net.get(uid, 0) - cents
                for payer in expense.payers:
                    portion = round(cents * payer.amount_cents / expense.amount_cents)
                    bump(uid, payer.user_id, portion)

        payments = self.db.execute(select(PaymentModel).where(PaymentModel.group_id == group_id)).scalars().all()
        for payment in payments:
            net[payment.from_user_id] = net.get(payment.from_user_id, 0) + payment.amount_cents
            net[payment.to_user_id] = net.get(payment.to_user_id, 0) - payment.amount_cents
            bump(payment.to_user_id, payment.from_user_id, payment.amount_cents)

        pairwise: list[Transfer] = []
        for key, cents in pair.items():
            if cents == 0:
                continue
            a, b = key.split("|")
            if cents > 0:
                pairwise.append(Transfer(from_user_id=a, to_user_id=b, amount_cents=cents))
            else:
                pairwise.append(Transfer(from_user_id=b, to_user_id=a, amount_cents=-cents))
        pairwise.sort(key=lambda t: -t.amount_cents)

        return GroupBalances(net=net, pairwise=pairwise, settlement=simplify_debts(net))

    def list_payments(self, group_id: str, user_id: str) -> list[Payment]:
        self._group_orm_or_404(group_id, user_id)
        rows = self.db.execute(select(PaymentModel).where(PaymentModel.group_id == group_id)).scalars().all()
        return [_payment_schema(p) for p in rows]

    def record_payment(self, group_id: str, user_id: str, input: NewPaymentInput) -> Payment:
        self._group_orm_or_404(group_id, user_id)
        payment = PaymentModel(
            id=_new_id("p"),
            group_id=group_id,
            from_user_id=input.from_user_id,
            to_user_id=input.to_user_id,
            amount_cents=input.amount_cents,
            date=input.date,
            note=input.note,
        )
        self.db.add(payment)
        to_user = self.db.get(UserModel, input.to_user_id)
        to_name = to_user.name.split()[0] if to_user else "member"
        self._log(group_id, ActivityKind.payment_recorded, input.from_user_id, f"recorded a payment to {to_name}", payment.amount_cents)
        self.db.commit()
        return _payment_schema(payment)

    # ---- activity ---------------------------------------------------------

    def list_activity(self, group_id: str, user_id: str) -> list[ActivityEvent]:
        self._group_orm_or_404(group_id, user_id)
        rows = self.db.execute(
            select(ActivityEventModel).where(ActivityEventModel.group_id == group_id).order_by(ActivityEventModel.at.desc())
        ).scalars().all()
        return [_activity_schema(a) for a in rows]

    def _log(self, group_id: str, kind: ActivityKind, actor_user_id: str, summary: str, amount_cents: int | None = None) -> None:
        self.db.add(
            ActivityEventModel(
                id=_new_id("a"),
                group_id=group_id,
                kind=kind,
                actor_user_id=actor_user_id,
                summary=summary,
                amount_cents=amount_cents,
                at=datetime.now(timezone.utc),
            )
        )


def get_store(db: Session = Depends(get_db)) -> Store:
    return Store(db)
