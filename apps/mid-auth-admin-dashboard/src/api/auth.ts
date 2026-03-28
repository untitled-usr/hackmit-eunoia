import { apiFetch } from "./client";

export type LoginPayload = {
  username: string;
  password: string;
};

export type AuthMeResponse = {
  authenticated: boolean;
  username?: string | null;
};

export async function login(payload: LoginPayload): Promise<{ ok: boolean; username: string; expires_in: number }> {
  return await apiFetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function logout(): Promise<void> {
  await apiFetch("/auth/logout", { method: "POST" });
}

export async function me(): Promise<AuthMeResponse> {
  return await apiFetch<AuthMeResponse>("/auth/me", { method: "GET" });
}

