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

export type EventListItem = {
  id: string;
  firm_name: string;
  firm_kind: string;
  event_title: string;
  event_url: string;
  registration_url: string | null;
  event_type: string;
  audience_tags: string[];
  location: string[];
  location_type: string;
  starts_at: string;
  ends_at: string | null;
  timezone: string | null;
  last_seen_at: string;
  is_active: boolean;
};

export type EventDetail = EventListItem & {
  source_id: string | null;
  source_provider: string;
  source_event_id: string | null;
  description: string | null;
  raw_payload: Record<string, unknown> | null;
  first_seen_at: string;
  is_active: boolean;
};

export type PaginatedEventsResponse = {
  items: EventListItem[];
  total: number;
  limit: number;
  offset: number;
};

export type EventSourceSummary = {
  id: string;
  firm_name: string;
  firm_kind: string;
  source_url: string;
  source_provider: string;
  source_scope: string;
  source_status: string;
  is_active: boolean;
  last_scraped_at: string | null;
  last_success_at: string | null;
  last_error_type: string | null;
  last_error_message: string | null;
  event_count: number;
  active_event_count: number;
};

export type SkillCount = {
  skill: string;
  count: number;
};

export type CompanySummary = {
  id: string;
  name: string;
  ats_provider: string;
  career_page_url: string | null;
  ats_board_token: string | null;
  is_active: boolean;
  last_scraped_at: string | null;
  job_count: number;
  active_job_count: number;
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
  country: string;
  remote_type: string;
  visa_status: string;
  skill: string;
};

export type EventFilters = {
  search: string;
  firm: string;
  firm_kind: string;
  event_type: string;
  location_type: string;
  starts_after: string;
  active_only: string;
};
