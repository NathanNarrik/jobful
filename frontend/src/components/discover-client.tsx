"use client";

import { ChevronLeft, ChevronRight, Database, Sparkles, Zap } from "lucide-react";
import { useEffect } from "react";
import { FilterBar } from "@/components/filter-bar";
import { JobDetailDrawer } from "@/components/job-detail-drawer";
import { JobRow } from "@/components/job-row";
import { Toast } from "@/components/toast";
import { useApplicationStore } from "@/stores/application-store";
import { useDiscoveryStore } from "@/stores/discovery-store";

export function DiscoverClient() {
  const { jobs, total, limit, offset, loading, error, loadJobs, loadSkills } = useDiscoveryStore();
  const { loadApplications } = useApplicationStore();

  useEffect(() => {
    void loadSkills();
    void loadJobs(0);
    void loadApplications();
  }, [loadApplications, loadJobs, loadSkills]);

  const nextOffset = offset + limit;
  const canGoBack = offset > 0;
  const canGoNext = nextOffset < total;

  return (
    <main>
      <div className="mx-auto max-w-7xl px-4 py-5 sm:px-6">
        <div className="mb-4 grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Direct-source feed</p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">Discover</h1>
            <p className="mt-1 text-sm text-[var(--muted)]">Verified company ATS links, normalized for student eligibility.</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <Stat icon={<Database size={15} />} label="Roles" value={total.toLocaleString()} />
            <Stat icon={<Zap size={15} />} label="Page" value={`${offset + 1}-${Math.min(offset + limit, total)}`} />
            <Stat icon={<Sparkles size={15} />} label="Source" value="ATS only" />
          </div>
        </div>
        <div className="mb-4">
          <FilterBar />
        </div>
        <div className="mb-3 flex items-center justify-end gap-2">
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-sm transition hover:bg-[var(--surface-soft)]"
              disabled={!canGoBack || loading}
              onClick={() => void loadJobs(Math.max(0, offset - limit))}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--surface)] shadow-sm transition hover:bg-[var(--surface-soft)]"
              disabled={!canGoNext || loading}
              onClick={() => void loadJobs(nextOffset)}
            >
              <ChevronRight size={16} />
            </button>
        </div>
        {error ? <div className="rounded-md border border-rose-300/30 bg-rose-400/10 p-3 text-sm text-rose-100">{error}</div> : null}
        <section className="overflow-hidden rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-[0_10px_30px_rgba(25,35,40,0.06)]">
          <div className="hidden grid-cols-[minmax(260px,1.5fr)_minmax(160px,0.8fr)_minmax(220px,1.1fr)_auto] border-b border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2.5 text-xs font-bold uppercase tracking-wide text-[var(--muted)] md:grid">
            <span>Role</span>
            <span>Fit</span>
            <span>Signals</span>
            <span className="text-right">Action</span>
          </div>
          {loading && !jobs.length
            ? Array.from({ length: 10 }).map((_, index) => (
                <div key={index} className="h-20 animate-pulse border-b border-[var(--line)] bg-[var(--surface)]" />
              ))
            : jobs.map((job) => <JobRow key={job.id} job={job} />)}
        </section>
      </div>
      <JobDetailDrawer />
      <Toast />
    </main>
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
