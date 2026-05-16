<script setup lang="ts">
/**
 * LeagueTable — таблица «Лига компаний» в режиме «Все компании».
 *
 *   - 6 колонок: rank | (sector stripe + name + count) | bar+debt | rate | donut+pct | pay year
 *   - Сортировка по любой из 5 числовых колонок
 *   - Цветовая семантика:
 *       % выплачено: red <35, amber 35-70, green ≥70
 *       Ставка %:    green <7, amber 7-10, red ≥10
 *   - Click по строке → выбрать компанию + перейти на TabOverview single-co
 */
import { computed, ref } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import { fmtMoneyShort, toNum, type CompanyAggregateRow } from "@/api/credit";

const credit = useCreditData();

type SortField = "company" | "debt_usd" | "rate" | "repaid_pct" | "pay_this_year" | "loans_count";
const sortField = ref<SortField>("debt_usd");
const sortDir = ref<"asc" | "desc">("desc");

const rows = computed(() => {
  const list = credit.companiesOverview.value.slice();
  const dir = sortDir.value === "asc" ? 1 : -1;
  list.sort((a, b) => {
    let va: number | string;
    let vb: number | string;
    switch (sortField.value) {
      case "company":
        va = a.company_name_ru;
        vb = b.company_name_ru;
        return (va as string).localeCompare(vb as string) * dir;
      case "debt_usd":
        va = toNum(a.debt_usd);
        vb = toNum(b.debt_usd);
        return ((va as number) - (vb as number)) * dir;
      case "rate":
        va = toNum(a.avg_rate);
        vb = toNum(b.avg_rate);
        return ((va as number) - (vb as number)) * dir;
      case "repaid_pct":
        va = a.repaid_pct;
        vb = b.repaid_pct;
        return ((va as number) - (vb as number)) * dir;
      case "pay_this_year":
        va = toNum(a.payment_this_year);
        vb = toNum(b.payment_this_year);
        return ((va as number) - (vb as number)) * dir;
      case "loans_count":
        return (a.loans_count - b.loans_count) * dir;
    }
  });
  return list;
});

/** Максимальный долг — для нормализации bar (фиксирован независимо от сортировки). */
const maxDebt = computed(() => {
  let m = 0;
  for (const c of credit.companiesOverview.value) {
    const v = toNum(c.debt_usd);
    if (v > m) m = v;
  }
  return m || 1;
});

const asOfYear = computed(() => credit.asOfYear.value);

function setSort(field: SortField) {
  if (sortField.value === field) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortField.value = field;
    sortDir.value = "desc";
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

function pluralLoans(n: number): string {
  if (n === 1) return "кредит";
  if (n >= 2 && n <= 4) return "кредита";
  return "кредитов";
}

function semTextColor(pct: number): string {
  return pct >= 70 ? "#1D9E75" : pct >= 35 ? "#BA7517" : "#E24B4A";
}
function rateColor(ratePct: number): string {
  return ratePct >= 10 ? "#E24B4A" : ratePct >= 7 ? "#BA7517" : "#1D9E75";
}
function semBarColor(pct: number): string {
  return pct >= 70 ? "#9FE1CB" : pct >= 35 ? "#FAC775" : "#F7C1C1";
}

function donutDash(pct: number): { dash: number; circ: number } {
  const r = 9;
  const circ = 2 * Math.PI * r;
  const dash = Math.max(0, Math.min(pct, 100)) / 100 * circ;
  return { dash, circ };
}

function onRowClick(co: CompanyAggregateRow) {
  credit.setSelectedCompanyById(co.company_id);
}

/** Cap arrow icon — sort indicator. */
function arrowFor(field: SortField): "asc" | "desc" | null {
  return sortField.value === field ? sortDir.value : null;
}
</script>

<template>
  <div class="pa-card">
    <div class="pa-card-h">
      <span class="pa-card-t">Лига компаний</span>
      <span class="pa-card-s">
        сортировка по
        <span v-if="sortField === 'debt_usd'">чистому долгу</span>
        <span v-else-if="sortField === 'company'">названию</span>
        <span v-else-if="sortField === 'rate'">ставке</span>
        <span v-else-if="sortField === 'repaid_pct'">% выплачено</span>
        <span v-else-if="sortField === 'pay_this_year'">платежу {{ asOfYear }}</span>
        <span v-else>кол-ву кредитов</span>
        {{ sortDir === 'desc' ? '↓' : '↑' }}
        <span class="cp-pf-sep"> · </span>
        клик по строке — открыть ДЗО
      </span>
    </div>

    <div class="cp-pf-lt">
      <!-- Header -->
      <div class="cp-pf-lt-h">
        <div></div>
        <div
          class="cp-pf-lt-hcell"
          :class="{ active: sortField === 'company' }"
          @click="setSort('company')"
          title="Клик — сортировать по названию"
        >
          Компания
          <svg v-if="arrowFor('company') === 'desc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
          <svg v-else-if="arrowFor('company') === 'asc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 15 12 9 18 15"/></svg>
        </div>
        <div
          class="cp-pf-lt-hcell"
          :class="{ active: sortField === 'debt_usd' }"
          @click="setSort('debt_usd')"
          title="Клик — сортировать по чистому долгу"
        >
          Чистый долг
          <svg v-if="arrowFor('debt_usd') === 'desc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
          <svg v-else-if="arrowFor('debt_usd') === 'asc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 15 12 9 18 15"/></svg>
        </div>
        <div
          class="cp-pf-lt-hcell right"
          :class="{ active: sortField === 'rate' }"
          @click="setSort('rate')"
          title="Клик — сортировать по ставке"
        >
          Ставка
          <svg v-if="arrowFor('rate') === 'desc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
          <svg v-else-if="arrowFor('rate') === 'asc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 15 12 9 18 15"/></svg>
        </div>
        <div
          class="cp-pf-lt-hcell"
          :class="{ active: sortField === 'repaid_pct' }"
          @click="setSort('repaid_pct')"
          title="Клик — сортировать по % выплачено"
        >
          % выплачено
          <svg v-if="arrowFor('repaid_pct') === 'desc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
          <svg v-else-if="arrowFor('repaid_pct') === 'asc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 15 12 9 18 15"/></svg>
        </div>
        <div
          class="cp-pf-lt-hcell right"
          :class="{ active: sortField === 'pay_this_year' }"
          @click="setSort('pay_this_year')"
          title="Клик — сортировать по платежу"
        >
          Платёж {{ asOfYear }}
          <svg v-if="arrowFor('pay_this_year') === 'desc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 9 12 15 18 9"/></svg>
          <svg v-else-if="arrowFor('pay_this_year') === 'asc'" class="cp-pf-lt-arr" viewBox="0 0 24 24"><polyline points="6 15 12 9 18 15"/></svg>
        </div>
      </div>

      <!-- Rows -->
      <div
        v-for="(c, i) in rows"
        :key="c.company_id"
        class="cp-pf-lt-r"
        :style="{ animationDelay: i * 45 + 'ms' }"
        :title="'Открыть дашборд: ' + c.company_name_ru"
        @click="onRowClick(c)"
      >
        <div class="cp-pf-lt-rank">{{ i + 1 }}</div>
        <div class="cp-pf-lt-co">
          <span
            v-if="c.sector_color"
            class="cp-pf-lt-stripe"
            :style="{ background: c.sector_color }"
          />
          <div class="cp-pf-lt-co-text">
            {{ shortenCo(c.company_name_ru) }}
            <small>{{ c.loans_count }} {{ pluralLoans(c.loans_count) }}</small>
          </div>
        </div>
        <div>
          <div class="cp-pf-lt-bar">
            <div
              :style="{
                width: Math.max(2, (toNum(c.debt_usd) / maxDebt) * 100) + '%',
                background: semBarColor(c.repaid_pct * 100),
              }"
            />
          </div>
          <div class="cp-pf-lt-bar-lbl">{{ fmtMoneyShort(c.debt_usd) }}</div>
        </div>
        <div
          class="cp-pf-lt-rate"
          :style="{ color: rateColor(toNum(c.avg_rate) * 100) }"
        >
          {{ toNum(c.avg_rate) > 0 ? (toNum(c.avg_rate) * 100).toFixed(2) + '%' : '—' }}
        </div>
        <div class="cp-pf-lt-pct">
          <svg width="22" height="22" viewBox="0 0 22 22">
            <circle cx="11" cy="11" r="9" fill="none" stroke="rgba(30,42,74,.08)" stroke-width="3"/>
            <circle
              cx="11" cy="11" r="9" fill="none"
              :stroke="semTextColor(c.repaid_pct * 100)"
              stroke-width="3"
              :stroke-dasharray="`${donutDash(c.repaid_pct * 100).dash.toFixed(2)} ${donutDash(c.repaid_pct * 100).circ.toFixed(2)}`"
              transform="rotate(-90 11 11)"
              stroke-linecap="round"
            />
          </svg>
          <span
            class="cp-pf-lt-pctn"
            :style="{ color: semTextColor(c.repaid_pct * 100) }"
          >{{ (c.repaid_pct * 100).toFixed(1) }}%</span>
        </div>
        <div class="cp-pf-lt-pay">
          {{ toNum(c.payment_this_year) > 0 ? fmtMoneyShort(c.payment_this_year) : '—' }}
        </div>
      </div>

      <div v-if="!rows.length" class="cp-pf-lt-empty">
        Загружаю данные…
      </div>
    </div>
  </div>
</template>

<style scoped>
.cp-pf-sep { color: var(--t3, #888780); }

.cp-pf-lt {
  padding: 4px 14px 12px;
}

.cp-pf-lt-h,
.cp-pf-lt-r {
  display: grid;
  grid-template-columns: 28px 1.6fr 1.5fr 0.7fr 1.1fr 1fr;
  align-items: center;
  gap: 12px;
}

.cp-pf-lt-h {
  padding: 10px 4px 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.cp-pf-lt-hcell {
  font-size: 9.5px;
  color: var(--t3, #888780);
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  cursor: pointer;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 3px;
  transition: color 0.12s;
}

.cp-pf-lt-hcell:hover {
  color: var(--t2, #555c6e);
}

.cp-pf-lt-hcell.active {
  color: #7F77DD;
}

.cp-pf-lt-hcell.right {
  justify-content: flex-end;
}

.cp-pf-lt-arr {
  width: 9px;
  height: 9px;
  fill: none;
  stroke: currentColor;
  stroke-width: 3;
  margin-left: 3px;
}

.cp-pf-lt-r {
  padding: 9px 4px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
  cursor: pointer;
  transition: background 0.12s;
  animation: cpLtIn 0.4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
}

.cp-pf-lt-r:hover {
  background: rgba(127, 119, 221, 0.04);
}

@keyframes cpLtIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cp-pf-lt-rank {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, #888780);
  text-align: center;
  font-feature-settings: "tnum";
}

.cp-pf-lt-co {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.cp-pf-lt-stripe {
  width: 3px;
  height: 28px;
  border-radius: 2px;
  flex-shrink: 0;
  opacity: 0.85;
}

.cp-pf-lt-co-text {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  letter-spacing: -0.005em;
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.cp-pf-lt-co-text small {
  font-size: 10px;
  font-weight: 400;
  color: var(--t3, #888780);
  font-feature-settings: "tnum";
}

.cp-pf-lt-bar {
  height: 5px;
  border-radius: 3px;
  background: rgba(127, 119, 221, 0.08);
  overflow: hidden;
}

.cp-pf-lt-bar > div {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}

.cp-pf-lt-bar-lbl {
  margin-top: 3px;
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
}

.cp-pf-lt-rate {
  font-size: 12px;
  font-weight: 600;
  font-feature-settings: "tnum";
  text-align: right;
}

.cp-pf-lt-pct {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cp-pf-lt-pctn {
  font-size: 11.5px;
  font-weight: 600;
  font-feature-settings: "tnum";
}

.cp-pf-lt-pay {
  font-size: 12px;
  font-weight: 600;
  color: var(--t1, #1e2a4a);
  font-feature-settings: "tnum";
  text-align: right;
}

.cp-pf-lt-empty {
  padding: 30px 0;
  text-align: center;
  color: var(--t3, #888780);
  font-size: 12px;
  font-style: italic;
}

@media (max-width: 1100px) {
  .cp-pf-lt-h,
  .cp-pf-lt-r {
    grid-template-columns: 22px 1.6fr 1.4fr 0.6fr 1fr;
    gap: 10px;
  }
  .cp-pf-lt-r > :nth-child(6),
  .cp-pf-lt-h > :nth-child(6) {
    display: none;
  }
}
</style>
