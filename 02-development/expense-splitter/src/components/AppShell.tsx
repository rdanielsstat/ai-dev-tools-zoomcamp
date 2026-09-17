import { Link } from "@tanstack/react-router";
import { useQueries, useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { balancesQuery, groupsQuery, meQuery } from "@/lib/queries";
import { formatSigned } from "@/lib/money";

export function AppShell({
  children,
  activeGroupId,
}: {
  children: ReactNode;
  activeGroupId?: string;
}) {
  const { data: me } = useQuery(meQuery);
  const { data: groups = [] } = useQuery(groupsQuery);
  const balances = useQueries({
    queries: groups.map((g) => balancesQuery(g.id)),
  });

  return (
    <div className="relative min-h-screen bg-surface text-ink">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 left-1/4 h-[420px] w-[420px] rounded-full bg-due/15 blur-[90px]" />
        <div className="absolute top-10 right-8 h-[380px] w-[380px] rounded-full bg-owe/10 blur-[100px]" />
        <div className="absolute bottom-0 left-10 h-[340px] w-[340px] rounded-full bg-due/10 blur-[90px]" />
      </div>

      <div className="relative mx-auto flex max-w-7xl flex-col lg:flex-row">
        <aside className="w-full shrink-0 border-b border-line/70 lg:w-72 lg:border-r lg:border-b-0 lg:border-line/70">
          <div className="glass2 sticky top-0 z-20 flex items-center gap-2 border-b border-line/60 px-5 py-4 ring-1 ring-black/5">
            <Link to="/" className="num text-[15px] font-semibold tracking-tight text-ink">
              Even
            </Link>
            <span className="ml-auto rounded-md bg-ink px-2 py-1 text-[10px] font-medium tracking-[0.12em] text-card uppercase">
              {groups.length} {groups.length === 1 ? "group" : "groups"}
            </span>
          </div>

          <nav className="p-3">
            <p className="label-eyebrow px-2 pt-1 pb-2">Your groups</p>
            {groups.map((group, i) => {
              const net = me ? (balances[i]?.data?.net[me.id] ?? 0) : 0;
              const active = group.id === activeGroupId;
              return (
                <Link
                  key={group.id}
                  to="/groups/$groupId"
                  params={{ groupId: group.id }}
                  className={`mb-1 flex items-center gap-3 rounded-lg px-3 py-2.5 ${
                    active ? "bg-card/70 ring-1 ring-black/5" : "hover:bg-card/60"
                  }`}
                >
                  <span
                    className={`num truncate text-[13px] ${active ? "font-semibold text-ink" : "font-medium text-ink2"}`}
                  >
                    {group.name}
                  </span>
                  <span
                    className={`num ml-auto shrink-0 text-[13px] ${
                      net > 0 ? "text-due" : net < 0 ? "text-owe" : "text-ink3"
                    }`}
                  >
                    {net === 0 ? "settled" : formatSigned(net)}
                  </span>
                </Link>
              );
            })}

            <Link
              to="/groups/new"
              className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2.5 text-[13px] font-medium text-ink2 hover:bg-card/60"
            >
              + New group
            </Link>

            <div className="mt-4 border-t border-line/60 pt-3">
              <Link
                to="/profile"
                className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-card/60"
              >
                <span className="num grid size-8 shrink-0 place-items-center rounded-full bg-card text-[11px] font-semibold text-ink2 ring-1 ring-black/5">
                  {me?.avatarInitials ?? "—"}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px] font-medium text-ink">
                    {me?.name ?? "Sign in"}
                  </span>
                  <span className="num block truncate text-[11px] text-ink3">
                    {me?.email ?? "no session"}
                  </span>
                </span>
              </Link>
            </div>
          </nav>
        </aside>

        <main className="min-w-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
