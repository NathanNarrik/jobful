import { clsx } from "clsx";

const tones = {
  neutral: "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--muted-strong)]",
  green: "border-emerald-400/30 bg-emerald-400/12 text-emerald-200",
  teal: "border-teal-300/30 bg-teal-300/12 text-teal-100",
  amber: "border-amber-300/30 bg-amber-300/12 text-amber-100",
  red: "border-rose-300/30 bg-rose-300/12 text-rose-100",
};

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: keyof typeof tones;
}) {
  return (
    <span className={clsx("inline-flex h-6 max-w-[12rem] items-center overflow-hidden text-ellipsis whitespace-nowrap rounded-md border px-2 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}
