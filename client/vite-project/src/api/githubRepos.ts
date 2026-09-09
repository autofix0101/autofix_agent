import { apiFetch } from "./client";
import type { GithubRepo } from "../types";

export async function getGithubRepos(): Promise<{ repos: GithubRepo[] }> {
  return apiFetch<{ repos: GithubRepo[] }>("/githubrepos");
}
