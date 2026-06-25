<script setup lang="ts">
/**
 * ExecDashTaxContributionBlock — Row 2.7.
 * Налоговый вклад портфеля в бюджет Республики Узбекистан.
 *
 * Как в легасие _execTaxContributionHtml:
 *   - 4 KPI band:
 *     · Налог на прибыль (синий)
 *     · НДС 12% от выручки (зелёный)
 *     · Итого вклад (фиолетовый)
 *     · % бюджета РУ (амбер)
 *   - Top-5 плательщиков с долей
 *   - YoY badges
 */
import { computed, onMounted, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import { useSectorMeta, SECTOR_COLORS } from "@/utils/sectorMeta";
import TaxContributionDrillModal, { type TaxKind } from "@/components/UZA/TaxContributionDrillModal.vue";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import CurrencyToggle from "@/components/UZA/CurrencyToggle.vue";
import Odometer from "@/components/Odometer.vue";

const exec = useExecutiveDashboard();
const secMeta = useSectorMeta();
const conv = useCurrencyConverter();

// Pack 7.22: reuse the fkb-card top-stripe + shimmer animation kit
onMounted(() => { ensureFinancialsCss(); });

const block = computed(() => exec.data.value?.tax_contribution || null);
const kpi = computed(() => block.value?.kpi || null);
const isFallback = computed(() =>
  !!block.value?.requested_year && block.value.requested_year !== block.value.year);
const topPayers = computed(() => block.value?.top_payers || []);

// Pack 7.22: pre-compute bar width as percentage of the largest payer
// so the rendered bars are visually proportional (top payer = 100%).
const topPayersWithBar = computed(() => {
  const rows = topPayers.value;
  if (!rows.length) return [];
  const maxAmount = Math.max(...rows.map(p => Number(p.amount) || 0));
  if (maxAmount <= 0) return rows.map(p => ({ ...p, _barPct: 0 }));
  return rows.map(p => ({
    ...p,
    _barPct: Math.max(2, Math.round((Number(p.amount) / maxAmount) * 100)),
  }));
});

const sectorColor = SECTOR_COLORS as Record<string, string>;

const sectorLabel = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  const byCode = secMeta.byCodeMap.value;
  for (const code of Object.keys(byCode)) {
    map[code] = byCode[code as keyof typeof byCode]?.label || code;
  }
  return map;
});

// Pack 7.34: форматирование с тремя знаками после запятой и поддержкой
// USD-конвертации. Возвращает {value, unit} раздельно — для гибкости вёрстки.
function fmt3(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const parts = (Math.round(v * 1000) / 1000).toFixed(3).split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
  return parts.join(".").replace(/\u00A0/g, " ");
}

// Денежная KPI в активной валюте
function fmtMoney(mlrdUzs: number | null | undefined): { value: string; unit: string } {
  if (mlrdUzs == null) return { value: "—", unit: "" };
  const f = conv.format(mlrdUzs, block.value?.year ?? exec.year.value);
  return { value: f.value, unit: f.unit };
}

// Pack 7.34: drill-down модалка для 4 KPI
const drillKind = ref<TaxKind | null>(null);
function openDrill(kind: TaxKind) {
  if (!block.value || !block.value.has_data) return;
  drillKind.value = kind;
}
function closeDrill() { drillKind.value = null; }
function onKpiKeydown(e: KeyboardEvent, kind: TaxKind) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openDrill(kind);
  }
}

function fmtYoY(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function yoyColor(v: number | null | undefined): string {
  if (v == null) return "#888780";
  if (v >= 5) return "#1D9E75";
  if (v >= -5) return "#EF9F27";
  return "#E24B4A";
}

// 2026-05-26: countup for 4 KPI tax values + YoY (sync with Dashboard motion).
const tIncomeTax    = useNumberTween(() => Number(kpi.value?.income_tax) || 0, { duration: 900 });
const tVat          = useNumberTween(() => Number(kpi.value?.vat) || 0, { duration: 900 });
const tTotal        = useNumberTween(() => Number(kpi.value?.total) || 0, { duration: 900 });
const tYoYIncTax    = useNumberTween(() => Number(kpi.value?.yoy_income_tax_pct) || 0, { duration: 900 });
const tYoYVat       = useNumberTween(() => Number(kpi.value?.yoy_vat_pct) || 0, { duration: 900 });
const tYoYTotal     = useNumberTween(() => Number(kpi.value?.yoy_total_pct) || 0, { duration: 900 });
</script>

<template>
  <section class="ed-card etx-card">
    <header class="etx-hdr">
      <div class="etx-hdr-l">
        <div class="etx-eyebrow">Налоговый вклад портфеля
          <span v-if="isFallback" class="etx-fallback">данные за FY {{ block?.year }}</span>
        </div>
        <div class="etx-sub">FY {{ block?.year || exec.year.value }} · вклад в бюджет Республики Узбекистан</div>
      </div>
      <div v-if="block && block.has_data" class="etx-hdr-r">
        <CurrencyToggle :year="block.year" :compact="true" :show-rate="false" />
        <span
          class="etx-stat"
          :title="block.missing_companies && block.missing_companies.length
            ? `Без NSBU PL за ${block.year}:\n• ` + block.missing_companies.join('\n• ')
            : 'Все компании портфеля учтены'"
        >
          {{ block.cos_count }} компаний · {{ block.standard }}
          <sup
            v-if="block.missing_companies && block.missing_companies.length"
            class="etx-missing"
          >−{{ block.missing_companies.length }}</sup>
        </span>
      </div>
    </header>

    <!-- Empty state -->
    <div v-if="!block || !block.has_data" class="etx-empty">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
      </svg>
      <div class="etx-empty-title">Нет налоговых данных за FY {{ exec.year.value }}</div>
      <div class="etx-empty-text">
        Заполните поля «Выручка» и «Налог на прибыль»<br>
        в финансовой отчётности портфеля (IFRS / NSBU PL).
      </div>
    </div>

    <template v-else-if="kpi">
      <!-- Pack 7.22: 4 KPI band in fkb-card style — top stripe instead of border-left
           Pack 7.34: cards clickable + 3-decimal formatter + USD support -->
      <div class="etx-kpi-band kpi-rail">
        <div
          class="etx-kpi etx-kpi--clickable"
          style="--accent: #378ADD; --d: 0ms;"
          role="button"
          tabindex="0"
          @click="openDrill('income_tax')"
          @keydown="onKpiKeydown($event, 'income_tax')"
          title="Подробнее: Налог на прибыль"
        >
          <div class="etx-kpi-lbl">Налог на прибыль</div>
          <div class="etx-kpi-val">
            {{ fmtMoney(tIncomeTax).value }}<span class="etx-kpi-u">{{ fmtMoney(tIncomeTax).unit }}</span>
          </div>
          <div class="etx-kpi-yoy" :style="{ color: yoyColor(kpi.yoy_income_tax_pct) }">
            <span v-if="kpi.yoy_income_tax_pct != null">{{ fmtYoY(tYoYIncTax) }} к {{ block.prev_year }}</span>
            <span v-else>—</span>
          </div>
        </div>

        <div
          class="etx-kpi etx-kpi--clickable"
          style="--accent: #1D9E75; --d: 80ms;"
          role="button"
          tabindex="0"
          @click="openDrill('vat')"
          @keydown="onKpiKeydown($event, 'vat')"
          title="Подробнее: Налог на добавленную стоимость"
        >
          <div class="etx-kpi-lbl">Налог на добавленную стоимость (12% от выручки)</div>
          <div class="etx-kpi-val">
            {{ fmtMoney(tVat).value }}<span class="etx-kpi-u">{{ fmtMoney(tVat).unit }}</span>
          </div>
          <div class="etx-kpi-yoy" :style="{ color: yoyColor(kpi.yoy_vat_pct) }">
            <span v-if="kpi.yoy_vat_pct != null">{{ fmtYoY(tYoYVat) }} к {{ block.prev_year }}</span>
            <span v-else>—</span>
          </div>
        </div>

        <div
          class="etx-kpi etx-kpi--clickable"
          style="--accent: #7F77DD; --d: 160ms;"
          role="button"
          tabindex="0"
          @click="openDrill('total')"
          @keydown="onKpiKeydown($event, 'total')"
          title="Подробнее: Итоговый налоговый вклад"
        >
          <div class="etx-kpi-lbl">Итоговый налоговый вклад</div>
          <div class="etx-kpi-val">
            {{ fmtMoney(tTotal).value }}<span class="etx-kpi-u">{{ fmtMoney(tTotal).unit }}</span>
          </div>
          <div class="etx-kpi-yoy" :style="{ color: yoyColor(kpi.yoy_total_pct) }">
            <span v-if="kpi.yoy_total_pct != null">{{ fmtYoY(tYoYTotal) }} к {{ block.prev_year }}</span>
            <span v-else>—</span>
          </div>
        </div>

        <div
          class="etx-kpi etx-kpi--clickable"
          style="--accent: #EF9F27; --d: 240ms;"
          role="button"
          tabindex="0"
          @click="openDrill('budget_share')"
          @keydown="onKpiKeydown($event, 'budget_share')"
          title="Подробнее: Доля портфеля в бюджете Республики"
        >
          <div class="etx-kpi-lbl">Процент бюджета Республики Узбекистан</div>
          <div class="etx-kpi-val">
            <span v-if="kpi.budget_share_pct != null"><Odometer :value="fmt3(kpi.budget_share_pct)" /><span class="etx-kpi-u">%</span></span>
            <span v-else>—</span>
          </div>
          <div class="etx-kpi-yoy">
            <span v-if="kpi.budget != null">из {{ fmtMoney(kpi.budget).value }} {{ fmtMoney(kpi.budget).unit }}</span>
            <span v-else>—</span>
          </div>
        </div>
      </div>

      <!-- Pack 7.22: Top-5 payers in CSS-grid with fixed name column.
           All progress bars start from the same vertical line regardless of
           name length. Bar width = amount / max_amount * 100 (relative scale). -->
      <div v-if="topPayersWithBar.length" class="etx-payers">
        <div class="etx-payers-hdr">Топ-5 плательщиков · {{ block.year }}</div>
        <div class="etx-grid">
          <template v-for="(p, i) in topPayersWithBar" :key="p.company_id">
            <div class="etx-cell etx-c-rank"><div class="etx-rank">{{ i + 1 }}</div></div>
            <div class="etx-cell etx-c-bar">
              <div class="etx-sec-bar" :style="{ background: sectorColor[p.sector] || '#888780' }" />
            </div>
            <div class="etx-cell etx-c-name" :title="p.name">{{ p.name }}</div>
            <div class="etx-cell etx-c-grow">
              <div class="etx-grow-track">
                <div class="etx-grow-fill" :style="{ width: p._barPct + '%' }" />
              </div>
            </div>
            <div class="etx-cell etx-c-amt">
              {{ fmtMoney(p.amount).value }}<span class="etx-row-u">{{ fmtMoney(p.amount).unit }}</span>
            </div>
            <div class="etx-cell etx-c-pct">{{ p.share_pct }}%</div>
          </template>
        </div>
      </div>
    </template>

    <!-- Pack 7.34: drill-down модалка для 4 KPI -->
    <TaxContributionDrillModal
      v-if="drillKind && block && kpi && block.has_data"
      :kind="drillKind"
      :kpi="kpi"
      :top-payers="topPayers"
      :year="block.year"
      :prev-year="block.prev_year"
      :cos-count="block.cos_count"
      :standard-label="block.standard"
      :sector-color="sectorColor"
      :sector-label="sectorLabel"
      @close="closeDrill"
    />
  </section>
</template>

<style scoped>
.etx-card {
  padding: 14px 14px;
  background: var(--bg1, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  margin-top: 14px;
}

.etx-hdr {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}
.etx-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  margin-bottom: 3px;
}
.etx-sub {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.04em;
}
.etx-stat {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  background: rgba(127, 119, 221, 0.07);
  padding: 4px 10px;
  border-radius: 8px;
}
.etx-fallback {
  display: inline-block;
  margin-left: 8px;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.03em;
  text-transform: none;
  color: #92610B;
  background: rgba(239, 159, 39, 0.14);
  border: 1px solid rgba(239, 159, 39, 0.3);
  padding: 2px 8px;
  border-radius: 999px;
  vertical-align: middle;
}

/* Pack 7.34: header right group — CurrencyToggle + stat */
.etx-hdr-r {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

/* Pack 7.34: clickable variant — hover-lift + focus ring */
.etx-kpi--clickable {
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
  outline: none;
}
.etx-kpi--clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(15, 23, 60, 0.10), 0 1px 3px rgba(15, 23, 60, 0.04);
  border-color: rgba(127, 119, 221, 0.30);
}
.etx-kpi--clickable:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45);
}
.etx-kpi--clickable:active {
  transform: translateY(-1px);
}

/* Empty state */
.etx-empty {
  padding: 50px 20px;
  text-align: center;
  color: #6B6A66;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.etx-empty-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  margin-top: 6px;
}
.etx-empty-text {
  font-size: 12px;
  line-height: 1.5;
  color: #6B6A66;
}

/* KPI band */
.etx-kpi-band {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 14px 0;
}
/* Pack 7.22: KPI card in fkb-card style — top stripe + shimmer, no border-left.
   Uses global animation kit injected by ensureFinancialsCss() in onMounted. */
.etx-kpi {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border-radius: 14px;
  padding: 14px 16px 12px;
  border: 1px solid rgba(255, 255, 255, 0.70);
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 96px;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.etx-kpi::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, var(--border-input));
  border-radius: 14px 14px 0 0;
  animation:
    finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both,
    finKpi2Breathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite;
  transform-origin: left center;
}
.etx-kpi::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  animation: finShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1;
  transform: translateX(-120%);
  pointer-events: none;
}
.etx-kpi-lbl {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.etx-kpi-val {
  font-size: 26px;
  font-weight: 400;
  letter-spacing: -0.035em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 2px 0 4px;
}
.etx-kpi-u {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  letter-spacing: 0;
}
.etx-kpi-yoy {
  font-size: 10.5px;
  font-weight: 600;
  margin-top: 4px;
  font-feature-settings: "tnum";
}

/* Top-5 payers */
.etx-payers-hdr {
  font-size: 11px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
}
/* Pack 7.22: top-5 payers — CSS-grid with FIXED name column so all
   progress bars start from the same vertical line, regardless of name length. */
.etx-grid {
  display: grid;
  grid-template-columns: 22px 3px 180px minmax(60px, 1fr) max-content max-content;
  /*                     rank  bar  name-fixed  grow-bar          amount    pct */
  align-items: center;
  column-gap: 10px;
  row-gap: 0;
}
.etx-cell {
  padding: 7px 0;
}
.etx-rank {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(127, 119, 221, 0.10);
  color: var(--p-deep);
  font-weight: 700;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-feature-settings: "tnum";
}
.etx-sec-bar {
  width: 3px;
  height: 16px;
  border-radius: 1.5px;
}
.etx-c-name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.etx-grow-track {
  height: 7px;
  background: rgba(127, 119, 221, 0.06);
  border-radius: 4px;
  overflow: hidden;
}
.etx-grow-fill {
  height: 100%;
  background: linear-gradient(90deg, #7F77DD 0%, #5DC093 100%);
  border-radius: 4px;
  transition: width 0.6s var(--ease-standard);
}
.etx-c-amt {
  font-size: 13px;
  font-weight: 700;
  color: var(--p-deep);
  font-feature-settings: "tnum";
  text-align: right;
  white-space: nowrap;
}
.etx-row-u {
  font-size: 9px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  margin-left: 2px;
}
.etx-c-pct {
  font-size: 12px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  font-feature-settings: "tnum";
  text-align: right;
  min-width: 36px;
}


@media (max-width: 1100px) {
  .etx-kpi-band { grid-template-columns: 1fr 1fr; }
}
</style>
