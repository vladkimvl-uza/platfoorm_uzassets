<script setup lang="ts">
/**
 * ESGEditor — редактор ESG показателей компании (модалка).
 *
 * Две секции:
 *   • «Метрики» — ESG-метрики по 3 столпам (E/S/G): значение, ед., цель,
 *     бенчмарк, заметки → esgApi.upsertMetric / deleteMetric (год-scoped)
 *   • «Риски» — ESG-проблемы: столп, заголовок, серьёзность, статус →
 *     esgApi.createIssue / updateIssue / deleteIssue (не year-scoped)
 *
 * Бэкенд гейтит esg.edit + пишет историю/модерацию (202 → на модерацию).
 * Данные общие с /esg → после сейва эмитим saved, родитель рефетчит.
 */
import { reactive, ref, computed } from "vue";
import {
  esgApi, PILLAR_META, SEVERITY_META, ISSUE_STATUS_META,
  type Pillar, type Severity, type IssueStatus,
  type ESGMetricBrief, type ESGIssueBrief,
} from "@/api/esg";
import { isModerationQueued } from "@/api/client";

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
  detail: any | null;          // ESGCompanyDetail (metrics_e/s/g)
  issues: ESGIssueBrief[];
}>();

const emit = defineEmits<{ close: []; saved: [] }>();

const section = ref<"metrics" | "issues">("metrics");
const saving = ref(false);
const err = ref<string | null>(null);
const queued = ref(false);

function pillarMeta(p: Pillar) { return PILLAR_META.find(x => x.key === p) || PILLAR_META[0]; }
function sevMeta(s: Severity | null) { return SEVERITY_META.find(x => x.key === s) || { label: "—", color: "#94A3B8" }; }
function statusMeta(s: IssueStatus) { return ISSUE_STATUS_META.find(x => x.key === s) || ISSUE_STATUS_META[0]; }

// ─── МЕТРИКИ ──────────────────────────────────────────────────────
const localMetrics = ref<ESGMetricBrief[]>([
  ...(props.detail?.metrics_e || []),
  ...(props.detail?.metrics_s || []),
  ...(props.detail?.metrics_g || []),
]);
const metricsByPillar = computed(() => {
  const out: Record<Pillar, ESGMetricBrief[]> = { E: [], S: [], G: [] };
  for (const m of localMetrics.value) (out[m.pillar as Pillar] ||= []).push(m);
  return out;
});

const showMetricForm = ref(false);
const editingMetric = ref<ESGMetricBrief | null>(null);
const mForm = reactive({
  pillar: "E" as Pillar, metric_code: "", metric_name: "",
  value: "" as string | number, unit: "", target: "" as string | number,
  benchmark: "" as string | number, notes: "",
});

function openAddMetric(): void {
  editingMetric.value = null;
  Object.assign(mForm, { pillar: "E", metric_code: "", metric_name: "", value: "", unit: "", target: "", benchmark: "", notes: "" });
  err.value = null; showMetricForm.value = true;
}
function openEditMetric(m: ESGMetricBrief): void {
  editingMetric.value = m;
  Object.assign(mForm, {
    pillar: m.pillar, metric_code: m.metric_code, metric_name: m.metric_name,
    value: m.value ?? "", unit: m.unit || "", target: m.target ?? "",
    benchmark: m.benchmark ?? "", notes: m.notes || "",
  });
  err.value = null; showMetricForm.value = true;
}
function _num(v: unknown): number | null {
  if (v === "" || v === null || v === undefined) return null;
  const n = Number(v); return Number.isFinite(n) ? n : null;
}

async function saveMetric(): Promise<void> {
  if (!mForm.metric_code.trim()) { err.value = "Укажите код метрики"; return; }
  if (!mForm.metric_name.trim()) { err.value = "Укажите название метрики"; return; }
  saving.value = true; err.value = null; queued.value = false;
  try {
    const res = await esgApi.upsertMetric({
      company_id: props.companyId, year: props.year, pillar: mForm.pillar,
      metric_code: mForm.metric_code.trim(), metric_name: mForm.metric_name.trim(),
      value: _num(mForm.value), unit: mForm.unit.trim() || null,
      target: _num(mForm.target), benchmark: _num(mForm.benchmark),
      notes: mForm.notes.trim() || null,
    });
    if (isModerationQueued(res)) { queued.value = true; setTimeout(() => { showMetricForm.value = false; emit("saved"); }, 1200); }
    else {
      const saved = res as ESGMetricBrief;
      const i = localMetrics.value.findIndex(x => x.id === saved.id
        || (x.pillar === saved.pillar && x.metric_code === saved.metric_code));
      if (i >= 0) localMetrics.value[i] = saved; else localMetrics.value.push(saved);
      showMetricForm.value = false; emit("saved");
    }
  } catch (e: any) {
    err.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить метрику";
  } finally { saving.value = false; }
}
async function removeMetric(m: ESGMetricBrief): Promise<void> {
  if (!confirm(`Удалить метрику «${m.metric_name}»?`)) return;
  saving.value = true; err.value = null;
  try {
    await esgApi.deleteMetric(m.id);
    localMetrics.value = localMetrics.value.filter(x => x.id !== m.id);
    emit("saved");
  } catch (e: any) { err.value = e?.response?.data?.detail || "Не удалось удалить"; }
  finally { saving.value = false; }
}

// ─── РИСКИ / ПРОБЛЕМЫ ─────────────────────────────────────────────
const localIssues = ref<ESGIssueBrief[]>([...(props.issues || [])]);
const showIssueForm = ref(false);
const editingIssue = ref<ESGIssueBrief | null>(null);
const iForm = reactive({
  pillar: "E" as Pillar, title: "", description: "",
  severity: "med" as Severity, status: "open" as IssueStatus,
});

function openAddIssue(): void {
  editingIssue.value = null;
  Object.assign(iForm, { pillar: "E", title: "", description: "", severity: "med", status: "open" });
  err.value = null; showIssueForm.value = true;
}
function openEditIssue(it: ESGIssueBrief): void {
  editingIssue.value = it;
  Object.assign(iForm, {
    pillar: it.pillar, title: it.title, description: it.description || "",
    severity: (it.severity || "med") as Severity, status: it.status,
  });
  err.value = null; showIssueForm.value = true;
}
async function saveIssue(): Promise<void> {
  if (!iForm.title.trim()) { err.value = "Укажите заголовок"; return; }
  saving.value = true; err.value = null; queued.value = false;
  try {
    let res: ESGIssueBrief | { detail?: string };
    if (editingIssue.value) {
      res = await esgApi.updateIssue(editingIssue.value.id, {
        pillar: iForm.pillar, title: iForm.title.trim(),
        description: iForm.description.trim() || null, severity: iForm.severity, status: iForm.status,
      }) as any;
    } else {
      res = await esgApi.createIssue({
        company_id: props.companyId, pillar: iForm.pillar, title: iForm.title.trim(),
        description: iForm.description.trim() || null, severity: iForm.severity,
      }) as any;
    }
    if (isModerationQueued(res)) { queued.value = true; setTimeout(() => { showIssueForm.value = false; emit("saved"); }, 1200); }
    else {
      const saved = res as ESGIssueBrief;
      if (editingIssue.value) {
        const i = localIssues.value.findIndex(x => x.id === editingIssue.value!.id);
        if (i >= 0) localIssues.value[i] = saved;
      } else localIssues.value.push(saved);
      showIssueForm.value = false; emit("saved");
    }
  } catch (e: any) {
    err.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить риск";
  } finally { saving.value = false; }
}
async function removeIssue(it: ESGIssueBrief): Promise<void> {
  if (!confirm(`Удалить риск «${it.title}»?`)) return;
  saving.value = true; err.value = null;
  try {
    await esgApi.deleteIssue(it.id);
    localIssues.value = localIssues.value.filter(x => x.id !== it.id);
    emit("saved");
  } catch (e: any) { err.value = e?.response?.data?.detail || "Не удалось удалить"; }
  finally { saving.value = false; }
}

const PILLARS = computed(() => PILLAR_META);
</script>

<template>
  <div class="ee-backdrop" @click.self="emit('close')">
    <div class="ee-modal">
      <header class="ee-head">
        <div>
          <div class="ee-eyebrow">ESG · FY {{ year }}</div>
          <h2 class="ee-title">{{ companyName }}</h2>
        </div>
        <button class="ee-close" @click="emit('close')" title="Закрыть">×</button>
      </header>

      <div class="ee-tabs">
        <button :class="{ on: section === 'metrics' }" @click="section = 'metrics'">
          Метрики <span class="ee-tab-count">{{ localMetrics.length }}</span>
        </button>
        <button :class="{ on: section === 'issues' }" @click="section = 'issues'">
          Риски <span class="ee-tab-count">{{ localIssues.length }}</span>
        </button>
      </div>

      <div class="ee-body">
        <p v-if="err" class="ee-err">{{ err }}</p>
        <p v-if="queued" class="ee-queued">⏳ Отправлено на модерацию</p>

        <!-- ─── МЕТРИКИ ─── -->
        <template v-if="section === 'metrics'">
          <div v-if="showMetricForm" class="ee-form">
            <div class="ee-sub-label">{{ editingMetric ? "Редактирование метрики" : "Новая метрика" }}</div>
            <div class="ee-grid">
              <label class="ee-field">
                <span class="ee-lbl">Столп</span>
                <select class="ee-in" v-model="mForm.pillar" :disabled="saving || !!editingMetric">
                  <option v-for="p in PILLARS" :key="p.key" :value="p.key">{{ p.label }}</option>
                </select>
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Код *</span>
                <input class="ee-in" v-model="mForm.metric_code" :disabled="saving || !!editingMetric" placeholder="co2_emissions" />
              </label>
              <label class="ee-field ee-wide">
                <span class="ee-lbl">Название *</span>
                <input class="ee-in" v-model="mForm.metric_name" :disabled="saving" placeholder="Выбросы CO₂" />
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Значение</span>
                <input type="number" class="ee-in" v-model="mForm.value" :disabled="saving" />
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Ед. изм.</span>
                <input class="ee-in" v-model="mForm.unit" :disabled="saving" placeholder="т / %" />
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Цель</span>
                <input type="number" class="ee-in" v-model="mForm.target" :disabled="saving" />
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Бенчмарк</span>
                <input type="number" class="ee-in" v-model="mForm.benchmark" :disabled="saving" />
              </label>
            </div>
            <label class="ee-field">
              <span class="ee-lbl">Заметки</span>
              <textarea class="ee-in ee-textarea" v-model="mForm.notes" rows="2" :disabled="saving"></textarea>
            </label>
            <div class="ee-actions">
              <button class="ee-btn ee-ghost" @click="showMetricForm = false" :disabled="saving">Отмена</button>
              <button class="ee-btn ee-primary" @click="saveMetric" :disabled="saving">
                <span v-if="saving" class="ee-spin"></span>{{ saving ? "" : "Сохранить" }}
              </button>
            </div>
          </div>

          <template v-else>
            <button class="ee-add-btn" @click="openAddMetric">＋ Добавить метрику</button>
            <div v-if="localMetrics.length === 0" class="ee-empty">Метрики не заведены</div>
            <div v-for="p in PILLARS" :key="p.key" v-show="metricsByPillar[p.key].length" class="ee-pillar-group">
              <div class="ee-pillar-head" :style="{ color: p.color }">
                <span class="ee-pillar-dot" :style="{ background: p.color }"></span>{{ p.label }}
              </div>
              <div class="ee-metric-row" v-for="m in metricsByPillar[p.key]" :key="m.id">
                <div class="ee-metric-main">
                  <div class="ee-metric-name">{{ m.metric_name }}</div>
                  <div class="ee-metric-sub">
                    <b>{{ m.value ?? "—" }}</b><span v-if="m.unit"> {{ m.unit }}</span>
                    <span v-if="m.target != null" class="ee-metric-target">цель {{ m.target }}</span>
                    <span v-if="m.target_attainment_pct != null" class="ee-metric-pct"
                          :style="{ color: m.target_attainment_pct >= 100 ? '#1D9E75' : m.target_attainment_pct >= 70 ? '#D97706' : '#E24B4A' }">
                      {{ Math.round(m.target_attainment_pct) }}%
                    </span>
                  </div>
                </div>
                <div class="ee-row-acts">
                  <button class="ee-icon-btn" @click="openEditMetric(m)" title="Редактировать">✎</button>
                  <button class="ee-icon-btn ee-del" @click="removeMetric(m)" title="Удалить">🗑</button>
                </div>
              </div>
            </div>
          </template>
        </template>

        <!-- ─── РИСКИ ─── -->
        <template v-else>
          <div v-if="showIssueForm" class="ee-form">
            <div class="ee-sub-label">{{ editingIssue ? "Редактирование риска" : "Новый риск" }}</div>
            <div class="ee-grid">
              <label class="ee-field">
                <span class="ee-lbl">Столп</span>
                <select class="ee-in" v-model="iForm.pillar" :disabled="saving">
                  <option v-for="p in PILLARS" :key="p.key" :value="p.key">{{ p.label }}</option>
                </select>
              </label>
              <label class="ee-field">
                <span class="ee-lbl">Серьёзность</span>
                <select class="ee-in" v-model="iForm.severity" :disabled="saving">
                  <option v-for="s in SEVERITY_META" :key="s.key" :value="s.key">{{ s.label }}</option>
                </select>
              </label>
              <label v-if="editingIssue" class="ee-field">
                <span class="ee-lbl">Статус</span>
                <select class="ee-in" v-model="iForm.status" :disabled="saving">
                  <option v-for="s in ISSUE_STATUS_META" :key="s.key" :value="s.key">{{ s.label }}</option>
                </select>
              </label>
              <label class="ee-field ee-wide">
                <span class="ee-lbl">Заголовок *</span>
                <input class="ee-in" v-model="iForm.title" :disabled="saving" placeholder="Превышение выбросов на участке №3" />
              </label>
            </div>
            <label class="ee-field">
              <span class="ee-lbl">Описание</span>
              <textarea class="ee-in ee-textarea" v-model="iForm.description" rows="3" :disabled="saving"></textarea>
            </label>
            <div class="ee-actions">
              <button class="ee-btn ee-ghost" @click="showIssueForm = false" :disabled="saving">Отмена</button>
              <button class="ee-btn ee-primary" @click="saveIssue" :disabled="saving">
                <span v-if="saving" class="ee-spin"></span>{{ saving ? "" : "Сохранить" }}
              </button>
            </div>
          </div>

          <template v-else>
            <button class="ee-add-btn" @click="openAddIssue">＋ Добавить риск</button>
            <div v-if="localIssues.length === 0" class="ee-empty">Риски не заведены</div>
            <div class="ee-metric-row" v-for="it in localIssues" :key="it.id">
              <div class="ee-metric-main">
                <div class="ee-metric-name">
                  <span class="ee-pillar-dot" :style="{ background: pillarMeta(it.pillar).color }"></span>
                  {{ it.title }}
                </div>
                <div class="ee-metric-sub">
                  <span class="ee-pill" :style="{ background: sevMeta(it.severity).color + '22', color: sevMeta(it.severity).color }">{{ sevMeta(it.severity).label }}</span>
                  <span class="ee-pill" :style="{ background: statusMeta(it.status).color + '22', color: statusMeta(it.status).color }">{{ statusMeta(it.status).label }}</span>
                </div>
              </div>
              <div class="ee-row-acts">
                <button class="ee-icon-btn" @click="openEditIssue(it)" title="Редактировать">✎</button>
                <button class="ee-icon-btn ee-del" @click="removeIssue(it)" title="Удалить">🗑</button>
              </div>
            </div>
          </template>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ee-backdrop { position: fixed; inset: 0; z-index: 300; background: rgba(15, 18, 40, 0.45); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 24px; }
.ee-modal { width: 100%; max-width: 620px; max-height: 88vh; background: var(--bg1, #fff); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08); display: flex; flex-direction: column; overflow: hidden; animation: eeIn 0.32s cubic-bezier(0.34, 1.2, 0.64, 1); }
@keyframes eeIn { from { opacity: 0; transform: translateY(12px) scale(0.98); } to { opacity: 1; transform: none; } }
.ee-head { display: flex; align-items: flex-start; justify-content: space-between; padding: 18px 20px 14px; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.ee-eyebrow { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.07em; color: var(--t3, #64748B); }
.ee-title { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 3px 0 0; }
.ee-close { background: none; border: none; font-size: 26px; line-height: 1; color: var(--t3, #94A3B8); cursor: pointer; padding: 0 4px; }
.ee-close:hover { color: var(--t1, #1E2A4A); }
.ee-tabs { display: flex; gap: 4px; padding: 10px 20px 0; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.ee-tabs button { background: none; border: none; padding: 8px 14px 12px; font-size: 13px; font-weight: 500; color: var(--t3, #64748B); cursor: pointer; border-bottom: 2px solid transparent; font-family: inherit; }
.ee-tabs button.on { color: var(--p-deep, #534AB7); border-bottom-color: var(--p, #7C6FF7); }
.ee-tab-count { font-size: 10.5px; background: rgba(124, 111, 247, 0.12); color: var(--p-deep, #534AB7); padding: 1px 6px; border-radius: 7px; margin-left: 3px; }
.ee-body { padding: 18px 20px; overflow-y: auto; }
.ee-err { font-size: 12px; color: var(--sev-high, #E24B4A); margin: 0 0 10px; }
.ee-queued { font-size: 12px; color: var(--p-deep, #534AB7); font-weight: 500; margin: 0 0 10px; }
.ee-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.ee-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.ee-wide { grid-column: 1 / -1; }
.ee-lbl { font-size: 11px; font-weight: 500; color: var(--t3, #64748B); }
.ee-in { width: 100%; box-sizing: border-box; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px; background: var(--bg2, #F8FAFC); padding: 8px 10px; font-size: 13px; font-family: inherit; color: var(--t1, #1E2A4A); outline: none; transition: border-color 0.14s, box-shadow 0.14s; }
.ee-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.14); }
.ee-textarea { resize: vertical; }
.ee-sub-label { font-size: 10px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.06em; color: var(--t3, #64748B); margin-bottom: 10px; }
.ee-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.ee-btn { border: none; border-radius: 8px; padding: 9px 18px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; display: inline-flex; align-items: center; gap: 6px; min-height: 36px; transition: all 0.14s; }
.ee-btn:disabled { opacity: 0.6; cursor: default; }
.ee-ghost { background: transparent; border: 1px solid var(--border-input, #E2E8F0); color: var(--t2, #334155); }
.ee-ghost:hover:not(:disabled) { background: var(--bg3, #F1F5F9); }
.ee-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108, 92, 231, 0.32); }
.ee-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108, 92, 231, 0.45); }
.ee-spin { width: 14px; height: 14px; border: 2px solid rgba(255, 255, 255, 0.4); border-top-color: #fff; border-radius: 50%; animation: eeSpin 0.7s linear infinite; }
@keyframes eeSpin { to { transform: rotate(360deg); } }
.ee-add-btn { width: 100%; padding: 10px; border: 1.5px dashed var(--border-input, #CBD5E1); border-radius: 10px; background: transparent; color: var(--p-deep, #534AB7); font-size: 13px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all 0.14s; margin-bottom: 14px; }
.ee-add-btn:hover { border-color: var(--p, #7C6FF7); background: rgba(124, 111, 247, 0.05); }
.ee-empty { text-align: center; color: var(--t3, #94A3B8); font-size: 13px; padding: 20px; }
.ee-pillar-group { margin-bottom: 14px; }
.ee-pillar-head { display: flex; align-items: center; gap: 7px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px; }
.ee-pillar-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.ee-metric-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 9px 12px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; margin-bottom: 7px; }
.ee-metric-name { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); display: flex; align-items: center; gap: 7px; }
.ee-metric-sub { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--t2, #475569); }
.ee-metric-target { color: var(--t3, #94A3B8); }
.ee-metric-pct { font-weight: 600; }
.ee-pill { font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 6px; }
.ee-row-acts { display: flex; gap: 4px; flex-shrink: 0; }
.ee-icon-btn { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--border-input, #E2E8F0); background: #fff; cursor: pointer; font-size: 13px; color: var(--t2, #475569); transition: all 0.14s; }
.ee-icon-btn:hover { border-color: var(--p, #7C6FF7); color: var(--p-deep, #534AB7); }
.ee-del:hover { border-color: var(--sev-high, #E24B4A); color: var(--sev-high, #E24B4A); }
.ee-form { display: flex; flex-direction: column; gap: 12px; }
</style>
