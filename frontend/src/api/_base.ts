// _base.ts — compatibility shim for Pack 7.41 creditScenario.ts
// Uses Pinia auth store (the same as src/api/client.ts).

import { useAuthStore } from "@/stores/auth"

/**
 * Build full API URL.
 * VITE_API_BASE_URL takes precedence; otherwise "/api" (nginx-proxied).
 */
export function apiUrl(path: string): string {
  const base = (import.meta as any).env?.VITE_API_BASE_URL || "/api"
  const clean = path.startsWith("/") ? path : `/${path}`
  return `${base}${clean}`
}

/**
 * Returns headers with Bearer token from the Pinia auth store.
 * Lazy import to avoid early-init issues.
 */
export function getAuthHeaders(): Record<string, string> {
  try {
    const auth = useAuthStore()
    const token = (auth as any).accessToken
    if (token) {
      return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      }
    }
  } catch {
    // store not initialised yet — fall through
  }
  return { "Content-Type": "application/json" }
}