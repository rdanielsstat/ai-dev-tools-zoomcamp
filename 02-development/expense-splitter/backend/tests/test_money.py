"""Unit tests for the split/settlement business logic — no HTTP involved.
Mirrors frontend/src/lib/money.test.ts so both implementations agree."""

from __future__ import annotations

from app.money import compute_split, distribute_by_weights, format_cents, simplify_debts
from app.schemas import ItemizedLine, SplitType


def sum_shares(shares: dict[str, int]) -> int:
    return sum(shares.values())


class TestFormatCents:
    def test_formats_whole_and_fractional_cents(self) -> None:
        assert format_cents(0) == "$0.00"
        assert format_cents(5) == "$0.05"
        assert format_cents(128000) == "$1,280.00"
        assert format_cents(-1234) == "-$12.34"


class TestDistributeByWeights:
    def test_splits_evenly_divisible_totals_exactly(self) -> None:
        assert distribute_by_weights(300, [1, 1, 1]) == [100, 100, 100]

    def test_distributes_remainder_so_sum_always_equals_total(self) -> None:
        out = distribute_by_weights(100, [1, 1, 1])
        assert sum(out) == 100
        assert sorted(out) == [33, 33, 34]

    def test_weights_proportionally_and_reconciles(self) -> None:
        out = distribute_by_weights(1000, [2, 1, 1])
        assert sum(out) == 1000
        assert out[0] > out[1]

    def test_returns_all_zeros_when_weights_sum_to_zero(self) -> None:
        assert distribute_by_weights(500, [0, 0]) == [0, 0]

    def test_handles_empty_weights(self) -> None:
        assert distribute_by_weights(500, []) == []


class TestComputeSplitEqual:
    def test_divides_evenly_with_no_remainder(self) -> None:
        shares, error = compute_split(SplitType.equal, 400, ["a", "b", "c", "d"])
        assert error is None
        assert shares == {"a": 100, "b": 100, "c": 100, "d": 100}

    def test_distributes_odd_remainder_without_losing_cents(self) -> None:
        shares, error = compute_split(SplitType.equal, 100, ["a", "b", "c"])
        assert error is None
        assert sum_shares(shares) == 100
        assert sorted(shares.values()) == [33, 33, 34]

    def test_errors_with_no_participants(self) -> None:
        _, error = compute_split(SplitType.equal, 100, [])
        assert error is not None
        assert "at least one participant" in error.lower()


class TestComputeSplitExact:
    def test_accepts_amounts_that_sum_exactly(self) -> None:
        shares, error = compute_split(SplitType.exact, 1000, ["a", "b"], values={"a": 400, "b": 600})
        assert error is None
        assert shares == {"a": 400, "b": 600}

    def test_errors_with_shortfall_when_amounts_dont_reconcile(self) -> None:
        _, error = compute_split(SplitType.exact, 1000, ["a", "b"], values={"a": 400, "b": 550})
        assert error is not None
        assert "$0.50" in error


class TestComputeSplitPercent:
    def test_splits_proportionally_and_reconciles(self) -> None:
        shares, error = compute_split(
            SplitType.percent, 2240, ["a", "b", "c"], values={"a": 40, "b": 30, "c": 30}
        )
        assert error is None
        assert sum_shares(shares) == 2240

    def test_flags_percentages_not_summing_to_100_but_still_reconciles(self) -> None:
        shares, error = compute_split(SplitType.percent, 1000, ["a", "b"], values={"a": 40, "b": 40})
        assert error is not None
        assert "100%" in error
        assert sum_shares(shares) == 1000


class TestComputeSplitShares:
    def test_divides_in_proportion_to_weights(self) -> None:
        shares, error = compute_split(
            SplitType.shares, 48000, ["a", "b", "c", "d"], values={"a": 2, "b": 1, "c": 1, "d": 1}
        )
        assert error is None
        assert shares["a"] == 19200
        assert shares["b"] == 9600
        assert sum_shares(shares) == 48000

    def test_errors_when_no_weight_assigned(self) -> None:
        _, error = compute_split(SplitType.shares, 1000, ["a", "b"], values={"a": 0, "b": 0})
        assert error is not None
        assert "at least one share" in error.lower()


class TestComputeSplitItemized:
    def test_splits_each_item_among_its_participants(self) -> None:
        items = [
            ItemizedLine(id="1", label="shared app", amount_cents=400, participant_ids=["a", "b"]),
            ItemizedLine(id="2", label="a's entree", amount_cents=600, participant_ids=["a"]),
        ]
        shares, error = compute_split(SplitType.itemized, 1000, ["a", "b"], items=items, extra_cents=0)
        assert error is None
        assert shares["a"] == 800
        assert shares["b"] == 200
        assert sum_shares(shares) == 1000

    def test_distributes_tax_and_tip_proportionally(self) -> None:
        items = [
            ItemizedLine(id="1", label="a's meal", amount_cents=750, participant_ids=["a"]),
            ItemizedLine(id="2", label="b's meal", amount_cents=250, participant_ids=["b"]),
        ]
        shares, error = compute_split(SplitType.itemized, 1100, ["a", "b"], items=items, extra_cents=100)
        assert error is None
        assert sum_shares(shares) == 1100
        assert shares["a"] == 825
        assert shares["b"] == 275

    def test_errors_when_items_plus_extras_dont_reconcile(self) -> None:
        items = [ItemizedLine(id="1", label="meal", amount_cents=1000, participant_ids=["a"])]
        _, error = compute_split(SplitType.itemized, 2000, ["a"], items=items, extra_cents=0)
        assert error is not None
        assert "must sum to" in error.lower()


class TestSimplifyDebts:
    def test_no_transfers_when_everyone_even(self) -> None:
        assert simplify_debts({"a": 0, "b": 0}) == []

    def test_settles_two_person_debt_in_one_transfer(self) -> None:
        out = simplify_debts({"a": 500, "b": -500})
        assert len(out) == 1
        assert out[0].from_user_id == "b"
        assert out[0].to_user_id == "a"
        assert out[0].amount_cents == 500

    def test_never_uses_more_than_n_minus_1_transactions(self) -> None:
        balances = {"a": 1000, "b": 500, "c": -300, "d": -700, "e": -500}
        out = simplify_debts(balances)
        assert len(out) <= len(balances) - 1

    def test_fully_clears_every_balance(self) -> None:
        balances = {"a": 1000, "b": 500, "c": -300, "d": -700, "e": -500}
        out = simplify_debts(balances)
        net = dict.fromkeys(balances, 0)
        for t in out:
            net[t.from_user_id] -= t.amount_cents
            net[t.to_user_id] += t.amount_cents
        assert net == balances

    def test_moves_total_amount_equal_to_sum_of_positive_balances(self) -> None:
        balances = {"a": 1000, "b": 500, "c": -300, "d": -700, "e": -500}
        positive_sum = sum(v for v in balances.values() if v > 0)
        out = simplify_debts(balances)
        assert sum(t.amount_cents for t in out) == positive_sum

    def test_ignores_members_already_at_zero(self) -> None:
        out = simplify_debts({"a": 500, "b": 0, "c": -500})
        assert len(out) == 1
        assert out[0].from_user_id == "c"
        assert out[0].to_user_id == "a"
        assert out[0].amount_cents == 500
