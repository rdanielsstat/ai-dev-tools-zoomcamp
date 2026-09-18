import { createFileRoute, Link } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";

import { AppShell } from "@/components/AppShell";
import { Panel } from "@/components/ledger";
import { balancesQuery, groupsQuery, meQuery } from "@/lib/queries";
import { formatCents, formatSigned } from "@/lib/money";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Your groups — Even" },
      {
        name: "description",
        content:
          "Every group you share costs with, and where you stand in each one: owed, owing, or settled.",
      },
      { property: "og:title", content: "Your groups — Even" },
      {
        property: "og:description",
        content: "See where you stand across every shared-expense group.",
      },
    ],
  }),
  component: GroupsOverview,
});

function GroupsOverview() {
  const { data: me } = useQuery(meQuery);
  const { data: groups = [], isPending } = useQuery(groupsQuery);
  const balances = useQueries({ queries: groups.map((g) => balancesQuery(g.id)) });

  const totalNet = me
    ? balances.reduce((a, b) => a + (b.data?.net[me.id] ?? 0), 0)
    : 0;

  return (
    <AppShell>
      <div className="glass sticky top-0 z-20 border-b border-line/60 px-5 py-4 ring-1 ring-black/5 sm:px-8">
        <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
          <div>
            <h1 className="text-[22px] leading-tight font-semibold text-ink text-balance">
              Your groups
            </h1>
            <p className="text-sm text-ink3 text-pretty">
              {me ? `Signed in as ${me.name}` : "No session"} · {groups.length} active
            </p>
          </div>
          <div className="ml-auto text-right">
            <p className="label-eyebrow">Across all groups</p>
            <p
              className={`num text-[26px] leading-none font-semibold ${
                totalNet > 0 ? "text-due" : totalNet < 0 ? "text-owe" : "text-ink3"
              }`}
            >
              {formatSigned(totalNet)}
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Link
            to="/groups/new"
            className="rounded-lg bg-ink px-3 py-2 text-sm font-medium text-card ring-1 ring-ink"
          >
            New group
          </Link>
          <Link
            to="/profile"
            className="rounded-lg bg-card px-3 py-2 text-sm font-medium text-ink2 ring-1 ring-black/5"
          >
            Profile
          </Link>
        </div>
      </div>

      <div className="grid gap-6 p-5 sm:p-8 lg:grid-cols-2">
        {isPending ? <p className="num text-[12px] text-ink3">Loading groups…</p> : null}
        {groups.map((group, i) => {
          const b = balances[i]?.data;
          const net = me ? (b?.net[me.id] ?? 0) : 0;
          return (
            <Link key={group.id} to="/groups/$groupId" params={{ groupId: group.id }}>
              <Panel className="h-full transition-transform hover:scale-[1.005]">
                <div className="flex items-start gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <h2 className="truncate text-[17px] font-semibold text-ink">{group.name}</h2>
                    <p className="num text-[11px] text-ink3">
                      {group.description} · {group.members.length} members
                    </p>
                  </div>
                  <div className="ml-auto shrink-0 text-right">
                    <p className="label-eyebrow">
                      {net > 0 ? "you are owed" : net < 0 ? "you owe" : "settled"}
                    </p>
                    <p
                      className={`num text-[18px] font-semibold ${
                        net > 0 ? "text-due" : net < 0 ? "text-owe" : "text-ink3"
                      }`}
                    >
                      {formatCents(Math.abs(net))}
                    </p>
                  </div>
                </div>
                <div className="border-t border-line/60 px-5 py-3">
                  <p className="num text-[11px] text-ink3">
                    {b ? `${b.settlement.length} payments clear this group` : "computing…"}
                  </p>
                </div>
              </Panel>
            </Link>
          );
        })}
      </div>
    </AppShell>
  );
}
