<script setup lang="ts">
/**
 * FinModelBalanceTable — рендер NSBU §1 шаблона (87 BS строк), редактируемые input-ячейки.
 *
 * Props:
 *   template   — массив TemplateRow (только BS секция, отсортированная по order_idx)
 *   values     — Record<row_code, string|null> — текущие значения для активного года
 *   computed   — Record<row_code, string>      — клиентский расчёт subtotal/grand/check
 *   editable   — boolean — можно ли вводить значения (false если нет companyId/year)
 *
 * Emits:
 *   cell-edit { code, value } — после blur пользователь поменял ячейку
 */
import { computed } from "vue";
import type { TemplateRow } from "@/api/finmodel";

const props = withDefaults(defineProps<{
  template: TemplateRow[];
  values: Record<string, string | null>;
  computedValues: Record<string, string>;
  editable: boolean;
  section?: "BS" | "PL";
  /** Display divisor: 1 = thousand (raw), 1000 = million, 1_000_000 = billion */
  divisor?: number;
}>(), { section: "BS", divisor: 1 });

const emit = defineEmits<{
  "cell-edit": [payload: { code: string; value: string | null }];
}>();

const rows = computed(() =>
  props.template
    .filter(r => r.section === props.section)
    .sort((a, b) => a.order_idx - b.order_idx)
);

// Section header injection — split by code range
interface DisplayItem {
  kind: "section" | "row";
  text?: string;
  row?: TemplateRow;
}

function bsSection(code: string): string {
  const n = Number(code);
  if (code === "CHECK") return "Контроль баланса";
  if (n >= 10 && n <= 130) return "АКТИВ · I. Узоқ муддатли активлар";
  if (n >= 140 && n <= 390) return "АКТИВ · II. Жорий активлар";
  if (n === 400) return "БАЛАНС АКТИВА";
  if (n >= 410 && n <= 480) return "ПАССИВ · I. Ўз маблағлари манбалари";
  if (n >= 490 && n <= 590 || n === 491) return "ПАССИВ · II. Узоқ муддатли мажбуриятлар";
  if (n >= 600 && n <= 770 || n === 601 || n === 602) return "ПАССИВ · III. Жорий мажбуриятлар";
  if (n === 770) return "ИТОГО Обязательства";
  if (n === 780) return "БАЛАНС ПАССИВА";
  return "";
}

function plSection(code: string): string {
  // code here is PL_XXX
  const n = Number(code.replace("PL_", ""));
  if (n >= 10 && n <= 40) return "ОПЕРАЦИОННАЯ ДЕЯТЕЛЬНОСТЬ";
  if (n >= 50 && n <= 90) return "ОПЕРАЦИОННЫЕ РАСХОДЫ И ПРОЧИЕ ДОХОДЫ";
  if (n === 100) return "РЕЗУЛЬТАТЫ ОПЕРАЦИОННОЙ ДЕЯТЕЛЬНОСТИ";
  if (n >= 110 && n <= 160) return "ФИНАНСОВЫЕ ДОХОДЫ";
  if (n >= 170 && n <= 210) return "ФИНАНСОВЫЕ РАСХОДЫ";
  if (n >= 220 && n <= 230) return "ПРОМЕЖУТОЧНЫЕ РЕЗУЛЬТАТЫ";
  if (n === 240) return "ПРИБЫЛЬ ДО НАЛОГА";
  if (n >= 250 && n <= 260) return "НАЛОГИ";
  if (n === 270) return "ЧИСТАЯ ПРИБЫЛЬ";
  return "";
}

const display = computed<DisplayItem[]>(() => {
  const out: DisplayItem[] = [];
  let lastSec = "";
  for (const r of rows.value) {
    const sec = props.section === "PL" ? plSection(r.code) : bsSection(r.code);
    if (sec && sec !== lastSec) {
      out.push({ kind: "section", text: sec });
      lastSec = sec;
    }
    out.push({ kind: "row", row: r });
  }
  return out;
});

function formatNum(s: string | null | undefined): string {
  if (s == null || s === "") return "";
  const n = Number(s);
  if (!Number.isFinite(n)) return s;
  const display = n / props.divisor;
  const decimals = props.divisor === 1 ? 0 : 1;
  return display.toLocaleString("ru-RU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function parseInput(raw: string): string | null {
  const cleaned = raw.replace(/[\s  ]/g, "").replace(",", ".").trim();
  if (cleaned === "") return null;
  const n = Number(cleaned);
  if (!Number.isFinite(n)) return null;
  return String(n * props.divisor);
}

function onBlur(row: TemplateRow, e: Event) {
  const target = e.target as HTMLInputElement;
  const newVal = parseInput(target.value);
  const oldVal = props.values[row.code];
  // No-op if unchanged
  if (newVal === oldVal || (newVal == null && (oldVal == null || oldVal === ""))) {
    target.value = formatNum(newVal);
    return;
  }
  emit("cell-edit", { code: row.code, value: newVal });
  target.value = formatNum(newVal);
}

function onFocus(row: TemplateRow, e: Event) {
  // Strip thousand separators while editing
  const target = e.target as HTMLInputElement;
  const raw = props.values[row.code];
  target.value = raw == null || raw === "" ? "" : String(Number(raw));
}

function displayValue(code: string, isInput: boolean): string {
  if (isInput) return formatNum(props.values[code]);
  return formatNum(props.computedValues[code]);
}

function rowClass(r: TemplateRow): string {
  if (r.code === "400" || r.code === "780" || r.code === "PL_270") return "fm-row-balance";
  if (r.row_type === "grand") return "fm-row-grand";
  if (r.row_type === "subtotal") return "fm-row-subtotal";
  if (r.row_type === "check") return "fm-row-check";
  return "";
}

function formulaHint(r: TemplateRow): string {
  if (!r.formula) return "";
  // Pretty-print: 010-011 → "= 010 − 011" ; 040+050+...→ "∑ 040..080" if range
  if (r.formula.length > 20) return `∑ ${r.formula.slice(0, 3)}..${r.formula.slice(-3)}`;
  return `= ${r.formula.replace(/-/g, " − ").replace(/\+/g, " + ")}`;
}
</script>

<template>
  <table class="fm-tbl">
    <thead>
      <tr>
        <th class="fm-th-lbl" style="width: 60px;">Код</th>
        <th class="fm-th-lbl">Показатель</th>
        <th class="fm-th-num">Значение</th>
      </tr>
    </thead>
    <tbody>
      <template v-for="(item, idx) in display" :key="idx">
        <tr v-if="item.kind === 'section'" class="fm-row-section">
          <td colspan="3">{{ item.text }}</td>
        </tr>
        <tr v-else-if="item.row" :class="rowClass(item.row)">
          <td class="fm-fcode">{{ item.row.code === 'CHECK' ? 'CHECK' : item.row.code }}</td>
          <td class="fm-flabel">
            <template v-if="item.row.row_type !== 'input'"><span class="fm-arrow">→ </span></template>
            <strong v-if="item.row.code === '400' || item.row.code === '780' || item.row.code === 'PL_270'" style="font-weight: 500;">
              {{ item.row.name_ru }}
            </strong>
            <template v-else>{{ item.row.name_ru }}</template>
            <span v-if="item.row.formula" class="fm-muted"> {{ formulaHint(item.row) }}</span>
          </td>
          <td class="fm-fcell">
            <input
              v-if="item.row.row_type === 'input'"
              type="text"
              class="fm-cell-input"
              inputmode="decimal"
              :value="formatNum(values[item.row.code])"
              :disabled="!editable"
              :placeholder="editable ? '0' : ''"
              @focus="onFocus(item.row, $event)"
              @blur="onBlur(item.row, $event)"
              @keydown.enter.prevent="($event.target as HTMLInputElement).blur()"
            />
            <span v-else-if="item.row.code === '400' || item.row.code === '780' || item.row.code === 'PL_270'" class="fm-cell-balance">
              {{ displayValue(item.row.code, false) || '—' }}
            </span>
            <span v-else-if="item.row.row_type === 'check'" class="fm-cell-check-ok">
              {{ displayValue(item.row.code, false) || '0' }}
            </span>
            <span v-else class="fm-cell-calc">
              {{ displayValue(item.row.code, false) || '—' }}
            </span>
          </td>
        </tr>
      </template>
      <tr v-if="display.length === 0" class="fm-row-empty">
        <td colspan="3">Шаблон загружается…</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.fm-tbl {
  width: 100%;
  border-collapse: collapse;
}
.fm-tbl thead th {
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, #888780);
  letter-spacing: .06em;
  text-transform: uppercase;
  padding: 9px 9px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid #E5E7EB;
  text-align: left;
}
.fm-th-lbl { padding-left: 14px; }
.fm-th-num { text-align: right; padding-right: 14px; width: 180px; }
.fm-tbl tbody tr { border-top: 0.5px solid #F1EFE8; }

.fm-fcode {
  padding: 4px 6px;
  font-size: 9.5px;
  color: var(--t3, #888780);
  font-family: ui-monospace, 'SF Mono', Menlo, Consolas, monospace;
  border-right: 0.5px solid #F1EFE8;
  text-align: center;
}
.fm-flabel {
  padding: 4px 12px;
  font-size: 11px;
  color: var(--t1, #1E2A4A);
  border-right: 0.5px solid #F1EFE8;
}
.fm-arrow { color: #C8C7C0; }
.fm-muted { color: var(--t3, #888780); font-size: 10.5px; margin-left: 4px; }
.fm-fcell {
  padding: 4px 9px;
  text-align: right;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.fm-cell-input {
  width: 140px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(55, 138, 221, .05);
  border: 0.5px solid rgba(55, 138, 221, .25);
  text-align: right;
  font-family: inherit;
  font-size: 11px;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  outline: none;
  transition: background .12s, border-color .12s, box-shadow .12s;
}
.fm-cell-input:hover:not(:disabled) {
  background: rgba(55, 138, 221, .10);
  border-color: rgba(55, 138, 221, .50);
}
.fm-cell-input:focus {
  background: var(--bg1, #fff);
  border-color: #378ADD;
  box-shadow: 0 0 0 3px rgba(55, 138, 221, .15);
}
.fm-cell-input:disabled {
  background: rgba(30, 42, 74, .03);
  color: rgba(30, 42, 74, .35);
  cursor: not-allowed;
  border-color: rgba(30, 42, 74, .06);
}

.fm-cell-calc {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(127, 119, 221, .06);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.fm-cell-balance {
  display: inline-block;
  padding: 3px 9px;
  border-radius: 5px;
  background: var(--bg1, #fff);
  font-weight: 500;
  font-size: 12px;
}
.fm-cell-check-ok {
  display: inline-block;
  padding: 2px 7px;
  border-radius: 4px;
  background: rgba(29, 158, 117, .08);
  color: #0F6E56;
  font-weight: 500;
}

.fm-row-section td {
  background: var(--bg2, #FAFAFC);
  padding: 8px 14px;
  font-weight: 500;
  text-transform: uppercase;
  font-size: 9.5px;
  letter-spacing: .06em;
  color: #534AB7;
}
.fm-row-subtotal td { background: #F5F4FA; font-weight: 500; }
.fm-row-grand td { background: #DDD8F0; font-weight: 500; }
.fm-row-balance td { background: #C8C1E8; font-weight: 500; }
.fm-row-balance .fm-fcode, .fm-row-balance .fm-flabel { color: var(--t1, #1E2A4A); }
.fm-row-check td { background: rgba(29, 158, 117, .06); }

.fm-row-empty td {
  padding: 36px 18px;
  text-align: center;
  font-size: 11px;
  color: var(--t3, #888780);
  font-style: italic;
}
</style>
