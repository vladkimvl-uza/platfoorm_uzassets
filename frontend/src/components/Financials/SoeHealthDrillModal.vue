<script setup lang="ts">
/**
 * SoeHealthDrillModal — детали SOE Health Check по компании: каждый
 * коэффициент со значением, зоной и порог-шкалой (5 сегментов, маркер
 * позиции), блоки «Тянут вниз» / «Сильные стороны» (стиль KPI good/bad).
 */
import { computed } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import Odometer from "@/components/Odometer.vue";
import type { SoeCompany, SoeRatio } from "@/components/Financials/SoeHealthBoard.vue";

const props = defineProps<{
  open: boolean;
  company: SoeCompany | null;
  zones: { key: string; label: string; color: string }[];
  year: number;
  standard: string;
}>();
const emit = defineEmits<{ (e: "close"): void }>();

function zoneColor(band: number | null): string {
  if (band == null) return "#94A3B8";
  return props.zones[Math.min(band, 5) - 1]?.color || "#94A3B8";
}
function zoneLabel(band: number | null): string {
  if (band == null) return "н/д";
  return props.zones[Math.min(band, 5) - 1]?.label || "н/д";
}
function fmtVal(r: SoeRatio): string {
  if (r.value == null) return r.note || "нет данных";
  if (r.fmt === "pct") return (r.value * 100).toFixed(1) + "%";
  if (r.fmt === "days") return Math.round(r.value) + " дн";
  return r.value.toFixed(2) + "×";
}
function fmtThrVal(r: SoeRatio, t: number): string {
  return r.fmt === "pct" ? Math.round(t * 100) + "%" : String(t);
}
// позиция маркера на шкале: центр сегмента бенда (5 сегментов по 20%)
function markerPos(r: SoeRatio): number | null {
  if (r.band == null) return null;
  return (r.band - 1) * 20 + 10;
}

const rows = computed(() => props.company?.ratios || []);
const worst = computed(() =>
  rows.value.filter((r) => r.band != null && r.band >= 4)
    .sort((a, b) => (b.band || 0) - (a.band || 0)).slice(0, 3));
const best = computed(() =>
  rows.value.filter((r) => r.band != null && r.band <= 2)
    .sort((a, b) => (a.band || 9) - (b.band || 9)).slice(0, 3));
</script>

<template>
  <ModalShell :open="open && !!company" size="lg" @close="emit('close')">
    <template v-if="company" #header>
      <div class="shd-head">
        <div class="shd-head-l">
          <div class="shd-eyebrow">SOE Health Check · {{ standard }} · FY {{ year }}</div>
          <h2 class="shd-title">
            <span class="shd-dot" :style="{ background: company.sector_color || '#94A3B8' }" />
            {{ company.name || company.code }}
          </h2>
          <div class="shd-meta">{{ company.sector_name || '—' }} · оценено коэффициентов: {{ company.available }} из {{ company.ratios.length }}</div>
        </div>
        <div v-if="company.overall != null" class="shd-score" :style="{ background: company.zone?.color || '#94A3B8' }">
          <div class="shd-score-v"><Odometer :value="company.overall.toFixed(1)" /></div>
          <div class="shd-score-l">{{ company.zone?.label }}</div>
        </div>
      </div>
    </template>

    <div v-if="company" class="shd-body">
      <!-- Сильные/слабые — стиль KPI-панелей good/bad -->
      <div v-if="worst.length || best.length" class="shd-grid2">
        <div class="shd-w">
          <div class="shd-w-t" style="color:#E24B4A">↓ Тянут вниз</div>
          <div v-for="r in worst" :key="r.key" class="shd-ind bad">
            <span class="shd-ind-name">{{ r.label }}</span>
            <b :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</b>
          </div>
          <div v-if="!worst.length" class="shd-none">нет критичных зон</div>
        </div>
        <div class="shd-w">
          <div class="shd-w-t" style="color:#1D9E75">↑ Сильные стороны</div>
          <div v-for="r in best" :key="r.key" class="shd-ind good">
            <span class="shd-ind-name">{{ r.label }}</span>
            <b :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</b>
          </div>
          <div v-if="!best.length" class="shd-none">—</div>
        </div>
      </div>

      <!-- Все коэффициенты с порог-шкалами -->
      <div class="shd-list">
        <div v-for="(r, i) in rows" :key="r.key" class="shd-row" :style="{ '--d': (i * 40) + 'ms' }">
          <div class="shd-row-top">
            <span class="shd-r-label" :title="r.formula">{{ r.label }}</span>
            <span class="shd-r-group">{{ r.group }}</span>
            <span class="shd-r-val" :style="{ color: zoneColor(r.band) }">{{ fmtVal(r) }}</span>
            <span class="shd-r-zone" :style="{ color: zoneColor(r.band), background: zoneColor(r.band) + '18' }">{{ zoneLabel(r.band) }}</span>
          </div>
          <div class="shd-scale">
            <div v-for="(z, zi) in zones" :key="z.key" class="shd-seg" :style="{ background: z.color }"
                 :title="z.label + (zi < 4 ? ' · порог ' + fmtThrVal(r, r.thresholds[zi]) : '')" />
            <div v-if="markerPos(r) != null" class="shd-marker" :style="{ left: markerPos(r) + '%' }" />
          </div>
          <div class="shd-thr">
            <span v-for="(t, ti) in r.thresholds" :key="ti" :style="{ left: ((ti + 1) * 20) + '%' }">{{ fmtThrVal(r, t) }}</span>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <span class="shd-note">Светофорная оценка финансовой устойчивости · пороги настраиваемые · ниже балл = устойчивее</span>
      <button class="shd-ok" type="button" @click="emit('close')">Понятно</button>
    </template>
  </ModalShell>
</template>

<style scoped>
.shd-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; width: 100%; }
.shd-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.shd-title { font-size: 17px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1E2A4A); display: flex; align-items: center; gap: 8px; }
.shd-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.shd-meta { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 4px; }
.shd-score {
  border-radius: 13px; color: #fff; padding: 9px 16px; text-align: center; flex-shrink: 0;
  box-shadow: 0 6px 18px rgba(15,23,60,.18); animation: shdPop .45s var(--ease-standard, ease) both;
}
@keyframes shdPop { from { opacity: 0; transform: scale(.9); } to { opacity: 1; transform: scale(1); } }
.shd-score-v { font-size: 24px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
.shd-score-l { font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-top: 3px; opacity: .92; }

.shd-body { display: flex; flex-direction: column; gap: 16px; }
.shd-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 700px) { .shd-grid2 { grid-template-columns: 1fr; } }
.shd-w { background: var(--bg2, #FAFAFD); border-radius: 11px; padding: 11px 13px; }
.shd-w-t { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 7px; }
.shd-ind { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 6px 10px; border-radius: 7px; margin-bottom: 4px; position: relative; overflow: hidden; }
.shd-ind::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; }
.shd-ind.bad { background: rgba(226,75,74,.05); }
.shd-ind.bad::before { background: #E24B4A; }
.shd-ind.good { background: rgba(29,158,117,.05); }
.shd-ind.good::before { background: #1D9E75; }
.shd-ind-name { font-size: 11.5px; color: var(--t1, #1E2A4A); font-weight: 500; }
.shd-ind b { font-size: 12px; font-variant-numeric: tabular-nums; }
.shd-none { font-size: 11px; color: #C4C8D4; font-style: italic; }

.shd-list { display: flex; flex-direction: column; gap: 13px; }
.shd-row { animation: shdRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes shdRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.shd-row-top { display: flex; align-items: baseline; gap: 9px; margin-bottom: 5px; }
.shd-r-label { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); cursor: help; border-bottom: 1px dashed rgba(148,163,184,.5); }
.shd-r-group { font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.shd-r-val { margin-left: auto; font-size: 13px; font-weight: 700; font-variant-numeric: tabular-nums; }
.shd-r-zone { font-size: 9.5px; font-weight: 700; border-radius: 6px; padding: 2px 7px; }
.shd-scale { position: relative; display: flex; gap: 2px; height: 8px; }
.shd-seg { flex: 1; border-radius: 3px; opacity: .32; transition: opacity .15s; }
.shd-row:hover .shd-seg { opacity: .5; }
.shd-marker {
  position: absolute; top: -3px; width: 3px; height: 14px; border-radius: 2px;
  background: var(--t1, #1E2A4A); box-shadow: 0 0 0 2.5px #fff, 0 1px 4px rgba(15,23,60,.35);
  transform: translateX(-50%); transition: left .5s var(--ease-standard, ease);
}
.shd-thr { position: relative; height: 12px; margin-top: 3px; }
.shd-thr span {
  position: absolute; transform: translateX(-50%);
  font-size: 8.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; white-space: nowrap;
}

.shd-note { margin-right: auto; font-size: 10.5px; color: var(--t3, #94A3B8); font-style: italic; }
.shd-ok {
  font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  border: none; border-radius: 10px; padding: 9px 20px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s;
}
.shd-ok:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
</style>
