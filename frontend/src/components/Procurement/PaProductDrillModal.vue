<script setup lang="ts">
/**
 * PaProductDrillModal — drill 3-го уровня по товару (productCode).
 *
 * Все SOE покупающие тот же product_code, отсортированы по avgPrice asc.
 * Badges: лидер цены (#1), пик (последний если >=3 SOE).
 * Expandable rows для SOE с >1 контрактом.
 */
import { computed, ref } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";

const props = defineProps<{
  productCode: string;
  data: ProcurementAggregate;
}>();

defineEmits<{
  (e: "close"): void;
  (e: "drill-purchase", purchase: ClosureRow): void;
}>();

// Все закупки этого товара
const rows = computed<ClosureRow[]>(() => {
  return props.data.purchases
    .filter(r => (r.product_code || r.sub_product_code || r.product_name) === props.productCode)
    .sort((a, b) => a.unit_price - b.unit_price);
});

const productMeta = computed(() => {
  const first = rows.value[0];
  if (!first) return null;
  return {
    name: first.product_name || props.productCode,
    code: props.productCode,
    unit: first.category_unit || "ед",
    categoryName: first.category_name,
  };
});

const stats = computed(() => {
  const list = rows.value;
  if (!list.length) {
    return { minPrice: 0, maxPrice: 0, avgPrice: 0, totalValue: 0, totalSaving: 0, uniqueBuyers: 0 };
  }
  const prices = list.map(r => r.unit_price);
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  const avgP = prices.reduce((s, v) => s + v, 0) / prices.length;
  let totalValue = 0, totalSaving = 0;
  const buyers = new Set<string>();
  for (const r of list) {
    totalValue += r.unit_price * r.volume;
    totalSaving += (r.unit_price - minP) * r.volume;
    buyers.add(r.company_id);
  }
  return { minPrice: minP, maxPrice: maxP, avgPrice: avgP, totalValue, totalSaving, uniqueBuyers: buyers.size };
});

const saveSharePct = computed(() => {
  return stats.value.totalValue > 0
    ? (stats.value.totalSaving / stats.value.totalValue) * 100
    : 0;
});

// Group by SOE (one row per SOE, expandable if >1 contract)
interface SoeGroup {
  companyId: string;
  companyName: string;
  companyColor: string | null;
  contracts: ClosureRow[];
  minPrice: number;
  maxPrice: number;
  sumSpend: number;
  sumVol: number;
  avgPrice: number;
}

const soeGroups = computed<SoeGroup[]>(() => {
  const map = new Map<string, SoeGroup>();
  for (const r of rows.value) {
    const k = r.company_id;
    let g = map.get(k);
    if (!g) {
      g = {
        companyId: k,
        companyName: r.company_name || k,
        companyColor: r.company_color,
        contracts: [],
        minPrice: r.unit_price,
        maxPrice: r.unit_price,
        sumSpend: 0,
        sumVol: 0,
        avgPrice: 0,
      };
      map.set(k, g);
    }
    g.contracts.push(r);
    if (r.unit_price < g.minPrice) g.minPrice = r.unit_price;
    if (r.unit_price > g.maxPrice) g.maxPrice = r.unit_price;
    g.sumSpend += r.unit_price * r.volume;
    g.sumVol += r.volume;
  }
  for (const g of map.values()) {
    g.avgPrice = g.sumVol > 0 ? g.sumSpend / g.sumVol : 0;
  }
  return [...map.values()].sort((a, b) => a.avgPrice - b.avgPrice);
});

// Expand state
const expandedSoe = ref<Set<string>>(new Set());
function toggleSoe(id: string) {
  if (expandedSoe.value.has(id)) expandedSoe.value.delete(id);
  else expandedSoe.value.add(id);
  expandedSoe.value = new Set(expandedSoe.value);
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return d;
}

function devPctVsAvg(price: number): number {
  return stats.value.avgPrice > 0 ? ((price - stats.value.avgPrice) / stats.value.avgPrice) * 100 : 0;
}

function distFromBest(price: number): number {
  return stats.value.minPrice > 0 ? ((price / stats.value.minPrice - 1) * 100) : 0;
}

function rowNum(i: number): string {
  return i < 9 ? "0" + (i + 1) : String(i + 1);
}

function supplierTxt(g: SoeGroup): string {
  if (g.contracts.length === 1) return g.contracts[0].supplier || "—";
  const supSet = new Set(g.contracts.map(c => c.supplier).filter(s => s && s !== "—") as string[]);
  if (supSet.size === 0) return "—";
  if (supSet.size === 1) return [...supSet][0];
  return `${supSet.size} разных`;
}

function dateTxt(g: SoeGroup): string {
  const dates = g.contracts.map(c => c.contract_date).filter(Boolean).sort() as string[];
  if (!dates.length) return "—";
  if (g.contracts.length > 1 && dates.length > 1) {
    return `${fmtDate(dates[0])} … ${fmtDate(dates[dates.length - 1])}`;
  }
  return fmtDate(dates[0]);
}

 * spread = (max-min)/min × 100 → quality band:
 *   clean: spread < 200%   → green badge "Чистый benchmark"
 *   wide:  spread 200-1000 → amber badge + warning "Большой разброс"
 *   dirty: spread > 1000   → red badge + warning "Подозрительный"
 */
const spreadPct = computed(() => {
  const s = stats.value;
  return s.minPrice > 0 ? ((s.maxPrice / s.minPrice - 1) * 100) : 0;
});
const spreadCol = computed(() => {
  const v = spreadPct.value;
  if (v >= 500) return "#A32D2D";
  if (v >= 100) return "#BA7517";
  return "#5F5E5A";
});
const qualityBand = computed<"clean" | "wide" | "dirty">(() => {
  const v = spreadPct.value;
  if (v < 200) return "clean";
  if (v <= 1000) return "wide";
  return "dirty";
});
const qualityMeta = computed(() => {
  switch (qualityBand.value) {
    case "clean":
      return { label: "Чистый benchmark", color: "#0F6E56", bg: "rgba(15,110,86,.10)" };
    case "wide":
      return { label: "Большой разброс", color: "#BA7517", bg: "rgba(186,117,23,.10)" };
    case "dirty":
      return { label: "Подозрительный", color: "#A32D2D", bg: "rgba(163,45,45,.10)" };
  }
  return { label: "—", color: "#5F5E5A", bg: "rgba(95,94,90,.10)" };
});
const warningText = computed(() => {
  if (qualityBand.value === "clean") return null;
  if (qualityBand.value === "wide") {
    return "Цены различаются в >2× раз — benchmark median может быть искажён. Возможно разные размеры/спецификации товара.";
  }
  return "Цены различаются в >10× раз — почти наверняка разные продукты под одним кодом. Не используй данные для аудита без proverки product spec.";
});

// Distribution markers — позиция точки 0-100% (left edge = min, right = max)
const distMarkers = computed(() => {
  const s = stats.value;
  const range = s.maxPrice - s.minPrice;
  if (!range) return [];
  return soeGroups.value.map((g, i) => ({
    x: ((g.avgPrice - s.minPrice) / range) * 100,
    color: g.companyColor || "#7F77DD",
    title: `${g.companyName}: ${paFmtMoney(g.avgPrice)}`,
    delay: i * 40,
  }));
});

function spreadShort(v: number): string {
  if (v < 100) return v.toFixed(0) + "%";
  return (v / 100).toFixed(1) + "×";
}
</script>

<template>
  <Transition name="uza-fade" appear>
    <div class="pa-modal-bg" @click.self="$emit('close')">
      <div class="pa-modal-card">

        <div class="pa-mh">
          <div class="pa-mh-l">
            <div class="pa-mh-cat" v-if="productMeta">
              <span class="pa-mh-pill">{{ productMeta.code }}</span>
              {{ productMeta.categoryName }}
              <span class="pa-pd-qbadge"
                :style="{ background: qualityMeta.bg, color: qualityMeta.color }"
                :title="`Спред цен: ${spreadShort(spreadPct)}`">
                {{ qualityMeta.label }}
              </span>
            </div>
            <div class="pa-mh-t">{{ productMeta?.name || '—' }}</div>
            <div class="pa-mh-s">
              {{ rows.length }} закупок · {{ stats.uniqueBuyers }} SOE-покупателей ·
              цена {{ paFmtMoneyShort(stats.minPrice) }}—{{ paFmtMoneyShort(stats.maxPrice) }} сум/{{ productMeta?.unit || 'ед' }}
            </div>
          </div>
          <button class="pa-mh-x" @click="$emit('close')">✕</button>
        </div>

        <div v-if="warningText" class="pa-pd-warn" :class="'pa-pd-warn-' + qualityBand">
          <div class="pa-pd-warn-icon">{{ qualityBand === 'dirty' ? '⚠' : '!' }}</div>
          <div class="pa-pd-warn-body">
            <div class="pa-pd-warn-t">
              {{ qualityMeta.label }}: спред {{ spreadShort(spreadPct) }}
            </div>
            <div class="pa-pd-warn-s">{{ warningText }}</div>
          </div>
        </div>

        <div class="pa-mk-row pa-pd-kpi">
          <div class="pa-mk" style="--pd-d:0ms">
            <div class="pa-mk-l">Средняя</div>
            <div class="pa-mk-v">{{ paFmtMoney(stats.avgPrice) }}<small>/{{ productMeta?.unit || 'ед' }}</small></div>
          </div>
          <div class="pa-mk pa-pd-mk-best" style="--pd-d:60ms">
            <div class="pa-mk-l">Минимум</div>
            <div class="pa-mk-v leader">{{ paFmtMoney(stats.minPrice) }}<small>/{{ productMeta?.unit || 'ед' }}</small></div>
          </div>
          <div class="pa-mk" style="--pd-d:120ms">
            <div class="pa-mk-l">Максимум</div>
            <div class="pa-mk-v lagger">{{ paFmtMoney(stats.maxPrice) }}<small>/{{ productMeta?.unit || 'ед' }}</small></div>
          </div>
          <div class="pa-mk" style="--pd-d:180ms">
            <div class="pa-mk-l">Спред</div>
            <div class="pa-mk-v" :style="{ color: spreadCol }">
              {{ spreadShort(spreadPct) }}
            </div>
          </div>
          <div class="pa-mk" style="--pd-d:240ms">
            <div class="pa-mk-l">Покупателей</div>
            <div class="pa-mk-v">{{ stats.uniqueBuyers }}<small>SOE</small></div>
          </div>
          <div class="pa-mk" style="--pd-d:300ms">
            <div class="pa-mk-l">Потенциал экономии</div>
            <div class="pa-mk-v overpay">
              +{{ paFmtMoneyShort(stats.totalSaving) }}
              <small>{{ saveSharePct.toFixed(0) }}% контрактов</small>
            </div>
          </div>
        </div>

        <div v-if="distMarkers.length > 2 && qualityBand !== 'dirty'" class="pa-pd-distrib">
          <div class="pa-pd-distrib-l">
            <span>Распределение цен</span>
            <span class="pa-pd-distrib-rng">
              {{ paFmtMoneyShort(stats.minPrice) }} ←→ {{ paFmtMoneyShort(stats.maxPrice) }}
            </span>
          </div>
          <div class="pa-pd-distrib-track">
            <span
              v-for="(m, i) in distMarkers"
              :key="i"
              class="pa-pd-distrib-dot"
              :style="{
                left: m.x + '%',
                background: m.color,
                animationDelay: m.delay + 'ms',
              }"
              :title="m.title"
            />
          </div>
        </div>

        <!-- Buyers table -->
        <div class="pa-mb">
          <table class="pa-pd-tbl">
            <thead>
              <tr>
                <th class="rk">#</th>
                <th>Покупатель</th>
                <th class="rt">Avg цена</th>
                <th class="rt">Объём</th>
                <th>Поставщик</th>
                <th>Период</th>
                <th class="rt">vs median</th>
                <th class="rt">Vs лидер</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(g, i) in soeGroups" :key="g.companyId">
                <tr class="pa-pd-row" :style="{ animationDelay: (i * 30) + 'ms' }"
                  @click="g.contracts.length > 1 ? toggleSoe(g.companyId) : $emit('drill-purchase', g.contracts[0])">
                  <td class="num rk">{{ rowNum(i) }}</td>
                  <td class="lt">
                    <span class="pa-sec-strip" :style="{ background: g.companyColor || '#888' }"></span>
                    <span class="pa-co-nm" :title="g.companyName">{{ g.companyName }}</span>
                    <span v-if="i === 0" class="pa-pd-badge leader">лидер цены</span>
                    <span v-else-if="i === soeGroups.length - 1 && soeGroups.length >= 3" class="pa-pd-badge lagger">пик</span>
                    <span v-if="g.contracts.length > 1" class="pa-pd-expand" :class="{ open: expandedSoe.has(g.companyId) }">▾</span>
                  </td>
                  <td class="rt">
                    <b>{{ paFmtMoney(g.avgPrice) }}</b>
                    <div v-if="distFromBest(g.avgPrice) > 0" class="pa-pd-dist">+{{ distFromBest(g.avgPrice).toFixed(0) }}% от лидера</div>
                  </td>
                  <td class="rt">{{ g.sumVol.toLocaleString('ru-RU') }}</td>
                  <td class="muted-italic">{{ supplierTxt(g) }}</td>
                  <td class="muted">{{ dateTxt(g) }}</td>
                  <td class="rt" :class="devPctVsAvg(g.avgPrice) >= 0 ? 'up' : 'dn'">
                    {{ devPctVsAvg(g.avgPrice) >= 0 ? '+' : '' }}{{ devPctVsAvg(g.avgPrice).toFixed(1) }}%
                  </td>
                  <td class="rt">
                    <span v-if="(g.avgPrice - stats.minPrice) * g.sumVol > 0" class="pa-pd-loss">
                      +{{ paFmtMoneyShort((g.avgPrice - stats.minPrice) * g.sumVol) }}
                    </span>
                    <span v-else class="pa-pd-zero">—</span>
                  </td>
                </tr>
                <!-- Expanded contract sub-rows -->
                <template v-if="expandedSoe.has(g.companyId) && g.contracts.length > 1">
                  <tr v-for="(c, ci) in g.contracts" :key="g.companyId + '-' + c.id" class="pa-pd-subrow">
                    <td></td>
                    <td class="lt sub">
                      <span class="pa-sub-mark">№{{ ci + 1 }}</span>
                      <span class="muted">{{ fmtDate(c.contract_date) }}</span>
                    </td>
                    <td class="rt">{{ paFmtMoney(c.unit_price) }}</td>
                    <td class="rt">{{ c.volume.toLocaleString('ru-RU') }}</td>
                    <td class="muted-italic">{{ c.supplier || '—' }}</td>
                    <td class="muted">{{ fmtDate(c.contract_date) }}</td>
                    <td class="rt" :class="devPctVsAvg(c.unit_price) >= 0 ? 'up' : 'dn'">
                      {{ devPctVsAvg(c.unit_price) >= 0 ? '+' : '' }}{{ devPctVsAvg(c.unit_price).toFixed(1) }}%
                    </td>
                    <td class="rt">
                      <button class="pa-mini-btn" @click.stop="$emit('drill-purchase', c)">→</button>
                    </td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>

        <div class="pa-mf">
          <div class="pa-mf-meta">
            Год {{ data.year || '—' }} · клик по строке —
            {{ soeGroups.some(g => g.contracts.length > 1) ? 'раскрыть/детализация' : 'детализация' }}
          </div>
          <div class="pa-mf-actions">
            <button class="pa-mf-btn primary" @click="$emit('close')">Закрыть</button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.pa-modal-bg {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.pa-modal-card {
  background: #fff;
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 30px 80px rgba(15, 23, 42, .32);
  width: 1100px; max-width: 100%;
  max-height: 90vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}

/* Pack 7.9k: quality badge in header */
.pa-pd-qbadge {
  display: inline-block;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 4px;
  margin-left: 6px;
  vertical-align: middle;
}

/* Pack 7.9k: warning banner for wide/dirty */
.pa-pd-warn {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin: 0 18px 14px;
  padding: 12px 14px;
  border-radius: 10px;
  animation: paWarnIn .45s cubic-bezier(0.34, 1.2, 0.64, 1) 60ms both;
}
.pa-pd-warn-wide {
  background: rgba(186, 117, 23, .08);
  border: 1px solid rgba(186, 117, 23, .25);
  color: #6B4308;
}
.pa-pd-warn-dirty {
  background: rgba(163, 45, 45, .08);
  border: 1px solid rgba(163, 45, 45, .30);
  color: #6B1717;
}
.pa-pd-warn-icon {
  flex-shrink: 0;
  width: 22px; height: 22px;
  display: grid; place-items: center;
  font-size: 13px; font-weight: 700;
  border-radius: 50%;
  background: rgba(255, 255, 255, .55);
}
.pa-pd-warn-t {
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 2px;
  letter-spacing: -.005em;
}
.pa-pd-warn-s {
  font-size: 11.5px;
  line-height: 1.45;
  opacity: .85;
}
@keyframes paWarnIn {
  from { opacity: 0; transform: translateY(-4px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Pack 7.9k: 6-card KPI row with staggered per-card delay */
.pa-pd-kpi {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}
@media (max-width: 900px) {
  .pa-pd-kpi { grid-template-columns: repeat(3, 1fr); }
}
.pa-pd-kpi .pa-mk {
  animation: kpiCardIn .55s cubic-bezier(.34, 1.2, .64, 1) var(--pd-d, 0ms) both;
}
.pa-pd-mk-best {
  position: relative;
}
.pa-pd-mk-best::after {
  content: "★";
  position: absolute;
  top: 8px; right: 10px;
  color: #1D9E75;
  font-size: 11px;
  opacity: .65;
}

/* Pack 7.9k: distribution bar */
.pa-pd-distrib {
  margin: 4px 18px 16px;
  padding: 10px 14px;
  background: #FAFAFD;
  border-radius: 10px;
  border: 1px solid rgba(15, 23, 60, .04);
}
.pa-pd-distrib-l {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 10.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 8px;
}
.pa-pd-distrib-rng {
  text-transform: none;
  letter-spacing: 0;
  font-size: 11px;
  color: rgba(15, 23, 60, .65);
  font-feature-settings: 'tnum';
}
.pa-pd-distrib-track {
  position: relative;
  height: 14px;
  background: linear-gradient(90deg,
    rgba(29, 158, 117, .15),
    rgba(186, 117, 23, .12),
    rgba(163, 45, 45, .15));
  border-radius: 4px;
}
.pa-pd-distrib-dot {
  position: absolute;
  top: 50%;
  width: 10px; height: 10px;
  border-radius: 50%;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 60, .25);
  transform: translate(-50%, -50%) scale(0);
  animation: paDistDotIn .35s cubic-bezier(.34, 1.2, .64, 1) both;
  cursor: pointer;
  transition: transform .15s;
}
.pa-pd-distrib-dot:hover {
  transform: translate(-50%, -50%) scale(1.25);
  z-index: 1;
}
@keyframes paDistDotIn {
  from { transform: translate(-50%, -50%) scale(0); opacity: 0; }
  to   { transform: translate(-50%, -50%) scale(1); opacity: 1; }
}

.pa-mh {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
}
.pa-mh-l { min-width: 0; flex: 1; }
.pa-mh-cat {
  font-size: 11px; color: #888780;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.pa-mh-pill {
  display: inline-block;
  background: rgba(127, 119, 221, .12); color: #534AB7;
  font-size: 10px; font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
}
.pa-mh-t { font-size: 15px; font-weight: 600; color: #1E2A4A; }
.pa-mh-s { font-size: 11.5px; color: #888780; margin-top: 4px; }
.pa-mh-x {
  border: 0; background: #F4F3F9;
  width: 30px; height: 30px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: #888780;
  flex-shrink: 0;
}
.pa-mh-x:hover { background: rgba(226, 75, 74, .12); color: #A32D2D; }

.pa-mk-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 14px 22px;
  background: linear-gradient(180deg, #FAFAFC, #fff);
  border-bottom: 1px solid rgba(0, 0, 0, .04);
}
.pa-mk {
  padding: 8px 0;
  border-right: 0.5px solid rgba(0, 0, 0, .06);
}
.pa-mk:last-child { border-right: 0; }
.pa-mk-l {
  font-size: 9.5px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .07em;
  margin-bottom: 4px;
}
.pa-mk-v {
  font-size: 18px; font-weight: 600; color: #1E2A4A;
  font-feature-settings: "tnum";
  line-height: 1.1;
}
.pa-mk-v small { font-size: 10px; color: #888780; font-weight: 500; margin-left: 4px; display: block; margin-top: 2px; }
.pa-mk-v.leader { color: #1D9E75; }
.pa-mk-v.lagger { color: #A32D2D; }
.pa-mk-v.overpay { color: #B07415; }

.pa-mb {
  flex: 1; overflow-y: auto;
}

.pa-pd-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pa-pd-tbl thead th {
  position: sticky; top: 0;
  background: #FAFAFA;
  padding: 9px 12px; text-align: left;
  font-size: 10px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .04em;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
  z-index: 1;
}
.pa-pd-tbl thead th.rt { text-align: right; }
.pa-pd-tbl thead th.rk { text-align: center; width: 40px; }

.pa-pd-row {
  cursor: pointer;
  transition: background .1s;
  animation: paPdIn .25s ease both;
}
.pa-pd-row:hover { background: rgba(127, 119, 221, .04); }

.pa-pd-subrow { background: #FAFAFC; }
.pa-pd-subrow td { padding-top: 6px; padding-bottom: 6px; font-size: 11.5px; }

.pa-pd-tbl tbody td {
  padding: 8px 12px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  color: #1E2A4A;
  font-feature-settings: "tnum";
}
.pa-pd-tbl tbody td.rt { text-align: right; }
.pa-pd-tbl tbody td.rk { text-align: center; color: #888780; font-weight: 600; }
.pa-pd-tbl tbody td.lt {
  display: flex; align-items: center; gap: 6px;
  max-width: 280px;
}
.pa-pd-tbl tbody td.lt.sub { padding-left: 24px; }
.pa-pd-tbl tbody td.muted { color: #888780; }
.pa-pd-tbl tbody td.muted-italic { color: #888780; font-style: italic; }
.pa-pd-tbl tbody td.up { color: #A32D2D; font-weight: 600; }
.pa-pd-tbl tbody td.dn { color: #0F6E56; font-weight: 600; }

.pa-sec-strip {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; flex-shrink: 0;
}
.pa-co-nm {
  font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  max-width: 180px;
}

.pa-pd-badge {
  font-size: 9px; font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: .03em;
  white-space: nowrap;
  margin-left: 4px;
}
.pa-pd-badge.leader { background: rgba(29, 158, 117, .15); color: #0F6E56; }
.pa-pd-badge.lagger { background: rgba(226, 75, 74, .15); color: #A32D2D; }

.pa-pd-expand {
  font-size: 12px; color: #888780;
  margin-left: auto;
  transition: transform .15s;
  cursor: pointer;
}
.pa-pd-expand.open { transform: rotate(180deg); color: #534AB7; }

.pa-pd-dist {
  font-size: 9.5px; color: #888780;
  font-weight: 500;
  margin-top: 2px;
}

.pa-pd-loss { color: #E24B4A; font-weight: 600; }
.pa-pd-zero { color: #888780; }

.pa-sub-mark {
  display: inline-block;
  background: rgba(127, 119, 221, .12); color: #534AB7;
  font-size: 9px; font-weight: 700;
  padding: 1px 6px; border-radius: 3px;
  margin-right: 8px;
}

.pa-mini-btn {
  background: rgba(127, 119, 221, .12); color: #534AB7;
  border: 0;
  width: 22px; height: 22px;
  border-radius: 5px;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
}
.pa-mini-btn:hover { background: #7F77DD; color: #fff; }

.pa-mf {
  padding: 12px 22px;
  border-top: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  background: #FAFAFC;
}
.pa-mf-meta { font-size: 11px; color: #888780; }
.pa-mf-actions { display: flex; gap: 8px; }
.pa-mf-btn {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid rgba(15, 23, 60, .12);
  background: #fff;
  color: #1E2A4A;
  cursor: pointer;
  font-family: inherit;
}
.pa-mf-btn.primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pa-mf-btn.primary:hover { background: #6F66D0; }

@keyframes paPdIn {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}

.pa-modal-enter-active, .pa-modal-leave-active { transition: opacity .2s; }
.pa-modal-enter-active .pa-modal-card,
.pa-modal-leave-active .pa-modal-card { transition: transform .2s, opacity .2s; }
.pa-modal-enter-from .pa-modal-card,
.pa-modal-leave-to .pa-modal-card { transform: scale(.96); opacity: 0; }
.pa-modal-enter-from, .pa-modal-leave-to { opacity: 0; }
</style>
