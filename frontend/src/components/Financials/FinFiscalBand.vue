<script setup lang="ts">
/**
 * FinFiscalBand — фискально-социальный ряд KPI Финансов (под основной полосой),
 * в обоих видах НСБУ/МСФО, ОДНОЙ строкой без горизонтального скролла:
 *   Субсидии · Спонсорство · Налог на прибыль · НДС (12% выручки) · Итоговый вклад.
 *
 * Субсидии/спонсорство — суммы годовых показателей (сырьё в сум). Налоги — из
 * exec-билдера (/financials/tax-contribution): income_tax/vat/total в млрд сум.
 */
import { computed, onMounted } from "vue";
import { fmtSubsidySum } from "@/api/subsidies";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";

interface TaxKpi {
  income_tax?: number | null;
  vat?: number | null;
  total?: number | null;
  yoy_income_tax_pct?: number | null;
  yoy_vat_pct?: number | null;
  yoy_total_pct?: number | null;
}

const props = defineProps<{
  year: number;
  subsidiesTotal?: number | null;   // raw сум
  sponsorshipTotal?: number | null; // raw сум
  taxKpi?: TaxKpi | null;
}>();
const emit = defineEmits<{ (e: "open-subsidies"): void }>();

onMounted(ensureFinancialsCss);

const subFmt = computed(() => fmtSubsidySum(props.subsidiesTotal ?? null));
const spoFmt = computed(() => fmtSubsidySum(props.sponsorshipTotal ?? null));

function fmtBln(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toLocaleString("ru", { maximumFractionDigits: 1 });
}
function fmtYoY(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}% к ${props.year - 1}`;
}
function yoyColor(v: number | null | undefined): string {
  if (v == null) return "var(--t3, #94A3B8)";
  if (v >= 5) return "#1D9E75"; if (v >= -5) return "#EF9F27"; return "#E24B4A";
}
</script>

<template>
  <div class="ffb">
    <div class="ffb-h">Фискально-социальный вклад · FY {{ year }}</div>
    <div class="ffb-band">
      <!-- Субсидии -->
      <div class="ffb-kpi ffb-clk" style="--accent:#378ADD; --d:0ms" role="button" tabindex="0"
           @click="emit('open-subsidies')" @keydown.enter="emit('open-subsidies')" @keydown.space.prevent="emit('open-subsidies')"
           title="Реестр субсидий">
        <div class="ffb-lbl">Субсидии</div>
        <div class="ffb-val">{{ subFmt.value }}<span class="ffb-u">{{ subFmt.unit || 'сум' }}</span></div>
        <div class="ffb-sub">реестр по компаниям и секторам</div>
      </div>
      <!-- Спонсорство -->
      <div class="ffb-kpi" style="--accent:#7C6FF7; --d:70ms">
        <div class="ffb-lbl">Спонсорство</div>
        <div class="ffb-val">{{ spoFmt.value }}<span class="ffb-u">{{ spoFmt.unit || 'сум' }}</span></div>
        <div class="ffb-sub">благотворительность и спонсорство</div>
      </div>
      <!-- Налог на прибыль -->
      <div class="ffb-kpi" style="--accent:#3B82F6; --d:140ms">
        <div class="ffb-lbl">Налог на прибыль</div>
        <div class="ffb-val">{{ fmtBln(taxKpi?.income_tax) }}<span class="ffb-u">млрд сум</span></div>
        <div class="ffb-sub" :style="{ color: yoyColor(taxKpi?.yoy_income_tax_pct) }">{{ fmtYoY(taxKpi?.yoy_income_tax_pct) || '—' }}</div>
      </div>
      <!-- НДС -->
      <div class="ffb-kpi" style="--accent:#1D9E75; --d:210ms">
        <div class="ffb-lbl">НДС (12% выручки)</div>
        <div class="ffb-val">{{ fmtBln(taxKpi?.vat) }}<span class="ffb-u">млрд сум</span></div>
        <div class="ffb-sub" :style="{ color: yoyColor(taxKpi?.yoy_vat_pct) }">{{ fmtYoY(taxKpi?.yoy_vat_pct) || '—' }}</div>
      </div>
      <!-- Итоговый налоговый вклад -->
      <div class="ffb-kpi ffb-hl" style="--accent:#EF9F27; --d:280ms">
        <div class="ffb-lbl">Итоговый налоговый вклад</div>
        <div class="ffb-val">{{ fmtBln(taxKpi?.total) }}<span class="ffb-u">млрд сум</span></div>
        <div class="ffb-sub" :style="{ color: yoyColor(taxKpi?.yoy_total_pct) }">{{ fmtYoY(taxKpi?.yoy_total_pct) || '—' }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ffb { margin-top: 12px; }
.ffb-h { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin: 0 2px 8px; }
/* 5 карточек СТРОГО в ОДИН ряд на всех десктоп-ширинах (minmax(0,1fr) сжимает,
   число ужимается clamp'ом) — без переноса и без горизонтального скролла.
   Перенос только планшет/телефон: ≤720 → 2, ≤460 → 1. Выровнено под верхний
   KPI-блок (раньше рвалось уже на 1180 — рассинхрон с полосой). */
.ffb-band { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 720px)  { .ffb-band { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 460px)  { .ffb-band { grid-template-columns: 1fr; } }

.ffb-kpi {
  position: relative; overflow: hidden; min-width: 0;
  background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px; padding: 13px 14px 11px;
  box-shadow: 0 2px 12px rgba(15,23,60,.07), 0 1px 3px rgba(15,23,60,.04);
  display: flex; flex-direction: column; min-height: 88px;
  animation: finKpiCardIn .55s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) var(--d, 0ms) both;
}
.ffb-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); border-radius: 14px 14px 0 0; }
.ffb-hl { background: linear-gradient(135deg, rgba(239,159,39,.10), rgba(239,159,39,.03)); box-shadow: 0 0 0 1.5px rgba(239,159,39,.35), 0 8px 22px rgba(239,159,39,.16); }
.ffb-clk { cursor: pointer; transition: transform .16s, box-shadow .16s, border-color .16s; outline: none; }
.ffb-clk:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(15,23,60,.10); border-color: rgba(127,119,221,.30); }
.ffb-clk:focus-visible { box-shadow: 0 0 0 2px rgba(127,119,221,.45); }

.ffb-lbl { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted));
  margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ffb-val { font-size: clamp(16px, 1.5vw, 28px); font-weight: 400; letter-spacing: -.03em; line-height: 1; color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 4px; margin: 2px 0 4px; white-space: nowrap; min-width: 0; }
.ffb-u { font-size: 10.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.ffb-sub { font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted)); font-feature-settings: 'tnum';
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
</style>
