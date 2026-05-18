"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { BriefcaseBusiness, Building2, LayoutDashboard } from "lucide-react";
import { clsx } from "clsx";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[var(--background)]">
      <header className="sticky top-0 z-40 border-b border-[var(--line)] bg-[var(--surface)]/88 shadow-[0_1px_0_rgba(255,255,255,0.03)] backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6">
          <Link href="/discover" className="flex items-center gap-3 font-semibold text-[var(--foreground)]">
            <Image src="/jobful-logo.svg" alt="Jobful" width={40} height={40} className="rounded-xl shadow-sm" priority />
            <span className="text-lg tracking-tight">Jobful</span>
          </Link>
          <nav className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] p-1">
            <NavLink href="/discover" active={pathname.startsWith("/discover")} icon={<BriefcaseBusiness size={16} />}>
              Discover
            </NavLink>
            <NavLink href="/companies" active={pathname.startsWith("/companies")} icon={<Building2 size={16} />}>
              Companies
            </NavLink>
            <NavLink href="/dashboard" active={pathname.startsWith("/dashboard")} icon={<LayoutDashboard size={16} />}>
              Dashboard
            </NavLink>
          </nav>
        </div>
      </header>
      {children}
    </div>
  );
}

function NavLink({
  href,
  active,
  icon,
  children,
}: {
  href: string;
  active: boolean;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={clsx(
        "inline-flex h-9 items-center gap-2 rounded-md px-3 text-sm font-semibold transition",
        active
          ? "bg-[var(--surface-strong)] text-[var(--foreground)] shadow-sm"
          : "text-[var(--muted)] hover:text-[var(--foreground)]",
      )}
    >
      {icon}
      <span className="hidden sm:inline">{children}</span>
    </Link>
  );
}
