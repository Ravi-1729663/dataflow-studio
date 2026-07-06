// Mirrors the DRF serializers under apps/*/serializers.py — keep in sync by hand, there is no
// codegen step (the OpenAPI schema at /api/schema/ is the source of truth if these drift).

export type Role = "ADMIN" | "ENGINEER" | "ANALYST" | "VIEWER";

export interface User {
  id: number;
  username: string;
  email: string;
  role: Role;
  date_joined: string;
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMembership {
  id: string;
  user: number;
  username: string;
  role: "OWNER" | "MEMBER";
  created_at: string;
}

export type SourceType = "FILE" | "POSTGRES" | "REST_API";

export interface DataSource {
  id: string;
  name: string;
  source_type: SourceType;
  config: Record<string, unknown>;
  owner: number;
  workspace: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type Severity = "blocking" | "warning";

export interface ValidationRule {
  type:
    | "required_columns"
    | "not_null"
    | "unique"
    | "no_duplicate_rows"
    | "column_type"
    | "range"
    | "allowed_values"
    | "freshness"
    | "business_rule";
  columns?: string[];
  column?: string;
  values?: string[];
  min?: number;
  max?: number;
  expected_type?: string;
  max_age_days?: number;
  name?: string;
  expression?: string;
  severity?: Severity;
}

export interface PipelineConfig {
  validation?: { rules: ValidationRule[] };
  transform?: {
    rename?: Record<string, string>;
    cast?: Record<string, string>;
    drop_duplicates?: boolean;
    select?: string[];
  };
  target?: string;
  incremental?: { column: string; grace_seconds?: number };
}

export interface Pipeline {
  id: string;
  name: string;
  source: string;
  config: PipelineConfig;
  schedule: string;
  owner: number;
  workspace: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type RunStatus = "PENDING" | "RUNNING" | "RETRYING" | "SUCCEEDED" | "FAILED";

export interface PipelineRun {
  id: string;
  pipeline: string;
  status: RunStatus;
  started_at: string | null;
  finished_at: string | null;
  metrics: Record<string, unknown>;
  logs: unknown[];
  error: string;
  traceback: string;
  retry_count: number;
  is_dead_lettered: boolean;
  created_at: string;
}

export interface DeadLetterRecord {
  id: string;
  run: PipelineRun;
  error: string;
  traceback: string;
  created_at: string;
}

export interface QualityScorecard {
  id: string;
  run: string;
  pipeline: string;
  completeness: number;
  consistency: number;
  accuracy: number;
  overall_score: number;
  passed: boolean;
  checks: unknown;
  score_delta: number | null;
  created_at: string;
}

export interface DashboardStats {
  total_runs: number;
  succeeded: number;
  failed: number;
  retrying: number;
  pending_or_running: number;
  success_rate_percent: number | null;
  avg_duration_seconds: number | null;
  failed_jobs: Array<{
    run_id: string;
    pipeline: string;
    error: string;
    created_at: string;
  }>;
}

export interface Dataset {
  id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
}

export type MedallionLayer = "SOURCE" | "BRONZE" | "SILVER" | "GOLD";

export interface LineageNodeRef {
  layer: MedallionLayer;
  name: string;
}

export interface LineageEdge {
  pipeline: string;
  from: LineageNodeRef;
  to: LineageNodeRef;
  column_mapping: Record<string, string>;
}

export interface LineageGraph {
  dataset: string;
  nodes: LineageNodeRef[];
  edges: LineageEdge[];
}
