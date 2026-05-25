// frontend/src/views/finmodel/fmUapSeed.ts
//
// Pack 7.9t: REAL UAP financial-model data ported 1:1 from
// "Financial model - example (Airport) (2).xlsx" supplied 2026-05-23.
// Source sheets: Volume, Revenue, "Cost of sales and OPEX",
// "Balance sheet schedules". Horizon 2022..2030 (4 fact + 5 forecast).
// Sums are in UZSm (млн сум) unless explicitly marked.

export type ScenarioId = "base" | "opt" | "str";

export interface FmHorizon {
  startYear: number;
  endYear: number;
  factYears: number[];
  forecastYears: number[];
}

export interface FmYearMap { [year: number]: number }

export interface FmMacro {
  inflation: FmYearMap;
  usInflation: FmYearMap;
  fx: FmYearMap;
}

export interface FmDriver {
  id: string;
  name: string;
  unit: string;
  values: FmYearMap;
  volumeRef?: string;
}

export interface FmCost extends FmDriver {
  type: "fixed" | "variable" | "semi-var";
  isDA?: boolean;
}

export interface FmCapex extends FmDriver {}

export interface FmWC {
  dso: number;
  dio: number;
  dpo: number;
  dap: number;
}

export interface FmDebt {
  ltDebt: FmYearMap;
  stDebt: FmYearMap;
  interestRate: number;
}

export interface FmEquity {
  shareCapital: FmYearMap;
  openingCash: number;
  openingRE: number;
}

export interface FmAirport {
  name: string;
  load: number;
}

export interface FmAssumptions {
  taxRate: number;
  wacc: number;
  dividendPayout: number;
  terminalGrowth: number;
  riskFreeRate: number;
  beta: number;
  marketRiskPremium: number;
  countryAdjustment: number;
  effectiveCostOfDebt: number;
}

export interface FmScenarioModel {
  horizon: FmHorizon;
  macro: FmMacro;
  drivers: {
    volumes: FmDriver[];
    tariffs: FmDriver[];
    costs: FmCost[];
    capex: FmCapex[];
    wc: FmWC;
    debt: FmDebt;
    equity: FmEquity;
  };
  revenueDirect: FmYearMap;
  assumptions: FmAssumptions;
  airportLoad: FmAirport[];
}

export type FmAllScenarios = Record<ScenarioId, FmScenarioModel>;

// ─────────────────────────────────────────────────────────────────
// HORIZON: 4 history years + 5 forecast (как в исходной таблице)
// ─────────────────────────────────────────────────────────────────
const FACT_YEARS = [2022, 2023, 2024, 2025];
const FORECAST_YEARS = [2026, 2027, 2028, 2029, 2030];
const ALL_YEARS = [...FACT_YEARS, ...FORECAST_YEARS];

const HORIZON: FmHorizon = {
  startYear: 2022,
  endYear: 2030,
  factYears: FACT_YEARS,
  forecastYears: FORECAST_YEARS,
};

// Helper: build FmYearMap from positional array (length === ALL_YEARS.length)
function ym(values: number[]): FmYearMap {
  const m: FmYearMap = {};
  ALL_YEARS.forEach((y, i) => { m[y] = values[i] ?? 0; });
  return m;
}

// ─────────────────────────────────────────────────────────────────
// MACRO — Excel sheet "Balance sheet schedules" R8/R9/R12
// 2022..2030
// ─────────────────────────────────────────────────────────────────
const MACRO_BASE: FmMacro = {
  inflation:   ym([0.11, 0.10, 0.09, 0.04, 0.075, 0.063, 0.054, 0.053, 0.05]),
  usInflation: ym([0.08, 0.04, 0.03, 0.02, 0.027, 0.021, 0.022, 0.022, 0.022]),
  fx:          ym([11045, 11736, 12652, 12894, 13640, 14237, 14714, 15105, 15519]),
};

// ─────────────────────────────────────────────────────────────────
// VOLUMES (Excel "Revenue" R31-R38 — Total traffic across 11 airports)
// Раздел Volume sheet даёт per-airport breakdown (он зафиксирован
// ниже в airportLoad). Здесь — total volumes per category.
// ─────────────────────────────────────────────────────────────────
const VOLUMES: FmDriver[] = [
  {
    id: "vol_pax_int", name: "Пассажиры · международные", unit: "тыс. PAX",
    values: ym([236513, 252094, 223465, 229927, 235499, 235499, 235499, 235499, 235499]),
  },
  {
    id: "vol_pax_dom", name: "Пассажиры · внутренние", unit: "тыс. PAX",
    values: ym([551863, 588219, 521419, 536497, 549499, 549499, 549499, 549499, 549499]),
  },
  {
    id: "vol_pax_trn", name: "Пассажиры · транзит", unit: "тыс. PAX",
    values: ym([8946, 8959, 8399, 8013, 8579, 8579, 8579, 8579, 8579]),
  },
  {
    id: "vol_mvm", name: "Aircraft movements", unit: "ед.",
    values: ym([425856, 495549, 491511, 579919, 498208, 498208, 498208, 498208, 498208]),
  },
  {
    id: "vol_cargo", name: "Карго handled", unit: "тонн",
    values: ym([34443, 40316, 41997, 46077, 40708, 40708, 40708, 40708, 40708]),
  },
  {
    id: "vol_fuel", name: "Fuelling operations", unit: "операций",
    values: ym([50612, 49519, 46984, 50311, 49356, 49356, 49356, 49356, 49356]),
  },
  {
    id: "vol_gh", name: "Ground handling operations", unit: "операций",
    values: ym([425856, 495549, 491511, 579919, 498208, 498208, 498208, 498208, 498208]),
  },
];

// ─────────────────────────────────────────────────────────────────
// TARIFFS — Excel "Revenue" R45-R51 (UZS thous. per unit)
// volumeRef связывает с VOLUMES для Revenue = Σ vol × tarf
// ─────────────────────────────────────────────────────────────────
const TARIFFS: FmDriver[] = [
  {
    id: "tar_pax_int", name: "International pass. fee", unit: "тыс. сум/PAX",
    volumeRef: "vol_pax_int",
    values: ym([1.439, 1.570, 1.805, 1.789, 1.923, 2.067, 2.223, 2.389, 2.568]),
  },
  {
    id: "tar_pax_dom", name: "Domestic pass. fee", unit: "тыс. сум/PAX",
    volumeRef: "vol_pax_dom",
    values: ym([1.439, 1.570, 1.805, 1.789, 1.923, 2.067, 2.223, 2.389, 2.568]),
  },
  {
    id: "tar_pax_trn", name: "Transit pass. fee", unit: "тыс. сум/PAX",
    volumeRef: "vol_pax_trn",
    values: ym([1.439, 1.570, 1.805, 1.789, 1.923, 2.067, 2.223, 2.389, 2.568]),
  },
  {
    id: "tar_landing", name: "Landing & parking", unit: "тыс. сум/movement",
    volumeRef: "vol_mvm",
    values: ym([0.936, 1.338, 1.070, 1.176, 1.264, 1.359, 1.460, 1.570, 1.688]),
  },
  {
    id: "tar_gh", name: "Ground handling fee", unit: "тыс. сум/op",
    volumeRef: "vol_gh",
    values: ym([1.120, 1.276, 1.830, 2.091, 2.248, 2.417, 2.598, 2.793, 3.002]),
  },
  {
    id: "tar_nav", name: "Navigation & fuel fee", unit: "тыс. сум/op",
    volumeRef: "vol_fuel",
    values: ym([2.448, 2.838, 3.828, 4.192, 4.506, 4.844, 5.208, 5.598, 6.018]),
  },
];

// ─────────────────────────────────────────────────────────────────
// COSTS (UZSm) — Excel "Cost of sales and OPEX" R19-R26
// ─────────────────────────────────────────────────────────────────
const COSTS: Array<Omit<FmCost, "id">> = [
  {
    name: "ФОТ операц. персонала (Staff costs)", unit: "млн сум", type: "fixed",
    values: ym([788376, 840313, 744884, 766424, 806250, 866718, 931722, 1001601, 1076721]),
  },
  {
    name: "Коммунальные услуги (Utilities)", unit: "млн сум", type: "semi-var",
    values: ym([425856, 495549, 491511, 579919, 752500, 924500, 1118067, 1201922, 1435629]),
  },
  {
    name: "Содержание ВПП и airfield (Runway maintenance)", unit: "млн сум", type: "variable",
    values: ym([34443, 40316, 41997, 46077, 48375, 52003, 55903, 60096, 64603]),
  },
  {
    name: "Содержание терминала (Terminal maint.)", unit: "млн сум", type: "semi-var",
    values: ym([8946, 8959, 8399, 8013, 5375, 5778, 6211, 6677, 7178]),
  },
  {
    name: "Безопасность (Security)", unit: "млн сум", type: "fixed",
    values: ym([425856, 495549, 491511, 579919, 623412, 670168, 720431, 774463, 832548]),
  },
  {
    name: "Амортизация (D&A · airport ops)", unit: "млн сум", type: "fixed", isDA: true,
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "Навигационные сервисы", unit: "млн сум", type: "variable",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "Прочие операц. расходы", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  // SG&A block (Excel R44-R51)
  {
    name: "SG&A · Менеджмент и админ. ФОТ", unit: "млн сум", type: "variable",
    values: ym([100000, 375000, 416000, 336000, 361200, 388289, 417411, 448717, 482371]),
  },
  {
    name: "SG&A · Соц. выплаты", unit: "млн сум", type: "variable",
    values: ym([12000, 45000, 49920, 40320, 43344, 46594, 50089, 53846, 57884]),
  },
  {
    name: "SG&A · Амортизация (admin)", unit: "млн сум", type: "fixed", isDA: true,
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "SG&A · Аудит / юр / консалтинг", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "SG&A · IT / связь", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "SG&A · Страхование", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "SG&A · Транспорт", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
  {
    name: "SG&A · Прочие админ.", unit: "млн сум", type: "fixed",
    values: ym([8946, 8959, 8399, 8013, 8613, 9260, 9954, 10701, 11503]),
  },
];

// ─────────────────────────────────────────────────────────────────
// CAPEX — Excel "Balance sheet schedules" R50 (Capital expenditure)
// + per-asset breakdown R58-R62
// ─────────────────────────────────────────────────────────────────
const CAPEX: Array<Omit<FmCapex, "id">> = [
  {
    name: "ВПП и airfield infrastructure", unit: "млн сум",
    values: ym([43859, 48245, 53069, 58376, 64214, 70636, 77699, 85469, 94016]),
  },
  {
    name: "Здания терминалов", unit: "млн сум",
    values: ym([17543, 19298, 21228, 23351, 25686, 28254, 31080, 34188, 37606]),
  },
  {
    name: "Ground support equipment", unit: "млн сум",
    values: ym([8772, 9649, 10614, 11675, 12843, 14127, 15540, 17094, 18803]),
  },
  {
    name: "IT & навигационные системы", unit: "млн сум",
    values: ym([439, 482, 530, 583, 642, 706, 777, 854, 940]),
  },
  {
    name: "Прочие (vehicles, fixtures)", unit: "млн сум",
    values: ym([4387, 4826, 5309, 5840, 6422, 7065, 7771, 8548, 9404]),
  },
];

// ─────────────────────────────────────────────────────────────────
// AIRPORT LOAD — Excel "Volume" R10-R20, computed as
//   load = 2025_pax / max(2025_pax) (relative scale 0..1).
//   Аэропорты без данных получают estimated load по характеру trafica.
// ─────────────────────────────────────────────────────────────────
const REAL_AIRPORTS: FmAirport[] = [
  { name: "Ташкент (TAS)",   load: 1.00 },          // 760000 / 760000
  { name: "Самарканд (SKD)", load: 0.17 },          // 130000 / 760000
  { name: "Бухара (BHK)",    load: 0.049 },         // 37200 / 760000
  { name: "Ургенч (UGC)",    load: 0.001 },         // 750 / 760000
  { name: "Навои (NVI)",     load: 0.0004 },        // 275 / 760000
  // Без данных в Excel — estimate из открытых источников / аналогии
  { name: "Фергана (FEG)",   load: 0.012 },
  { name: "Термез (TMJ)",    load: 0.008 },
  { name: "Карши (KSQ)",     load: 0.006 },
  { name: "Нукус (NCU)",     load: 0.010 },
  { name: "Наманган (NMA)",  load: 0.015 },
  { name: "Андижан (AZN)",   load: 0.010 },
];

// ─────────────────────────────────────────────────────────────────
// SCENARIO BUILDER — base = 1.0×, opt = +15% revenue / −10% costs,
// str = −18% revenue / +12% costs (применяется к forecast years only).
// ─────────────────────────────────────────────────────────────────
const FORECAST_SET = new Set(FORECAST_YEARS);

function scaleMap(src: FmYearMap, factor: number): FmYearMap {
  const m: FmYearMap = {};
  for (const y of ALL_YEARS) {
    const base = src[y] || 0;
    m[y] = FORECAST_SET.has(y) ? base * factor : base;
  }
  return m;
}

function buildScenario(volFactor: number, costFactor: number, capexFactor: number): FmScenarioModel {
  const macro: FmMacro = {
    inflation: { ...MACRO_BASE.inflation },
    usInflation: { ...MACRO_BASE.usInflation },
    fx: { ...MACRO_BASE.fx },
  };

  return {
    horizon: HORIZON,
    macro,
    drivers: {
      volumes: VOLUMES.map((d, i) => ({
        ...d, id: `vol_${i + 1}`, values: scaleMap(d.values, volFactor),
      })),
      // Tariffs остаются те же — это unit prices, не зависят от scenario.
      tariffs: TARIFFS.map((d, i) => ({
        ...d, id: `tar_${i + 1}`, values: { ...d.values },
      })),
      costs: COSTS.map((d, i) => ({
        ...d, id: `cost_${i + 1}`, values: scaleMap(d.values, costFactor),
      })),
      capex: CAPEX.map((d, i) => ({
        ...d, id: `capex_${i + 1}`, values: scaleMap(d.values, capexFactor),
      })),
      wc: { dso: 11, dio: 19, dpo: 19, dap: 11 },  // R25/R29/R33/R41 historical avg
      debt: {
        // Excel R109-R111: 10M baseline, repay 1M/year
        ltDebt: ym([10_000_000, 10_000_000, 10_000_000, 10_000_000,
                     10_000_000, 9_000_000, 8_000_000, 7_000_000, 6_000_000]),
        stDebt: ym([0, 0, 0, 0, 1_000_000, 1_000_000, 1_000_000, 1_000_000, 1_000_000]),
        interestRate: 0.09,  // оценочно — Excel R116 даёт payment 1000 UZSm
      },
      equity: {
        shareCapital: ym([1_800_000, 1_800_000, 1_800_000, 1_800_000,
                           2_100_000, 2_100_000, 2_400_000, 2_400_000, 2_700_000]),
        openingCash: 580_000,
        openingRE: 100_000,  // R101 Excel: 100,000 UZSm baseline RE
      },
    },
    // Direct revenue override — pull from Excel "Revenue" R24 (Total revenue).
    // Forecast years адаптированы под scenario factor.
    revenueDirect: scaleMap(ym([
      2_208_442, 2_837_172, 3_058_350, 3_579_457,         // 2022-2025 fact
      3_594_604, 3_864_199, 4_154_014, 4_465_565, 4_800_482,  // 2026-2030 forecast
    ]), volFactor),
    assumptions: {
      taxRate: 0.15,             // UZ corporate tax
      wacc: 0.12,
      dividendPayout: 0.50,      // R103 Excel: ~50% payout actual
      terminalGrowth: 0.03,
      riskFreeRate: 0.14,
      beta: 1.10,
      marketRiskPremium: 0.06,
      countryAdjustment: -0.058,
      effectiveCostOfDebt: 0.09,
    },
    airportLoad: REAL_AIRPORTS.map((a) => ({ ...a })),
  };
}

export const UAP_SEED: FmAllScenarios = {
  base: buildScenario(1.00, 1.00, 1.00),
  opt:  buildScenario(1.15, 0.90, 1.10),
  str:  buildScenario(0.82, 1.12, 0.85),
};

export const SCENARIOS: Array<{ id: ScenarioId; label: string; tone: string }> = [
  { id: "base", label: "Базовый",       tone: "#7F77DD" },
  { id: "opt",  label: "Оптимистичный", tone: "#1D9E75" },
  { id: "str",  label: "Стрессовый",    tone: "#E24B4A" },
];

// ─────────────────────────────────────────────────────────────────
// Compute helpers (waterfall P&L)
// ─────────────────────────────────────────────────────────────────
export interface FmYearOutputs {
  revenue: number;
  cogs: number;
  ebitda: number;
  da: number;
  ebit: number;
  finCost: number;
  ebt: number;
  tax: number;
  netIncome: number;
  ocf: number;
  capex: number;
  fcf: number;
  totalDebt: number;
  netDebt: number;
}

export function computeOutputs(model: FmScenarioModel): Record<number, FmYearOutputs> {
  const years = [...model.horizon.factYears, ...model.horizon.forecastYears];
  const out: Record<number, FmYearOutputs> = {};
  let cumulCash = model.drivers.equity.openingCash;

  for (const y of years) {
    // Revenue: direct override (Excel total) OR derived от Σ(vol × tarf).
    // Тарифы в "UZS thous per unit" → result в (units × тыс.сум) = тыс.сум,
    // делим на 1_000 чтобы получить млн сум.
    let revenue = model.revenueDirect[y] || 0;
    if (!revenue) {
      for (const t of model.drivers.tariffs) {
        const vol = model.drivers.volumes.find((v) => v.id === t.volumeRef);
        if (vol) revenue += (vol.values[y] || 0) * (t.values[y] || 0);
      }
      revenue = revenue / 1_000;
    }

    let opex = 0, da = 0;
    for (const c of model.drivers.costs) {
      const v = c.values[y] || 0;
      if (c.isDA) da += v;
      else opex += v;
    }
    const cogs = opex;
    const ebitda = revenue - cogs;
    const ebit = ebitda - da;
    const totalDebt = (model.drivers.debt.ltDebt[y] || 0) + (model.drivers.debt.stDebt[y] || 0);
    const finCost = totalDebt * model.drivers.debt.interestRate;
    const ebt = ebit - finCost;
    const tax = Math.max(0, ebt * model.assumptions.taxRate);
    const netIncome = ebt - tax;
    const capexY = model.drivers.capex.reduce((s, c) => s + (c.values[y] || 0), 0);
    const ocf = netIncome + da;
    const fcf = ocf - capexY;
    cumulCash += fcf;

    out[y] = {
      revenue, cogs, ebitda, da, ebit, finCost, ebt, tax, netIncome,
      ocf, capex: capexY, fcf, totalDebt, netDebt: totalDebt - cumulCash,
    };
  }
  return out;
}

export function fmtMln(v: number): string {
  if (!Number.isFinite(v) || v === 0) return "—";
  const abs = Math.abs(v);
  if (abs >= 1_000_000) return (v / 1_000_000).toFixed(2) + " трлн";
  if (abs >= 1_000) return (v / 1_000).toFixed(1) + " млрд";
  return Math.round(v).toLocaleString("ru-RU") + " млн";
}

export function fmtPct(v: number, decimals = 1): string {
  if (!Number.isFinite(v)) return "—";
  return (v * 100).toFixed(decimals) + "%";
}
