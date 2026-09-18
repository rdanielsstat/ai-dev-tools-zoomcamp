import { describe, expect, it } from "vitest";
import {
  computeSplit,
  distributeByWeights,
  formatCents,
  formatSigned,
  parseAmountToCents,
  simplifyDebts,
  type Transfer,
} from "./money";

function sumShares(shares: Record<string, number>): number {
  return Object.values(shares).reduce((a, b) => a + b, 0);
}

describe("formatCents / formatSigned", () => {
  it("formats whole and fractional cents with thousands separators", () => {
    expect(formatCents(0)).toBe("$0.00");
    expect(formatCents(5)).toBe("$0.05");
    expect(formatCents(128000)).toBe("$1,280.00");
    expect(formatCents(-1234)).toBe("−$12.34");
  });

  it("signs positive amounts with a leading plus and leaves zero unsigned", () => {
    expect(formatSigned(0)).toBe("$0.00");
    expect(formatSigned(500)).toBe("+$5.00");
    expect(formatSigned(-500)).toBe("−$5.00");
  });
});

describe("parseAmountToCents", () => {
  it("parses plain and comma-formatted decimal strings", () => {
    expect(parseAmountToCents("128")).toBe(12800);
    expect(parseAmountToCents("128.5")).toBe(12850);
    expect(parseAmountToCents("1,280.05")).toBe(128005);
    expect(parseAmountToCents("")).toBe(0);
    expect(parseAmountToCents("abc")).toBe(0);
  });
});

describe("distributeByWeights", () => {
  it("splits evenly divisible totals exactly", () => {
    expect(distributeByWeights(300, [1, 1, 1])).toEqual([100, 100, 100]);
  });

  it("distributes remainder cents so the sum always equals the total", () => {
    const out = distributeByWeights(100, [1, 1, 1]);
    expect(sumShares(Object.fromEntries(out.map((v, i) => [i, v])))).toBe(100);
    expect(out.filter((v) => v === 34)).toHaveLength(1);
    expect(out.filter((v) => v === 33)).toHaveLength(2);
  });

  it("weights proportionally and still reconciles exactly", () => {
    const out = distributeByWeights(1000, [2, 1, 1]);
    expect(out.reduce((a, b) => a + b, 0)).toBe(1000);
    expect(out[0]).toBeGreaterThan(out[1]!);
  });

  it("returns all zeros when weights sum to zero", () => {
    expect(distributeByWeights(500, [0, 0])).toEqual([0, 0]);
  });

  it("handles an empty weights list", () => {
    expect(distributeByWeights(500, [])).toEqual([]);
  });
});

describe("computeSplit: equal", () => {
  it("divides evenly with no remainder", () => {
    const { shares, error } = computeSplit({
      type: "equal",
      totalCents: 400,
      participantIds: ["a", "b", "c", "d"],
    });
    expect(error).toBeNull();
    expect(shares).toEqual({ a: 100, b: 100, c: 100, d: 100 });
  });

  it("distributes an odd remainder without losing or inventing cents", () => {
    const { shares, error } = computeSplit({
      type: "equal",
      totalCents: 100,
      participantIds: ["a", "b", "c"],
    });
    expect(error).toBeNull();
    expect(sumShares(shares)).toBe(100);
    expect(Object.values(shares).sort()).toEqual([33, 33, 34]);
  });

  it("errors when there are no participants", () => {
    const { error } = computeSplit({ type: "equal", totalCents: 100, participantIds: [] });
    expect(error).toMatch(/at least one participant/i);
  });
});

describe("computeSplit: exact", () => {
  it("accepts amounts that sum exactly to the total", () => {
    const { shares, error } = computeSplit({
      type: "exact",
      totalCents: 1000,
      participantIds: ["a", "b"],
      values: { a: 400, b: 600 },
    });
    expect(error).toBeNull();
    expect(shares).toEqual({ a: 400, b: 600 });
  });

  it("errors with the exact shortfall when amounts don't reconcile", () => {
    const { error } = computeSplit({
      type: "exact",
      totalCents: 1000,
      participantIds: ["a", "b"],
      values: { a: 400, b: 550 },
    });
    expect(error).toContain("$0.50");
  });
});

describe("computeSplit: percent", () => {
  it("splits proportionally to percentages and reconciles to the total", () => {
    const { shares, error } = computeSplit({
      type: "percent",
      totalCents: 2240,
      participantIds: ["a", "b", "c"],
      values: { a: 40, b: 30, c: 30 },
    });
    expect(error).toBeNull();
    expect(sumShares(shares)).toBe(2240);
  });

  it("flags percentages that don't sum to 100 while still reconciling the split", () => {
    const { shares, error } = computeSplit({
      type: "percent",
      totalCents: 1000,
      participantIds: ["a", "b"],
      values: { a: 40, b: 40 },
    });
    expect(error).toMatch(/100%/);
    expect(sumShares(shares)).toBe(1000);
  });
});

describe("computeSplit: shares", () => {
  it("divides in proportion to integer weights", () => {
    const { shares, error } = computeSplit({
      type: "shares",
      totalCents: 48000,
      participantIds: ["a", "b", "c", "d"],
      values: { a: 2, b: 1, c: 1, d: 1 },
    });
    expect(error).toBeNull();
    expect(shares["a"]).toBe(19200);
    expect(shares["b"]).toBe(9600);
    expect(sumShares(shares)).toBe(48000);
  });

  it("errors when no weight is assigned", () => {
    const { error } = computeSplit({
      type: "shares",
      totalCents: 1000,
      participantIds: ["a", "b"],
      values: { a: 0, b: 0 },
    });
    expect(error).toMatch(/at least one share/i);
  });
});

describe("computeSplit: itemized", () => {
  it("splits each item among its own participants and reconciles to the total", () => {
    const { shares, error } = computeSplit({
      type: "itemized",
      totalCents: 1000,
      participantIds: ["a", "b"],
      items: [
        { id: "1", label: "shared app", amountCents: 400, participantIds: ["a", "b"] },
        { id: "2", label: "a's entree", amountCents: 600, participantIds: ["a"] },
      ],
      extraCents: 0,
    });
    expect(error).toBeNull();
    expect(shares["a"]).toBe(800);
    expect(shares["b"]).toBe(200);
    expect(sumShares(shares)).toBe(1000);
  });

  it("distributes tax and tip proportionally to each person's item subtotal", () => {
    const { shares, error } = computeSplit({
      type: "itemized",
      totalCents: 1100,
      participantIds: ["a", "b"],
      items: [
        { id: "1", label: "a's meal", amountCents: 750, participantIds: ["a"] },
        { id: "2", label: "b's meal", amountCents: 250, participantIds: ["b"] },
      ],
      extraCents: 100,
    });
    expect(error).toBeNull();
    expect(sumShares(shares)).toBe(1100);
    expect(shares["a"]).toBe(825);
    expect(shares["b"]).toBe(275);
  });

  it("errors when items + extras don't reconcile to the stated total", () => {
    const { error } = computeSplit({
      type: "itemized",
      totalCents: 2000,
      participantIds: ["a"],
      items: [{ id: "1", label: "meal", amountCents: 1000, participantIds: ["a"] }],
      extraCents: 0,
    });
    expect(error).toMatch(/must sum to/i);
  });
});

describe("simplifyDebts", () => {
  const transferSum = (transfers: Transfer[]) => transfers.reduce((a, t) => a + t.amountCents, 0);

  it("produces no transfers when everyone is already even", () => {
    expect(simplifyDebts({ a: 0, b: 0 })).toEqual([]);
  });

  it("settles a simple two-person debt in one transfer", () => {
    const out = simplifyDebts({ a: 500, b: -500 });
    expect(out).toEqual([{ fromUserId: "b", toUserId: "a", amountCents: 500 }]);
  });

  it("never uses more than n-1 transactions for n members", () => {
    const balances = { a: 1000, b: 500, c: -300, d: -700, e: -500 };
    const out = simplifyDebts(balances);
    expect(out.length).toBeLessThanOrEqual(Object.keys(balances).length - 1);
  });

  it("fully clears every balance to zero", () => {
    const balances = { a: 1000, b: 500, c: -300, d: -700, e: -500 };
    const out = simplifyDebts(balances);
    const net: Record<string, number> = {};
    for (const k of Object.keys(balances)) net[k] = 0;
    for (const t of out) {
      net[t.fromUserId]! -= t.amountCents;
      net[t.toUserId]! += t.amountCents;
    }
    for (const k of Object.keys(balances)) {
      expect(net[k]).toBe(balances[k as keyof typeof balances]);
    }
  });

  it("moves the same total amount as the sum of positive balances", () => {
    const balances = { a: 1000, b: 500, c: -300, d: -700, e: -500 };
    const positiveSum = Object.values(balances)
      .filter((v) => v > 0)
      .reduce((a, b) => a + b, 0);
    expect(transferSum(simplifyDebts(balances))).toBe(positiveSum);
  });

  it("ignores members who are already at zero", () => {
    const out = simplifyDebts({ a: 500, b: 0, c: -500 });
    expect(out).toEqual([{ fromUserId: "c", toUserId: "a", amountCents: 500 }]);
  });
});
