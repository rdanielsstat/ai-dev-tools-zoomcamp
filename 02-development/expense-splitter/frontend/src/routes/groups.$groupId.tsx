import { createFileRoute, notFound, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { ExpenseForm, NewExpensePanel } from "@/components/NewExpensePanel";
import { InkButton, Loading, Panel, QuietButton } from "@/components/ledger";
import { api } from "@/lib/api";
import { requireAuth } from "@/lib/auth-guard";
import { activityQuery, balancesQuery, expensesQuery, groupQuery, meQuery } from "@/lib/queries";
import { SPLIT_TYPES, formatCents, formatSigned } from "@/lib/money";
import type { Expense, Group } from "@/lib/types";

export const Route = createFileRoute("/groups/$groupId")({
  beforeLoad: ({ context }) => requireAuth(context.queryClient),
  loader: async ({ params, context }) => {
    const group = await context.queryClient.ensureQueryData(groupQuery(params.groupId));
    if (!group) throw notFound();
    return { group };
  },
  head: ({ loaderData }) => {
    const name = loaderData?.group.name;
    if (!name) {
      return {
        meta: [{ title: "Group unavailable — Even" }, { name: "robots", content: "noindex" }],
      };
    }
    const title = `${name} — Even`;
    const description = `Balances, expenses and the smallest set of payments that clears ${name}.`;
    return {
      meta: [
        { title },
        { name: "description", content: description },
        { property: "og:title", content: title },
        { property: "og:description", content: description },
      ],
    };
  },
  component: GroupDetail,
  errorComponent: () => (
    <AppShell>
      <p className="num p-8 text-[12px] text-owe">This group didn't load. Try again.</p>
    </AppShell>
  ),
  notFoundComponent: () => (
    <AppShell>
      <p className="num p-8 text-[12px] text-ink3">Group not found.</p>
    </AppShell>
  ),
});

function GroupDetail() {
  const { groupId } = Route.useParams();
  const { group } = Route.useLoaderData();
  const { data: me } = useQuery(meQuery);
  const { data: balances } = useQuery(balancesQuery(groupId));
  const { data: expenses = [] } = useQuery(expensesQuery(groupId));
  const { data: activity = [] } = useQuery(activityQuery(groupId));
  const [showRaw, setShowRaw] = useState(false);
  const [filterMember, setFilterMember] = useState("all");
  const [filterCategory, setFilterCategory] = useState("all");
  const [filterFrom, setFilterFrom] = useState("");
  const [filterTo, setFilterTo] = useState("");
  const [editingExpenseId, setEditingExpenseId] = useState<string | null>(null);

  const name = (userId: string) =>
    group.members.find((m) => m.userId === userId)?.name ?? (userId === me?.id ? "You" : "member");

  const myNet = me ? (balances?.net[me.id] ?? 0) : 0;
  const maxAbs = useMemo(
    () => Math.max(1, ...Object.values(balances?.net ?? {}).map((c) => Math.abs(c))),
    [balances],
  );

  const categories = useMemo(
    () =>
      Array.from(new Set(expenses.map((e) => e.category).filter((c): c is string => !!c))).sort(),
    [expenses],
  );

  const visibleExpenses = expenses.filter(
    (e) =>
      (filterMember === "all" ||
        e.payers.some((p) => p.userId === filterMember) ||
        Object.keys(e.shares).includes(filterMember)) &&
      (filterCategory === "all" || e.category === filterCategory) &&
      (!filterFrom || e.date >= filterFrom) &&
      (!filterTo || e.date <= filterTo),
  );

  return (
    <AppShell activeGroupId={groupId}>
      <div className="glass sticky top-0 z-20 border-b border-line/60 px-5 py-4 ring-1 ring-black/5 sm:px-8">
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
          <div className="min-w-0">
            <h1 className="truncate text-[22px] leading-tight font-semibold text-ink">
              {group.name}
            </h1>
            <p className="text-sm text-ink3 text-pretty">
              {group.description} · {group.members.length} members · {expenses.length} expenses
            </p>
          </div>
          <div className="ml-auto text-right">
            <p className="label-eyebrow">
              {myNet > 0 ? "You are owed" : myNet < 0 ? "You owe" : "You're even"}
            </p>
            <p
              className={`num text-[26px] leading-none font-semibold ${
                myNet > 0 ? "text-due" : myNet < 0 ? "text-owe" : "text-ink3"
              }`}
            >
              {formatSigned(myNet)}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <a
            href="#new-expense"
            className="rounded-lg bg-ink px-3 py-2 text-sm font-medium text-card ring-1 ring-ink"
          >
            Add expense
          </a>
          <a
            href="#settle-up"
            className="rounded-lg bg-card px-3 py-2 text-sm font-medium text-ink2 ring-1 ring-black/5"
          >
            Settle up
          </a>
          <InviteMember group={group} />
          <LeaveGroup group={group} myUserId={me?.id} myNet={myNet} />
          {me && group.members.find((m) => m.userId === me.id)?.role === "admin" ? (
            <DeleteGroup group={group} />
          ) : null}
        </div>
      </div>

      <div className="grid gap-6 p-5 sm:p-8 lg:grid-cols-3">
        <section className="space-y-6 lg:col-span-2">
          <Panel
            title="Net balances · scale to level"
            aside={
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                className="num text-[11px] text-ink3 underline decoration-line"
              >
                {showRaw ? "hide raw IOUs" : "show raw IOUs"}
              </button>
            }
          >
            {!balances ? (
              <Loading label="Computing balances" />
            ) : (
              <div className="divide-y divide-line/60">
                {group.members.map((m, i) => {
                  const net = balances.net[m.userId] ?? 0;
                  const width = `${Math.round((Math.abs(net) / maxAbs) * 100)}%`;
                  return (
                    <div
                      key={m.userId}
                      className="settle flex items-center gap-3 px-5 py-3"
                      style={{ animationDelay: `${i * 0.06}s` }}
                    >
                      <span className="num w-24 shrink-0 truncate text-[13px] font-medium">
                        {m.name}
                      </span>
                      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-line/60">
                        {net >= 0 ? (
                          <div
                            className="absolute top-0 left-1/2 h-full -translate-x-full rounded-r-full bg-due/70"
                            style={{ width }}
                          />
                        ) : (
                          <div
                            className="absolute top-0 left-1/2 h-full rounded-l-full bg-owe/70"
                            style={{ width }}
                          />
                        )}
                        <div className="absolute top-1/2 left-1/2 h-3 w-px -translate-y-1/2 bg-ink3/50" />
                      </div>
                      <span
                        className={`num w-20 text-right text-[13px] font-medium ${
                          net > 0 ? "text-due" : net < 0 ? "text-owe" : "text-ink3"
                        }`}
                      >
                        {formatSigned(net)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
            {showRaw && balances ? (
              <div className="border-t border-line/60 bg-card/50 px-5 py-3">
                <p className="label-eyebrow">Raw pairwise balances</p>
                <div className="mt-2 space-y-1">
                  {balances.pairwise.length === 0 ? (
                    <p className="num text-[12px] text-ink3">Nothing outstanding.</p>
                  ) : (
                    balances.pairwise.map((p, i) => (
                      <p key={i} className="num text-[12px] text-ink2">
                        {name(p.fromUserId)} owes {name(p.toUserId)}{" "}
                        <span className="font-medium text-ink">{formatCents(p.amountCents)}</span>
                      </p>
                    ))
                  )}
                </div>
              </div>
            ) : null}
          </Panel>

          <div id="settle-up">
            <SettlementPlan groupId={groupId} nameOf={name} />
          </div>

          <Panel
            title="Expenses"
            aside={
              <div className="flex flex-wrap items-center gap-1.5">
                <select
                  value={filterMember}
                  onChange={(e) => setFilterMember(e.target.value)}
                  className="num rounded-md bg-card px-2 py-1 text-[11px] text-ink2 ring-1 ring-black/5 outline-none"
                >
                  <option value="all">all members</option>
                  {group.members.map((m) => (
                    <option key={m.userId} value={m.userId}>
                      {m.name}
                    </option>
                  ))}
                </select>
                <select
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                  className="num rounded-md bg-card px-2 py-1 text-[11px] text-ink2 ring-1 ring-black/5 outline-none"
                >
                  <option value="all">all categories</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={filterFrom}
                  onChange={(e) => setFilterFrom(e.target.value)}
                  className="num rounded-md bg-card px-2 py-1 text-[11px] text-ink2 ring-1 ring-black/5 outline-none"
                />
                <input
                  type="date"
                  value={filterTo}
                  onChange={(e) => setFilterTo(e.target.value)}
                  className="num rounded-md bg-card px-2 py-1 text-[11px] text-ink2 ring-1 ring-black/5 outline-none"
                />
              </div>
            }
          >
            <div className="divide-y divide-line/60">
              {visibleExpenses.length === 0 ? (
                <p className="num px-5 py-6 text-[12px] text-ink3">
                  No expenses match these filters.
                </p>
              ) : (
                visibleExpenses.map((e) =>
                  editingExpenseId === e.id ? (
                    <div key={e.id} className="border-b border-line/60 last:border-0">
                      <ExpenseForm
                        groupId={groupId}
                        members={group.members}
                        editing={e}
                        onSaved={() => setEditingExpenseId(null)}
                        onCancel={() => setEditingExpenseId(null)}
                      />
                    </div>
                  ) : (
                    <div key={e.id} className="flex items-center gap-3 px-5 py-3.5">
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-ink">{e.description}</p>
                        <p className="num text-[11px] text-ink3">
                          {e.date} · {SPLIT_TYPES.find((t) => t.id === e.splitType)?.label} ·{" "}
                          {e.payers.map((p) => name(p.userId)).join(" + ")} paid
                          {e.category ? ` · ${e.category}` : ""}
                        </p>
                      </div>
                      <span className="num ml-auto shrink-0 text-[14px] font-semibold text-ink">
                        {formatCents(e.amountCents)}
                      </span>
                      <button
                        type="button"
                        onClick={() => setEditingExpenseId(e.id)}
                        className="num ml-2 shrink-0 text-[11px] text-ink3 underline decoration-line hover:text-ink"
                      >
                        edit
                      </button>
                      <DeleteExpense expenseId={e.id} groupId={groupId} />
                    </div>
                  ),
                )
              )}
            </div>
          </Panel>
        </section>

        <section className="space-y-6">
          <div id="new-expense">
            <NewExpensePanel groupId={groupId} members={group.members} />
          </div>

          <Panel title="Activity">
            <div className="divide-y divide-line/60 text-sm">
              {activity.length === 0 ? (
                <p className="num px-5 py-6 text-[12px] text-ink3">Nothing yet.</p>
              ) : (
                activity.map((a) => (
                  <div key={a.id} className="px-5 py-3">
                    <p className="text-ink2 text-pretty">
                      <span className="font-medium text-ink">{name(a.actorUserId)}</span>{" "}
                      {a.summary}
                      {a.amountCents ? (
                        <span className="num"> {formatCents(a.amountCents)}</span>
                      ) : null}
                    </p>
                    <p className="num mt-0.5 text-[11px] text-ink3">
                      {new Date(a.at).toLocaleString("en-US", {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </p>
                  </div>
                ))
              )}
            </div>
          </Panel>
        </section>
      </div>
    </AppShell>
  );
}

function SettlementPlan({
  groupId,
  nameOf,
}: {
  groupId: string;
  nameOf: (userId: string) => string;
}) {
  const queryClient = useQueryClient();
  const { data: balances } = useQuery(balancesQuery(groupId));
  const settlement = balances?.settlement ?? [];
  const total = settlement.reduce((a, t) => a + t.amountCents, 0);

  const markPaid = useMutation({
    mutationFn: (t: { fromUserId: string; toUserId: string; amountCents: number }) =>
      api.recordPayment({
        groupId,
        fromUserId: t.fromUserId,
        toUserId: t.toUserId,
        amountCents: t.amountCents,
        date: new Date().toISOString().slice(0, 10),
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["balances", groupId] }),
        queryClient.invalidateQueries({ queryKey: ["activity", groupId] }),
      ]);
    },
  });

  return (
    <Panel
      title="Settle up · smallest set of payments"
      aside={
        <span className="num text-[11px] text-ink3">
          {settlement.length} {settlement.length === 1 ? "payment" : "payments"} ·{" "}
          {formatCents(total)}
        </span>
      }
    >
      <div className="divide-y divide-line/60">
        {settlement.length === 0 ? (
          <p className="num px-5 py-6 text-[12px] text-ink3">
            Everyone is even. Nothing to settle.
          </p>
        ) : (
          settlement.map((t, i) => (
            <div key={i} className="flex items-center gap-3 px-5 py-3.5">
              <span className="num w-16 shrink-0 truncate text-[13px] font-medium text-ink2">
                {nameOf(t.fromUserId)}
              </span>
              <span className="num shrink-0 text-ink3">→</span>
              <span className="num w-16 shrink-0 truncate text-[13px] font-medium text-ink2">
                {nameOf(t.toUserId)}
              </span>
              <span className="num ml-auto text-[14px] font-semibold text-ink">
                {formatCents(t.amountCents)}
              </span>
              {i === 0 ? (
                <InkButton
                  className="ml-3 px-3 py-1.5 text-[12px]"
                  disabled={markPaid.isPending}
                  onClick={() => markPaid.mutate(t)}
                >
                  Mark paid
                </InkButton>
              ) : (
                <QuietButton
                  className="ml-3 px-3 py-1.5 text-[12px]"
                  disabled={markPaid.isPending}
                  onClick={() => markPaid.mutate(t)}
                >
                  Mark paid
                </QuietButton>
              )}
            </div>
          ))
        )}
      </div>
    </Panel>
  );
}

function DeleteExpense({ expenseId, groupId }: { expenseId: string; groupId: string }) {
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: () => api.deleteExpense(expenseId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["expenses", groupId] }),
        queryClient.invalidateQueries({ queryKey: ["balances", groupId] }),
        queryClient.invalidateQueries({ queryKey: ["activity", groupId] }),
      ]);
    },
  });
  return (
    <button
      type="button"
      onClick={() => remove.mutate()}
      disabled={remove.isPending}
      className="num ml-2 shrink-0 text-[11px] text-ink3 underline decoration-line hover:text-owe"
    >
      delete
    </button>
  );
}

function InviteMember({ group }: { group: Group }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const invite = useMutation({
    mutationFn: () => api.addMember(group.id, email.trim()),
    onSuccess: async () => {
      setEmail("");
      setOpen(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["group", group.id] }),
        queryClient.invalidateQueries({ queryKey: ["activity", group.id] }),
      ]);
    },
  });

  if (!open) {
    return <QuietButton onClick={() => setOpen(true)}>Invite member</QuietButton>;
  }
  return (
    <div className="flex items-center gap-2">
      <input
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="name@email.com"
        className="num rounded-lg bg-card px-3 py-2 text-[12px] text-ink ring-1 ring-black/5 outline-none"
      />
      <InkButton
        className="py-2 text-[12px]"
        disabled={!email.trim() || invite.isPending}
        onClick={() => invite.mutate()}
      >
        Add
      </InkButton>
    </div>
  );
}

function LeaveGroup({
  group,
  myUserId,
  myNet,
}: {
  group: Group;
  myUserId: string | undefined;
  myNet: number;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const leave = useMutation({
    mutationFn: () => api.leaveGroup(group.id),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["group", group.id] });
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
      navigate({ to: "/" });
    },
  });

  if (!myUserId || !group.members.some((m) => m.userId === myUserId)) return null;
  const canLeave = myNet === 0;

  return (
    <div className="flex items-center gap-2">
      <QuietButton
        disabled={!canLeave || leave.isPending}
        onClick={() => leave.mutate()}
        title={canLeave ? undefined : "Settle up before leaving this group."}
      >
        {leave.isPending ? "Leaving…" : "Leave group"}
      </QuietButton>
      {leave.isError ? (
        <span className="num text-[11px] text-owe">{(leave.error as Error).message}</span>
      ) : null}
    </div>
  );
}

function DeleteGroup({ group }: { group: Group }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const del = useMutation({
    mutationFn: () => api.deleteGroup(group.id),
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: ["group", group.id] });
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
      navigate({ to: "/" });
    },
  });

  if (!confirming) {
    return (
      <QuietButton onClick={() => setConfirming(true)} className="text-owe">
        Delete group
      </QuietButton>
    );
  }
  return (
    <div className="flex items-center gap-2">
      <span className="num text-[11px] text-ink3">Delete “{group.name}” for everyone?</span>
      <InkButton className="py-2 text-[12px]" disabled={del.isPending} onClick={() => del.mutate()}>
        {del.isPending ? "Deleting…" : "Confirm"}
      </InkButton>
      <QuietButton
        className="py-2 text-[12px]"
        disabled={del.isPending}
        onClick={() => setConfirming(false)}
      >
        Cancel
      </QuietButton>
    </div>
  );
}
