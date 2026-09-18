import type { ReactNode } from "react";

export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`glass overflow-hidden rounded-xl ring-1 ring-black/5 ${className}`}>
      {title ? (
        <div className="flex items-center justify-between gap-3 border-b border-line/60 px-5 py-3">
          <h2 className="label-eyebrow">{title}</h2>
          {aside}
        </div>
      ) : null}
      {children}
    </div>
  );
}

export function InkButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-lg bg-ink px-3 py-2 text-sm font-medium text-card ring-1 ring-ink transition-transform hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-40 ${className}`}
    >
      {children}
    </button>
  );
}

export function QuietButton({
  children,
  className = "",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...rest}
      className={`rounded-lg bg-card px-3 py-2 text-sm font-medium text-ink2 ring-1 ring-black/5 disabled:opacity-40 ${className}`}
    >
      {children}
    </button>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[12px] font-medium text-ink2">{label}</span>
      {children}
    </label>
  );
}

export function TextInput({
  className = "",
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...rest}
      className={`mt-1 w-full rounded-lg bg-card px-3 py-2 text-sm text-ink ring-1 ring-black/5 outline-none focus:ring-2 focus:ring-ink/20 ${className}`}
    />
  );
}

export function Select({
  className = "",
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...rest}
      className={`mt-1 w-full rounded-lg bg-card px-3 py-2 text-sm text-ink ring-1 ring-black/5 outline-none focus:ring-2 focus:ring-ink/20 ${className}`}
    >
      {children}
    </select>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return <p className="num px-5 py-6 text-[12px] text-ink3">{label}…</p>;
}
