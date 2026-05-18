import type {
  ApplicationRecord,
  ApplicationStatus,
  CompanySummary,
  JobDetail,
  PaginatedJobsResponse,
  SkillCount,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_JOBFUL_API_BASE ?? "http://127.0.0.1:8000";

type RequestOptions = RequestInit & {
  query?: Record<string, string | number | undefined | null>;
};

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = new URL(path, API_BASE);
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function listJobs(query: RequestOptions["query"]) {
  return apiFetch<PaginatedJobsResponse>("/jobs", { query });
}

export function getJob(jobId: string) {
  return apiFetch<JobDetail>(`/jobs/${jobId}`);
}

export function listPopularSkills(limit = 18) {
  return apiFetch<SkillCount[]>("/skills/popular", { query: { limit } });
}

export function listCompanies() {
  return apiFetch<CompanySummary[]>("/companies");
}

export function listApplications() {
  return apiFetch<ApplicationRecord[]>("/applications");
}

export function createApplication(jobId: string, status: ApplicationStatus) {
  return apiFetch<ApplicationRecord>("/applications", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId, status }),
  });
}

export function updateApplication(
  applicationId: string,
  payload: Partial<Pick<ApplicationRecord, "status" | "notes" | "kanban_order" | "applied_at">>,
) {
  return apiFetch<ApplicationRecord>(`/applications/${applicationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}
