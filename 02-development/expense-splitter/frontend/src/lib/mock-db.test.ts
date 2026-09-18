import { beforeEach, describe, expect, it } from "vitest";
import { db } from "./mock-db";
import type { NewExpenseInput } from "./types";

// The mock store holds module-level state shared across tests, so every test
// signs in explicitly and builds its own group instead of relying on another
// test's leftovers — but it also inherits the seed fixtures (Lisbon trip,
// Apartment 4B, Dinner club, and their users), which a couple of tests assert
// against directly.

beforeEach(() => {
  db.signIn("mara@even.app");
});

describe("auth", () => {
  it("signs in by email and exposes the current user", () => {
    const user = db.signIn("theo@even.app");
    expect(user.name).toBe("Theo Lang");
    expect(db.currentUser()?.id).toBe(user.id);
  });

  it("signs up a brand new user and signs them in", () => {
    const user = db.signUp("Nadia Kahn", "nadia@even.app");
    expect(user.email).toBe("nadia@even.app");
    expect(db.currentUser()?.id).toBe(user.id);
  });

  it("signs out and clears the current user", () => {
    db.signOut();
    expect(db.currentUser()).toBeNull();
  });

  it("updates the signed-in user's profile", () => {
    const updated = db.updateProfile({ name: "Mara S." });
    expect(updated.name).toBe("Mara S.");
    expect(db.currentUser()?.name).toBe("Mara S.");
  });
});

describe("groups", () => {
  it("creates a group with the current user as sole admin", () => {
    const group = db.createGroup("Ski trip", "Feb weekend");
    expect(group.members).toHaveLength(1);
    expect(group.members[0]).toMatchObject({ role: "admin" });
    expect(db.groupsForCurrentUser().some((g) => g.id === group.id)).toBe(true);
  });

  it("only lists groups the current user belongs to", () => {
    const marasOnly = db.createGroup("Solo group", "");
    db.signIn("priya@even.app");
    const groups = db.groupsForCurrentUser();
    expect(groups.every((g) => g.members.some((m) => m.userId === "u_priya"))).toBe(true);
    expect(groups.some((g) => g.id === marasOnly.id)).toBe(false);
  });

  it("adds an existing user by email without duplicating membership", () => {
    const group = db.createGroup("Book club", "");
    db.addMember(group.id, "theo@even.app");
    db.addMember(group.id, "theo@even.app");
    const membershipCount = db.group(group.id)!.members.filter((m) => m.userId === "u_theo").length;
    expect(membershipCount).toBe(1);
  });

  it("adds a brand new user by email when none exists", () => {
    const group = db.createGroup("Book club", "");
    const updated = db.addMember(group.id, "wren@even.app");
    expect(updated.members.some((m) => m.name === "Wren")).toBe(true);
  });

  it("renames a group", () => {
    const group = db.createGroup("Temp name", "");
    const renamed = db.renameGroup(group.id, "Permanent name");
    expect(renamed.name).toBe("Permanent name");
  });
});

describe("expenses", () => {
  function twoPersonGroup() {
    const group = db.createGroup("Duo", "");
    db.addMember(group.id, "theo@even.app");
    return group;
  }

  it("adds an expense, computes shares, and logs activity", () => {
    const group = twoPersonGroup();
    const input: NewExpenseInput = {
      groupId: group.id,
      description: "Coffee",
      amountCents: 1000,
      date: "2026-01-01",
      category: "Food",
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1000 }],
      participantIds: ["u_mara", "u_theo"],
    };
    const expense = db.addExpense(input);
    expect(expense.shares).toEqual({ u_mara: 500, u_theo: 500 });

    const activity = db.activity(group.id);
    expect(activity[0]).toMatchObject({
      kind: "expense_added",
      summary: expect.stringContaining("Coffee"),
    });
  });

  it("edits an expense in place, preserving its id, and logs the edit", () => {
    const group = twoPersonGroup();
    const expense = db.addExpense({
      groupId: group.id,
      description: "Coffee",
      amountCents: 1000,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    const edited = db.editExpense(expense.id, {
      groupId: group.id,
      description: "Coffee and pastries",
      amountCents: 2000,
      date: "2026-01-02",
      category: "Food",
      splitType: "exact",
      payers: [{ userId: "u_mara", amountCents: 2000 }],
      participantIds: ["u_mara", "u_theo"],
      values: { u_mara: 1200, u_theo: 800 },
    });

    expect(edited.id).toBe(expense.id);
    expect(edited.description).toBe("Coffee and pastries");
    expect(edited.shares).toEqual({ u_mara: 1200, u_theo: 800 });
    expect(db.expenses(group.id)).toHaveLength(1);
    expect(db.activity(group.id)[0]).toMatchObject({ kind: "expense_edited" });
  });

  it("deletes an expense and logs the deletion", () => {
    const group = twoPersonGroup();
    const expense = db.addExpense({
      groupId: group.id,
      description: "One-off",
      amountCents: 500,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 500 }],
      participantIds: ["u_mara", "u_theo"],
    });
    db.deleteExpense(expense.id);
    expect(db.expenses(group.id)).toHaveLength(0);
    expect(db.activity(group.id)[0]).toMatchObject({ kind: "expense_deleted" });
  });
});

describe("balances, payments, and settlement", () => {
  it("computes net balances and a settlement plan that clears them", () => {
    const group = db.createGroup("Duo balances", "");
    db.addMember(group.id, "theo@even.app");
    db.addExpense({
      groupId: group.id,
      description: "Dinner",
      amountCents: 4000,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 4000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    const balances = db.balances(group.id);
    expect(balances.net["u_mara"]).toBe(2000);
    expect(balances.net["u_theo"]).toBe(-2000);
    expect(balances.settlement).toEqual([
      { fromUserId: "u_theo", toUserId: "u_mara", amountCents: 2000 },
    ]);
  });

  it("recording a payment updates balances to zero and appears in the feed", () => {
    const group = db.createGroup("Settle test", "");
    db.addMember(group.id, "theo@even.app");
    db.addExpense({
      groupId: group.id,
      description: "Groceries",
      amountCents: 2000,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 2000 }],
      participantIds: ["u_mara", "u_theo"],
    });
    db.recordPayment({
      groupId: group.id,
      fromUserId: "u_theo",
      toUserId: "u_mara",
      amountCents: 1000,
      date: "2026-01-02",
    });

    const balances = db.balances(group.id);
    expect(balances.net["u_mara"]).toBe(0);
    expect(balances.net["u_theo"]).toBe(0);
    expect(balances.settlement).toEqual([]);
    expect(db.activity(group.id)[0]).toMatchObject({ kind: "payment_recorded", amountCents: 1000 });
  });
});

describe("leaving and deleting a group", () => {
  it("refuses to let a member leave with a non-zero balance", () => {
    const group = db.createGroup("Leave test", "");
    db.addMember(group.id, "theo@even.app");
    db.addExpense({
      groupId: group.id,
      description: "Rent",
      amountCents: 1000,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    db.signIn("theo@even.app");
    expect(() => db.leaveGroup(group.id)).toThrow(/settle up/i);
    expect(db.group(group.id)!.members.some((m) => m.userId === "u_theo")).toBe(true);
  });

  it("lets a member leave once their balance is zero, and logs it", () => {
    const group = db.createGroup("Leave test 2", "");
    db.addMember(group.id, "theo@even.app");

    db.signIn("theo@even.app");
    db.leaveGroup(group.id);

    expect(db.group(group.id)!.members.some((m) => m.userId === "u_theo")).toBe(false);
    expect(db.activity(group.id)[0]).toMatchObject({ kind: "member_left", actorUserId: "u_theo" });
  });

  it("refuses to let a non-admin delete a group", () => {
    const group = db.createGroup("Admin-only delete", "");
    db.addMember(group.id, "theo@even.app");

    db.signIn("theo@even.app");
    expect(() => db.deleteGroup(group.id)).toThrow(/admin/i);
    expect(db.group(group.id)).not.toBeNull();
  });

  it("lets the admin delete a group and cascades its expenses, payments, and activity", () => {
    const group = db.createGroup("Admin delete", "");
    db.addMember(group.id, "theo@even.app");
    db.addExpense({
      groupId: group.id,
      description: "Something",
      amountCents: 100,
      date: "2026-01-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 100 }],
      participantIds: ["u_mara", "u_theo"],
    });

    db.deleteGroup(group.id);

    expect(db.group(group.id)).toBeNull();
    expect(db.expenses(group.id)).toHaveLength(0);
    expect(db.activity(group.id)).toHaveLength(0);
    expect(db.groupsForCurrentUser().some((g) => g.id === group.id)).toBe(false);
  });
});
