/**
 * Скан остаточной (необёрнутой) кириллицы во фронтенде.
 *
 * Эвристика: строка кода содержит кириллицу, но НЕ содержит вызова t(...)
 * вокруг неё, не является комментарием и не лежит в словарях/локали.
 * Выдаёт файл:строка + текст — рабочий список для фикс-раунда.
 *
 *   node scripts/i18n-residual.mjs            — сводка по файлам
 *   node scripts/i18n-residual.mjs --lines    — все строки
 *   node scripts/i18n-residual.mjs --top 30   — топ-N файлов
 */
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.cwd(), "src");
const CYR = /[А-Яа-яЁё]/;
const args = process.argv.slice(2);
const showLines = args.includes("--lines");
const topN = args.includes("--top") ? Number(args[args.indexOf("--top") + 1] || 20) : 20;

const SKIP_DIRS = ["/locale/", "\\locale\\", "__tests__", "/test/", "\\test\\", "/sdk/", "\\sdk\\"];

/** Комментарий/лог/сравнение с данными — не считаем долгом. */
function isExempt(line) {
  const s = line.trim();
  if (s.startsWith("//") || s.startsWith("*") || s.startsWith("/*") || s.startsWith("<!--")) return true;
  if (/console\.(log|warn|error|info|debug)/.test(s)) return true;
  // строка целиком внутри t("...") / t('...') / t(`...`)
  return false;
}

/** Убираем из строки содержимое всех вызовов t("…") — остаток и есть долг. */
function stripTranslated(line) {
  return line
    .replace(/\bt\(\s*"(?:[^"\\]|\\.)*"/g, 't("')
    .replace(/\bt\(\s*'(?:[^'\\]|\\.)*'/g, "t('")
    .replace(/\bt\(\s*`(?:[^`\\]|\\.)*`/g, "t(`");
}

const perFile = new Map();
let totalLines = 0;

function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { walk(p); continue; }
    if (!/\.(vue|ts)$/.test(e.name)) continue;
    const rel = p.replace(/\\/g, "/");
    if (SKIP_DIRS.some((s) => rel.includes(s.replace(/\\/g, "/")))) continue;
    const src = fs.readFileSync(p, "utf8");
    let inBlockComment = false;
    let inHtmlComment = false;
    const hits = [];
    src.split("\n").forEach((line, i) => {
      const t = line.trim();
      if (inBlockComment) { if (t.includes("*/")) inBlockComment = false; return; }
      if (inHtmlComment) { if (t.includes("-->")) inHtmlComment = false; return; }
      if (t.startsWith("/*") && !t.includes("*/")) { inBlockComment = true; return; }
      if (t.startsWith("<!--") && !t.includes("-->")) { inHtmlComment = true; return; }
      if (!CYR.test(line)) return;
      if (isExempt(line)) return;
      const rest = stripTranslated(line);
      if (!CYR.test(rest)) return;
      hits.push([i + 1, t.slice(0, 140)]);
    });
    if (hits.length) { perFile.set(rel, hits); totalLines += hits.length; }
  }
}
walk(ROOT);

const sorted = [...perFile.entries()].sort((a, b) => b[1].length - a[1].length);
console.log(`Файлов с остатками: ${perFile.size}; строк с необёрнутой кириллицей: ${totalLines}\n`);
for (const [f, hits] of sorted.slice(0, showLines ? sorted.length : topN)) {
  console.log(`${String(hits.length).padStart(5)}  ${f}`);
  if (showLines) for (const [n, s] of hits) console.log(`         :${n}  ${s}`);
}
