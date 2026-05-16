"use client";

import { Bookmark, ExternalLink, X } from "lucide-react";
import { Badge } from "@/components/badge";
import { titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import { useDiscoveryStore } from "@/stores/discovery-store";

export function JobDetailDrawer() {
  const { activeJob, detailLoading, closeJob } = useDiscoveryStore();
  const { trackJob } = useApplicationStore();

  if (!activeJob && !detailLoading) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/20" onClick={closeJob}>
      <aside
        className="ml-auto flex h-full w-full max-w-2xl flex-col bg-white shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-[var(--line)] p-4">
          <div>
            <p className="text-sm font-semibold text-[var(--accent)]">{activeJob?.company_name ?? "Loading"}</p>
            <h2 className="mt-1 text-xl font-semibold leading-7">{activeJob?.job_title ?? "Opening job"}</h2>
          </div>
          <button className="grid h-9 w-9 place-items-center rounded-md hover:bg-[var(--surface-strong)]" onClick={closeJob}>
            <X size={18} />
          </button>
        </div>

        {activeJob ? (
          <>
            <div className="flex flex-wrap gap-2 border-b border-[var(--line)] p-4">
              <Badge tone="teal">{titleCase(activeJob.program_type)}</Badge>
              <Badge>{titleCase(activeJob.remote_type)}</Badge>
              <Badge tone={activeJob.visa_status === "sponsors" ? "green" : "neutral"}>{titleCase(activeJob.visa_status)}</Badge>
              {activeJob.required_grad_years.map((year) => (
                <Badge key={year}>{year}</Badge>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Field label="Location" value={activeJob.location.join(", ")} />
                <Field label="ATS" value={titleCase(activeJob.ats_provider)} />
                <Field label="Academic levels" value={activeJob.academic_levels.join(", ") || "Not specified"} />
                <Field label="Skills" value={activeJob.required_skills.slice(0, 10).join(", ") || "Not specified"} />
              </dl>
              <section className="mt-5">
                <h3 className="text-sm font-semibold">Description</h3>
                <p className="mt-2 whitespace-pre-line text-sm leading-6 text-[var(--muted)]">
                  {(activeJob.cleaned_description || activeJob.raw_description || "").slice(0, 5000)}
                </p>
              </section>
            </div>
            <div className="flex flex-col gap-2 border-t border-[var(--line)] p-4 sm:flex-row">
              <button
                className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[var(--line)] px-4 text-sm font-semibold hover:bg-[var(--surface-strong)]"
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
                className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md bg-[var(--accent)] px-4 text-sm font-semibold text-white hover:bg-[var(--accent-strong)]"
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

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--line)] bg-[var(--surface-strong)] p-3">
      <dt className="text-xs font-medium text-[var(--muted)]">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}
