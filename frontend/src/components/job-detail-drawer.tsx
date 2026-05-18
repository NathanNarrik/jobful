"use client";

import { Bookmark, BriefcaseBusiness, CalendarDays, Clock, ExternalLink, GraduationCap, MapPin, RefreshCw, Sparkles, X } from "lucide-react";
import { Badge } from "@/components/badge";
import { companyInitials, daysSinceLabel, plainTextDescription, shortDate, titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import { useDiscoveryStore } from "@/stores/discovery-store";

export function JobDetailDrawer() {
  const { activeJob, detailLoading, closeJob } = useDiscoveryStore();
  const { trackJob } = useApplicationStore();

  if (!activeJob && !detailLoading) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/25 backdrop-blur-[1px]" onClick={closeJob}>
      <aside
        className="ml-auto flex h-full w-full max-w-3xl flex-col bg-[var(--surface)] shadow-2xl ring-1 ring-white/10"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="border-b border-[var(--line)] bg-[var(--surface-soft)] p-5">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 items-start gap-3">
              {activeJob ? (
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-[var(--accent-soft)] text-sm font-bold text-[var(--accent-strong)] shadow-sm ring-1 ring-teal-300/20">
                  {companyInitials(activeJob.company_name)}
                </div>
              ) : null}
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[var(--accent)]">{activeJob?.company_name ?? "Loading"}</p>
                <h2 className="mt-1 text-2xl font-semibold leading-8 tracking-tight">{activeJob?.job_title ?? "Opening job"}</h2>
                {activeJob ? (
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-sm text-[var(--muted)]">
                    <Meta icon={<Clock size={15} />} value={daysSinceLabel(activeJob.date_posted ?? activeJob.last_seen_at)} />
                    <Meta icon={<MapPin size={15} />} value={activeJob.location.slice(0, 2).join("; ")} />
                    <Meta icon={<BriefcaseBusiness size={15} />} value={titleCase(activeJob.ats_provider)} />
                  </div>
                ) : null}
              </div>
            </div>
            <button className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-transparent hover:border-[var(--line)] hover:bg-[var(--surface-strong)]" onClick={closeJob}>
              <X size={18} />
            </button>
          </div>
        </div>

        {activeJob ? (
          <>
            <div className="flex flex-wrap gap-2 border-b border-[var(--line)] px-5 py-3">
              <Badge tone="teal">{titleCase(activeJob.program_type)}</Badge>
              <Badge>{titleCase(activeJob.remote_type)}</Badge>
              <Badge tone={activeJob.visa_status === "sponsors" ? "green" : "neutral"}>{titleCase(activeJob.visa_status)}</Badge>
              {activeJob.required_grad_years.map((year) => (
                <Badge key={year}>{year}</Badge>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto bg-[var(--background)] px-5 py-5">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Field icon={<MapPin size={16} />} label="Location" value={activeJob.location.join("; ")} />
                <Field icon={<CalendarDays size={16} />} label="Posted" value={`${daysSinceLabel(activeJob.date_posted ?? activeJob.last_seen_at)} (${shortDate(activeJob.date_posted ?? activeJob.last_seen_at)})`} />
                <Field icon={<RefreshCw size={16} />} label="Seen by Jobful" value={`First ${shortDate(activeJob.first_seen_at)} | latest ${shortDate(activeJob.last_seen_at)}`} />
                <Field icon={<GraduationCap size={16} />} label="Academic levels" value={activeJob.academic_levels.join(", ") || "Not specified"} />
                <Field icon={<Sparkles size={16} />} label="Skills" value={activeJob.required_skills.slice(0, 12).join(", ") || "Not specified"} wide />
                <Field icon={<BriefcaseBusiness size={16} />} label="ATS" value={`${titleCase(activeJob.ats_provider)} | ${activeJob.ats_job_id}`} />
              </dl>
              <section className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--surface)] shadow-sm">
                <div className="border-b border-[var(--line)] px-4 py-3">
                  <h3 className="text-sm font-semibold">Description</h3>
                </div>
                <p className="max-h-[48vh] overflow-y-auto whitespace-pre-line px-4 py-4 text-sm leading-6 text-[var(--muted)]">
                  {plainTextDescription(activeJob.cleaned_description || activeJob.raw_description).slice(0, 7000)}
                </p>
              </section>
            </div>
            <div className="flex flex-col gap-2 border-t border-[var(--line)] bg-[var(--surface)] p-4 shadow-[0_-10px_30px_rgba(25,35,40,0.04)] sm:flex-row">
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-[var(--line)] px-4 text-sm font-semibold hover:bg-[var(--surface-strong)]"
                onClick={() => void trackJob(activeJob.id, "SAVED")}
              >
                <Bookmark size={16} />
                Save
              </button>
              <a
                href={activeJob.job_url}
                target="_blank"
                rel="noreferrer"
                onClick={() => void trackJob(activeJob.id, "APPLIED")}
                className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-semibold text-[#061018] shadow-sm hover:bg-[var(--accent-strong)]"
              >
                <ExternalLink size={16} />
                Apply on {activeJob.company_name}
              </a>
            </div>
          </>
        ) : (
          <div className="p-4 text-sm text-[var(--muted)]">Loading job detail...</div>
        )}
      </aside>
    </div>
  );
}

function Meta({ icon, value }: { icon: React.ReactNode; value: string }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <span className="shrink-0 text-[var(--muted)]">{icon}</span>
      <span className="truncate">{value}</span>
    </span>
  );
}

function Field({
  icon,
  label,
  value,
  wide = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  wide?: boolean;
}) {
  return (
    <div className={`rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3 shadow-sm ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-[var(--muted)]">
        {icon}
        {label}
      </dt>
      <dd className="mt-2 text-sm font-medium leading-5">{value}</dd>
    </div>
  );
}
