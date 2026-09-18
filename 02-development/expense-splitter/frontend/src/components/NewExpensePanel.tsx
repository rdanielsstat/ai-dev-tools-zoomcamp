import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import {
  SPLIT_TYPES,
  centsToInput,
  computeSplit,
  formatCents,
  parseAmountToCents,
  type ItemizedLine,
  type SplitType,
} from "@/lib/money";
import type { Expense, Member } from "@/lib/types";
import { Field, InkButton, Panel, QuietButton, Select, TextInput } from "@/components/ledger";

const today = () => new Date().toISOString().slice(0, 10);
const lineId = () => `li_${Math.random().toString(36).slice(2, 8)}`;
const defaultItems = (members: Member[]): ItemizedLine[] => [
  { id: lineId(), label: "", amountCents: 0, participantIds: members.map((m) => m.userId) },
];

/** Reusable create/edit form for an expense. Pass `editing` to prefill and PATCH instead of POST. */
export function ExpenseForm({
  groupId,
  members,
  editing,
  onSaved,
  onCancel,
}: {
  groupId: string;
  members: Member[];
  editing?: Expense;
  onSaved?: () => void;
  onCancel?: () => void;
}) {
  const queryClient = useQueryClient();
  const [description, setDescription] = useState(editing?.description ?? "");
  const [amountStr, setAmountStr] = useState(
    editing && editing.splitType !== "itemized" ? centsToInput(editing.amountCents) : "",
  );
  const [date, setDate] = useState(editing?.date ?? today());
  const [category, setCategory] = useState(editing?.category ?? "");
  const [splitType, setSplitType] = useState<SplitType>(editing?.splitType ?? "equal");
  const [multiPayer, setMultiPayer] = useState((editing?.payers.length ?? 0) > 1);
  const [payerId, setPayerId] = useState(
    editing?.payers.length === 1 ? editing.payers[0]!.userId : (members[0]?.userId ?? ""),
  );
  const [payerAmounts, setPayerAmounts] = useState<Record<string, string>>(() => {
    if (!editing || editing.payers.length <= 1) return {};
    const out: Record<string, string> = {};
    for (const p of editing.payers) out[p.userId] = centsToInput(p.amountCents);
    return out;
  });
  const [participants, setParticipants] = useState<string[]>(
    editing ? Object.keys(editing.shares) : members.map((m) => m.userId),
  );
  const [values, setValues] = useState<Record<string, string>>(() => {
    if (!editing?.splitValues) return {};
    const out: Record<string, string> = {};
    for (const [id, v] of Object.entries(editing.splitValues)) {
      out[id] = editing.splitType === "exact" ? centsToInput(v) : String(v);
    }
    return out;
  });
  const [items, setItems] = useState<ItemizedLine[]>(editing?.items ?? defaultItems(members));
  const [taxTipStr, setTaxTipStr] = useState(() => {
    if (!editing || editing.splitType !== "itemized") return "";
    const itemsSum = (editing.items ?? []).reduce((a, i) => a + i.amountCents, 0);
    return centsToInput(editing.amountCents - itemsSum);
  });

  const itemsTotal = items.reduce((a, i) => a + i.amountCents, 0);
  const extraCents = parseAmountToCents(taxTipStr);
  const totalCents =
    splitType === "itemized" ? itemsTotal + extraCents : parseAmountToCents(amountStr);

  const numericValues = useMemo(() => {
    const out: Record<string, number> = {};
    for (const id of participants) {
      const raw = values[id] ?? "";
      out[id] = splitType === "exact" ? parseAmountToCents(raw) : Number(raw || 0);
    }
    return out;
  }, [participants, values, splitType]);

  const split = useMemo(
    () =>
      computeSplit({
        type: splitType,
        totalCents,
        participantIds: participants,
        values: numericValues,
        items,
        extraCents,
      }),
    [splitType, totalCents, participants, numericValues, items, extraCents],
  );

  const payers = multiPayer
    ? members
        .map((m) => ({
          userId: m.userId,
          amountCents: parseAmountToCents(payerAmounts[m.userId] ?? ""),
        }))
        .filter((p) => p.amountCents > 0)
    : payerId
      ? [{ userId: payerId, amountCents: totalCents }]
      : [];
  const payersTotal = payers.reduce((a, p) => a + p.amountCents, 0);
  const payerError =
    payers.length === 0
      ? "Pick who paid."
      : payersTotal !== totalCents
        ? `Payers must add up to ${formatCents(totalCents)}.`
        : null;

  const blocked = !description.trim() || totalCents <= 0 || !!split.error || !!payerError;

  const invalidate = () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: ["expenses", groupId] }),
      queryClient.invalidateQueries({ queryKey: ["balances", groupId] }),
      queryClient.invalidateQueries({ queryKey: ["activity", groupId] }),
    ]);

  const save = useMutation({
    mutationFn: () => {
      const input = {
        groupId,
        description: description.trim(),
        amountCents: totalCents,
        date,
        category: category.trim() || null,
        splitType,
        payers,
        participantIds: participants,
        values: numericValues,
        items: splitType === "itemized" ? items : undefined,
        extraCents: splitType === "itemized" ? extraCents : 0,
      };
      return editing ? api.editExpense(editing.id, input) : api.addExpense(input);
    },
    onSuccess: async () => {
      if (editing) {
        await invalidate();
        onSaved?.();
        return;
      }
      setDescription("");
      setAmountStr("");
      setValues({});
      setTaxTipStr("");
      setItems(defaultItems(members));
      await invalidate();
    },
  });

  const toggleParticipant = (userId: string) =>
    setParticipants((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId],
    );

  const name = (userId: string) => members.find((m) => m.userId === userId)?.name ?? "—";

  return (
    <div className="space-y-4 p-5">
      <Field label="Description">
        <TextInput
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Fado dinner, Alfama"
        />
      </Field>

      <Field label={splitType === "itemized" ? "Total (from items)" : "Amount"}>
        <div className="mt-1 flex items-center rounded-lg bg-card px-3 py-2 ring-1 ring-black/5">
          <span className="num text-[13px] text-ink3">$</span>
          {splitType === "itemized" ? (
            <span className="num ml-1 text-[15px] font-medium text-ink">
              {centsToInput(totalCents)}
            </span>
          ) : (
            <input
              value={amountStr}
              onChange={(e) => setAmountStr(e.target.value)}
              inputMode="decimal"
              placeholder="0.00"
              className="num ml-1 w-full bg-transparent text-[15px] font-medium text-ink outline-none"
            />
          )}
        </div>
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Date">
          <TextInput type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Category">
          <TextInput
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="Food"
          />
        </Field>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <span className="text-[12px] font-medium text-ink2">Paid by</span>
          <button
            type="button"
            onClick={() => setMultiPayer((v) => !v)}
            className="num text-[11px] text-ink3 underline decoration-line"
          >
            {multiPayer ? "single payer" : "multiple payers"}
          </button>
        </div>
        {multiPayer ? (
          <div className="mt-1 space-y-1.5 rounded-lg bg-card/70 p-3 ring-1 ring-black/5">
            {members.map((m) => (
              <div key={m.userId} className="flex items-center gap-2">
                <span className="num flex-1 text-[12px] text-ink2">{m.name}</span>
                <span className="num text-[11px] text-ink3">$</span>
                <input
                  value={payerAmounts[m.userId] ?? ""}
                  onChange={(e) => setPayerAmounts((p) => ({ ...p, [m.userId]: e.target.value }))}
                  inputMode="decimal"
                  placeholder="0.00"
                  className="num w-20 rounded-md bg-card px-2 py-1 text-right text-[12px] text-ink ring-1 ring-black/5 outline-none"
                />
              </div>
            ))}
          </div>
        ) : (
          <Select value={payerId} onChange={(e) => setPayerId(e.target.value)}>
            {members.map((m) => (
              <option key={m.userId} value={m.userId}>
                {m.name}
              </option>
            ))}
          </Select>
        )}
      </div>

      <div>
        <span className="text-[12px] font-medium text-ink2">Split type</span>
        <div className="mt-1 flex flex-wrap gap-1 rounded-lg bg-line/40 p-1">
          {SPLIT_TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setSplitType(t.id)}
              className={`rounded-md px-3 py-1.5 text-[12px] font-medium ${
                splitType === t.id
                  ? "bg-card text-ink ring-1 ring-black/5"
                  : "text-ink2 hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {splitType === "itemized" ? (
        <div className="space-y-2 rounded-lg bg-card/70 p-3 ring-1 ring-black/5">
          <p className="label-eyebrow">Line items</p>
          {items.map((item) => (
            <div key={item.id} className="space-y-1.5 border-b border-line/60 pb-2 last:border-0">
              <div className="flex items-center gap-2">
                <input
                  value={item.label}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((i) => (i.id === item.id ? { ...i, label: e.target.value } : i)),
                    )
                  }
                  placeholder="Grilled sardines"
                  className="min-w-0 flex-1 rounded-md bg-card px-2 py-1 text-[12px] text-ink ring-1 ring-black/5 outline-none"
                />
                <input
                  value={item.amountCents ? centsToInput(item.amountCents) : ""}
                  onChange={(e) =>
                    setItems((prev) =>
                      prev.map((i) =>
                        i.id === item.id
                          ? { ...i, amountCents: parseAmountToCents(e.target.value) }
                          : i,
                      ),
                    )
                  }
                  inputMode="decimal"
                  placeholder="0.00"
                  className="num w-20 rounded-md bg-card px-2 py-1 text-right text-[12px] text-ink ring-1 ring-black/5 outline-none"
                />
              </div>
              <div className="flex flex-wrap gap-1">
                {members.map((m) => {
                  const on = item.participantIds.includes(m.userId);
                  return (
                    <button
                      key={m.userId}
                      type="button"
                      onClick={() =>
                        setItems((prev) =>
                          prev.map((i) =>
                            i.id === item.id
                              ? {
                                  ...i,
                                  participantIds: on
                                    ? i.participantIds.filter((id) => id !== m.userId)
                                    : [...i.participantIds, m.userId],
                                }
                              : i,
                          ),
                        )
                      }
                      className={`num rounded-md px-2 py-0.5 text-[11px] ${
                        on ? "bg-ink text-card" : "bg-card text-ink3 ring-1 ring-black/5"
                      }`}
                    >
                      {m.name}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={() => setItems((prev) => [...prev, ...defaultItems(members)])}
              className="num text-[11px] text-ink2 underline decoration-line"
            >
              + item
            </button>
            <span className="num ml-auto text-[11px] text-ink3">tax + tip $</span>
            <input
              value={taxTipStr}
              onChange={(e) => setTaxTipStr(e.target.value)}
              inputMode="decimal"
              placeholder="0.00"
              className="num w-20 rounded-md bg-card px-2 py-1 text-right text-[12px] text-ink ring-1 ring-black/5 outline-none"
            />
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-card/70 p-3 ring-1 ring-black/5">
          <p className="label-eyebrow">Participants</p>
          <div className="mt-2 space-y-1.5">
            {members.map((m) => {
              const on = participants.includes(m.userId);
              return (
                <div key={m.userId} className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => toggleParticipant(m.userId)}
                    className={`num flex-1 rounded-md px-2 py-1 text-left text-[12px] ${
                      on ? "bg-ink text-card" : "text-ink3 ring-1 ring-black/5"
                    }`}
                  >
                    {m.name}
                  </button>
                  {on && splitType !== "equal" ? (
                    <div className="flex items-center gap-1">
                      {splitType === "exact" ? (
                        <span className="num text-[11px] text-ink3">$</span>
                      ) : null}
                      <input
                        value={values[m.userId] ?? ""}
                        onChange={(e) => setValues((p) => ({ ...p, [m.userId]: e.target.value }))}
                        inputMode="decimal"
                        placeholder={splitType === "shares" ? "1" : "0"}
                        className="num w-16 rounded-md bg-card px-2 py-1 text-right text-[12px] text-ink ring-1 ring-black/5 outline-none"
                      />
                      {splitType === "percent" ? (
                        <span className="num text-[11px] text-ink3">%</span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="rounded-lg bg-card/70 p-3 ring-1 ring-black/5">
        <p className="label-eyebrow">
          Live share · {participants.length} {participants.length === 1 ? "person" : "people"}
        </p>
        <div className="mt-2 space-y-1.5">
          {participants.map((id) => (
            <div key={id} className="flex items-center justify-between">
              <span className="num text-[12px] text-ink2">{name(id)}</span>
              <span className="num text-[12px] font-medium text-ink">
                {formatCents(split.shares[id] ?? 0)}
              </span>
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between border-t border-line/60 pt-2">
          <span className="num text-[11px] text-ink3">reconciles to total</span>
          <span className="num text-[12px] font-semibold text-ink">{formatCents(totalCents)}</span>
        </div>
      </div>

      {split.error || payerError ? (
        <p className="num text-[11px] text-owe">{split.error ?? payerError}</p>
      ) : null}
      {save.isError ? (
        <p className="num text-[11px] text-owe">{(save.error as Error).message}</p>
      ) : null}

      <div className="flex items-center gap-2">
        <InkButton
          className="flex-1 py-2.5"
          disabled={blocked || save.isPending}
          onClick={() => save.mutate()}
        >
          {save.isPending ? "Saving…" : editing ? "Save changes" : "Save expense"}
        </InkButton>
        {onCancel ? (
          <QuietButton className="py-2.5" onClick={onCancel} disabled={save.isPending}>
            Cancel
          </QuietButton>
        ) : null}
      </div>
    </div>
  );
}

export function NewExpensePanel({ groupId, members }: { groupId: string; members: Member[] }) {
  return (
    <Panel title="New expense">
      <ExpenseForm groupId={groupId} members={members} />
    </Panel>
  );
}
