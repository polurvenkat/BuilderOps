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
