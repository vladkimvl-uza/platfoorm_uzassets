/**
 * Per-company invest-projects storage (Pack 154).
 *
 * Backend route: /invest-projects-storage/root/{path:path}
 * Stores arbitrary JSON tree; we put the full InvestProjectsCompanyData
 * object at `companies/<code>/invest_data`.
 *
 * Path convention (kept consistent with backend _enforce_path_scope, which
 * requires the first segment to be `companies/<code>` for non-admin scoped
 * users so they can only touch their own data).
 */
import { api } from "./client";
import type { InvestProjectsCompanyData } from "@/data/ngmk-invest-seed";

const ROOT = "/invest-projects-storage/root";
const KEY = "invest_data";

function pathFor(companyCode: string): string {
  const code = (companyCode || "").trim().toLowerCase();
  if (!code) throw new Error("companyCode is required");
  return `${ROOT}/companies/${encodeURIComponent(code)}/${KEY}`;
}

/** Load per-company invest-projects payload from backend. Returns null if
 *  nothing stored yet (or 404 from the namespace endpoint). */
export async function loadCompanyInvestData(
  companyCode: string,
): Promise<InvestProjectsCompanyData | null> {
  try {
    const { data } = await api.get(pathFor(companyCode));
    if (!data || typeof data !== "object") return null;
    return data as InvestProjectsCompanyData;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

/** Save (overwrite) per-company invest-projects payload. */
export async function saveCompanyInvestData(
  companyCode: string,
  payload: InvestProjectsCompanyData,
): Promise<void> {
  await api.put(pathFor(companyCode), payload);
}

/** Wipe per-company invest-projects payload. Idempotent — backend returns
 *  `{ok: true, removed: false}` if nothing was stored. */
export async function deleteCompanyInvestData(companyCode: string): Promise<{
  ok: boolean; removed: boolean;
}> {
  const { data } = await api.delete(pathFor(companyCode));
  return data;
}
