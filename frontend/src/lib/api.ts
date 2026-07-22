import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

const ACCESS_TOKEN_KEY = "dataflow.access";
const REFRESH_TOKEN_KEY = "dataflow.refresh";

export const tokenStorage = {
  getAccess: () => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_TOKEN_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, access);
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh);
  },
  setAccess: (access: string) => localStorage.setItem(ACCESS_TOKEN_KEY, access),
  clear: () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
};

export const api = axios.create({ baseURL: `${API_BASE_URL}/api/v1` });

api.interceptors.request.use((config) => {
  const access = tokenStorage.getAccess();
  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

// A single in-flight refresh is shared across concurrent 401s so a page that fires several
// requests at once doesn't each try to refresh the token and race each other.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const refresh = tokenStorage.getRefresh();
  if (!refresh) {
    throw new Error("no refresh token available");
  }
  const response = await axios.post<{ access: string }>(
    `${API_BASE_URL}/api/v1/auth/token/refresh/`,
    { refresh },
  );
  tokenStorage.setAccess(response.data.access);
  return response.data.access;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    const isAuthEndpoint = original?.url?.includes("/auth/token");

    if (error.response?.status === 401 && original && !original._retried && !isAuthEndpoint) {
      original._retried = true;
      try {
        refreshPromise ??= refreshAccessToken().finally(() => {
          refreshPromise = null;
        });
        const access = await refreshPromise;
        original.headers.Authorization = `Bearer ${access}`;
        return api.request(original);
      } catch {
        tokenStorage.clear();
        window.location.assign("/login");
      }
    }
    return Promise.reject(error);
  },
);

/** Pulls a readable message out of an API error. Handles the common exception handler's
 * `{error: {message, details}}` envelope, the plain `{error: string}` shape some actions
 * (e.g. test-connection) return directly, and falls back to the raw error for network-level
 * failures. */
export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as
      | { error?: { message?: string; details?: unknown } | string }
      | undefined;
    if (data?.error) {
      if (typeof data.error === "string") return data.error;
      const details = data.error.details;
      if (details && typeof details === "object") {
        const parts = Object.entries(details).map(
          ([field, messages]) => `${field}: ${Array.isArray(messages) ? messages.join(", ") : messages}`,
        );
        if (parts.length) return parts.join("; ");
      }
      if (data.error.message) return data.error.message;
    }
    return error.message;
  }
  return error instanceof Error ? error.message : String(error);
}
