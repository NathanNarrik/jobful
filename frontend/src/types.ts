export type JobListItem = {
  id: string;
  company_id: string;
  company_name: string;
  job_title: string;
  job_url: string;
  location: string[];
  program_type: string;
  academic_levels: string[];
  required_grad_years: number[];
  visa_status: string;
  remote_type: string;
  required_skills: string[];
  normalization_status: string;
  normalization_confidence: number;
  date_posted: string | null;
  last_seen_at: string;
};

export type JobDetail = JobListItem & {
  ats_provider: string;
  ats_job_id: string;
  departments: string[];
  employment_type: string | null;
  degree_requirements: string[];
  visa_sponsorship: boolean | null;
  nice_to_have_skills: string[];
  min_gpa: number | null;
  clearance_required: boolean;
  cleaned_description: string | null;
  raw_description: string | null;
  description_html: string | null;
  normalization_method: string;
  normalization_review_reasons: string[];
  normalized_at: string;
  first_seen_at: string;
  is_active: boolean;
};

export type PaginatedJobsResponse = {
  items: JobListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type SkillCount = {
  skill: string;
  count: number;
};

export type ApplicationStatus =
  | "SAVED"
  | "APPLIED"
  | "PHONE_SCREEN"
  | "TECHNICAL"
  | "FINAL"
  | "OFFER"
  | "REJECTED";

export type ApplicationRecord = {
  id: string;
  user_id: string;
  job_id: string | null;
  status: ApplicationStatus;
  applied_at: string | null;
  notes: string | null;
  kanban_order: number;
  created_at: string;
  updated_at: string;
  job: JobListItem | null;
};

export type DiscoveryFilters = {
  search: string;
  program_type: string;
  grad_year: string;
  remote_type: string;
  visa_status: string;
  skill: string;
};
