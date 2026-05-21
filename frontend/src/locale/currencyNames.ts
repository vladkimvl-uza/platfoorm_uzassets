/**
 * Currency words + symbols + scale suffixes per locale.
 *
 * Intl can't generate "сум" / "so'm" / "сўм" reliably across browsers, so we
 * keep a small static map here. Same for compact scale suffixes (млрд / mlrd / B).
 */
import type { AppLocale } from "./locales";

export type CurrencyCode = "UZS" | "USD" | "EUR" | "RUB" | "CNY";

/** Full word ("сум", "so'm", etc.) — used in formal contexts. */
export const CURRENCY_WORD: Record<AppLocale, Record<CurrencyCode, string>> = {
  "ru":      { UZS: "сум",   USD: "долл.",  EUR: "евро",   RUB: "руб.",  CNY: "юань" },
  "uz-latn": { UZS: "soʻm",  USD: "dollar", EUR: "yevro",  RUB: "rubl",  CNY: "yuan" },
  "uz-cyr":  { UZS: "сўм",   USD: "доллар", EUR: "евро",   RUB: "рубль", CNY: "юан"  },
  "en":      { UZS: "UZS",   USD: "USD",    EUR: "EUR",    RUB: "RUB",   CNY: "CNY"  },
};

/** Symbol ("$", "€") — used in compact / button contexts. UZS has no widely-used symbol. */
export const CURRENCY_SYMBOL: Record<CurrencyCode, string> = {
  UZS: "",
  USD: "$",
  EUR: "€",
  RUB: "₽",
  CNY: "¥",
};

/** Compact scale suffixes for fmtMoneyCompact and fmtNumberCompact. */
export const SCALE_SUFFIX: Record<AppLocale, {
  thousand: string; million: string; billion: string; trillion: string;
}> = {
  "ru":      { thousand: "тыс.",  million: "млн",  billion: "млрд",  trillion: "трлн" },
  "uz-latn": { thousand: "ming",  million: "mln",  billion: "mlrd",  trillion: "trln" },
  "uz-cyr":  { thousand: "минг",  million: "млн",  billion: "млрд",  trillion: "трлн" },
  "en":      { thousand: "K",     million: "M",    billion: "B",     trillion: "T" },
};

/** Relative-time short suffixes (used when Intl.RelativeTimeFormat is unavailable). */
export const REL_SHORT: Record<AppLocale, {
  now: string;
  minute: (n: number, future: boolean) => string;
  hour:   (n: number, future: boolean) => string;
  day:    (n: number, future: boolean) => string;
  week:   (n: number, future: boolean) => string;
  month:  (n: number, future: boolean) => string;
  year:   (n: number, future: boolean) => string;
}> = {
  "ru":      {
    now: "сейчас",
    minute: (n, f) => f ? `через ${n} мин`  : `${n} мин назад`,
    hour:   (n, f) => f ? `через ${n} ч`    : `${n} ч назад`,
    day:    (n, f) => f ? `через ${n} дн`   : `${n} дн назад`,
    week:   (n, f) => f ? `через ${n} нед`  : `${n} нед назад`,
    month:  (n, f) => f ? `через ${n} мес`  : `${n} мес назад`,
    year:   (n, f) => f ? `через ${n} г.`   : `${n} г. назад`,
  },
  "uz-latn": {
    now: "hozir",
    minute: (n, f) => f ? `${n} daq keyin` : `${n} daq oldin`,
    hour:   (n, f) => f ? `${n} soat keyin`: `${n} soat oldin`,
    day:    (n, f) => f ? `${n} kun keyin` : `${n} kun oldin`,
    week:   (n, f) => f ? `${n} hafta keyin`: `${n} hafta oldin`,
    month:  (n, f) => f ? `${n} oy keyin`  : `${n} oy oldin`,
    year:   (n, f) => f ? `${n} yil keyin` : `${n} yil oldin`,
  },
  "uz-cyr": {
    now: "ҳозир",
    minute: (n, f) => f ? `${n} дақ кейин` : `${n} дақ олдин`,
    hour:   (n, f) => f ? `${n} соат кейин`: `${n} соат олдин`,
    day:    (n, f) => f ? `${n} кун кейин` : `${n} кун олдин`,
    week:   (n, f) => f ? `${n} ҳафта кейин`: `${n} ҳафта олдин`,
    month:  (n, f) => f ? `${n} ой кейин`  : `${n} ой олдин`,
    year:   (n, f) => f ? `${n} йил кейин` : `${n} йил олдин`,
  },
  "en": {
    now: "now",
    minute: (n, f) => f ? `in ${n}m` : `${n}m ago`,
    hour:   (n, f) => f ? `in ${n}h` : `${n}h ago`,
    day:    (n, f) => f ? `in ${n}d` : `${n}d ago`,
    week:   (n, f) => f ? `in ${n}w` : `${n}w ago`,
    month:  (n, f) => f ? `in ${n}mo`: `${n}mo ago`,
    year:   (n, f) => f ? `in ${n}y` : `${n}y ago`,
  },
};
