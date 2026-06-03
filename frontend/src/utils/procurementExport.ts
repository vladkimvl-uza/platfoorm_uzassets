// frontend/src/utils/procurementExport.ts
//
// XLSX-export для модуля Procurement Analysis (Pack 7.9g — закрытие
//   • exportProcurementYear(data, year)    — выгрузка текущего года
//   • downloadProcurementTemplate()        — пустой шаблон для импорта
//
// xlsx-library грузится лениво (вместе с ForensicTemplate / InvestTemplate)
// — не раздуваем bundle main chunk.

import type { ProcurementAggregate } from "@/api/procurement_analysis";

async function loadXlsx() {
  const x = await import("xlsx");
  return x;
}

function fmtRu(n: number | null | undefined): number | string {
  if (n === null || n === undefined || Number.isNaN(n)) return "";
  return Math.round(Number(n) * 100) / 100;
}

export async function exportProcurementYear(
  data: ProcurementAggregate | null,
  year: number | null,
): Promise<void> {
  if (!data) {
    alert("Нет данных для экспорта.");
    return;
  }
  const XLSX = await loadXlsx();
  const wb = XLSX.utils.book_new();

  // Sheet 1: KPI summary
  const k = data.kpis;
  const sheetKpi = XLSX.utils.aoa_to_sheet([
    ["Год", year ?? "—"],
    ["Сектор", data.sector_code || "all"],
    ["Источник", data.meta?.source || "—"],
    [],
    ["KPI", "Значение"],
    ["Всего компаний", k.total_companies],
    ["Чистых компаний", k.clean_companies],
    ["Всего закупок", k.total_closures],
    ["Чистых закупок", k.clean_closures],
    ["Совокупная переплата (UZS)", fmtRu(k.total_overpay_uzs)],
    ["% компаний выше рынка", fmtRu(k.above_market_pct)],
    ["Медианное отклонение, %", fmtRu(k.median_deviation_pct)],
  ]);
  XLSX.utils.book_append_sheet(wb, sheetKpi, "KPI");

  // Sheet 2: Rating (per-company)
  const ratingHeader = [
    "№", "Компания", "Сектор", "Откл. ср. %", "Σ Переплата (UZS)",
    "Σ Объём (UZS)", "Закупок всего", "Чистых", "Красных", "Выше рынка",
  ];
  const ratingRows = data.rating.map((r, i) => [
    i + 1,
    r.company_name,
    r.company_sector || "",
    fmtRu(r.company_deviation),
    fmtRu(Math.max(0, r.sum_dev)),
    fmtRu(r.sum_ref),
    r.cat_count ?? "",
    "",  // clean_count: больше не в API CompanyRatingRow
    r.above_count,
    r.above_count > 0 ? "yes" : "no",
  ]);
  const sheetRating = XLSX.utils.aoa_to_sheet([ratingHeader, ...ratingRows]);
  XLSX.utils.book_append_sheet(wb, sheetRating, "Rating");

  // Sheet 3: Closures (all purchases — детальная база)
  if (data.purchases?.length) {
    const purchHeader = [
      "ID", "Company", "Category", "Product code", "Product name",
      "Supplier", "Closure date", "Quantity", "Unit price",
      "Total (UZS)", "Benchmark median", "Deviation %", "Is dirty",
    ];
    const purchRows = data.purchases.map((p) => [
      p.id, p.company_name || "", p.category_name || p.category_id || "",
      p.product_code || "", p.product_name || "",
      p.supplier || "", p.contract_date || "",
      fmtRu(p.volume), fmtRu(p.unit_price), fmtRu((Number(p.unit_price) || 0) * (Number(p.volume) || 0)),
      fmtRu(p.market_avg), fmtRu(p.deviation_pct),
      p.is_dirty ? "yes" : "no",
    ]);
    const sheetPurch = XLSX.utils.aoa_to_sheet([purchHeader, ...purchRows]);
    XLSX.utils.book_append_sheet(wb, sheetPurch, "Closures");
  }

  // Sheet 4: Categories aggregate
  if (data.category_aggregates?.length) {
    const catHeader = [
      "Category ID", "Label", "Закупок", "Σ Объём (UZS)", "Σ Переплата (UZS)",
      "Медиана откл. %",
    ];
    const catRows = data.category_aggregates.map((c) => [
      c.id, c.name || "",
      c.all_products?.length ?? "", "", "",
      "",  // sum_ref/sum_dev/median_deviation_pct больше не в API CategoryAggregate
    ]);
    const sheetCat = XLSX.utils.aoa_to_sheet([catHeader, ...catRows]);
    XLSX.utils.book_append_sheet(wb, sheetCat, "Categories");
  }

  const fname = `procurement_${year || "all"}_${new Date().toISOString().slice(0, 10)}.xlsx`;
  XLSX.writeFile(wb, fname);
}

export async function downloadProcurementTemplate(): Promise<void> {
  const XLSX = await loadXlsx();
  const wb = XLSX.utils.book_new();

  const header = [
    "lotId", "organ", "vendor", "Unit price", "amount", "Currency",
    "Category", "productCode", "productName", "closureDate",
  ];
  const example = [
    "L-2026-EXAMPLE-001", "АО Навоийский ГМК", "ООО Поставщик",
    1250, 100, "UZS", "Канцелярия", "PROD-001", "Бумага A4 500 л",
    "2026-01-15",
  ];
  const ws = XLSX.utils.aoa_to_sheet([header, example, [], [], []]);
  // Column widths
  ws["!cols"] = [
    { wch: 22 }, { wch: 28 }, { wch: 28 }, { wch: 12 }, { wch: 10 },
    { wch: 10 }, { wch: 18 }, { wch: 18 }, { wch: 32 }, { wch: 14 },
  ];
  XLSX.utils.book_append_sheet(wb, ws, "Sample-Company");

  const readme = XLSX.utils.aoa_to_sheet([
    ["Шаблон импорта закупок UzAssets — Procurement Analysis"],
    [],
    ["1. Один лист = одна компания SOE (имя листа = name_short)."],
    ["2. Header строка обязательна: " + header.join(" / ")],
    ["3. Currency: UZS / USD / EUR (UZS по умолчанию, обменка по as_of_date)."],
    ["4. Category: используйте 15-категорийную таксономию портфеля"],
    ["   (или оставьте пустым — будет 'Прочее')."],
    ["5. productCode: уникальный код товара/услуги — нужен для кластеризации"],
    ["   и расчёта benchmark median цены."],
    ["6. closureDate: ISO формат YYYY-MM-DD."],
    [],
    ["Загрузка через: модуль Procurement → ⋯ меню → Импорт прайс-листа Excel"],
  ]);
  XLSX.utils.book_append_sheet(wb, readme, "README");

  XLSX.writeFile(wb, "procurement_template.xlsx");
}
