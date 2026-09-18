"""Money + split math. All amounts are integer minor units (cents). Never use
floats for currency. Port of frontend/src/lib/money.ts — keep both in sync."""

from __future__ import annotations

import math

from .schemas import ItemizedLine, SplitType, Transfer


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    abs_cents = abs(cents)
    whole = f"{abs_cents // 100:,}"
    frac = f"{abs_cents % 100:02d}"
    return f"{sign}${whole}.{frac}"


def distribute_by_weights(total: int, weights: list[float]) -> list[int]:
    """Distribute `total` cents across `weights` proportionally, giving
    leftover cents to the participants with the largest fractional remainder
    (ties broken by position) so the sum always equals `total` exactly."""
    if not weights:
        return []
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return [0 for _ in weights]

    base = [math.floor(total * w / weight_sum) for w in weights]
    remainder = total - sum(base)

    order = sorted(
        range(len(weights)),
        key=lambda i: (-(total * weights[i] / weight_sum - base[i]), i),
    )
    k = 0
    while remainder > 0:
        base[order[k % len(order)]] += 1
        remainder -= 1
        k += 1
    return base


def compute_split(
    split_type: SplitType,
    total_cents: int,
    participant_ids: list[str],
    values: dict[str, float] | None = None,
    items: list[ItemizedLine] | None = None,
    extra_cents: int = 0,
) -> tuple[dict[str, int], str | None]:
    values = values or {}
    items = items or []
    shares: dict[str, int] = dict.fromkeys(participant_ids, 0)

    if not participant_ids:
        return shares, "Pick at least one participant."

    if split_type == SplitType.equal:
        amounts = distribute_by_weights(total_cents, [1] * len(participant_ids))
        for pid, amount in zip(participant_ids, amounts, strict=True):
            shares[pid] = amount
        return shares, None

    if split_type == SplitType.exact:
        assigned = 0
        for pid in participant_ids:
            shares[pid] = round(values.get(pid, 0))
            assigned += shares[pid]
        error = None
        if assigned != total_cents:
            error = (
                f"Exact amounts must sum to {format_cents(total_cents)} "
                f"(off by {format_cents(total_cents - assigned)})."
            )
        return shares, error

    if split_type == SplitType.percent:
        pct = [values.get(pid, 0) for pid in participant_ids]
        total_pct = sum(pct)
        amounts = distribute_by_weights(total_cents, pct)
        for pid, amount in zip(participant_ids, amounts, strict=True):
            shares[pid] = amount
        error = None if abs(total_pct - 100) < 0.001 else f"Percentages must sum to 100% (currently {total_pct}%)."
        return shares, error

    if split_type == SplitType.shares:
        weights = [max(0, values.get(pid, 0)) for pid in participant_ids]
        total_weight = sum(weights)
        amounts = distribute_by_weights(total_cents, weights)
        for pid, amount in zip(participant_ids, amounts, strict=True):
            shares[pid] = amount
        error = None if total_weight > 0 else "Assign at least one share."
        return shares, error

    # itemized: each line splits equally among its own participants; tax/tip
    # is distributed in proportion to each person's item subtotal.
    subtotals: dict[str, int] = dict.fromkeys(participant_ids, 0)
    for item in items:
        people = [pid for pid in item.participant_ids if pid in participant_ids]
        if not people:
            continue
        amounts = distribute_by_weights(item.amount_cents, [1] * len(people))
        for pid, amount in zip(people, amounts, strict=True):
            subtotals[pid] += amount

    extra_amounts = distribute_by_weights(extra_cents, [subtotals.get(pid, 0) for pid in participant_ids])
    for pid, amount in zip(participant_ids, extra_amounts, strict=True):
        shares[pid] = subtotals.get(pid, 0) + amount

    assigned = sum(shares.values())
    error = None
    if assigned != total_cents:
        error = (
            f"Items + tax/tip must sum to {format_cents(total_cents)} "
            f"(currently {format_cents(assigned)})."
        )
    return shares, error


def simplify_debts(balances: dict[str, int]) -> list[Transfer]:
    """Greedy debt simplification: largest debtor pays largest creditor until
    all balances are zero. Produces at most n-1 transfers for n members."""
    creditors = sorted(
        ([uid, cents] for uid, cents in balances.items() if cents > 0),
        key=lambda pair: -pair[1],
    )
    debtors = sorted(
        ([uid, -cents] for uid, cents in balances.items() if cents < 0),
        key=lambda pair: -pair[1],
    )

    transfers: list[Transfer] = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        debtor = debtors[i]
        creditor = creditors[j]
        amount = min(debtor[1], creditor[1])
        if amount > 0:
            transfers.append(Transfer(from_user_id=debtor[0], to_user_id=creditor[0], amount_cents=amount))
            debtor[1] -= amount
            creditor[1] -= amount
        if debtor[1] == 0:
            i += 1
        if creditor[1] == 0:
            j += 1
    return transfers
