/**
 * Календарь государственных праздников Республики Узбекистан 2025-2027.
 *
 * ИСТОЧНИКИ (в порядке актуальности):
 *   1. Указ Президента №УП-257 от 24.12.2025 -- "Об установлении дополнительных
 *      нерабочих дней в период празднования официальных дат и переносе
 *      выходных дней в 2026 году" (president.uz/ru/lists/view/8832)
 *   2. Постановление Президента от 18.03.2026 -- дата Руза хайит
 *   3. Трудовой кодекс РУз ст. 208 -- постоянные нерабочие даты
 *   4. buxgalter.uz / kadrovik.uz -- производственный календарь
 *
 * Религиозные праздники (Руза/Курбан хайит) объявляются Постановлением
 * Президента отдельно за неделю до даты. Указанные даты для 2026 -- предв.
 *
 * ОБНОВЛЕНИЕ: при выходе нового Указа на следующий год -- добавить в
 * UZ_HOLIDAYS соответствующий блок. Праздники меняются раз в год.
 */

export type HolidayKind =
  | "public" // постоянные нерабочие (1 янв, 8 мар, 9 мая...)
  | "religious" // Руза/Курбан хайит
  | "memorial" // памятные (рабочие, например 14 янв)
  | "transferred" // выходной перенесённый на понедельник
  | "extra"; // дополнительный нерабочий по Указу

export interface UzHoliday {
  date: string; // YYYY-MM-DD
  title_ru: string;
  title_uz: string;
  title_en: string;
  kind: HolidayKind;
  is_dayoff: boolean; // нерабочий ли это день
  description?: string;
  // Для transferred: с какого дня перенесён
  transferred_from?: string;
  // Для 5/6-дневной недели различия
  applies_5day?: boolean; // действует для 5-дневки (default true)
  applies_6day?: boolean; // действует для 6-дневки (default true)
}

// === 2025 (для архивных записей и прошлых дат) ===
const HOLIDAYS_2025: UzHoliday[] = [
  { date: "2025-01-01", title_ru: "Новый год", title_uz: "Yangi yil", title_en: "New Year", kind: "public", is_dayoff: true },
  { date: "2025-01-14", title_ru: "День защитников Родины", title_uz: "Vatan himoyachilari kuni", title_en: "Defender of the Motherland Day", kind: "memorial", is_dayoff: false },
  { date: "2025-03-08", title_ru: "Международный женский день", title_uz: "Xalqaro xotin-qizlar kuni", title_en: "International Women's Day", kind: "public", is_dayoff: true },
  { date: "2025-03-21", title_ru: "Навруз", title_uz: "Navro'z", title_en: "Navruz", kind: "public", is_dayoff: true },
  { date: "2025-03-30", title_ru: "Руза хайит (Рамазон хайит)", title_uz: "Ro'za hayit", title_en: "Eid al-Fitr", kind: "religious", is_dayoff: true },
  { date: "2025-05-09", title_ru: "День памяти и почестей", title_uz: "Xotira va qadrlash kuni", title_en: "Day of Remembrance and Honor", kind: "public", is_dayoff: true },
  { date: "2025-06-06", title_ru: "Курбан хайит", title_uz: "Qurbon hayit", title_en: "Eid al-Adha", kind: "religious", is_dayoff: true },
  { date: "2025-09-01", title_ru: "День Независимости", title_uz: "Mustaqillik kuni", title_en: "Independence Day", kind: "public", is_dayoff: true },
  { date: "2025-10-01", title_ru: "День учителя и наставника", title_uz: "O'qituvchi va murabbiylar kuni", title_en: "Teacher's Day", kind: "public", is_dayoff: true },
  { date: "2025-12-08", title_ru: "День Конституции", title_uz: "Konstitutsiya kuni", title_en: "Constitution Day", kind: "public", is_dayoff: true },
  { date: "2025-12-31", title_ru: "Дополнительный выходной (Новый год)", title_uz: "Qo'shimcha dam olish kuni", title_en: "Extra day off (New Year)", kind: "extra", is_dayoff: true },
];

// === 2026 -- по Указу Президента №УП-257 от 24.12.2025 ===
const HOLIDAYS_2026: UzHoliday[] = [
  { date: "2026-01-01", title_ru: "Новый год", title_uz: "Yangi yil", title_en: "New Year", kind: "public", is_dayoff: true },
  { date: "2026-01-02", title_ru: "Дополнительный выходной (Новый год)", title_uz: "Qo'shimcha dam olish kuni", title_en: "Extra day off (New Year)", kind: "extra", is_dayoff: true, transferred_from: "2026-01-01" },
  { date: "2026-01-14", title_ru: "День защитников Родины", title_uz: "Vatan himoyachilari kuni", title_en: "Defender of the Motherland Day", kind: "memorial", is_dayoff: false },
  { date: "2026-03-08", title_ru: "Международный женский день", title_uz: "Xalqaro xotin-qizlar kuni", title_en: "International Women's Day", kind: "public", is_dayoff: true },
  { date: "2026-03-09", title_ru: "Перенос с 8 марта (для 5-дневки)", title_uz: "Dam olish kuni ko'chirilgan", title_en: "Day off transferred (5-day week)", kind: "transferred", is_dayoff: true, transferred_from: "2026-03-08", applies_5day: true, applies_6day: false },
  { date: "2026-03-20", title_ru: "Руза хайит (Рамазон хайит)", title_uz: "Ro'za hayit", title_en: "Eid al-Fitr", kind: "religious", is_dayoff: true, description: "Постановление Президента от 18.03.2026" },
  { date: "2026-03-21", title_ru: "Навруз", title_uz: "Navro'z", title_en: "Navruz", kind: "public", is_dayoff: true },
  { date: "2026-03-23", title_ru: "Перенос с 21 марта (для 5-дневки)", title_uz: "Dam olish kuni ko'chirilgan", title_en: "Day off transferred (5-day week)", kind: "transferred", is_dayoff: true, transferred_from: "2026-03-21", applies_5day: true, applies_6day: false },
  { date: "2026-05-09", title_ru: "День памяти и почестей", title_uz: "Xotira va qadrlash kuni", title_en: "Day of Remembrance and Honor", kind: "public", is_dayoff: true },
  { date: "2026-05-11", title_ru: "Перенос с 9 мая (для 5-дневки)", title_uz: "Dam olish kuni ko'chirilgan", title_en: "Day off transferred (5-day week)", kind: "transferred", is_dayoff: true, transferred_from: "2026-05-09", applies_5day: true, applies_6day: false },
  { date: "2026-05-27", title_ru: "Курбан хайит", title_uz: "Qurbon hayit", title_en: "Eid al-Adha", kind: "religious", is_dayoff: true, description: "Предв. дата по лунному календарю" },
  { date: "2026-05-28", title_ru: "Дополнительный выходной (Курбан хайит)", title_uz: "Qo'shimcha dam olish kuni", title_en: "Extra day off (Eid al-Adha)", kind: "extra", is_dayoff: true, transferred_from: "2026-05-27" },
  { date: "2026-05-29", title_ru: "Дополнительный выходной (Курбан хайит)", title_uz: "Qo'shimcha dam olish kuni", title_en: "Extra day off (Eid al-Adha)", kind: "extra", is_dayoff: true, transferred_from: "2026-05-27" },
  { date: "2026-08-31", title_ru: "Дополнительный выходной (День Независимости)", title_uz: "Qo'shimcha dam olish kuni", title_en: "Extra day off (Independence)", kind: "extra", is_dayoff: true, transferred_from: "2026-09-01" },
  { date: "2026-09-01", title_ru: "День Независимости", title_uz: "Mustaqillik kuni", title_en: "Independence Day", kind: "public", is_dayoff: true },
  { date: "2026-10-01", title_ru: "День учителя и наставника", title_uz: "O'qituvchi va murabbiylar kuni", title_en: "Teacher's Day", kind: "public", is_dayoff: true },
  { date: "2026-12-08", title_ru: "День Конституции", title_uz: "Konstitutsiya kuni", title_en: "Constitution Day", kind: "public", is_dayoff: true },
  { date: "2026-12-31", title_ru: "Перенос (с 12 дек, для 5-дневки)", title_uz: "Dam olish kuni ko'chirilgan", title_en: "Day off transferred (5-day week)", kind: "transferred", is_dayoff: true, transferred_from: "2026-12-12", applies_5day: true, applies_6day: false },
];

// === 2027 -- скелет, постоянные даты по ТК ст. 208 ===
// Религиозные/переносы добавятся после Указа Президента (декабрь 2026).
const HOLIDAYS_2027: UzHoliday[] = [
  { date: "2027-01-01", title_ru: "Новый год", title_uz: "Yangi yil", title_en: "New Year", kind: "public", is_dayoff: true },
  { date: "2027-01-14", title_ru: "День защитников Родины", title_uz: "Vatan himoyachilari kuni", title_en: "Defender of the Motherland Day", kind: "memorial", is_dayoff: false },
  { date: "2027-03-08", title_ru: "Международный женский день", title_uz: "Xalqaro xotin-qizlar kuni", title_en: "International Women's Day", kind: "public", is_dayoff: true },
  { date: "2027-03-21", title_ru: "Навруз", title_uz: "Navro'z", title_en: "Navruz", kind: "public", is_dayoff: true },
  { date: "2027-05-09", title_ru: "День памяти и почестей", title_uz: "Xotira va qadrlash kuni", title_en: "Day of Remembrance and Honor", kind: "public", is_dayoff: true },
  { date: "2027-09-01", title_ru: "День Независимости", title_uz: "Mustaqillik kuni", title_en: "Independence Day", kind: "public", is_dayoff: true },
  { date: "2027-10-01", title_ru: "День учителя и наставника", title_uz: "O'qituvchi va murabbiylar kuni", title_en: "Teacher's Day", kind: "public", is_dayoff: true },
  { date: "2027-12-08", title_ru: "День Конституции", title_uz: "Konstitutsiya kuni", title_en: "Constitution Day", kind: "public", is_dayoff: true },
];

export const UZ_HOLIDAYS: UzHoliday[] = [
  ...HOLIDAYS_2025,
  ...HOLIDAYS_2026,
  ...HOLIDAYS_2027,
];

// === Цвета по kind (UzAssets palette) ===
export const HOLIDAY_KIND_COLORS: Record<HolidayKind, string> = {
  public: "#1D9E75", // teal -- основные госпраздники
  religious: "#EF9F27", // amber -- религиозные
  memorial: "#378ADD", // blue -- памятные (рабочие)
  transferred: "#7F77DD", // purple -- переносы
  extra: "#7F77DD", // purple -- доп. выходные
};

export const HOLIDAY_KIND_LABELS: Record<HolidayKind, string> = {
  public: "Государственный",
  religious: "Религиозный",
  memorial: "Памятный",
  transferred: "Перенос",
  extra: "Доп. выходной",
};

// ============================================================
// Helpers
// ============================================================

const _byDate: Map<string, UzHoliday[]> = new Map();
for (const h of UZ_HOLIDAYS) {
  if (!_byDate.has(h.date)) _byDate.set(h.date, []);
  _byDate.get(h.date)!.push(h);
}

/** YYYY-MM-DD строка из Date в локальной TZ Tashkent. */
export function toIsoDate(d: Date | string): string {
  if (typeof d === "string") {
    // Если уже YYYY-MM-DD -- вернуть как есть
    if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
    return toIsoDate(new Date(d));
  }
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Все праздники на конкретную дату (может быть несколько -- 20-21 марта 2026). */
export function getHolidays(date: Date | string): UzHoliday[] {
  return _byDate.get(toIsoDate(date)) || [];
}

/** Первый праздник (для UI badge). null если нет. */
export function getHoliday(date: Date | string): UzHoliday | null {
  const list = getHolidays(date);
  return list[0] || null;
}

/** Праздник ли это (любой kind). */
export function isHoliday(date: Date | string): boolean {
  return getHolidays(date).length > 0;
}

/** Официальный нерабочий день? Учитывает workweek (5 vs 6). */
export function isOfficialDayoff(
  date: Date | string,
  workweek: 5 | 6 = 5,
): boolean {
  const list = getHolidays(date);
  for (const h of list) {
    if (!h.is_dayoff) continue;
    if (workweek === 5 && h.applies_5day === false) continue;
    if (workweek === 6 && h.applies_6day === false) continue;
    return true;
  }
  // Воскресенье -- всегда выходной
  const d = typeof date === "string" ? new Date(date) : date;
  if (d.getDay() === 0) return true;
  // Суббота -- выходной только при 5-дневке
  if (workweek === 5 && d.getDay() === 6) return true;
  return false;
}

/** Следующий рабочий день (учитывает праздники + выходные). */
export function nextWorkingDay(
  date: Date | string,
  workweek: 5 | 6 = 5,
): Date {
  let d = typeof date === "string" ? new Date(date) : new Date(date);
  d.setDate(d.getDate() + 1);
  // Защита от бесконечного цикла
  for (let i = 0; i < 14; i++) {
    if (!isOfficialDayoff(d, workweek)) return d;
    d.setDate(d.getDate() + 1);
  }
  return d;
}

/** Предстоящие праздники в диапазоне [from, from+days]. */
export function upcomingHolidays(
  from: Date = new Date(),
  days: number = 14,
): UzHoliday[] {
  const fromIso = toIsoDate(from);
  const to = new Date(from);
  to.setDate(to.getDate() + days);
  const toIso = toIsoDate(to);

  const result: UzHoliday[] = [];
  for (const h of UZ_HOLIDAYS) {
    if (h.date >= fromIso && h.date <= toIso) {
      result.push(h);
    }
  }
  result.sort((a, b) => a.date.localeCompare(b.date));
  return result;
}

/** Сколько дней до даты (целое, может быть отрицательным). */
export function daysUntil(date: Date | string, from: Date = new Date()): number {
  const target = typeof date === "string" ? new Date(date) : date;
  const ms = target.getTime() - from.getTime();
  return Math.round(ms / 86_400_000);
}

/** Форматирование даты праздника для группировочного заголовка. */
export function formatHolidayDate(d: Date | string): string {
  const date = typeof d === "string" ? new Date(d) : d;
  const months = [
    "янв", "фев", "мар", "апр", "май", "июн",
    "июл", "авг", "сен", "окт", "ноя", "дек",
  ];
  return `${date.getDate()} ${months[date.getMonth()]}`;
}

/** Проверить попадает ли due_date на нерабочий и предложить альтернативу. */
export function checkDueDateConflict(
  date: Date | string,
  workweek: 5 | 6 = 5,
): { conflicts: boolean; holiday: UzHoliday | null; suggested: Date | null } {
  if (!isOfficialDayoff(date, workweek)) {
    return { conflicts: false, holiday: null, suggested: null };
  }
  return {
    conflicts: true,
    holiday: getHoliday(date),
    suggested: nextWorkingDay(date, workweek),
  };
}
