<template>
  <!-- Source: paRenderCategoryGrid line 23067-23250 (legacy mode) -->
  <div class="pa-acc" id="pa-cat-grid">
    <div
      v-for="(cat, idx) in categories"
      :key="cat.id"
      class="pa-acc-row"
      :class="{ 'pa-acc-empty': !purchasesByCat(cat.id).length }"
      :style="{ animationDelay: `${idx * 25}ms` }"
      :data-acc-id="cat.id"
    >
      <!-- Empty row stub — line 23085-23091 -->
      <template v-if="!purchasesByCat(cat.id).length">
        <div class="pa-acc-head pa-acc-head-empty">
          <span class="pa-acc-num">{{ pad2(cat.id) }}</span>
          <span class="pa-acc-name">
            {{ cat.name }}
            <small>{{ cat.unit || "ед" }}</small>
          </span>
          <span class="pa-acc-spread pa-empty-stat">нет данных</span>
        </div>
      </template>

      <!-- Active row — line 23218-23230 -->
      <template v-else>
        <div class="pa-acc-head" @click="toggle(cat.id)">
          <span class="pa-acc-num">{{ pad2(cat.id) }}</span>
          <span class="pa-acc-name">
            {{ cat.name }}
            <small>{{ subtitleFor(cat) }}</small>
          </span>
          <!-- Spread label — line 23222 -->
          <span class="pa-acc-spread">
            {{ paFmtMoneyShort(spreadFor(cat).min) }} – {{ paFmtMoneyShort(spreadFor(cat).max) }}
          </span>
          <!-- Deviation bar — line 23223 -->
          <span class="pa-acc-bar">
            <span
              class="pa-acc-bar-fill"
              :style="barFillStyle(cat, idx)"
            />
          </span>
          <!-- Key stat — line 23224 -->
          <span class="pa-acc-stat" :style="{ color: keyStatFor(cat).color }">
            {{ keyStatFor(cat).text }}
          </span>
          <span class="pa-acc-chev" :class="{ open: isOpen(cat.id) }">▼</span>
        </div>

        <!-- Detail content — line 23226-23228 -->
        <div class="pa-acc-detail" :class="{ open: isOpen(cat.id) }">
          <div class="pa-acc-detail-inner">
            <!-- Legacy mode table — line 23192-23215 -->
            <table class="pa-acc-tbl">
              <colgroup>
                <col />
                <col style="width: 110px" />
                <col style="width: 90px" />
                <col />
                <col style="width: 70px" />
              </colgroup>
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
                <tr
                  v-for="r in detailRowsFor(cat.id)"
                  :key="r.id"
                  @click.stop="$emit('drill-closure', r)"
                >
                  <td>
                    <span class="sec" :style="{ background: r.company_color || '#888780' }" />
                    <span class="nm">{{ r.company_name }}</span>
                  </td>
                  <td class="r px">{{ paFmtMoney(r.unit_price) }}</td>
                  <td class="r vol">{{ Number(r.volume).toLocaleString("ru-RU") }}</td>
                  <td class="px sup">{{ r.supplier || "—" }}</td>
                  <td class="r vs" :class="r.deviation_pct >= 0 ? 'up' : 'dn'">
                    {{ r.deviation_pct >= 0 ? "+" : "" }}{{ r.deviation_pct.toFixed(1) }}%
                  </td>
                </tr>
              </tbody>
            </table>
            <!-- Footer — line 23215 -->
            <div class="pa-acc-foot">
              {{ coCountFor(cat.id) }}{{ coCountFor(cat.id) === 1 ? " компания" : " компаний" }} · клик по строке — детализация
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * PaCategoryGrid — TRUE 1:1 port of paRenderCategoryGrid (line 23067-23250).
 *
 * Renders 15-category accordion (legacy mode — fromContracts=false).
 * Each row shows:
 *   - Number + name + subtitle (unit + avg price)
 *   - Spread label (min – max prices)
 *   - Deviation bar (centered at 50%, ±30% range)
 *   - Key stat (max abs deviation with prefix "макс"/"мин")
 *   - Chevron
 * Click head → toggle. Click row → drill-closure.
 *
 * Note: contracts mode (top-15 products with productCode filter, line 23097+)
 * requires `data.productsByCode` and per-category `cat.allProducts[]`.
 * Backend currently doesn't expose these — deferred to next session.
 */
import { computed, ref } from "vue";
import {
  paColorByDev,
  paFmtMoney,
  paFmtMoneyShort,
  type CategoryMeta,
  type ClosureRow,
} from "@/api/procurement_analysis";

const props = defineProps<{
  categories: CategoryMeta[];
  purchases: ClosureRow[];
  marketAvgByCat?: Record<string, number>; // optional avg price per category for subtitle
}>();

defineEmits<{
  (e: "drill-closure", r: ClosureRow): void;
}>();

const openIds = ref<Set<number>>(new Set());

function toggle(id: number) {
  if (openIds.value.has(id)) openIds.value.delete(id);
  else openIds.value.add(id);
  // Trigger reactivity on Set mutation
  openIds.value = new Set(openIds.value);
}
function isOpen(id: number): boolean { return openIds.value.has(id); }

function pad2(id: number): string {
  if (id === 0) return "—";
  return id < 10 ? "0" + id : String(id);
}

// ─── Per-category data ─── (line 23073-23083)
function purchasesByCat(catId: number): ClosureRow[] {
  return props.purchases.filter((r) => r.category_id === catId);
}
function coCountFor(catId: number): number {
  return new Set(purchasesByCat(catId).map((r) => r.company_id)).size;
}

// ─── Spread (legacy mode) — line 23147-23150 ───
function spreadFor(cat: CategoryMeta): { min: number; max: number } {
  const inCat = purchasesByCat(cat.id);
  if (!inCat.length) return { min: 0, max: 0 };
  const prices = inCat.map((r) => Number(r.unit_price));
  return { min: Math.min(...prices), max: Math.max(...prices) };
}

// ─── Subtitle (legacy mode) — line 23172-23175 ───
function subtitleFor(cat: CategoryMeta): string {
  const parts: string[] = [cat.unit || "ед"];
  const avg = props.marketAvgByCat?.[String(cat.id)];
  if (avg) parts.push("ср. " + paFmtMoney(avg) + " сум");
  parts.push(purchasesByCat(cat.id).length + " закупок");
  return parts.join(" · ");
}

// ─── Bar fill — line 23129-23132 ───
function barFillStyle(cat: CategoryMeta, idx: number): Record<string, string> {
  const inCat = purchasesByCat(cat.id);
  const devs = inCat.map((r) => r.deviation_pct);
  if (!devs.length) return { display: "none" };
  const maxDev = Math.max(...devs);
  const minDev = Math.min(...devs);
  const avgDev = devs.reduce((s, v) => s + v, 0) / devs.length;
  // line 23129-23131
  const barLeft = Math.max(0, Math.min(100, 50 + (minDev / 30) * 50));
  const barRight = Math.max(0, Math.min(100, 50 + (maxDev / 30) * 50));
  const barWidth = Math.max(3, barRight - barLeft);
  return {
    background: paColorByDev(avgDev),
    left: barLeft + "%",
    width: barWidth + "%",
    animationDelay: (idx * 25 + 250) + "ms",
  };
}

// ─── Key stat (right side) — line 23133-23137 ───
function keyStatFor(cat: CategoryMeta): { text: string; color: string } {
  const inCat = purchasesByCat(cat.id);
  const devs = inCat.map((r) => r.deviation_pct);
  if (!devs.length) return { text: "", color: "" };
  const maxDev = Math.max(...devs);
  const minDev = Math.min(...devs);
  // line 23134: keyVal = whichever has greater absolute value
  const keyVal = Math.abs(maxDev) > Math.abs(minDev) ? maxDev : minDev;
  const keyLabel = (keyVal >= 0 ? "+" : "") + keyVal.toFixed(0) + "%";
  // line 23136
  const color = keyVal >= 10 ? "#C53030" : keyVal >= 0 ? "#B07415" : "#0F6E56";
  // line 23137: prefix
  const prefix = Math.abs(maxDev) > Math.abs(minDev) ? "макс " : "мин ";
  return { text: prefix + keyLabel, color };
}

// ─── Detail rows (legacy mode) — line 23192-23193 ───
function detailRowsFor(catId: number): ClosureRow[] {
  return [...purchasesByCat(catId)].sort((a, b) => a.deviation_pct - b.deviation_pct);
}
</script>

<style scoped>
.pa-acc {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pa-acc-row {
  background: #fff;
  border: 1px solid rgba(15, 23, 60, .06);
  border-radius: 8px;
  overflow: hidden;
  animation: paAccIn .35s cubic-bezier(.4, 0, .2, 1) backwards;
}
@keyframes paAccIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.pa-acc-row.pa-acc-empty { opacity: .55; }

/* line 23218 — head */
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
.pa-acc-head-empty { cursor: default; }
.pa-acc-head-empty:hover { background: transparent; }

.pa-acc-num {
  font-size: 10.5px;
  font-weight: 600;
  color: rgba(15, 23, 60, .55);
  font-feature-settings: 'tnum';
  text-align: center;
}

.pa-acc-name {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.pa-acc-name {
  font-size: 12px;
  font-weight: 500;
  color: #1e2a4a;
}
.pa-acc-name small {
  display: block;
  font-size: 10px;
  font-weight: 400;
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
.pa-empty-stat {
  color: rgba(15, 23, 60, .35);
  font-style: italic;
}

/* line 23223 — bar */
.pa-acc-bar {
  position: relative;
  height: 5px;
  background: rgba(15, 23, 60, .04);
  border-radius: 3px;
  overflow: hidden;
}
.pa-acc-bar::before {
  content: "";
  position: absolute;
  top: 0; bottom: 0;
  left: 50%;
  width: 1px;
  background: rgba(15, 23, 60, .15);
}
.pa-acc-bar-fill {
  position: absolute;
  top: 0; bottom: 0;
  border-radius: 2px;
  animation: barIn .8s cubic-bezier(.4, 0, .2, 1) backwards;
}
@keyframes barIn { from { transform: scaleX(0); transform-origin: center; } to { transform: scaleX(1); } }

.pa-acc-stat {
  font-size: 11px;
  font-weight: 600;
  font-feature-settings: 'tnum';
  text-align: right;
}

.pa-acc-chev {
  font-size: 9px;
  color: rgba(15, 23, 60, .35);
  transition: transform .25s cubic-bezier(.4, 0, .2, 1);
  text-align: center;
}
.pa-acc-chev.open { transform: rotate(180deg); color: #7F77DD; }

/* line 23226 — detail accordion */
.pa-acc-detail {
  max-height: 0;
  overflow: hidden;
  transition: max-height .35s cubic-bezier(.4, 0, .2, 1);
}
.pa-acc-detail.open { max-height: 800px; }
.pa-acc-detail-inner {
  padding: 4px 14px 14px;
  background: linear-gradient(180deg, #FAFAFD 0%, #fff 100%);
}

/* line 23213 — table */
.pa-acc-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.pa-acc-tbl thead td {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
}
.pa-acc-tbl thead td.r { text-align: right; }
.pa-acc-tbl tbody tr {
  cursor: pointer;
  transition: background .15s;
}
.pa-acc-tbl tbody tr:hover td { background: rgba(127, 119, 221, .04); }
.pa-acc-tbl tbody td {
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: #1e2a4a;
}
.pa-acc-tbl tbody td.r { text-align: right; }
.pa-acc-tbl tbody td.up { color: #C53030; font-weight: 600; }
.pa-acc-tbl tbody td.dn { color: #0F6E56; font-weight: 600; }
.pa-acc-tbl tbody td.sup {
  font-style: italic;
  color: rgba(15, 23, 60, .55);
  max-width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sec {
  display: inline-block;
  width: 4px;
  height: 14px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
}
.nm { vertical-align: middle; font-weight: 500; }

.pa-acc-foot {
  margin-top: 10px;
  padding: 6px 8px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
  font-style: italic;
}

/* Responsive */
@media (max-width: 900px) {
  .pa-acc-head {
    grid-template-columns: 28px 1fr 80px 24px;
  }
  .pa-acc-spread, .pa-acc-bar { display: none; }
}
</style>
