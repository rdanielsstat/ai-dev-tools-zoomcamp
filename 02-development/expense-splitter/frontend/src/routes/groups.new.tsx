import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Field, InkButton, Panel, TextInput } from "@/components/ledger";
import { api } from "@/lib/api";
import { requireAuth } from "@/lib/auth-guard";

export const Route = createFileRoute("/groups/new")({
  beforeLoad: ({ context }) => requireAuth(context.queryClient),
  head: () => ({
    meta: [
      { title: "New group — Even" },
      { name: "description", content: "Start a group for a trip, a household, or a dinner club." },
      { property: "og:title", content: "New group — Even" },
      { property: "og:description", content: "Start a new shared-expense group in Even." },
    ],
  }),
  component: NewGroup,
});

function NewGroup() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [emails, setEmails] = useState("");

  const create = useMutation({
    mutationFn: async () => {
      const group = await api.createGroup(name.trim(), description.trim());
      for (const email of emails
        .split(/[\n,]/)
        .map((e) => e.trim())
        .filter(Boolean)) {
        await api.addMember(group.id, email);
      }
      return group;
    },
    onSuccess: async (group) => {
      await queryClient.invalidateQueries({ queryKey: ["groups"] });
      navigate({ to: "/groups/$groupId", params: { groupId: group.id } });
    },
  });

  return (
    <AppShell>
      <div className="glass sticky top-0 z-20 border-b border-line/60 px-5 py-4 ring-1 ring-black/5 sm:px-8">
        <h1 className="text-[22px] leading-tight font-semibold text-ink">New group</h1>
        <p className="text-sm text-ink3">A trip, a household, a dinner club — anything shared.</p>
      </div>

      <div className="p-5 sm:p-8">
        <Panel title="Group details" className="max-w-xl">
          <div className="space-y-4 p-5">
            <Field label="Name">
              <TextInput
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Lisbon trip"
              />
            </Field>
            <Field label="Description">
              <TextInput
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Nov 12–16"
              />
            </Field>
            <Field label="Invite by email (one per line)">
              <textarea
                value={emails}
                onChange={(e) => setEmails(e.target.value)}
                rows={3}
                placeholder="theo@even.app"
                className="mt-1 w-full rounded-lg bg-card px-3 py-2 text-sm text-ink ring-1 ring-black/5 outline-none focus:ring-2 focus:ring-ink/20"
              />
            </Field>
            <InkButton
              className="w-full py-2.5"
              disabled={!name.trim() || create.isPending}
              onClick={() => create.mutate()}
            >
              {create.isPending ? "Creating…" : "Create group"}
            </InkButton>
          </div>
        </Panel>
      </div>
    </AppShell>
  );
}
