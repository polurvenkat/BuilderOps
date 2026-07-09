export interface StageCheckOut {
  status: string;
  source: string;
  detail: Record<string, unknown> | null;
  updated_at: string | null;
}

export interface RepoOut {
  id: number;
  name: string;
  domain: string | null;
  team: string | null;
  migration_wave: string;
  github_url: string;
  last_synced_at: string | null;
  dockerize_eligible?: boolean | null;
  e2e_test_plan_id?: number | null;
  app_count?: number | null;
  primary_language?: string | null;
  complexity?: "low" | "medium" | "high" | null;
  stages: Record<string, StageCheckOut>;
  current_stage: string;
  is_stuck: boolean;
  dwell_days: number | null;
  stuck_reason: string | null;
}

export interface ListReposParams {
  stage?: string;
  domain?: string;
  sort?: "dwell_desc";
}

export interface RepoPatchIn {
  domain?: string;
  team?: string;
  migration_wave?: "not_started" | "pilot" | "rolling_out" | "migrated";
  dockerize_eligible?: boolean;
  e2e_test_plan_id?: number;
  ado_pipeline_id?: number;
  app_count?: number;
  new_name?: string;
}

export interface OnboardingLogIn {
  engineer_name: string;
  hours: number;
}

export interface OnboardingLogOut {
  id: number;
  repo_id: number;
  engineer_name: string;
  hours: number;
  logged_at: string;
}

export interface OnboardingSummaryOut {
  entries: OnboardingLogOut[];
  median_hours: number | null;
}

export interface PipelineStageStatusOut {
  name: string;
  status: string;
  pending_approval_description: string | null;
}

export interface PipelineStatusOut {
  stages: PipelineStageStatusOut[];
}
