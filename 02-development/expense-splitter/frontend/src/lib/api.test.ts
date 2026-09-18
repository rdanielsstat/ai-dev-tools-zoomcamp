import { beforeEach, describe, expect, it } from "vitest";
import { api } from "./api";

// `api` is the ONLY module the UI is allowed to call (see api.ts). These
// tests exercise it the way the UI does — through its public async surface —
// as a stand-in for API endpoint tests until a real REST backend exists.

beforeEach(async () => {
  await api.signIn("mara@even.app", "unused");
});

describe("auth surface", () => {
  it("getCurrentUser reflects the signed-in user", async () => {
    const me = await api.getCurrentUser();
    expect(me?.email).toBe("mara@even.app");
  });

  it("signOut clears the session", async () => {
    await api.signOut();
    expect(await api.getCurrentUser()).toBeNull();
  });
});

describe("groups + expenses surface", () => {
  it("creates a group, adds an expense, and reflects it in balances", async () => {
    const group = await api.createGroup("Road trip", "");
    await api.addMember(group.id, "theo@even.app");
    await api.addExpense({
      groupId: group.id,
      description: "Gas",
      amountCents: 6000,
      date: "2026-02-01",
      category: "Transit",
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 6000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    const expenses = await api.listExpenses(group.id);
    expect(expenses).toHaveLength(1);

    const balances = await api.getBalances(group.id);
    expect(balances.net["u_mara"]).toBe(3000);
    expect(balances.settlement).toEqual([
      { fromUserId: "u_theo", toUserId: "u_mara", amountCents: 3000 },
    ]);
  });

  it("editExpense and deleteExpense round-trip through the service layer", async () => {
    const group = await api.createGroup("Edits", "");
    const expense = await api.addExpense({
      groupId: group.id,
      description: "Original",
      amountCents: 1000,
      date: "2026-02-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1000 }],
      participantIds: ["u_mara"],
    });

    const edited = await api.editExpense(expense.id, {
      groupId: group.id,
      description: "Updated",
      amountCents: 1500,
      date: "2026-02-02",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1500 }],
      participantIds: ["u_mara"],
    });
    expect(edited.description).toBe("Updated");

    await api.deleteExpense(expense.id);
    expect(await api.listExpenses(group.id)).toHaveLength(0);
  });

  it("markPaid via recordPayment clears a suggested settlement", async () => {
    const group = await api.createGroup("Settle via API", "");
    await api.addMember(group.id, "theo@even.app");
    await api.addExpense({
      groupId: group.id,
      description: "Hotel",
      amountCents: 2000,
      date: "2026-02-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 2000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    const before = await api.getBalances(group.id);
    const [payment] = before.settlement;
    await api.recordPayment({
      groupId: group.id,
      fromUserId: payment!.fromUserId,
      toUserId: payment!.toUserId,
      amountCents: payment!.amountCents,
      date: "2026-02-03",
    });

    const after = await api.getBalances(group.id);
    expect(after.settlement).toEqual([]);
    const activity = await api.listActivity(group.id);
    expect(activity[0]?.kind).toBe("payment_recorded");
  });

  it("leaveGroup rejects a non-zero balance and resolves once settled", async () => {
    const group = await api.createGroup("Leave via API", "");
    await api.addMember(group.id, "theo@even.app");
    await api.addExpense({
      groupId: group.id,
      description: "Split",
      amountCents: 1000,
      date: "2026-02-01",
      category: null,
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 1000 }],
      participantIds: ["u_mara", "u_theo"],
    });

    await api.signIn("theo@even.app", "unused");
    await expect(api.leaveGroup(group.id)).rejects.toThrow(/settle up/i);

    await api.recordPayment({
      groupId: group.id,
      fromUserId: "u_theo",
      toUserId: "u_mara",
      amountCents: 500,
      date: "2026-02-02",
    });
    await expect(api.leaveGroup(group.id)).resolves.toBeUndefined();
  });

  it("deleteGroup requires admin", async () => {
    const group = await api.createGroup("Delete via API", "");
    await api.addMember(group.id, "theo@even.app");

    await api.signIn("theo@even.app", "unused");
    await expect(api.deleteGroup(group.id)).rejects.toThrow(/admin/i);

    await api.signIn("mara@even.app", "unused");
    await expect(api.deleteGroup(group.id)).resolves.toBeUndefined();
    expect(await api.getGroup(group.id)).toBeNull();
  });
});
