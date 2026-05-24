/** Endpoints de auth. */

import { apiFetch } from "./api";
import { useAuthStore } from "./store";
import type { LoginDemoResponse, UserOut } from "./types";

export async function loginDemo(username: string): Promise<UserOut> {
  const res = await apiFetch<LoginDemoResponse>("/auth/login-demo", {
    method: "POST",
    json: { username },
    anonymous: true,
  });
  useAuthStore.getState().setSession(res.access_token, res.user, res.expires_at);
  return res.user;
}

export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/auth/logout", { method: "POST" });
  } catch {
    // Logout idempotente — ignora 401 etc.
  }
  useAuthStore.getState().logout();
}

export async function refreshMe(): Promise<UserOut> {
  return apiFetch<UserOut>("/auth/me");
}
