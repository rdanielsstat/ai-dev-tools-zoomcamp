"""In-memory mock store standing in for the real database. Everything here
disappears on restart — swap this module for a real ORM-backed repository
later; routers only ever call methods on a Store instance, never touch
internal state directly, so the swap shouldn't require router changes."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from .errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from .money import compute_split, simplify_debts
from .schemas import (
    ActivityEvent,
    ActivityKind,
    Expense,
    Group,
    GroupBalances,
    Member,
    NewExpenseInput,
    NewPaymentInput,
    Payment,
    Role,
    Transfer,
    User,
)
from .security import hash_password, new_token, verify_password


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _today() -> date:
    return datetime.now(timezone.utc).date()


class Store:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self._password_hashes: dict[str, str] = {}
        self.tokens: dict[str, str] = {}  # token -> user_id
        self.groups: dict[str, Group] = {}
        self.expenses: dict[str, Expense] = {}
        self.payments: dict[str, Payment] = {}
        self.activity: list[ActivityEvent] = []

    # ---- auth ---------------------------------------------------------

    def sign_up(self, name: str, email: str, password: str) -> tuple[User, str]:
        email_lower = email.strip().lower()
        if any(u.email.lower() == email_lower for u in self.users.values()):
            raise ConflictError("An account with this email already exists.")
        initials = "".join(p[0] for p in name.split() if p)[:2].upper() or "EV"
        user = User(id=_new_id("u"), name=name, email=email, avatar_initials=initials)
        self.users[user.id] = user
        self._password_hashes[user.id] = hash_password(password)
        token = new_token()
        self.tokens[token] = user.id
        return user, token

    def log_in(self, email: str, password: str) -> tuple[User, str]:
        email_lower = email.strip().lower()
        user = next((u for u in self.users.values() if u.email.lower() == email_lower), None)
        if user is None or not verify_password(password, self._password_hashes[user.id]):
            from .errors import UnauthorizedError

            raise UnauthorizedError("Invalid email or password.")
        token = new_token()
        self.tokens[token] = user.id
        return user, token

    def log_out(self, token: str) -> None:
        self.tokens.pop(token, None)

    def user_for_token(self, token: str) -> User | None:
        user_id = self.tokens.get(token)
        return self.users.get(user_id) if user_id else None

    def update_profile(self, user_id: str, name: str | None, email: str | None) -> User:
        user = self.users[user_id]
        if email is not None:
            email_lower = email.strip().lower()
            taken = any(
                uid != user_id and u.email.lower() == email_lower for uid, u in self.users.items()
            )
            if taken:
                raise ConflictError("This email is already in use by another account.")
        updated = user.model_copy(
            update={"name": name if name is not None else user.name, "email": email or user.email}
        )
        self.users[user_id] = updated
        return updated

    # ---- groups ---------------------------------------------------------

    def groups_for_user(self, user_id: str) -> list[Group]:
        return [g for g in self.groups.values() if any(m.user_id == user_id for m in g.members)]

    def get_group(self, group_id: str) -> Group | None:
        return self.groups.get(group_id)

    def require_membership(self, group_id: str, user_id: str) -> Group:
        group = self.groups.get(group_id)
        if group is None or not any(m.user_id == user_id for m in group.members):
            raise NotFoundError("Group not found.")
        return group

    def create_group(self, user_id: str, name: str, description: str) -> Group:
        user = self.users[user_id]
        group = Group(
            id=_new_id("g"),
            name=name,
            description=description,
            created_by=user_id,
            created_at=_today(),
            members=[Member(user_id=user_id, name=user.name, avatar_initials=user.avatar_initials, role=Role.admin, joined_at=_today())],
        )
        self.groups[group.id] = group
        self._log(group.id, ActivityKind.group_created, user_id, f"created {name}")
        return group

    def rename_group(self, group_id: str, user_id: str, name: str) -> Group:
        group = self.require_membership(group_id, user_id)
        self._require_admin(group, user_id)
        updated = group.model_copy(update={"name": name})
        self.groups[group_id] = updated
        return updated

    def add_member(self, group_id: str, user_id: str, email: str) -> Group:
        group = self.require_membership(group_id, user_id)
        email_lower = email.strip().lower()
        member_user = next((u for u in self.users.values() if u.email.lower() == email_lower), None)
        if member_user is None:
            handle = email.split("@")[0] or "guest"
            member_user = User(
                id=_new_id("u"),
                name=handle[:1].upper() + handle[1:],
                email=email,
                avatar_initials=handle[:2].upper(),
            )
            self.users[member_user.id] = member_user
            self._password_hashes[member_user.id] = hash_password(new_token())

        if not any(m.user_id == member_user.id for m in group.members):
            new_members = [
                *group.members,
                Member(
                    user_id=member_user.id,
                    name=member_user.name,
                    avatar_initials=member_user.avatar_initials,
                    role=Role.member,
                    joined_at=_today(),
                ),
            ]
            group = group.model_copy(update={"members": new_members})
            self.groups[group_id] = group
            self._log(group_id, ActivityKind.member_joined, member_user.id, "joined the group")
        return group

    def leave_group(self, group_id: str, user_id: str) -> None:
        group = self.require_membership(group_id, user_id)
        net = self.get_balances(group_id, user_id).net.get(user_id, 0)
        if net != 0:
            raise BadRequestError("Settle up before leaving this group.")
        remaining = [m for m in group.members if m.user_id != user_id]
        self.groups[group_id] = group.model_copy(update={"members": remaining})
        self._log(group_id, ActivityKind.member_left, user_id, "left the group")

    def delete_group(self, group_id: str, user_id: str) -> None:
        group = self.require_membership(group_id, user_id)
        self._require_admin(group, user_id)
        del self.groups[group_id]
        for expense_id in [e.id for e in self.expenses.values() if e.group_id == group_id]:
            del self.expenses[expense_id]
        for payment_id in [p.id for p in self.payments.values() if p.group_id == group_id]:
            del self.payments[payment_id]
        self.activity = [a for a in self.activity if a.group_id != group_id]

    def _require_admin(self, group: Group, user_id: str) -> None:
        member = next((m for m in group.members if m.user_id == user_id), None)
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
        self.require_membership(group_id, user_id)
        items = [e for e in self.expenses.values() if e.group_id == group_id]
        if member_id:
            items = [
                e for e in items if any(p.user_id == member_id for p in e.payers) or member_id in e.shares
            ]
        if category:
            items = [e for e in items if e.category == category]
        if date_from:
            items = [e for e in items if e.date >= date_from]
        if date_to:
            items = [e for e in items if e.date <= date_to]
        return sorted(items, key=lambda e: e.date, reverse=True)

    def _build_expense(self, expense_id: str, input: NewExpenseInput, created_by: str) -> Expense:
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

        return Expense(
            id=expense_id,
            group_id=input.group_id,
            description=input.description,
            amount_cents=input.amount_cents,
            date=input.date,
            category=input.category,
            split_type=input.split_type,
            payers=input.payers,
            shares=shares,
            items=input.items,
            split_values=input.values,
            created_by=created_by,
        )

    def add_expense(self, group_id: str, user_id: str, input: NewExpenseInput) -> Expense:
        self.require_membership(group_id, user_id)
        expense = self._build_expense(_new_id("e"), input, user_id)
        self.expenses[expense.id] = expense
        self._log(group_id, ActivityKind.expense_added, user_id, f"added {expense.description}", expense.amount_cents)
        return expense

    def edit_expense(self, expense_id: str, user_id: str, input: NewExpenseInput) -> Expense:
        existing = self.expenses.get(expense_id)
        if existing is None:
            raise NotFoundError("Expense not found.")
        self.require_membership(existing.group_id, user_id)
        updated = self._build_expense(expense_id, input, existing.created_by)
        self.expenses[expense_id] = updated
        self._log(updated.group_id, ActivityKind.expense_edited, user_id, f"edited {updated.description}", updated.amount_cents)
        return updated

    def delete_expense(self, expense_id: str, user_id: str) -> None:
        existing = self.expenses.get(expense_id)
        if existing is None:
            raise NotFoundError("Expense not found.")
        self.require_membership(existing.group_id, user_id)
        del self.expenses[expense_id]
        self._log(existing.group_id, ActivityKind.expense_deleted, user_id, f"deleted {existing.description}", existing.amount_cents)

    # ---- balances, payments, settlement ------------------------------------

    def get_balances(self, group_id: str, user_id: str) -> GroupBalances:
        group = self.require_membership(group_id, user_id)
        net: dict[str, int] = {m.user_id: 0 for m in group.members}
        pair: dict[str, int] = {}

        def bump(frm: str, to: str, cents: int) -> None:
            if frm == to or cents == 0:
                return
            key = f"{frm}|{to}" if frm < to else f"{to}|{frm}"
            sign = 1 if frm < to else -1
            pair[key] = pair.get(key, 0) + sign * cents

        for expense in self.expenses.values():
            if expense.group_id != group_id:
                continue
            for payer in expense.payers:
                net[payer.user_id] = net.get(payer.user_id, 0) + payer.amount_cents
            for uid, cents in expense.shares.items():
                net[uid] = net.get(uid, 0) - cents
                for payer in expense.payers:
                    portion = round(cents * payer.amount_cents / expense.amount_cents)
                    bump(uid, payer.user_id, portion)

        for payment in self.payments.values():
            if payment.group_id != group_id:
                continue
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
        self.require_membership(group_id, user_id)
        return [p for p in self.payments.values() if p.group_id == group_id]

    def record_payment(self, group_id: str, user_id: str, input: NewPaymentInput) -> Payment:
        self.require_membership(group_id, user_id)
        payment = Payment(id=_new_id("p"), **input.model_dump(exclude={"group_id"}), group_id=group_id)
        self.payments[payment.id] = payment
        to_user = self.users.get(input.to_user_id)
        to_name = to_user.name.split()[0] if to_user else "member"
        self._log(group_id, ActivityKind.payment_recorded, input.from_user_id, f"recorded a payment to {to_name}", payment.amount_cents)
        return payment

    # ---- activity ---------------------------------------------------------

    def list_activity(self, group_id: str, user_id: str) -> list[ActivityEvent]:
        self.require_membership(group_id, user_id)
        return sorted(
            (a for a in self.activity if a.group_id == group_id),
            key=lambda a: a.at,
            reverse=True,
        )

    def _log(self, group_id: str, kind: ActivityKind, actor_user_id: str, summary: str, amount_cents: int | None = None) -> None:
        self.activity.append(
            ActivityEvent(
                id=_new_id("a"),
                group_id=group_id,
                kind=kind,
                actor_user_id=actor_user_id,
                summary=summary,
                amount_cents=amount_cents,
                at=datetime.now(timezone.utc),
            )
        )
