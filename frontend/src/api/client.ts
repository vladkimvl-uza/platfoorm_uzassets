import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import { useAuthStore } from "@/stores/auth";
import router from "@/router";

// API base URL.
// Default `/api` is a relative path — works in single-origin deployments
// where nginx proxies /api/* → backend (recommended for production).
// Override with VITE_API_BASE_URL only for raw-Vite local dev where nginx
// is not in the path (e.g. http://localhost:8000).
const baseURL = import.meta.env.VITE_API_BASE_URL || "/api";

export const api = axios.create({
  baseURL,
  timeout: 30000,
  headers: { "Content-Type": "application/json" },
});

// =====================================================================
// Request: attach JWT
// =====================================================================
api.interceptors.request.use((config) => {
  const auth = useAuthStore();
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }
  return config;
});

// =====================================================================
// Response: on 401 try to refresh once, then retry original request
// =====================================================================
let refreshing: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const auth = useAuthStore();
  if (!auth.refreshToken) return null;
  try {
    // Direct fetch to avoid the interceptor recursion
    const resp = await axios.post(
      `${baseURL}/auth/refresh`,
      { refresh_token: auth.refreshToken },
      { headers: { "Content-Type": "application/json" } },
    );
    const tokens = resp.data;
    auth.setTokens(tokens);
    return tokens.access_token;
  } catch {
    auth.clear();
    return null;
  }
}

// =====================================================================
// Moderation-queued helper
// =====================================================================
// When a write endpoint is intercepted by the moderation gate, the
// backend returns HTTP 202 with body `{queued: true, submission_id, ...}`.
// We surface that via a toast here and tag the response so callers know
// not to treat the body as the "real" entity. Each save handler can opt-in
// to ignore queued responses (treat as silent success) by checking
// `resp.data?.__moderation_queued`.

/** Tag added by the response interceptor on queued submissions. */
export interface ModerationQueuedTag {
  __moderation_queued: true;
  submission_id: string;
  status: string;
  message?: string;
}

export function isModerationQueued(value: unknown): value is ModerationQueuedTag {
  return !!(value && typeof value === "object" && (value as any).__moderation_queued === true);
}

api.interceptors.response.use(
  (resp) => {
    const d = resp.data as { queued?: boolean; submission_id?: string; status?: string; message?: string } | undefined;
    if (d && d.queued === true && d.submission_id) {
      // Lazy import — toast composable imports stores, avoid circular at module init.
      import("@/composables/useToast")
        .then(({ useToast }) => {
          const toast = useToast();
          const idShort = d.submission_id!.slice(0, 8);
          toast.info(
            (d.message || "Изменение отправлено на модерацию") + ` · #${idShort}`,
            5000,
          );
        })
        .catch(() => { /* ignore */ });
      // Tag the response data so callers can branch cleanly.
      resp.data = {
        __moderation_queued: true,
        submission_id: d.submission_id,
        status: d.status || "pending",
        message: d.message,
      } as ModerationQueuedTag;
    }
    return resp;
  },
  async (err: AxiosError) => {
    const original = err.config as InternalAxiosRequestConfig & { _retried?: boolean };

    // Only handle 401 once per request, and never retry the refresh endpoint itself
    if (
      err.response?.status === 401 &&
      original &&
      !original._retried &&
      !original.url?.includes("/auth/refresh") &&
      !original.url?.includes("/auth/login")
    ) {
      original._retried = true;

      // Coalesce concurrent 401s into a single refresh call
      if (!refreshing) {
        refreshing = performRefresh();
      }
      const newAccess = await refreshing;
      refreshing = null;

      if (newAccess) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newAccess}`;
        return api(original);
      }

      // Refresh failed — bounce to login
      void router.push({ name: "login" });
    }

    return Promise.reject(err);
  },
);
