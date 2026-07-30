<script setup lang="ts">
/**
 * MatrixEditor — РУЧНОЙ конструктор «Сводного обзора» по компании+году.
 *
 * Пользователь сам добавляет направления (строки) и проекты по кварталам.
 * Название проекта — с автоподсказкой из существующих проектов; при выборе
 * подставляются детали (в выноску внизу отчёта) и срок. Всё сохраняется в БД.
 */
import { computed, onMounted, ref } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import {
  overviewMatrixApi,
  emptyMatrixConfig,
  type MatrixConfig,
  type ManualDirection,
  type ManualProject,
} from "@/api/overviewMatrix";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


interface Proj {
  id: string;
  title: string;
  due_date: string | null;
  description?: string | null;
  direction?: string | null;
}

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
  projects: Proj[];
  directions: Array<{ id: string; name: string }>;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", companyId: string, config: MatrixConfig): void;
}>();

const toast = useToast();
const loading = ref(true);
const saving = ref(false);
const loadError = ref(false);   // сбой загрузки → НЕ давать сохранять (иначе затрём отчёт пустым)

const QOPTS: { v: number | null; l: string }[] = [
  { v: null, l: i18nKey("авто (по сроку)") },
  { v: 0, l: "Q1" }, { v: 1, l: "Q2" }, { v: 2, l: "Q3" }, { v: 3, l: "Q4" },
];
const QEND_OPTS: { v: number | null; l: string }[] = [
  { v: null, l: i18nKey("— один") },
  { v: 0, l: i18nKey("до Q1") }, { v: 1, l: i18nKey("до Q2") }, { v: 2, l: i18nKey("до Q3") }, { v: 3, l: i18nKey("до Q4") },
];

// Рабочее состояние ручного отчёта + сохранённый базовый конфиг (чтобы не затереть hidden/overrides/custom).
const dirs = ref<ManualDirection[]>([]);
let baseCfg: MatrixConfig = emptyMatrixConfig();
let seq = 0;
function uid(p: string): string { return `${p}_${Date.now().toString(36)}_${seq++}`; }

function dstr(d: string | null | undefined): string { return (d || "").slice(0, 10); }

async function loadCfg() {
  loading.value = true;
  loadError.value = false;
  try {
    const r = await overviewMatrixApi.get(props.companyId, props.year);
    baseCfg = { ...emptyMatrixConfig(), ...r.config };
    const md = (r.config.manual_directions || []) as ManualDirection[];
    dirs.value = md.map((d) => ({
      id: d.id || uid("d"),
      name: d.name || "",
      projects: (d.projects || []).map((p) => ({
        id: p.id || uid("p"),
        title: p.title || "",
        ref_project_id: p.ref_project_id || null,
        quarter: p.quarter ?? null,
        quarter_end: p.quarter_end ?? null,
        due_date: dstr(p.due_date),
        details: p.details || "",
        status: p.status ?? null,
        requires_minister: p.requires_minister ?? false,
        goal: p.goal || "",
        cost: p.cost || "",
        responsible: p.responsible || "",
        minister_ask: p.minister_ask || "",
      })),
    }));
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    loadError.value = true;
    toast.error(t('Не удалось загрузить: {value0}', { value0: (err?.response?.data?.detail || err?.message || t("ошибка")) }));
  } finally {
    loading.value = false;
  }
}
onMounted(loadCfg);

function addDirection(name = "") {
  dirs.value.push({ id: uid("d"), name, projects: [] });
}
function removeDirection(i: number) { dirs.value.splice(i, 1); }
function moveDirection(i: number, delta: number) {
  const j = i + delta;
  if (j < 0 || j >= dirs.value.length) return;
  const arr = dirs.value;
  [arr[i], arr[j]] = [arr[j], arr[i]];
}

function addProject(dir: ManualDirection) {
  dir.projects.push({
    id: uid("p"), title: "", ref_project_id: null, quarter: 0, quarter_end: null, due_date: "", details: "",
    status: null, requires_minister: false, goal: "", cost: "", responsible: "", minister_ask: "",
  });
}
function removeProject(dir: ManualDirection, j: number) { dir.projects.splice(j, 1); }

// Автоподстановка: если введённое название совпало с существующим проектом —
// подтянуть детали (в выноску) и срок (если ещё не заданы).
function onTitlePick(p: ManualProject) {
  const q = (p.title || "").trim().toLowerCase();
  if (!q) { p.ref_project_id = null; return; }
  const m = props.projects.find((x) => (x.title || "").trim().toLowerCase() === q);
  if (!m) { p.ref_project_id = null; return; }
  p.ref_project_id = m.id;
  if (!(p.goal || "").trim()) p.goal = (m.description || "").trim();
  if (!p.due_date && m.due_date) p.due_date = dstr(m.due_date);
}

function buildConfig(): MatrixConfig {
  return {
    ...baseCfg,
    manual_directions: dirs.value
      .map((d) => ({
        id: d.id,
        name: (d.name || "").trim(),
        projects: (d.projects || [])
          .filter((p) => (p.title || "").trim() || (p.goal || "").trim() || (p.minister_ask || "").trim())
          .map((p) => ({
            id: p.id,
            title: (p.title || "").trim(),
            ref_project_id: p.ref_project_id || null,
            quarter: p.quarter ?? null,
            quarter_end: p.quarter_end ?? null,
            due_date: p.due_date || null,
            details: (p.details || "").trim() || null,
            status: p.status || null,
            requires_minister: !!p.requires_minister,
            goal: (p.goal || "").trim() || null,
            cost: (p.cost || "").trim() || null,
            responsible: (p.responsible || "").trim() || null,
            minister_ask: (p.minister_ask || "").trim() || null,
          })),
      }))
      .filter((d) => d.name.trim() || d.projects.length),
  };
}

async function save() {
  if (saving.value) return;
  if (loadError.value) { toast.error(t('Загрузка не удалась — сохранение заблокировано, чтобы не затереть отчёт. Нажмите «Повторить».')); return; }
  saving.value = true;
  try {
    const cfg = buildConfig();
    const r = await overviewMatrixApi.save(props.companyId, props.year, cfg);
    toast.success(t('Отчёт сохранён'));
    emit("saved", props.companyId, r.config);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(t('Не удалось сохранить: {value0}', { value0: (err?.response?.data?.detail || err?.message || t("ошибка")) }));
  } finally {
    saving.value = false;
  }
}

const totalProjects = computed(() =>
  dirs.value.reduce((n, d) => n + d.projects.filter((p) => (p.title || "").trim()).length, 0),
);
const ministerCount = computed(() =>
  dirs.value.reduce((n, d) => n + d.projects.filter((p) => p.requires_minister).length, 0),
);
</script>

<template>
  <ModalShell :open="true" size="full" @close="emit('close')">
    <template #header>
      <div class="mx-head">
        <div class="mx-head-t">{{ t('Сводный обзор —') }} {{ companyName }}</div>
        <div class="mx-head-s">
          FY {{ year }} {{ t('· направлений:') }} {{ dirs.length }} {{ t('· проектов:') }} {{ totalProjects }} {{ t('· требует решения министра:') }} {{ ministerCount }}
        </div>
      </div>
    </template>

    <div v-if="loading" class="mx-state">{{ t('Загрузка…') }}</div>

    <div v-else class="mx">
      <!-- Подсказка-инструкция -->
      <div class="mx-tip">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>
        <div>
          <b>{{ t('Как заполнять.') }}</b> {{ t('Добавьте') }} <b>{{ t('направления') }}</b> {{ t('(строки отчёта) и в каждом —') }} <b>{{ t('проекты') }}</b> {{ t('по кварталам. Для каждого проекта укажите') }} <b>{{ t('статус') }}</b> {{ t('(В графике / Внимание / Заблокирован) — он задаёт цвет в матрице, и заполните') }} <b>{{ t('Цель / результат') }}</b>, <b>{{ t('Ответственного') }}</b> {{ t('и') }} <b>{{ t('«Требуется распоряжение»') }}</b> {{ t('— всё это 1-в-1 попадёт в печатный отчёт и таблицу «Детали проекта». Пустая цель в печати отметится как') }}
          <i>«ochiq»</i> {{ t('(данные ещё не внесены). Квартал «авто» — по сроку; «до Q…» — Гант на несколько кварталов.') }}
        </div>
      </div>

      <!-- Ошибка загрузки — НЕ показываем редактируемый пустой шаблон (иначе сейв затрёт отчёт) -->
      <div v-if="loadError" class="mx-load-error">
        <div class="mx-empty-ttl">{{ t('Не удалось загрузить отчёт') }}</div>
        <div class="mx-empty-sub">{{ t('Сохранение заблокировано, чтобы не затереть существующие данные.') }}</div>
        <button class="mx-add-dir mx-add-dir-big" type="button" @click="loadCfg">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
          {{ t('Повторить') }}
        </button>
      </div>

      <!-- Пустой шаблон -->
      <div v-else-if="!dirs.length" class="mx-empty-all">
        <div class="mx-empty-ttl">{{ t('Пустой отчёт') }}</div>
        <div class="mx-empty-sub">{{ t('Начните с добавления первого направления.') }}</div>
        <button class="mx-add-dir mx-add-dir-big" type="button" @click="addDirection()">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('Добавить направление') }}
        </button>
      </div>

      <!-- Направления -->
      <div v-for="(d, di) in dirs" :key="d.id" class="mx-dir">
        <div class="mx-dir-head">
          <span class="mx-dir-no">{{ di + 1 }}</span>
          <input v-model="d.name" class="mx-in mx-dir-name-in" list="mxDirList" :placeholder="t('Название направления (напр. «Финансы / Риски / Аудит»)')" />
          <div class="mx-dir-actions">
            <button class="mx-icon" type="button" :title="t('Выше')" :disabled="di === 0" @click="moveDirection(di, -1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M18 15l-6-6-6 6"/></svg>
            </button>
            <button class="mx-icon" type="button" :title="t('Ниже')" :disabled="di === dirs.length - 1" @click="moveDirection(di, 1)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M6 9l6 6 6-6"/></svg>
            </button>
            <button class="mx-icon mx-icon-del" type="button" :title="t('Удалить направление')" @click="removeDirection(di)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
            </button>
          </div>
        </div>

        <div v-for="(p, pi) in d.projects" :key="p.id" class="mx-pcard" :class="{ 'mx-pcard-star': p.requires_minister }">
          <!-- строка 1: название + статус + ★ министру + удалить -->
          <div class="mx-pc-row mx-pc-r1">
            <div class="mx-title-wrap">
              <input v-model="p.title" class="mx-in mx-in-title" list="mxProjList" :placeholder="t('Название проекта (начните вводить — подсказка)…')"
                     @change="onTitlePick(p)" @blur="onTitlePick(p)" />
              <span v-if="p.ref_project_id" class="mx-linked" :title="t('Связано с проектом системы')">{{ t('авто') }}</span>
            </div>
            <select v-model="p.status" class="mx-in mx-in-status" :class="'st-' + (p.status || 'none')" :title="t('Статус проекта')">
              <option :value="null">{{ t('— статус —') }}</option>
              <option value="on_track">{{ t('В графике') }}</option>
              <option value="attention">{{ t('Внимание') }}</option>
              <option value="blocked">{{ t('Заблокирован') }}</option>
            </select>
            <button class="mx-icon mx-icon-del" type="button" :title="t('Удалить проект')" @click="removeProject(d, pi)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
            </button>
          </div>
          <!-- строка 2: квартал · гант · срок -->
          <div class="mx-pc-row mx-pc-r2">
            <label class="mx-fl"><span>{{ t('Квартал') }}</span>
              <select v-model="p.quarter" class="mx-in mx-in-q"><option v-for="o in QOPTS" :key="String(o.v)" :value="o.v">{{ t(o.l) }}</option></select>
            </label>
            <label class="mx-fl"><span>{{ t('Гант — до') }}</span>
              <select v-model="p.quarter_end" class="mx-in mx-in-q"><option v-for="o in QEND_OPTS" :key="'e' + String(o.v)" :value="o.v">{{ t(o.l) }}</option></select>
            </label>
            <label class="mx-fl"><span>{{ t('Срок') }}</span>
              <input v-model="p.due_date" type="date" class="mx-in" />
            </label>
          </div>
          <!-- строка 3: цель + ответственный -->
          <div class="mx-pc-row mx-pc-r3">
            <label class="mx-fl mx-fl-grow"><span>{{ t('Цель / результат') }}</span>
              <textarea v-model="p.goal" class="mx-in mx-in-area" rows="2" :placeholder="t('Что должно быть достигнуто…')"></textarea>
            </label>
            <label class="mx-fl mx-fl-grow"><span>{{ t('Ответственный') }}</span>
              <input v-model="p.responsible" class="mx-in" :placeholder="t('напр. «PwC · договор 13.03.26» / «не назначен»')" />
            </label>
          </div>
          <!-- строка 4: требуется распоряжение -->
          <div class="mx-pc-row">
            <label class="mx-fl mx-fl-grow"><span>{{ t('Требуется распоряжение') }}</span>
              <textarea v-model="p.minister_ask" class="mx-in mx-in-area" rows="2" :placeholder="t('Какое решение/действие требуется (пусто = «Распоряжений не требуется»)')"></textarea>
            </label>
          </div>
        </div>

        <button class="mx-add-proj" type="button" @click="addProject(d)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          {{ t('Добавить проект') }}
        </button>
      </div>

      <button v-if="dirs.length" class="mx-add-dir" type="button" @click="addDirection()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
        {{ t('Добавить направление') }}
      </button>

      <!-- Источники автоподсказки -->
      <datalist id="mxProjList">
        <option v-for="p in projects" :key="p.id" :value="p.title" />
      </datalist>
      <datalist id="mxDirList">
        <option v-for="dd in directions" :key="dd.id" :value="dd.name" />
      </datalist>
    </div>

    <template #footer>
      <div class="mx-foot">
        <span class="mx-foot-note">{{ t('Печатается 1-в-1: статус-цвет в матрице и таблица «Детали проекта».') }}</span>
        <div class="mx-foot-btns">
          <button class="mx-btn-cancel" type="button" :disabled="saving" @click="emit('close')">{{ t('Отмена') }}</button>
          <button class="mx-btn-save" type="button" :disabled="saving || loading || loadError" @click="save">{{ saving ? t('Сохранение…') : t('Сохранить отчёт') }}</button>
        </div>
      </div>
    </template>
  </ModalShell>
</template>

<style scoped>
.mx-head-t { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); }
.mx-head-s { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.mx-state { text-align: center; padding: 40px; color: var(--t3, var(--t-muted)); font-size: 13px; }

.mx { display: flex; flex-direction: column; gap: 14px; }

.mx-tip {
  display: flex; gap: 10px; align-items: flex-start;
  padding: 11px 14px; border-radius: 10px;
  background: rgba(127, 119, 221, .07); border: 1px solid rgba(127, 119, 221, .18);
  font-size: 12px; line-height: 1.5; color: var(--t2, #3a4256);
}
.mx-tip svg { color: #6B63D4; flex-shrink: 0; margin-top: 1px; }
.mx-tip b { font-weight: 600; color: var(--t1, #1E2A4A); }

.mx-empty-all { text-align: center; padding: 36px 16px; border: 1px dashed rgba(127,119,221,.35); border-radius: 12px; background: rgba(127,119,221,.03); }
.mx-load-error { text-align: center; padding: 36px 16px; border: 1px solid rgba(226,75,74,.35); border-radius: 12px; background: rgba(226,75,74,.05); }
.mx-empty-ttl { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mx-empty-sub { font-size: 12px; color: var(--t3, var(--t-muted)); margin: 4px 0 14px; }

.mx-dir { border: 1px solid var(--border1, rgba(0, 0, 0, .08)); border-radius: 12px; overflow: hidden; }
.mx-dir-head {
  display: flex; align-items: center; gap: 9px;
  padding: 9px 12px; background: var(--bg2, #FAFBFC);
  border-bottom: 1px solid var(--border1, rgba(0, 0, 0, .06));
}
.mx-dir-no {
  flex-shrink: 0; width: 22px; height: 22px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  background: #7F77DD; color: #fff; font-size: 11px; font-weight: 700;
}
.mx-dir-name-in { font-weight: 600; color: var(--p-deep, #5B53B8); }
.mx-dir-actions { display: flex; gap: 4px; flex-shrink: 0; }

.mx-cols {
  display: grid; grid-template-columns: minmax(0,1fr) 124px 92px 138px minmax(0,1.3fr) 30px; gap: 8px;
  padding: 7px 12px 2px; font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .03em; color: var(--t3, #9aa0b0);
}
.mx-cols i { font-weight: 400; text-transform: none; letter-spacing: 0; }

.mx-prow {
  display: grid; grid-template-columns: minmax(0,1fr) 124px 92px 138px minmax(0,1.3fr) 30px; gap: 8px;
  align-items: start; padding: 6px 12px; border-bottom: 1px solid rgba(0, 0, 0, .035);
}
.mx-prow:last-of-type { border-bottom: none; }
.mx-title-wrap { position: relative; display: flex; align-items: center; }
.mx-linked {
  position: absolute; right: 6px; font-size: 8.5px; font-weight: 700; letter-spacing: .04em;
  color: #1D9E75; background: rgba(29,158,117,.12); border-radius: 4px; padding: 1px 5px; pointer-events: none;
}

.mx-in {
  padding: 6px 9px; border-radius: 7px; border: 1px solid rgba(0, 0, 0, .12);
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff); outline: none; min-width: 0; box-sizing: border-box; width: 100%;
}
.mx-in:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.mx-in-q { cursor: pointer; }
.mx-in-det { resize: vertical; line-height: 1.35; min-height: 32px; }

/* ── Карточка проекта (министерский отчёт) ── */
.mx-pcard { padding: 11px 12px; border-bottom: 1px solid rgba(0,0,0,.05); display: flex; flex-direction: column; gap: 9px; }
.mx-pcard:last-of-type { border-bottom: none; }
.mx-pcard-star { background: rgba(202, 138, 4, .045); }
.mx-pc-row { display: flex; gap: 8px; align-items: flex-end; flex-wrap: wrap; }
.mx-pc-r1 { align-items: center; }
.mx-pc-r1 .mx-title-wrap { flex: 1 1 240px; }
.mx-fl { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.mx-fl > span { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #9aa0b0); }
.mx-fl-grow { flex: 1 1 240px; }
.mx-pc-r2 .mx-fl:not(.mx-fl-grow) { flex: 0 0 120px; }
.mx-in-title { font-weight: 500; }
.mx-in-area { resize: vertical; line-height: 1.4; min-height: 40px; }
.mx-in-status { flex: 0 0 152px; cursor: pointer; font-weight: 600; }
.mx-in-status.st-on_track { color: #0F6E56; border-color: rgba(29,158,117,.4); background: rgba(29,158,117,.06); }
.mx-in-status.st-attention { color: #854F0B; border-color: rgba(202,138,4,.4); background: rgba(202,138,4,.07); }
.mx-in-status.st-blocked { color: #A32D2D; border-color: rgba(226,75,74,.4); background: rgba(226,75,74,.06); }
.mx-star { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 5px; padding: 6px 10px; border-radius: 7px; border: 1px solid rgba(0,0,0,.12); font-size: 11.5px; font-weight: 600; color: var(--t3, #9aa0b0); cursor: pointer; user-select: none; transition: all .14s; white-space: nowrap; }
.mx-star input { display: none; }
.mx-star-ic { font-size: 13px; line-height: 1; }
.mx-star.on { color: #854F0B; background: rgba(202,138,4,.1); border-color: rgba(202,138,4,.45); }
.mx-star:hover { border-color: rgba(202,138,4,.4); }

.mx-icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px; border-radius: 6px; cursor: pointer;
  background: transparent; border: 1px solid transparent; color: var(--t3, var(--t-muted)); transition: all .15s;
}
.mx-icon:hover:not(:disabled) { background: rgba(127, 119, 221, .1); color: var(--p-deep, #5B53B8); }
.mx-icon:disabled { opacity: .3; cursor: default; }
.mx-icon-del:hover:not(:disabled) { background: rgba(226, 75, 74, .1); color: #C53030; }

.mx-add-proj {
  display: inline-flex; align-items: center; gap: 6px; margin: 8px 12px;
  padding: 5px 12px; border-radius: 7px; font-size: 11.5px; font-weight: 500; font-family: inherit; cursor: pointer;
  background: rgba(127, 119, 221, .08); border: 1px solid rgba(127, 119, 221, .22); color: var(--p-deep, #5B53B8); transition: all .15s;
}
.mx-add-proj:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.mx-add-dir {
  align-self: flex-start;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 9px 16px; border-radius: 9px; font-size: 12.5px; font-weight: 600; font-family: inherit; cursor: pointer;
  background: #7F77DD; color: #fff; border: none; transition: all .15s;
}
.mx-add-dir:hover { background: #6B63D4; }
.mx-add-dir-big { margin: 0 auto; }

.mx-foot { display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 14px; flex-wrap: wrap; }
.mx-foot-note { font-size: 11px; color: var(--t3, var(--t-muted)); font-style: italic; }
.mx-foot-btns { display: flex; gap: 8px; }
.mx-btn-cancel, .mx-btn-save { padding: 8px 18px; font-size: 12px; font-weight: 500; border-radius: 7px; cursor: pointer; font-family: inherit; transition: all .15s; }
.mx-btn-cancel { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, .1); }
.mx-btn-cancel:hover:not(:disabled) { color: var(--t1, #1E2A4A); }
.mx-btn-save { background: #7F77DD; color: #fff; border: none; }
.mx-btn-save:hover:not(:disabled) { background: #6B63D4; }
.mx-btn-cancel:disabled, .mx-btn-save:disabled { opacity: .6; cursor: not-allowed; }

@media (max-width: 820px) {
  .mx-cols { display: none; }
  .mx-prow { grid-template-columns: 1fr 1fr; grid-auto-rows: auto; }
  .mx-title-wrap { grid-column: 1 / 3; }
  .mx-in-det { grid-column: 1 / 3; }
}
</style>
