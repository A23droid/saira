/**
 * Centralized API layer for the FastAPI backend.
 *
 * Every request:
 *  - sends `credentials: "include"` so the browser attaches the httpOnly
 *    `access_token` / `refresh_token` cookies the backend sets on login —
 *    there is no token stored in JS anywhere in this app.
 *  - on a 401 (other than from `/auth/refresh` or `/auth/login` itself),
 *    attempts one silent `/auth/refresh` and retries the original request
 *    once. Concurrent 401s share a single in-flight refresh call instead of
 *    each firing their own (which would race against the rotation and
 *    invalidate each other).
 *
 * UI code should never call `fetch` directly against the backend — go
 * through `apiFetch` (or the typed helpers in `lib/api/auth.ts`) so this
 * behavior stays in one place.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  errors?: unknown;

  constructor(status: number, message: string, errors?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errors = errors;
  }
}

let refreshPromise: Promise<boolean> | null = null;

function performRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      credentials: "include",
    })
      .then((res) => res.ok)
      .catch(() => false)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

interface ApiFetchOptions extends RequestInit {
  /** Internal flag — set on the retried call so we never loop more than once. */
  _isRetry?: boolean;
}

const NO_RETRY_PATHS = ["/auth/refresh", "/auth/login", "/auth/register"];

export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { _isRetry, headers, body, ...rest } = options;

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    body,
    credentials: "include",
    headers: {
      ...(body && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
  });

  if (res.status === 401 && !_isRetry && !NO_RETRY_PATHS.includes(path)) {
    const refreshed = await performRefresh();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, _isRetry: true });
    }
  }

  if (!res.ok) {
    const payload = await res.json().catch(() => null);
    throw new ApiError(
      res.status,
      payload?.detail ?? `Request failed with status ${res.status}.`,
      payload?.errors
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
