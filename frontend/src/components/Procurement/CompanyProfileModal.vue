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
import PaCategoryDeviationBars from "./PaCategoryDeviationBars.vue";
import PaSpendBreakdown from "./PaSpendBreakdown.vue";

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
// ОБЪЁМ = СОВОКУПНЫЙ расход компании (лот-дедуп, ВСЕ типы) из бэкенда. Это НЕ
// sum_ref (тот = только сопоставимый товарный benchmark для расчёта отклонения).
const totalVol = computed(() => Number(props.company?.company_total_spend ?? 0));
// Сопоставимая база отклонения (товары в полосе) — для пояснения, что +X% считается
// именно по ней, а не по всему объёму.
const comparableRef = computed(() => Number(props.company?.sum_ref ?? 0));

const sortedPurchases = computed(() =>
  [...props.purchases].sort((a, b) => b.deviation_pct - a.deviation_pct),
);

const aiRecommendation = computed(() => {
  if (!props.company) return "";
  // Худшую категорию берём из band-агрегата cat_dev (worst_cats), а НЕ из сырой
  // строки sortedPurchases[0] — иначе в текст попадал мусорный line-level
  // deviation_pct грязной/self-ref позиции (давал «+137345.7%»).
  const w = props.company.worst_cats?.[0];
  return paGenerateCompanyRecommendation(props.company, w ? {
    categoryName: w.category_name || "—",
    deviationPct: Number(w.deviation_pct) || 0,
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

// Категории берём из company.cat_dev (бэкенд band, только товары) — согласовано
// с рейтингом и радаром; клиентский пересчёт по строкам включал бы услуги/грязь.
const categoryStats = computed<CategoryStat[]>(() => {
  if (!props.company) return [];
  return props.categories.map(cat => {
    const d = props.company!.cat_dev.find(x => paSameCat(x.category_id, cat.id));
    const sumRef = d ? Number(d.sum_ref) : 0;
    const devSum = d ? Number(d.sum_dev) : 0;
    return {
      id: cat.id,
      name: cat.name,
      short: cat.short || cat.name,
      closures: d ? d.closure_count : 0,
      sumSpend: sumRef + devSum,
      sumRef,
      devSum,
      devPct: d ? Number(d.deviation_pct) : 0,
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
    // Деньги/Δ% — ТОЛЬКО по сопоставимым товарам (PRODUCT + рыночная медиана +
    // отклонение в полосе ≤1000%). Иначе line-level sum_ref по услугам/грязи
    // раздувал объём в десятки раз и согласованность с вкладкой «Категории»
    // (band, cat_dev) ломалась (баг аудита #4: 84× завышение).
    if (p.is_dirty) continue;
    if (p.product_type !== "PRODUCT") continue;
    if (!(Number(p.market_avg) > 0)) continue;
    if (Math.abs(Number(p.deviation_pct) || 0) > 1000) continue;
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

const accentColor = computed(() => props.company?.company_color || "#7F77DD");

function padCat(id: string | number | null | undefined): string {
  if (id == null || id === "") return "—";
  const n = Number(id);
  if (Number.isNaN(n)) return String(id);
  return n < 10 ? "0" + n : String(n);
}

// Δ% осмысленно только для ТОВАРОВ и сопоставимых кодов: услуги (shartli birlik)
// и «грязные» коды дают аномальные сотни тысяч % — для них показываем «—».
function devComparable(p: ClosureRow): boolean {
  return p.product_type === "PRODUCT" && Math.abs(Number(p.deviation_pct) || 0) <= 1000;
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

    <!-- ─── Tab content (animated switch) ─── -->
    <Transition name="pa-tab" mode="out-in">
    <div :key="activeTab" class="cp2-tab-wrap">
    <!-- ─── Tab: Overview ─── -->
    <div v-if="activeTab === 'overview'" class="cp2-tab-overview">
      <!-- Совокупный объём + разбивка товары/услуги/работы -->
      <PaSpendBreakdown
        :total="totalVol"
        :goods="Number(company.goods_spend)"
        :services="Number(company.services_spend)"
        :works="Number(company.works_spend)"
        :lots="company.total_lots"
      />

      <!-- AI recommendation -->
      <div class="cp2-rec uza-side-stripe" v-html="aiRecommendation" />

      <!-- Отклонение по категориям — дивержентные бары (заменили radar) -->
      <div class="cp2-dev-section">
        <div class="cp2-sec-h">
          Отклонение цен по категориям
          <span class="cp2-sec-note">по сопоставимым товарам · база {{ paFmtMoneyShort(comparableRef) }} сум</span>
        </div>
        <PaCategoryDeviationBars :cats="company.cat_dev" />
      </div>
    </div>

    <!-- ─── Tab: Categories ─── -->
    <div v-else-if="activeTab === 'categories'" class="cp2-tab-table">
      <table class="cp2-tbl pa-stagger">
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
      <table class="cp2-tbl pa-stagger">
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
      <table class="cp2-tbl pa-stagger">
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
            <td class="right" :class="devComparable(p) ? (p.deviation_pct >= 0 ? 'neg' : 'pos') : 'neu'"
                :title="devComparable(p) ? '' : 'Услуга/работа или несопоставимый код — отклонение по цене за единицу неинформативно'">
              <template v-if="devComparable(p)">{{ fmt.fmtPercent(p.deviation_pct, { decimals: 1, signed: true }) }}</template>
              <template v-else>—</template>
            </td>
          </tr>
          <tr v-if="!sortedPurchases.length"><td colspan="7" class="pms-empty">Нет закупок</td></tr>
        </tbody>
      </table>
    </div>
    </div>
    </Transition>
  </PaModalShell>
</template>

<style scoped>
/* Wrapper для анимированного переключения вкладок — наследует flex-растяжку */
.cp2-tab-wrap {
  display: flex; flex-direction: column;
  flex: 1; min-height: 0;
}

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
  color: var(--t1, #1E2A4A);
  line-height: 1.55;
  position: relative; overflow: hidden;
  --stripe-color: var(--accent, #7F77DD);
}
.cp2-rec :deep(b) { font-weight: 600; }

.cp2-dev-section { display: flex; flex-direction: column; gap: 10px; }
.cp2-sec-h {
  font-size: 10.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap;
}
.cp2-sec-note {
  font-size: 9.5px; font-weight: 500; letter-spacing: .02em;
  text-transform: none; color: rgba(15, 23, 60, .42);
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
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  padding: 10px 14px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky; top: 0; z-index: 1;
  white-space: nowrap;
}
.cp2-tbl thead th.right { text-align: right; }
.cp2-tbl thead th.left { text-align: left; }

.cp2-tbl tbody td {
  padding: 9px 14px;
  border-bottom: 0.5px solid rgba(15, 23, 60, .05);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.cp2-tbl tbody td.right { text-align: right; }
.cp2-tbl tbody td.left { text-align: left; }
.cp2-tbl tbody td.neu { color: rgba(15, 23, 60, .55); font-weight: 400; }
.cp2-tbl tbody td.pos { color: var(--green); font-weight: 600; }
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
.cp2-unit { font-size: 10.5px; color: var(--t3, var(--t-muted)); font-weight: 400; }

/* премиум: мягкая подсветка строк при наведении */
.cp2-tbl tbody tr { transition: background .15s ease; }
.cp2-tbl tbody tr:not(.cp2-row-clickable):hover td { background: rgba(127, 119, 221, .035); }

.cp2-row-clickable { cursor: pointer; transition: background .15s ease, box-shadow .15s ease; }
.cp2-row-clickable td { transition: background .15s ease, transform .15s cubic-bezier(.22, 1, .36, 1); }
.cp2-row-clickable:hover td { background: rgba(127, 119, 221, .06); }
.cp2-row-clickable:hover td:first-child { transform: translateX(2px); }

@media (prefers-reduced-motion: reduce) {
  .cp2-radar-poly, .cp2-radar-dot { animation: none !important; opacity: 1 !important; }
  .cp2-tbl tbody tr, .cp2-row-clickable, .cp2-row-clickable td { transition: none; }
  .cp2-row-clickable:hover td:first-child { transform: none; }
}
</style>
