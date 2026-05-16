"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
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
      <FilterBar />
      <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Discover</h1>
            <p className="text-sm text-[var(--muted)]">{total.toLocaleString()} direct-source roles</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--line)] bg-white"
              disabled={!canGoBack || loading}
              onClick={() => void loadJobs(Math.max(0, offset - limit))}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-[var(--line)] bg-white"
              disabled={!canGoNext || loading}
              onClick={() => void loadJobs(nextOffset)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        {error ? <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}
        <section className="overflow-hidden rounded-lg border border-[var(--line)] bg-white shadow-sm">
          <div className="hidden grid-cols-[minmax(260px,1.5fr)_minmax(160px,0.8fr)_minmax(220px,1.1fr)_auto] border-b border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-bold uppercase tracking-wide text-[var(--muted)] md:grid">
            <span>Role</span>
            <span>Fit</span>
            <span>Signals</span>
            <span className="text-right">Action</span>
          </div>
          {loading && !jobs.length
            ? Array.from({ length: 10 }).map((_, index) => (
                <div key={index} className="h-20 animate-pulse border-b border-[var(--line)] bg-white" />
              ))
            : jobs.map((job) => <JobRow key={job.id} job={job} />)}
        </section>
      </div>
      <JobDetailDrawer />
      <Toast />
    </main>
  );
}
