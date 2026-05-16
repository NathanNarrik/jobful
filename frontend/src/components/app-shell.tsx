import Link from "next/link";
import { BriefcaseBusiness, LayoutDashboard } from "lucide-react";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="sticky top-0 z-40 border-b border-[var(--line)] bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
          <Link href="/discover" className="flex items-center gap-2 font-semibold text-[var(--foreground)]">
            <span className="grid h-8 w-8 place-items-center rounded-md bg-[var(--accent)] text-sm font-bold text-white">
              JF
            </span>
            <span>Jobful</span>
          </Link>
          <nav className="flex items-center gap-1">
            <Link
              href="/discover"
              className="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-[var(--muted)] hover:bg-[var(--surface-strong)] hover:text-[var(--foreground)]"
            >
              <BriefcaseBusiness size={16} />
              Discover
            </Link>
            <Link
              href="/dashboard"
              className="inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-[var(--muted)] hover:bg-[var(--surface-strong)] hover:text-[var(--foreground)]"
            >
              <LayoutDashboard size={16} />
              Dashboard
            </Link>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}
