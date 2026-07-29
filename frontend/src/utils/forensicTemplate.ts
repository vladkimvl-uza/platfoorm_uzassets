import { i18nKey } from "@/locale/keys";
import { t } from "@/locale/i18n";
interface ForensicCompanyMini {
  n: string;
  k: string;
  s: string;
}

const SECTOR_LABELS_RU: Record<string, string> = {
  mining:    i18nKey("Горнодобывающий"),
  oilgas:    i18nKey("Нефтегазовый"),
  energy:    i18nKey("Энергетика"),
  transport: i18nKey("Транспорт"),
  other:     i18nKey("Прочие"),
};

/** Generate the workbook and trigger browser download. xlsx lazy-loaded on first call. */
export async function downloadForensicTemplate(companies: ForensicCompanyMini[], year: number = 2026): Promise<void> {
  const XLSX = await import("xlsx");
  const wb = XLSX.utils.book_new();

  // ─── Sheet 1: Instructions ───
  const instr: (string | number)[][] = [
    [t("ШАБЛОН ИМПОРТА · Закупки и Форензик аудит · {year} год", { year })],
    [""],
    [t("КАК ЗАПОЛНЯТЬ:")],
    [t("1. Лист «Компании» — справочник, не редактируйте.")],
    [t("2. Лист «Данные» — заполните по каждой компании план/факт по году + квартально.")],
    [""],
    [t("ПОЛЯ:")],
    [t("• Код компании — обязателен, ровно как в листе «Компании».")],
    [t("• Год — 4-значное число.")],
    [t("• Все суммы — в млрд сум, только числа (без пробелов / валют).")],
    [t("• Статус плана: «Утверждён» / «Не утверждён» / пусто.")],
    [t("• Статус форензика: «Завершён» / «В процессе» / «Тендер в YYYY» / «Не начат» / пусто.")],
    [t("• Аудитор: KPMG / PwC / Deloitte / E&Y (или пусто).")],
    [""],
    [t("ИМПОРТ ВЫПОЛНЯЕТСЯ ЧЕРЕЗ МЕНЮ ⋮ → ИМПОРТ EXCEL")],
  ];
  const ws0 = XLSX.utils.aoa_to_sheet(instr);
  ws0["!cols"] = [{ wch: 90 }];
  XLSX.utils.book_append_sheet(wb, ws0, "Инструкция"); // i18n-exempt -- stable workbook sheet name

  // ─── Sheet 2: Companies ───
  const coData: (string | number)[][] = [
    // i18n-exempt-start -- exact import headers consumed by the parser.
    ["Код", "Полное название", "Сектор (id)", "Сектор (название)"],
    // i18n-exempt-end
  ];
  // i18n-exempt-start -- official fallback company names are data.
  const cos = companies.length ? companies : [
    { n: "НГМК",          k: "ngmk", s: "mining"    },
    { n: "Узбекуголь",    k: "uug",  s: "mining"    },
    { n: "Узбекнефтегаз", k: "ung",  s: "oilgas"    },
    { n: "Узтрансгаз",    k: "utg",  s: "oilgas"    },
    { n: "ТЭС",           k: "tes",  s: "energy"    },
    { n: "UzTelecom",     k: "utc",  s: "transport" },
    { n: "Узкимёсаноат",  k: "uks",  s: "other"     },
  ];
  // i18n-exempt-end
  for (const co of cos) {
    coData.push([co.k, co.n, co.s, SECTOR_LABELS_RU[co.s] ? t(SECTOR_LABELS_RU[co.s]) : ""]);
  }
  const ws1 = XLSX.utils.aoa_to_sheet(coData);
  ws1["!cols"] = [{ wch: 12 }, { wch: 38 }, { wch: 14 }, { wch: 28 }];
  XLSX.utils.book_append_sheet(wb, ws1, "Компании"); // i18n-exempt -- importer contract

  // ─── Sheet 3: Data — one row per (company × year) ───
  // i18n-exempt-start -- exact import headers and accepted status values.
  const dataHeaders = [
    "Код компании", "Компания", "Год",
    "План год", "Факт год",
    "План 9 мес", "Факт 9 мес",
    "Q1 план", "Q1 факт", "Q2 план", "Q2 факт",
    "Q3 план", "Q3 факт", "Q4 план", "Q4 факт",
    "Статус плана", "Статус форензика", "Аудитор", "Период аудита",
  ];
  const dataRows: (string | number)[][] = [dataHeaders];

  // Pre-fill 3 example rows (first 3 companies for current year)
  cos.slice(0, 3).forEach((co, i) => {
    dataRows.push([
      co.k, co.n, year,
      1500 + i * 200,  1200 + i * 150,
      1100 + i * 150,   900 + i * 100,
        300 + i * 30,    250 + i * 25,
        400 + i * 40,    350 + i * 30,
        400 + i * 40,    300 + i * 35,
        400 + i * 50,    300 + i * 50,
      i === 0 ? "Утверждён" : "Не утверждён",
      i === 0 ? "Завершён" : i === 1 ? "В процессе" : `Тендер в ${year}`,
      i === 0 ? "KPMG" : i === 1 ? "PwC" : "Deloitte",
      i === 0 ? "2024-2025" : `${year - 1}-${year}`,
    ]);
  });
  // i18n-exempt-end

  // 20 empty rows for the user
  for (let i = 0; i < 20; i++) {
    dataRows.push(["", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]);
  }

  const ws2 = XLSX.utils.aoa_to_sheet(dataRows);
  ws2["!cols"] = [
    { wch: 12 }, { wch: 30 }, { wch: 8 },
    { wch: 11 }, { wch: 11 }, { wch: 12 }, { wch: 12 },
    { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 10 },
    { wch: 10 }, { wch: 10 }, { wch: 10 }, { wch: 10 },
    { wch: 18 }, { wch: 22 }, { wch: 12 }, { wch: 16 },
  ];
  XLSX.utils.book_append_sheet(wb, ws2, "Данные"); // i18n-exempt -- importer contract

  // Trigger download
  XLSX.writeFile(wb, `procurement_forensic_template_${year}.xlsx`);
}
