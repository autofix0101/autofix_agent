// User returned by GET /auth/me → { user }
export interface User {
  github_id: number;
  github_username: string;
  email: string | null;
  avatar_url: string | null;
  created_at: string;
}

// Single repo item from GET /repositories (list)
export interface Repo {
  id: string;
  github_repo_id: string;
  name: string;
  owner: string;
  is_private: boolean;
  default_branch: string;
}

// Full repo detail from GET /repositories/:id
export interface RepoDetail {
  id: string;
  github_repo_id: string;
  name: string;
  owner: string;
  clone_url: string;
  html_url: string;
  default_branch: string;
  is_private: boolean;
  last_commit_sha: string | null;
  github_webhook_id: number | null;
  created_at: string;
  updated_at: string;
}

// Item from GET /githubrepos → { repos: GithubRepo[] }
export interface GithubRepo {
  githubRepoId: number;
  name: string;
  owner: string;
  htmlUrl: string;
  cloneUrl: string;
  defaultBranch: string;
  isPrivate: boolean;
}

// Body for POST /repositories
export interface AddRepoBody {
  githubRepoId: number;
  name: string;
  owner: string;
  cloneUrl: string;
  htmlUrl: string;
  defaultBranch: string;
  isPrivate: boolean;
}

// Signal from GET /repositories/:id/signals
export interface Signal {
  id: string;
  type: "github_issue" | "ci_failure";
  source_ref: string;
  status: "open" | "in_progress" | "resolved" | "failed" | "ignored";
  parsed_data: IssueSignalData | CiFailureSignalData;
  raw_content: string;
  created_at: string;
  // Latest fix job for this signal (null if never queued)
  job_id: string | null;
  job_status: FixJobStatus | null;
  job_error: string | null;
  pr_number: number | null;
  pr_url: string | null;
}

export type FixJobStatus =
  | "queued"
  | "reindexing"
  | "analyzing_signal"
  | "localizing"
  | "root_cause"
  | "generating"
  | "validating"
  | "awaiting_approval"
  | "pr_created"
  | "failed";

// Response from POST /repositories/:id/signals/:signalId/fix
export interface FixJobResponse {
  message: string;
  job: { id: string; status: FixJobStatus; signal_id: string };
}

export interface IssueSignalData {
  title: string;
  body: string | null;
  url: string;
  number: number;
  author: string | null;
  labels: string[];
  action: string;
  repository_full_name: string | null;
}

export interface CiFailureSignalData {
  workflow_name: string;
  run_id: number;
  run_number: number;
  branch: string;
  head_sha: string;
  conclusion: string;
  html_url: string;
  event: string;
  actor: string | null;
  repository_full_name: string | null;
}

// SSE event pushed from /signals/stream
export interface SignalEvent {
  repoId: string;
  signalId: string;
  type: "github_issue" | "ci_failure";
  title: string;
}

// ── Issue detail: GET /repositories/:id/signals/:signalId ───────────────────

// Plain-language progress message written by the agent
export interface JobEvent {
  id: string;
  job_id: string;
  stage: FixJobStatus | "pr_failed";
  message: string;
  created_at: string;
  // Resume token for the progress stream
  cursor: string;
}

// Code location the agent suspected
export interface FixCandidate {
  rank: number;
  method: string;
  file_path: string;
  start_line: number;
  end_line: number;
}

// One generate → validate attempt within a run
export interface FixAttempt {
  attempt_number: number;
  explanation: string | null;
  diff_content: string;
  diff_truncated: boolean;
  // null while the attempt is still being tested
  validation_passed: boolean | null;
  outcome: string | null;
  log_excerpt: string | null;
  created_at: string;
}

// One fix job for the signal
export interface FixRun {
  id: string;
  status: FixJobStatus;
  attempt_count: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  pull_request: { pr_number: number | null; pr_url: string; status: string } | null;
  events: JobEvent[];
  candidates: FixCandidate[];
  attempts: FixAttempt[];
}

export interface SignalDetail {
  signal: Omit<Signal, "job_id" | "job_status" | "job_error" | "pr_number" | "pr_url">;
  // Newest first
  runs: FixRun[];
}
