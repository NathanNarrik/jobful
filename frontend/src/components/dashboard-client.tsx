"use client";

import { ArrowUpRight, BriefcaseBusiness, CalendarDays, Search, Table2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/badge";
import { Toast } from "@/components/toast";
import { compactLocation, statusLabels, statusOrder, titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import type { ApplicationRecord, ApplicationStatus } from "@/types";

const statusTone: Record<ApplicationStatus, string> = {
  SAVED: "bg-slate-50 text-slate-700 ring-slate-200",
  APPLIED: "bg-teal-50 text-teal-800 ring-teal-200",
  PHONE_SCREEN: "bg-sky-50 text-sky-800 ring-sky-200",
  TECHNICAL: "bg-indigo-50 text-indigo-800 ring-indigo-200",
  FINAL: "bg-violet-50 text-violet-800 ring-violet-200",
  OFFER: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  REJECTED: "bg-rose-50 text-rose-800 ring-rose-200",
};

export function DashboardClient() {
  const { applications, loading, error, loadApplications, moveApplication, saveNotes } = useApplicationStore();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "ALL">("ALL");

  useEffect(() => {
    void loadApplications();
  }, [loadApplications]);

  const statusCounts = useMemo(() => {
    return Object.fromEntries(
      statusOrder.map((status) => [
        status,
        applications.filter((application) => application.status === status).length,
      ]),
    ) as Record<ApplicationStatus, number>;
  }, [applications]);

  const visibleApplications = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return applications
      .filter((application) => application.job)
      .filter((application) => statusFilter === "ALL" || application.status === statusFilter)
      .filter((application) => {
        if (!normalizedQuery) return true;
        const job = application.job;
        if (!job) return false;
        return [
          job.company_name,
          job.job_title,
          compactLocation(job.location),
          application.notes ?? "",
          statusLabels[application.status],
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((a, b) => {
        const statusDelta = statusOrder.indexOf(a.status) - statusOrder.indexOf(b.status);
        if (statusDelta !== 0) return statusDelta;
        return a.kanban_order - b.kanban_order || new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
      });
  }, [applications, query, statusFilter]);

  const appliedCount = applications.filter((application) => application.status !== "SAVED").length;
  const activeCount = applications.filter((application) => !["OFFER", "REJECTED"].includes(application.status)).length;

  return (
    <main className="mx-auto max-w-[1500px] px-4 py-5 sm:px-6">
      <div className="mb-4 grid gap-3 xl:grid-cols-[1fr_auto] xl:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[var(--accent)]">Closed-loop tracker</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Dashboard</h1>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:w-[460px]">
          <Metric icon={<Table2 size={15} />} label="Tracked" value={applications.length} />
          <Metric icon={<BriefcaseBusiness size={15} />} label="Active" value={activeCount} />
          <Metric icon={<CalendarDays size={15} />} label="Applied+" value={appliedCount} />
        </div>
      </div>

      {error ? <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}

      <section className="overflow-hidden rounded-lg border border-[var(--line)] bg-white shadow-sm">
        <div className="grid gap-2 border-b border-[var(--line)] bg-[var(--surface-soft)] p-2 lg:grid-cols-[minmax(260px,1fr)_auto]">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]" size={15} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search tracked roles"
              className="h-9 w-full rounded-md border border-[var(--line)] bg-white pl-8 pr-3 text-sm outline-none focus:border-[var(--accent)]"
            />
          </label>
          <div className="flex gap-1 overflow-x-auto">
            <FilterButton active={statusFilter === "ALL"} onClick={() => setStatusFilter("ALL")}>
              All <span>{applications.length}</span>
            </FilterButton>
            {statusOrder.map((status) => (
              <FilterButton key={status} active={statusFilter === status} onClick={() => setStatusFilter(status)}>
                {statusLabels[status]} <span>{statusCounts[status]}</span>
              </FilterButton>
            ))}
          </div>
        </div>

        {loading && !applications.length ? (
          <div className="divide-y divide-[var(--line)]">
            {Array.from({ length: 10 }).map((_, index) => (
              <div key={index} className="h-14 animate-pulse bg-white even:bg-[var(--surface-soft)]" />
            ))}
          </div>
        ) : (
          <div className="max-h-[calc(100vh-220px)] overflow-auto">
            <table className="w-full table-fixed border-separate border-spacing-0 text-left text-sm">
              <colgroup>
                <col className="w-[3%]" />
                <col className="w-[10%]" />
                <col className="w-[22%]" />
                <col className="w-[12%]" />
                <col className="w-[15%]" />
                <col className="w-[9%]" />
                <col className="w-[7%]" />
                <col className="w-[7%]" />
                <col className="w-[12%]" />
                <col className="w-[3%]" />
              </colgroup>
              <thead className="sticky top-0 z-10 bg-white text-[11px] uppercase tracking-wide text-[var(--muted)] shadow-[0_1px_0_var(--line)]">
                <tr>
                  <th className="px-2 py-2 font-bold">#</th>
                  <th className="px-2 py-2 font-bold">Status</th>
                  <th className="px-2 py-2 font-bold">Role</th>
                  <th className="px-2 py-2 font-bold">Company</th>
                  <th className="px-2 py-2 font-bold">Location</th>
                  <th className="px-2 py-2 font-bold">Type</th>
                  <th className="px-2 py-2 font-bold">Applied</th>
                  <th className="px-2 py-2 font-bold">Updated</th>
                  <th className="px-2 py-2 font-bold">Notes</th>
                  <th className="px-1 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--line)]">
                {visibleApplications.map((application, index) => (
                  <ApplicationRow
                    key={application.id}
                    application={application}
                    index={index}
                    onMove={moveApplication}
                    onSaveNotes={saveNotes}
                  />
                ))}
              </tbody>
            </table>
            {!visibleApplications.length ? (
              <div className="grid min-h-52 place-items-center border-t border-[var(--line)] text-sm text-[var(--muted)]">
                No roles match this view.
              </div>
            ) : null}
          </div>
        )}
      </section>
      <Toast />
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="flex h-12 items-center gap-2 rounded-lg border border-[var(--line)] bg-white px-3 shadow-sm">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md bg-[var(--blue-soft)] text-[var(--blue)]">{icon}</span>
      <span className="min-w-0">
        <span className="block truncate text-[10px] font-bold uppercase tracking-wide text-[var(--muted)]">{label}</span>
        <span className="block text-sm font-semibold tabular-nums">{value}</span>
      </span>
    </div>
  );
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex h-9 shrink-0 items-center gap-1 rounded-md border px-2.5 text-xs font-semibold transition ${
        active
          ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
          : "border-[var(--line)] bg-white text-[var(--muted-strong)] hover:border-[var(--line-strong)]"
      }`}
    >
      {children}
    </button>
  );
}

function ApplicationRow({
  application,
  index,
  onMove,
  onSaveNotes,
}: {
  application: ApplicationRecord;
  index: number;
  onMove: (applicationId: string, status: ApplicationStatus, kanbanOrder?: number) => Promise<void>;
  onSaveNotes: (applicationId: string, notes: string) => Promise<void>;
}) {
  const job = application.job;
  if (!job) return null;

  return (
    <tr className="group bg-white align-middle transition hover:bg-[var(--surface-soft)]">
      <td className="border-b border-[var(--line)] px-2 py-2 text-xs tabular-nums text-[var(--muted)]">{index + 1}</td>
      <td className="border-b border-[var(--line)] px-2 py-2">
        <select
          value={application.status}
          onChange={(event) => void onMove(application.id, event.target.value as ApplicationStatus, application.kanban_order)}
          className={`h-8 w-full rounded-md border-0 px-1.5 text-[11px] font-bold outline-none ring-1 ${statusTone[application.status]}`}
        >
          {statusOrder.map((status) => (
            <option key={status} value={status}>
              {statusLabels[status]}
            </option>
          ))}
        </select>
      </td>
      <td className="border-b border-[var(--line)] px-2 py-2">
        <a href={job.job_url} target="_blank" rel="noreferrer" className="line-clamp-1 font-semibold leading-5 hover:text-[var(--accent)]">
          {job.job_title}
        </a>
      </td>
      <td className="border-b border-[var(--line)] px-2 py-2">
        <span className="block truncate text-xs font-bold uppercase tracking-wide text-[var(--accent)]">{job.company_name}</span>
      </td>
      <td className="border-b border-[var(--line)] px-2 py-2 text-xs text-[var(--muted-strong)]">
        <span className="block truncate">{compactLocation(job.location)}</span>
      </td>
      <td className="border-b border-[var(--line)] px-2 py-2">
        <div className="flex flex-wrap gap-1">
          <Badge tone="teal">{titleCase(job.program_type)}</Badge>
          <Badge>{titleCase(job.remote_type)}</Badge>
        </div>
      </td>
      <td className="border-b border-[var(--line)] px-2 py-2 text-xs tabular-nums text-[var(--muted-strong)]">{compactDate(application.applied_at)}</td>
      <td className="border-b border-[var(--line)] px-2 py-2 text-xs tabular-nums text-[var(--muted-strong)]">{compactDate(application.updated_at)}</td>
      <td className="border-b border-[var(--line)] px-2 py-2">
        <input
          defaultValue={application.notes ?? ""}
          onBlur={(event) => void onSaveNotes(application.id, event.currentTarget.value)}
          placeholder="Notes"
          className="h-8 w-full rounded-md border border-transparent bg-transparent px-2 text-xs outline-none transition placeholder:text-[var(--muted)] hover:border-[var(--line)] hover:bg-white focus:border-[var(--accent)] focus:bg-white"
        />
      </td>
      <td className="border-b border-[var(--line)] px-1 py-2 text-right">
        <a
          href={job.job_url}
          target="_blank"
          rel="noreferrer"
          className="inline-grid h-8 w-8 place-items-center rounded-md text-[var(--muted)] transition hover:bg-[var(--accent-soft)] hover:text-[var(--accent)]"
          title="Open job"
        >
          <ArrowUpRight size={15} />
        </a>
      </td>
    </tr>
  );
}

function compactDate(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  const currentYear = new Date().getFullYear();
  const sameYear = date.getFullYear() === currentYear;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: sameYear ? undefined : "2-digit",
  }).format(date);
}
