/**
 * Axios instance for TWA (Phase C).
 *
 * - baseURL = /api (proxied by nginx to FastAPI)
 * - attaches Bearer token from localStorage on every request
 * - on 401 → clears token and bumps user back to /twa/login
 */
import axios from "axios";

const LS_TOKEN = "uza-twa-access";

export const api = axios.create({
  baseURL: "/api",
  timeout: 20_000,
});

api.interceptors.request.use((config) => {
  const tok = localStorage.getItem(LS_TOKEN);
  if (tok && config.headers) {
    config.headers["Authorization"] = `Bearer ${tok}`;
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401) {
      localStorage.removeItem(LS_TOKEN);
      if (!location.pathname.endsWith("/twa/login")) {
        const next = encodeURIComponent(location.pathname + location.search);
        location.href = `/twa/login?next=${next}`;
      }
    }
    return Promise.reject(err);
  },
);
