import { getCurrentIntlLocale } from "@/locale/i18n";
import { APP_TIMEZONE } from "@/locale/locales";

interface ParsedRatingDate {
  date: Date;
  hasDay: boolean;
}

const MONTH_NUMBER: Record<string, number> = {
  // i18n-exempt-start: accepted month tokens from persisted/imported date data.
  jan: 1, january: 1, yan: 1, yanv: 1, yanvar: 1, янв: 1, январь: 1, января: 1,
  feb: 2, february: 2, fev: 2, fevral: 2, фев: 2, февраль: 2, февраля: 2,
  mar: 3, march: 3, mart: 3, мар: 3, март: 3, марта: 3,
  apr: 4, april: 4, aprel: 4, апр: 4, апрель: 4, апреля: 4,
  may: 5, май: 5, мая: 5,
  jun: 6, june: 6, iyun: 6, июн: 6, июнь: 6, июня: 6,
  jul: 7, july: 7, iyul: 7, июл: 7, июль: 7, июля: 7,
  aug: 8, august: 8, avg: 8, avgust: 8, авг: 8, август: 8, августа: 8,
  sep: 9, sept: 9, september: 9, sen: 9, sent: 9, sentabr: 9, сен: 9, сент: 9, сентябрь: 9, сентября: 9,
  oct: 10, october: 10, okt: 10, oktabr: 10, окт: 10, октябрь: 10, октября: 10,
  nov: 11, november: 11, noy: 11, noyabr: 11, ноя: 11, ноябрь: 11, ноября: 11,
  dec: 12, december: 12, dek: 12, dekabr: 12, дек: 12, декабрь: 12, декабря: 12,
  // i18n-exempt-end
};

function monthNumber(token: string): number | null {
  const normalized = token.trim().toLocaleLowerCase().replace(/\.$/, "");
  return MONTH_NUMBER[normalized] || null;
}

function buildDate(year: number, month: number, day: number, hasDay: boolean): ParsedRatingDate | null {
  if (year < 1900 || year > 2200 || month < 1 || month > 12 || day < 1 || day > 31) return null;
  const date = new Date(Date.UTC(year, month - 1, day, 12));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return { date, hasDay };
}

function parseRatingDate(value: string): ParsedRatingDate | null {
  const raw = value.trim();
  let match = raw.match(/^(\d{4})-(\d{1,2})(?:-(\d{1,2}))?/);
  if (match) return buildDate(Number(match[1]), Number(match[2]), Number(match[3] || 1), !!match[3]);

  match = raw.match(/^(\d{1,2})[./](\d{1,2})[./](\d{4})$/);
  if (match) return buildDate(Number(match[3]), Number(match[2]), Number(match[1]), true);

  match = raw.match(/^(\d{1,2})\s+([^\d\s]+)\s+(\d{4})$/u);
  if (match) {
    const month = monthNumber(match[2]);
    return month ? buildDate(Number(match[3]), month, Number(match[1]), true) : null;
  }

  match = raw.match(/^([^\d\s]+)\s+(\d{4})$/u);
  if (match) {
    const month = monthNumber(match[1]);
    return month ? buildDate(Number(match[2]), month, 1, false) : null;
  }

  match = raw.match(/^(\d{4})\s+([^\d\s]+)$/u);
  if (match) {
    const month = monthNumber(match[2]);
    return month ? buildDate(Number(match[1]), month, 1, false) : null;
  }
  return null;
}

export function formatRatingDate(
  value: string | null | undefined,
  options: { monthYear?: boolean } = {},
): string {
  const raw = (value || "").trim();
  if (!raw) return "";
  const parsed = parseRatingDate(raw);
  if (!parsed) return raw;

  const formatOptions: Intl.DateTimeFormatOptions = {
    month: "short",
    year: "numeric",
    timeZone: APP_TIMEZONE,
  };
  if (!options.monthYear && parsed.hasDay) formatOptions.day = "2-digit";
  const formatter = new Intl.DateTimeFormat(getCurrentIntlLocale(), formatOptions);
  if (!options.monthYear && parsed.hasDay) return formatter.format(parsed.date);

  const parts = formatter.formatToParts(parsed.date);
  const month = (parts.find((part) => part.type === "month")?.value || "").replace(/\.$/, "");
  const year = parts.find((part) => part.type === "year")?.value || "";
  return month && year ? `${month} ${year}` : formatter.format(parsed.date);
}

export function ratingDateSortKey(value: string | null | undefined): string {
  const raw = (value || "").trim();
  if (!raw) return "0000-00-00";
  const parsed = parseRatingDate(raw);
  if (!parsed) return raw.toLocaleLowerCase();
  const year = parsed.date.getUTCFullYear();
  const month = String(parsed.date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(parsed.date.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}
