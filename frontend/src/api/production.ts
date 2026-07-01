import { api } from "@/api/client";

export interface ProdLine {
  name: string;
  unit?: string | null;
  total?: boolean;
  parent?: number | null;
  baseN?: number | null; baseM?: number | null;
  planN?: number | null; planM?: number | null;
  expN?: number | null; expM?: number | null;
  factN?: number | null; factM?: number | null;
  growthM?: number | null; growthN?: number | null; growthPct?: number | null;
  execPct?: number | null; execState?: "pct" | "nofact" | "noplan"; execBasis?: "money" | "natura";
  execKind?: "fact" | "forecast";
}

export interface ProdCompany {
  k: string; n: string; s: string; sector_color: string;
  unit?: string | null;
  baseM?: number | null; planM?: number | null; expM?: number | null; factM?: number | null;
  baseN?: number | null; planN?: number | null; expN?: number | null; factN?: number | null;
  execPct?: number | null; execState: "pct" | "nofact" | "noplan"; execBasis?: "money" | "natura";
  execKind?: "fact" | "forecast";
  growthPct?: number | null;
  has_data: boolean;
  lines: ProdLine[];
}

export interface ProdKpis {
  present: number; with_data: number;
  plan_total: number; expect_total: number; fact_total?: number; exec_pct: number | null;
  over: number; under: number; ontarget: number; overpar: number;
}

export interface ProdOverview {
  companies: ProdCompany[];
  kpis: ProdKpis;
  year: number;
  period: string;
}

export interface ProdCompanyDetail {
  company: ProdCompany;
  year: number;
  period: string;
  years: number[];
  combos: { year: number; period: string }[];
}

export const productionApi = {
  overview: (year: number, period: string) =>
    api.get<ProdOverview>("/production/overview", { params: { year, period } }).then((r) => r.data),
  available: () =>
    api.get<{ years: number[]; combos: { year: number; period: string }[] }>("/production/available").then((r) => r.data),
  // Одна компания — для вкладки БП в карточке компании (scoped на бэке).
  companyDetail: (code: string, year: number, period: string) =>
    api.get<ProdCompanyDetail>(`/production/companies/${encodeURIComponent(code)}`, { params: { year, period } }).then((r) => r.data),
  upsertCompany: (code: string, body: { year: number; period: string; lines: ProdLine[] }) =>
    api.put(`/production/companies/${encodeURIComponent(code)}`, body).then((r) => r.data),
};
