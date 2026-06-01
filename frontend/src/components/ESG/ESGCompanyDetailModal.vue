<template>
  <div class="ec-backdrop" @click.self="$emit('close')">
    <div class="ec-modal">
      <div v-if="loading && !detail" class="ec-loading">Загрузка...</div>
      <div v-else-if="error && !detail" class="ec-error">{{ error }}</div>

      <template v-else-if="detail">
        <!-- Header -->
        <div class="ec-header">
          <div class="ec-header-l">
            <div class="ec-eyebrow">ESG · детали компании</div>
            <h2 class="ec-title">{{ detail.company_name || detail.company_code }}</h2>
            <div class="ec-meta">
              <span class="ec-co-code">{{ detail.company_code }}</span>
              <span v-if="detail.sector_code" class="ec-sector">{{ detail.sector_code }}</span>
              <span class="ec-meta-sep">·</span>
              <span>FY {{ detail.year }}</span>
            </div>
          </div>
          <div class="ec-header-r">
            <select
              v-if="detail.available_years.length > 1"
              :value="String(detail.year)"
              @change="onYearChange"
              class="ec-year-sel"
            >
              <option v-for="y in detail.available_years" :key="y" :value="y">{{ y }}</option>
            </select>
            <button class="ec-close" @click="$emit('close')">×</button>
          </div>
        </div>

        <!-- 3 pillar score cards -->
        <div class="ec-pillars">
          <div
            v-for="p in PILLAR_META"
            :key="p.key"
            class="ec-pillar"
            :style="{ '--stripe-color': p.color }"
          >
            <div class="ec-pillar-h">
              <span class="ec-pillar-letter" :style="{ background: p.color }">{{ p.key }}</span>
              <span class="ec-pillar-l">{{ p.label }}</span>
            </div>
            <div class="ec-pillar-score" :style="{ color: scoreColor(scoreFor(p.key)) }">
              {{ scoreFor(p.key) != null ? scoreFor(p.key)!.toFixed(0) : '—' }}
              <span v-if="scoreFor(p.key) != null" class="ec-pillar-of">/100</span>
            </div>
            <div class="ec-pillar-count">
              {{ metricsFor(p.key).length }} метрик
            </div>
          </div>

          <div class="ec-pillar ec-pillar-overall">
            <div class="ec-pillar-h">
              <span class="ec-pillar-letter" style="background: #1e2a4a">Σ</span>
              <span class="ec-pillar-l">Общий балл</span>
            </div>
            <div class="ec-pillar-score" :style="{ color: scoreColor(detail.overall_score) }">
              {{ detail.overall_score != null ? detail.overall_score.toFixed(0) : '—' }}
              <span v-if="detail.overall_score != null" class="ec-pillar-of">/100</span>
            </div>
            <div class="ec-pillar-count">
              среднее E·S·G
            </div>
          </div>
        </div>

        <!-- Body: 3-column metrics breakdown -->
        <div class="ec-body">
          <div class="ec-sec">
            <div class="ec-sec-h">Метрики по столпам</div>
            <div class="ec-metrics-grid">
              <div v-for="p in PILLAR_META" :key="p.key" class="ec-pillar-col">
                <div class="ec-col-h" :style="{ color: p.color }">
                  <span class="ec-col-dot" :style="{ background: p.color }" />
                  {{ p.label }}
                </div>
                <div class="ec-metric-list">
                  <div v-for="m in metricsFor(p.key)" :key="m.id" class="ec-metric">
                    <div class="ec-metric-h">
                      <span class="ec-metric-name">{{ m.metric_name }}</span>
                      <span class="ec-metric-code">{{ m.metric_code }}</span>
                    </div>
                    <div class="ec-metric-row">
                      <div class="ec-metric-v">
                        <span class="ec-metric-val">{{ fmtMetricValue(m.value, m.unit) }}</span>
                        <span v-if="m.target != null" class="ec-metric-target">/ цель {{ fmtMetricValue(m.target, m.unit) }}</span>
                      </div>
                      <div v-if="m.target_attainment_pct != null" class="ec-metric-att" :style="{ color: attColor(m.target_attainment_pct) }">
                        {{ m.target_attainment_pct.toFixed(0) }}%
                      </div>
                    </div>
                    <div v-if="m.target != null" class="ec-metric-bar">
                      <div class="ec-metric-bar-fill" :style="{ width: Math.min(100, m.target_attainment_pct || 0) + '%', background: attColor(m.target_attainment_pct) }" />
                    </div>
                  </div>
                  <div v-if="!metricsFor(p.key).length" class="ec-col-empty">
                    Нет метрик за {{ detail.year }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Issues -->
          <div v-if="detail.issues.length" class="ec-sec">
            <div class="ec-sec-h">
              Существенные вопросы и риски ·
              <span class="ec-sec-h-small">{{ openIssues }} открытых из {{ detail.issues.length }}</span>
            </div>
            <div class="ec-issue-list">
              <div
                v-for="i in detail.issues"
                :key="i.id"
                class="ec-issue"
                :style="{ '--stripe-color': severityMeta(i.severity).color }"
              >
                <div class="ec-issue-h">
                  <span class="ec-issue-pillar" :style="{ background: pillarMeta(i.pillar).color + '18', color: pillarMeta(i.pillar).color }">
                    {{ i.pillar }}
                  </span>
                  <span class="ec-issue-title">{{ i.title }}</span>
                  <span class="ec-issue-sev" :style="{ color: severityMeta(i.severity).color }">
                    {{ severityMeta(i.severity).label }}
                  </span>
                  <span class="ec-issue-status" :style="{ background: issueStatusMeta(i.status).color + '18', color: issueStatusMeta(i.status).color }">
                    {{ issueStatusMeta(i.status).label }}
                  </span>
                </div>
                <div v-if="i.description" class="ec-issue-d">{{ i.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  PILLAR_META,
  esgApi,
  fmtMetricValue,
  issueStatusMeta,
  pillarMeta,
  scoreColor,
  severityMeta,
  type ESGCompanyDetail,
  type ESGMetricBrief,
  type Pillar,
} from "@/api/esg";

const props = defineProps<{
  companyId: string;
  initialYear?: number | null;
}>();

defineEmits<{
  (e: "close"): void;
}>();

const detail = ref<ESGCompanyDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const currentYear = ref<number | null>(props.initialYear ?? null);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    detail.value = await esgApi.getCompanyDetail(
      props.companyId,
      currentYear.value ?? undefined,
    );
    currentYear.value = detail.value.year;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => props.companyId, load);

function onYearChange(e: Event) {
  const v = parseInt((e.target as HTMLSelectElement).value, 10);
  if (!isNaN(v)) {
    currentYear.value = v;
    load();
  }
}

function metricsFor(p: Pillar): ESGMetricBrief[] {
  if (!detail.value) return [];
  if (p === "E") return detail.value.metrics_e;
  if (p === "S") return detail.value.metrics_s;
  return detail.value.metrics_g;
}

function scoreFor(p: Pillar): number | null {
  if (!detail.value) return null;
  if (p === "E") return detail.value.e_score;
  if (p === "S") return detail.value.s_score;
  return detail.value.g_score;
}

function attColor(p: number | null | undefined): string {
  if (p == null) return "#94A3B8";
  if (p >= 100) return "#1D9E75";
  if (p >= 75)  return "#7DC4A0";
  if (p >= 50)  return "#EF9F27";
  return "#E24B4A";
}

const openIssues = computed(() =>
  (detail.value?.issues || []).filter((i) => i.status !== "closed").length,
);
</script>

<style scoped>
.ec-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ec-modal {
  background: var(--card-bg, rgba(255, 255, 255, 0.86));
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: min(1100px, 96vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: modalIn .45s cubic-bezier(0.34, 1.2, 0.64, 1);
  overflow: hidden;
}
@keyframes modalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

.ec-loading, .ec-error { padding: 50px 20px; text-align: center; font-size: 13px; color: rgba(15, 23, 60, .55); }
.ec-error { color: #E24B4A; }

.ec-header {
  padding: 18px 22px 14px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.ec-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: rgba(15, 23, 60, .55); }
.ec-title { font-size: 17px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1e2a4a); line-height: 1.3; letter-spacing: -.005em; }
.ec-meta { font-size: 11px; color: rgba(15, 23, 60, .55); margin-top: 4px; display: flex; gap: 6px; align-items: center; }
.ec-co-code { font-family: 'SF Mono', 'Menlo', monospace; background: rgba(15, 23, 60, .06); padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.ec-sector { background: rgba(127, 119, 221, .12); color: #7F77DD; padding: 1px 6px; border-radius: 3px; font-weight: 600; font-size: 10px; }
.ec-meta-sep { opacity: .4; }

.ec-header-r { display: flex; align-items: center; gap: 8px; }
.ec-year-sel {
  font: inherit;
  font-size: 11px;
  padding: 4px 9px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 5px;
  background: var(--bg1, #fff);
  font-feature-settings: 'tnum';
  outline: none;
  font-family: inherit;
}

.ec-close { background: transparent; border: none; font-size: 24px; color: rgba(15, 23, 60, .45); cursor: pointer; padding: 0 8px; }
.ec-close:hover { color: var(--t1, #1e2a4a); }

.ec-pillars {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 14px 22px;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
@media (max-width: 800px) { .ec-pillars { grid-template-columns: repeat(2, 1fr); } }

.ec-pillar {
  background: var(--bg2, #FAFAFD);
  border-radius: 9px;
  padding: 10px 12px 10px 18px;
  animation: cardIn .35s cubic-bezier(0.34, 1.2, 0.64, 1) backwards;
  position: relative; overflow: hidden;
  --ec-accent: #94A3B8;
}
.ec-pillar::before {
  content: ""; position: absolute;
  left: 6px; top: 12px; bottom: 12px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, var(--ec-accent));
  pointer-events: none;
}
@keyframes cardIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.ec-pillar:nth-child(2) { animation-delay: 60ms; }
.ec-pillar:nth-child(3) { animation-delay: 120ms; }
.ec-pillar:nth-child(4) { animation-delay: 180ms; }

.ec-pillar-overall { background: #1e2a4a; color: #fff; --ec-accent: #1e2a4a; }
.ec-pillar-overall .ec-pillar-l { color: rgba(255, 255, 255, .8); }
.ec-pillar-overall .ec-pillar-count { color: rgba(255, 255, 255, .55); }

.ec-pillar-h {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}
.ec-pillar-letter {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ec-pillar-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .65);
}
.ec-pillar-score {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -.025em;
  font-feature-settings: 'tnum';
}
.ec-pillar-of {
  font-size: 11px;
  opacity: .55;
  font-weight: 500;
  margin-left: 1px;
}
.ec-pillar-count { font-size: 10px; color: rgba(15, 23, 60, .55); }

.ec-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.ec-sec-h {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 8px;
}
.ec-sec-h-small {
  font-size: 10px;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: rgba(15, 23, 60, .65);
  margin-left: 4px;
}

.ec-metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
@media (max-width: 900px) { .ec-metrics-grid { grid-template-columns: 1fr; } }

.ec-pillar-col {
  background: var(--bg2, #FAFAFD);
  border-radius: 9px;
  padding: 12px;
}
.ec-col-h {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 8px;
}
.ec-col-dot { width: 8px; height: 8px; border-radius: 50%; }

.ec-metric-list { display: flex; flex-direction: column; gap: 8px; }

.ec-metric {
  background: var(--bg1, #fff);
  border-radius: 6px;
  padding: 8px 10px;
  border: 1px solid rgba(15, 23, 60, .04);
}
.ec-metric-h { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; gap: 8px; }
.ec-metric-name { font-size: 11.5px; font-weight: 500; color: var(--t1, #1e2a4a); }
.ec-metric-code {
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 9px;
  color: rgba(15, 23, 60, .45);
}

.ec-metric-row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.ec-metric-v { font-size: 11px; font-feature-settings: 'tnum'; }
.ec-metric-val { font-weight: 500; color: var(--t1, #1e2a4a); }
.ec-metric-target { font-size: 10px; color: rgba(15, 23, 60, .5); margin-left: 4px; }
.ec-metric-att {
  font-size: 12px;
  font-weight: 600;
  font-feature-settings: 'tnum';
}

.ec-metric-bar {
  margin-top: 6px;
  height: 4px;
  background: rgba(15, 23, 60, .06);
  border-radius: 2px;
  overflow: hidden;
}
.ec-metric-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width .8s cubic-bezier(0.34, 1.2, 0.64, 1);
}

.ec-col-empty {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .35);
  text-align: center;
  font-style: italic;
  padding: 16px;
}

.ec-issue-list { display: flex; flex-direction: column; gap: 8px; }
.ec-issue {
  background: var(--bg2, #FAFAFD);
  border-radius: 6px;
  padding: 9px 12px 9px 18px;
  position: relative; overflow: hidden;
}
.ec-issue::before {
  content: ""; position: absolute;
  left: 6px; top: 6px; bottom: 6px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, #94A3B8);
  pointer-events: none;
}
.ec-issue-h {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  font-size: 11px;
}
.ec-issue-pillar {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ec-issue-title { font-weight: 500; color: var(--t1, #1e2a4a); flex: 1; min-width: 0; }
.ec-issue-sev { font-size: 10px; font-weight: 600; }
.ec-issue-status {
  font-size: 9.5px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.ec-issue-d {
  font-size: 11px;
  color: rgba(15, 23, 60, .65);
  margin-top: 4px;
  line-height: 1.45;
}
</style>
