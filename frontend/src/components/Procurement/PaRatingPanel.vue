<template>
  <!-- Source: paRatingPanelHtml line 22177-22221 -->
  <div class="pa-rate-panel">
    <div v-if="!rating.length" class="pa-rate-empty">{{ t("Нет данных по рейтингу") }}</div>

    <template v-else>
      <template v-for="(c, i) in sortedRating" :key="c.company_id">
        <!-- Divider before leaders — line 22186-22188 -->
        <div
          v-if="i === firstSaverIdx && firstSaverIdx > 0"
          class="pa-rate-divider"
        >
          ▾ {{ t("лидеры портфеля — торгуются ниже рынка") }}
        </div>

        <!-- Row — line 22202-22217 -->
        <div
          class="pa-rate-row"
          :class="{ 'is-saver': netSum(c) < 0, 'is-lowsample': c.low_sample }"
          :style="{ animationDelay: `${i * 30}ms` }"
          @click="$emit('select-co', c.company_id)"
        >
          <span class="pa-rate-num">{{ pad2(i + 1) }}</span>
          <span class="pa-rate-sec" :style="{ background: c.company_color || '#888780' }" />

          <div class="pa-rate-mid">
            <div class="pa-rate-nm" :title="c.company_name">
              {{ c.company_name }}
              <span
                v-if="c.low_sample"
                class="pa-rate-lowsample"
                :title="t('Мало сопоставимых позиций — отклонение и % красных статистически недостоверны')"
              >{{ t("мало данных") }}</span>
            </div>
            <!-- 3-color stripe bar — line 22206 -->
            <div class="pa-rate-bar">
              <span :style="{ background: '#E24B4A', width: stripeOf(c).red.toFixed(0) + '%' }" />
              <span :style="{ background: '#B4B2A9', width: stripeOf(c).yellow.toFixed(0) + '%' }" />
              <span :style="{ background: '#1D9E75', width: stripeOf(c).green.toFixed(0) + '%' }" />
            </div>
          </div>

          <!-- Sum overpay/savings — line 22209-22212 -->
          <div class="pa-rate-overpay">
            <div class="pa-rate-overpay-v" :style="{ color: sumColor(c) }">
              {{ sumPrefix(c) }}{{ paFmtMoneyShort(Math.abs(netSum(c))) }}
            </div>
            <div class="pa-rate-overpay-l">{{ sumLabel(c) }}</div>
          </div>

          <!-- Red pct — line 22213-22215 -->
          <div class="pa-rate-redpct">
            <div class="pa-rate-redpct-v" :style="{ color: redColor(stripeOf(c).red) }">{{ stripeOf(c).red.toFixed(0) }}%</div>
            <div class="pa-rate-redpct-l">{{ t("красных") }}</div>
          </div>

          <!-- Problem cats badge — line 22216 -->
          <div
            class="pa-rate-cats"
            :style="{ background: pcBadgeBg(problemCatsOf(c)), color: pcBadgeColor(problemCatsOf(c)) }"
          >
            {{ problemCatsOf(c) }}
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * PaRatingPanel — TRUE 1:1 port of paRatingPanelHtml (line 22177-22221).
 *
 * Default sort: sumOverpay desc — worst (max overpay) first; leaders (negative sumOverpay) last.
 * Divider inserted before first leader.
 * 3-color stripe bar showing red/yellow/green pct of purchases.
 * Click row → emit('select-co', companyId) — line 22203
 */
import { computed } from "vue";
import { paFmtMoneyShort, type CompanyRatingRow } from "@/api/procurement_analysis";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

const props = defineProps<{
  rating: CompanyRatingRow[];
}>();

defineEmits<{
  (e: "select-co", companyId: string): void;
}>();

// Pack 7.9p: backend возвращает signed `sum_dev` (Decimal string),
// derive sum_overpay/savings/netSum через fallback computed.
// sum_dev > 0 → company overpays (positive); < 0 → saves.
function devOf(c: CompanyRatingRow): number {
  return Number((c as unknown as { sum_dev?: string }).sum_dev) || 0;
}
function overpayOf(c: CompanyRatingRow): number {
  const ov = (c as unknown as { sum_overpay?: number | string }).sum_overpay;
  if (ov !== undefined) return Number(ov);
  const d = devOf(c);
  return d > 0 ? d : 0;
}
function savingsOf(c: CompanyRatingRow): number {
  const sv = (c as unknown as { sum_savings?: number | string }).sum_savings;
  if (sv !== undefined) return Number(sv);
  const d = devOf(c);
  return d < 0 ? -d : 0;
}

// Полоса красных/жёлтых/зелёных — берём ПРЯМО из бэкенда (red_pct/yellow_pct/
// green_pct: доля сопоставимых ПОЗИЦИЙ с отклонением >=10% / 0..10% / <0). Раньше
// фронт пересчитывал из cat_dev по другому порогу (>1% на уровне категорий) —
// получалось ДВА расходящихся определения «красных %». Теперь единое (BE).
function stripeOf(c: CompanyRatingRow): { red: number; yellow: number; green: number } {
  return {
    red: Number(c.red_pct) || 0,
    yellow: Number(c.yellow_pct) || 0,
    green: Number(c.green_pct) || 0,
  };
}
function problemCatsOf(c: CompanyRatingRow): number {
  return Number(c.problem_cats) || 0;
}

const sortedRating = computed(() =>
  [...props.rating].sort((a, b) => overpayOf(b) - overpayOf(a)),
);

const firstSaverIdx = computed(() => {
  for (let i = 0; i < sortedRating.value.length; i++) {
    if (overpayOf(sortedRating.value[i]) <= 0) return i;
  }
  return -1;
});

function pad2(n: number): string { return n < 10 ? "0" + n : String(n); }

function netSum(c: CompanyRatingRow): number {
  return overpayOf(c) - savingsOf(c);
}

// line 22194-22196
function sumColor(c: CompanyRatingRow): string {
  const v = netSum(c);
  if (v >= 10e9) return "#A32D2D";
  if (v >= 0) return "#BA7517";
  return "#0F6E56";
}
function sumLabel(c: CompanyRatingRow): string {
  return netSum(c) >= 0 ? t("сум переплаты") : t("сум экономии");
}
function sumPrefix(c: CompanyRatingRow): string {
  return netSum(c) >= 0 ? "+" : "−";
}

// line 22198
function redColor(p: number): string {
  if (p >= 40) return "#A32D2D";
  if (p >= 20) return "#BA7517";
  return "#0F6E56";
}

// line 22199-22200
function pcBadgeBg(n: number): string {
  if (n >= 5) return "rgba(226,75,74,.10)";
  if (n >= 2) return "rgba(239,159,39,.14)";
  return "rgba(29,158,117,.14)";
}
function pcBadgeColor(n: number): string {
  if (n >= 5) return "#A32D2D";
  if (n >= 2) return "#BA7517";
  return "#0F6E56";
}
</script>

<style scoped>
.pa-rate-panel {
  display: flex;
  flex-direction: column;
}

.pa-rate-empty {
  padding: 30px 16px;
  text-align: center;
  color: rgba(15, 23, 60, .35);
  font-style: italic;
  font-size: 11.5px;
}

.pa-rate-divider {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .04em;
  color: #0F6E56;
  background: rgba(29, 158, 117, .06);
  padding: 6px 12px;
  margin: 6px 0;
  border-radius: 4px;
}

/* line 22202: row */
.pa-rate-row {
  display: grid;
  grid-template-columns: 22px 5px 1fr 110px 60px 32px;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  animation: rateRowIn .35s var(--ease-standard) backwards;
  transition: background .15s;
}
@keyframes rateRowIn { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }
.pa-rate-row:hover { background: rgba(127, 119, 221, .04); }
.pa-rate-row.is-saver { opacity: .92; }
/* мало данных — приглушаем строку, числа недостоверны */
.pa-rate-row.is-lowsample { opacity: .6; }
.pa-rate-row.is-lowsample:hover { opacity: .85; }
.pa-rate-lowsample {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .03em;
  text-transform: uppercase;
  color: #6B6A66;
  background: rgba(136, 135, 128, .16);
  vertical-align: middle;
}

.pa-rate-num {
  font-size: 9.5px;
  font-weight: 600;
  color: rgba(15, 23, 60, .55);
  text-align: center;
  font-feature-settings: 'tnum';
}
.pa-rate-sec {
  height: 22px;
  border-radius: 1.5px;
}

.pa-rate-mid { min-width: 0; }
.pa-rate-nm {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--t1, #1e2a4a);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* line 22206 — 3-color stripe bar */
.pa-rate-bar {
  display: flex;
  height: 4px;
  background: rgba(15, 23, 60, .04);
  border-radius: 2px;
  overflow: hidden;
  margin-top: 4px;
}
.pa-rate-bar > span {
  height: 100%;
  display: inline-block;
  transition: width .8s var(--ease-standard);
}

/* line 22210-22212 */
.pa-rate-overpay { text-align: right; }
.pa-rate-overpay-v {
  font-size: 12px;
  font-weight: 600;
  font-feature-settings: 'tnum';
  letter-spacing: -.005em;
}
.pa-rate-overpay-l {
  font-size: 9px;
  color: rgba(15, 23, 60, .55);
  text-transform: lowercase;
  letter-spacing: .02em;
  margin-top: 1px;
}

.pa-rate-redpct { text-align: right; }
.pa-rate-redpct-v {
  font-size: 11.5px;
  font-weight: 600;
  font-feature-settings: 'tnum';
}
.pa-rate-redpct-l {
  font-size: 9px;
  color: rgba(15, 23, 60, .55);
  margin-top: 1px;
}

.pa-rate-cats {
  width: 28px;
  height: 22px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  font-feature-settings: 'tnum';
}
</style>
