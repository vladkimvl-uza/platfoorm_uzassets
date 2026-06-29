// frontend/src/utils/procurementExport.ts
//
// XLSX-export для модуля Procurement Analysis закрытие
// регрессий vs легасиа). Реализует:
//   • exportProcurementYear(data, year)    — выгрузка текущего года
//   • downloadProcurementTemplate()        — пустой шаблон для импорта
//
// xlsx-library грузится лениво (вместе с ForensicTemplate / InvestTemplate)
// — не раздуваем bundle main chunk.

import type { ProcurementAggregate } from "@/api/procurement_analysis";
import { useToast } from "@/composables/useToast";

const toast = useToast();

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
    toast.info("Нет данных для экспорта.");
    return;
  }
  const XLSX = await loadXlsx();
  const wb = XLSX.utils.book_new();

  // Sheet 1: KPI summary — синхронизирован с карточками дашборда
  const k = data.kpis;
  const sheetKpi = XLSX.utils.aoa_to_sheet([
    ["Год", year ?? "—"],
    ["Сектор", data.sector_code || "all"],
    ["Источник", data.meta?.source || "—"],
    [],
    ["KPI", "Значение"],
    ["Совокупный расход (UZS, лот-дедуп)", fmtRu(k.total_spend)],
    ["Уникальных лотов", k.total_lots],
    ["Всего компаний", k.total_companies],
    ["Уже сэкономлено на торгах (UZS)", fmtRu(k.saved_amount)],
    ["Ставка экономии, %", fmtRu(k.saved_rate_pct)],
    ["Потенциал экономии (UZS, только товары)", fmtRu(k.potential_saving_uzs)],
    ["Без конкурентной процедуры (UZS, каталог/e-shop)", fmtRu(k.no_tender_spend)],
    ["Без конкурентной процедуры, %", fmtRu(k.no_tender_pct)],
    ["Конкурентные процедуры без экономии (UZS)", fmtRu(k.competitive_no_saving_spend)],
    ["Конкурентные процедуры без экономии, %", fmtRu(k.competitive_no_saving_pct)],
    ["Товары (UZS)", fmtRu(k.goods_spend)],
    ["Услуги (UZS)", fmtRu(k.services_spend)],
    ["Работы (UZS)", fmtRu(k.works_spend)],
    ["Раскрытых поставщиков", k.supplier_count],
    ["Доля спенда с раскрытым поставщиком, %", fmtRu(k.disclosed_supplier_pct)],
    ["Доля спенда у сквозных поставщиков, %", fmtRu(k.cross_supplier_pct)],
    [],
    ["Совокупная переплата (UZS, нетто по компаниям)", fmtRu(k.total_overpay_uzs)],
    ["% компаний выше рынка", fmtRu(k.above_market_pct)],
    ["Медианное отклонение, %", fmtRu(k.median_deviation_pct)],
    ["Компаний с сопоставимыми данными", k.clean_companies],
    ["Закупок всего / чистых", `${k.total_closures} / ${k.clean_closures}`],
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

  // Sheet 3: Closures (all purchases — детальная база, ПО СТРОКАМ)
  if (data.purchases?.length) {
    // Δ% осмысленно только для сопоставимых товаров — иначе пусто (раньше
    // выгружался мусор до 1 000 000% от self-ref/сентинельного market_avg).
    const devCell = (p: typeof data.purchases[number]) =>
      p.product_type === "PRODUCT" && Number(p.market_avg) > 0 && Math.abs(Number(p.deviation_pct) || 0) <= 1000
        ? fmtRu(p.deviation_pct) : "";
    const purchHeader = [
      "ID", "Компания", "Категория", "Код товара", "Наименование", "Тип",
      "Поставщик", "Дата", "Кол-во", "Цена/ед.",
      "Сумма строки (цена×кол-во)", "Рыночная медиана", "Откл. % (сопост.)", "Грязная",
    ];
    const purchRows = data.purchases.map((p) => [
      p.id, p.company_name || "", p.category_name || p.category_id || "",
      p.product_code || "", p.product_name || "", p.product_type || "",
      p.supplier || "", p.contract_date || "",
      fmtRu(p.volume), fmtRu(p.unit_price), fmtRu((Number(p.unit_price) || 0) * (Number(p.volume) || 0)),
      fmtRu(p.market_avg), devCell(p),
      p.is_dirty ? "да" : "нет",
    ]);
    // Явное предупреждение, если список усечён бэкендом (cap 15k в _build_purchases).
    if (data.purchases.length >= 15000) {
      purchRows.push([], ["⚠ Список усечён до 15 000 строк — выгрузка неполная."]);
    }
    const sheetPurch = XLSX.utils.aoa_to_sheet([purchHeader, ...purchRows]);
    XLSX.utils.book_append_sheet(wb, sheetPurch, "Closures");
  }

  // Sheet 4: Categories aggregate (считаем по товарам категории — band-метрики)
  if (data.category_aggregates?.length) {
    const catHeader = [
      "ID категории", "Категория", "Товаров", "Товаров с benchmark",
      "Σ Объём товаров (UZS)", "Σ Потенциал экономии (UZS)",
    ];
    const catRows = data.category_aggregates.map((c) => {
      const prods = c.all_products || [];
      const sumSpend = prods.reduce((s, p) => s + (Number(p.total_spend) || 0), 0);
      const sumPot = prods.reduce((s, p) => s + (Number(p.potential_saving) || 0), 0);
      return [
        c.id === 0 ? "—" : c.id,
        c.name || "",
        prods.length,
        c.benchmark_product_count ?? c.clean_count ?? "",
        fmtRu(sumSpend),
        fmtRu(sumPot),
      ];
    });
    const sheetCat = XLSX.utils.aoa_to_sheet([catHeader, ...catRows]);
    XLSX.utils.book_append_sheet(wb, sheetCat, "Categories");
  }

  // Sheet 5: Suppliers (топ по спенду, лот-дедуп)
  if (data.suppliers_top?.length) {
    const supHeader = [
      "Поставщик", "ИНН", "Спенд (UZS)", "Доля спенда, %", "Лотов",
      "Компаний", "Сквозной", "Экономия (UZS)", "Премия к рынку, %", "Переплата (UZS)",
    ];
    const supRows = data.suppliers_top.map((s) => [
      s.supplier_name || "—", s.supplier_inn || "",
      fmtRu(s.spend), fmtRu(s.spend_share_pct), s.lot_count, s.company_count,
      s.is_cross ? "да" : "нет", fmtRu(s.saved_amount),
      fmtRu(s.premium_pct), fmtRu(s.excess_uzs),
    ]);
    const sheetSup = XLSX.utils.aoa_to_sheet([supHeader, ...supRows]);
    XLSX.utils.book_append_sheet(wb, sheetSup, "Suppliers");
  }

  // Sheet 6: Methods (способы закупки, лот-дедуп)
  if (data.methods?.length) {
    const mHeader = [
      "Способ", "Конкурентный", "Лотов", "Спенд (UZS)", "Доля спенда, %",
      "Экономия (UZS)", "Ставка экономии, %",
    ];
    const mRows = data.methods.map((m) => [
      m.label || m.method, m.is_competitive ? "да" : "нет",
      m.lot_count, fmtRu(m.spend), fmtRu(m.spend_share_pct),
      fmtRu(m.saved_amount), fmtRu(m.saved_rate_pct),
    ]);
    const sheetM = XLSX.utils.aoa_to_sheet([mHeader, ...mRows]);
    XLSX.utils.book_append_sheet(wb, sheetM, "Methods");
  }

  const fname = `procurement_${year || "all"}_${new Date().toISOString().slice(0, 10)}.xlsx`;
  XLSX.writeFile(wb, fname);
}

// ── Эталонный шаблон импорта — 1:1 с парсером бэкенда ────────────────
// Колонки и имена листов ДОЛЖНЫ совпадать с import_service.py:
//   • лист = компания (имя листа = код из списка ниже; регистр не важен);
//   • строка-заголовок обязательна, имена колонок — точно как здесь;
//   • один лист = много строк-закупок (по одной строке на товар лота).
// Парсер сопоставляет колонки ПО ИМЕНИ (порядок не важен), листы — по имени.

/** Точные имена колонок, которые читает import_service._parse_row. */
const IMPORT_COLUMNS = [
  "lotId", "contractDate", "startDate", "purchaseType", "platformName",
  "vendor", "vendorInn", "regionName", "Category", "productCode",
  "productName", "productType", "unit", "amount", "Unit price",
  "startSumma", "contractAmount", "savedAmount", "savedPercent",
];

/** Признанные коды компаний (имя листа). Из _PA_SHEET_TO_CODE. */
const IMPORT_COMPANIES: [string, string][] = [
  ["NGMK", "Навоийский ГМК"],
  ["NAVOIYURAN", "Навоийуран"],
  ["AGMK", "Алмалыкский ГМК"],
  ["UMK", "Узметкомбинат"],
  ["UUG", "Узбекуголь"],
  ["UNG", "Узбекнефтегаз"],
  ["UTG", "Узтрансгаз"],
  ["HGT", "Худудгазтаъминот"],
  ["UGT", "UzGasTrade"],
  ["NES", "Национальные электрические сети"],
  ["TES", "Тепловые электрические станции"],
  ["RES", "Региональные электрические сети"],
  ["UGE", "Узбекгидроэнерго"],
  ["UTY", "Узбекистон темир йуллари"],
  ["UHY", "Uzbekistan Airways"],
  ["UAP", "Uzbekistan Airports"],
  ["UTC", "Узбектелеком"],
  ["TSHT", "Тошшахартрансхизмат"],
  ["UPT", "Ўзбекистон почтаси"],
  ["UAS", "Узавтосаноат"],
  ["NAZ", "Навоийазот"],
  ["UKS", "Узкимёсаноат"],
];

const IMPORT_CATEGORIES: [number, string][] = [
  [1, "Офисная бумага"], [2, "Канцелярские товары"], [3, "Компьютеры и периферия"],
  [4, "Картриджи и расходники"], [5, "СИЗ и спецодежда"], [6, "Офисная мебель"],
  [7, "Гигиена и чистящие средства"], [8, "Продукты питания"], [9, "Топливо-смазочные материалы"],
  [10, "Запчасти для автотранспорта"], [11, "Стройматериалы"], [12, "Освещение и электротехника"],
  [13, "Кондиционеры и вентиляция"], [14, "Связь и телекоммуникации"], [15, "Лицензии на ПО"],
];

const COL_WIDTHS = [
  { wch: 18 }, { wch: 13 }, { wch: 13 }, { wch: 26 }, { wch: 16 },
  { wch: 26 }, { wch: 13 }, { wch: 16 }, { wch: 10 }, { wch: 20 },
  { wch: 34 }, { wch: 11 }, { wch: 14 }, { wch: 10 }, { wch: 14 },
  { wch: 15 }, { wch: 16 }, { wch: 14 }, { wch: 13 },
];

export async function downloadProcurementTemplate(): Promise<void> {
  const XLSX = await loadXlsx();
  const wb = XLSX.utils.book_new();

  // ── Лист 1: СПРАВКА (правила + значения + коды + категории) ──
  const ref: (string | number)[][] = [
    ["Эталонный шаблон импорта закупок — Единая платформа трансформации"],
    [],
    ["КАК ИМПОРТИРОВАТЬ"],
    ["1. Один лист = одна компания. Имя листа — КОД из таблицы «Коды компаний» (NGMK, AGMK…). Регистр не важен."],
    ["2. Первая строка листа — заголовки колонок РОВНО как на листе «ОБРАЗЕЦ» (имена нельзя менять/переводить)."],
    ["3. Каждая следующая строка — одна позиция (товар/услуга/работа) внутри лота."],
    ["4. Несколько товаров одного лота — несколько строк с ОДНИМ lotId (сумма контракта учитывается один раз)."],
    ["5. Листы «СПРАВКА» и «ОБРАЗЕЦ» при импорте игнорируются (их имена — не коды компаний)."],
    ["6. Загрузка: модуль «Анализ закупок» → меню ⋯ → Импорт Excel."],
    [],
    ["КОЛОНКИ (имя — обязательность — описание)"],
    ["lotId", "обязательно", "ID лота/контракта. Строки с одним lotId = один лот."],
    ["contractDate", "желательно", "Дата контракта, формат YYYY-MM-DD."],
    ["startDate", "опц.", "Дата начала процедуры, YYYY-MM-DD."],
    ["purchaseType", "желательно", "Способ закупки — см. «Способы закупки» ниже."],
    ["platformName", "опц.", "Электронная площадка (например xarid.uz)."],
    ["vendor", "желательно", "Наименование поставщика."],
    ["vendorInn", "желательно", "ИНН поставщика (для сквозных поставщиков/концентрации)."],
    ["regionName", "опц.", "Регион."],
    ["Category", "желательно", "Номер категории 1–15 (см. «Категории»). Пусто → «Без категории»."],
    ["productCode", "ВАЖНО", "Код товара (KTRU). По нему считается рыночная медиана и сравнение цен. Без кода — позиция не попадёт в ценовой бенчмарк."],
    ["productName", "желательно", "Наименование товара/услуги."],
    ["productType", "ВАЖНО", "PRODUCT (товар) / SERVICE (услуга) / WORK (работа). Пусто → определяется по ед.изм."],
    ["unit", "желательно", "Единица измерения (шт, кг, т, л … ; для услуг часто «shartli birlik»)."],
    ["amount", "обязательно", "Количество (число > 0)."],
    ["Unit price", "обязательно*", "Цена за единицу (число > 0). *Если пусто — будет вычислено как contractAmount / amount."],
    ["startSumma", "опц.", "Начальная сумма процедуры (UZS)."],
    ["contractAmount", "желательно", "Сумма контракта (UZS). Источник «спенда» лота; при пустой Unit price — основа для расчёта цены."],
    ["savedAmount", "опц.", "Сэкономлено на торгах (UZS)."],
    ["savedPercent", "опц.", "Процент экономии."],
    [],
    ["СПОСОБЫ ЗАКУПКИ (purchaseType)"],
    ["E-SHOP", "электронный магазин/каталог (НЕконкурентный — торга нет)"],
    ["AUCTION", "аукцион (конкурентный)"],
    ["BEST_OFFER", "лучшее предложение (конкурентный)"],
    ["OTHER_COMPETITIVE_METHODS", "иные конкурентные методы"],
    ["TENDER", "тендер (конкурентный)"],
    [],
    ["ТИП ПОЗИЦИИ (productType)"],
    ["PRODUCT", "товар — участвует в ценовом бенчмарке/рейтинге/потенциале"],
    ["SERVICE", "услуга — показывается отдельно (несравнима по цене за единицу)"],
    ["WORK", "работа — показывается отдельно"],
    [],
    ["КАТЕГОРИИ (номер → название)"],
    ...IMPORT_CATEGORIES.map(([id, name]) => [id, name]),
    [],
    ["КОДЫ КОМПАНИЙ (имя листа → компания)"],
    ...IMPORT_COMPANIES.map(([code, name]) => [code, name]),
  ];
  const wsRef = XLSX.utils.aoa_to_sheet(ref);
  wsRef["!cols"] = [{ wch: 28 }, { wch: 18 }, { wch: 80 }];
  XLSX.utils.book_append_sheet(wb, wsRef, "СПРАВКА");

  // ── Лист 2: ОБРАЗЕЦ (заголовки + примеры) ──
  const examples: (string | number)[][] = [
    [
      "L-2026-000123", "2026-01-15", "2026-01-05", "OTHER_COMPETITIVE_METHODS", "xarid.uz",
      "ООО «Канцторг»", "301234567", "город Ташкент", 2, "17.23.13.130-00007",
      "Бумага офисная A4, 80 г/м²", "PRODUCT", "пачка", 1000, 12500,
      13000000, 12500000, 500000, 3.8,
    ],
    [
      "L-2026-000124", "2026-02-10", "2026-02-01", "E-SHOP", "xarid.uz",
      "ООО «СпецСнаб»", "309876543", "город Навои", 5, "14.12.30.190-00002",
      "Костюм рабочий, хлопок", "PRODUCT", "комплект", 200, 185000,
      "", 37000000, 0, 0,
    ],
    [
      "L-2026-000125", "2026-03-05", "2026-02-20", "OTHER_COMPETITIVE_METHODS", "xt-xarid.uz",
      "ООО «КлинСервис»", "302555111", "город Алмалык", "", "81.21.10.000-00001",
      "Уборка производственных помещений", "SERVICE", "shartli birlik", 1, "",
      9000000, 8500000, 500000, 5.6,
    ],
  ];
  const wsEx = XLSX.utils.aoa_to_sheet([IMPORT_COLUMNS, ...examples]);
  wsEx["!cols"] = COL_WIDTHS;
  XLSX.utils.book_append_sheet(wb, wsEx, "ОБРАЗЕЦ");

  // ── Листы 3..: по одному на компанию (только заголовки) ──
  for (const [code] of IMPORT_COMPANIES) {
    const ws = XLSX.utils.aoa_to_sheet([IMPORT_COLUMNS]);
    ws["!cols"] = COL_WIDTHS;
    XLSX.utils.book_append_sheet(wb, ws, code);
  }

  XLSX.writeFile(wb, "Шаблон_импорта_закупок.xlsx");
}
