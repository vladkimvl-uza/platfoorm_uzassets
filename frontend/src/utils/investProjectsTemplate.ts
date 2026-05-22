/**
 * Invest-projects Excel template (Pack 154).
 *
 * Two flows:
 *   downloadInvestTemplate(name, year, options) — writes a workbook the user
 *     fills out. Same schema as NGMK seed but blank rows (or seeded rows
 *     from NGMK as an example, controlled by `includeExample`).
 *   parseInvestTemplate(file) — reads an uploaded .xlsx, returns
 *     InvestProjectsCompanyData ready to send to backend.
 *
 * Sheets:
 *   1. Инструкция — how to fill, what each column means
 *   2. Мета — company / fiscal_year / reporting_period / currency / ceo
 *   3. Проекты — one row per project (kind column: РАСШИРЕНИЕ / МОДЕРНИЗАЦИЯ)
 *   4. CAPEX — one annual row + 8 quarterly rows (current + prev year)
 *   5. Финпоказатели — one row per fiscal year (history)
 *
 * xlsx is lazy-loaded so we don't ship 700kB on every page.
 */
import { NGMK_SEED } from "@/data/ngmk-invest-seed";
import type {
  InvestProjectsCompanyData,
  ProjectKind, ProjectRow, ProjectStatus, FSStatus,
  CapexData, QuarterRow, FinancialsRow,
} from "@/data/ngmk-invest-seed";

// ─── Column layout for the «Проекты» sheet ─────────────────────────────
// Order matters — used both when writing template and reading it back.
const PROJECT_COLUMNS: { key: keyof ProjectRow | "_skip"; header: string }[] = [
  { key: "num",                       header: "№" },
  { key: "kind",                      header: "Тип (расширение / модернизация)" },
  { key: "name",                      header: "Наименование проекта" },
  { key: "capacity",                  header: "Мощность / описание" },
  { key: "period_start",              header: "Дата начала (YYYY-MM-DD)" },
  { key: "period_end",                header: "Дата окончания (YYYY-MM-DD)" },
  { key: "lifetime_years",            header: "Срок жизни, лет" },
  { key: "total_investment_mln",      header: "Всего инвестиций, млн" },
  { key: "funding_source",            header: "Источник финансирования" },
  { key: "funding_2026_mln",          header: "Финансирование текущего года, млн" },
  { key: "disbursed_ytd_mln",         header: "Освоено YTD, млн" },
  { key: "revenue_impact_mln",        header: "Эффект на выручку, млн" },
  { key: "energy_mkwh",               header: "Электроэнергия, ГВт·ч" },
  { key: "water_mm3",                 header: "Вода, млн м³" },
  { key: "gas_mm3",                   header: "Газ, млн м³" },
  { key: "npv_mln",                   header: "NPV, млн" },
  { key: "irr_pct",                   header: "IRR, %" },
  { key: "payback_years",             header: "Окупаемость, лет" },
  { key: "infrastructure",            header: "Инфраструктура (да/нет)" },
  { key: "new_jobs",                  header: "Новые рабочие места" },
  { key: "fs_status",                 header: "Статус ТЭО" },
  { key: "responsible",               header: "Ответственный" },
  { key: "status",                    header: "Статус проекта" },
  { key: "capex_budget_cumul_mln",    header: "CAPEX бюджет накопительно, млн" },
  { key: "capex_actual_cumul_mln",    header: "CAPEX освоено накопительно, млн" },
];

const FIN_COLUMNS: { key: keyof FinancialsRow; header: string }[] = [
  { key: "fy",                  header: "Год" },
  { key: "revenue",             header: "Выручка" },
  { key: "cogs",                header: "Себестоимость" },
  { key: "gross_profit",        header: "Валовая прибыль" },
  { key: "ebitda",              header: "EBITDA" },
  { key: "ebitda_margin",       header: "EBITDA margin, %" },
  { key: "da",                  header: "D&A" },
  { key: "ebit",                header: "EBIT" },
  { key: "net_profit",          header: "Чистая прибыль" },
  { key: "net_margin",          header: "Net margin, %" },
  { key: "total_assets",        header: "Активы" },
  { key: "total_equity",        header: "Капитал" },
  { key: "total_debt",          header: "Долг" },
  { key: "net_debt",            header: "Чистый долг" },
  { key: "net_debt_ebitda",     header: "ND/EBITDA, x" },
  { key: "headcount",           header: "Численность" },
  { key: "capex",               header: "CAPEX" },
  { key: "capex_revenue_pct",   header: "CAPEX/Выручка, %" },
  { key: "roa",                 header: "ROA, %" },
  { key: "roe",                 header: "ROE, %" },
];

const KIND_RU: Record<ProjectKind, string> = {
  expansion:      "РАСШИРЕНИЕ",
  modernization:  "МОДЕРНИЗАЦИЯ",
};
const KIND_FROM_RU: Record<string, ProjectKind> = {
  "РАСШИРЕНИЕ":      "expansion",
  "МОДЕРНИЗАЦИЯ":    "modernization",
  "РАСШИРЕНИЕ ":     "expansion",
  "МОДЕРНИЗАЦИЯ ":   "modernization",
};

// ──────────────────────────────────────────────────────────────────────
// Download — generates blank or example-filled workbook
// ──────────────────────────────────────────────────────────────────────

export async function downloadInvestTemplate(
  companyName: string,
  fiscalYear: number = NGMK_SEED.fiscal_year,
  opts: { includeExample?: boolean } = {},
): Promise<void> {
  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();
  const useExample = opts.includeExample !== false;  // default true

  // ─── 1. Инструкция ────────────────────────────────────────────────
  const instr: (string | number)[][] = [
    [`ШАБЛОН ИМПОРТА · Инвест-проекты · ${companyName} · ${fiscalYear} год`],
    [""],
    ["КАК ЗАПОЛНЯТЬ:"],
    ["1. Лист «Мета» — общая информация о компании."],
    ["2. Лист «Проекты» — одна строка = один инвест-проект."],
    ["3. Лист «CAPEX» — годовой и поквартальный план/факт."],
    ["4. Лист «Финпоказатели» — историческая динамика (P&L, баланс)."],
    [""],
    ["ПРАВИЛА:"],
    ["• Все суммы — в млн долларов США (если в Мете указано USD)."],
    ["• Тип проекта: ровно «РАСШИРЕНИЕ» или «МОДЕРНИЗАЦИЯ»."],
    ["• Даты — формат YYYY-MM-DD (например: 2026-03-15)."],
    ["• Числа без пробелов, разделитель — точка («212.97», не «212,97»)."],
    ["• Пустая ячейка = нет данных (для опциональных полей — NPV/IRR/срок окуп.)."],
    ["• «Инфраструктура»: пишите «да» или «нет» (или ИСТИНА / ЛОЖЬ)."],
    [""],
    [useExample ? "ПРИМЕР ЗАПОЛНЕНИЯ: данные НГМК уже подставлены — замените на свои." : "ВНИМАНИЕ: листы пустые, заполните по вашей компании."],
    [""],
    ["ИМПОРТ: меню ⋮ → Импорт шаблона Excel → выбрать этот файл после заполнения."],
  ];
  const ws0 = XLSX.utils.aoa_to_sheet(instr);
  ws0["!cols"] = [{ wch: 100 }];
  XLSX.utils.book_append_sheet(wb, ws0, "Инструкция");

  // ─── 2. Мета ──────────────────────────────────────────────────────
  const src = useExample ? NGMK_SEED : null;
  const meta: (string | number)[][] = [
    ["Поле",            "Значение",          "Комментарий"],
    ["company",          companyName || "",   "Короткое имя компании (как в Companies admin)"],
    ["fiscal_year",      fiscalYear,          "Год отчётности"],
    ["reporting_period", src?.reporting_period ?? "Q1",   "Q1 / Q2 / Q3 / Q4 / Year"],
    ["currency",         src?.currency ?? "USD",          "USD / UZS / EUR"],
    ["ceo",              src?.ceo ?? "",      "ФИО или наименование исполнительного руководства"],
  ];
  const ws1 = XLSX.utils.aoa_to_sheet(meta);
  ws1["!cols"] = [{ wch: 22 }, { wch: 36 }, { wch: 70 }];
  XLSX.utils.book_append_sheet(wb, ws1, "Мета");

  // ─── 3. Проекты ───────────────────────────────────────────────────
  const projRows: any[][] = [PROJECT_COLUMNS.map((c) => c.header)];
  const projData = useExample ? NGMK_SEED.projects : [];
  for (const p of projData) {
    projRows.push(PROJECT_COLUMNS.map((c) => {
      if (c.key === "_skip") return "";
      const v = (p as any)[c.key];
      if (c.key === "kind") return KIND_RU[v as ProjectKind] ?? v;
      if (c.key === "infrastructure") return v ? "да" : "нет";
      return v ?? "";
    }));
  }
  // If empty, leave 1 blank row hint
  if (projData.length === 0) {
    projRows.push(PROJECT_COLUMNS.map((c) =>
      c.key === "num" ? 1
        : c.key === "kind" ? "РАСШИРЕНИЕ"
        : c.key === "infrastructure" ? "нет"
        : "",
    ));
  }
  const ws2 = XLSX.utils.aoa_to_sheet(projRows);
  ws2["!cols"] = PROJECT_COLUMNS.map(() => ({ wch: 22 }));
  XLSX.utils.book_append_sheet(wb, ws2, "Проекты");

  // ─── 4. CAPEX ─────────────────────────────────────────────────────
  const capex = useExample ? NGMK_SEED.capex : null;
  const capexRows: any[][] = [
    ["Поле",                     "Значение"],
    ["annual_plan_mln",          capex?.annual_plan_mln ?? ""],
    ["annual_actual_ytd_mln",    capex?.annual_actual_ytd_mln ?? ""],
    ["annual_exec_rate",         capex?.annual_exec_rate ?? ""],
    ["prev_year_plan_mln",       capex?.prev_year_plan_mln ?? ""],
    ["prev_year_actual_mln",     capex?.prev_year_actual_mln ?? ""],
    ["prev_year_exec_rate",      capex?.prev_year_exec_rate ?? ""],
    ["fte_approved",             capex?.fte_approved ?? ""],
    ["fte_deployed",             capex?.fte_deployed ?? ""],
    [""],
    ["Поквартально, текущий год"],
    ["Q",      "plan_mln",            "actual_mln",            "exec_rate"],
    ...(["Q1","Q2","Q3","Q4"] as const).map((q) => {
      const row = capex?.current_year_quarters.find((x) => x.q === q);
      return [q, row?.plan_mln ?? "", row?.actual_mln ?? "", row?.exec_rate ?? ""];
    }),
    [""],
    ["Поквартально, предыдущий год"],
    ["Q",      "plan_mln",            "actual_mln",            "exec_rate"],
    ...(["Q1","Q2","Q3","Q4"] as const).map((q) => {
      const row = capex?.prev_year_quarters.find((x) => x.q === q);
      return [q, row?.plan_mln ?? "", row?.actual_mln ?? "", row?.exec_rate ?? ""];
    }),
  ];
  const ws3 = XLSX.utils.aoa_to_sheet(capexRows);
  ws3["!cols"] = [{ wch: 28 }, { wch: 16 }, { wch: 16 }, { wch: 14 }];
  XLSX.utils.book_append_sheet(wb, ws3, "CAPEX");

  // ─── 5. Финпоказатели ────────────────────────────────────────────
  const finRows: any[][] = [FIN_COLUMNS.map((c) => c.header)];
  const finData = useExample ? NGMK_SEED.financials : [];
  for (const f of finData) {
    finRows.push(FIN_COLUMNS.map((c) => (f as any)[c.key] ?? ""));
  }
  if (finData.length === 0) {
    finRows.push(FIN_COLUMNS.map((c) => c.key === "fy" ? fiscalYear : ""));
  }
  const ws4 = XLSX.utils.aoa_to_sheet(finRows);
  ws4["!cols"] = FIN_COLUMNS.map(() => ({ wch: 18 }));
  XLSX.utils.book_append_sheet(wb, ws4, "Финпоказатели");

  // ─── Save ────────────────────────────────────────────────────────
  const safeName = (companyName || "company").replace(/[^\wЀ-ӿ\- ]+/g, "_");
  XLSX.writeFile(wb, `invest-template_${safeName}_${fiscalYear}.xlsx`);
}

// ──────────────────────────────────────────────────────────────────────
// Parser
// ──────────────────────────────────────────────────────────────────────

function _n(v: any): number | null {
  if (v == null || v === "") return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).replace(/\s+/g, "").replace(",", ".");
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
function _nReq(v: any): number {
  const n = _n(v);
  return n ?? 0;
}
function _s(v: any): string {
  return v == null ? "" : String(v).trim();
}
function _bool(v: any): boolean {
  if (typeof v === "boolean") return v;
  const s = _s(v).toLowerCase();
  return s === "да" || s === "yes" || s === "true" || s === "истина" || s === "1";
}
function _readSheet(XLSX: any, ws: any): any[][] {
  return XLSX.utils.sheet_to_json(ws, { header: 1, defval: "", blankrows: false }) as any[][];
}

export async function parseInvestTemplate(file: File): Promise<InvestProjectsCompanyData> {
  const XLSX = await import("xlsx");
  const buf = await file.arrayBuffer();
  const wb = XLSX.read(buf, { type: "array" });

  // Auto-detect format: original НГМК 7-sheet layout has ТИТУЛЬНЫЙ ЛИСТ +
  // РАСШИРЕНИЕ; our generated template has Мета + Проекты. Use the original
  // parser for the former so the 21 source files import as-is.
  if (wb.Sheets["ТИТУЛЬНЫЙ ЛИСТ"] && wb.Sheets["РАСШИРЕНИЕ"]) {
    return _parseOriginalFormat(XLSX, wb);
  }

  // ─── Мета ───────────────────────────────────────────────────────
  const wsMeta = wb.Sheets["Мета"];
  if (!wsMeta) throw new Error("Не найден лист «Мета» или «ТИТУЛЬНЫЙ ЛИСТ». Скачайте свежий шаблон или используйте оригинальный формат.");
  const metaRows = _readSheet(XLSX, wsMeta);
  const metaMap = new Map<string, any>();
  for (const r of metaRows.slice(1)) {
    if (!r[0]) continue;
    metaMap.set(_s(r[0]).toLowerCase(), r[1]);
  }
  const company = _s(metaMap.get("company"));
  if (!company) throw new Error("В листе «Мета» не указано поле «company».");
  const fiscal_year = _nReq(metaMap.get("fiscal_year"));

  // ─── Проекты ───────────────────────────────────────────────────
  const wsProj = wb.Sheets["Проекты"];
  if (!wsProj) throw new Error("Не найден лист «Проекты».");
  const projRows = _readSheet(XLSX, wsProj);
  const projHeaders = projRows[0]?.map((h: any) => _s(h)) ?? [];
  const projects: ProjectRow[] = [];
  for (let i = 1; i < projRows.length; i++) {
    const row = projRows[i];
    if (!row || row.every((c: any) => c === "" || c == null)) continue;

    const get = (key: keyof ProjectRow) => {
      const col = PROJECT_COLUMNS.findIndex((c) => c.key === key);
      return col >= 0 ? row[col] : undefined;
    };
    const kindRaw = _s(get("kind")).toUpperCase();
    const kind: ProjectKind = KIND_FROM_RU[kindRaw] ?? "expansion";

    projects.push({
      num: _nReq(get("num")) || (i),
      kind,
      name: _s(get("name")),
      capacity: _s(get("capacity")),
      period_start: _s(get("period_start")),
      period_end: _s(get("period_end")),
      lifetime_years: _nReq(get("lifetime_years")),
      total_investment_mln: _nReq(get("total_investment_mln")),
      funding_source: _s(get("funding_source")),
      funding_2026_mln: _nReq(get("funding_2026_mln")),
      disbursed_ytd_mln: _nReq(get("disbursed_ytd_mln")),
      revenue_impact_mln: _nReq(get("revenue_impact_mln")),
      energy_mkwh: _nReq(get("energy_mkwh")),
      water_mm3: _nReq(get("water_mm3")),
      gas_mm3: _nReq(get("gas_mm3")),
      npv_mln: _n(get("npv_mln")),
      irr_pct: _n(get("irr_pct")),
      payback_years: _n(get("payback_years")),
      infrastructure: _bool(get("infrastructure")),
      new_jobs: _nReq(get("new_jobs")),
      fs_status: (_s(get("fs_status")).toUpperCase() as FSStatus) || "-",
      responsible: _s(get("responsible")),
      status: (_s(get("status")) as ProjectStatus) || "Планируется",
      capex_budget_cumul_mln: _n(get("capex_budget_cumul_mln")) ?? undefined,
      capex_actual_cumul_mln: _n(get("capex_actual_cumul_mln")) ?? undefined,
    });
  }

  // ─── CAPEX ─────────────────────────────────────────────────────
  const wsCapex = wb.Sheets["CAPEX"];
  let capex: CapexData = {
    annual_plan_mln: 0, annual_actual_ytd_mln: 0, annual_exec_rate: 0,
    prev_year_plan_mln: 0, prev_year_actual_mln: 0, prev_year_exec_rate: 0,
    fte_approved: 0, fte_deployed: 0,
    current_year_quarters: [], prev_year_quarters: [],
  };
  if (wsCapex) {
    const cap = _readSheet(XLSX, wsCapex);
    const flat = new Map<string, any>();
    for (const r of cap) {
      if (r[0] && r[1] !== undefined && r[1] !== "" && r.length < 4) {
        flat.set(_s(r[0]), r[1]);
      }
    }
    capex.annual_plan_mln       = _nReq(flat.get("annual_plan_mln"));
    capex.annual_actual_ytd_mln = _nReq(flat.get("annual_actual_ytd_mln"));
    capex.annual_exec_rate      = _nReq(flat.get("annual_exec_rate"));
    capex.prev_year_plan_mln    = _nReq(flat.get("prev_year_plan_mln"));
    capex.prev_year_actual_mln  = _nReq(flat.get("prev_year_actual_mln"));
    capex.prev_year_exec_rate   = _nReq(flat.get("prev_year_exec_rate"));
    capex.fte_approved          = _nReq(flat.get("fte_approved"));
    capex.fte_deployed          = _nReq(flat.get("fte_deployed"));
    // Quarterly blocks — find the two "Q | plan_mln | actual_mln | exec_rate"
    // markers and read the next 4 rows from each.
    const isQHeader = (r: any[]) => _s(r[0]) === "Q" && _s(r[1]) === "plan_mln";
    const cur: QuarterRow[] = [];
    const prv: QuarterRow[] = [];
    let target = cur;
    for (let i = 0; i < cap.length; i++) {
      if (isQHeader(cap[i])) {
        for (let j = i + 1; j < Math.min(i + 5, cap.length); j++) {
          const r = cap[j];
          const q = _s(r[0]).toUpperCase();
          if (!["Q1","Q2","Q3","Q4"].includes(q)) break;
          target.push({
            q: q as "Q1"|"Q2"|"Q3"|"Q4",
            plan_mln: _nReq(r[1]),
            actual_mln: _n(r[2]),
            exec_rate: _n(r[3]),
          });
        }
        target = prv;  // first block = current, second = prev
      }
    }
    capex.current_year_quarters = cur;
    capex.prev_year_quarters = prv;
  }

  // ─── Финпоказатели ────────────────────────────────────────────
  const wsFin = wb.Sheets["Финпоказатели"];
  const financials: FinancialsRow[] = [];
  if (wsFin) {
    const fin = _readSheet(XLSX, wsFin);
    for (let i = 1; i < fin.length; i++) {
      const row = fin[i];
      if (!row || row.every((c: any) => c === "" || c == null)) continue;
      const fy = _nReq(row[0]);
      if (!fy) continue;
      const f: any = { fy };
      for (let k = 1; k < FIN_COLUMNS.length; k++) {
        const col = FIN_COLUMNS[k].key;
        const v = row[k];
        if (col === "headcount") {
          f[col] = _n(v) ?? undefined;
        } else {
          f[col] = _nReq(v);
        }
      }
      financials.push(f as FinancialsRow);
    }
  }

  return {
    company,
    fiscal_year,
    reporting_period: _s(metaMap.get("reporting_period")) || "Q1",
    currency: _s(metaMap.get("currency")) || "USD",
    ceo: _s(metaMap.get("ceo")),
    projects,
    capex,
    financials,
  } as InvestProjectsCompanyData;
}

// ──────────────────────────────────────────────────────────────────────
// Original 7-sheet format parser (the 21 source files from "21 компания" folder).
// Layout discovered by inspection of НГМК.xlsx:
//   ТИТУЛЬНЫЙ ЛИСТ   — col B label, col D value (rows: name R7, FY R11, period R12, currency R16)
//   ФИН ПОКАЗАТЕЛИ   — R5 cols 3..7 = years; rows 7..32 = metrics, one column per year
//   РАСШИРЕНИЕ       — R4 headers, R5+ data, 22 columns (period text in col 5 = "DD.MM.YYYY - DD.MM.YYYY")
//   МОДЕРНИЗАЦИЯ     — same shape as РАСШИРЕНИЕ
//   CAPEX            — annual block R7..R15, quarterly R20..R27, per-project R32+
// ──────────────────────────────────────────────────────────────────────

function _cell(ws: any, addr: string): any {
  const c = ws[addr];
  return c ? c.v : undefined;
}

function _parsePeriodRange(raw: any): { start: string; end: string } {
  const s = _s(raw).replace(/\s+/g, " ");
  // Accept "01.01.2025 - 31.12.2027" / "01.01.2024 й-31.12.2026 й" / similar
  const m = s.match(/(\d{1,2})[.,/-](\d{1,2})[.,/-](\d{4})\s*[-–—йЙ\s]+(\d{1,2})[.,/-](\d{1,2})[.,/-](\d{4})/);
  if (!m) return { start: "", end: "" };
  const pad = (n: string) => n.padStart(2, "0");
  return {
    start: `${m[3]}-${pad(m[2])}-${pad(m[1])}`,
    end:   `${m[6]}-${pad(m[5])}-${pad(m[4])}`,
  };
}

function _parseProjectsSheet(
  XLSX: any, ws: any, kind: ProjectKind, startNum: number,
): ProjectRow[] {
  if (!ws) return [];
  const rows = _readSheet(XLSX, ws);
  // Header row is row 4 (zero-indexed 3) per inspection. Data starts at row 5 (idx 4).
  const out: ProjectRow[] = [];
  let n = startNum;
  for (let i = 4; i < rows.length; i++) {
    const r = rows[i];
    if (!r) continue;
    // Cols 1-indexed in Excel; sheet_to_json with header:1 gives 0-indexed arrays
    // where index 0 = col A (usually empty), index 1 = col B (#/num), etc.
    const name = _s(r[2]);
    if (!name) continue;
    // Bail at "ИТОГО" totals row + footer notes
    if (/^итого/i.test(name) || /^рекомендац/i.test(name)) break;

    const period = _parsePeriodRange(r[4]);
    const fsRaw = _s(r[19]).toUpperCase();
    const fs: FSStatus =
      fsRaw.includes("УТВЕРЖД") ? "УТВЕРЖДЕНО"
      : fsRaw.includes("ПРОЦЕС") ? "В ПРОЦЕССЕ"
      : "-";

    out.push({
      num:                _nReq(r[1]) || n,
      kind,
      name,
      capacity:           _s(r[3]),
      period_start:       period.start,
      period_end:         period.end,
      lifetime_years:     _nReq(r[5]),
      total_investment_mln: _nReq(r[6]),
      funding_source:     _s(r[7]),
      funding_2026_mln:   _nReq(r[8]),
      disbursed_ytd_mln:  _nReq(r[9]),
      revenue_impact_mln: _nReq(r[10]),
      energy_mkwh:        _nReq(r[11]),
      water_mm3:          _nReq(r[12]),
      gas_mm3:            _nReq(r[13]),
      npv_mln:            _n(r[14]),
      irr_pct:            (() => { const v = _n(r[15]); return v != null ? (v <= 1 ? v * 100 : v) : null; })(),
      payback_years:      _n(r[16]),
      infrastructure:     _bool(r[17]),
      new_jobs:           _nReq(r[18]),
      fs_status:          fs,
      responsible:        _s(r[20]),
      status:             (_s(r[21]) as ProjectStatus) || "Планируется",
    });
    n++;
  }
  return out;
}

function _parseOriginalFormat(XLSX: any, wb: any): InvestProjectsCompanyData {
  // ─── ТИТУЛЬНЫЙ ЛИСТ ────────────────────────────────────────────
  // Most files in "21 компания" leave the title sheet as untouched placeholders
  // ("Официальное зарегистрированное название", "e.g. 2024", "Выберите Q1/...")
  // so we detect those and fall back. The UI overrides company name with the
  // selected dropdown choice anyway.
  const wsT = wb.Sheets["ТИТУЛЬНЫЙ ЛИСТ"];
  const _isPlaceholder = (s: string) =>
    !s || /^официальное\b|^e\.?g\.?\s|^ггг|^выбер|^фио\s|^enter\b|^placeholder/i.test(s.trim());

  const rawCompany = _s(_cell(wsT, "D7"));
  const company = _isPlaceholder(rawCompany) ? "" : rawCompany;

  const rawFy = _cell(wsT, "D11");
  const titleFy = typeof rawFy === "number" ? Math.round(rawFy) : 0;

  const rawPeriod = _s(_cell(wsT, "D12"));
  const reporting_period = _isPlaceholder(rawPeriod) ? "Q1" : rawPeriod;

  const rawCurrency = _s(_cell(wsT, "D16"));
  const currency = _isPlaceholder(rawCurrency) ? "USD" : rawCurrency;

  const rawCeo = _s(_cell(wsT, "D19"));
  const ceo = _isPlaceholder(rawCeo) ? "" : rawCeo;

  // ─── ФИН ПОКАЗАТЕЛИ ────────────────────────────────────────────
  const wsF = wb.Sheets["ФИН ПОКАЗАТЕЛИ"];
  const finRows = _readSheet(XLSX, wsF);
  // R5 (idx 4) cols C..G (idx 2..6) = 5 years (FY-4 .. FY current)
  const yearsRow = finRows[4] || [];
  const years: number[] = [];
  for (let c = 2; c <= 6; c++) {
    const y = _n(yearsRow[c]);
    if (y) years.push(Math.round(y));
  }
  // Each metric row is mapped by the label in col B (idx 1).
  // Use partial-match because labels are wordy.
  const rowByLabel = (substr: string): any[] | null => {
    for (const r of finRows) {
      const lbl = _s(r?.[1]).toLowerCase();
      if (lbl && lbl.includes(substr.toLowerCase())) return r;
    }
    return null;
  };
  const v = (r: any[] | null, col: number): number => {
    if (!r) return 0;
    return _nReq(r[col]);
  };
  // Note: COGS in the original sheet is stored as a NEGATIVE number
  // (e.g. -1855). The schema expects positive figures; flip if negative.
  const _abs = (x: number) => Math.abs(x);

  const rRev   = rowByLabel("общая выручка");
  const rCogs  = rowByLabel("себестоимость");
  const rGp    = rowByLabel("валовая прибыль");
  const rEbitda= rowByLabel("ebitda (млн");
  const rEbMgn = rowByLabel("рентабельность по ebitda");
  const rDa    = rowByLabel("износ и амортизация");
  const rEbit  = rowByLabel("ebit");
  const rNp    = rowByLabel("чистая прибыль");
  const rNpMgn = rowByLabel("рентабельность по чистой");
  const rAssets= rowByLabel("общая сумма активов");
  const rEquity= rowByLabel("общая сумма собственного");
  const rDebt  = rowByLabel("общая сумма долга");
  const rNetD  = rowByLabel("чистый долг (млн");
  const rNdEb  = rowByLabel("чистый долг / ebitda");
  const rHc    = rowByLabel("количество сотрудников");
  const rCx    = rowByLabel("капитальные затраты (млн");
  const rCxRev = rowByLabel("капитальные затраты в процентах");
  const rRoa   = rowByLabel("рентабельность активов");
  const rRoe   = rowByLabel("рентабельность собственного капитала");

  const financials: FinancialsRow[] = years.map((fy, i) => {
    const c = 2 + i;
    return {
      fy,
      revenue:           v(rRev, c),
      cogs:              _abs(v(rCogs, c)),
      gross_profit:      v(rGp, c),
      ebitda:            v(rEbitda, c),
      ebitda_margin:     v(rEbMgn, c),
      da:                v(rDa, c),
      ebit:              v(rEbit, c),
      net_profit:        v(rNp, c),
      net_margin:        v(rNpMgn, c),
      total_assets:      v(rAssets, c),
      total_equity:      v(rEquity, c),
      total_debt:        v(rDebt, c),
      net_debt:          v(rNetD, c),
      net_debt_ebitda:   v(rNdEb, c),
      headcount:         _n(rHc?.[c]) ?? undefined,
      capex:             v(rCx, c),
      capex_revenue_pct: v(rCxRev, c),
      roa:               v(rRoa, c),
      roe:               v(rRoe, c),
    };
  });

  // ─── РАСШИРЕНИЕ + МОДЕРНИЗАЦИЯ ─────────────────────────────────
  const projectsExpansion = _parseProjectsSheet(XLSX, wb.Sheets["РАСШИРЕНИЕ"], "expansion", 1);
  const projectsModernization = _parseProjectsSheet(
    XLSX, wb.Sheets["МОДЕРНИЗАЦИЯ"], "modernization", projectsExpansion.length + 1,
  );
  const projects = [...projectsExpansion, ...projectsModernization];

  // ─── CAPEX ─────────────────────────────────────────────────────
  const wsC = wb.Sheets["CAPEX"];
  const capRows = _readSheet(XLSX, wsC);
  const cap = (r: number, c: number) => _nReq(capRows[r - 1]?.[c - 1]);
  // Part 1: rows 7..15
  const capex: CapexData = {
    annual_plan_mln:        cap(7, 3),
    annual_actual_ytd_mln:  cap(8, 3),
    annual_exec_rate:       cap(9, 3),
    prev_year_plan_mln:     cap(7, 4),
    prev_year_actual_mln:   cap(8, 4),
    prev_year_exec_rate:    cap(9, 4),
    fte_approved:           cap(14, 3),
    fte_deployed:           cap(15, 3),
    current_year_quarters:  [],
    prev_year_quarters:     [],
  };
  // Part 2: R20..R23 current, R24..R27 prev. Each: col 3 plan, col 4 fact, col 5 exec
  for (let i = 0; i < 4; i++) {
    const q = (["Q1","Q2","Q3","Q4"] as const)[i];
    capex.current_year_quarters.push({
      q,
      plan_mln:   cap(20 + i, 3),
      actual_mln: _n(capRows[20 + i - 1]?.[3]) ?? null,
      exec_rate:  _n(capRows[20 + i - 1]?.[4]) ?? null,
    });
    capex.prev_year_quarters.push({
      q,
      plan_mln:   cap(24 + i, 3),
      actual_mln: _n(capRows[24 + i - 1]?.[3]) ?? null,
      exec_rate:  _n(capRows[24 + i - 1]?.[4]) ?? null,
    });
  }

  // Part 3: per-project cumulative budget/actual — match by name and stamp
  // capex_budget_cumul_mln + capex_actual_cumul_mln on the corresponding ProjectRow.
  for (let r = 32; r < capRows.length + 1; r++) {
    const name = _s(capRows[r - 1]?.[1]);
    if (!name) continue;
    const budget = _n(capRows[r - 1]?.[2]);
    const actual = _n(capRows[r - 1]?.[3]);
    if (budget == null && actual == null) continue;
    const proj = projects.find((p) => p.name.toLowerCase().startsWith(name.slice(0, 30).toLowerCase()));
    if (proj) {
      if (budget != null) proj.capex_budget_cumul_mln = budget;
      if (actual != null) proj.capex_actual_cumul_mln = actual;
    }
  }

  const fiscal_year = titleFy || (years.length ? years[years.length - 1] : new Date().getFullYear());

  return {
    company,
    fiscal_year,
    reporting_period,
    currency,
    ceo,
    projects,
    capex,
    financials,
  } as InvestProjectsCompanyData;
}
