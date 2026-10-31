import { apiFetch } from "./client";
import type { AddRepoBody, FixJobResponse, Repo, RepoDetail, Signal, SignalDetail } from "../types";

export async function getRepos(): Promise<Repo[]> {
  return apiFetch<Repo[]>("/repositories");
}

export async function getRepoById(id: string): Promise<RepoDetail> {
  return apiFetch<RepoDetail>(`/repositories/${id}`);
}

export async function addRepo(
  body: AddRepoBody
): Promise<{ message: string; result: RepoDetail; webhookSetupError?: string }> {
  return apiFetch<{ message: string; result: RepoDetail; webhookSetupError?: string }>(
    "/repositories",
    {
      method: "POST",
      body: JSON.stringify(body),
    }
  );
}

export async function deleteRepo(
  id: string
): Promise<{ message: string; result: RepoDetail }> {
  return apiFetch<{ message: string; result: RepoDetail }>(`/repositories/${id}`, {
    method: "DELETE",
  });
}

export async function getRepoSignals(id: string): Promise<Signal[]> {
  return apiFetch<Signal[]>(`/repositories/${id}/signals`);
}

export async function fixSignal(
  repoId: string,
  signalId: string
): Promise<FixJobResponse> {
  return apiFetch<FixJobResponse>(`/repositories/${repoId}/signals/${signalId}/fix`, {
    method: "POST",
  });
}

export async function getSignalDetail(repoId: string, signalId: string): Promise<SignalDetail> {
  return apiFetch<SignalDetail>(`/repositories/${repoId}/signals/${signalId}`);
}

// Live progress for a signal's fix runs (server-sent events)
export function streamSignalProgress(repoId: string, signalId: string, after?: string): EventSource {
  const query = after ? `?after=${encodeURIComponent(after)}` : "";
  return new EventSource(`/repositories/${repoId}/signals/${signalId}/stream${query}`, {
    withCredentials: true,
  });
}
