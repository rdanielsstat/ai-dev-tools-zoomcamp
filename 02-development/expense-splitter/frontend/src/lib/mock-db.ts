/**
 * In-memory mock store standing in for the real backend.
 * Everything here disappears when the real REST API lands — the API surface in
 * src/lib/api.ts is the only thing the UI touches.
 */
import { computeSplit, simplifyDebts } from "./money";
import type {
  ActivityEvent,
  Expense,
  Group,
  GroupBalances,
  NewExpenseInput,
  Payment,
  User,
} from "./types";

const id = (prefix: string) => `${prefix}_${Math.random().toString(36).slice(2, 9)}`;

const users: User[] = [
  { id: "u_mara", name: "Mara Silva", email: "mara@even.app", avatarInitials: "MA" },
  { id: "u_theo", name: "Theo Lang", email: "theo@even.app", avatarInitials: "TH" },
  { id: "u_priya", name: "Priya Rao", email: "priya@even.app", avatarInitials: "PR" },
  { id: "u_jonas", name: "Jonas Weber", email: "jonas@even.app", avatarInitials: "JO" },
];

let currentUserId: string | null = "u_mara";

const memberOf = (userId: string, role: "admin" | "member", joinedAt: string) => {
  const u = users.find((x) => x.id === userId)!;
  return { userId, name: u.name.split(" ")[0]!, avatarInitials: u.avatarInitials, role, joinedAt };
};

const groups: Group[] = [
  {
    id: "g_lisbon",
    name: "Lisbon trip",
    description: "Nov 12–16",
    createdBy: "u_mara",
    createdAt: "2026-11-10",
    members: [
      memberOf("u_mara", "admin", "2026-11-10"),
      memberOf("u_theo", "member", "2026-11-10"),
      memberOf("u_priya", "member", "2026-11-11"),
      memberOf("u_jonas", "member", "2026-11-12"),
    ],
  },
  {
    id: "g_apt",
    name: "Apartment 4B",
    description: "Ongoing household costs",
    createdBy: "u_theo",
    createdAt: "2026-01-04",
    members: [
      memberOf("u_theo", "admin", "2026-01-04"),
      memberOf("u_mara", "member", "2026-01-04"),
      memberOf("u_priya", "member", "2026-02-01"),
    ],
  },
  {
    id: "g_dinner",
    name: "Dinner club",
    description: "Monthly rotation",
    createdBy: "u_priya",
    createdAt: "2026-03-02",
    members: [
      memberOf("u_priya", "admin", "2026-03-02"),
      memberOf("u_mara", "member", "2026-03-02"),
    ],
  },
];

function buildExpense(input: NewExpenseInput, createdBy: string): Expense {
  const { shares } = computeSplit({
    type: input.splitType,
    totalCents: input.amountCents,
    participantIds: input.participantIds,
    values: input.values,
    items: input.items,
    extraCents: input.extraCents,
  });
  return {
    id: id("e"),
    groupId: input.groupId,
    description: input.description,
    amountCents: input.amountCents,
    date: input.date,
    category: input.category,
    splitType: input.splitType,
    payers: input.payers,
    shares,
    items: input.items,
    splitValues: input.values,
    createdBy,
  };
}

const expenses: Expense[] = [
  buildExpense(
    {
      groupId: "g_lisbon",
      description: "Fado dinner, Alfama",
      amountCents: 12800,
      date: "2026-11-14",
      category: "Food",
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 12800 }],
      participantIds: ["u_mara", "u_theo", "u_priya", "u_jonas"],
    },
    "u_mara",
  ),
  buildExpense(
    {
      groupId: "g_lisbon",
      description: "Airbnb, Bairro Alto",
      amountCents: 48000,
      date: "2026-11-12",
      category: "Lodging",
      splitType: "shares",
      payers: [{ userId: "u_mara", amountCents: 48000 }],
      participantIds: ["u_mara", "u_theo", "u_priya", "u_jonas"],
      values: { u_mara: 2, u_theo: 1, u_priya: 1, u_jonas: 1 },
    },
    "u_mara",
  ),
  buildExpense(
    {
      groupId: "g_lisbon",
      description: "Tram passes",
      amountCents: 3600,
      date: "2026-11-13",
      category: "Transit",
      splitType: "equal",
      payers: [{ userId: "u_jonas", amountCents: 3600 }],
      participantIds: ["u_mara", "u_theo", "u_priya", "u_jonas"],
    },
    "u_jonas",
  ),
  buildExpense(
    {
      groupId: "g_lisbon",
      description: "Pastéis & coffee",
      amountCents: 2240,
      date: "2026-11-15",
      category: "Food",
      splitType: "percent",
      payers: [{ userId: "u_theo", amountCents: 2240 }],
      participantIds: ["u_mara", "u_theo", "u_priya"],
      values: { u_mara: 40, u_theo: 30, u_priya: 30 },
    },
    "u_theo",
  ),
  buildExpense(
    {
      groupId: "g_apt",
      description: "November rent",
      amountCents: 210000,
      date: "2026-11-01",
      category: "Rent",
      splitType: "shares",
      payers: [{ userId: "u_theo", amountCents: 210000 }],
      participantIds: ["u_theo", "u_mara", "u_priya"],
      values: { u_theo: 2, u_mara: 1, u_priya: 1 },
    },
    "u_theo",
  ),
  buildExpense(
    {
      groupId: "g_apt",
      description: "Groceries run",
      amountCents: 8630,
      date: "2026-11-09",
      category: "Groceries",
      splitType: "equal",
      payers: [{ userId: "u_mara", amountCents: 8630 }],
      participantIds: ["u_theo", "u_mara", "u_priya"],
    },
    "u_mara",
  ),
  buildExpense(
    {
      groupId: "g_dinner",
      description: "Tasting menu",
      amountCents: 9000,
      date: "2026-10-21",
      category: "Food",
      splitType: "equal",
      payers: [{ userId: "u_priya", amountCents: 9000 }],
      participantIds: ["u_priya", "u_mara"],
    },
    "u_priya",
  ),
];

const payments: Payment[] = [
  {
    id: id("p"),
    groupId: "g_lisbon",
    fromUserId: "u_theo",
    toUserId: "u_priya",
    amountCents: 1000,
    date: "2026-11-15",
  },
  {
    id: id("p"),
    groupId: "g_dinner",
    fromUserId: "u_mara",
    toUserId: "u_priya",
    amountCents: 4500,
    date: "2026-10-22",
  },
];

const activity: ActivityEvent[] = [
  {
    id: id("a"),
    groupId: "g_lisbon",
    kind: "expense_added",
    actorUserId: "u_mara",
    summary: "added Fado dinner, Alfama",
    amountCents: 12800,
    at: "2026-11-14T20:10:00Z",
  },
  {
    id: id("a"),
    groupId: "g_lisbon",
    kind: "payment_recorded",
    actorUserId: "u_theo",
    summary: "recorded a payment to Priya",
    amountCents: 1000,
    at: "2026-11-15T09:30:00Z",
  },
  {
    id: id("a"),
    groupId: "g_lisbon",
    kind: "member_joined",
    actorUserId: "u_jonas",
    summary: "joined the group",
    at: "2026-11-12T08:00:00Z",
  },
  {
    id: id("a"),
    groupId: "g_apt",
    kind: "expense_added",
    actorUserId: "u_theo",
    summary: "added November rent",
    amountCents: 210000,
    at: "2026-11-01T07:00:00Z",
  },
];

function log(event: Omit<ActivityEvent, "id" | "at">) {
  activity.unshift({ ...event, id: id("a"), at: new Date().toISOString() });
}

export const db = {
  users: () => users,
  user: (userId: string) => users.find((u) => u.id === userId) ?? null,
  currentUser: () => (currentUserId ? (users.find((u) => u.id === currentUserId) ?? null) : null),
  signIn: (email: string) => {
    const found =
      users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase()) ?? users[0]!;
    currentUserId = found.id;
    return found;
  },
  signUp: (name: string, email: string) => {
    const initials = name
      .split(" ")
      .map((p) => p[0] ?? "")
      .join("")
      .slice(0, 2)
      .toUpperCase();
    const user: User = { id: id("u"), name, email, avatarInitials: initials || "EV" };
    users.push(user);
    currentUserId = user.id;
    return user;
  },
  signOut: () => {
    currentUserId = null;
  },
  updateProfile: (patch: { name?: string; email?: string }) => {
    const user = users.find((u) => u.id === currentUserId);
    if (!user) throw new Error("Not signed in");
    Object.assign(user, patch);
    return user;
  },

  groupsForCurrentUser: () =>
    groups.filter((g) => g.members.some((m) => m.userId === currentUserId)),
  group: (groupId: string) => groups.find((g) => g.id === groupId) ?? null,
  createGroup: (name: string, description: string) => {
    const uid = currentUserId!;
    const group: Group = {
      id: id("g"),
      name,
      description,
      createdBy: uid,
      createdAt: new Date().toISOString().slice(0, 10),
      members: [memberOf(uid, "admin", new Date().toISOString().slice(0, 10))],
    };
    groups.push(group);
    log({ groupId: group.id, kind: "group_created", actorUserId: uid, summary: `created ${name}` });
    return group;
  },
  renameGroup: (groupId: string, name: string) => {
    const group = groups.find((g) => g.id === groupId)!;
    group.name = name;
    return group;
  },
  addMember: (groupId: string, email: string) => {
    const group = groups.find((g) => g.id === groupId)!;
    let user = users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
    if (!user) {
      const handle = email.split("@")[0] ?? "guest";
      user = {
        id: id("u"),
        name: handle.charAt(0).toUpperCase() + handle.slice(1),
        email,
        avatarInitials: handle.slice(0, 2).toUpperCase(),
      };
      users.push(user);
    }
    if (!group.members.some((m) => m.userId === user!.id)) {
      group.members.push(memberOf(user.id, "member", new Date().toISOString().slice(0, 10)));
      log({
        groupId,
        kind: "member_joined",
        actorUserId: user.id,
        summary: "joined the group",
      });
    }
    return group;
  },
  leaveGroup: (groupId: string) => {
    const uid = currentUserId!;
    const group = groups.find((g) => g.id === groupId);
    if (!group) throw new Error("Group not found");
    const member = group.members.find((m) => m.userId === uid);
    if (!member) throw new Error("Not a member of this group");
    const net = db.balances(groupId).net[uid] ?? 0;
    if (net !== 0) throw new Error("Settle up before leaving this group.");
    group.members = group.members.filter((m) => m.userId !== uid);
    log({ groupId, kind: "member_left", actorUserId: uid, summary: "left the group" });
  },
  deleteGroup: (groupId: string) => {
    const uid = currentUserId!;
    const group = groups.find((g) => g.id === groupId);
    if (!group) throw new Error("Group not found");
    const member = group.members.find((m) => m.userId === uid);
    if (!member || member.role !== "admin") throw new Error("Only an admin can delete this group.");
    const idx = groups.findIndex((g) => g.id === groupId);
    groups.splice(idx, 1);
    for (let i = expenses.length - 1; i >= 0; i -= 1) {
      if (expenses[i]!.groupId === groupId) expenses.splice(i, 1);
    }
    for (let i = payments.length - 1; i >= 0; i -= 1) {
      if (payments[i]!.groupId === groupId) payments.splice(i, 1);
    }
    for (let i = activity.length - 1; i >= 0; i -= 1) {
      if (activity[i]!.groupId === groupId) activity.splice(i, 1);
    }
  },

  expenses: (groupId: string) =>
    [...expenses.filter((e) => e.groupId === groupId)].sort((a, b) => b.date.localeCompare(a.date)),
  addExpense: (input: NewExpenseInput) => {
    const uid = currentUserId!;
    const expense = buildExpense(input, uid);
    expenses.push(expense);
    log({
      groupId: input.groupId,
      kind: "expense_added",
      actorUserId: uid,
      summary: `added ${input.description}`,
      amountCents: input.amountCents,
    });
    return expense;
  },
  editExpense: (expenseId: string, input: NewExpenseInput) => {
    const idx = expenses.findIndex((e) => e.id === expenseId);
    if (idx < 0) throw new Error("Expense not found");
    const existing = expenses[idx]!;
    const updated = buildExpense(input, existing.createdBy);
    updated.id = existing.id;
    expenses[idx] = updated;
    log({
      groupId: updated.groupId,
      kind: "expense_edited",
      actorUserId: currentUserId!,
      summary: `edited ${updated.description}`,
      amountCents: updated.amountCents,
    });
    return updated;
  },
  deleteExpense: (expenseId: string) => {
    const idx = expenses.findIndex((e) => e.id === expenseId);
    if (idx < 0) return;
    const [removed] = expenses.splice(idx, 1);
    log({
      groupId: removed!.groupId,
      kind: "expense_deleted",
      actorUserId: currentUserId!,
      summary: `deleted ${removed!.description}`,
      amountCents: removed!.amountCents,
    });
  },

  payments: (groupId: string) => payments.filter((p) => p.groupId === groupId),
  recordPayment: (input: Omit<Payment, "id">) => {
    const payment: Payment = { ...input, id: id("p") };
    payments.push(payment);
    const to = users.find((u) => u.id === input.toUserId);
    log({
      groupId: input.groupId,
      kind: "payment_recorded",
      actorUserId: input.fromUserId,
      summary: `recorded a payment to ${to?.name.split(" ")[0] ?? "member"}`,
      amountCents: input.amountCents,
    });
    return payment;
  },

  activity: (groupId: string) =>
    [...activity.filter((a) => a.groupId === groupId)].sort((a, b) => b.at.localeCompare(a.at)),

  balances: (groupId: string): GroupBalances => {
    const group = groups.find((g) => g.id === groupId)!;
    const net: Record<string, number> = {};
    group.members.forEach((m) => (net[m.userId] = 0));
    const pair: Record<string, number> = {};

    const bump = (from: string, to: string, cents: number) => {
      if (from === to || cents === 0) return;
      const key = from < to ? `${from}|${to}` : `${to}|${from}`;
      const sign = from < to ? 1 : -1;
      pair[key] = (pair[key] ?? 0) + sign * cents;
    };

    for (const e of expenses.filter((x) => x.groupId === groupId)) {
      for (const p of e.payers) net[p.userId] = (net[p.userId] ?? 0) + p.amountCents;
      for (const [userId, cents] of Object.entries(e.shares)) {
        net[userId] = (net[userId] ?? 0) - cents;
        for (const p of e.payers) {
          const portion = Math.round((cents * p.amountCents) / e.amountCents);
          bump(userId, p.userId, portion);
        }
      }
    }
    for (const p of payments.filter((x) => x.groupId === groupId)) {
      net[p.fromUserId] = (net[p.fromUserId] ?? 0) + p.amountCents;
      net[p.toUserId] = (net[p.toUserId] ?? 0) - p.amountCents;
      bump(p.toUserId, p.fromUserId, p.amountCents);
    }

    const pairwise = Object.entries(pair)
      .filter(([, cents]) => cents !== 0)
      .map(([key, cents]) => {
        const [a, b] = key.split("|") as [string, string];
        return cents > 0
          ? { fromUserId: a, toUserId: b, amountCents: cents }
          : { fromUserId: b, toUserId: a, amountCents: -cents };
      })
      .sort((x, y) => y.amountCents - x.amountCents);

    return { net, pairwise, settlement: simplifyDebts(net) };
  },
};
