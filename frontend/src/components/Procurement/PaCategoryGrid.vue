<script setup lang="ts">
/**
 * PaCategoryGrid — 1:1 port of paRenderCategoryGrid (legacy line 23067).
 *
 * Two modes:
 *  1. **Contracts mode** (meta.source === 'procurementContracts')
 *     — top-15 products per category from category_aggregates[].all_products
 *     — sortable headers (Товар/Средняя/Объём/Δ макс)
 *     — clean/wide/dirty quality bands
 *     — click product → emit drill-product (parent opens PaProductDrillModal)
 *
 *  2. **Legacy mode** (price-list seed)
 *     — list of individual closures sorted by deviation
 *     — click row → emit drill-closure
 *
 * Single-open accordion: opening one row closes others (legacy paToggleAccRow).
 */
import { computed, ref } from "vue";
import {
  paColorByDev,
  paFmtMoney,
  paFmtMoneyShort,
  paSameCat,
  type CategoryAggregate,
  type CategoryMeta,
  type ClosureRow,
  type ProductAgg,
} from "@/api/procurement_analysis";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const props = defineProps<{
  categories: CategoryMeta[];
  purchases: ClosureRow[];
  /** Per-category product aggregations from /procurement/aggregate.
   *  When present + non-empty → render contracts mode (top-15 products). */
  categoryAggregates?: CategoryAggregate[];
  /** Convenience map productCode → ProductAgg (for click drill). */
  productsByCode?: Record<string, ProductAgg>;
  /** Source flag. */
  source?: "procurementContracts" | "priceListLegacy";
}>();

defineEmits<{
  (e: "drill-closure", r: ClosureRow): void;
  (e: "drill-product", productCode: string): void;
}>();

// ─── Open-state (single-open accordion) ─────────────────────────
const openId = ref<number | null>(null);
function toggle(id: number) { openId.value = openId.value === id ? null : id; }
function isOpen(id: number): boolean { return openId.value === id; }

// ─── Sort state (contracts mode) ────────────────────────────────
type ProdSortKey = "totalSpend" | "avgPrice" | "spreadPct" | "maxDeviationPct" | "name";
const sortKey = ref<ProdSortKey>("totalSpend");
const sortDir = ref<"asc" | "desc">("desc");
function setSort(key: ProdSortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === "desc" ? "asc" : "desc";
  } else {
    sortKey.value = key;
    sortDir.value = key === "name" ? "asc" : "desc";
  }
}
function sortIndicator(key: ProdSortKey): string {
  if (sortKey.value !== key) return "";
  return sortDir.value === "desc" ? "▼" : "▲";
}

// ─── Mode detection ────────────────────────────────────────────
const fromContracts = computed<boolean>(() => {
  if (props.source === "procurementContracts") return true;
  return !!(props.categoryAggregates && props.categoryAggregates.length);
});

const aggByCat = computed<Record<number, CategoryAggregate>>(() => {
  const map: Record<number, CategoryAggregate> = {};
  for (const a of props.categoryAggregates || []) map[a.id] = a;
  return map;
});

// ─── Per-category helpers (legacy + contracts) ─────────────────
function purchasesByCat(catId: number): ClosureRow[] {
  const k = String(catId);
  return props.purchases.filter(r => r.category_id != null && String(r.category_id) === k);
}

/** "Has data" check — uses category_aggregates first (works for any volume of
 *  closures since aggregates are pre-computed). Falls back to purchases filter
 *  for legacy mode. */
function hasDataFor(catId: number): boolean {
  if (fromContracts.value) {
    const a = aggByCat.value[catId];
    return !!(a && a.all_products.length);
  }
  return purchasesByCat(catId).length > 0;
}

function coCountFor(catId: number): number {
  // Use unique buyers across products if available (more accurate than
  // filtering raw purchases when capped).
  if (fromContracts.value) {
    const a = aggByCat.value[catId];
    if (a) {
      const set = new Set<string>();
      for (const p of a.all_products) {
        // ProductAgg doesn't carry buyer IDs — approximate via unique_buyers.
        // For row count, sum up but cap at unique companies across cat.
        // Without raw data, return max unique_buyers as a proxy.
        set.add(String(p.unique_buyers));
      }
      // Better proxy: max of unique_buyers across products
      return Math.max(0, ...a.all_products.map(p => p.unique_buyers));
    }
  }
  return new Set(purchasesByCat(catId).map(r => r.company_id)).size;
}

function pad2(id: number): string {
  if (id === 0) return "—";
  return id < 10 ? "0" + id : String(id);
}

// ─── Spread (header) ──────────────────────────────────────────
function spreadFor(cat: CategoryMeta): { min: number; max: number; clean: boolean } {
  if (fromContracts.value) {
    const a = aggByCat.value[cat.id];
    if (a && a.clean_spread_min != null && a.clean_spread_max != null) {
      return { min: a.clean_spread_min, max: a.clean_spread_max, clean: true };
    }
    if (a && a.all_products.length) {
      const avgs = a.all_products.map(p => p.avg_price);
      return { min: Math.min(...avgs), max: Math.max(...avgs), clean: false };
    }
  }
  // Legacy
  const inCat = purchasesByCat(cat.id);
  if (!inCat.length) return { min: 0, max: 0, clean: false };
  const prices = inCat.map(r => Number(r.unit_price));
  return { min: Math.min(...prices), max: Math.max(...prices), clean: false };
}

// ─── Subtitle ─────────────────────────────────────────────────
function subtitleFor(cat: CategoryMeta): string {
  const parts: string[] = [(aggByCat.value[cat.id]?.unit) || cat.unit || "ед"];
  const inCat = purchasesByCat(cat.id);
  if (fromContracts.value) {
    const a = aggByCat.value[cat.id];
    if (a && a.benchmark_product_count) parts.push(a.benchmark_product_count + " товаров с benchmark");
    parts.push(inCat.length + " закупок");
  } else {
    parts.push(inCat.length + " закупок");
  }
  return parts.join(" · ");
}

// ─── Deviation bar + key stat ─────────────────────────────────
interface DevStats { min: number; max: number; avg: number; }
function devStatsFor(cat: CategoryMeta): DevStats | null {
  let inCat: { deviation_pct: number }[];
  if (fromContracts.value) {
    const a = aggByCat.value[cat.id];
    if (!a) return null;
    // Use clean products' max deviation (legacy filter dirty)
    const cleaners = a.all_products.filter(p => p.quality_band !== "dirty");
    const src = cleaners.length ? cleaners : a.all_products;
    if (!src.length) return null;
    const devs = src.map(p => p.max_deviation_pct);
    return {
      min: Math.min(...devs.map(d => -d)),   // negative side
      max: Math.max(...devs),
      avg: devs.reduce((s, v) => s + v, 0) / devs.length,
    };
  }
  inCat = purchasesByCat(cat.id);
  if (!inCat.length) return null;
  const devs = inCat.map(r => r.deviation_pct);
  return {
    min: Math.min(...devs),
    max: Math.max(...devs),
    avg: devs.reduce((s, v) => s + v, 0) / devs.length,
  };
}

function barFillStyle(cat: CategoryMeta, idx: number): Record<string, string> {
  const s = devStatsFor(cat);
  if (!s) return { display: "none" };
  const barLeft = Math.max(0, Math.min(100, 50 + (s.min / 30) * 50));
  const barRight = Math.max(0, Math.min(100, 50 + (s.max / 30) * 50));
  const barWidth = Math.max(3, barRight - barLeft);
  return {
    background: paColorByDev(s.avg),
    left: barLeft + "%",
    width: barWidth + "%",
    animationDelay: (idx * 25 + 250) + "ms",
  };
}

function keyStatFor(cat: CategoryMeta): { text: string; color: string } {
  const s = devStatsFor(cat);
  if (!s) return { text: "", color: "" };
  const safeMax = Number.isFinite(s.max) ? s.max : 0;
  const safeMin = Number.isFinite(s.min) ? s.min : 0;
  const keyVal = Math.abs(safeMax) > Math.abs(safeMin) ? safeMax : safeMin;
  const keyLabel = fmt.fmtPercent(keyVal, { decimals: 0, signed: true });
  const color = keyVal >= 10 ? "#C53030" : keyVal >= 0 ? "#B07415" : "#0F6E56";
  const prefix = Math.abs(safeMax) > Math.abs(safeMin) ? "макс " : "мин ";
  return { text: prefix + keyLabel, color };
}

// ─── Contracts mode: sorted top-15 products per opened category ─
function sortedProducts(cat: CategoryMeta): ProductAgg[] {
  const a = aggByCat.value[cat.id];
  if (!a) return [];
  const list = [...a.all_products];
  const sk = sortKey.value;
  list.sort((x, y) => {
    if (sk === "name") return (x.name || "").localeCompare(y.name || "");
    const xv = (x as unknown as Record<string, number>)[sortMapToField(sk)] || 0;
    const yv = (y as unknown as Record<string, number>)[sortMapToField(sk)] || 0;
    return yv - xv;
  });
  if (sortDir.value === "asc") list.reverse();
  return list.slice(0, 15);
}

function sortMapToField(k: ProdSortKey): string {
  switch (k) {
    case "totalSpend":      return "total_spend";
    case "avgPrice":        return "avg_price";
    case "spreadPct":       return "spread_pct";
    case "maxDeviationPct": return "max_deviation_pct";
    case "name":            return "name";
  }
}

function spreadCls(p: ProductAgg): "sp-hi" | "sp-md" | "sp-lo" {
  if (p.spread_pct >= 500) return "sp-hi";
  if (p.spread_pct >= 100) return "sp-md";
  return "sp-lo";
}
function spreadTxt(p: ProductAgg): string {
  const sp = Number(p.spread_pct) || 0;
  return "+" + (sp >= 1000 ? (sp / 100).toFixed(0) + "×" : sp.toFixed(0) + "%");
}
function rowNum(i: number): string { return i < 9 ? "0" + (i + 1) : String(i + 1); }

// Legacy mode detail rows
function detailRowsFor(catId: number): ClosureRow[] {
  return [...purchasesByCat(catId)].sort((a, b) => a.deviation_pct - b.deviation_pct);
}

function excludedCount(cat: CategoryMeta): { kept: number; raw: number; excluded: number } {
  const a = aggByCat.value[cat.id];
  const inCatRaw = props.purchases.filter(r => paSameCat(r.category_id, cat.id) && r.product_code);
  const uniqueRaw = new Set(inCatRaw.map(r => r.product_code)).size;
  const kept = a?.all_products.length || 0;
  return { kept, raw: uniqueRaw, excluded: Math.max(0, uniqueRaw - kept) };
}
</script>

<template>
  <div class="pa-acc">
    <div
      v-for="(cat, idx) in categories"
      :key="cat.id"
      class="pa-acc-row"
      :class="{
        'pa-acc-open':  isOpen(cat.id),
        'pa-acc-empty': !hasDataFor(cat.id),
      }"
      :style="{ animationDelay: `${idx * 25}ms` }"
      :data-acc-id="cat.id"
    >
      <!-- Empty row stub -->
      <template v-if="!hasDataFor(cat.id)">
        <div class="pa-acc-head pa-acc-head-empty">
          <span class="pa-acc-num">{{ pad2(cat.id) }}</span>
          <span class="pa-acc-name">
            {{ cat.name }}
            <small>{{ cat.unit || "ед" }}</small>
          </span>
          <span class="pa-acc-spread pa-empty-stat">нет данных</span>
        </div>
      </template>

      <!-- Active row -->
      <template v-else>
        <div class="pa-acc-head" @click="toggle(cat.id)">
          <span class="pa-acc-num">{{ pad2(cat.id) }}</span>
          <span class="pa-acc-name">
            {{ cat.name }}
            <small>{{ subtitleFor(cat) }}</small>
          </span>
          <span class="pa-acc-spread" :title="fromContracts ? (spreadFor(cat).clean ? 'Диапазон средних цен товаров с чистым benchmark (spread<200%)' : 'Все товары — clean выборки нет') : ''">
            {{ paFmtMoneyShort(spreadFor(cat).min) }} – {{ paFmtMoneyShort(spreadFor(cat).max) }}
          </span>
          <span class="pa-acc-bar">
            <span class="pa-acc-bar-fill" :style="barFillStyle(cat, idx)" />
          </span>
          <span class="pa-acc-stat" :style="{ color: keyStatFor(cat).color }">
            {{ keyStatFor(cat).text }}
          </span>
          <span class="pa-acc-chev" :class="{ open: isOpen(cat.id) }">▼</span>
        </div>

        <!-- Detail content -->
        <div class="pa-acc-detail" :class="{ open: isOpen(cat.id) }">
          <div class="pa-acc-detail-inner">
            <!-- CONTRACTS MODE: top-15 products with sortable headers -->
            <template v-if="fromContracts && aggByCat[cat.id] && aggByCat[cat.id].all_products.length">
              <table class="pa-prod-tbl">
                <colgroup>
                  <col style="width:30px"/>
                  <col/>
                  <col style="width:130px"/>
                  <col style="width:170px"/>
                  <col style="width:115px"/>
                  <col style="width:75px"/>
                  <col style="width:75px"/>
                </colgroup>
                <thead>
                  <tr>
                    <td>#</td>
                    <td class="sortable" :class="{ on: sortKey === 'name' }" @click.stop="setSort('name')">
                      Товар <span class="arr">{{ sortIndicator("name") }}</span>
                    </td>
                    <td class="r sortable" :class="{ on: sortKey === 'avgPrice' }" @click.stop="setSort('avgPrice')">
                      Средняя <span class="arr">{{ sortIndicator("avgPrice") }}</span>
                    </td>
                    <td class="r">Диапазон</td>
                    <td class="r sortable" :class="{ on: sortKey === 'totalSpend' }" @click.stop="setSort('totalSpend')">
                      Объём <span class="arr">{{ sortIndicator("totalSpend") }}</span>
                    </td>
                    <td class="r">Покупатели</td>
                    <td class="r sortable" :class="{ on: sortKey === 'spreadPct' }" @click.stop="setSort('spreadPct')">
                      Δ макс <span class="arr">{{ sortIndicator("spreadPct") }}</span>
                    </td>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(p, pi) in sortedProducts(cat)"
                    :key="p.code"
                    class="pa-prod-row"
                    :style="{ animationDelay: (pi * 30 + 200) + 'ms' }"
                    @click.stop="$emit('drill-product', p.code)"
                  >
                    <td class="num">{{ rowNum(pi) }}</td>
                    <td>
                      <div class="pa-prod-nm" :title="p.name">{{ p.name.length > 62 ? p.name.slice(0, 62) + "…" : p.name }}</div>
                      <div class="pa-prod-code">{{ p.root_code || p.code }}</div>
                      <div class="pa-prod-meta">{{ p.unit }} · {{ p.unique_buyers }} SOE × {{ p.contract_count }} закупок</div>
                    </td>
                    <td class="r">
                      <b>{{ paFmtMoney(p.avg_price) }}</b>
                      <div class="pa-prod-unit-sub">сум/{{ p.unit }}</div>
                    </td>
                    <td class="rng">
                      <span class="lo">{{ paFmtMoneyShort(p.min_price) }}</span>
                      –
                      <span class="hi">{{ paFmtMoneyShort(p.max_price) }}</span>
                    </td>
                    <td class="r"><b>{{ paFmtMoneyShort(p.total_spend) }}</b></td>
                    <td class="r buyers">{{ p.unique_buyers }} SOE</td>
                    <td class="r vs" :class="spreadCls(p)">{{ spreadTxt(p) }}</td>
                  </tr>
                </tbody>
              </table>
              <div class="pa-acc-foot">
                <template v-if="excludedCount(cat).excluded">
                  {{ coCountFor(cat.id) }}{{ coCountFor(cat.id) === 1 ? " компания" : " компаний" }}
                  · {{ excludedCount(cat).kept }} товаров с benchmark из {{ excludedCount(cat).raw }}
                  (отсечено {{ excludedCount(cat).excluded }}: n_co&lt;2 или n&lt;3)
                  · клик по товару — все покупатели
                </template>
                <template v-else>
                  {{ coCountFor(cat.id) }}{{ coCountFor(cat.id) === 1 ? " компания" : " компаний" }}
                  · {{ excludedCount(cat).kept }} товаров · клик по товару — все покупатели
                </template>
              </div>
            </template>

            <!-- LEGACY MODE: list of closures -->
            <template v-else>
              <table class="pa-acc-tbl">
                <colgroup><col/><col style="width:110px"/><col style="width:90px"/><col/><col style="width:70px"/></colgroup>
                <thead>
                  <tr>
                    <td>Компания</td>
                    <td class="r">Цена</td>
                    <td class="r">Объём</td>
                    <td>Поставщик</td>
                    <td class="r">vs рынок</td>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in detailRowsFor(cat.id)" :key="r.id" @click.stop="$emit('drill-closure', r)">
                    <td>
                      <span class="sec" :style="{ background: r.company_color || '#888780' }" />
                      <span class="nm">{{ r.company_name }}</span>
                    </td>
                    <td class="r px">{{ paFmtMoney(r.unit_price) }}</td>
                    <td class="r vol">{{ fmt.fmtNumber(Number(r.volume)) }}</td>
                    <td class="px sup">{{ r.supplier || "—" }}</td>
                    <td class="r vs" :class="(r.deviation_pct ?? 0) >= 0 ? 'up' : 'dn'">
                      {{ fmt.fmtPercent(r.deviation_pct ?? 0, { decimals: 1, signed: true }) }}
                    </td>
                  </tr>
                </tbody>
              </table>
              <div class="pa-acc-foot">
                {{ coCountFor(cat.id) }}{{ coCountFor(cat.id) === 1 ? " компания" : " компаний" }} · клик по строке — детализация
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.pa-acc { display: flex; flex-direction: column; gap: 4px; }

.pa-acc-row {
  background: var(--bg1, #fff);
  border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 8px;
  overflow: hidden;
  animation: paAccIn .35s var(--ease-standard) backwards;
}
@keyframes paAccIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.pa-acc-row.pa-acc-empty { opacity: .55; }

.pa-acc-head {
  display: grid;
  grid-template-columns: 36px 1fr 130px 200px 80px 24px;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background .15s;
}
.pa-acc-head:hover { background: rgba(127, 119, 221, .04); }
.pa-acc-row.pa-acc-open .pa-acc-head { background: linear-gradient(to right, rgba(127, 119, 221, .06), transparent); }
.pa-acc-head-empty { cursor: default; }
.pa-acc-head-empty:hover { background: transparent; }

.pa-acc-num {
  font-size: 10.5px; font-weight: 600;
  color: rgba(15, 23, 60, .55);
  font-feature-settings: 'tnum';
  text-align: center;
}

.pa-acc-name { font-size: 12px; font-weight: 500; color: var(--t1, #1e2a4a); min-width: 0; }
.pa-acc-name small {
  display: block;
  font-size: 10px; font-weight: 400;
  color: rgba(15, 23, 60, .55);
  margin-top: 2px;
  letter-spacing: .02em;
}

.pa-acc-spread {
  font-size: 10.5px;
  font-feature-settings: 'tnum';
  color: rgba(15, 23, 60, .65);
  text-align: right;
}
.pa-empty-stat { color: rgba(15, 23, 60, .35); font-style: italic; }

.pa-acc-bar {
  position: relative; height: 5px;
  background: rgba(15, 23, 60, .04);
  border-radius: 3px; overflow: hidden;
}
.pa-acc-bar::before {
  content: ""; position: absolute; top: 0; bottom: 0; left: 50%;
  width: 1px; background: rgba(15, 23, 60, .15);
}
.pa-acc-bar-fill {
  position: absolute; top: 0; bottom: 0;
  border-radius: 2px;
  animation: barIn .8s var(--ease-standard) backwards;
  transform-origin: left center;
}
@keyframes barIn { from { transform: scaleX(0); transform-origin: center; } to { transform: scaleX(1); } }

.pa-acc-stat {
  font-size: 11px; font-weight: 600;
  font-feature-settings: 'tnum';
  text-align: right;
}

.pa-acc-chev {
  font-size: 9px;
  color: rgba(15, 23, 60, .35);
  transition: transform .25s var(--ease-standard);
  text-align: center;
}
.pa-acc-chev.open { transform: rotate(180deg); color: #7F77DD; }

.pa-acc-detail {
  max-height: 0; overflow: hidden;
  transition: max-height .35s var(--ease-standard);
}
.pa-acc-detail.open { max-height: 1200px; }
.pa-acc-detail-inner {
  padding: 4px 14px 14px;
  background: linear-gradient(180deg, #FAFAFD 0%, #fff 100%);
}

/* ─── Contracts mode: products table ─── */
.pa-prod-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum';
}
.pa-prod-tbl thead td {
  font-size: 9.5px; font-weight: 600;
  letter-spacing: .07em; text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  white-space: nowrap;
}
.pa-prod-tbl thead td.r { text-align: right; }
.pa-prod-tbl thead td.sortable {
  cursor: pointer; user-select: none;
  transition: color .15s, background .15s;
}
.pa-prod-tbl thead td.sortable:hover { color: var(--t1, #1e2a4a); background: rgba(127, 119, 221, .05); }
.pa-prod-tbl thead td.sortable.on { color: #7F77DD; }
.pa-prod-tbl thead td .arr { font-size: 8px; opacity: .55; margin-left: 3px; }

.pa-prod-row {
  cursor: pointer;
  animation: prodIn .25s ease backwards;
  transition: background .12s;
}
@keyframes prodIn { from { opacity: 0; transform: translateY(2px); } to { opacity: 1; transform: translateY(0); } }
.pa-prod-row:hover td { background: rgba(127, 119, 221, .04); }
.pa-prod-tbl tbody td {
  padding: 7px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: var(--t1, #1e2a4a);
  vertical-align: top;
}
.pa-prod-tbl tbody td.r { text-align: right; }
.pa-prod-tbl tbody td.num { color: rgba(15, 23, 60, .55); font-weight: 600; text-align: center; }
.pa-prod-tbl tbody td.rng { text-align: right; font-size: 10.5px; }
.pa-prod-tbl tbody td.rng .lo { color: #0F6E56; }
.pa-prod-tbl tbody td.rng .hi { color: var(--sev-critical); }
.pa-prod-tbl tbody td.buyers { color: rgba(15, 23, 60, .55); font-weight: 500; }

.pa-prod-nm {
  font-weight: 500; color: var(--t1, #1e2a4a);
  font-size: 11.5px;
}
.pa-prod-code {
  font-size: 9.5px; color: rgba(15, 23, 60, .45);
  font-family: ui-monospace, monospace;
  margin-top: 2px;
}
.pa-prod-meta {
  font-size: 9.5px; color: rgba(15, 23, 60, .55);
  margin-top: 2px;
}
.pa-prod-unit-sub {
  font-size: 9px; color: rgba(15, 23, 60, .45);
  margin-top: 2px;
}

.pa-prod-tbl tbody td.vs {
  font-weight: 600;
}
.pa-prod-tbl tbody td.vs.sp-hi { color: #C53030; }
.pa-prod-tbl tbody td.vs.sp-md { color: #B07415; }
.pa-prod-tbl tbody td.vs.sp-lo { color: #0F6E56; }

/* ─── Legacy mode table ─── */
.pa-acc-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 11px; font-variant-numeric: tabular-nums;
}
.pa-acc-tbl thead td {
  font-size: 9.5px; font-weight: 600;
  letter-spacing: .07em; text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
}
.pa-acc-tbl thead td.r { text-align: right; }
.pa-acc-tbl tbody tr {
  cursor: pointer; transition: background .15s;
}
.pa-acc-tbl tbody tr:hover td { background: rgba(127, 119, 221, .04); }
.pa-acc-tbl tbody td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: var(--t1, #1e2a4a);
}
.pa-acc-tbl tbody td.r { text-align: right; }
.pa-acc-tbl tbody td.up { color: #C53030; font-weight: 600; }
.pa-acc-tbl tbody td.dn { color: #0F6E56; font-weight: 600; }
.pa-acc-tbl tbody td.sup {
  font-style: italic; color: rgba(15, 23, 60, .55);
  max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.sec {
  display: inline-block; width: 4px; height: 14px;
  border-radius: 2px; margin-right: 6px; vertical-align: middle;
}
.nm { vertical-align: middle; font-weight: 500; }

.pa-acc-foot {
  margin-top: 10px;
  padding: 6px 8px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
  font-style: italic;
}

@media (max-width: 900px) {
  .pa-acc-head { grid-template-columns: 28px 1fr 80px 24px; }
  .pa-acc-spread, .pa-acc-bar { display: none; }
}
</style>
