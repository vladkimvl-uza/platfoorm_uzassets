<script setup lang="ts">
/**
 * PaProductDrillModal — drill 3-го уровня по товару (productCode).
 * v2 rewrite 2026-05-26: built on PaModalShell + 2 tabs.
 *
 *   Tabs:
 *     • Покупатели — SOE groups (expandable если >1 контракт)
 *     • Контракты — flat-list всех контрактов товара
 *
 * 2026-05-26: фильтр is_dirty в default-view. Чекбокс «показать dirty»
 * откроет полный набор включая мусор (для аудита).
 *
 * Quality-band:
 *   spread < 200%   → clean (зелёный)
 *   200-1000%       → wide  (амбер) с warning
 *   > 1000%         → dirty (красный) — обычно автоматически is_dirty=true
 */
import { computed, ref } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import PaModalShell from "./PaModalShell.vue";

const props = defineProps<{
  productCode: string;
  data: ProcurementAggregate;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "drill-purchase", purchase: ClosureRow): void;
}>();

// ─── Tab state ──────────────────────────────────────────────────
type Tab = "buyers" | "contracts";
const activeTab = ref<Tab>("buyers");

// ─── Show-dirty toggle ─────────────────────────────────────────
const showDirty = ref(false);

// Бэкенд-агрегат по этому коду (band-методика: median/min/max/потенциал/quality
// согласованы с дашбордом). Заголовочные числа берём отсюда, а не из line-level.
const prod = computed(() => props.data.products_by_code?.[props.productCode] || null);

// ─── All purchases of this product (raw + filtered) ────────────
// Ключ группировки = product_code (как на бэке aggregate_products), без fallback
// на sub_product_code/product_name — иначе набор строк расходился бы с агрегатом.
const allRows = computed<ClosureRow[]>(() =>
  props.data.purchases
    .filter(r => r.product_code === props.productCode)
    .sort((a, b) => a.unit_price - b.unit_price),
);

const dirtyCount = computed(() => allRows.value.filter(r => r.is_dirty).length);

const rows = computed<ClosureRow[]>(() =>
  showDirty.value ? allRows.value : allRows.value.filter(r => !r.is_dirty),
);

// ─── Product metadata ──────────────────────────────────────────
const productMeta = computed(() => {
  const first = allRows.value[0];
  if (!first) return null;
  return {
    name: first.product_name || props.productCode,
    code: props.productCode,
    unit: first.category_unit || "ед",
    categoryName: first.category_name,
  };
});

// ─── Stats ──────────────────────────────────────────────────────
// Заголовочные числа — из backend band-агрегата (потенциал/median/min/max
// согласованы с дашбордом; грязные/услуги/<3 покупателей уже учтены на бэке).
// Fallback на line-level только если кода нет в агрегате.
const stats = computed(() => {
  const p = prod.value;
  if (p) {
    return {
      minPrice: Number(p.min_price),
      maxPrice: Number(p.max_price),
      avgPrice: Number(p.avg_price),
      totalValue: Number(p.total_spend),
      totalSaving: Number(p.potential_saving),
      uniqueBuyers: Number(p.unique_buyers),
    };
  }
  const list = rows.value;
  if (!list.length) {
    return { minPrice: 0, maxPrice: 0, avgPrice: 0, totalValue: 0, totalSaving: 0, uniqueBuyers: 0 };
  }
  const prices = list.map(r => Number(r.unit_price));
  const minP = Math.min(...prices);
  const maxP = Math.max(...prices);
  let sumP = 0, sumV = 0;
  for (const r of list) {
    sumP += Number(r.unit_price) * Number(r.volume);
    sumV += Number(r.volume);
  }
  const avgP = sumV > 0 ? sumP / sumV : 0;
  const buyers = new Set<string>(list.map(r => r.company_id));
  return { minPrice: minP, maxPrice: maxP, avgPrice: avgP, totalValue: sumP, totalSaving: 0, uniqueBuyers: buyers.size };
});

// Разброс/качество — из backend (band spread + полный разброс для плашки).
const spreadPct = computed(() => prod.value ? Number(prod.value.spread_pct) : (
  stats.value.minPrice > 0 ? ((stats.value.maxPrice / stats.value.minPrice - 1) * 100) : 0
));
const fullSpreadPct = computed(() => prod.value ? Number(prod.value.full_spread_pct) : spreadPct.value);

const qualityBand = computed<"clean" | "wide" | "dirty">(() => {
  if (prod.value) return prod.value.quality_band;
  const v = fullSpreadPct.value;
  if (v < 200) return "clean";
  if (v <= 1000) return "wide";
  return "dirty";
});

const qualityMeta = computed(() => {
  switch (qualityBand.value) {
    case "clean":
      return { label: "Чистый benchmark", color: "#0F6E56", bg: "rgba(15,110,86,.12)" };
    case "wide":
      return { label: "Большой разброс", color: "#B07415", bg: "rgba(176,116,21,.12)" };
    default:
      return { label: "Подозрительный", color: "#A32D2D", bg: "rgba(163,45,45,.12)" };
  }
});

const warningText = computed(() => {
  if (qualityBand.value === "clean") return null;
  if (qualityBand.value === "wide") {
    return "Цены различаются в >2× раз — benchmark median может быть искажён. Возможно разные размеры/спецификации товара.";
  }
  return "Цены различаются в >10× раз — почти наверняка разные продукты под одним кодом. Не используйте данные для аудита без проверки product spec.";
});

const accentColor = computed(() => qualityMeta.value.color);

// ─── SOE groups (one per company, expandable if >1 contract) ────
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
    const price = Number(r.unit_price);
    const vol = Number(r.volume);
    let g = map.get(r.company_id);
    if (!g) {
      g = {
        companyId: r.company_id,
        companyName: r.company_name || r.company_id,
        companyColor: r.company_color,
        contracts: [],
        minPrice: price, maxPrice: price,
        sumSpend: 0, sumVol: 0, avgPrice: 0,
      };
      map.set(r.company_id, g);
    }
    g.contracts.push(r);
    if (price < g.minPrice) g.minPrice = price;
    if (price > g.maxPrice) g.maxPrice = price;
    g.sumSpend += price * vol;
    g.sumVol += vol;
  }
  for (const g of map.values()) g.avgPrice = g.sumVol > 0 ? g.sumSpend / g.sumVol : 0;
  return [...map.values()].sort((a, b) => a.avgPrice - b.avgPrice);
});

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

function rowNum(i: number): string { return i < 9 ? "0" + (i + 1) : String(i + 1); }

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

function spreadShort(v: number): string {
  if (v < 100) return v.toFixed(0) + "%";
  return (v / 100).toFixed(1) + "×";
}

// Для плашки/баннера: у грязных/широких кодов band-спред может быть мал (≈0%),
// тогда как полный разброс огромен — показываем именно полный, чтобы плашка
// «грязный» и число согласовывались.
const displaySpreadShort = computed(() =>
  spreadShort(qualityBand.value === "clean" ? spreadPct.value : fullSpreadPct.value),
);

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

// Flat-list of contracts for the Contracts tab
const flatContracts = computed<ClosureRow[]>(() =>
  [...rows.value].sort((a, b) => a.unit_price - b.unit_price),
);
</script>

<template>
  <PaModalShell
    kind="Товар"
    :title="productMeta?.name || productCode"
    :accent="accentColor"
    max-width="1080px"
    @close="emit('close')"
  >
    <!-- ─── Stats ─── -->
    <template #stats>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Median</div>
        <div class="pms-stat-val">{{ paFmtMoney(stats.avgPrice) }}<small>/{{ productMeta?.unit || 'ед' }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Минимум</div>
        <div class="pms-stat-val pos">{{ paFmtMoney(stats.minPrice) }}</div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Максимум</div>
        <div class="pms-stat-val neg">{{ paFmtMoney(stats.maxPrice) }}</div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Спред</div>
        <div class="pms-stat-val" :style="{ color: accentColor }">{{ spreadShort(spreadPct) }}</div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Покупателей</div>
        <div class="pms-stat-val">{{ stats.uniqueBuyers }}<small>SOE</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Потенциал</div>
        <div class="pms-stat-val neg">+{{ paFmtMoneyShort(stats.totalSaving) }}<small>сум</small></div>
      </div>
    </template>

    <!-- ─── Tabs ─── -->
    <template #tabs>
      <button class="pms-tab" :class="{ active: activeTab === 'buyers' }" @click="activeTab = 'buyers'">
        Покупатели<span class="pms-tab-count">{{ soeGroups.length }}</span>
      </button>
      <button class="pms-tab" :class="{ active: activeTab === 'contracts' }" @click="activeTab = 'contracts'">
        Контракты<span class="pms-tab-count">{{ flatContracts.length }}</span>
      </button>
      <!-- Right-aligned controls -->
      <div class="ppd-tab-right">
        <span class="ppd-quality-badge"
              :style="{ background: qualityMeta.bg, color: qualityMeta.color }"
              :title="`Полный разброс цен: ${displaySpreadShort}`">{{ qualityMeta.label }}</span>
        <label v-if="dirtyCount > 0" class="ppd-show-dirty">
          <input type="checkbox" v-model="showDirty" />
          <span>Показать dirty ({{ dirtyCount }})</span>
        </label>
      </div>
    </template>

    <!-- ─── Body ─── -->
    <div class="ppdv-body">

      <!-- Warning banner -->
      <div v-if="warningText" class="ppdv-warn" :class="'ppdv-warn-' + qualityBand">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v4M12 17h.01"/>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        </svg>
        <div>
          <div class="ppdv-warn-t"><b>{{ qualityMeta.label }}</b> · полный разброс {{ displaySpreadShort }}</div>
          <div class="ppdv-warn-s">{{ warningText }}</div>
        </div>
      </div>

      <!-- Distribution bar (only for non-dirty) -->
      <div v-if="distMarkers.length > 2 && qualityBand !== 'dirty'" class="ppdv-dist">
        <div class="ppdv-dist-l">
          <span class="ppdv-dist-lbl">Распределение цен</span>
          <span class="ppdv-dist-rng">
            {{ paFmtMoneyShort(stats.minPrice) }}
            <span class="ppdv-dist-arrow">←—→</span>
            {{ paFmtMoneyShort(stats.maxPrice) }}
          </span>
        </div>
        <div class="ppdv-dist-track">
          <span v-for="(m, i) in distMarkers" :key="i"
                class="ppdv-dist-dot"
                :style="{
                  left: m.x + '%',
                  background: m.color,
                  animationDelay: m.delay + 'ms',
                }"
                :title="m.title" />
        </div>
      </div>

      <!-- Tab content (animated switch) -->
      <Transition name="pa-tab" mode="out-in">
      <div :key="activeTab" class="ppdv-tab-wrap">
      <!-- Tab: Buyers -->
      <div v-if="activeTab === 'buyers'" class="ppdv-tab-table">
        <table class="ppdv-tbl pa-stagger" v-if="soeGroups.length">
          <thead>
            <tr>
              <th class="rk">#</th>
              <th class="left">Покупатель</th>
              <th class="right">Avg цена</th>
              <th class="right">Объём</th>
              <th class="left">Поставщик</th>
              <th class="left">Период</th>
              <th class="right">vs median</th>
              <th class="right">vs лидер</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="(g, i) in soeGroups" :key="g.companyId">
              <tr class="ppdv-row" :class="{ 'ppdv-row-clickable': true }"
                  @click="g.contracts.length > 1 ? toggleSoe(g.companyId) : emit('drill-purchase', g.contracts[0])"
                  :title="g.contracts.length > 1 ? `${g.contracts.length} контрактов — кликни для раскрытия` : 'Открыть детали закупки'">
                <td class="rk">{{ rowNum(i) }}</td>
                <td class="left">
                  <span class="ppdv-strip" :style="{ background: g.companyColor || '#888' }"></span>
                  {{ g.companyName }}
                  <span v-if="i === 0" class="ppdv-badge leader">лидер цены</span>
                  <span v-else-if="i === soeGroups.length - 1 && soeGroups.length >= 3" class="ppdv-badge lagger">пик</span>
                  <span v-if="g.contracts.length > 1" class="ppdv-expand" :class="{ open: expandedSoe.has(g.companyId) }">▾</span>
                </td>
                <td class="right">
                  <b>{{ paFmtMoney(g.avgPrice) }}</b>
                  <div v-if="distFromBest(g.avgPrice) > 0" class="ppdv-dist-from">+{{ distFromBest(g.avgPrice).toFixed(0) }}% от лидера</div>
                </td>
                <td class="right">{{ g.sumVol.toLocaleString('ru-RU') }}</td>
                <td class="left supplier">{{ supplierTxt(g) }}</td>
                <td class="left muted">{{ dateTxt(g) }}</td>
                <td class="right" :class="devPctVsAvg(g.avgPrice) >= 0 ? 'neg' : 'pos'">
                  {{ devPctVsAvg(g.avgPrice) >= 0 ? '+' : '' }}{{ devPctVsAvg(g.avgPrice).toFixed(1) }}%
                </td>
                <td class="right">
                  <span v-if="(g.avgPrice - stats.minPrice) * g.sumVol > 0" class="ppdv-loss">
                    +{{ paFmtMoneyShort((g.avgPrice - stats.minPrice) * g.sumVol) }}
                  </span>
                  <span v-else class="muted">—</span>
                </td>
              </tr>
              <!-- Expanded contracts -->
              <template v-if="expandedSoe.has(g.companyId) && g.contracts.length > 1">
                <tr v-for="(c, ci) in g.contracts" :key="g.companyId + '-' + c.id" class="ppdv-subrow">
                  <td></td>
                  <td class="left sub">
                    <span class="ppdv-sub-mark">№{{ ci + 1 }}</span>
                    <span class="muted">{{ fmtDate(c.contract_date) }}</span>
                  </td>
                  <td class="right">{{ paFmtMoney(c.unit_price) }}</td>
                  <td class="right">{{ c.volume.toLocaleString('ru-RU') }}</td>
                  <td class="left supplier">{{ c.supplier || '—' }}</td>
                  <td class="left muted">{{ fmtDate(c.contract_date) }}</td>
                  <td class="right" :class="devPctVsAvg(c.unit_price) >= 0 ? 'neg' : 'pos'">
                    {{ devPctVsAvg(c.unit_price) >= 0 ? '+' : '' }}{{ devPctVsAvg(c.unit_price).toFixed(1) }}%
                  </td>
                  <td class="right">
                    <button class="ppdv-mini-btn" @click.stop="emit('drill-purchase', c)" title="Открыть детали">→</button>
                  </td>
                </tr>
              </template>
            </template>
          </tbody>
        </table>
        <div v-else class="pms-empty">Нет данных по товару</div>
      </div>

      <!-- Tab: Contracts (flat list) -->
      <div v-else-if="activeTab === 'contracts'" class="ppdv-tab-table">
        <table class="ppdv-tbl pa-stagger" v-if="flatContracts.length">
          <thead>
            <tr>
              <th class="left">Покупатель</th>
              <th class="left">Дата</th>
              <th class="left">Поставщик</th>
              <th class="right">Цена</th>
              <th class="right">Объём</th>
              <th class="right">vs median</th>
              <th class="right"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in flatContracts" :key="c.id"
                class="ppdv-row ppdv-row-clickable"
                :class="{ 'ppdv-row-dirty': c.is_dirty }"
                @click="emit('drill-purchase', c)"
                title="Открыть детали закупки">
              <td class="left">
                <span class="ppdv-strip" :style="{ background: c.company_color || '#888' }"></span>
                {{ c.company_name || c.company_id }}
              </td>
              <td class="left muted">{{ fmtDate(c.contract_date) }}</td>
              <td class="left supplier">{{ c.supplier || '—' }}</td>
              <td class="right"><b>{{ paFmtMoney(c.unit_price) }}</b></td>
              <td class="right">{{ c.volume.toLocaleString('ru-RU') }}</td>
              <td class="right" :class="devPctVsAvg(c.unit_price) >= 0 ? 'neg' : 'pos'">
                {{ devPctVsAvg(c.unit_price) >= 0 ? '+' : '' }}{{ devPctVsAvg(c.unit_price).toFixed(1) }}%
                <span v-if="c.is_dirty" class="ppdv-dirty-tag" title="Dirty">⚠</span>
              </td>
              <td class="right">
                <span class="ppdv-arrow">→</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="pms-empty">Нет контрактов</div>
      </div>
      </div>
      </Transition>
    </div>
  </PaModalShell>
</template>

<style scoped>
.ppd-tab-right {
  margin-left: auto;
  display: flex; align-items: center; gap: 12px;
  padding: 8px 0;
}
.ppd-quality-badge {
  font-size: 10px; font-weight: 700;
  padding: 3px 9px; border-radius: 4px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.ppd-show-dirty {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; color: var(--t3, #5F5E5A);
  cursor: pointer;
  user-select: none;
}
.ppd-show-dirty input { margin: 0; cursor: pointer; }

.ppdv-body {
  padding: 0;
  display: flex; flex-direction: column;
  flex: 1; min-height: 0;
}

.ppdv-warn {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 12px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  font-size: 12px;
  background: rgba(239, 159, 39, .08);
  color: var(--t1, #1E2A4A);
}
.ppdv-warn-dirty { background: rgba(163, 45, 45, .08); }
.ppdv-warn svg { color: #B07415; flex-shrink: 0; margin-top: 2px; }
.ppdv-warn-dirty svg { color: var(--sev-critical); }
.ppdv-warn-t :deep(b), .ppdv-warn-t b { font-weight: 600; }
.ppdv-warn-s { font-size: 11.5px; color: var(--t3, #5F5E5A); margin-top: 2px; line-height: 1.5; }

.ppdv-dist {
  padding: 12px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  background: var(--bg2, #FAFAFC);
}
.ppdv-dist-l {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.ppdv-dist-lbl { font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: 0.06em; }
.ppdv-dist-rng { font-size: 11px; color: var(--t3, #5F5E5A); font-variant-numeric: tabular-nums; }
.ppdv-dist-arrow { margin: 0 6px; color: var(--t3, var(--t-muted)); }
.ppdv-dist-track {
  position: relative;
  height: 8px;
  background: linear-gradient(to right, rgba(29, 158, 117, .12), rgba(127, 119, 221, .10), rgba(226, 75, 74, .12));
  border-radius: 4px;
}
.ppdv-dist-dot {
  position: absolute;
  top: -2px;
  width: 6px; height: 12px;
  border-radius: 3px;
  transform: translateX(-50%);
  animation: ppdvDistFade .4s ease both;
}
@keyframes ppdvDistFade { from { opacity: 0; transform: translateX(-50%) translateY(4px); } to { opacity: 1; transform: translateX(-50%) translateY(0); } }

/* ─── Table ─── */
.ppdv-tab-wrap {
  display: flex; flex-direction: column;
  flex: 1; min-height: 0;
}
.ppdv-tab-table {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.ppdv-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.ppdv-tbl thead th {
  padding: 10px 14px;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  background: var(--bg2, #FAFAFC);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky; top: 0; z-index: 1;
  white-space: nowrap;
}
.ppdv-tbl thead th.left { text-align: left; }
.ppdv-tbl thead th.right { text-align: right; }
.ppdv-tbl thead th.rk { text-align: center; width: 36px; }

.ppdv-tbl tbody td {
  padding: 9px 14px;
  border-bottom: 0.5px solid rgba(15, 23, 60, .05);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.ppdv-tbl tbody td.left { text-align: left; }
.ppdv-tbl tbody td.right { text-align: right; }
.ppdv-tbl tbody td.rk { text-align: center; color: var(--t3, var(--t-muted)); font-weight: 600; font-size: 11px; }
.ppdv-tbl tbody td.muted { color: rgba(15, 23, 60, .55); font-weight: 400; }
.ppdv-tbl tbody td.supplier { color: rgba(15, 23, 60, .65); font-style: italic; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ppdv-tbl tbody td.pos { color: var(--green); font-weight: 600; }
.ppdv-tbl tbody td.neg { color: #C53030; font-weight: 600; }

.ppdv-row-clickable { cursor: pointer; transition: background .15s ease; }
.ppdv-row-clickable td { transition: background .15s ease, transform .15s cubic-bezier(.22, 1, .36, 1); }
.ppdv-row-clickable:hover td { background: rgba(127, 119, 221, .06); }
.ppdv-row-clickable:hover td:nth-child(2) { transform: translateX(2px); }

.ppdv-row-dirty td { opacity: 0.6; }

@media (prefers-reduced-motion: reduce) {
  .ppdv-dist-dot { animation: none !important; opacity: 1 !important; }
  .ppdv-row-clickable, .ppdv-row-clickable td { transition: none; }
  .ppdv-row-clickable:hover td:nth-child(2) { transform: none; }
}

.ppdv-strip {
  display: inline-block;
  width: 3px; height: 14px;
  border-radius: 2px;
  margin-right: 8px;
  vertical-align: middle;
}

.ppdv-badge {
  display: inline-block;
  font-size: 9px; font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: 6px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.ppdv-badge.leader { background: rgba(29, 158, 117, .14); color: #0F6E56; }
.ppdv-badge.lagger { background: rgba(226, 75, 74, .14); color: var(--sev-critical); }

.ppdv-expand {
  display: inline-block;
  margin-left: 6px;
  color: var(--t3, var(--t-muted));
  transition: transform .15s;
  font-size: 10px;
}
.ppdv-expand.open { transform: rotate(180deg); }

.ppdv-dist-from {
  font-size: 9.5px; color: var(--t3, var(--t-muted));
  margin-top: 1px;
  font-weight: 400;
}

.ppdv-loss { color: #C53030; font-weight: 600; }
.ppdv-arrow { color: rgba(0, 0, 0, .25); }

.ppdv-subrow {
  background: rgba(127, 119, 221, .03);
}
.ppdv-subrow td { padding: 7px 14px; font-size: 11.5px; }
.ppdv-sub-mark {
  display: inline-block;
  font-size: 9px; font-weight: 700;
  background: rgba(127, 119, 221, .15);
  color: var(--p-deep);
  padding: 1px 5px; border-radius: 3px;
  margin-right: 6px;
}

.ppdv-mini-btn {
  background: transparent;
  border: 1px solid rgba(127, 119, 221, .25);
  color: var(--p-deep);
  width: 22px; height: 22px;
  border-radius: 5px;
  font-size: 13px; font-family: inherit;
  cursor: pointer;
  transition: all .12s;
}
.ppdv-mini-btn:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }

.ppdv-dirty-tag {
  font-size: 10px;
  margin-left: 4px;
  color: #B07415;
}
</style>
