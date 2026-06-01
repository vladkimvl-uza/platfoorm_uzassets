#!/usr/bin/env node
/* ============================================================================
   UzAssets · unify-tokens.mjs · codemod (АДАПТИРОВАН под токены ЭТОГО проекта)
   ─────────────────────────────────────────────────────────────────────────
   Оригинал из fixes-пакета был калиброван под чужой tokens.css
   (--purple, --brand, --danger, --tint-…, --ease), которого в репо НЕТ. Здесь MAP
   переписан на реальные токены проекта (colors_and_type.css):
     --t3 --t-muted --border-input --border-hard --p-deep --green --amber
     --blue --sev-high(red) --sev-mid --sev-critical --green-l --red-l --orange-l
     --ease-standard --ease-out --font

   AUTO  — ТОЛЬКО value-точные замены (light-значение токена == легаси-хекс),
           значит в светлой теме ноль визуального сдвига; тема-варьирующие
           токены вдобавок корректно темнеют.
   CONSOLIDATE — кандидаты со сдвигом оттенка (#7f77dd→--p, light-greys→--bg2/3):
           НЕ применяются, только в отчёт — решение за человеком.
   REVIEW — контекстное (navy текст vs градиент, веса, эмодзи) — только отчёт.

     node scripts/unify-tokens.mjs                 # DRY-RUN
     node scripts/unify-tokens.mjs --write         # применить AUTO
     node scripts/unify-tokens.mjs --write frontend/src/components/ExecDash
   ========================================================================== */
import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const WRITE = process.argv.includes("--write");
const argPath = process.argv.find((a, i) => i >= 2 && !a.startsWith("--"));
const ROOT = argPath || "frontend/src";
// ТОЛЬКО style-контексты: .css/.scss целиком, .vue — лишь внутри <style>.
// .ts/.js и <script>-секции НЕ трогаем (там хексы = Chart.js/canvas-цвета,
// где var(--…) не резолвится → графики поломались бы).
const EXT = new Set([".vue", ".css", ".scss"]);
const SKIP_FILES = new Set(["colors_and_type.css", "tokens.css"]);

/* AUTO: value-точные литералы → var() (light == токен, dark корректен). */
const MAP = {
  "#64748b": "var(--t3)",
  "#888780": "var(--t-muted)",
  "#e2e8f0": "var(--border-input)",
  "#e5e7eb": "var(--border-hard)",
  "#534ab7": "var(--p-deep)",
  "#1d9e75": "var(--green)",
  "#ef9f27": "var(--amber)",
  "#378add": "var(--blue)",
  "#e24b4a": "var(--sev-high)",       // красный — выбор пользователя
  "#ba7517": "var(--sev-mid)",
  "#a32d2d": "var(--sev-critical)",
  "#dcfce7": "var(--green-l)",
  "#fee2e2": "var(--red-l)",
  "#fef9c3": "var(--orange-l)",
};

/* AUTO: строковые (easing точно совпадает, font). */
const STR = [
  [/cubic-bezier\(\s*0?\.34\s*,\s*1\.2\s*,\s*0?\.64\s*,\s*1\s*\)/gi, "var(--ease-standard)"],
  [/cubic-bezier\(\s*\.?0?\.22\s*,\s*1\s*,\s*\.?0?\.36\s*,\s*1\s*\)/gi, "var(--ease-out)"],
  [/'Inter',\s*'SF Pro',\s*'Helvetica Neue',\s*Arial,\s*sans-serif/gi, "var(--font)"],
];

/* CONSOLIDATE: сдвиг оттенка — только отчёт (НЕ применяется автоматически). */
const CONSOLIDATE = {
  "#7f77dd": "var(--p)   // легаси-фиолет #7F77DD → #7C6FF7 (сдвиг оттенка)",
  "#94a3b8": "var(--t3)  // светлый slate → #64748B (темнее)",
  "#fafbfc": "var(--bg2) // сплошной → translucent",
  "#fafafc": "var(--bg2) // сплошной → translucent",
  "#f1f5f9": "var(--bg3) // сплошной → translucent",
  "#f1f2f5": "var(--bg3) // сплошной → translucent",
};

const REVIEW_HEX = /#1e2a4a|#0c1230|#2d3e6b|#5b54b8/gi;
const REVIEW_WEIGHT = /font-weight:\s*[67]00/gi;
const REVIEW_EMOJI = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}️]/gu;

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name.startsWith(".")) continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (EXT.has(extname(name)) && !SKIP_FILES.has(name)) out.push(p);
  }
  return out;
}

let files, totalAuto = 0, touched = 0;
try { files = walk(ROOT); }
catch { console.error(`✗ Не найден путь "${ROOT}". Запускайте из корня репо.`); process.exit(1); }

const review = { navy: 0, weight: 0, emoji: 0, consolidate: new Map() };

function applyReplacements(text) {
  let n = 0;
  for (const [hex, tok] of Object.entries(MAP)) {
    text = text.replace(new RegExp(hex, "gi"), () => { n++; return tok; });
  }
  for (const [re, tok] of STR) text = text.replace(re, () => { n++; return tok; });
  return [text, n];
}

for (const f of files) {
  const before = readFileSync(f, "utf8");
  let src, autoInFile;

  if (f.endsWith(".vue")) {
    // заменяем ТОЛЬКО внутри <style …>…</style>, <script>/template не трогаем
    autoInFile = 0;
    src = before.replace(/(<style[^>]*>)([\s\S]*?)(<\/style>)/gi, (_m, open, body, close) => {
      const [b, n] = applyReplacements(body);
      autoInFile += n;
      return open + b + close;
    });
  } else {
    [src, autoInFile] = applyReplacements(before);  // .css/.scss целиком
  }

  if (before.match(REVIEW_HEX)) review.navy++;
  if (before.match(REVIEW_WEIGHT)) review.weight++;
  if (before.match(REVIEW_EMOJI)) review.emoji++;
  for (const hex of Object.keys(CONSOLIDATE)) {
    const n = (before.match(new RegExp(hex, "gi")) || []).length;
    if (n) review.consolidate.set(hex, (review.consolidate.get(hex) || 0) + n);
  }

  totalAuto += autoInFile;
  if (autoInFile && src !== before) {
    touched++;
    if (WRITE) writeFileSync(f, src, "utf8");
    if (process.env.VERBOSE) console.log(`${WRITE ? "✓" : "·"} ${f} (${autoInFile})`);
  }
}

console.log("\n──────── AUTO (value-точные, ноль сдвига в light) ────────");
console.log(`Файлов просканировано: ${files.length}`);
console.log(`${WRITE ? "Изменено" : "Будет изменено"}: ${touched} файлов, ${totalAuto} замен`);
if (!WRITE) console.log("DRY-RUN. С --write применит ТОЛЬКО эти безопасные замены.");

console.log("\n──────── CONSOLIDATE (сдвиг оттенка — решение за тобой, НЕ применено) ────────");
if (review.consolidate.size) {
  [...review.consolidate.entries()].sort((a, b) => b[1] - a[1])
    .forEach(([h, n]) => console.log(`   ${h} ×${n}  →  ${CONSOLIDATE[h]}`));
} else console.log("   нет");

console.log("\n──────── REVIEW (контекст — ручная правка) ────────");
console.log(`navy (#1E2A4A/#0C1230…) в ${review.navy} файлах — текст→var(--t1)/var(--navy-heading), градиент→var(--navy)`);
console.log(`font-weight 600/700 в ${review.weight} файлах`);
console.log(`emoji в ${review.emoji} файлах → stroke-SVG`);
