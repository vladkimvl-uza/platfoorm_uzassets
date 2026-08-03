<template>
  <div class="pa-compare">
    <!-- Filter strip -->
    <div class="pa-compare-h">
      <div>
        <div class="pa-compare-eyebrow">{{ t("Сравнение компаний") }}</div>
        <h3 class="pa-compare-title">{{ t("Рейтинг по среднему отклонению") }}</h3>
        <div class="pa-compare-sub">
          {{ t("1 строка на компанию · sparkline = отклонения по 15 категориям · высота столбика = модуль отклонения, цвет = знак") }}
        </div>
      </div>

      <div class="pa-compare-controls">
        <div class="pa-pill">
          <span class="pa-pill-l">{{ t("Топ:") }}</span>
          <button v-for="n in topNOptions" :key="n" :class="{ on: topN === n }" @click="topN = n">
            {{ n === 'all' ? t('Все') : n }}
          </button>
        </div>
      </div>
    </div>

    <!-- Table -->
    <div class="pa-rtbl-wrap">
      <table class="pa-rtbl">
        <colgroup>
          <col style="width: 36px" />
          <col />
          <col style="width: 100px" />
          <col style="width: 130px" />
          <col style="width: 280px" />
          <col style="width: 80px" />
          <col style="width: 130px" />
        </colgroup>
        <thead>
          <tr>
            <th class="center">№</th>
            <th>{{ t("Компания") }}</th>
            <th class="right" :class="sortClass('deviation')" @click="setSort('deviation')">
              {{ t("Откл. ср.") }}
              <span class="pa-sort-arrow" v-if="sortKey === 'deviation'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="right" :class="sortClass('overpay')" @click="setSort('overpay')">
              {{ t("Переплата") }}
              <span class="pa-sort-arrow" v-if="sortKey === 'overpay'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="center">{{ t("Откл. по 15 категориям") }}</th>
            <th class="center" :class="sortClass('red')" @click="setSort('red')">
              {{ t("Красных") }}
              <span class="pa-sort-arrow" v-if="sortKey === 'red'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th class="right" :class="sortClass('volume')" @click="setSort('volume')">
              {{ t("Объём") }}
              <span class="pa-sort-arrow" v-if="sortKey === 'volume'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(c, i) in visibleRating"
            :key="c.company_id"
            class="pa-rtbl-row"
            :style="{ animationDelay: `${Math.min(i, 30) * 30}ms` }"
            @click="$emit('drill-company', c)"
          >
            <td class="num">{{ i + 1 }}</td>
            <td>
              <div class="nm-cell">
                <span class="sec" :style="{ background: c.company_color || '#888780' }" />
                <span class="nm" :title="companyName(c)">{{ companyName(c) }}</span>
              </div>
            </td>
            <td class="right" :class="c.company_deviation == null ? 'neu' : (c.company_deviation >= 0 ? 'up' : 'dn')"
                :title="c.company_deviation == null ? t('Нет сопоставимых позиций — отклонение не рассчитывается') : undefined">
              <template v-if="c.company_deviation == null">—</template>
              <template v-else>{{ c.company_deviation >= 0 ? "+" : "" }}{{ c.company_deviation.toFixed(1) }}%</template>
            </td>
            <td class="right neu">
              <template v-if="Math.max(0, c.sum_dev) > 0">
                {{ paFmtMoneyShort(Math.max(0, c.sum_dev)) }} {{ t("сум") }}
              </template>
              <template v-else>—</template>
            </td>
            <td class="center">
              <span class="pa-rtbl-mini">
                <span
                  v-for="cat in categories"
                  :key="cat.id"
                  :style="sparkBarStyle(c, cat.id)"
                  :title="sparkBarTitle(c, cat)"
                />
              </span>
            </td>
            <td class="center">
              <span :class="redBadgeClass(c.above_count)">{{ c.above_count }}</span>
            </td>
            <td class="right neu">{{ paFmtMoneyShort(c.sum_ref) }} {{ t("сум") }}</td>
          </tr>
          <tr v-if="!visibleRating.length">
            <td colspan="7" class="pa-empty">{{ t("Нет компаний для сравнения") }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="pa-compare-foot">
      <span>{{ t("Показано {shown} из {total} компаний · клик по строке — профиль компании", { shown: visibleRating.length, total: sortedRating.length }) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CategoryCompareTable — verbatim from legacy line 22965+.
 *
 * Sortable rating table; each row = company; cell with mini-sparkline showing
 * deviation per 15 categories. Click row → company drill modal.
 */
import { computed } from "vue";
import {
  paColorByDev,
  paFmtMoneyShort,
  paSameCat,
  type CategoryMeta,
  type CompanyRatingRow,
} from "@/api/procurement_analysis";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useI18n } from "@/composables/useI18n";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const { t } = useI18n();
const companyName = (company: CompanyRatingRow) =>
  resolveCompanyDisplayName(company.company_name || company.company_code, company.company_id || company.company_code) || "—";

const props = defineProps<{
  rating: CompanyRatingRow[];
  categories: CategoryMeta[];
}>();

defineEmits<{
  (e: "drill-company", co: CompanyRatingRow): void;
}>();

type SortKey = "deviation" | "overpay" | "red" | "volume";
const sortKey = useSavedFilter<SortKey>("procurement.compareSortKey", "deviation");
const sortDir = useSavedFilter<"asc" | "desc">("procurement.compareSortDir", "asc");
const topN = useSavedFilter<number | "all">("procurement.compareTopN", "all");
const topNOptions: (number | "all")[] = [5, 10, 20, "all"];

function setSort(key: SortKey) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  } else {
    sortKey.value = key;
    // Logical defaults: deviation asc (leaders first), others desc (large first)
    sortDir.value = key === "deviation" ? "asc" : "desc";
  }
}

function sortClass(key: SortKey): string {
  return sortKey.value === key ? `pa-sorted ${sortDir.value}` : "";
}

const sortedRating = computed(() => {
  const list = [...props.rating];
  const fn: Record<SortKey, (a: CompanyRatingRow, b: CompanyRatingRow) => number> = {
    deviation: (a, b) => (a.company_deviation ?? Number.POSITIVE_INFINITY)
      - (b.company_deviation ?? Number.POSITIVE_INFINITY),
    overpay: (a, b) => Math.max(0, a.sum_dev) - Math.max(0, b.sum_dev),
    red: (a, b) => a.above_count - b.above_count,
    volume: (a, b) => a.sum_ref - b.sum_ref,
  };
  list.sort(fn[sortKey.value]);
  if (sortDir.value === "desc") list.reverse();
  return list;
});

const visibleRating = computed(() => {
  if (topN.value === "all") return sortedRating.value;
  return sortedRating.value.slice(0, topN.value as number);
});

function sparkBarStyle(c: CompanyRatingRow, catId: number) {
  const d = c.cat_dev.find((x) => paSameCat(x.category_id, catId));
  if (!d || !d.sum_ref) {
    return { background: "#fff", height: "2px" };
  }
  const dev = (d.sum_dev / d.sum_ref) * 100;
  const col = paColorByDev(dev);
  const h = Math.min(100, Math.max(8, Math.abs(dev) * 3.5));
  return { background: col, height: `${h}%` };
}

function sparkBarTitle(c: CompanyRatingRow, cat: CategoryMeta): string {
  const d = c.cat_dev.find((x) => paSameCat(x.category_id, cat.id));
  if (!d || !d.sum_ref) return `${cat.short}: ${t("нет данных")}`;
  const dev = (d.sum_dev / d.sum_ref) * 100;
  return `${cat.short}: ${dev >= 0 ? "+" : ""}${dev.toFixed(1)}%`;
}

function redBadgeClass(n: number): string {
  if (n === 0) return "badge-grn";
  if (n <= 2) return "badge-neu";
  return "badge-red";
}
</script>

<style scoped>
.pa-compare {
  background: var(--bg1, #fff);
  border-radius: 12px;
  padding: 16px 18px;
  border: 1px solid rgba(15, 23, 60, .06);
}

.pa-compare-h {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.pa-compare-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: #7F77DD;
}
.pa-compare-title { font-size: 14px; font-weight: 500; margin: 4px 0 0; color: var(--t1, #1e2a4a); }
.pa-compare-sub { font-size: 10.5px; color: rgba(15, 23, 60, .55); margin-top: 4px; }

.pa-compare-controls { display: flex; gap: 8px; }

.pa-pill {
  display: inline-flex;
  background: rgba(15, 23, 60, .04);
  border-radius: 6px;
  padding: 2px;
  align-items: center;
  gap: 2px;
  padding-left: 8px;
}
.pa-pill-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-right: 4px;
}
.pa-pill button {
  background: transparent;
  border: none;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  color: rgba(15, 23, 60, .55);
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
}
.pa-pill button:hover { color: var(--t1, #1e2a4a); }
.pa-pill button.on { background: var(--bg1, #fff); color: #7F77DD; box-shadow: 0 1px 2px rgba(15, 23, 60, .08); }

.pa-rtbl-wrap { overflow-x: auto; }
.pa-rtbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}

.pa-rtbl thead th {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 8px 8px;
  background: var(--bg2, #FAFAFD);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}
.pa-rtbl thead th.right { text-align: right; }
.pa-rtbl thead th.center { text-align: center; cursor: default; }
.pa-rtbl thead th.pa-sorted { color: #7F77DD; }

.pa-sort-arrow { font-weight: 700; }

.pa-rtbl tbody td {
  padding: 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: var(--t1, #1e2a4a);
}
.pa-rtbl tbody td.num { color: rgba(15, 23, 60, .55); font-weight: 600; text-align: center; }
.pa-rtbl tbody td.right { text-align: right; }
.pa-rtbl tbody td.center { text-align: center; }
.pa-rtbl tbody td.neu { color: rgba(15, 23, 60, .65); }
.pa-rtbl tbody td.up { color: #C53030; font-weight: 600; }
.pa-rtbl tbody td.dn { color: #0F6E56; font-weight: 600; }

.pa-rtbl-row {
  cursor: pointer;
  animation: rowIn .35s var(--ease-standard) backwards;
}
@keyframes rowIn { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }
.pa-rtbl-row:hover td { background: rgba(127, 119, 221, .04); }

.nm-cell { display: flex; align-items: center; gap: 8px; min-width: 0; }
.sec { display: inline-block; width: 4px; height: 18px; border-radius: 2px; flex-shrink: 0; }
.nm { font-weight: 500; color: var(--t1, #1e2a4a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.pa-rtbl-mini {
  display: inline-flex;
  align-items: flex-end;
  gap: 1px;
  height: 32px;
  width: 100%;
  max-width: 270px;
  padding: 4px 8px;
  background: var(--bg2, #FAFAFD);
  border-radius: 4px;
}
.pa-rtbl-mini > span {
  flex: 1;
  min-width: 4px;
  border-radius: 1px 1px 0 0;
  align-self: flex-end;
  cursor: pointer;
  transition: opacity .15s;
}
.pa-rtbl-mini > span:hover { opacity: .7; }

.badge-grn, .badge-neu, .badge-red {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  font-feature-settings: 'tnum';
  min-width: 24px;
  text-align: center;
}
.badge-grn { background: rgba(29, 158, 117, .14); color: var(--green); }
.badge-neu { background: rgba(239, 159, 39, .14); color: #B07415; }
.badge-red { background: rgba(226, 75, 74, .14); color: #C53030; }

.pa-empty {
  text-align: center !important;
  padding: 30px !important;
  color: rgba(15, 23, 60, .35);
  font-style: italic;
}

.pa-compare-foot {
  margin-top: 8px;
  padding: 0 4px;
  font-size: 10.5px;
  color: rgba(15, 23, 60, .55);
}
.pa-compare-foot b { color: var(--t1, #1e2a4a); }
</style>
