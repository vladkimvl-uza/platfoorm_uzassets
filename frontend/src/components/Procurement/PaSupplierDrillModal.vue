<script setup lang="ts">
/**
 * PaSupplierDrillModal — Drill-down for a supplier in PaSupplierAudit.
 *
 * Filters all purchases by normalized supplier key (matches PaSupplierAudit's
 * grouping). Shows:
 *   • Stats: contracts · overcharge · avg deviation · SOE-buyers · categories
 *   • Tabs:
 *       - Покупатели  → SOE breakdown (which companies bought, sumOverpay)
 *       - Категории   → category breakdown (which cats, sumOverpay)
 *       - Закупки     → full purchase list (clickable → drill)
 */
import { computed, ref } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  type CategoryMeta,
  type ClosureRow,
  type CompanyRatingRow,
} from "@/api/procurement_analysis";
import { useFormatters } from "@/composables/useFormatters";
import PaModalShell from "./PaModalShell.vue";

const fmt = useFormatters();

const props = defineProps<{
  /** Normalized supplier key (from PaSupplierAudit.normalize()) — used to
   *  match purchases.supplier via the same normalization. */
  supplierKey: string;
  /** Display name (most-common spelling). */
  supplierName: string;
  /** All purchases of the current aggregate (will be filtered client-side). */
  purchases: ClosureRow[];
  /** All companies for SOE-name lookup. */
  companies: CompanyRatingRow[];
  /** Categories metadata for label lookup. */
  categories: CategoryMeta[];
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "drill-closure", closure: ClosureRow): void;
  (e: "select-company", companyId: string): void;
}>();

// ─── Same normalize() as PaSupplierAudit ───────────────────────
function normalize(name: string): string {
  if (!name || name === "—") return "";
  let s = name.toLowerCase();
  s = s.replace(/[«»"'""()[\]]/g, " ");
  s = s.replace(
    /\b(ооо|ао|оао|зао|пао|ип|чп|тоо|llc|ltd|mchj|mch|aj|aksiyadorlik|jamiyat|мчж|оаж|aksdor|ятт|yatt|mchk|sp|sho|fuqarolar|ip)\b/g,
    " ",
  );
  s = s.replace(/[\s\-,.]+/g, " ").trim();
  return s || name.toLowerCase().trim();
}

// ─── Active tab ───────────────────────────────────────────────
type Tab = "buyers" | "categories" | "purchases";
const activeTab = ref<Tab>("buyers");

// ─── Filtered purchases for this supplier ─────────────────────
const supplierPurchases = computed<ClosureRow[]>(() => {
  return props.purchases.filter(p => {
    if (p.is_dirty) return false;
    if (!p.supplier || p.supplier === "—") return false;
    return normalize(p.supplier) === normalize(props.supplierKey);
  });
});

// ─── Stats ────────────────────────────────────────────────────
const sumSpend = computed(() =>
  supplierPurchases.value.reduce((s, p) => s + p.unit_price * p.volume, 0),
);
const sumRef = computed(() =>
  supplierPurchases.value.reduce((s, p) => s + p.market_avg * p.volume, 0),
);
const sumOverpay = computed(() => {
  let acc = 0;
  for (const p of supplierPurchases.value) {
    const spend = p.unit_price * p.volume;
    const ref = p.market_avg * p.volume;
    if (spend > ref) acc += (spend - ref);
  }
  return acc;
});
const sumDev = computed(() => sumSpend.value - sumRef.value);
const devPct = computed(() => sumRef.value > 0 ? (sumDev.value / sumRef.value) * 100 : 0);

const buyersMap = computed(() => {
  const m = new Map<string, {
    companyId: string;
    name: string;
    color: string | null;
    sumSpend: number;
    sumRef: number;
    sumOverpay: number;
    closures: number;
  }>();
  for (const p of supplierPurchases.value) {
    let s = m.get(p.company_id);
    if (!s) {
      const co = props.companies.find(c => c.company_id === p.company_id);
      s = {
        companyId: p.company_id,
        name: co?.company_name || "—",
        color: co?.company_color || null,
        sumSpend: 0, sumRef: 0, sumOverpay: 0, closures: 0,
      };
      m.set(p.company_id, s);
    }
    const spend = p.unit_price * p.volume;
    const ref = p.market_avg * p.volume;
    s.sumSpend += spend;
    s.sumRef += ref;
    s.closures++;
    if (spend > ref) s.sumOverpay += (spend - ref);
  }
  return Array.from(m.values()).sort((a, b) => b.sumOverpay - a.sumOverpay);
});

const categoryStats = computed(() => {
  const m = new Map<string | number, {
    id: string | number;
    name: string;
    closures: number;
    sumSpend: number;
    sumRef: number;
    sumOverpay: number;
  }>();
  for (const p of supplierPurchases.value) {
    const key = p.category_id ?? "—";
    let s = m.get(key);
    if (!s) {
      s = { id: key, name: p.category_name || "—", closures: 0, sumSpend: 0, sumRef: 0, sumOverpay: 0 };
      m.set(key, s);
    }
    const spend = p.unit_price * p.volume;
    const ref = p.market_avg * p.volume;
    s.closures++;
    s.sumSpend += spend;
    s.sumRef += ref;
    if (spend > ref) s.sumOverpay += (spend - ref);
  }
  return Array.from(m.values()).sort((a, b) => b.sumOverpay - a.sumOverpay);
});

const buyersCount = computed(() => buyersMap.value.length);
const catsCount = computed(() => categoryStats.value.length);

const sortedPurchases = computed(() =>
  [...supplierPurchases.value].sort((a, b) => b.deviation_pct - a.deviation_pct),
);

function padCat(id: string | number | null | undefined): string {
  if (id == null || id === "") return "—";
  const n = Number(id);
  if (Number.isNaN(n)) return String(id);
  return n < 10 ? "0" + n : String(n);
}

// Accent severity-color based on deviation
const accentColor = computed(() => {
  if (devPct.value >= 50) return "#E24B4A";
  if (devPct.value >= 25) return "#EF9F27";
  if (devPct.value >= 10) return "#D97706";
  return "#7F77DD";
});
</script>

<template>
  <PaModalShell
    kind="Поставщик"
    :title="supplierName"
    :accent="accentColor"
    max-width="1080px"
    @close="emit('close')"
  >
    <!-- ─── Stats ─── -->
    <template #stats>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Контрактов</div>
        <div class="pms-stat-val">{{ supplierPurchases.length }}</div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Объём</div>
        <div class="pms-stat-val">{{ paFmtMoneyShort(sumSpend) }}<small>сум</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Median рынка</div>
        <div class="pms-stat-val">{{ paFmtMoneyShort(sumRef) }}<small>сум</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Переплата</div>
        <div class="pms-stat-val neg">+{{ paFmtMoneyShort(sumOverpay) }}<small>сум</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Откл.</div>
        <div class="pms-stat-val" :class="devPct >= 10 ? 'neg' : devPct >= 0 ? 'warn' : 'pos'">
          {{ devPct >= 0 ? '+' : '' }}{{ devPct.toFixed(1) }}<small>%</small>
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">SOE-клиентов</div>
        <div class="pms-stat-val">{{ buyersCount }}</div>
      </div>
    </template>

    <!-- ─── Tabs ─── -->
    <template #tabs>
      <button class="pms-tab" :class="{ active: activeTab === 'buyers' }" @click="activeTab = 'buyers'">
        Покупатели<span class="pms-tab-count">{{ buyersCount }}</span>
      </button>
      <button class="pms-tab" :class="{ active: activeTab === 'categories' }" @click="activeTab = 'categories'">
        Категории<span class="pms-tab-count">{{ catsCount }}</span>
      </button>
      <button class="pms-tab" :class="{ active: activeTab === 'purchases' }" @click="activeTab = 'purchases'">
        Закупки<span class="pms-tab-count">{{ supplierPurchases.length }}</span>
      </button>
    </template>

    <!-- ─── Tab: Buyers (SOE breakdown) ─── -->
    <div v-if="activeTab === 'buyers'" class="psd-tab-table">
      <table class="psd-tbl">
        <thead>
          <tr>
            <th class="left">SOE-клиент</th>
            <th class="right">Закупок</th>
            <th class="right">Объём</th>
            <th class="right">Median рынка</th>
            <th class="right">Переплата</th>
            <th class="right">{{ 'Δ %' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in buyersMap" :key="b.companyId"
              class="psd-row-clickable"
              @click="emit('select-company', b.companyId); emit('close')"
              :title="`Открыть профиль ${b.name}`">
            <td class="left">
              <span class="psd-co-dot" :style="{ background: b.color || '#888' }"></span>
              {{ b.name }}
            </td>
            <td class="right">{{ b.closures }}</td>
            <td class="right">{{ paFmtMoneyShort(b.sumSpend) }}</td>
            <td class="right neu">{{ paFmtMoneyShort(b.sumRef) }}</td>
            <td class="right" :class="b.sumOverpay > 0 ? 'neg' : 'pos'">
              +{{ paFmtMoneyShort(b.sumOverpay) }}
            </td>
            <td class="right" :class="(b.sumRef > 0 ? ((b.sumSpend - b.sumRef) / b.sumRef) * 100 : 0) >= 0 ? 'neg' : 'pos'">
              {{ b.sumRef > 0 ? (((b.sumSpend - b.sumRef) / b.sumRef) * 100).toFixed(1) : '0' }}%
            </td>
          </tr>
          <tr v-if="!buyersMap.length"><td colspan="6" class="pms-empty">Нет SOE-клиентов</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Tab: Categories ─── -->
    <div v-else-if="activeTab === 'categories'" class="psd-tab-table">
      <table class="psd-tbl">
        <thead>
          <tr>
            <th class="left">№</th>
            <th class="left">Категория</th>
            <th class="right">Закупок</th>
            <th class="right">Объём</th>
            <th class="right">Median рынка</th>
            <th class="right">Переплата</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in categoryStats" :key="c.id">
            <td class="left psd-num">{{ padCat(c.id) }}</td>
            <td class="left">{{ c.name }}</td>
            <td class="right">{{ c.closures }}</td>
            <td class="right">{{ paFmtMoneyShort(c.sumSpend) }}</td>
            <td class="right neu">{{ paFmtMoneyShort(c.sumRef) }}</td>
            <td class="right" :class="c.sumOverpay > 0 ? 'neg' : 'pos'">
              +{{ paFmtMoneyShort(c.sumOverpay) }}
            </td>
          </tr>
          <tr v-if="!categoryStats.length"><td colspan="6" class="pms-empty">Нет категорий</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ─── Tab: Purchases ─── -->
    <div v-else-if="activeTab === 'purchases'" class="psd-tab-table">
      <table class="psd-tbl">
        <thead>
          <tr>
            <th class="left">Категория</th>
            <th class="left">SOE</th>
            <th class="right">Цена</th>
            <th class="right">Median</th>
            <th class="right">Объём</th>
            <th class="right">{{ 'Δ %' }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in sortedPurchases" :key="p.id"
              class="psd-row-clickable"
              @click="emit('drill-closure', p)"
              title="Подробнее о закупке">
            <td class="left">
              <span class="psd-num">{{ padCat(p.category_id) }}</span>
              {{ p.category_name }}
            </td>
            <td class="left">
              {{ companies.find(c => c.company_id === p.company_id)?.company_name || '—' }}
            </td>
            <td class="right">{{ paFmtMoney(p.unit_price) }}</td>
            <td class="right neu">{{ paFmtMoney(p.market_avg) }}</td>
            <td class="right">{{ fmt.fmtNumber(Number(p.volume)) }}</td>
            <td class="right" :class="p.deviation_pct >= 0 ? 'neg' : 'pos'">
              {{ fmt.fmtPercent(p.deviation_pct, { decimals: 1, signed: true }) }}
            </td>
          </tr>
          <tr v-if="!sortedPurchases.length"><td colspan="6" class="pms-empty">Нет закупок</td></tr>
        </tbody>
      </table>
    </div>
  </PaModalShell>
</template>

<style scoped>
.psd-tab-table {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.psd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.psd-tbl thead th {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  padding: 10px 14px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky; top: 0; z-index: 1;
  white-space: nowrap;
}
.psd-tbl thead th.right { text-align: right; }
.psd-tbl thead th.left { text-align: left; }

.psd-tbl tbody td {
  padding: 9px 14px;
  border-bottom: 0.5px solid rgba(15, 23, 60, .05);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.psd-tbl tbody td.right { text-align: right; }
.psd-tbl tbody td.left { text-align: left; }
.psd-tbl tbody td.neu { color: rgba(15, 23, 60, .55); font-weight: 400; }
.psd-tbl tbody td.pos { color: var(--green); font-weight: 600; }
.psd-tbl tbody td.neg { color: #C53030; font-weight: 600; }

.psd-num {
  display: inline-block;
  font-weight: 700; color: #7F77DD;
  font-size: 11px;
  margin-right: 6px;
}
.psd-co-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  margin-right: 7px;
  vertical-align: middle;
}

.psd-row-clickable { cursor: pointer; transition: background .12s; }
.psd-row-clickable:hover td { background: rgba(127, 119, 221, .05); }
</style>
