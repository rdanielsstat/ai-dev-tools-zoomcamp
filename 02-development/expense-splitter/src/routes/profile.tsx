import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Field, InkButton, Panel, QuietButton, TextInput } from "@/components/ledger";
import { api } from "@/lib/api";
import { meQuery } from "@/lib/queries";

export const Route = createFileRoute("/profile")({
  head: () => ({
    meta: [
      { title: "Your profile — Even" },
      { name: "description", content: "Update the name and email shown to your groups." },
      { property: "og:title", content: "Your profile — Even" },
      { property: "og:description", content: "Manage your Even account details." },
    ],
  }),
  component: Profile,
});

function Profile() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: me } = useQuery(meQuery);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    if (me) {
      setName(me.name);
      setEmail(me.email);
    }
  }, [me]);

  const update = useMutation({
    mutationFn: () => api.updateProfile({ name: name.trim(), email: email.trim() }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
  });

  const signOut = useMutation({
    mutationFn: () => api.signOut(),
    onSuccess: async () => {
      queryClient.clear();
      navigate({ to: "/auth" });
    },
  });

  return (
    <AppShell>
      <div className="glass sticky top-0 z-20 border-b border-line/60 px-5 py-4 ring-1 ring-black/5 sm:px-8">
        <h1 className="text-[22px] leading-tight font-semibold text-ink">Your profile</h1>
        <p className="text-sm text-ink3">This is what other members of your groups see.</p>
      </div>

      <div className="p-5 sm:p-8">
        <Panel title="Account" className="max-w-xl">
          <div className="space-y-4 p-5">
            <Field label="Name">
              <TextInput value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Email">
              <TextInput value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
            </Field>
            <div className="flex flex-wrap gap-2">
              <InkButton disabled={update.isPending || !me} onClick={() => update.mutate()}>
                {update.isPending ? "Saving…" : update.isSuccess ? "Saved" : "Save changes"}
              </InkButton>
              <QuietButton onClick={() => signOut.mutate()}>Sign out</QuietButton>
            </div>
          </div>
        </Panel>
      </div>
    </AppShell>
  );
}
