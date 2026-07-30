import { apiFetch, API_BASE_URL } from "@/lib/api/client";

export interface AuthUser {
  id: string;
  name: string;
  email: string;
  provider: "local" | "google" | "orcid";
  avatar_url: string | null;
  is_active: boolean;
  created_at: string;
}

export function registerRequest(name: string, email: string, password: string) {
  return apiFetch<AuthUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ name, email, password }),
  });
}

export function loginRequest(email: string, password: string) {
  return apiFetch<AuthUser>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function logoutRequest() {
  return apiFetch<{ detail: string }>("/auth/logout", { method: "POST" });
}

export function getCurrentUserRequest() {
  return apiFetch<AuthUser>("/auth/me");
}

export function updateProfileRequest(name: string) {
  return apiFetch<AuthUser>("/auth/me", {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
}

export function uploadAvatarRequest(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<AuthUser>("/auth/me/avatar", {
    method: "POST",
    body: formData,
  });
}

/** Full-page navigation target for "Sign in with Google" — not a fetch call,
 * since the OAuth flow requires an actual browser redirect to Google. */
export const googleLoginUrl = `${API_BASE_URL}/auth/google/login`;
