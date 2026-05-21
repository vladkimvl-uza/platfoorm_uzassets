<template>
  <CpDrillModal
    v-if="company"
    :title="company.company_name"
    :subtitle="`Ранг #${rank} из ${totalCompanies} · ${company.cat_count} категорий`"
    :accent="company.company_color || '#7F77DD'"
    size="xl"
    @close="$emit('close')"
  >
    <!-- Custom hero: 4 KPIs row -->
    <template #hero>
      <div class="pco-mk-row">
        <div class="pco-mk">
          <div class="pco-mk-l">Ранг рейтинга</div>
          <div class="pco-mk-v">#{{ rank }}<small>/ {{ totalCompanies }}</small></div>
        </div>
        <div class="pco-mk">
          <div class="pco-mk-l">Среднее отклонение</div>
          <div class="pco-mk-v" :class="dirClass">
            {{ fmt.fmtNumber(company.company_deviation, { decimals: 1, signed: true }) }}<small>%</small>
          </div>
        </div>
        <div class="pco-mk">
          <div class="pco-mk-l">{{ overpay > 0 ? "Переплата" : "Экономия" }}</div>
          <div class="pco-mk-v" :class="dirClass">
            {{ paFmtMoneyShort(Math.abs(company.sum_dev)) }}<small>сум</small>
          </div>
        </div>
        <div class="pco-mk">
          <div class="pco-mk-l">Объём закупок</div>
          <div class="pco-mk-v">{{ paFmtMoneyShort(totalVol) }}<small>сум</small></div>
        </div>
      </div>
    </template>

    <!-- AI Recommendation -->
    <div class="pco-rec" v-html="aiRecommendation" />

    <!-- Radar chart by 15 categories -->
    <div class="pco-section">
      <div class="pco-section-h">Отклонение по 15 категориям</div>
      <div class="pco-radar-wrap">
        <svg :viewBox="`0 0 ${radarSize} ${radarSize}`" preserveAspectRatio="xMidYMid meet" class="pco-radar">
          <!-- Grid circles -->
          <circle v-for="r in [0.25, 0.5, 0.75, 1]" :key="r" :cx="radarCx" :cy="radarCy" :r="radarR * r" fill="none" stroke="rgba(15, 23, 60, .08)" stroke-width="0.5" />

          <!-- Center mark -->
          <circle :cx="radarCx" :cy="radarCy" r="2" fill="rgba(15, 23, 60, .25)" />

          <!-- Axes -->
          <line v-for="(c, i) in categories" :key="`ax-${i}`"
                :x1="radarCx" :y1="radarCy"
                :x2="radarCx + Math.cos(angleFor(i)) * radarR"
                :y2="radarCy + Math.sin(angleFor(i)) * radarR"
                stroke="rgba(15, 23, 60, .08)" stroke-width="0.5" />

          <!-- Polygon -->
          <polygon
            :points="radarPoints"
            :fill="(company.company_color || '#7F77DD') + '24'"
            :stroke="company.company_color || '#7F77DD'"
            stroke-width="1.5"
            stroke-linejoin="round"
            class="pco-radar-poly"
          />

          <!-- Dots + value labels -->
          <g v-for="(p, i) in radarDataPoints" :key="`p-${i}`">
            <circle
              :cx="p.x" :cy="p.y" r="3.5"
              :fill="paColorByDev(p.devPct)"
              :stroke="company.company_color || '#7F77DD'"
              stroke-width="1.2"
              class="pco-radar-dot"
              :style="{ '--rd-d': `${i * 50 + 200}ms` }"
            />
          </g>

          <!-- Axis labels -->
          <text v-for="(c, i) in categories" :key="`lbl-${i}`"
                :x="radarCx + Math.cos(angleFor(i)) * (radarR + 14)"
                :y="radarCy + Math.sin(angleFor(i)) * (radarR + 14) + 3"
                :text-anchor="textAnchor(i)"
                font-size="9.5"
                font-weight="500"
                fill="rgba(15, 23, 60, .65)"
          >{{ c.short }}</text>
        </svg>
      </div>
    </div>

    <!-- Purchases table -->
    <div class="pco-section">
      <div class="pco-section-h">Все закупки компании ({{ purchases.length }})</div>
      <div class="pco-tbl-wrap">
        <table class="pco-tbl">
          <thead>
            <tr>
              <th>Категория</th>
              <th class="right">Цена / ед.</th>
              <th class="right">Median рынка</th>
              <th class="right">Объём</th>
              <th>Поставщик</th>
              <th class="right">Откл.</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(p, i) in sortedPurchases.slice(0, 50)" :key="p.id"
                @click="$emit('drill-closure', p)"
                :style="{ animationDelay: `${Math.min(i, 30) * 18}ms` }"
                class="pco-row">
              <td>
                <span class="pco-cat-num">{{ padCat(p.category_id) }}</span>
                {{ p.category_name }}
              </td>
              <td class="right">{{ paFmtMoney(p.unit_price) }} / {{ p.category_unit || "ед" }}</td>
              <td class="right neu">{{ paFmtMoney(p.market_avg) }}</td>
              <td class="right">{{ fmt.fmtNumber(Number(p.volume)) }}</td>
              <td class="supplier">{{ p.supplier || "—" }}</td>
              <td class="right" :class="p.deviation_pct >= 0 ? 'up' : 'dn'">
                {{ fmt.fmtPercent(p.deviation_pct, { decimals: 1, signed: true }) }}
              </td>
            </tr>
            <tr v-if="!sortedPurchases.length">
              <td colspan="6" class="pco-empty">Нет закупок</td>
            </tr>
            <tr v-if="sortedPurchases.length > 50">
              <td colspan="6" class="pco-truncated">
                Показано 50 из {{ sortedPurchases.length }} · отсортировано по убыванию отклонения
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </CpDrillModal>
</template>

<script setup lang="ts">
import { computed } from "vue";
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
import CpDrillModal from "@/components/UZA/CpDrillModal.vue";
import { useFormatters } from "@/composables/useFormatters";

const fmt = useFormatters();

const props = defineProps<{
  company: CompanyRatingRow | null;
  categories: CategoryMeta[];
  purchases: ClosureRow[];
  totalCompanies: number;
}>();

defineEmits<{
  (e: "close"): void;
  (e: "drill-closure", closure: ClosureRow): void;
}>();

/** Pad numeric/string category id to "01".."15". `category_id` arrives as
 *  string from backend (TEXT column in DB). */
function padCat(id: string | number | null | undefined): string {
  if (id == null || id === "") return "—";
  const n = Number(id);
  if (Number.isNaN(n)) return String(id);
  return n < 10 ? "0" + n : String(n);
}

const rank = computed(() => props.company?.rank ?? 0);
const overpay = computed(() => Math.max(0, props.company?.sum_dev ?? 0));
const dirClass = computed(() => ((props.company?.company_deviation ?? 0) >= 0 ? "up" : "dn"));
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

// Radar chart math
const radarSize = 360;
const radarCx = radarSize / 2;
const radarCy = radarSize / 2;
const radarR = 130;

function angleFor(i: number): number {
  // -PI/2 = top start, clockwise
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
    // Map deviation to radius: 0% = center, ±20% = full radius
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
</script>

<style scoped>
.pco-mk-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  width: 100%;
}
@media (max-width: 800px) { .pco-mk-row { grid-template-columns: 1fr 1fr; } }

.pco-mk {
  text-align: center;
  padding: 10px 8px;
  background: rgba(255, 255, 255, .65);
  border-radius: 8px;
  backdrop-filter: blur(4px);
}
.pco-mk-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.pco-mk-v {
  font-size: 22px;
  font-weight: 500;
  color: #1e2a4a;
  margin-top: 4px;
  letter-spacing: -.025em;
  font-feature-settings: 'tnum';
}
.pco-mk-v small {
  font-size: 11px;
  font-weight: 400;
  color: rgba(15, 23, 60, .55);
  margin-left: 2px;
}
.pco-mk-v.up { color: #C53030; }
.pco-mk-v.dn { color: #0F6E56; }

.pco-rec {
  background: linear-gradient(135deg, rgba(127, 119, 221, .06) 0%, rgba(29, 158, 117, .04) 100%);
  border-radius: 8px;
  padding: 12px 16px;
  font-size: 12.5px;
  color: #1e2a4a;
  line-height: 1.55;
  position: relative; overflow: hidden;
}
.pco-rec::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #7F77DD;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s cubic-bezier(.4,0,.2,1) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.pco-rec :deep(b) { font-weight: 600; }

.pco-section {
  margin-top: 4px;
}

.pco-section-h {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 12px;
}

/* Radar chart */
.pco-radar-wrap {
  display: flex;
  justify-content: center;
}
.pco-radar {
  width: 100%;
  max-width: 420px;
  height: auto;
}

.pco-radar-poly {
  animation: polyIn .8s cubic-bezier(.4, 0, .2, 1) backwards;
}
@keyframes polyIn { from { opacity: 0; transform: scale(.7); transform-origin: center; } to { opacity: 1; transform: scale(1); } }

.pco-radar-dot {
  opacity: 0;
  animation: dotIn .35s cubic-bezier(.34, 1.2, .64, 1) forwards;
  animation-delay: var(--rd-d, 0ms);
}
@keyframes dotIn { from { opacity: 0; transform: scale(.4); } to { opacity: 1; transform: scale(1); } }

/* Purchases table */
.pco-tbl-wrap { overflow-x: auto; max-height: 360px; overflow-y: auto; border: 1px solid rgba(15, 23, 60, .06); border-radius: 6px; }
.pco-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.pco-tbl thead th {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 8px 10px;
  background: #FAFAFD;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky;
  top: 0;
  z-index: 1;
  white-space: nowrap;
}
.pco-tbl thead th.right { text-align: right; }

.pco-row {
  cursor: pointer;
  animation: rowIn .35s cubic-bezier(.4, 0, .2, 1) backwards;
}
@keyframes rowIn { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }
.pco-row:hover td { background: rgba(127, 119, 221, .04); }

.pco-tbl tbody td { padding: 8px 10px; border-bottom: 1px solid rgba(15, 23, 60, .04); color: #1e2a4a; }
.pco-tbl tbody td.right { text-align: right; }
.pco-tbl tbody td.neu { color: rgba(15, 23, 60, .55); }
.pco-tbl tbody td.up { color: #C53030; font-weight: 600; }
.pco-tbl tbody td.dn { color: #0F6E56; font-weight: 600; }
.pco-tbl tbody td.supplier { color: rgba(15, 23, 60, .65); font-style: italic; max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.pco-cat-num {
  display: inline-block;
  width: 24px;
  font-weight: 600;
  color: #7F77DD;
  font-size: 10px;
  margin-right: 6px;
}

.pco-empty, .pco-truncated {
  text-align: center !important;
  padding: 16px !important;
  color: rgba(15, 23, 60, .35);
  font-style: italic;
  font-size: 11px;
}
</style>
