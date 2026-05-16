/**
 * NGMK Invest Projects — seed data (extracted from НГМК_1.xlsx).
 *
 * Источник: 4 листа Excel (РАСШИРЕНИЕ, МОДЕРНИЗАЦИЯ, CAPEX, ФИН ПОКАЗАТЕЛИ).
 * Будет заменено Excel-парсером в Pack 8.5.
 */

export type ProjectKind = "expansion" | "modernization";
export type ProjectStatus = "Реализуется" | "Планируется" | "В процессе";
export type FSStatus = "УТВЕРЖДЕНО" | "В ПРОЦЕССЕ" | "-";

export interface ProjectRow {
  num: number;
  kind: ProjectKind;
  name: string;
  capacity: string;
  period_start: string;     // YYYY-MM-DD
  period_end: string;
  lifetime_years: number;
  total_investment_mln: number;
  funding_source: string;
  funding_2026_mln: number;
  disbursed_ytd_mln: number;
  revenue_impact_mln: number;
  energy_mkwh: number;
  water_mm3: number;
  gas_mm3: number;
  npv_mln: number | null;
  irr_pct: number | null;
  payback_years: number | null;
  infrastructure: boolean;
  new_jobs: number;
  fs_status: FSStatus;
  responsible: string;
  status: ProjectStatus;
  // CAPEX execution (from CAPEX sheet Part 3)
  capex_budget_cumul_mln?: number;  // финансирование с начала проекта
  capex_actual_cumul_mln?: number;  // освоение с начала проекта
}

export interface QuarterRow {
  q: "Q1" | "Q2" | "Q3" | "Q4";
  plan_mln: number;
  actual_mln: number | null;
  exec_rate: number | null;
}

export interface CapexData {
  annual_plan_mln: number;
  annual_actual_ytd_mln: number;
  annual_exec_rate: number;
  prev_year_plan_mln: number;
  prev_year_actual_mln: number;
  prev_year_exec_rate: number;
  fte_approved: number;
  fte_deployed: number;
  current_year_quarters: QuarterRow[];
  prev_year_quarters: QuarterRow[];
}

export interface FinancialsRow {
  fy: number;
  revenue: number;
  cogs: number;
  gross_profit: number;
  ebitda: number;
  ebitda_margin: number;
  da: number;
  ebit: number;
  net_profit: number;
  net_margin: number;
  total_assets: number;
  total_equity: number;
  total_debt: number;
  net_debt: number;
  net_debt_ebitda: number;
  headcount?: number;
  capex: number;
  capex_revenue_pct: number;
  roa: number;
  roe: number;
}

export interface InvestProjectsCompanyData {
  company: string;
  fiscal_year: number;
  reporting_period: string;
  currency: string;
  ceo: string;
  projects: ProjectRow[];
  capex: CapexData;
  financials: FinancialsRow[];
}


export const NGMK_SEED: InvestProjectsCompanyData = {
  company: "НГМК",
  fiscal_year: 2026,
  reporting_period: "Q1",
  currency: "USD",
  ceo: "АО НГМК",

  projects: [
    {
      num: 1, kind: "expansion",
      name: "Расширение перерабатывающих мощностей ГМЗ-7",
      capacity: "Переработка техногенных отходов 10 млн т/год",
      period_start: "2025-01-01", period_end: "2027-12-31", lifetime_years: 13,
      total_investment_mln: 212.97,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 11.39, disbursed_ytd_mln: 2,
      revenue_impact_mln: 74, energy_mkwh: 219, water_mm3: 5.1, gas_mm3: 0.87312,
      npv_mln: 239.1, irr_pct: 11.8, payback_years: 6.4,
      infrastructure: true, new_jobs: 488,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Рустамов Б.А НГМК; Усманов А.Н. +998935217408",
      status: "Реализуется",
      capex_budget_cumul_mln: 111.16, capex_actual_cumul_mln: 124.61,
    },
    {
      num: 2, kind: "expansion",
      name: "Расширение хвостового хозяйства ГМЗ-2 (ГМЗ-2+ГМЗ-7)",
      capacity: "Складирование хвостовой пульпы 65 млн т/год",
      period_start: "2024-01-01", period_end: "2032-12-31", lifetime_years: 9,
      total_investment_mln: 134.38,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 10.92, disbursed_ytd_mln: 1.5,
      revenue_impact_mln: 0, energy_mkwh: 17.5, water_mm3: 0, gas_mm3: 0,
      npv_mln: null, irr_pct: null, payback_years: null,
      infrastructure: true, new_jobs: 32,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Атауллаев А.О. +998935217333; Махмудов А.Т. +998935217217",
      status: "Реализуется",
      capex_budget_cumul_mln: 11.66, capex_actual_cumul_mln: 20.76,
    },
    {
      num: 3, kind: "expansion",
      name: "Кокпатас + Даугызтау III очередь",
      capacity: "Добыча и переработка золотосодержащей руды 2 млн т/год",
      period_start: "2024-01-01", period_end: "2026-12-31", lifetime_years: 13,
      total_investment_mln: 319.83,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 38.67, disbursed_ytd_mln: 11.5,
      revenue_impact_mln: 60, energy_mkwh: 192.7, water_mm3: 0.9, gas_mm3: 8.76,
      npv_mln: 651.1, irr_pct: 38.7, payback_years: 4.3,
      infrastructure: true, new_jobs: 1308,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Рустамов Б.А +998935217664; Тажиев У.Р. +998935217143",
      status: "Реализуется",
      capex_budget_cumul_mln: 213.11, capex_actual_cumul_mln: 188.76,
    },
    {
      num: 4, kind: "expansion",
      name: "Зармитан, отработка нижних горизонтов (до 0.0 м)",
      capacity: "Добыча и транспортировка золотосодержащей руды 0,85 млн т/год",
      period_start: "2017-01-01", period_end: "2027-12-31", lifetime_years: 10,
      total_investment_mln: 235.57,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 15.91, disbursed_ytd_mln: 2.3,
      revenue_impact_mln: 21, energy_mkwh: 105.1, water_mm3: 0.2, gas_mm3: 0,
      npv_mln: 170.6, irr_pct: 10.4, payback_years: 13.3,
      infrastructure: true, new_jobs: 220,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Рахимова С.Б. +998977970341; Шарипов К.А. +998932640857",
      status: "Реализуется",
      capex_budget_cumul_mln: 176.81, capex_actual_cumul_mln: 191.16,
    },
    {
      num: 5, kind: "expansion",
      name: "Карьер Мурунтау V очередь · 2 этап",
      capacity: "Добыча и транспортировка золотосодержащей руды 13 млн т/год",
      period_start: "2026-01-01", period_end: "2030-12-31", lifetime_years: 14,
      total_investment_mln: 1876.13,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 211.04, disbursed_ytd_mln: 0.07,
      revenue_impact_mln: 60.1, energy_mkwh: 499.3, water_mm3: 0.45, gas_mm3: 0,
      npv_mln: 1666.5, irr_pct: 25.8, payback_years: 6.6,
      infrastructure: true, new_jobs: 2633,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Зарипов О.Г. +998935217811; Атауллаев А.О. +998935217333",
      status: "Планируется",
      capex_budget_cumul_mln: 0.0007, capex_actual_cumul_mln: 0.07,
    },
    {
      num: 6, kind: "expansion",
      name: "Серебро: Нукракон + Космоначи + Окжетпес",
      capacity: "Добыча и транспортировка серебросодержащей руды 4 млн т/год",
      period_start: "2026-01-01", period_end: "2030-12-31", lifetime_years: 16,
      total_investment_mln: 548.02,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 51.8, disbursed_ytd_mln: 0.42,
      revenue_impact_mln: 0, energy_mkwh: 569.4, water_mm3: 5.2, gas_mm3: 13.14,
      npv_mln: 331.7, irr_pct: 16.8, payback_years: 10.7,
      infrastructure: true, new_jobs: 2835,
      fs_status: "В ПРОЦЕССЕ",
      responsible: "Абдуллаев У.М. +998935218126; Тураев М.К. +998909023833; Рустамов Б.А. +998935217664",
      status: "Реализуется",
      capex_actual_cumul_mln: 0.42,
    },
    {
      num: 7, kind: "expansion",
      name: "Цех аффинажа золота и серебра на ГМЗ-2",
      capacity: "Аффинаж золота до 150 т/год и серебра до 250 т/год",
      period_start: "2026-01-01", period_end: "2027-12-31", lifetime_years: 25,
      total_investment_mln: 172.33,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 19.96, disbursed_ytd_mln: 0.24,
      revenue_impact_mln: 0, energy_mkwh: 58.7, water_mm3: 0.4, gas_mm3: 0,
      npv_mln: 111.2, irr_pct: 10.3, payback_years: 10.2,
      infrastructure: true, new_jobs: 74,
      fs_status: "В ПРОЦЕССЕ",
      responsible: "Раззаков О.О. +998935217144; Атауллаев А.О. +998935217333",
      status: "Планируется",
      capex_actual_cumul_mln: 0.24,
    },
    {
      num: 8, kind: "expansion",
      name: "Хвостовое хозяйство ГМЗ-4 ЮРУ · 3-я очередь (2-этап)",
      capacity: "Складирование хвостовой пульпы 5 268 м³",
      period_start: "2024-01-01", period_end: "2026-12-31", lifetime_years: 2,
      total_investment_mln: 8.02,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 6.3, disbursed_ytd_mln: 0,
      revenue_impact_mln: 0, energy_mkwh: 1.7, water_mm3: 0, gas_mm3: 0,
      npv_mln: null, irr_pct: null, payback_years: null,
      infrastructure: true, new_jobs: 0,
      fs_status: "УТВЕРЖДЕНО",
      responsible: "Рахимова С.Б. +998977970341; Шарипов К.А. +998932640857",
      status: "Реализуется",
      capex_budget_cumul_mln: 3.22, capex_actual_cumul_mln: 4.89,
    },
    {
      num: 9, kind: "modernization",
      name: "Техническое и технологическое перевооружение",
      capacity: "Приобретение нового оборудования и замена старого",
      period_start: "2020-01-01", period_end: "2030-12-31", lifetime_years: 10,
      total_investment_mln: 716.82,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 151.72, disbursed_ytd_mln: 16,
      revenue_impact_mln: 0, energy_mkwh: 0, water_mm3: 0, gas_mm3: 0,
      npv_mln: null, irr_pct: null, payback_years: null,
      infrastructure: true, new_jobs: 0,
      fs_status: "-",
      responsible: "Буронов Н.Б. +998935217664; Рустамов Б.А.; Атауллаев А.О. +998935217333",
      status: "Реализуется",
      capex_budget_cumul_mln: 504.84, capex_actual_cumul_mln: 617.37,
    },
    {
      num: 10, kind: "modernization",
      name: "Поддержание действующих мощностей АО «НГМК»",
      capacity: "Замена 126 единиц устаревшего оборудования на новые 119 ед.",
      period_start: "2023-01-01", period_end: "2027-12-31", lifetime_years: 5,
      total_investment_mln: 247.02,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 57.38, disbursed_ytd_mln: 13.6,
      revenue_impact_mln: 0, energy_mkwh: 0, water_mm3: 0, gas_mm3: 0,
      npv_mln: null, irr_pct: null, payback_years: null,
      infrastructure: false, new_jobs: 0,
      fs_status: "-",
      responsible: "Буронов Н.Б. +998935217664; Рустамов Б.А.; Атауллаев А.О. +998935217333",
      status: "Реализуется",
      capex_budget_cumul_mln: 151.47, capex_actual_cumul_mln: 108.74,
    },
    {
      num: 11, kind: "modernization",
      name: "Оборудование, не входящее в смету строек",
      capacity: "Приобретение нового оборудования и замена старого",
      period_start: "2024-01-01", period_end: "2027-12-31", lifetime_years: 4,
      total_investment_mln: 263.64,
      funding_source: "Синдицированная револьверная кредитная линия международных банков",
      funding_2026_mln: 25, disbursed_ytd_mln: 7.5,
      revenue_impact_mln: 0, energy_mkwh: 0, water_mm3: 0, gas_mm3: 0,
      npv_mln: null, irr_pct: null, payback_years: null,
      infrastructure: false, new_jobs: 0,
      fs_status: "-",
      responsible: "Буронов Н.Б. +998935217664; Рустамов Б.А.; Атауллаев А.О. +998935217333",
      status: "Реализуется",
      capex_budget_cumul_mln: 176.16, capex_actual_cumul_mln: 218.39,
    },
  ],

  capex: {
    annual_plan_mln: 392.8,
    annual_actual_ytd_mln: 55.13,
    annual_exec_rate: 0.1404,
    prev_year_plan_mln: 545.75,
    prev_year_actual_mln: 560.76,
    prev_year_exec_rate: 1.0275,
    fte_approved: 43,
    fte_deployed: 43,
    current_year_quarters: [
      { q: "Q1", plan_mln: 96.88, actual_mln: null, exec_rate: 0 },
      { q: "Q2", plan_mln: 88.85, actual_mln: null, exec_rate: 0 },
      { q: "Q3", plan_mln: 105.38, actual_mln: null, exec_rate: 0 },
      { q: "Q4", plan_mln: 101.69, actual_mln: null, exec_rate: 0 },
    ],
    prev_year_quarters: [
      { q: "Q1", plan_mln: 118.4, actual_mln: 118.5, exec_rate: 1.0008 },
      { q: "Q2", plan_mln: 98.1, actual_mln: 98.1, exec_rate: 1.0 },
      { q: "Q3", plan_mln: 107.14, actual_mln: 126.34, exec_rate: 1.1792 },
      { q: "Q4", plan_mln: 222.01, actual_mln: 217.82, exec_rate: 0.9811 },
    ],
  },

  financials: [
    { fy: 2022, revenue: 5123.45, cogs: -1855.54, gross_profit: 3267.92, ebitda: 2545.9, ebitda_margin: 0.4969, da: 0, ebit: 2545.9, net_profit: 1392.85, net_margin: 0.2719, total_assets: 11121.4, total_equity: 8574.5, total_debt: 2249.33, net_debt: 2053.16, net_debt_ebitda: 0.8065, capex: 0, capex_revenue_pct: 0, roa: 0.1252, roe: 0.1624 },
    { fy: 2023, revenue: 5752.35, cogs: -2006.32, gross_profit: 3746.04, ebitda: 3336.95, ebitda_margin: 0.5801, da: 403.48, ebit: 2933.48, net_profit: 1269.15, net_margin: 0.2206, total_assets: 10889.69, total_equity: 8116.68, total_debt: 2029.46, net_debt: 1874.79, net_debt_ebitda: 0.5618, capex: 473.11, capex_revenue_pct: 0.0822, roa: 0.1165, roe: 0.1564 },
    { fy: 2024, revenue: 7441.84, cogs: -2400.07, gross_profit: 5041.77, ebitda: 4623.96, ebitda_margin: 0.6213, da: 693.86, ebit: 3930.11, net_profit: 1999.07, net_margin: 0.2686, total_assets: 10843.79, total_equity: 7780.81, total_debt: 1972.32, net_debt: 1917.56, net_debt_ebitda: 0.4147, capex: 500.29, capex_revenue_pct: 0.0672, roa: 0.1844, roe: 0.2569 },
    { fy: 2025, revenue: 10576.46, cogs: -2921.17, gross_profit: 7655.29, ebitda: 6800.77, ebitda_margin: 0.643, da: 672.24, ebit: 6128.53, net_profit: 3368.79, net_margin: 0.3185, total_assets: 11008.84, total_equity: 7993.97, total_debt: 2081.65, net_debt: 1941.39, net_debt_ebitda: 0.2855, headcount: 51999, capex: 1249.27, capex_revenue_pct: 0.1181, roa: 0.306, roe: 0.4214 },
  ],
};
