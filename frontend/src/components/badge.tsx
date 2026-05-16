import { clsx } from "clsx";

const tones = {
  neutral: "border-[var(--line)] bg-white text-[var(--muted)]",
  green: "border-emerald-200 bg-emerald-50 text-emerald-800",
  teal: "border-teal-200 bg-teal-50 text-teal-800",
  amber: "border-amber-200 bg-amber-50 text-amber-800",
  red: "border-red-200 bg-red-50 text-red-800",
};

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
}) {
  return (
    <span className={clsx("inline-flex h-6 items-center rounded-md border px-2 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}
