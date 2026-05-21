/**
 * UzAssets Platform SDK — TypeScript (Phase 5.7).
 *
 * Minimal hand-rolled wrapper around fetch + JWT auth. Companion to the
 * auto-generated `types.generated.ts` (run `npm run sdk:types` to refresh).
 *
 * Designed to be tree-shakable and zero-dependency apart from `fetch` (which
 * is available natively in browsers and Node 18+).
 *
 * Usage:
 *   import { UzAssetsClient } from "@/sdk";
 *
 *   const sdk = new UzAssetsClient({
 *     baseUrl: "https://platform.uz-assets.uz/api",
 *     token: "<your_jwt>",
 *   });
 *
 *   const companies = await sdk.companies.list();
 *   const detail = await sdk.companies.get("ngmk");
 *   const ratings = await sdk.ratings.byCompany(companyId);
 */

export interface UzAssetsClientOptions {
  baseUrl?: string;
  token?: string | (() => string | null);
  /** Custom fetch impl (e.g. node-fetch for old Node). */
  fetch?: typeof fetch;
  /** Optional callback for 401 — re-auth flow lives outside the SDK. */
  onUnauthorized?: () => void;
  /** Custom timeout in ms (default 30s). */
  timeout?: number;
}

export class UzAssetsApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
    this.name = "UzAssetsApiError";
  }
}

const DEFAULT_BASE = "https://platform.uz-assets.uz/api";

export class UzAssetsClient {
  private baseUrl: string;
  private tokenProvider: () => string | null;
  private fetchImpl: typeof fetch;
  private timeout: number;
  private onUnauthorized?: () => void;

  // Resource namespaces — initialized in constructor
  readonly companies: CompaniesResource;
  readonly library:   LibraryResource;
  readonly ratings:   RatingsResource;
  readonly financials:FinancialsResource;
  readonly catalog:   CatalogResource;

  constructor(opts: UzAssetsClientOptions = {}) {
    this.baseUrl = (opts.baseUrl || DEFAULT_BASE).replace(/\/$/, "");
    this.tokenProvider = typeof opts.token === "function"
      ? opts.token
      : (() => (opts.token as string | null) ?? null);
    this.fetchImpl = opts.fetch || globalThis.fetch.bind(globalThis);
    this.timeout = opts.timeout ?? 30_000;
    this.onUnauthorized = opts.onUnauthorized;

    this.companies = new CompaniesResource(this);
    this.library   = new LibraryResource(this);
    this.ratings   = new RatingsResource(this);
    this.financials= new FinancialsResource(this);
    this.catalog   = new CatalogResource(this);
  }

  async request<T = unknown>(
    method: string,
    path: string,
    body?: unknown,
    extraHeaders?: Record<string, string>,
  ): Promise<T> {
    const url = `${this.baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "Accept":       "application/json",
      ...(extraHeaders || {}),
    };
    const tok = this.tokenProvider();
    if (tok && !headers.Authorization) headers.Authorization = `Bearer ${tok}`;

    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), this.timeout);
    let resp: Response;
    try {
      resp = await this.fetchImpl(url, {
        method,
        headers,
        body: body == null ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
    } finally {
      clearTimeout(t);
    }

    if (resp.status === 401) this.onUnauthorized?.();

    let parsedBody: any = undefined;
    const text = await resp.text();
    if (text) {
      try { parsedBody = JSON.parse(text); }
      catch { parsedBody = text; }
    }

    if (!resp.ok) {
      const detail = (parsedBody && typeof parsedBody === "object" && "detail" in parsedBody)
        ? parsedBody.detail
        : (typeof parsedBody === "string" ? parsedBody : `HTTP ${resp.status}`);
      throw new UzAssetsApiError(resp.status, String(detail), parsedBody);
    }

    return parsedBody as T;
  }
}

// ── Resource implementations ────────────────────────────────────────

class CompaniesResource {
  constructor(private c: UzAssetsClient) {}
  list() {
    return this.c.request<any[]>("GET", "/companies");
  }
  get(codeOrId: string) {
    return this.c.request<any>("GET", `/companies/${encodeURIComponent(codeOrId)}`);
  }
}

class LibraryResource {
  constructor(private c: UzAssetsClient) {}
  list(params: { sector?: string; search?: string; limit?: number; offset?: number } = {}) {
    const qs = new URLSearchParams();
    if (params.sector) qs.set("sector", params.sector);
    if (params.search) qs.set("search", params.search);
    if (params.limit != null) qs.set("limit", String(params.limit));
    if (params.offset != null) qs.set("offset", String(params.offset));
    const s = qs.toString();
    return this.c.request<any>("GET", `/library/companies${s ? "?" + s : ""}`);
  }
  detail(companyId: string) {
    return this.c.request<any>("GET", `/library/companies/${companyId}`);
  }
  updateField(companyId: string, fieldCode: string, value: unknown, reason?: string) {
    return this.c.request<any>(
      "PATCH",
      `/library/companies/${companyId}/fields/${fieldCode}`,
      { value, reason: reason ?? null },
    );
  }
  fields() {
    return this.c.request<any[]>("GET", "/field-definitions");
  }
  tabs() {
    return this.c.request<any[]>("GET", "/library-tabs");
  }
}

class RatingsResource {
  constructor(private c: UzAssetsClient) {}
  byCompany(companyCodeOrId: string) {
    return this.c.request<any>("GET", `/companies/${encodeURIComponent(companyCodeOrId)}/ratings`);
  }
  list(params: { company_id?: string; agency?: string; is_esg?: boolean } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v != null) qs.set(k, String(v));
    }
    const s = qs.toString();
    return this.c.request<any>("GET", `/ratings${s ? "?" + s : ""}`);
  }
}

class FinancialsResource {
  constructor(private c: UzAssetsClient) {}
  list(params: { company_code?: string; year?: number; standard?: "IFRS" | "NSBU" } = {}) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v != null) qs.set(k, String(v));
    }
    const s = qs.toString();
    return this.c.request<any[]>("GET", `/financials${s ? "?" + s : ""}`);
  }
  get(reportId: string) {
    return this.c.request<any>("GET", `/financials/${reportId}`);
  }
}

class CatalogResource {
  constructor(private c: UzAssetsClient) {}
  summary() {
    return this.c.request<any>("GET", "/api-catalog/summary");
  }
  openapi() {
    return this.c.request<any>("GET", "/api-catalog/openapi.json");
  }
  byCompany(companyId: string, tab?: string) {
    const q = tab ? `?tab=${encodeURIComponent(tab)}` : "";
    return this.c.request<any>("GET", `/api-catalog/by-company/${companyId}${q}`);
  }
  status() {
    return this.c.request<any>("GET", "/api-catalog/status");
  }
}

// ── Re-export generated types if present ─────────────────────────────
// `types.generated.ts` is created by `npm run sdk:types`. Don't fail at
// import time if it's missing — keep the SDK usable without codegen.
export type {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  default as ApiTypes,
} from "./types.generated";
