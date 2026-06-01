<script setup lang="ts">
/**
 * CompanyProfileModal — Profile of a single SOE in /procurement-analysis.
 *
 * v2 rewrite 2026-05-26: built on PaModalShell with tabbed layout.
 *
 *   Tabs:
 *     • Обзор       — KPI grid + AI rec + radar (15 categories)
 *     • Категории   — table of all 15 categories with deviation
 *     • Поставщики  — supplier breakdown (this company × suppliers)
 *     • Закупки     — full purchases list (sortable, clickable)
 */
import { computed, ref } from "vue";
import {
  paColorByDev,
  paFmtMoney,
  paSameCat,
  paFmtMoneyShort,
  type CategoryMeta,
  type ClosureRow,
  type CompanyRatingRow,
} from "@/api/procurement_analysis";
import { paGenerateCompanyRecommendation } from "@/composables/usePaRecommendation";
import { useFormatters } from "@/composables/useFormatters";
import PaModalShell from "./PaModalShell.vue";

const fmt = useFormatters();

const props = defineProps<{
  company: CompanyRatingRow | null;
  categories: CategoryMeta[];
  purchases: ClosureRow[];
  totalCompanies: number;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "drill-closure", closure: ClosureRow): void;
}>();

// ─── Active tab ──────────────────────────────────────────────────
type Tab = "overview" | "categories" | "suppliers" | "purchases";
const activeTab = ref<Tab>("overview");

// ─── Computed metrics ────────────────────────────────────────────
const rank = computed(() => props.company?.rank ?? 0);
const overpay = computed(() => Math.max(0, props.company?.sum_dev ?? 0));
const savings = computed(() => Math.max(0, -(props.company?.sum_dev ?? 0)));
const totalVol = computed(() =>
  props.purchases.reduce((s, p) => s + Number(p.volume) * Number(p.market_avg), 0),
);

const sortedPurchases = computed(() =>
  [...props.purchases].sort((a, b) => b.deviation_pct - a.deviation_pct),
);

const aiRecommendation = computed(() => {
  if (!props.company) return "";
  const worst = sortedPurchases.value[0];
  return paGenerateCompanyRecommendation(props.company, worst ? {
    categoryName: worst.category_name,
    deviationPct: worst.deviation_pct,
  } : null);
});

// ─── Category breakdown ──────────────────────────────────────────
interface CategoryStat {
  id: string | number;
  name: string;
  short: string;
  closures: number;
  sumSpend: number;
  sumRef: number;
  devSum: number;
  devPct: number;
}

const categoryStats = computed<CategoryStat[]>(() => {
  if (!props.company) return [];
  return props.categories.map(cat => {
    const rows = props.purchases.filter(p => paSameCat(p.category_id, cat.id));
    const sumSpend = rows.reduce((s, p) => s + p.unit_price * p.volume, 0);
    const sumRef = rows.reduce((s, p) => s + p.market_avg * p.volume, 0);
    const devSum = sumSpend - sumRef;
    return {
      id: cat.id,
      name: cat.name,
      short: cat.short || cat.name,
      closures: rows.length,
      sumSpend,
      sumRef,
      devSum,
      devPct: sumRef > 0 ? (devSum / sumRef) * 100 : 0,
    };
  }).filter(c => c.closures > 0)
    .sort((a, b) => b.devPct - a.devPct);
});

// ─── Supplier breakdown ─────────────────────────────────────────
interface SupplierStat {
  name: string;
  closures: number;
  sumSpend: number;
  sumRef: number;
  devSum: number;
  devPct: number;
  categories: number;
}

const supplierStats = computed<SupplierStat[]>(() => {
  const map = new Map<string, { sumSpend: number; sumRef: number; closures: number; cats: Set<string | number> }>();
  for (const p of props.purchases) {
    if (!p.supplier || p.supplier === "—") continue;
    const key = p.supplier;
    let s = map.get(key);
    if (!s) { s = { sumSpend: 0, sumRef: 0, closures: 0, cats: new Set() }; map.set(key, s); }
    s.sumSpend += p.unit_price * p.volume;
    s.sumRef   += p.market_avg * p.volume;
    s.closures++;
    if (p.category_id != null) s.cats.add(p.category_id);
  }
  return Array.from(map.entries()).map(([name, s]) => ({
    name,
    closures: s.closures,
    sumSpend: s.sumSpend,
    sumRef: s.sumRef,
    devSum: s.sumSpend - s.sumRef,
    devPct: s.sumRef > 0 ? ((s.sumSpend - s.sumRef) / s.sumRef) * 100 : 0,
    categories: s.cats.size,
  })).sort((a, b) => b.devSum - a.devSum);
});

// ─── Radar chart math (for Overview tab) ─────────────────────────
const radarSize = 320;
const radarCx = radarSize / 2;
const radarCy = radarSize / 2;
const radarR = 115;

function angleFor(i: number): number {
  return -Math.PI / 2 + (i / props.categories.length) * 2 * Math.PI;
}
function textAnchor(i: number): "start" | "middle" | "end" {
  const a = angleFor(i);
  const x = Math.cos(a);
  if (x > 0.3) return "start";
  if (x < -0.3) return "end";
  return "middle";
}

const radarDataPoints = computed(() => {
  if (!props.company) return [];
  return props.categories.map((cat, i) => {
    const d = props.company!.cat_dev.find((x) => paSameCat(x.category_id, cat.id));
    const devPct = d && d.sum_ref > 0 ? (d.sum_dev / d.sum_ref) * 100 : 0;
    const ratio = Math.min(1, Math.abs(devPct) / 20);
    const r = ratio * radarR;
    const a = angleFor(i);
    return {
      x: radarCx + Math.cos(a) * r,
      y: radarCy + Math.sin(a) * r,
      devPct,
      catId: cat.id,
    };
  });
});

const radarPoints = computed(() =>
  radarDataPoints.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
);

const accentColor = computed(() => props.company?.company_color || "#7F77DD");

function padCat(id: string | number | null | undefined): string {
  if (id == null || id === "") return "—";
  const n = Number(id);
  if (Number.isNaN(n)) return String(id);
  return n < 10 ? "0" + n : String(n);
}
</script>

<template>
  <PaModalShell
    v-if="company"
    kind="Компания"
    :title="company.company_name"
    :accent="accentColor"
    max-width="1100px"
    @close="emit('close')"
  >
    <!-- ─── Stats strip ─── -->
    <template #stats>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Ранг</div>
        <div class="pms-stat-val">#{{ rank }}<small>из {{ totalCompanies }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Средн. отклонение</div>
        <div class="pms-stat-val" :class="(company.company_deviation ?? 0) >= 0 ? 'neg' : 'pos'">
          {{ fmt.fmtNumber(company.company_deviation, { decimals: 1, signed: true }) }}<small>%</small>
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ overpay > 0 ? 'Переплата' : 'Экономия' }}</div>
        <div class="pms-stat-val" :class="overpay > 0 ? 'neg' : 'pos'">
          {{ paFmtMoneyShort(overpay > 0 ? overpay : savings) }}<small>сум</small>
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Объём</div>
        <div class="pms-stat-val">{{ paFmtMoneyShort(totalVol) }}<small>сум</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Категорий</div>
        <div class="pms-stat-val">{{ categoryStats.length }}</div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Закупок</div>
        <div class="pms-stat-val">{{ purchases.length }}</div>
      </div>
    </template>

    <!-- ─── Tabs ─── -->
    <template #tabs>
      <button class="pms-tab" :class="{ active: activeTab === 'overview' }" @click="activeTab = 'overview'">Обзор</button>
      <button class="pms-tab" :class="{ active: activeTab === 'categories' }" @click="activeTab = 'categories'">
        Категории<span class="pms-tab-count">{{ categoryStats.length }}</span>
      </button>
      <button class="pms-tab" :class="{ active: activeTab === 'suppliers' }" @click="activeTab = 'suppliers'">
        Поставщики<span class="pms-tab-count">{{ supplierStats.length }}</span>
      </button>
      <button class="pms-tab" :class="{ active: activeTab === 'purchases' }" @click="activeTab = 'purchases'">
        Закупки<span class="pms-tab-count">{{ purchases.length }}</span>
      </button>
    </template>

    <!-- ─── Tab: Overview ─── -->
    <div v-if="activeTab === 'overview'" class="cp2-tab-overview">
      <!-- AI recommendation -->
      <div class="cp2-rec uza-side-stripe" v-html="aiRecommendation" />

      <!-- Radar -->
      <div class="cp2-radar-section">
        <div class="cp2-sec-h">Отклонение по 15 категориям</div>
        <div class="cp2-radar-wrap">
          <svg :viewBox="`0 0 ${radarSize} ${radarSize}`" preserveAspectRatio="xMidYMid meet" class="cp2-radar">
            <circle v-for="r in [0.25, 0.5, 0.75, 1]" :key="r"
                    :cx="radarCx" :cy="radarCy" :r="radarR * r"
                    fill="none" stroke="rgba(15, 23, 60, .08)" stroke-width="0.5" />
            <circle :cx="radarCx" :cy="radarCy" r="2" fill="rgba(15, 23, 60, .25)" />
            <line v-for="(c, i) in categories" :key="`ax-${i}`"
                  :x1="radarCx" :y1="radarCy"
                  :x2="radarCx + Math.cos(angleFor(i)) * radarR"
                  :y2="radarCy + Math.sin(angleFor(i)) * radarR"
                  stroke="rgba(15, 23, 60, .08)" stroke-width="0.5" />
            <polygon
              :points="radarPoints"
              :fill="accentColor + '24'"
              :stroke="accentColor"
              stroke-width="1.5"
              stroke-linejoin="round"
              class="cp2-radar-poly"
            />
            <g v-for="(p, i) in radarDataPoints" :key="`p-${i}`">
              <circle :cx="p.x" :cy="p.y" r="3.5"
                      :fill="paColorByDev(p.devPct)"
                      :stroke="accentColor"
                      stroke-width="1.2"
                      class="cp2-radar-dot"
                      :style="{ '--rd-d': `${i * 50 + 200}ms` }" />
            </g>
            <text v-for="(c, i) in categories" :key="`lbl-${i}`"
                  :x="radarCx + Math.cos(angleFor(i)) * (radarR + 14)"
                  :y="radarCy + Math.sin(angleFor(i)) * (radarR + 14) + 3"
                  :text-anchor="textAnchor(i)"
                  font-size="9.5" font-weight="500"
                  fill="rgba(15, 23, 60, .65)">{{ c.short }}</text>
          </svg>
        </div>
      </div>
    </div>

    <!-- ─── Tab: Categories ─── -->
    <div v-else-if="activeTab === 'categories'" class="cp2-tab-table">
      <table class="cp2-tbl">
        <thead>
          <tr>
            <th class="left">№</th>
            <th class="left">Категория</th>
            <th class="right">Закупок</th>
            <th class="right">Объём (сум)</th>
            <th class="right">Median рынка</th>
            <th class="right">{{ 'Δ сумма' }}</th>
            <th class="right">{{ 'Δ %' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in categoryStats" :key="c.id">
            <td class="left cp2-num">{{ padCat(c.id) }}</td>
            <td class="left">{{ c.name }}</td>
            <td class="right">{{ c.closures }}</td>
            <td class="right">{{ paFmtMoneyShort(c.sumSpend) }}</td>
            <td class="right neu">{{ paFmtMoneyShort(c.sumRef) }}</td>
            <td class="right" :class="c.devSum >= 0 ? 'neg' : 'pos'">
              {{ c.devSum >= 0 ? '+' : '' }}{{ paFmtMoneyShort(c.devSum) }}
            </td>
            <td class="right" :class="c.devPct >= 0 ? 'neg' : 'pos'">
              {{ fmt.fmtPercent(c.devPct, { decimals: 1, signed: true }) }}
            </td>
          </tr>
          <tr v-if="!categoryStats.length"><td colspan="7" class="pms-empty">Нет данных</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Tab: Suppliers ─── -->
    <div v-else-if="activeTab === 'suppliers'" class="cp2-tab-table">
      <table class="cp2-tbl">
        <thead>
          <tr>
            <th class="left">Поставщик</th>
            <th class="right">Закупок</th>
            <th class="right">Категорий</th>
            <th class="right">Объём</th>
            <th class="right">Median рынка</th>
            <th class="right">{{ 'Δ сумма' }}</th>
            <th class="right">{{ 'Δ %' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in supplierStats" :key="s.name">
            <td class="left cp2-supplier">{{ s.name }}</td>
            <td class="right">{{ s.closures }}</td>
            <td class="right">{{ s.categories }}</td>
            <td class="right">{{ paFmtMoneyShort(s.sumSpend) }}</td>
            <td class="right neu">{{ paFmtMoneyShort(s.sumRef) }}</td>
            <td class="right" :class="s.devSum >= 0 ? 'neg' : 'pos'">
              {{ s.devSum >= 0 ? '+' : '' }}{{ paFmtMoneyShort(s.devSum) }}
            </td>
            <td class="right" :class="s.devPct >= 0 ? 'neg' : 'pos'">
              {{ fmt.fmtPercent(s.devPct, { decimals: 1, signed: true }) }}
            </td>
          </tr>
          <tr v-if="!supplierStats.length"><td colspan="7" class="pms-empty">Нет поставщиков</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Tab: Purchases ─── -->
    <div v-else-if="activeTab === 'purchases'" class="cp2-tab-table">
      <table class="cp2-tbl">
        <thead>
          <tr>
            <th class="left">№</th>
            <th class="left">Категория</th>
            <th class="left">Поставщик</th>
            <th class="right">Цена / ед.</th>
            <th class="right">Median</th>
            <th class="right">Объём</th>
            <th class="right">{{ 'Δ %' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in sortedPurchases" :key="p.id"
              class="cp2-row-clickable"
              @click="emit('drill-closure', p)"
              title="Подробнее о закупке">
            <td class="left cp2-num">{{ padCat(p.category_id) }}</td>
            <td class="left">{{ p.category_name }}</td>
            <td class="left cp2-supplier">{{ p.supplier || '—' }}</td>
            <td class="right">{{ paFmtMoney(p.unit_price) }}<span class="cp2-unit"> / {{ p.category_unit || 'ед' }}</span></td>
            <td class="right neu">{{ paFmtMoney(p.market_avg) }}</td>
            <td class="right">{{ fmt.fmtNumber(Number(p.volume)) }}</td>
            <td class="right" :class="p.deviation_pct >= 0 ? 'neg' : 'pos'">
              {{ fmt.fmtPercent(p.deviation_pct, { decimals: 1, signed: true }) }}
            </td>
          </tr>
          <tr v-if="!sortedPurchases.length"><td colspan="7" class="pms-empty">Нет закупок</td></tr>
        </tbody>
      </table>
    </div>
  </PaModalShell>
</template>

<style scoped>
/* ─── Tab: Overview ─── */
.cp2-tab-overview {
  padding: 18px 22px 22px;
  display: flex; flex-direction: column; gap: 18px;
}
.cp2-rec {
  background: linear-gradient(135deg, rgba(127, 119, 221, .06) 0%, rgba(29, 158, 117, .04) 100%);
  border-radius: 10px;
  padding: 14px 18px 14px 20px;
  font-size: 12.5px;
  color: #1E2A4A;
  line-height: 1.55;
  position: relative; overflow: hidden;
  --stripe-color: var(--accent, #7F77DD);
}
.cp2-rec :deep(b) { font-weight: 600; }

.cp2-radar-section { display: flex; flex-direction: column; gap: 10px; }
.cp2-sec-h {
  font-size: 10.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: #888780;
}
.cp2-radar-wrap { display: flex; justify-content: center; }
.cp2-radar { width: 100%; max-width: 380px; height: auto; }
.cp2-radar-poly {
  animation: cp2PolyIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) backwards;
}
@keyframes cp2PolyIn {
  from { opacity: 0; transform: scale(.7); transform-origin: center; }
  to   { opacity: 1; transform: scale(1); }
}
.cp2-radar-dot {
  opacity: 0;
  animation: cp2DotIn .35s cubic-bezier(0.34, 1.2, 0.64, 1) forwards;
  animation-delay: var(--rd-d, 0ms);
}
@keyframes cp2DotIn {
  from { opacity: 0; transform: scale(.4); }
  to   { opacity: 1; transform: scale(1); }
}

/* ─── Tab: Tables (Categories / Suppliers / Purchases) ─── */
.cp2-tab-table {
  padding: 0;
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.cp2-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.cp2-tbl thead th {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: #888780;
  padding: 10px 14px;
  background: #FAFAFC;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky; top: 0; z-index: 1;
  white-space: nowrap;
}
.cp2-tbl thead th.right { text-align: right; }
.cp2-tbl thead th.left { text-align: left; }

.cp2-tbl tbody td {
  padding: 9px 14px;
  border-bottom: 0.5px solid rgba(15, 23, 60, .05);
  color: #1E2A4A;
  font-weight: 500;
}
.cp2-tbl tbody td.right { text-align: right; }
.cp2-tbl tbody td.left { text-align: left; }
.cp2-tbl tbody td.neu { color: rgba(15, 23, 60, .55); font-weight: 400; }
.cp2-tbl tbody td.pos { color: #1D9E75; font-weight: 600; }
.cp2-tbl tbody td.neg { color: #C53030; font-weight: 600; }

.cp2-num {
  display: inline-block;
  font-weight: 700; color: #7F77DD;
  font-size: 11px;
}
.cp2-supplier {
  color: rgba(15, 23, 60, .75);
  font-weight: 500;
  max-width: 240px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cp2-unit { font-size: 10.5px; color: #888780; font-weight: 400; }

.cp2-row-clickable { cursor: pointer; transition: background .12s; }
.cp2-row-clickable:hover td { background: rgba(127, 119, 221, .05); }
</style>
