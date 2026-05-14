/**
 * TypeScript types mirroring the Python Pydantic models in applyslave.shared.
 * Keep this file in sync with packages/shared/src/applyslave/shared/models.py.
 */

export interface Education {
  school: string;
  degree?: string | null;
  major?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface Experience {
  company: string;
  title: string;
  description?: string | null;
  start_date?: string | null;
  end_date?: string | null;
}

export interface UserProfile {
  id?: number | null;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  linkedin_url?: string | null;
  github_url?: string | null;
  education: Education[];
  experience: Experience[];
  skills: string[];
  resume_path?: string | null;
  updated_at?: string | null;
}

export type JobSourceName =
  | "greenhouse"
  | "lever"
  | "ashby"
  | "workable"
  | "linkedin"
  | "jsearch";

export interface JobListing {
  id: string;
  source: JobSourceName;
  company: string;
  title: string;
  location?: string | null;
  url: string;
  apply_url?: string | null;
  description_snippet?: string | null;
  posted_at?: string | null;
  remote: boolean;
}

export type ApplicationStatus =
  | "queued"
  | "in_progress"
  | "submitted"
  | "failed"
  | "skipped"
  | "needs_review";

export interface ApplicationRecord {
  id?: number | null;
  url: string;
  company: string;
  title: string;
  status: ApplicationStatus;
  error?: string | null;
  applied_at?: string | null;
  created_at?: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  model_installed: boolean;
  model_name: string;
}

export interface ModelStatusResponse {
  installed: boolean;
  downloading: boolean;
  model_name: string;
}

export interface DiscoverRequest {
  keywords: string;
  location: string;
  remote_only: boolean;
  exclude_companies: string[];
  max_results: number;
}

export interface DiscoverResponse {
  task_id: string;
  status: string;
}

export interface DiscoveryTaskDetail {
  task_id: string;
  status: string;
  results?: JobListing[] | null;
}

export interface ApplicationsListResponse {
  total: number;
  applications: ApplicationRecord[];
}

export interface SubmitBatchResponse {
  accepted: number;
  skipped_duplicates: number;
}
