/**
 * Money + split math. All amounts are integer minor units (cents).
 * Never use floats for currency.
 */

export type SplitType = "equal" | "exact" | "percent" | "shares" | "itemized";

export const SPLIT_TYPES: { id: SplitType; label: string }[] = [
  { id: "equal", label: "Equal" },
  { id: "exact", label: "Exact" },
  { id: "percent", label: "Percent" },
  { id: "shares", label: "Shares" },
  { id: "itemized", label: "Itemized" },
];

export function formatCents(cents: number, currency = "$"): string {
  const sign = cents < 0 ? "−" : "";
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100).toLocaleString("en-US");
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${currency}${whole}.${frac}`;
}

export function formatSigned(cents: number, currency = "$"): string {
  if (cents === 0) return `${currency}0.00`;
  return cents > 0 ? `+${formatCents(cents, currency)}` : formatCents(cents, currency);
}

/** Parse a user-typed amount ("128", "128.5", "1,280.05") into cents. */
export function parseAmountToCents(input: string): number {
  const cleaned = input.replace(/[^0-9.]/g, "");
  if (!cleaned) return 0;
  const [whole, frac = ""] = cleaned.split(".");
  const cents = Number(whole || "0") * 100 + Number((frac + "00").slice(0, 2));
  return Number.isFinite(cents) ? cents : 0;
}

export function centsToInput(cents: number): string {
  return (cents / 100).toFixed(2);
}

/**
 * Distribute `total` cents across `weights` proportionally, giving leftover
 * cents to the first participants so the sum always equals `total` exactly.
 */
export function distributeByWeights(total: number, weights: number[]): number[] {
  const sum = weights.reduce((a, b) => a + b, 0);
  if (sum <= 0 || weights.length === 0) return weights.map(() => 0);
  const base = weights.map((w) => Math.floor((total * w) / sum));
  let remainder = total - base.reduce((a, b) => a + b, 0);
  // Give remaining cents out one at a time, largest fractional part first.
  const order = weights
    .map((w, i) => ({ i, frac: (total * w) / sum - base[i]! }))
    .sort((a, b) => b.frac - a.frac || a.i - b.i);
  let k = 0;
  while (remainder > 0) {
    base[order[k % order.length]!.i]! += 1;
    remainder -= 1;
    k += 1;
  }
  return base;
}

export interface ItemizedLine {
  id: string;
  label: string;
  amountCents: number;
  participantIds: string[];
}

export interface SplitInput {
  type: SplitType;
  totalCents: number;
  /** Participants included in the split. */
  participantIds: string[];
  /** Raw per-participant value: exact cents / percent points / share weights. */
  values?: Record<string, number> | undefined;
  /** Itemized only. */
  items?: ItemizedLine[] | undefined;
  /** Itemized only: tax + tip distributed proportionally to item subtotals. */
  extraCents?: number | undefined;
}

export interface SplitResult {
  shares: Record<string, number>;
  totalAssigned: number;
  /** Non-empty when the input can't be reconciled to the total. */
  error: string | null;
}

export function computeSplit(input: SplitInput): SplitResult {
  const { type, totalCents, participantIds, values = {}, items = [], extraCents = 0 } = input;
  const shares: Record<string, number> = {};
  participantIds.forEach((id) => (shares[id] = 0));

  if (participantIds.length === 0) {
    return { shares, totalAssigned: 0, error: "Pick at least one participant." };
  }

  if (type === "equal") {
    const amounts = distributeByWeights(
      totalCents,
      participantIds.map(() => 1),
    );
    participantIds.forEach((id, i) => (shares[id] = amounts[i]!));
    return { shares, totalAssigned: totalCents, error: null };
  }

  if (type === "exact") {
    let assigned = 0;
    participantIds.forEach((id) => {
      shares[id] = Math.round(values[id] ?? 0);
      assigned += shares[id]!;
    });
    return {
      shares,
      totalAssigned: assigned,
      error:
        assigned === totalCents
          ? null
          : `Exact amounts must sum to ${formatCents(totalCents)} (off by ${formatCents(totalCents - assigned)}).`,
    };
  }

  if (type === "percent") {
    const pct = participantIds.map((id) => values[id] ?? 0);
    const sum = pct.reduce((a, b) => a + b, 0);
    const amounts = distributeByWeights(totalCents, pct);
    participantIds.forEach((id, i) => (shares[id] = amounts[i]!));
    return {
      shares,
      totalAssigned: totalCents,
      error:
        Math.abs(sum - 100) < 0.001 ? null : `Percentages must sum to 100% (currently ${sum}%).`,
    };
  }

  if (type === "shares") {
    const weights = participantIds.map((id) => Math.max(0, values[id] ?? 0));
    const sum = weights.reduce((a, b) => a + b, 0);
    const amounts = distributeByWeights(totalCents, weights);
    participantIds.forEach((id, i) => (shares[id] = amounts[i]!));
    return {
      shares,
      totalAssigned: totalCents,
      error: sum > 0 ? null : "Assign at least one share.",
    };
  }

  // itemized: each line splits equally among its participants; tax/tip is
  // distributed in proportion to each person's item subtotal.
  const subtotals: Record<string, number> = {};
  participantIds.forEach((id) => (subtotals[id] = 0));
  let itemsTotal = 0;
  for (const item of items) {
    const people = item.participantIds.filter((id) => participantIds.includes(id));
    if (people.length === 0) continue;
    const amounts = distributeByWeights(
      item.amountCents,
      people.map(() => 1),
    );
    people.forEach((id, i) => (subtotals[id]! += amounts[i]!));
    itemsTotal += item.amountCents;
  }
  const extraAmounts = distributeByWeights(
    extraCents,
    participantIds.map((id) => subtotals[id] ?? 0),
  );
  participantIds.forEach((id, i) => (shares[id] = (subtotals[id] ?? 0) + extraAmounts[i]!));
  const assigned = participantIds.reduce((a, id) => a + shares[id]!, 0);
  return {
    shares,
    totalAssigned: assigned,
    error:
      assigned === totalCents
        ? null
        : `Items + tax/tip must sum to ${formatCents(totalCents)} (currently ${formatCents(assigned)}).`,
  };
}

export interface Transfer {
  fromUserId: string;
  toUserId: string;
  amountCents: number;
}

/**
 * Greedy debt simplification: largest debtor pays largest creditor until all
 * balances are zero. Produces at most n-1 transfers for n members.
 */
export function simplifyDebts(balances: Record<string, number>): Transfer[] {
  const creditors = Object.entries(balances)
    .filter(([, c]) => c > 0)
    .map(([userId, cents]) => ({ userId, cents }))
    .sort((a, b) => b.cents - a.cents);
  const debtors = Object.entries(balances)
    .filter(([, c]) => c < 0)
    .map(([userId, cents]) => ({ userId, cents: -cents }))
    .sort((a, b) => b.cents - a.cents);

  const transfers: Transfer[] = [];
  let i = 0;
  let j = 0;
  while (i < debtors.length && j < creditors.length) {
    const debtor = debtors[i]!;
    const creditor = creditors[j]!;
    const amount = Math.min(debtor.cents, creditor.cents);
    if (amount > 0) {
      transfers.push({ fromUserId: debtor.userId, toUserId: creditor.userId, amountCents: amount });
      debtor.cents -= amount;
      creditor.cents -= amount;
    }
    if (debtor.cents === 0) i += 1;
    if (creditor.cents === 0) j += 1;
  }
  return transfers;
}
