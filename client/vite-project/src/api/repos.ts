import { apiFetch } from "./client";
import type { AddRepoBody, Repo, RepoDetail } from "../types";

export async function getRepos(): Promise<Repo[]> {
  return apiFetch<Repo[]>("/repositories");
}

export async function getRepoById(id: string): Promise<RepoDetail> {
  return apiFetch<RepoDetail>(`/repositories/${id}`);
}

export async function addRepo(body: AddRepoBody): Promise<{ message: string; result: RepoDetail }> {
  return apiFetch<{ message: string; result: RepoDetail }>("/repositories", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteRepo(id: string): Promise<{ message: string; result: RepoDetail }> {
  return apiFetch<{ message: string; result: RepoDetail }>(`/repositories/${id}`, {
    method: "DELETE",
  });
}
