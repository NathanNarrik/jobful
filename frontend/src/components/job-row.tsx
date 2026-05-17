"use client";

import { Bookmark, Clock, ExternalLink, GraduationCap, MapPin } from "lucide-react";
import { Badge } from "@/components/badge";
import { compactLocation, companyInitials, daysSince, titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import { useDiscoveryStore } from "@/stores/discovery-store";
import type { JobListItem } from "@/types";

export function JobRow({ job }: { job: JobListItem }) {
  const { openJob } = useDiscoveryStore();
  const { trackJob } = useApplicationStore();
  const visaTone = job.visa_status === "sponsors" || job.visa_status === "opt_cpt_allowed" ? "green" : "neutral";

  async function applyNow(event: React.MouseEvent<HTMLAnchorElement>) {
    event.stopPropagation();
    await trackJob(job.id, "APPLIED");
  }

  return (
    <article
      className="grid cursor-pointer gap-3 border-b border-[var(--line)] bg-white px-3 py-3 transition hover:bg-[var(--surface-strong)] hover:shadow-[inset_3px_0_0_var(--accent)] md:grid-cols-[minmax(260px,1.5fr)_minmax(160px,0.8fr)_minmax(220px,1.1fr)_auto] md:items-center"
      onClick={() => void openJob(job.id)}
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-[var(--surface-strong)] text-xs font-bold text-[var(--accent-strong)]">
          {companyInitials(job.company_name)}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--accent)]">{job.company_name}</p>
          <h2 className="line-clamp-2 text-sm font-semibold leading-5 text-[var(--foreground)]">{job.job_title}</h2>
        </div>
      </div>

      <div className="grid gap-1 text-xs text-[var(--muted)] sm:grid-cols-3 md:block md:space-y-1">
        <span className="flex min-w-0 items-center gap-1.5">
          <MapPin size={14} />
          <span className="truncate">{compactLocation(job.location)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <GraduationCap size={14} />
          <span>{job.required_grad_years.slice(0, 2).join(", ") || titleCase(job.program_type)}</span>
        </span>
        <span className="flex items-center gap-1.5">
          <Clock size={14} />
          <span>{daysSince(job.date_posted ?? job.last_seen_at)}</span>
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5">
        <Badge tone="teal">{titleCase(job.program_type)}</Badge>
        <Badge>{titleCase(job.remote_type)}</Badge>
        <Badge tone={visaTone}>{titleCase(job.visa_status)}</Badge>
        {job.required_skills.slice(0, 2).map((skill) => (
          <Badge key={skill}>{skill}</Badge>
        ))}
      </div>

      <div className="flex items-center gap-2 md:justify-end">
        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] text-[var(--muted)] hover:bg-white"
          title="Save job"
          onClick={(event) => {
            event.stopPropagation();
            void trackJob(job.id, "SAVED");
          }}
        >
          <Bookmark size={15} />
        </button>
        <a
          href={job.job_url}
          target="_blank"
          rel="noreferrer"
          onClick={applyNow}
          className="inline-flex h-8 items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 text-xs font-semibold text-white hover:bg-[var(--accent-strong)]"
        >
          <ExternalLink size={14} />
          Apply
        </a>
      </div>
    </article>
  );
}
