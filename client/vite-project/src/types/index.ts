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
  status: "open" | "in_progress" | "resolved" | "ignored";
  parsed_data: IssueSignalData | CiFailureSignalData;
  raw_content: string;
  created_at: string;
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
