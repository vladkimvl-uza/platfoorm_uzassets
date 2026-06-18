/**
 * useNsbuCalculator.ts — Pack 7.51
 * ─────────────────────────────────────────────────────────────────
 * Safe expression evaluator for the NSBU editor's calculator.
 *
 * Supports:
 *   • Numbers (Russian format: 12,5 or 12.5)
 *   • Operators: + - * / %  ( )
 *   • Absolute value: |x|
 *   • Cell references: revenue.2024  myField.2025  field name (.year)
 *   • Financial helpers (resolved at parse time):
 *       GROWTH(curRef, prevRef)  → (cur - prev) / |prev| * 100
 *       CAGR(startRef, endRef, n) → (end/start)^(1/n) - 1, в %
 *       MARGIN(numRef, revRef)   → num / rev * 100  (rev default = revenue.{year})
 *       AVG(refA, refB, ...)     → среднее
 *
 * Anti-injection: только разрешённые символы пропускаются в Function();
 * any non-whitelisted token → returns null.
 */

import { ref } from "vue";

export interface CellRef {
  field: string;   // e.g. 'revenue', 'opProfit', custom 'myDivYield'
  year: number;    // e.g. 2024
}

export type CellMatrix = Record<string, Record<number, number | null>>;
// matrix[field][year] = value

const CELL_REF_RE = /([a-zA-Zа-яА-Я_][a-zA-Z0-9а-яА-Я_]*)\.(\d{4})/g;
const FN_RE = /(GROWTH|CAGR|MARGIN|AVG)\s*\(([^()]*)\)/g;
const ALLOWED_AFTER_NORMALIZE = /^[0-9+\-*/%().,\s]*$/;

export function parseCellRef(s: string): CellRef | null {
  const m = /^([a-zA-Zа-яА-Я_][a-zA-Z0-9а-яА-Я_]*)\.(\d{4})$/.exec(s.trim());
  if (!m) return null;
  return { field: m[1], year: parseInt(m[2], 10) };
}

export function formatCellRef(ref: CellRef): string {
  return `${ref.field}.${ref.year}`;
}

function lookupCell(matrix: CellMatrix, ref: CellRef): number | null {
  const fieldData = matrix[ref.field];
  if (!fieldData) return null;
  const v = fieldData[ref.year];
  if (v == null || !isFinite(v)) return null;
  return v;
}

/** Replace financial helper functions with their numeric expansions. */
function expandHelpers(expr: string, matrix: CellMatrix, contextYear: number): string {
  return expr.replace(FN_RE, (_full, fn, argsRaw) => {
    const args = argsRaw.split(",").map((a: string) => a.trim()).filter(Boolean);
    if (fn === "GROWTH" && args.length === 2) {
      const a = parseCellRef(args[0]), b = parseCellRef(args[1]);
      if (!a || !b) return "NaN";
      const va = lookupCell(matrix, a), vb = lookupCell(matrix, b);
      if (va == null || vb == null || vb === 0) return "NaN";
      return String(((va - vb) / Math.abs(vb)) * 100);
    }
    if (fn === "CAGR" && args.length >= 2) {
      const start = parseCellRef(args[0]), end = parseCellRef(args[1]);
      if (!start || !end) return "NaN";
      const vs = lookupCell(matrix, start), ve = lookupCell(matrix, end);
      if (vs == null || ve == null || vs <= 0) return "NaN";
      const n = args[2] ? Number(args[2]) : end.year - start.year;
      if (!n) return "NaN";
      return String((Math.pow(ve / vs, 1 / n) - 1) * 100);
    }
    if (fn === "MARGIN" && args.length >= 1) {
      const num = parseCellRef(args[0]);
      if (!num) return "NaN";
      const rev = args[1] ? parseCellRef(args[1]) : { field: "revenue", year: contextYear };
      if (!rev) return "NaN";
      const vn = lookupCell(matrix, num), vr = lookupCell(matrix, rev);
      if (vn == null || vr == null || vr === 0) return "NaN";
      return String((vn / vr) * 100);
    }
    if (fn === "AVG" && args.length >= 1) {
      const vals: number[] = [];
      for (const a of args) {
        const ref = parseCellRef(a);
        if (!ref) continue;
        const v = lookupCell(matrix, ref);
        if (v != null) vals.push(v);
      }
      if (!vals.length) return "NaN";
      return String(vals.reduce((s, v) => s + v, 0) / vals.length);
    }
    return "NaN";
  });
}

/**
 * Safely evaluate the expression.
 * Returns the numeric result, or null if invalid/unsafe.
 */
export function safeEvalExpression(
  expr: string,
  matrix: CellMatrix,
  contextYear: number,
): { value: number | null; error: string | null } {
  if (!expr.trim()) return { value: null, error: null };

  // 1. Russian decimal comma -> dot (do this on the raw expression)
  let work = expr.replace(/(\d),(\d)/g, "$1.$2");

  // 2. Expand financial helpers (GROWTH/CAGR/MARGIN/AVG) -> numbers
  work = expandHelpers(work, matrix, contextYear);

  // 3. Replace cell refs (field.year) with their numeric values
  let hasUnresolved = false;
  work = work.replace(CELL_REF_RE, (_match, field, yearStr) => {
    const v = lookupCell(matrix, { field, year: parseInt(yearStr, 10) });
    if (v == null) {
      hasUnresolved = true;
      return "NaN";
    }
    return String(v);
  });
  if (hasUnresolved) return { value: null, error: "Не все ячейки заполнены" };

  // 4. Convert |x| → Math.abs(x). Single level only.
  work = work.replace(/\|([^|]+)\|/g, "Math.abs($1)");

  // 5. Validate only allowed chars remain
  const stripped = work.replace(/Math\.abs/g, "");
  if (!ALLOWED_AFTER_NORMALIZE.test(stripped)) {
    return { value: null, error: "Недопустимые символы в выражении" };
  }

  // 6. Evaluate
  try {
     
    const fn = new Function("Math", `"use strict"; return (${work});`);
    const result = fn(Math);
    if (typeof result !== "number" || !isFinite(result)) {
      return { value: null, error: "Результат не число" };
    }
    return { value: Math.round(result * 1000) / 1000, error: null };
  } catch (e) {
    return { value: null, error: "Ошибка вычисления" };
  }
}

/**
 * Calculator state singleton (per editor session).
 */
export interface CalcHistoryEntry {
  expression: string;
  result: number;
  targetField: string | null;
  targetYear: number | null;
  appliedAt: number;
}

export function useNsbuCalculator() {
  const expression = ref<string>("");
  const targetField = ref<string | null>(null);
  const targetYear = ref<number | null>(null);
  const history = ref<CalcHistoryEntry[]>([]);
  const memory = ref<number | null>(null);

  function setTarget(field: string | null, year: number | null) {
    targetField.value = field;
    targetYear.value = year;
  }

  function appendToExpression(token: string) {
    expression.value = (expression.value + token).trimStart();
  }

  function appendCellRef(field: string, year: number) {
    const ref = `${field}.${year}`;
    // Insert with operator-friendly spacing
    if (expression.value && !/[+\-*/(\s]$/.test(expression.value)) {
      expression.value += " ";
    }
    expression.value += ref;
  }

  function backspace() {
    expression.value = expression.value.slice(0, -1);
  }
  function clearExpression() { expression.value = ""; }

  function recordHistory(value: number) {
    history.value.unshift({
      expression: expression.value,
      result: value,
      targetField: targetField.value,
      targetYear: targetYear.value,
      appliedAt: Date.now(),
    });
    if (history.value.length > 20) history.value.length = 20;
  }

  function recallHistory(idx: number) {
    const h = history.value[idx];
    if (!h) return;
    expression.value = h.expression;
  }

  function memorySet(v: number) { memory.value = v; }
  function memoryRecall(): number | null { return memory.value; }
  function memoryClear() { memory.value = null; }

  return {
    expression,
    targetField,
    targetYear,
    history,
    memory,
    setTarget,
    appendToExpression,
    appendCellRef,
    backspace,
    clearExpression,
    recordHistory,
    recallHistory,
    memorySet,
    memoryRecall,
    memoryClear,
  };
}
