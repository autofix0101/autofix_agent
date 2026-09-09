import { apiFetch } from "./client";
import type { User } from "../types";

export async function getMe(): Promise<{ user: User }> {
  return apiFetch<{ user: User }>("/auth/me");
}

export async function logout(): Promise<void> {
  await apiFetch<{ message: string }>("/auth/logout", { method: "POST" });
}
