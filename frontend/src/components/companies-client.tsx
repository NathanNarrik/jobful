"use client";

import { ArrowUpRight, BriefcaseBusiness, Building2, Database, ExternalLink, Search, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/badge";
import { listCompanies } from "@/lib/api";
import { companyInitials, shortDate, titleCase } from "@/lib/format";
import type { CompanySummary } from "@/types";

type CompanyMode = "active" | "all" | "quiet";

export function CompaniesClient() {
  const [companies, setCompanies] = useState<CompanySummary[]>([]);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<CompanyMode>("active");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        setCompanies(await listCompanies());
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load companies");
      } finally {
        setLoading(false);
      }
    }

    void load();
  }, []);

  const stats = useMemo(() => {
    const activeCompanies = companies.filter((company) => company.active_job_count > 0).length;
    const activeJobs = companies.reduce((sum, company) => sum + company.active_job_count, 0);
    const totalJobs = companies.reduce((sum, company) => sum + company.job_count, 0);
    return { activeCompanies, activeJobs, totalCompanies: companies.length, totalJobs };
  }, [companies]);

  const filteredCompanies = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return companies
      .filter((company) => {
        if (mode === "active" && company.active_job_count === 0) return false;
        if (mode === "quiet" && company.active_job_count > 0) return false;
        if (!normalizedQuery) return true;
        return [
          company.name,
          company.ats_provider,
          company.ats_board_token ?? "",
        ].some((value) => value.toLowerCase().includes(normalizedQuery));
      })
      .sort((left, right) => {
        if (left.active_job_count !== right.active_job_count) {
          return right.active_job_count - left.active_job_count;
        }
        if (left.job_count !== right.job_count) {
          return right.job_count - left.job_count;
        }
        return left.name.localeCompare(right.name);
      });
  }, [companies, mode, query]);

  const featuredCompanies = filteredCompanies.slice(0, 8);

  return (
    <main>
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
        <div className="mb-5 grid gap-4 xl:grid-cols-[1fr_420px] xl:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Company index</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">Companies</h1>
            <p className="mt-1 max-w-2xl text-sm text-[var(--muted)]">
              Browse every source Jobful is tracking and jump straight into active CS roles.
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Stat icon={<Building2 size={15} />} label="Active" value={stats.activeCompanies.toLocaleString()} />
            <Stat icon={<BriefcaseBusiness size={15} />} label="Roles" value={stats.activeJobs.toLocaleString()} />
            <Stat icon={<Database size={15} />} label="Sources" value={stats.totalCompanies.toLocaleString()} />
          </div>
        </div>

        <section className="mb-4 rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 shadow-[0_10px_30px_rgba(0,0,0,0.16)]">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <label className="relative h-11 min-w-0 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={16} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search company or ATS"
                className="focus-ring h-11 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] pl-9 pr-3 text-sm outline-none transition focus:border-[var(--accent)]"
              />
            </label>
            <div className="grid grid-cols-3 gap-2 sm:w-[430px]">
              <ModeButton active={mode === "active"} label="Active" count={stats.activeCompanies} onClick={() => setMode("active")} />
              <ModeButton active={mode === "all"} label="All" count={stats.totalCompanies} onClick={() => setMode("all")} />
              <ModeButton
                active={mode === "quiet"}
                label="No active"
                count={stats.totalCompanies - stats.activeCompanies}
                onClick={() => setMode("quiet")}
              />
            </div>
          </div>
        </section>

        {error ? <div className="mb-4 rounded-md border border-rose-300/30 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</div> : null}

        <section className="mb-4 grid gap-3 lg:grid-cols-4">
          {loading
            ? Array.from({ length: 8 }).map((_, index) => <div key={index} className="h-28 animate-pulse rounded-xl border border-[var(--line)] bg-[var(--surface)]" />)
            : featuredCompanies.map((company) => <FeaturedCompany key={company.id} company={company} />)}
        </section>

        <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-[0_10px_30px_rgba(0,0,0,0.16)]">
          <div className="hidden grid-cols-[minmax(260px,1.4fr)_120px_120px_minmax(140px,0.8fr)_minmax(120px,0.7fr)_auto] border-b border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-[var(--muted)] md:grid">
            <span>Company</span>
            <span>Active</span>
            <span>Total</span>
            <span>ATS</span>
            <span>Seen</span>
            <span className="text-right">Open</span>
          </div>
          {loading ? (
            Array.from({ length: 12 }).map((_, index) => (
              <div key={index} className="h-16 animate-pulse border-b border-[var(--line)] bg-[var(--surface)]" />
            ))
          ) : filteredCompanies.length ? (
            filteredCompanies.map((company) => <CompanyRow key={company.id} company={company} maxActive={Math.max(1, featuredCompanies[0]?.active_job_count ?? 1)} />)
          ) : (
            <div className="flex min-h-40 flex-col items-center justify-center gap-2 px-4 py-10 text-center">
              <Sparkles className="text-[var(--muted)]" size={24} />
              <p className="font-semibold">No companies match that view.</p>
              <p className="text-sm text-[var(--muted)]">Try another search or switch the segment.</p>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function FeaturedCompany({ company }: { company: CompanySummary }) {
  return (
    <Link
      href={`/discover?search=${encodeURIComponent(company.name)}`}
      className="group rounded-xl border border-[var(--line)] bg-[var(--surface)] p-4 shadow-[0_10px_28px_rgba(0,0,0,0.14)] transition hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-xs font-bold text-[var(--accent-strong)] ring-1 ring-inset ring-teal-300/20">
          {companyInitials(company.name)}
        </div>
        <ArrowUpRight className="text-[var(--muted)] transition group-hover:text-[var(--accent)]" size={17} />
      </div>
      <h2 className="mt-3 truncate text-base font-semibold">{company.name}</h2>
      <div className="mt-3 flex items-center gap-2">
        <Badge tone={company.active_job_count > 0 ? "teal" : "neutral"}>{company.active_job_count.toLocaleString()} active</Badge>
        <Badge>{titleCase(company.ats_provider)}</Badge>
      </div>
    </Link>
  );
}

function CompanyRow({ company, maxActive }: { company: CompanySummary; maxActive: number }) {
  const activeWidth = `${Math.max(4, Math.round((company.active_job_count / maxActive) * 100))}%`;

  return (
    <article className="grid gap-3 border-b border-[var(--line)] bg-[var(--surface)] px-4 py-3 transition hover:bg-[var(--surface-soft)] md:grid-cols-[minmax(260px,1.4fr)_120px_120px_minmax(140px,0.8fr)_minmax(120px,0.7fr)_auto] md:items-center">
      <div className="flex min-w-0 items-center gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-[var(--blue-soft)] text-xs font-bold text-[var(--blue)] ring-1 ring-inset ring-violet-300/20">
          {companyInitials(company.name)}
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold">{company.name}</h2>
          <p className="truncate text-xs text-[var(--muted)]">{company.ats_board_token ?? company.ats_provider}</p>
        </div>
      </div>

      <div>
        <p className="text-sm font-semibold">{company.active_job_count.toLocaleString()}</p>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-[var(--surface-strong)]">
          <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: activeWidth }} />
        </div>
      </div>

      <p className="text-sm text-[var(--muted-strong)]">{company.job_count.toLocaleString()}</p>
      <Badge>{titleCase(company.ats_provider)}</Badge>
      <p className="text-xs text-[var(--muted)]">{shortDate(company.last_scraped_at)}</p>

      <div className="flex items-center gap-2 md:justify-end">
        {company.career_page_url ? (
          <a
            href={company.career_page_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] text-[var(--muted)] transition hover:bg-[var(--surface-strong)] hover:text-[var(--foreground)]"
            title="Open company careers page"
          >
            <ExternalLink size={14} />
          </a>
        ) : null}
        <Link
          href={`/discover?search=${encodeURIComponent(company.name)}`}
          className="inline-flex h-8 items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 text-xs font-semibold text-[#061018] transition hover:bg-[var(--accent-strong)]"
        >
          Jobs
          <ArrowUpRight size={14} />
        </Link>
      </div>
    </article>
  );
}

function ModeButton({ active, label, count, onClick }: { active: boolean; label: string; count: number; onClick: () => void }) {
  return (
    <button
      type="button"
      className={`rounded-lg border px-3 py-2 text-left transition ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--muted-strong)] hover:border-[var(--line-strong)] hover:bg-[var(--surface-strong)]"
      }`}
      onClick={onClick}
    >
      <span className="block truncate text-xs font-bold uppercase tracking-wide">{label}</span>
      <span className="mt-0.5 block text-sm font-semibold">{count.toLocaleString()}</span>
    </button>
  );
}

function Stat({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="flex h-12 items-center gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 shadow-sm">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)]">{icon}</span>
      <span>
        <span className="block text-[11px] font-bold uppercase tracking-wide text-[var(--muted)]">{label}</span>
        <span className="block text-sm font-semibold">{value}</span>
      </span>
    </div>
  );
}
