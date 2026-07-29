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
import { t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

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
    toast.info(t("Нет данных для экспорта."));
    return;
  }
  const XLSX = await loadXlsx();
  const wb = XLSX.utils.book_new();

  // Sheet 1: KPI summary — синхронизирован с карточками дашборда
  const k = data.kpis;
  const sheetKpi = XLSX.utils.aoa_to_sheet([
    [t("Год"), year ?? "—"],
    [t("Сектор"), data.sector_code || "all"],
    [t("Источник"), data.meta?.source || "—"],
    [],
    ["KPI", t("Значение")],
    [t("Совокупный расход (UZS, лот-дедуп)"), fmtRu(k.total_spend)],
    [t("Уникальных лотов"), k.total_lots],
    [t("Всего компаний"), k.total_companies],
    [t("Уже сэкономлено на торгах (UZS)"), fmtRu(k.saved_amount)],
    [t("Ставка экономии, %"), fmtRu(k.saved_rate_pct)],
    [t("Потенциал экономии (UZS, только товары)"), fmtRu(k.potential_saving_uzs)],
    [t("Без конкурентной процедуры (UZS, каталог/e-shop)"), fmtRu(k.no_tender_spend)],
    [t("Без конкурентной процедуры, %"), fmtRu(k.no_tender_pct)],
    [t("Конкурентные процедуры без экономии (UZS)"), fmtRu(k.competitive_no_saving_spend)],
    [t("Конкурентные процедуры без экономии, %"), fmtRu(k.competitive_no_saving_pct)],
    [t("Товары (UZS)"), fmtRu(k.goods_spend)],
    [t("Услуги (UZS)"), fmtRu(k.services_spend)],
    [t("Работы (UZS)"), fmtRu(k.works_spend)],
    [t("Раскрытых поставщиков"), k.supplier_count],
    [t("Доля спенда с раскрытым поставщиком, %"), fmtRu(k.disclosed_supplier_pct)],
    [t("Доля спенда у сквозных поставщиков, %"), fmtRu(k.cross_supplier_pct)],
    [],
    [t("Совокупная переплата (UZS, нетто по компаниям)"), fmtRu(k.total_overpay_uzs)],
    [t("% компаний выше рынка"), fmtRu(k.above_market_pct)],
    [t("Медианное отклонение, %"), fmtRu(k.median_deviation_pct)],
    [t("Компаний с сопоставимыми данными"), k.clean_companies],
    [t("Закупок всего / чистых"), `${k.total_closures} / ${k.clean_closures}`],
  ]);
  XLSX.utils.book_append_sheet(wb, sheetKpi, "KPI");

  // Sheet 2: Rating (per-company)
  const ratingHeader = [
    "№", t("Компания"), t("Сектор"), t("Откл. ср. %"), "Σ " + t("Переплата") + " (UZS)",
    "Σ " + t("Объём") + " (UZS)", t("Закупок всего"), t("Чистых"), t("Красных"), t("Выше рынка"),
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
      "ID", t("Компания"), t("Категория"), t("Код товара"), t("Наименование"), t("Тип"),
      t("Поставщик"), t("Дата"), t("Кол-во"), t("Цена/ед."),
      t("Сумма строки (цена×кол-во)"), t("Рыночная медиана"), t("Откл. % (сопост.)"), t("Грязная"),
    ];
    const purchRows = data.purchases.map((p) => [
      p.id, p.company_name || "", p.category_name || p.category_id || "",
      p.product_code || "", p.product_name || "", p.product_type || "",
      p.supplier || "", p.contract_date || "",
      fmtRu(p.volume), fmtRu(p.unit_price), fmtRu((Number(p.unit_price) || 0) * (Number(p.volume) || 0)),
      fmtRu(p.market_avg), devCell(p),
      p.is_dirty ? t("да") : t("нет"),
    ]);
    // Явное предупреждение, если список усечён бэкендом (cap 15k в _build_purchases).
    if (data.purchases.length >= 15000) {
      purchRows.push([], [t("⚠ Список усечён до 15 000 строк — выгрузка неполная.")]);
    }
    const sheetPurch = XLSX.utils.aoa_to_sheet([purchHeader, ...purchRows]);
    XLSX.utils.book_append_sheet(wb, sheetPurch, "Closures");
  }

  // Sheet 4: Categories aggregate (считаем по товарам категории — band-метрики)
  if (data.category_aggregates?.length) {
    const catHeader = [
      t("ID категории"), t("Категория"), t("Товаров"), t("Товаров с benchmark"),
      t("Σ Объём товаров (UZS)"), t("Σ Потенциал экономии (UZS)"),
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
      t("Поставщик"), t("ИНН"), t("Спенд (UZS)"), t("Доля спенда, %"), t("Лотов"),
      t("Компаний"), t("Сквозной"), t("Экономия (UZS)"), t("Премия к рынку, %"), t("Переплата (UZS)"),
    ];
    const supRows = data.suppliers_top.map((s) => [
      s.supplier_name || "—", s.supplier_inn || "",
      fmtRu(s.spend), fmtRu(s.spend_share_pct), s.lot_count, s.company_count,
      s.is_cross ? t("да") : t("нет"), fmtRu(s.saved_amount),
      fmtRu(s.premium_pct), fmtRu(s.excess_uzs),
    ]);
    const sheetSup = XLSX.utils.aoa_to_sheet([supHeader, ...supRows]);
    XLSX.utils.book_append_sheet(wb, sheetSup, "Suppliers");
  }

  // Sheet 6: Methods (способы закупки, лот-дедуп)
  if (data.methods?.length) {
    const mHeader = [
      t("Способ"), t("Конкурентный"), t("Лотов"), t("Спенд (UZS)"), t("Доля спенда, %"),
      t("Экономия (UZS)"), t("Ставка экономии, %"),
    ];
    const mRows = data.methods.map((m) => [
      m.label || m.method, m.is_competitive ? t("да") : t("нет"),
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
  // i18n-exempt-start -- official company names are data, not UI copy.
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
  // i18n-exempt-end
];

const IMPORT_CATEGORIES: [number, string][] = [
  [1, i18nKey("Офисная бумага")], [2, i18nKey("Канцелярские товары")], [3, i18nKey("Компьютеры и периферия")],
  [4, i18nKey("Картриджи и расходники")], [5, i18nKey("СИЗ и спецодежда")], [6, i18nKey("Офисная мебель")],
  [7, i18nKey("Гигиена и чистящие средства")], [8, i18nKey("Продукты питания")], [9, i18nKey("Топливо-смазочные материалы")],
  [10, i18nKey("Запчасти для автотранспорта")], [11, i18nKey("Стройматериалы")], [12, i18nKey("Освещение и электротехника")],
  [13, i18nKey("Кондиционеры и вентиляция")], [14, i18nKey("Связь и телекоммуникации")], [15, i18nKey("Лицензии на ПО")],
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
    [t("Эталонный шаблон импорта закупок — Единая платформа трансформации")],
    [],
    [t("КАК ИМПОРТИРОВАТЬ")],
    [t("1. Один лист = одна компания. Имя листа — КОД из таблицы «Коды компаний» (NGMK, AGMK…). Регистр не важен.")],
    [t("2. Первая строка листа — заголовки колонок РОВНО как на листе «ОБРАЗЕЦ» (имена нельзя менять/переводить).")],
    [t("3. Каждая следующая строка — одна позиция (товар/услуга/работа) внутри лота.")],
    [t("4. Несколько товаров одного лота — несколько строк с ОДНИМ lotId (сумма контракта учитывается один раз).")],
    [t("5. Листы «СПРАВКА» и «ОБРАЗЕЦ» при импорте игнорируются (их имена — не коды компаний).")],
    [t("6. Загрузка: модуль «Анализ закупок» → меню ⋯ → Импорт Excel.")],
    [],
    [t("КОЛОНКИ (имя — обязательность — описание)")],
    ["lotId", t("обязательно"), t("ID лота/контракта. Строки с одним lotId = один лот.")],
    ["contractDate", t("желательно"), t("Дата контракта, формат YYYY-MM-DD.")],
    ["startDate", t("опц."), t("Дата начала процедуры, YYYY-MM-DD.")],
    ["purchaseType", t("желательно"), t("Способ закупки — см. «Способы закупки» ниже.")],
    ["platformName", t("опц."), t("Электронная площадка (например xarid.uz).")],
    ["vendor", t("желательно"), t("Наименование поставщика.")],
    ["vendorInn", t("желательно"), t("ИНН поставщика (для сквозных поставщиков/концентрации).")],
    ["regionName", t("опц."), t("Регион.")],
    ["Category", t("желательно"), t("Номер категории 1–15 (см. «Категории»). Пусто → «Без категории»." )],
    ["productCode", t("ВАЖНО"), t("Код товара (KTRU). По нему считается рыночная медиана и сравнение цен. Без кода — позиция не попадёт в ценовой бенчмарк.")],
    ["productName", t("желательно"), t("Наименование товара/услуги.")],
    ["productType", t("ВАЖНО"), t("PRODUCT (товар) / SERVICE (услуга) / WORK (работа). Пусто → определяется по ед.изм.")],
    ["unit", t("желательно"), t("Единица измерения (шт, кг, т, л … ; для услуг часто «shartli birlik»).")],
    ["amount", t("обязательно"), t("Количество (число > 0).")],
    ["Unit price", t("обязательно*"), t("Цена за единицу (число > 0). *Если пусто — будет вычислено как contractAmount / amount.")],
    ["startSumma", t("опц."), t("Начальная сумма процедуры (UZS).")],
    ["contractAmount", t("желательно"), t("Сумма контракта (UZS). Источник «спенда» лота; при пустой Unit price — основа для расчёта цены.")],
    ["savedAmount", t("опц."), t("Сэкономлено на торгах (UZS).")],
    ["savedPercent", t("опц."), t("Процент экономии.")],
    [],
    [t("СПОСОБЫ ЗАКУПКИ (purchaseType)")],
    ["E-SHOP", t("электронный магазин/каталог (НЕконкурентный — торга нет)")],
    ["AUCTION", t("аукцион (конкурентный)")],
    ["BEST_OFFER", t("лучшее предложение (конкурентный)")],
    ["OTHER_COMPETITIVE_METHODS", t("иные конкурентные методы")],
    ["TENDER", t("тендер (конкурентный)")],
    [],
    [t("ТИП ПОЗИЦИИ (productType)")],
    ["PRODUCT", t("товар — участвует в ценовом бенчмарке/рейтинге/потенциале")],
    ["SERVICE", t("услуга — показывается отдельно (несравнима по цене за единицу)")],
    ["WORK", t("работа — показывается отдельно")],
    [],
    [t("КАТЕГОРИИ (номер → название)")],
    ...IMPORT_CATEGORIES.map(([id, name]) => [id, t(name)]),
    [],
    [t("КОДЫ КОМПАНИЙ (имя листа → компания)")],
    ...IMPORT_COMPANIES.map(([code, name]) => [code, name]),
  ];
  const wsRef = XLSX.utils.aoa_to_sheet(ref);
  wsRef["!cols"] = [{ wch: 28 }, { wch: 18 }, { wch: 80 }];
  XLSX.utils.book_append_sheet(wb, wsRef, "СПРАВКА"); // i18n-exempt -- importer contract

  // ── Лист 2: ОБРАЗЕЦ (заголовки + примеры) ──
  const examples: (string | number)[][] = [
    [
      "L-2026-000123", "2026-01-15", "2026-01-05", "OTHER_COMPETITIVE_METHODS", "xarid.uz",
      "ООО «Канцторг»", "301234567", t("город Ташкент"), 2, "17.23.13.130-00007", // i18n-exempt -- supplier name is sample data
      t("Бумага офисная A4, 80 г/м²"), "PRODUCT", t("пачка"), 1000, 12500,
      13000000, 12500000, 500000, 3.8,
    ],
    [
      "L-2026-000124", "2026-02-10", "2026-02-01", "E-SHOP", "xarid.uz",
      "ООО «СпецСнаб»", "309876543", t("город Навои"), 5, "14.12.30.190-00002", // i18n-exempt -- supplier name is sample data
      t("Костюм рабочий, хлопок"), "PRODUCT", t("комплект"), 200, 185000,
      "", 37000000, 0, 0,
    ],
    [
      "L-2026-000125", "2026-03-05", "2026-02-20", "OTHER_COMPETITIVE_METHODS", "xt-xarid.uz",
      "ООО «КлинСервис»", "302555111", t("город Алмалык"), "", "81.21.10.000-00001", // i18n-exempt -- supplier name is sample data
      t("Уборка производственных помещений"), "SERVICE", "shartli birlik", 1, "",
      9000000, 8500000, 500000, 5.6,
    ],
  ];
  const wsEx = XLSX.utils.aoa_to_sheet([IMPORT_COLUMNS, ...examples]);
  wsEx["!cols"] = COL_WIDTHS;
  XLSX.utils.book_append_sheet(wb, wsEx, "ОБРАЗЕЦ"); // i18n-exempt -- importer contract

  // ── Листы 3..: по одному на компанию (только заголовки) ──
  for (const [code] of IMPORT_COMPANIES) {
    const ws = XLSX.utils.aoa_to_sheet([IMPORT_COLUMNS]);
    ws["!cols"] = COL_WIDTHS;
    XLSX.utils.book_append_sheet(wb, ws, code);
  }

  XLSX.writeFile(wb, "procurement_import_template.xlsx");
}
