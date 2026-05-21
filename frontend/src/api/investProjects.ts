/**
 * Invest projects storage — Firebase-style JSON KV.
 * Path scheme: companies/{company_code}/projects/{num} → ProjectRow patch.
 *
 * Used to persist user edits over the static `ngmk-invest-seed.ts` baseline.
 */
import { api } from "./client";

const BASE = "/invest-projects-storage";

export async function getStoredProject(companyCode: string, num: number): Promise<Record<string, any> | null> {
  try {
    const { data } = await api.get(`${BASE}/root/companies/${companyCode}/projects/${num}.json`);
    return data ?? null;
  } catch (e: any) {
    if (e?.response?.status === 404) return null;
    throw e;
  }
}

export async function saveProject(
  companyCode: string,
  num: number,
  payload: Record<string, any>,
): Promise<void> {
  await api.put(`${BASE}/root/companies/${companyCode}/projects/${num}.json`, payload);
}

export async function patchProject(
  companyCode: string,
  num: number,
  patch: Record<string, any>,
): Promise<void> {
  await api.patch(`${BASE}/root/companies/${companyCode}/projects/${num}.json`, patch);
}
