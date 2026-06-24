<script setup lang="ts">
/**
 * ESGMaturityProfileModal — профиль ESG-зрелости компании.
 * Radar по 6 измерениям (из heatmap.dim_stage) + разбивка по стадиям.
 * Данные приходят пропсом — без обращения к бэкенду.
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { Chart } from "@/utils/chartjsRegister";
import type { ESGMaturityCompany } from "@/api/esg";

const props = defineProps<{ company: ESGMaturityCompany | null }>();
const emit = defineEmits<{ (e: "close"): void }>();

const DIMS = [
  { key: "D1", label: "ISO-системы", max: 4, desc: "Системы менеджмента ISO 14001 / 45001 / 50001" },
  { key: "D2", label: "Отчётность", max: 4, desc: "ESG-отчётность: GRI/SASB → IFRS SDS → независимый assurance" },
  { key: "D3", label: "Рейтинги", max: 4, desc: "Независимые ESG-рейтинги агентств (Fitch / S&P / CDP)" },
  { key: "D4", label: "Климат", max: 4, desc: "Стратегия: выбросы Scope 1–2 → риски → декарбонизация → реализация" },
  { key: "D5", label: "Риски", max: 4, desc: "ESG-риски: double-materiality → оценка → интеграция в ERM" },
  { key: "D6", label: "KPI", max: 4, desc: "ESG-KPI устойчивого развития на уровне менеджмента" },
];

function emsColor(e: number): string { return e >= 70 ? "#1D9E75" : e >= 40 ? "#D97706" : "#E24B4A"; }
function stageOf(key: string): number { return props.company?.dim_stage?.[key] ?? 0; }

const canvas = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

function render() {
  if (!canvas.value || !props.company) return;
  const data = DIMS.map((d) => Math.round((stageOf(d.key) / d.max) * 100));
  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(canvas.value, {
    type: "radar",
    data: {
      labels: DIMS.map((d) => d.label),
      datasets: [{
        data,
        backgroundColor: "rgba(124,111,247,.16)",
        borderColor: "#7C6FF7",
        borderWidth: 2,
        pointBackgroundColor: "#6C5CE7",
        pointBorderColor: "#fff",
        pointBorderWidth: 1.5,
        pointRadius: 4,
        pointHoverRadius: 6,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 700 },
      scales: {
        r: {
          min: 0, max: 100, beginAtZero: true,
          ticks: { display: false, stepSize: 25 },
          grid: { color: "#ECEAF5" },
          angleLines: { color: "#E7E5F2" },
          pointLabels: { font: { size: 11, weight: 600 }, color: "#475569" },
        },
      },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c: { raw: unknown }) => `${c.raw}%` } } },
    },
  } as never);
}

watch(() => props.company, async (c) => { if (c) { await nextTick(); render(); } }, { immediate: true });
onBeforeUnmount(() => { if (chart) chart.destroy(); });

const ems = computed(() => props.company?.ems ?? 0);
</script>

<template>
  <ModalShell :open="!!company" size="lg" @close="emit('close')">
    <template #header v-if="company">
      <div class="mp-head">
        <div>
          <div class="mp-eyebrow">{{ company.sector_name || company.company_code }} · ESG-зрелость</div>
          <div class="mp-title">{{ company.company_name || company.company_code }}</div>
        </div>
        <div class="mp-ems" :style="{ color: emsColor(ems) }">
          <span class="mp-ems-n">{{ Math.round(ems) }}</span><span class="mp-ems-u">EMS</span>
        </div>
      </div>
    </template>

    <div v-if="company" class="mp-body">
      <div class="mp-radar"><canvas ref="canvas"></canvas></div>
      <div class="mp-dims">
        <div v-for="d in DIMS" :key="d.key" class="mp-dim">
          <div class="mp-dim-top">
            <span class="mp-dim-l">{{ d.label }}</span>
            <span class="mp-dim-st" :class="'st'+stageOf(d.key)">стадия {{ stageOf(d.key) }} / {{ d.max }}</span>
          </div>
          <div class="mp-dim-bar"><i :style="{ width: (stageOf(d.key)/d.max*100)+'%' }"></i></div>
          <div class="mp-dim-desc">{{ d.desc }}</div>
        </div>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.mp-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%; }
.mp-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.mp-title { font-size: 18px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; }
.mp-ems { display: inline-flex; align-items: baseline; gap: 5px; }
.mp-ems-n { font-size: 30px; font-weight: 700; font-feature-settings: 'tnum'; }
.mp-ems-u { font-size: 11px; font-weight: 600; color: var(--t3, #94A3B8); }

.mp-body { display: grid; grid-template-columns: 320px 1fr; gap: 22px; }
.mp-radar { height: 300px; position: relative; }
.mp-dims { display: flex; flex-direction: column; gap: 12px; }
.mp-dim { }
.mp-dim-top { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.mp-dim-l { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mp-dim-st { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 5px; }
.mp-dim-st.st0 { background: #F1F5F9; color: #94A3B8; }
.mp-dim-st.st1 { background: #FEF9C3; color: #D97706; }
.mp-dim-st.st2 { background: #E0F2FE; color: #378ADD; }
.mp-dim-st.st3 { background: #EDE9FE; color: #6C5CE7; }
.mp-dim-st.st4 { background: #DCFCE7; color: #1D9E75; }
.mp-dim-bar { height: 5px; border-radius: 3px; background: #ECEAF5; overflow: hidden; margin: 5px 0 4px; }
.mp-dim-bar i { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #8B7FF0, #6C5CE7); transition: width .5s var(--ease-standard, ease); }
.mp-dim-desc { font-size: 10.5px; color: var(--t3, #94A3B8); line-height: 1.35; }

@media (max-width: 720px) { .mp-body { grid-template-columns: 1fr; } .mp-radar { height: 260px; } }
@media (min-width: 2200px) {
  .mp-title { font-size: 24px; } .mp-ems-n { font-size: 40px; }
  .mp-body { grid-template-columns: 420px 1fr; gap: 30px; } .mp-radar { height: 380px; }
  .mp-dim-l { font-size: 15px; } .mp-dim-desc { font-size: 13px; }
}
</style>
