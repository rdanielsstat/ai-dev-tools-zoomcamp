import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Field, InkButton, Panel, TextInput } from "@/components/ledger";
import { api } from "@/lib/api";

export const Route = createFileRoute("/auth")({
  head: () => ({
    meta: [
      { title: "Sign in — Even" },
      {
        name: "description",
        content: "Sign in to Even to track shared expenses and settle up with your group.",
      },
      { property: "og:title", content: "Sign in — Even" },
      { property: "og:description", content: "Sign in or create an Even account." },
    ],
  }),
  component: AuthPage,
});

function AuthPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("mara@even.app");
  const [password, setPassword] = useState("");

  const submit = useMutation({
    mutationFn: () =>
      mode === "signin"
        ? api.signIn(email.trim(), password)
        : api.signUp(name.trim(), email.trim(), password),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      navigate({ to: "/" });
    },
  });

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-surface px-5">
      <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
        <div className="absolute -top-40 left-1/4 h-[420px] w-[420px] rounded-full bg-due/15 blur-[90px]" />
        <div className="absolute top-10 right-8 h-[380px] w-[380px] rounded-full bg-owe/10 blur-[100px]" />
      </div>

      <div className="relative w-full max-w-sm">
        <p className="num mb-3 text-[15px] font-semibold tracking-tight text-ink">Even</p>
        <Panel title={mode === "signin" ? "Sign in" : "Create account"}>
          <div className="space-y-4 p-5">
            {mode === "signup" ? (
              <Field label="Name">
                <TextInput
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Mara Silva"
                />
              </Field>
            ) : null}
            <Field label="Email">
              <TextInput value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
            </Field>
            <Field label="Password">
              <TextInput
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                placeholder="••••••••"
              />
            </Field>
            <InkButton
              className="w-full py-2.5"
              disabled={!email.trim() || submit.isPending}
              onClick={() => submit.mutate()}
            >
              {submit.isPending ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
            </InkButton>
            <button
              type="button"
              onClick={() => setMode(mode === "signin" ? "signup" : "signin")}
              className="num w-full text-[11px] text-ink3 underline decoration-line"
            >
              {mode === "signin" ? "Need an account? Sign up" : "Already have an account? Sign in"}
            </button>
          </div>
        </Panel>
      </div>
    </div>
  );
}
