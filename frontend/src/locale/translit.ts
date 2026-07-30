/**
 * Транслитерация узбекской латиницы → узбекской кириллицы (uz-latn → uz-cyr).
 *
 * Словари платформы ведутся ТОЛЬКО в латинице — кириллическая графика
 * генерируется на лету этим модулем. Правила почти полностью регулярны;
 * редкие слова-исключения (в основном заимствования с «ь»: фильтр, модуль)
 * задаются в dict-модулях через export `cyr` и имеют приоритет (см. i18n.ts).
 *
 * Особые случаи:
 *  - oʻ/gʻ распознаются с любым видом апострофа (ʻ ' ` ’ ʼ);
 *  - остаточный апостроф (тутук белгиси) → ъ;
 *  - «e» в начале слова → э, внутри → е; диграф «ye» → е;
 *  - токены-акронимы (KPI, IFRS, FY…) и {placeholders} не транслитерируются.
 */

const ACRONYM_RE = /^[A-Z0-9.\-+/%№]{2,}$/;
// Одиночные I/V/X — римские цифры (I chorak → I чорак), не буквы слова.
const ROMAN_RE = /^[IVX]$/;

// Порядок важен: сначала диграфы/апострофные пары, затем одиночные буквы.
const DIGRAPHS: Array<[RegExp, string]> = [
  // Заимствования на -tsiya/-tsion (generatsiya, operatsion) → ция/цион:
  // без этого правила транслит давал бы «генератсия/оператсион».
  [/tsiya/g, "ция"], [/Tsiya/g, "Ция"], [/TSIYA/g, "ЦИЯ"],
  [/tsion/g, "цион"], [/Tsion/g, "Цион"], [/TSION/g, "ЦИОН"],
  [/O[ʻ'`’ʼ]/g, "Ў"], [/o[ʻ'`’ʼ]/g, "ў"],
  [/G[ʻ'`’ʼ]/g, "Ғ"], [/g[ʻ'`’ʼ]/g, "ғ"],
  [/SH/g, "Ш"], [/Sh/g, "Ш"], [/sh/g, "ш"],
  [/CH/g, "Ч"], [/Ch/g, "Ч"], [/ch/g, "ч"],
  [/YO/g, "Ё"], [/Yo/g, "Ё"], [/yo/g, "ё"],
  [/YA/g, "Я"], [/Ya/g, "Я"], [/ya/g, "я"],
  [/YU/g, "Ю"], [/Yu/g, "Ю"], [/yu/g, "ю"],
  [/YE/g, "Е"], [/Ye/g, "Е"], [/ye/g, "е"],
];

const SINGLES: Record<string, string> = {
  a: "а", b: "б", c: "с", d: "д", e: "е", f: "ф", g: "г", h: "ҳ", i: "и",
  j: "ж", k: "к", l: "л", m: "м", n: "н", o: "о", p: "п", q: "қ", r: "р",
  s: "с", t: "т", u: "у", v: "в", x: "х", y: "й", z: "з",
  A: "А", B: "Б", C: "С", D: "Д", E: "Е", F: "Ф", G: "Г", H: "Ҳ", I: "И",
  J: "Ж", K: "К", L: "Л", M: "М", N: "Н", O: "О", P: "П", Q: "Қ", R: "Р",
  S: "С", T: "Т", U: "У", V: "В", X: "Х", Y: "Й", Z: "З",
};

function translitWord(w: string): string {
  if (ACRONYM_RE.test(w)) return w;   // KPI, IFRS, FY-2026 — остаются латиницей
  if (ROMAN_RE.test(w)) return w;     // I/V/X — римские цифры
  let s = w;
  for (const [re, sub] of DIGRAPHS) s = s.replace(re, sub);
  // «e» в начале слова → э (после диграфов: «ye» уже стало «е»)
  s = s.replace(/^E/, "Э").replace(/^e/, "э");
  // остаточный апостроф-тутук → ъ
  s = s.replace(/[ʻ'`’ʼ]/g, "ъ");
  let out = "";
  for (const ch of s) out += SINGLES[ch] ?? ch;
  return out;
}

/** Полная строка: слова транслитерируются, {placeholders} и не-буквы — как есть. */
export function translitLatinToCyrillic(text: string): string {
  return text
    .split(/(\{\w+\})/)                                   // не трогаем плейсхолдеры
    .map((part) =>
      part.startsWith("{")
        ? part
        : part.replace(/[A-Za-zʻʼ'`’]+/g, (w) => translitWord(w)),
    )
    .join("");
}

const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "j",
  з: "z", и: "i", й: "y", к: "k", қ: "q", л: "l", м: "m", н: "n",
  о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "x",
  ҳ: "h", ц: "ts", ч: "ch", ш: "sh", ъ: "ʼ", ь: "", э: "e", ю: "yu",
  я: "ya", ў: "oʻ", ғ: "gʻ",
  А: "A", Б: "B", В: "V", Г: "G", Д: "D", Е: "E", Ё: "Yo", Ж: "J",
  З: "Z", И: "I", Й: "Y", К: "K", Қ: "Q", Л: "L", М: "M", Н: "N",
  О: "O", П: "P", Р: "R", С: "S", Т: "T", У: "U", Ф: "F", Х: "X",
  Ҳ: "H", Ц: "Ts", Ч: "Ch", Ш: "Sh", Ъ: "ʼ", Ь: "", Э: "E", Ю: "Yu",
  Я: "Ya", Ў: "Oʻ", Ғ: "Gʻ",
};

/** Узбекская кириллица → латиница для локализованных данных из БД. */
export function translitCyrillicToLatin(text: string): string {
  let out = "";
  for (const ch of text) out += CYRILLIC_TO_LATIN[ch] ?? ch;
  return out;
}
