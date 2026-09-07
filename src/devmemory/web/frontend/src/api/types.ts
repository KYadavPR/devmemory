// Hand-maintained mirror of the FastAPI response models (see
// src/devmemory/api/schemas.py and domain/models.py). Regenerate the raw
// OpenAPI types with `npm run gen:api` if you need to cross-check.

export type VersionStatus =
  | "SUCCESS"
  | "PARTIAL_SUCCESS"
  | "REGRESSION"
  | "ERROR"
  | "NEEDS_REVIEW"
  | "IN_PROGRESS";

export type ChangeType =
  | "added"
  | "modified"
  | "deleted"
  | "renamed"
  | "copied"
  | "type_changed";

export interface ProjectSummary {
  project_id: string;
  name: string;
  repo_path: string;
  branch: string | null;
  head_sha: string | null;
  head_subject: string | null;
  working_tree_clean: boolean;
  version_count: number;
  latest_version_id: string | null;
  latest_status: VersionStatus | null;
  latest_intent: string | null;
  head_has_version: boolean;
  last_regression_id: string | null;
  open_features: string[];
  latest_metrics: Record<string, number | null>;
  entire_installed: boolean;
  entire_enabled: boolean;
  entire_version: string | null;
  entire_agents: string[];
}

export interface VersionListItem {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  intent: string | null;
  agent: string | null;
  model: string | null;
  feature: string | null;
  git_commit: string;
  branch: string | null;
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  checkpoint_id: string | null;
  association_method: string;
  association_confidence: number;
  metrics: Record<string, number | null>;
  tests_passed: number | null;
  tests_failed: number | null;
  has_regression: boolean;
  committed_at: string | null;
  created_at: string;
}

export interface ChangedFile {
  path: string;
  change_type: ChangeType;
  old_path: string | null;
  additions: number;
  deletions: number;
  binary: boolean;
}

export interface Metric {
  name: string;
  before: number | null;
  after: number | null;
  unit: string | null;
  direction: "higher_is_better" | "lower_is_better" | "neutral";
  metadata: Record<string, unknown>;
}

export interface Regression {
  version_id: string | null;
  kind: string;
  metric: string | null;
  before: number | null;
  after: number | null;
  change_percent: number | null;
  severity: "LOW" | "MEDIUM" | "HIGH" | string;
  detail: string | null;
}

export interface TestOutcome {
  command: string | null;
  framework: string | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  errors: number;
  exit_code: number | null;
  duration_seconds: number | null;
  failing: string[];
  output: string | null;
}

export interface TokenUsage {
  input?: number | null;
  output?: number | null;
  total?: number | null;
}

export interface CheckpointReference {
  checkpoint_id: string;
  commit_sha: string | null;
  intent: string | null;
  agent: string | null;
  model: string | null;
  strategy: string | null;
  created_at: string | null;
  sessions: unknown[];
  tokens: TokenUsage;
  association_method: string;
  association_confidence: number;
  ref: string | null;
  imported: boolean;
}

export interface Analysis {
  version_id: string | null;
  summary: string;
  reasoning: string | null;
  recommendation: string | null;
  warnings: string[];
  risk: "low" | "medium" | "high" | null;
  provider: string;
  model: string | null;
  generated_at: string | null;
}

export interface DevelopmentVersion {
  version_id: string;
  version_number: number;
  project_id: string;
  intent: string | null;
  agent: string | null;
  model: string | null;
  git_commit: string;
  parent_commit: string | null;
  branch: string | null;
  feature_id: string | null;
  status: VersionStatus;
  files_changed: number;
  lines_added: number;
  lines_removed: number;
  changed_files: ChangedFile[];
  primary_checkpoint: CheckpointReference | null;
  checkpoint_ids: string[];
  entire_association_method: string;
  entire_association_confidence: number;
  tests: TestOutcome | null;
  metrics: Metric[];
  regressions: Regression[];
  analysis: Analysis | null;
  artifacts: unknown[];
  doc_flags: unknown[];
  environment: unknown | null;
  run_id: string | null;
  created_at: string;
  committed_at: string | null;
}

export interface TraceNode {
  key: string;
  label: string;
  value: string;
  detail: string | null;
  source: string;
  status: string | null;
}

export interface DevelopmentTrace {
  version_id: string;
  nodes: TraceNode[];
}

export interface MetricChange {
  name: string;
  before: number | null;
  after: number | null;
  delta: number | null;
  unit: string | null;
  direction: string;
}

export interface DiffStat {
  files_changed: number;
  additions: number;
  deletions: number;
}

export interface ComparisonResponse {
  from_version: string;
  to_version: string;
  from_commit: string;
  to_commit: string;
  stat: DiffStat;
  files: ChangedFile[];
  diff_text: string;
  metric_changes: MetricChange[];
  test_changes: Record<string, number | null>;
  status_from: VersionStatus;
  status_to: VersionStatus;
  feature_from: string | null;
  feature_to: string | null;
  checkpoint_from: string | null;
  checkpoint_to: string | null;
}

export interface FeatureHistoryPoint {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  metrics: Record<string, number | null>;
  committed_at: string | null;
}

export interface FeatureDetail {
  feature_id: string;
  name: string;
  status: "COMPLETE" | "IN_PROGRESS" | "NOT_STARTED" | "NEEDS_REVIEW" | string;
  derived_from: string | null;
  version_count: number;
  latest_metrics: Record<string, number | null>;
  history: FeatureHistoryPoint[];
}

export interface SearchHit {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  intent: string | null;
  agent: string | null;
  feature: string | null;
  git_commit: string;
  snippet: string | null;
}

export interface SearchResponse {
  query: string;
  count: number;
  results: SearchHit[];
}

export interface PreviousAttempt {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  intent: string | null;
  agent: string | null;
  feature: string | null;
  git_commit: string;
  files: string[];
  change_summary: string;
  result: string;
  recommendation: string | null;
  is_adverse: boolean;
  score: number;
  matched_on: string[];
}

export interface SymbolRef {
  name: string;
  file_path: string;
  kind: string;
  start_line: number | null;
  depth: number;
  via: string | null;
}

export interface SymbolImpact {
  query: string;
  resolved: boolean;
  callers_total: number;
  callees_total: number;
  type_consumers_total: number;
  callers: SymbolRef[];
  callees: SymbolRef[];
  cochange_files: string[];
  definitions: SymbolRef[];
  blast_radius: number;
}

export interface ChangeGuidance {
  verdict: string;
  headline: string;
  files: string[];
  intent: string | null;
  feature: string | null;
  related_attempts: PreviousAttempt[];
  warnings: string[];
  recommendations: string[];
  graph_available: boolean;
  symbol_impacts: SymbolImpact[];
  max_blast_radius: number;
}

export interface TrendPoint {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  test_pass_rate: number | null;
  key_metric: number | null;
}

export interface RegressionRow {
  version_id: string;
  intent: string | null;
  feature: string | null;
  agent: string | null;
  git_commit: string;
  severity: string;
  detail: string;
}

export interface FeatureRow {
  feature: string;
  attempts: number;
  successes: number;
  regressions: number;
  success_rate: number;
  latest_status: VersionStatus;
}

export interface FileChurnRow {
  path: string;
  changes: number;
  adverse_changes: number;
  risk: number;
}

export interface AgentRow {
  agent: string;
  versions: number;
  success_rate: number;
  regressions: number;
  tokens_per_success: number | null;
}

export interface FailedApproach {
  signature: string[];
  occurrences: number;
  version_ids: string[];
  example_intent: string | null;
}

export interface AnalyticsSummary {
  source: "local" | "databricks" | string;
  project: string;
  version_count: number;
  regression_count: number;
  success_rate: number;
  regressions: RegressionRow[];
  features: FeatureRow[];
  file_churn: FileChurnRow[];
  agents: AgentRow[];
  trend: TrendPoint[];
  failed_approaches: FailedApproach[];
}

export interface VersionBrief {
  version_id: string;
  version_number: number;
  status: VersionStatus;
  is_adverse: boolean;
  intent: string | null;
  feature: string | null;
  agent: string | null;
  model: string | null;
  git_commit: string;
  files_changed: number;
  changed_paths: string[];
  lines_added: number;
  lines_removed: number;
  tests: string | null;
  metrics: string[];
  regressions: string[];
  committed_at: string | null;
}

export interface ProjectBrief {
  project: string;
  repo_path: string;
  branch: string | null;
  head_commit: string | null;
  head_subject: string | null;
  working_tree_clean: boolean;
  head_has_version: boolean;
  entire_installed: boolean;
  entire_enabled: boolean;
  version_count: number;
  success_rate: number;
  open_features: string[];
  last_regression_id: string | null;
  latest: VersionBrief | null;
  recent_adverse: VersionBrief[];
  notes: string[];
}

export interface ChangedEntity {
  path: string;
  language: string | null;
  file_status: string;
  change_type: string;
  kind: string;
  name: string;
  dependents_count: number;
  old_signature: string | null;
  new_signature: string | null;
  line: number | null;
}

export interface GraphImpact {
  version_id: string | null;
  base_commit: string;
  head_commit: string;
  entities: ChangedEntity[];
  generated_at: string | null;
  entity_count: number;
  max_dependents: number;
}

// --- state-aware coding loop ------------------------------------------------

export type TaskStatus = "IN_PROGRESS" | "NEEDS_WORK" | "READY" | "BLOCKED";
export type RequirementStatus = "COMPLETE" | "PARTIAL" | "INCOMPLETE" | "UNKNOWN";
export type TestRunStatus =
  | "NOT_RUN"
  | "PASSED"
  | "FAILED"
  | "FAILED_TO_PARSE"
  | "ERROR";

export interface StateTask {
  id: string;
  goal: string;
  status: TaskStatus;
}

export interface StateRequirement {
  id: string;
  description: string;
  status: RequirementStatus;
  reason: string;
}

export interface StateCheckpoint {
  current_id: string | null;
  last_committed_id: string | null;
  session_id: string | null;
  commit_sha: string | null;
  association: string | null;
}

export interface StateGit {
  branch: string;
  commit_sha: string | null;
  commit_subject: string | null;
  files_changed: number;
  lines_added: number;
  lines_deleted: number;
  working_tree_clean: boolean;
  available: boolean;
  reason: string | null;
}

export interface StateTests {
  command: string | null;
  passed: number;
  failed: number;
  skipped: number;
  status: TestRunStatus;
  exit_code: number | null;
  output_path: string | null;
}

export interface StateImpact {
  affected_files: number;
  affected_tests: number;
  available: boolean;
  reason: string | null;
  details: string[];
}

export interface StateIssue {
  id: number | null;
  description: string;
  kind: string;
  blocking: boolean;
}

export interface NormalizedState {
  task: StateTask;
  requirements: StateRequirement[];
  checkpoint: StateCheckpoint;
  git: StateGit;
  tests: StateTests;
  impact: StateImpact;
  unresolved: StateIssue[];
  findings: string[];
  recommended_focus: string[];
  overall_status: TaskStatus;
  snapshot_id: number | null;
  refreshed_at: string | null;
}

export interface TaskSummary {
  id: string;
  goal: string;
  status: TaskStatus;
  branch: string;
  requirements_total: number;
  requirements_complete: number;
  test_command: string | null;
  updated_at: string | null;
}

export interface SnapshotSummary {
  id: number | null;
  overall_status: TaskStatus;
  commit_sha: string | null;
  checkpoint_id: string | null;
  tests_passed: number;
  tests_failed: number;
  tests_status: TestRunStatus;
  requirements_total: number;
  requirements_complete: number;
  created_at: string | null;
}

export interface ProjectBriefDoc {
  content: string;
  updated_at: string | null;
}

export interface GenieStatus {
  configured: boolean;
  mode: "genie" | "local" | "none";
  engine: string | null;
  space_id: string | null;
  reason: string | null;
}

export interface GenieAnswer {
  conversation_id: string | null;
  message_id: string | null;
  question: string;
  text: string | null;
  sql: string | null;
  sql_description: string | null;
  columns: string[];
  rows: unknown[][];
  row_count: number | null;
  truncated: boolean;
  error: string | null;
}
