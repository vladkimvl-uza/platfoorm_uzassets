<template>
  <div class="ec-backdrop" @click.self="$emit('close')">
    <div class="ec-modal">
      <UzaStateBlock v-if="loading && !detail" state="loading" />
      <UzaStateBlock v-else-if="error && !detail" state="error" variant="block" :text="error" />

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
            <button v-if="canEditEsg" class="ec-edit-btn" type="button" @click="editorOpen = true">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:5px"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>Редактировать
            </button>
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
                        <span v-if="canEditEsg && editingId === m.id" class="ec-metric-edit" @click.stop>
                          <input v-model="editVal" class="ec-metric-input" type="number" step="any"
                                 :disabled="savingId === m.id"
                                 @keydown.enter.prevent="saveEdit(m)" @keydown.esc.prevent="cancelEdit" />
                          <button class="ec-metric-iok" type="button" :disabled="savingId === m.id" @click="saveEdit(m)" title="Сохранить">✓</button>
                          <button class="ec-metric-ix" type="button" @click="cancelEdit" title="Отмена">×</button>
                        </span>
                        <span v-else class="ec-metric-val" :class="{ 'ec-metric-val-edit': canEditEsg }"
                              :title="canEditEsg ? 'Кликните, чтобы изменить значение' : ''"
                              @click.stop="canEditEsg && startEdit(m)">{{ fmtMetricValue(m.value, m.unit) }}</span>
                        <span v-if="m.target != null" class="ec-metric-target">/ цель {{ fmtMetricValue(m.target, m.unit) }}</span>
                      </div>
                      <div v-if="m.target_attainment_pct != null" class="ec-metric-att" :style="{ color: attColor(m.target_attainment_pct) }">
                        {{ m.target_attainment_pct.toFixed(0) }}%
                      </div>
                    </div>
                    <div v-if="m.target != null" class="ec-metric-bar">
                      <div class="ec-metric-bar-fill" :style="{ width: Math.min(100, m.target_attainment_pct || 0) + '%', backgroundColor: attBarFill(m.target_attainment_pct) }" />
                    </div>
                  </div>
                  <UzaStateBlock
                    v-if="!metricsFor(p.key).length"
                    state="empty"
                    variant="inline"
                    :text="`Нет метрик за ${detail.year}`"
                  />
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

  <ESGEditor
    v-if="editorOpen && detail"
    :company-id="companyId"
    :company-name="detail.company_name || detail.company_code"
    :year="currentYear ?? detail.year"
    :detail="detail"
    :issues="detail.issues"
    @close="editorOpen = false"
    @saved="onEditorSaved"
  />
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
import ESGEditor from "@/components/ESG/ESGEditor.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useAuthStore } from "@/stores/auth";
import { useToast } from "@/composables/useToast";
import { isModerationQueued } from "@/api/client";

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

// Редактирование ESG-показателей: открываем существующий редактор ESGEditor.
const auth = useAuthStore();
const canEditEsg = computed(() =>
  auth.isOwner || (auth.userRoles || []).includes("admin") || (auth.userPermissions || []).includes("esg.edit"),
);
const editorOpen = ref(false);
async function onEditorSaved() { await load(); }

// ─── Инлайн-редактирование значения метрики (клик по значению) ───
const toast = useToast();
const editingId = ref<string | null>(null);
const editVal = ref<string>("");
const savingId = ref<string | null>(null);
function startEdit(m: ESGMetricBrief) {
  if (!canEditEsg.value) return;
  editingId.value = m.id;
  editVal.value = m.value == null ? "" : String(m.value);
}
function cancelEdit() { editingId.value = null; }
async function saveEdit(m: ESGMetricBrief) {
  const raw = editVal.value.trim();
  const num = raw === "" ? null : Number(raw);
  if (raw !== "" && Number.isNaN(num)) { toast.error("Введите число"); return; }
  savingId.value = m.id;
  try {
    const res = await esgApi.upsertMetric({
      company_id: m.company_id, year: m.year, pillar: m.pillar,
      metric_code: m.metric_code, metric_name: m.metric_name,
      value: num, unit: m.unit, target: m.target,
      benchmark: m.benchmark, notes: m.notes,
    });
    editingId.value = null;
    if (isModerationQueued(res)) toast.info("Изменение отправлено на модерацию");
    else toast.success("Сохранено");
    await load();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось сохранить");
  } finally {
    savingId.value = null;
  }
}

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

/**
 * Цвет ЗАЛИВКИ бара target-attainment — мягкая пастель (единый стиль баров
 * портфеля). Отдельно от attColor, которая остаётся для ТЕКСТА % (читаемость).
 */
function attBarFill(p: number | null | undefined): string {
  if (p == null) return "#B8B7B0";
  if (p >= 100) return "#5DC093";
  if (p >= 75)  return "#93D3B0";
  if (p >= 50)  return "#EFB373";
  return "#E2807F";
}

const openIssues = computed(() =>
  (detail.value?.issues || []).filter((i) => i.status !== "closed").length,
);
</script>

<style scoped>
.ec-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: var(--z-overlay, 9000);
  display: flex;
  align-items: center;
  justify-content: center;
}
.ec-modal {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: min(1100px, 96vw);
  max-height: 92dvh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: modalIn .45s var(--ease-standard);
  overflow: hidden;
}
@keyframes modalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

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
.ec-edit-btn {
  display: inline-flex; align-items: center;
  padding: 6px 13px; border: none; border-radius: 9px;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff;
  font-size: 12.5px; font-weight: 600; font-family: inherit; cursor: pointer;
  box-shadow: 0 2px 10px rgba(108, 92, 231, .28);
  transition: transform .14s, box-shadow .14s, filter .14s;
}
.ec-edit-btn:hover { transform: translateY(-1px); filter: brightness(1.04); box-shadow: 0 4px 14px rgba(108, 92, 231, .4); }

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
  animation: cardIn .35s var(--ease-standard) backwards;
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
.ec-metric-val-edit { cursor: pointer; border-bottom: 1px dashed transparent; transition: border-color .14s, color .14s; }
.ec-metric-val-edit:hover { color: var(--p-deep, #534AB7); border-bottom-color: rgba(124, 111, 247, .5); }
.ec-metric-edit { display: inline-flex; align-items: center; gap: 4px; }
.ec-metric-input {
  width: 92px; box-sizing: border-box;
  border: 1.5px solid var(--p, #7C6FF7); border-radius: 7px;
  background: var(--bg2, #F8FAFC); padding: 3px 7px;
  font-size: 13px; font-family: inherit; color: var(--t1, #1E2A4A); outline: none;
}
.ec-metric-input:focus { box-shadow: 0 0 0 3px rgba(124, 111, 247, .14); }
.ec-metric-iok, .ec-metric-ix {
  width: 22px; height: 22px; flex-shrink: 0;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 700; font-family: inherit;
}
.ec-metric-iok { background: #1D9E75; color: #fff; }
.ec-metric-iok:disabled { opacity: .6; cursor: default; }
.ec-metric-ix { background: rgba(15, 23, 60, .08); color: var(--t2, #334155); }
.ec-metric-ix:hover { background: rgba(15, 23, 60, .14); }
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
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  transition: width .8s var(--ease-standard);
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
