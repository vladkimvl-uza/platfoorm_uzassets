<script setup lang="ts">
/**
 * HeatmapPayments — тепловая карта годов погашения × компаний.
 *
 * Порт фрагмента cpRenderPortfolioOverview hmCellStyle (lines 26595-26610).
 *
 * Колонки: asOfYear, +1, +2, +3, +4, +5, +6, ">+6"
 * Строки: 19 компаний (от companiesOverview, sorted by debt_usd desc)
 * Заливка: rgba (hue зависит от года) с alpha от 0.06 до 0.40 нормализованно по hmMax
 *
 * Hue ranges:
 *   - asOfYear     → red 226,75,74
 *   - +1..+5       → amber 239,159,39
 *   - >+5          → purple 127,119,221
 *
 * Click cell → filter year + select company.
 */
import { computed } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, toNum, type CompanyAggregateRow } from "@/api/credit";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

const credit = useCreditData();

const asOfYear = computed(() => credit.asOfYear.value);

const cols = computed<{ year: number; isGt: boolean; label: string }[]>(() => {
  const y0 = asOfYear.value;
  const arr = [] as { year: number; isGt: boolean; label: string }[];
  for (let i = 0; i < 7; i++) {
    arr.push({ year: y0 + i, isGt: false, label: String(y0 + i) });
  }
  arr.push({ year: y0 + 7, isGt: true, label: `>${y0 + 6}` });
  return arr;
});

const rows = computed(() => {
  return credit.companiesOverview.value
    .slice()
    .sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd));
});

/** Глобальный максимум платежа в одной (компания, год) ячейке для нормализации alpha. */
const hmMax = computed(() => {
  let m = 0;
  for (const co of rows.value) {
    for (const yc of cols.value) {
      const amt = yc.isGt
        ? toNum(co.pay_gt2032)
        : toNum(
            co.pay_by_year.find((p) => p.year === yc.year)?.debt_usd || 0,
          );
      if (amt > m) m = amt;
    }
  }
  return m || 1;
});

function payAmount(co: CompanyAggregateRow, col: { year: number; isGt: boolean }): number {
  if (col.isGt) {
    return toNum(co.pay_gt2032);
  }
  return toNum(co.pay_by_year.find((p) => p.year === col.year)?.debt_usd || 0);
}

function hueFor(col: { year: number; isGt: boolean }): string {
  if (col.year === asOfYear.value) return "226,75,74";   // red
  if (col.isGt || col.year > asOfYear.value + 5) return "127,119,221"; // purple
  return "239,159,39"; // amber
}

function cellStyle(co: CompanyAggregateRow, col: { year: number; isGt: boolean }) {
  const amt = payAmount(co, col);
  if (amt <= 0) {
    return {
      background: "rgba(127,119,221,.04)",
      color: "var(--t3, #888780)",
      fontWeight: "400",
    };
  }
  const rel = Math.min(1, amt / hmMax.value);
  const alpha = 0.06 + rel * 0.34;
  const hue = hueFor(col);
  const textColor = alpha > 0.32 ? "#fff" : "var(--t1, #1e2a4a)";
  return {
    background: `rgba(${hue},${alpha.toFixed(2)})`,
    color: textColor,
    fontWeight: "500",
  };
}

function cellLabel(amt: number): string {
  if (amt <= 0) return "·";
  if (amt >= 1e6) return fmt.fmtMoneyCompact(amt, "USD", { decimals: amt >= 1e9 ? 1 : 0 });
  return fmt.fmtMoneyCompact(amt, "USD", { decimals: 0 });
}

function onCellClick(co: CompanyAggregateRow, col: { year: number; isGt: boolean }) {
  if (payAmount(co, col) <= 0) return;
  // Set company first
  credit.setSelectedCompanyById(co.company_id);
  // Then set year filter & switch to payments tab
  if (!col.isGt) {
    credit.filterByYear(col.year);
  }
}

function shortenCo(name: string): string {
  return name
    .replace(/^АО\s*"?/, "")
    .replace(/^"/, "")
    .replace(/"$/, "")
    .replace(/\s*ДК$/, "")
    .replace(/\s*АЖ$/, " АЖ");
}
</script>

<template>
  <div class="pa-card">
    <div class="pa-card-h">
      <span class="pa-card-t">Карта погашений по годам</span>
      <span class="pa-card-s">
        интенсивность — объём платежа · клик по ячейке — drill в TabPayments
      </span>
    </div>

    <div class="cp-hm-wrap">
      <table class="cp-hm">
        <thead>
          <tr>
            <th class="cp-hm-co">Компания</th>
            <th
              v-for="col in cols"
              :key="col.label"
              class="cp-hm-yr"
              :class="{ 'cp-hm-yr-current': col.year === asOfYear }"
            >
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(co, i) in rows"
            :key="co.company_id"
            :style="{ animationDelay: i * 30 + 'ms' }"
          >
            <td
              class="cp-hm-co-name"
              :title="co.company_name_ru"
              @click="credit.setSelectedCompanyById(co.company_id)"
            >
              <span
                v-if="co.sector_color"
                class="cp-hm-stripe"
                :style="{ background: co.sector_color }"
              />
              <span class="cp-hm-co-text">{{ shortenCo(co.company_name_ru) }}</span>
            </td>
            <td
              v-for="col in cols"
              :key="co.company_id + col.label"
              class="cp-hm-cell"
              :style="cellStyle(co, col)"
              :title="payAmount(co, col) > 0
                ? co.company_name_ru + ' · ' + col.label + ': ' + fmtMoneyShort(payAmount(co, col))
                : ''"
              @click="onCellClick(co, col)"
            >
              {{ cellLabel(payAmount(co, col)) }}
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="cols.length + 1" class="cp-hm-empty">
              Загружаю данные…
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.cp-hm-wrap {
  padding: 6px 14px 16px;
  overflow-x: auto;
}

.cp-hm {
  width: 100%;
  border-collapse: separate;
  border-spacing: 3px;
  font-size: 11.5px;
}

.cp-hm-co {
  text-align: left;
  font-size: 9.5px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 8px 4px 6px;
  width: 220px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.cp-hm-yr {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 8px 6px 6px;
  text-align: center;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  font-feature-settings: "tnum";
}

.cp-hm-yr-current {
  color: #C97070;
  font-weight: 600;
}

.cp-hm tbody tr {
  animation: cpHmRowIn 0.45s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}

@keyframes cpHmRowIn {
  from { opacity: 0; transform: translateX(-6px); }
  to   { opacity: 1; transform: translateX(0); }
}

.cp-hm-co-name {
  padding: 6px 4px;
  cursor: pointer;
  transition: background 0.12s;
  border-radius: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.cp-hm-co-name:hover {
  background: rgba(127, 119, 221, 0.04);
}

.cp-hm-stripe {
  width: 3px;
  height: 18px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.85;
}

.cp-hm-co-text {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}

.cp-hm-cell {
  text-align: center;
  padding: 7px 4px;
  border-radius: 4px;
  font-feature-settings: "tnum";
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: transform 0.16s ease, filter 0.16s ease;
  min-width: 56px;
  letter-spacing: -0.005em;
}

.cp-hm-cell:hover {
  transform: scale(1.04);
  filter: brightness(1.06);
}

.cp-hm-empty {
  text-align: center;
  padding: 30px 0;
  color: var(--t3, #888780);
  font-style: italic;
  font-size: 12px;
}
</style>
