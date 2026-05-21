<script setup lang="ts">
/**
 * FinModelDashboardTab — multi-year analytical aggregation.
 *
 * Three variants per Excel "Control - dashboard" sheet:
 *   pl — P&L: 23 строки (Выручка → Net income + EBITDA/FCFF)
 *   bs — BS: 16 агрегированных по dashboard_category строк
 *   cf — CF: упрощённый — Δ BS items + net income
 *
 * Получает `multiYearComputed` от родителя — {year → {code → value}}.
 * Все цифры compute-only, не редактируются.
 */
import { computed } from "vue";
import type { TemplateRow } from "@/api/finmodel";

const props = withDefaults(defineProps<{
  variant: "pl" | "bs" | "cf";
  template: TemplateRow[];
  /** {year → {row_code → numeric value}} for all loaded years */
  multiYearComputed: Record<number, Record<string, number>>;
  /** sorted years to render as columns */
  years: number[];
  loading: boolean;
  divisor?: number;
}>(), { divisor: 1 });

// ─── Helpers ──────────────────────────────────────────────────────
function val(year: number, code: string): number {
  return props.multiYearComputed[year]?.[code] ?? 0;
}

/** Sum of all inputs in a given dashboard_category for one year. */
function catSum(year: number, category: string, section: "BS" | "PL"): number {
  const yc = props.multiYearComputed[year];
  if (!yc) return 0;
  let total = 0;
  for (const r of props.template) {
    if (r.section !== section) continue;
    if (r.dashboard_category !== category) continue;
    if (r.row_type !== "input") continue;  // sum only leaves
    total += yc[r.code] ?? 0;
  }
  return total;
}

function deltaPrev(year: number, code: string): number {
  const idx = props.years.indexOf(year);
  if (idx <= 0) return 0;
  return val(year, code) - val(props.years[idx - 1], code);
}

// ─── Row definitions ──────────────────────────────────────────────
type RowKind = "header" | "data" | "subtotal" | "grand" | "percent" | "manual";
interface DashRow {
  label: string;
  kind: RowKind;
  values?: (y: number) => number;
  hint?: string;  // small grey suffix
}

const plRows: DashRow[] = [
  { label: "Выручка",                       kind: "data",     values: y => val(y, "PL_010") },
  { label: "Себестоимость",                 kind: "data",     values: y => -val(y, "PL_020") },
  { label: "Валовая прибыль",               kind: "subtotal", values: y => val(y, "PL_030") },
  { label: "Валовая прибыль, %",            kind: "percent",  values: y => {
      const rev = val(y, "PL_010"); return rev === 0 ? 0 : val(y, "PL_030") / rev * 100;
    }},
  { label: "Расходы по реализации",         kind: "data",     values: y => -val(y, "PL_050") },
  { label: "Административные расходы",      kind: "data",     values: y => -val(y, "PL_060") },
  { label: "Прочие доходы",                 kind: "data",     values: y => val(y, "PL_090") },
  { label: "Прочие расходы",                kind: "data",     values: y => -(val(y, "PL_070") + val(y, "PL_080")) },
  { label: "Результаты опер. деятельности", kind: "subtotal", values: y => val(y, "PL_100") },
  { label: "Финансовые доходы",             kind: "data",     values: y => val(y, "PL_110") },
  { label: "Финансовые расходы",            kind: "data",     values: y => -val(y, "PL_170") },
  { label: "Net forex gain / (loss)",       kind: "data",     values: y => val(y, "PL_150") - val(y, "PL_200") },
  { label: "Прибыль до налогообложения",    kind: "subtotal", values: y => val(y, "PL_240") },
  { label: "Налог на прибыль",              kind: "data",     values: y => -(val(y, "PL_250") + val(y, "PL_260")) },
  { label: "Чистая прибыль",                kind: "grand",    values: y => val(y, "PL_270") },
  { label: "(+) Износ и амортизация",       kind: "manual",   hint: "manual override" },
  { label: "(−) CAPEX",                     kind: "manual",   hint: "manual override" },
  { label: "Изменение в ЧОК",               kind: "manual",   hint: "manual override" },
  { label: "EBITDA",                        kind: "subtotal", values: y => val(y, "PL_100"), hint: "= EBIT + D&A (placeholder)" },
  { label: "FCFF",                          kind: "subtotal", values: y => val(y, "PL_270"), hint: "placeholder" },
];

const bsRows: DashRow[] = [
  { label: "Внеоборотные активы",                              kind: "header" },
  { label: "Основные средства",                                kind: "data",     values: y => catSum(y, "Основные средства", "BS") },
  { label: "Нематериальные активы",                            kind: "data",     values: y => catSum(y, "Нематериальные активы", "BS") },
  { label: "Долгосрочные инвестиции",                          kind: "data",     values: y => catSum(y, "Долгосрочные инвестиции", "BS") },
  { label: "Долгосрочная торг. и проч. деб. зад-ть",          kind: "data",     values: y => catSum(y, "Долгосрочная торговая и прочая дебиторская задолженность", "BS") },
  { label: "Прочие внеоборотные активы",                       kind: "data",     values: y => catSum(y, "Другие внеоборотные активы", "BS") },
  { label: "Total non-current assets",                         kind: "subtotal", values: y => val(y, "130") },
  { label: "Оборотные активы",                                 kind: "header" },
  { label: "Запасы",                                           kind: "data",     values: y => catSum(y, "Запасы", "BS") },
  { label: "Краткосрочная торг. и проч. деб. зад-ть",         kind: "data",     values: y => catSum(y, "Краткосрочная торговая и прочая дебиторская задолженность", "BS") },
  { label: "Денежные средства и их эквиваленты",               kind: "data",     values: y => catSum(y, "Денежные средства и их эквиваленты", "BS") },
  { label: "Краткосрочные инвестиции",                         kind: "data",     values: y => catSum(y, "Краткосрочные инвестиции", "BS") },
  { label: "Прочие оборотные активы",                          kind: "data",     values: y => catSum(y, "Other current assets", "BS") },
  { label: "Total current assets",                             kind: "subtotal", values: y => val(y, "390") },
  { label: "БАЛАНС АКТИВА",                                    kind: "grand",    values: y => val(y, "400") },
  { label: "Капитал",                                          kind: "header" },
  { label: "Уставной капитал",                                 kind: "data",     values: y => catSum(y, "Уставной капитал", "BS") },
  { label: "Нераспределенная прибыль",                         kind: "data",     values: y => catSum(y, "Нераспределенная прибыль", "BS") },
  { label: "Другой капитал",                                   kind: "data",     values: y => catSum(y, "Other capital", "BS") },
  { label: "Total equity",                                     kind: "subtotal", values: y => val(y, "480") },
  { label: "Долгосрочные обязательства",                       kind: "header" },
  { label: "Долгосрочная торг. кред. зад-ть",                 kind: "data",     values: y => catSum(y, "Долгосрочная торговая кредиторская задолженность", "BS") },
  { label: "Долгосрочные кредиты и займы",                     kind: "data",     values: y => catSum(y, "Долгосрочные кредиты и займы", "BS") },
  { label: "Прочие долгосрочные обязательства",                kind: "data",     values: y => catSum(y, "Прочие долгосрочные обязательства", "BS") },
  { label: "Total non-current liabilities",                    kind: "subtotal", values: y => val(y, "490") },
  { label: "Краткосрочные обязательства",                      kind: "header" },
  { label: "Краткосрочная торг. кред. зад-ть",                kind: "data",     values: y => catSum(y, "Краткосрочная торговая кредиторская задолженность", "BS") },
  { label: "Краткосрочные кредиты и займы",                    kind: "data",     values: y => catSum(y, "Краткосрочные кредиты и займы", "BS") },
  { label: "Прочие краткосрочные обязательства",               kind: "data",     values: y => catSum(y, "Прочие краткосрочные обязательства", "BS") },
  { label: "Total current liabilities",                        kind: "subtotal", values: y => val(y, "600") },
  { label: "Total liabilities",                                kind: "subtotal", values: y => val(y, "770") },
  { label: "БАЛАНС ПАССИВА",                                   kind: "grand",    values: y => val(y, "780") },
];

const cfRows: DashRow[] = [
  { label: "Чистая прибыль",                       kind: "data",     values: y => val(y, "PL_270") },
  { label: "(+) Износ и амортизация",              kind: "manual",   hint: "manual override" },
  { label: "(−) Δ ТМЗ",                            kind: "data",     values: y => -deltaPrev(y, "140") },
  { label: "(−) Δ Дебиторская задолженность",      kind: "data",     values: y => -deltaPrev(y, "210") },
  { label: "(+) Δ Краткоср. обязательства",        kind: "data",     values: y => deltaPrev(y, "600") },
  { label: "Операционный CF",                      kind: "subtotal", values: y =>
      val(y, "PL_270") - deltaPrev(y, "140") - deltaPrev(y, "210") + deltaPrev(y, "600") },
  { label: "(−) CAPEX",                            kind: "manual",   hint: "manual override" },
  { label: "Инвестиционный CF",                    kind: "manual",   hint: "placeholder" },
  { label: "(+) Δ Долгоср. кредиты",               kind: "data",     values: y => deltaPrev(y, "570") + deltaPrev(y, "580") },
  { label: "(+) Δ Краткоср. кредиты",              kind: "data",     values: y => deltaPrev(y, "730") + deltaPrev(y, "740") },
  { label: "Финансовый CF",                        kind: "subtotal", values: y =>
      deltaPrev(y, "570") + deltaPrev(y, "580") + deltaPrev(y, "730") + deltaPrev(y, "740") },
  { label: "Δ Денежные средства",                  kind: "grand",    values: y => deltaPrev(y, "320") },
];

const rows = computed<DashRow[]>(() =>
  props.variant === "pl" ? plRows : props.variant === "bs" ? bsRows : cfRows
);

const title = computed(() =>
  props.variant === "pl" ? "Profit & Loss statement"
  : props.variant === "bs" ? "Balance sheet"
  : "Cash flow statement (simplified)"
);

function formatVal(r: DashRow, y: number): string {
  if (r.kind === "header" || r.kind === "manual") return "";
  const v = r.values ? r.values(y) : 0;
  if (r.kind === "percent") return `${v.toFixed(1)}%`;
  if (!Number.isFinite(v) || v === 0) return "—";
  const scaled = v / props.divisor;
  const decimals = props.divisor === 1 ? 0 : 1;
  return scaled.toLocaleString("ru-RU", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}
</script>

<template>
  <section class="fm-dash">
    <header class="fm-dash-head">
      <span class="fm-dash-cap">{{ variant.toUpperCase() }}</span>
      <h2 class="fm-dash-title">{{ title }}</h2>
      <span v-if="loading" class="fm-dash-loading">Загружаем годы…</span>
      <span v-else class="fm-dash-years">{{ years.length }} {{ years.length === 1 ? 'год' : years.length < 5 ? 'года' : 'лет' }}</span>
    </header>

    <div v-if="years.length === 0 && !loading" class="fm-dash-empty">
      Нет годов для агрегации. Выберите компанию и создайте хотя бы один год в табе «Баланс».
    </div>

    <div v-else class="fm-dash-tbl-wrap">
      <table class="fm-dash-tbl">
        <thead>
          <tr>
            <th class="fm-dh-lbl">Показатель</th>
            <th v-for="y in years" :key="y" class="fm-dh-yr">{{ y }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, idx) in rows" :key="idx" :class="`fm-dr-${r.kind}`">
            <td class="fm-d-lbl">
              {{ r.label }}
              <span v-if="r.hint" class="fm-d-hint">· {{ r.hint }}</span>
            </td>
            <td v-for="y in years" :key="y" class="fm-d-val">{{ formatVal(r, y) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.fm-dash { padding: 16px 18px; }
.fm-dash-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.fm-dash-cap {
  font-size: 10px;
  font-weight: 500;
  color: #888780;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.fm-dash-title {
  font-size: 14px;
  font-weight: 500;
  color: #1E2A4A;
  letter-spacing: -.01em;
  margin: 0;
}
.fm-dash-loading { font-size: 10.5px; color: #EF9F27; margin-left: auto; }
.fm-dash-years { font-size: 10.5px; color: #888780; margin-left: auto; }

.fm-dash-empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 11px;
  color: #888780;
  font-style: italic;
}

.fm-dash-tbl-wrap {
  border: 0.5px solid #E5E7EB;
  border-radius: 9px;
  overflow: auto;
}
.fm-dash-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.fm-dash-tbl thead th {
  background: #FAFAFC;
  padding: 8px 12px;
  text-align: right;
  font-size: 9.5px;
  font-weight: 500;
  color: #888780;
  letter-spacing: .06em;
  text-transform: uppercase;
  border-bottom: 0.5px solid #E5E7EB;
  white-space: nowrap;
}
.fm-dh-lbl { text-align: left; padding-left: 14px; }
.fm-dh-yr { font-variant-numeric: tabular-nums; }
.fm-dash-tbl tbody tr { border-top: 0.5px solid #F1EFE8; }
.fm-d-lbl { padding: 5px 12px; color: #1E2A4A; }
.fm-d-val {
  padding: 5px 12px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.fm-d-hint {
  font-size: 9.5px;
  color: #C8C7C0;
  margin-left: 4px;
  font-style: italic;
}

.fm-dr-header td { background: #F5F4FA; font-weight: 500; text-transform: uppercase; font-size: 9.5px; letter-spacing: .06em; color: #534AB7; }
.fm-dr-header .fm-d-val { color: #C8C7C0; }
.fm-dr-subtotal td { background: rgba(127, 119, 221, .06); font-weight: 500; }
.fm-dr-grand td { background: #DDD8F0; font-weight: 500; }
.fm-dr-percent td { background: rgba(55, 138, 221, .04); color: #1F5A99; }
.fm-dr-manual td { opacity: .55; }
.fm-dr-manual .fm-d-val { color: #C8C7C0; }
</style>
