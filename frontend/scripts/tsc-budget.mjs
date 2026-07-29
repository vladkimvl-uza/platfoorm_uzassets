#!/usr/bin/env node
/**
 * Гейт-бюджет ошибок типов.
 *
 * Запускает АВТОРИТЕТНЫЙ `vue-tsc -b` (build/solution-режим — в отличие от
 * слабого `vue-tsc --noEmit`, который на этом проекте почти ничего не ловит).
 * Падает ТОЛЬКО если число ошибок выросло сверх зафиксированного бюджета —
 * то есть останавливает накопление, не требуя разовой зачистки всех ошибок.
 *
 * Правило: BUDGET можно только СНИЖАТЬ (по мере исправления). Повышение —
 * осознанное решение, а не тихий коммит. Цель — довести до 0 и сделать гейт
 * блокирующим на нуле.
 *
 * Корень проблемы (аудит здоровья кода, июль 2026): прод собирается через
 * `vite build`, который типы не проверяет, поэтому ошибки копились бесконтрольно.
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

// Обновлено 2026-07-29 после исправления журнала аудита (было 56 → стало 55).
const BUDGET = 55;

// --force не даёт incremental-кэшу скрыть ошибки из предыдущего запуска.
// Локальный bin запускаем через Node, чтобы не зависеть от shell/npx на Windows.
const vueTscBin = fileURLToPath(new URL("../node_modules/vue-tsc/bin/vue-tsc.js", import.meta.url));
const res = spawnSync(process.execPath, [vueTscBin, "-b", "--force"], {
  encoding: "utf8",
  shell: false,
  maxBuffer: 1024 * 1024 * 64,
});

if (res.error) {
  console.error(`Не удалось запустить vue-tsc: ${res.error.message}`);
  process.exit(1);
}

const out = (res.stdout || "") + (res.stderr || "");
const count = (out.match(/error TS\d+/g) || []).length;

process.stdout.write(out);
console.log("\n----------------------------------------");
console.log(`vue-tsc -b: ${count} ошибок типов; бюджет = ${BUDGET}`);

if (count > BUDGET) {
  console.error(
    `\n[FAIL] Ошибок типов стало больше: ${BUDGET} -> ${count}. ` +
      `Почини новые ошибки. Если рост неизбежен — обсуди прежде чем поднимать бюджет.`,
  );
  process.exit(1);
}

if (count < BUDGET) {
  console.log(
    `\n[OK, стало лучше] Исправлено ошибок: ${BUDGET - count}. ` +
      `Снизь BUDGET в frontend/scripts/tsc-budget.mjs до ${count}, чтобы закрепить.`,
  );
} else {
  console.log("\n[OK] Новых ошибок типов нет.");
}
process.exit(0);
