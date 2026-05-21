"use client";

import { Bookmark, Clock, ExternalLink, GraduationCap, MapPin } from "lucide-react";
import type { JobListItem } from "@/types";
import { Badge } from "@/components/badge";
import { compactLocation, companyInitials, compactPostedAge, titleCase } from "@/lib/format";
import { useApplicationStore } from "@/stores/application-store";
import { useDiscoveryStore } from "@/stores/discovery-store";

export function JobCard({ job }: { job: JobListItem }) {
  const { openJob } = useDiscoveryStore();
  const { trackJob } = useApplicationStore();
  const visaTone = job.visa_status === "sponsors" || job.visa_status === "opt_cpt_allowed" ? "green" : "neutral";

  async function applyNow(event: React.MouseEvent<HTMLAnchorElement>) {
    event.stopPropagation();
    await trackJob(job.id, "APPLIED");
  }

  return (
    <article
      className="grid min-h-[178px] cursor-pointer grid-rows-[auto_1fr_auto] rounded-lg border border-[var(--line)] bg-[var(--surface)] p-3 shadow-sm transition hover:border-[var(--accent)] hover:shadow-md"
      onClick={() => void openJob(job.id)}
    >
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-md bg-[var(--surface-strong)] text-sm font-bold text-[var(--accent-strong)]">
          {companyInitials(job.company_name)}
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--foreground)]">{job.company_name}</p>
          <h2 className="mt-1 line-clamp-2 text-[15px] font-semibold leading-5">{job.job_title}</h2>
        </div>
      </div>

      <div className="mt-3 space-y-2 text-xs text-[var(--muted)]">
        <div className="flex items-center gap-1.5">
          <MapPin size={14} />
          <span className="truncate">{compactLocation(job.location)}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <GraduationCap size={14} />
          <span>{job.required_grad_years.slice(0, 2).join(", ") || titleCase(job.program_type)}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock size={14} />
          <span>{compactPostedAge(job.date_posted ?? job.last_seen_at)}</span>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge tone="teal">{titleCase(job.program_type)}</Badge>
        <Badge>{titleCase(job.remote_type)}</Badge>
        <Badge tone={visaTone}>{titleCase(job.visa_status)}</Badge>
        <button
          type="button"
          className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md border border-[var(--line)] text-[var(--muted)] hover:bg-[var(--surface-strong)]"
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
          className="inline-flex h-8 items-center gap-1 rounded-md bg-[var(--accent)] px-2.5 text-xs font-semibold text-[#061018] hover:bg-[var(--accent-strong)]"
        >
          <ExternalLink size={14} />
          Apply
        </a>
      </div>
    </article>
  );
}
