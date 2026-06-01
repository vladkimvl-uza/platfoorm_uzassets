<script setup lang="ts">
/**
 * ExecDashEconomicEffectBlock — Row 2.55.
 * Экономический эффект портфеля.
 *
 *   - 4 KPI band (kpi2 fin-shimmer pattern):
 *     · Реализовано (факт) — зелёный
 *     · План (потенциал) — амбер
 *     · Остаток до плана — фиолетовый
 *     · % реализации — синий
 *   - Top-10 проектов с эконом. эффектом
 *
 * Empty state когда has_data=false (нет projects.extra.economicEffect).
 */
import { computed, ref } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useSectorMeta } from "@/utils/sectorMeta";
import EconomicEffectDrillModal, { type EeKind } from "@/components/UZA/EconomicEffectDrillModal.vue";

const exec = useExecutiveDashboard();
const secMeta = useSectorMeta();

const block = computed(() => exec.data.value?.economic_effect || null);
const kpi = computed(() => block.value?.kpi || null);
const projects = computed(() => block.value?.top_projects || []);

const sectorColor: Record<string, string> = {
  mining: "#7F77DD",
  oilgas: "#1D9E75",
  energy: "#EF9F27",
  transport: "#378ADD",
  other: "#888780",
};

const sectorLabel = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {};
  const byCode = secMeta.byCodeMap.value;
  for (const code of Object.keys(byCode)) {
    map[code] = byCode[code as keyof typeof byCode]?.label || code;
  }
  return map;
});

// Pack 7.33: drill-down модалка для 4 KPI карточек
const drillKind = ref<EeKind | null>(null);
function openDrill(kind: EeKind) {
  if (!kpi.value || !kpi.value.has_data) return;
  drillKind.value = kind;
}
function closeDrill() { drillKind.value = null; }
function onKpiKeydown(e: KeyboardEvent, kind: EeKind) {
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    openDrill(kind);
  }
}

function fmtMlrd(v: number): string {
  if (v == null || isNaN(v)) return "—";
  if (v >= 1000) return (v / 1000).toFixed(1) + " трлн";
  if (v >= 100) return Math.round(v).toLocaleString("ru-RU");
  if (v >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

function pctColor(pct: number): string {
  if (pct >= 75) return "#1D9E75";
  if (pct >= 40) return "#EF9F27";
  return "#E24B4A";
}
</script>

<template>
  <section class="ed-card eee-card">
    <header class="eee-hdr">
      <div class="eee-hdr-l">
        <div class="eee-eyebrow">Экономический эффект портфеля</div>
        <div class="eee-sub">FY {{ exec.year.value }} · влияние программы трансформации</div>
      </div>
      <div v-if="kpi && kpi.has_data" class="eee-hdr-r">
        <span class="eee-stat">{{ kpi.total_count }} проектов</span>
      </div>
    </header>

    <!-- Empty state -->
    <div v-if="!kpi || !kpi.has_data" class="eee-empty">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 14l4-4 4 4 6-6" />
      </svg>
      <div class="eee-empty-title">Эконом. эффект не настроен</div>
      <div class="eee-empty-text">
        Откройте проект в Workspace → раздел «Экономический эффект» —<br>
        укажите plannedValue / realizedValue для отслеживания вклада.
      </div>
    </div>

    <template v-else>
      <!-- 4 KPI band -->
      <div class="eee-kpi-band">
        <div
          class="eee-kpi eee-kpi--clickable"
          style="--accent: #1D9E75;"
          role="button"
          tabindex="0"
          @click="openDrill('realized')"
          @keydown="onKpiKeydown($event, 'realized')"
          title="Подробнее: Реализованный эффект"
        >
          <div class="eee-kpi-lbl">Реализовано (факт)</div>
          <div class="eee-kpi-val" style="color: #1D9E75;">
            {{ fmtMlrd(kpi.realized_sum) }}<span class="eee-kpi-u">млрд сум</span>
          </div>
          <div class="eee-kpi-sub">{{ kpi.done_count }} завершённых проектов
            <template v-if="kpi.active_count > 0"> · {{ kpi.active_count }} в процессе</template>
          </div>
        </div>

        <div
          class="eee-kpi eee-kpi--clickable"
          style="--accent: #EF9F27;"
          role="button"
          tabindex="0"
          @click="openDrill('planned')"
          @keydown="onKpiKeydown($event, 'planned')"
          title="Подробнее: Плановый эффект"
        >
          <div class="eee-kpi-lbl">План (потенциал)</div>
          <div class="eee-kpi-val" style="color: #EF9F27;">
            {{ fmtMlrd(kpi.planned_sum) }}<span class="eee-kpi-u">млрд сум</span>
          </div>
          <div class="eee-kpi-sub">{{ kpi.total_count }} проектов с целевым эффектом</div>
        </div>

        <div
          class="eee-kpi eee-kpi--clickable"
          style="--accent: #7F77DD;"
          role="button"
          tabindex="0"
          @click="openDrill('pipeline')"
          @keydown="onKpiKeydown($event, 'pipeline')"
          title="Подробнее: Остаток до плана"
        >
          <div class="eee-kpi-lbl">Остаток до плана</div>
          <div class="eee-kpi-val" style="color: #7F77DD;">
            {{ fmtMlrd(kpi.pipeline_sum) }}<span class="eee-kpi-u">млрд сум</span>
          </div>
          <div class="eee-kpi-sub">∑ (план − факт)</div>
        </div>

        <div
          class="eee-kpi eee-kpi--clickable"
          style="--accent: #378ADD;"
          role="button"
          tabindex="0"
          @click="openDrill('conversion')"
          @keydown="onKpiKeydown($event, 'conversion')"
          title="Подробнее: Процент реализации"
        >
          <div class="eee-kpi-lbl">% реализации</div>
          <div class="eee-kpi-val" style="color: #378ADD;">
            {{ kpi.conversion_pct }}<span class="eee-kpi-u">%</span>
          </div>
          <div class="eee-kpi-sub">факт ÷ план</div>
        </div>
      </div>

      <!-- Top projects -->
      <div v-if="projects.length" class="eee-projects">
        <div class="eee-projects-hdr">Топ проектов по реализованному эффекту</div>
        <div class="eee-rows">
          <div
            v-for="p in projects"
            :key="p.project_id"
            class="eee-row"
          >
            <div class="eee-bar" :style="{ background: sectorColor[p.sector] || '#888780' }" />
            <div class="eee-row-info">
              <div class="eee-row-title" :title="p.title">{{ p.title }}</div>
              <div class="eee-row-co">{{ p.company_name }}</div>
            </div>
            <div class="eee-row-vals">
              <div class="eee-row-fact">{{ fmtMlrd(p.realized_value) }}</div>
              <div class="eee-row-plan">из {{ fmtMlrd(p.planned_value) }}</div>
            </div>
            <div class="eee-row-pct" :style="{ color: pctColor(p.pct_realized) }">
              {{ p.pct_realized }}%
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Pack 7.33: drill-down модалка -->
    <EconomicEffectDrillModal
      v-if="drillKind && kpi && kpi.has_data"
      :kind="drillKind"
      :kpi="kpi"
      :projects="projects"
      :year="block?.year ?? exec.year.value"
      :sector-color="sectorColor"
      :sector-label="sectorLabel"
      @close="closeDrill"
    />
  </section>
</template>

<style scoped>
.eee-card {
  padding: 14px 14px 14px;
  background: var(--bg1, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  margin-top: 14px;
}

.eee-hdr {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  padding-bottom: 12px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
}
.eee-eyebrow {
  font-size: 13px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 3px;
}
.eee-sub {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.04em;
}
.eee-stat {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  background: rgba(127, 119, 221, 0.07);
  padding: 4px 10px;
  border-radius: 8px;
}

/* Empty state */
.eee-empty {
  padding: 50px 20px;
  text-align: center;
  color: #B4B2A9;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}
.eee-empty-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  margin-top: 6px;
}
.eee-empty-text {
  font-size: 12px;
  line-height: 1.5;
  color: #B4B2A9;
}

/* KPI band */
.eee-kpi-band {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 14px 0;
}
.eee-kpi {
  background: linear-gradient(135deg, rgba(255,255,255,0.5), rgba(248, 247, 251, 0.9));
  border-radius: 10px;
  padding: 14px 12px;
  position: relative;
  overflow: hidden;
  animation: eeeKpiIn 0.55s var(--ease-standard) both;
}
.eee-kpi::after {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--accent, #888);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none; z-index: 2;
}
.eee-kpi::before {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(115deg, transparent 38%, rgba(255,255,255,0.4) 50%, transparent 62%);
  transform: translateX(-100%);
  animation: eeeKpiSheen 4s ease-in-out infinite;
  pointer-events: none;
}
/* Pack 7.33: clickable EE card */
.eee-kpi--clickable {
  cursor: pointer;
  transition: transform 0.16s ease, box-shadow 0.16s ease;
  outline: none;
}
.eee-kpi--clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 22px rgba(15, 23, 60, 0.08);
}
.eee-kpi--clickable:focus-visible {
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.45);
}
.eee-kpi--clickable:active {
  transform: translateY(-1px);
}
.eee-kpi-lbl {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 600;
}
.eee-kpi-val {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  font-feature-settings: "tnum";
  margin-top: 4px;
  line-height: 1.1;
}
.eee-kpi-u {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  margin-left: 4px;
  letter-spacing: 0;
}
.eee-kpi-sub {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  margin-top: 6px;
  font-weight: 500;
}

/* Top projects list */
.eee-projects-hdr {
  font-size: 11px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.06);
}
.eee-rows {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.eee-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 8px;
  border-radius: 8px;
  transition: background 0.15s;
}
.eee-row:hover {
  background: rgba(127, 119, 221, 0.05);
}
.eee-bar {
  width: 3px;
  height: 18px;
  border-radius: 1.5px;
  flex-shrink: 0;
}
.eee-row-info {
  flex: 1;
  min-width: 0;
}
.eee-row-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.eee-row-co {
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
}
.eee-row-vals {
  text-align: right;
  flex-shrink: 0;
  min-width: 100px;
}
.eee-row-fact {
  font-size: 13px;
  font-weight: 700;
  color: var(--green);
  font-feature-settings: "tnum";
}
.eee-row-plan {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  margin-top: 1px;
}
.eee-row-pct {
  font-size: 13px;
  font-weight: 700;
  font-feature-settings: "tnum";
  min-width: 50px;
  text-align: right;
  flex-shrink: 0;
}

@keyframes eeeKpiIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
@keyframes eeeKpiSheen {
  0% { transform: translateX(-100%); }
  60%, 100% { transform: translateX(250%); }
}

@media (max-width: 1100px) {
  .eee-kpi-band { grid-template-columns: 1fr 1fr; }
}
</style>
