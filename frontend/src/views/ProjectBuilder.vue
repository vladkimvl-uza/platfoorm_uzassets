<script setup lang="ts">
/**
 * ProjectBuilder.vue — конструктор массового заведения проектов и задач.
 *
 * Автоматизация: мультивыбор компаний (одно заведение → во все), общие
 * настройки (год/направление/дедлайн на всё), вставка списком (строка =
 * задача), вложенные задачи под проектами + отдельные задачи. Один вызов
 * /builder/bulk создаёт всё.
 */
import { ref, computed, onMounted } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import ModalShell from "@/components/ModalShell.vue";
import EptLogo from "@/components/EptLogo.vue";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


interface Co { id: string; code: string; name: string; }
interface Dir { id: string; code: string; name: string; }
interface BTask { title: string; status: string; priority: string; due_date: string; assignee_email: string; comment: string; }
interface BProject { title: string; status: string; priority: string; due_date: string; direction_id: string; comment: string; tasks: BTask[]; }

const toast = useToast();
// Область доступа: при единственной доступной компании шаг «Компании» не
// показываем — выбирать не из чего, компания проставляется сама.
const scope = useCompanyScope();
/** Номер шага в мастере: без шага «Компании» нумерация сдвигается на один. */
function stepNo(n: number): number { return scope.showCompanyPicker.value ? n : n - 1; }
const companies = ref<Co[]>([]);
const directions = ref<Dir[]>([]);
const selected = ref<Set<string>>(new Set());
const submitting = ref(false);

const common = ref({ portfolio_year: new Date().getFullYear(), direction_id: "", due_date: "" });

const STATUSES = [
  { v: "new", l: "Не начато" }, { v: "init", l: "Инициирование" }, { v: "active", l: "В процессе" },
  { v: "quarterly", l: "Ежеквартально" }, { v: "monthly", l: "Ежемесячно" }, { v: "ongoing", l: "Постоянно" },
];
const PRIOS = [{ v: "high", l: "Высокий" }, { v: "medium", l: "Средний" }, { v: "low", l: "Низкий" }];

const projects = ref<BProject[]>([]);
const standalone = ref<BTask[]>([]);

function newTask(): BTask { return { title: "", status: "new", priority: "medium", due_date: "", assignee_email: "", comment: "" }; }
function newProject(): BProject { return { title: "", status: "new", priority: "medium", due_date: "", direction_id: "", comment: "", tasks: [] }; }

function addProject() { projects.value.push(newProject()); }
function rmProject(i: number) { projects.value.splice(i, 1); }
function addTask(p: BProject) { p.tasks.push(newTask()); }
function rmTask(p: BProject, i: number) { p.tasks.splice(i, 1); }
function addStandalone() { standalone.value.push(newTask()); }
function rmStandalone(i: number) { standalone.value.splice(i, 1); }

// вставка списком: каждая непустая строка → задача
const pasteFor = ref<{ kind: "project" | "standalone"; idx: number } | null>(null);
const pasteText = ref("");
function openPaste(kind: "project" | "standalone", idx: number) { pasteFor.value = { kind, idx }; pasteText.value = ""; }
function applyPaste() {
  const lines = pasteText.value.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !pasteFor.value) { pasteFor.value = null; return; }
  const tasks = lines.map((l) => ({ ...newTask(), title: l }));
  if (pasteFor.value.kind === "project") projects.value[pasteFor.value.idx].tasks.push(...tasks);
  else standalone.value.push(...tasks);
  toast.success(`Добавлено задач: ${tasks.length}`);
  pasteFor.value = null;
}

function toggleCo(id: string) { selected.value.has(id) ? selected.value.delete(id) : selected.value.add(id); selected.value = new Set(selected.value); }
function selectAll() { selected.value = new Set(companies.value.map((c) => c.id)); }
function clearCo() { selected.value = new Set(); }

const totalTasks = computed(() => projects.value.reduce((s, p) => s + p.tasks.length, 0) + standalone.value.length);
const totalProjects = computed(() => projects.value.length);
const perCompany = computed(() => `${totalProjects.value} проектов · ${totalTasks.value} задач`);
const canSubmit = computed(() => (totalProjects.value > 0 || totalTasks.value > 0) &&
  projects.value.every((p) => p.title.trim()) && standalone.value.every((t) => t.title.trim()) &&
  projects.value.every((p) => p.tasks.every((t) => t.title.trim())));

async function load() {
  const [c, d] = await Promise.all([api.get("/builder/companies"), api.get("/builder/directions")]);
  companies.value = c.data.items || [];
  directions.value = d.data.items || [];
  // Шаг «Компании» скрыт — выбор обязан проставиться сам, иначе кнопка
  // «Создать всё» останется заблокированной (submit требует selected.size).
  if (!scope.showCompanyPicker.value) selectAll();
}
onMounted(load);

// ─── ИИ-импорт из файла ───────────────────────────────────────────
interface IngestRes {
  target: string; target_label: string; supported: boolean; confidence: number;
  fields: { name: string; type: string; desc: string; enum: string[] }[];
  projects: any[]; standalone_tasks: any[]; rows: Record<string, string>[];
  rows_parsed: number; source: string; notes: string;
}
const fileInput = ref<HTMLInputElement | null>(null);
const importing = ref(false);
const ingest = ref<IngestRes | null>(null);       // последний результат (для баннера)
const previewRows = ref<IngestRes | null>(null);   // модал превью для неподдержанных целей

function pickFile() { fileInput.value?.click(); }

function addPreviewRow() {
  if (!previewRows.value) return;
  const blank: Record<string, string> = {};
  for (const f of previewRows.value.fields) blank[f.name] = "";
  previewRows.value.rows.push(blank);
}

// создание для поддержанных целей (пока — KPI)
const kpiYear = ref(new Date().getFullYear());
const kpiManager = ref("Импорт KPI");
const creatingKpi = ref(false);

async function createKpi() {
  if (!previewRows.value) return;
  creatingKpi.value = true;
  try {
    const { data } = await api.post("/builder/bulk-kpi", {
      year: kpiYear.value,
      manager_title: kpiManager.value || "Импорт KPI",
      rows: previewRows.value.rows,
    });
    let msg = `Создано KPI: ${data.indicators_created} показателей в ${data.companies} комп.`;
    if (data.unresolved?.length) msg += ` Не сопоставлены: ${data.unresolved.join(", ")}`;
    toast.success(msg, 6000);
    previewRows.value = null;
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка создания KPI");
  } finally {
    creatingKpi.value = false;
  }
}

// создание для финансов
const finYear = ref(new Date().getFullYear());
const finStandard = ref<"IFRS" | "NSBU">("IFRS");
const finReportType = ref<"PL" | "BS" | "CF">("PL");
const creatingFin = ref(false);

async function createFin() {
  if (!previewRows.value) return;
  creatingFin.value = true;
  try {
    const { data } = await api.post("/builder/bulk-financials", {
      default_year: finYear.value,
      default_standard: finStandard.value,
      default_report_type: finReportType.value,
      default_currency: "UZS",
      rows: previewRows.value.rows,
    });
    let msg = `Создано строк финотчётов: ${data.lines_created} в ${data.reports} отчётах.`;
    if (data.unresolved?.length) msg += ` Не сопоставлены: ${data.unresolved.join(", ")}`;
    toast.success(msg, 6000);
    previewRows.value = null;
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка создания финотчётов");
  } finally {
    creatingFin.value = false;
  }
}

async function onFile(e: Event) {
  const input = e.target as HTMLInputElement;
  const f = input.files?.[0];
  input.value = "";
  if (!f) return;
  importing.value = true;
  ingest.value = null;
  try {
    const form = new FormData();
    form.append("file", f);
    const { data } = await api.post<IngestRes>("/builder/ingest", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    ingest.value = data;
    if (data.target === "projects_tasks" && data.supported) {
      projects.value = (data.projects || []).map((p: any) => ({
        title: p.title || "", status: p.status || "new", priority: p.priority || "medium",
        due_date: p.due_date || "", direction_id: p.direction_id || "", comment: p.comment || "",
        tasks: (p.tasks || []).map((t: any) => ({
          title: t.title || "", status: t.status || "new", priority: t.priority || "medium",
          due_date: t.due_date || "", assignee_email: t.assignee_email || "", comment: t.comment || "",
        })),
      }));
      standalone.value = (data.standalone_tasks || []).map((t: any) => ({
        title: t.title || "", status: t.status || "new", priority: t.priority || "medium",
        due_date: t.due_date || "", assignee_email: t.assignee_email || "", comment: t.comment || "",
      }));
      toast.success(`Распознано: ${totalProjects.value} проектов · ${totalTasks.value} задач. Проверьте и создайте.`, 5000);
    } else {
      // другой дашборд — авто-создание не подключено: показываем превью
      previewRows.value = data;
    }
  } catch (err: any) {
    toast.error(err?.response?.data?.detail || "Не удалось распознать файл");
  } finally {
    importing.value = false;
  }
}

async function submit() {
  if (!canSubmit.value) { toast.error("Заполните названия проектов/задач"); return; }
  submitting.value = true;
  try {
    const clean = (t: BTask) => ({ title: t.title, status: t.status, priority: t.priority, due_date: t.due_date || null, assignee_email: t.assignee_email || null, comment: t.comment || null });
    const body = {
      company_ids: [...selected.value],
      common: { portfolio_year: common.value.portfolio_year, direction_id: common.value.direction_id || null, due_date: common.value.due_date || null },
      projects: projects.value.map((p) => ({ title: p.title, status: p.status, priority: p.priority, due_date: p.due_date || null, direction_id: p.direction_id || null, comment: p.comment || null, tasks: p.tasks.map(clean) })),
      standalone_tasks: standalone.value.map(clean),
    };
    const { data } = await api.post("/builder/bulk", body);
    let okMsg = `Создано: ${data.projects_created} проектов · ${data.tasks_created} задач в ${data.companies} компаниях`;
    if (data.comments_created) okMsg += ` · ${data.comments_created} комментариев`;
    toast.success(okMsg, 5000);
    projects.value = []; standalone.value = [];
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка создания");
  } finally { submitting.value = false; }
}
</script>

<template>
  <div class="pb">
    <div class="pb-top">
      <div class="pb-brand">
        <div class="pb-logo"><EptLogo :size="22" /></div>
        <div><div class="pb-eyebrow">{{ t('МАССОВОЕ ЗАВЕДЕНИЕ') }}</div><div class="pb-tt">{{ t('Конструктор проектов и задач') }}</div></div>
      </div>
      <div class="pb-top-r">
        <input ref="fileInput" type="file" accept=".xlsx,.xlsm,.xls,.csv,.tsv,.txt,.pdf,.docx" class="pb-file" @change="onFile" />
        <button class="pb-import" :disabled="importing" @click="pickFile" :title="t('Excel / CSV / PDF — ИИ распознает и заполнит')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          {{ importing ? "Распознаю…" : "Импорт из файла" }}
        </button>
        <button class="pb-create" :disabled="!canSubmit || submitting || !selected.size" @click="submit">
          {{ submitting ? "Создаю…" : `Создать всё → ${selected.size || 0} комп.` }}
        </button>
      </div>
    </div>

    <!-- ИИ-баннер: какой дашборд распознан -->
    <Transition name="pb-modal">
      <div v-if="ingest && ingest.target === 'projects_tasks'" class="pb-ai-banner ok">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
        <div class="pb-ai-txt">
          <b>{{ t('ИИ распознал дашборд: «') }}{{ ingest.target_label }}»</b>
          <span v-if="ingest.confidence"> {{ t('· уверенность') }} {{ Math.round(ingest.confidence * 100) }}%</span>
          <div v-if="ingest.notes" class="pb-ai-notes">{{ ingest.notes }}</div>
          <div class="pb-ai-hint">{{ t('Данные подставлены в шаги ниже — отредактируйте при необходимости, выберите компании и нажмите «Создать всё».') }}</div>
        </div>
        <button class="pb-ai-x" @click="ingest = null"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
      </div>
    </Transition>

    <div class="pb-page">
      <!-- 1. КОМПАНИИ (скрыт при единственной доступной компании) -->
      <div v-if="scope.showCompanyPicker.value" class="pb-card">
        <div class="pb-card-h">
          <span class="pb-step">1</span><span class="pb-card-t">{{ t('Компании') }}</span>
          <span class="pb-card-cap">{{ selected.size }} {{ t('выбрано') }}</span>
          <div class="pb-card-r"><button class="pb-mini" @click="selectAll">{{ t('Все') }}</button><button class="pb-mini" @click="clearCo">{{ t('Сброс') }}</button></div>
        </div>
        <div class="pb-cos">
          <button v-for="c in companies" :key="c.id" class="pb-co" :class="{ on: selected.has(c.id) }" @click="toggleCo(c.id)">{{ c.name }}</button>
        </div>
      </div>

      <!-- 2. ОБЩИЕ НАСТРОЙКИ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">{{ stepNo(2) }}</span><span class="pb-card-t">{{ t('Общие настройки') }}</span><span class="pb-card-cap">{{ t('применяются ко всему') }}</span></div>
        <div class="pb-common">
          <div class="pb-fld"><label>{{ t('Год портфеля') }}</label><input type="number" v-model.number="common.portfolio_year" class="pb-in" /></div>
          <div class="pb-fld"><label>{{ t('Направление (по умолч.)') }}</label>
            <select v-model="common.direction_id" class="pb-in"><option value="">—</option><option v-for="d in directions" :key="d.id" :value="d.id">{{ d.name }}</option></select>
          </div>
          <div class="pb-fld"><label>{{ t('Дедлайн (по умолч.)') }}</label><input type="date" v-model="common.due_date" class="pb-in" /></div>
        </div>
      </div>

      <!-- 3. ПРОЕКТЫ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">{{ stepNo(3) }}</span><span class="pb-card-t">{{ t('Проекты') }}</span><span class="pb-card-cap">{{ projects.length }}</span>
          <div class="pb-card-r"><button class="pb-add" @click="addProject">{{ t('＋ Проект') }}</button></div>
        </div>
        <div v-if="!projects.length" class="pb-empty">{{ t('Проектов нет. Добавьте проект или сразу отдельные задачи ниже.') }}</div>
        <div v-for="(p, pi) in projects" :key="pi" class="pb-proj">
          <div class="pb-proj-head">
            <input v-model="p.title" class="pb-in title" :placeholder="t('Название проекта')" />
            <select v-model="p.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
            <select v-model="p.direction_id" class="pb-in sm"><option value="">{{ t('направление…') }}</option><option v-for="d in directions" :key="d.id" :value="d.id">{{ d.name }}</option></select>
            <input type="date" v-model="p.due_date" class="pb-in sm" />
            <button class="pb-del" @click="rmProject(pi)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg></button>
          </div>
          <div v-if="p.comment" class="pb-cmt-row">
            <span class="pb-cmt-tag">{{ t('Комментарий') }}</span>
            <textarea v-model="p.comment" class="pb-cmt" rows="2" :placeholder="t('Комментарий из документа')"></textarea>
          </div>
          <div class="pb-tasks">
            <div v-for="(t, ti) in p.tasks" :key="ti" class="pb-task-wrap">
              <div class="pb-task">
                <span class="pb-task-dot" />
                <input v-model="t.title" class="pb-in" :placeholder="t('Задача')" />
                <select v-model="t.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
                <input type="date" v-model="t.due_date" class="pb-in sm" />
                <button class="pb-del" @click="rmTask(p, ti)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg></button>
              </div>
              <div v-if="t.comment" class="pb-cmt-row sub">
                <span class="pb-cmt-tag">{{ t('Комментарий') }}</span>
                <textarea v-model="t.comment" class="pb-cmt" rows="2" :placeholder="t('Комментарий из документа')"></textarea>
              </div>
            </div>
            <div class="pb-task-actions">
              <button class="pb-add sm" @click="addTask(p)">{{ t('＋ Задача') }}</button>
              <button class="pb-paste" @click="openPaste('project', pi)">{{ t('⤓ Вставить списком') }}</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 4. ОТДЕЛЬНЫЕ ЗАДАЧИ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">{{ stepNo(4) }}</span><span class="pb-card-t">{{ t('Отдельные задачи') }}</span><span class="pb-card-cap">{{ standalone.length }}</span>
          <div class="pb-card-r"><button class="pb-add" @click="addStandalone">{{ t('＋ Задача') }}</button><button class="pb-paste" @click="openPaste('standalone', 0)">{{ t('⤓ Вставить списком') }}</button></div>
        </div>
        <div v-for="(t, ti) in standalone" :key="ti" class="pb-task-wrap">
          <div class="pb-task">
            <span class="pb-task-dot" />
            <input v-model="t.title" class="pb-in" :placeholder="t('Задача')" />
            <select v-model="t.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
            <select v-model="t.priority" class="pb-in sm"><option v-for="p in PRIOS" :key="p.v" :value="p.v">{{ p.l }}</option></select>
            <input type="date" v-model="t.due_date" class="pb-in sm" />
            <button class="pb-del" @click="rmStandalone(ti)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg></button>
          </div>
          <div v-if="t.comment" class="pb-cmt-row sub">
            <span class="pb-cmt-tag">{{ t('Комментарий') }}</span>
            <textarea v-model="t.comment" class="pb-cmt" rows="2" :placeholder="t('Комментарий из документа')"></textarea>
          </div>
        </div>
      </div>

      <div class="pb-summary">
        {{ t('Итого на') }} <b>{{ selected.size }}</b> {{ t('компаний:') }} <b>{{ perCompany }}</b> {{ t('· всего будет создано') }} <b>{{ totalProjects * (selected.size||1) }}</b> {{ t('проектов и') }} <b>{{ totalTasks * (selected.size||1) }}</b> {{ t('задач') }}
      </div>
    </div>

    <!-- ПРЕВЬЮ для других дашбордов (распознано, авто-создание пока не подключено) -->
    <ModalShell :open="!!previewRows" size="xl" @close="previewRows = null">
      <template v-if="previewRows" #header>
        <div class="pb-mod-t">{{ t('Распознан дашборд: «') }}{{ previewRows.target_label }}»
          <span v-if="previewRows.confidence" class="pb-conf">{{ Math.round(previewRows.confidence * 100) }}%</span>
        </div>
      </template>
      <template v-if="previewRows">
              <p v-if="previewRows.supported" class="pb-mod-hint">
                {{ t('ИИ отнёс документ к дашборду') }} <b>«{{ previewRows.target_label }}»</b> {{ t('и распознал') }}
                <b>{{ previewRows.rows.length }}</b> {{ t('строк. Проверьте/отредактируйте и нажмите «Создать» — показатели добавятся в компании') }} <b>{{ t('по имени') }}</b> {{ t('за выбранный год,') }}
                <b>{{ t('не затирая') }}</b> {{ t('существующие.') }} <span v-if="previewRows.notes">{{ previewRows.notes }}</span>
              </p>
              <p v-else class="pb-mod-hint">
                {{ t('ИИ отнёс документ к дашборду') }} <b>«{{ previewRows.target_label }}»</b> {{ t('и распознал') }}
                <b>{{ previewRows.rows.length }}</b> {{ t('строк. Авто-создание для этого дашборда ещё не подключено — ниже распознанные данные.') }} <span v-if="previewRows.notes">{{ previewRows.notes }}</span>
              </p>
              <div class="pb-tbl-wrap">
                <table class="pb-tbl edit">
                  <thead><tr><th v-for="f in previewRows.fields" :key="f.name" :title="f.desc">{{ f.name }}</th><th class="pb-tbl-act"></th></tr></thead>
                  <tbody>
                    <tr v-for="(r, ri) in previewRows.rows" :key="ri">
                      <td v-for="f in previewRows.fields" :key="f.name"><input v-model="r[f.name]" class="pb-cell" :placeholder="f.type" /></td>
                      <td class="pb-tbl-act"><button class="pb-del" @click="previewRows.rows.splice(ri, 1)" :title="t('Удалить строку')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg></button></td>
                    </tr>
                  </tbody>
                </table>
              </div>
      </template>
      <template v-if="previewRows" #footer>
              <button class="pb-add" @click="addPreviewRow"><span>{{ t('＋ Строка') }}</span></button>
              <span class="pb-mod-spacer" />
              <template v-if="previewRows.supported && previewRows.target === 'kpi'">
                <label class="pb-kpi-fld">{{ t('Год') }} <input type="number" v-model.number="kpiYear" class="pb-in sm" /></label>
                <label class="pb-kpi-fld">{{ t('Менеджер') }} <input v-model="kpiManager" class="pb-in sm wide" /></label>
                <button class="pb-save" :disabled="creatingKpi || !previewRows.rows.length" @click="createKpi">
                  {{ creatingKpi ? "Создаю…" : `Создать в KPI → ${previewRows.rows.length}` }}
                </button>
              </template>
              <template v-else-if="previewRows.supported && previewRows.target === 'financials'">
                <label class="pb-kpi-fld">{{ t('Год') }} <input type="number" v-model.number="finYear" class="pb-in sm" /></label>
                <label class="pb-kpi-fld">{{ t('Стандарт') }}
                  <select v-model="finStandard" class="pb-in sm"><option value="IFRS">{{ t('МСФО') }}</option><option value="NSBU">{{ t('НСБУ') }}</option></select>
                </label>
                <label class="pb-kpi-fld">{{ t('Отчёт') }}
                  <select v-model="finReportType" class="pb-in sm"><option value="PL">{{ t('ОПУ') }}</option><option value="BS">{{ t('Баланс') }}</option><option value="CF">{{ t('ДДС') }}</option></select>
                </label>
                <button class="pb-save" :disabled="creatingFin || !previewRows.rows.length" @click="createFin">
                  {{ creatingFin ? "Создаю…" : `Создать в Финансы → ${previewRows.rows.length}` }}
                </button>
              </template>
              <button class="pb-cancel" @click="previewRows = null">{{ t('Закрыть') }}</button>
      </template>
    </ModalShell>

    <!-- PASTE -->
    <ModalShell :open="!!pasteFor" size="md" :title="t('Вставить списком')" @close="pasteFor = null">
      <div class="pb-mod-b">
        <p class="pb-mod-hint">{{ t('Каждая строка станет отдельной задачей.') }}</p>
        <textarea v-model="pasteText" rows="10" class="pb-area" :placeholder="t('Разработать стратегию Привлечь консультанта Провести инвентаризацию …')"></textarea>
      </div>
      <template #footer>
        <button class="pb-cancel" @click="pasteFor = null">{{ t('Отмена') }}</button>
        <button class="pb-save" @click="applyPaste">{{ t('Добавить') }}</button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.pb { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); color:#0F172A; }
.pb-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.pb-brand { display: flex; align-items: center; gap: 12px; }
.pb-logo { width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12); display: grid; place-items: center; }
.pb-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .1em; color: #9A8FFF; }
.pb-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.pb-top-r { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.pb-file { display: none; }
.pb-import { display: inline-flex; align-items: center; gap: 7px; background: rgba(255,255,255,.10); color: #fff; border: 1px solid rgba(255,255,255,.18); font: 600 12px inherit; padding: 9px 15px; border-radius: 10px; cursor: pointer; transition: background .12s; }
.pb-import:hover:not(:disabled) { background: rgba(255,255,255,.18); }
.pb-import:disabled { opacity: .55; cursor: default; }
.pb-create { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12.5px inherit; padding: 10px 18px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); }
.pb-create:disabled { opacity: .5; cursor: default; }

.pb-ai-banner { max-width: 1100px; margin: 14px auto -4px; display: flex; gap: 11px; align-items: flex-start; padding: 13px 16px; border-radius: 13px; }
.pb-ai-banner.ok { background: linear-gradient(135deg,rgba(29,158,117,.09),rgba(29,158,117,.04)); border: 1px solid rgba(29,158,117,.28); color: #0F6E56; }
.pb-ai-banner > svg { flex-shrink: 0; margin-top: 1px; }
.pb-ai-txt { flex: 1; font-size: 12.5px; line-height: 1.5; } .pb-ai-txt b { color: #0B5A45; }
.pb-ai-notes { color: #3F6B5C; margin-top: 3px; }
.pb-ai-hint { color: #5B7A6E; margin-top: 4px; font-size: 11.5px; }
.pb-ai-x { border: 0; background: transparent; color: #4E8472; cursor: pointer; padding: 3px; flex-shrink: 0; }

.pb-mod.wide { width: min(880px,100%); }
.pb-conf { font-size: 11px; font-weight: 600; color: var(--p-deep); background: #F0EEFF; padding: 2px 8px; border-radius: 8px; margin-left: 8px; }
.pb-tbl-wrap { max-height: 56dvh; overflow: auto; border: 1px solid var(--bd); border-radius: 10px; }
.pb-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pb-tbl th { position: sticky; top: 0; background: #F7F7FB; color: #475569; font-weight: 600; text-align: left; padding: 8px 11px; border-bottom: 1px solid var(--bd); white-space: nowrap; }
.pb-tbl td { padding: 7px 11px; border-bottom: 1px solid var(--line); color: #1E2A4A; }
.pb-tbl tr:last-child td { border-bottom: 0; }
.pb-tbl.edit td { padding: 3px 4px; } .pb-tbl.edit th:first-child, .pb-tbl.edit td:first-child { padding-left: 8px; }
.pb-cell { width: 100%; min-width: 90px; border: 1px solid transparent; border-radius: 6px; padding: 5px 7px; font: 12px inherit; color: #1E2A4A; background: transparent; outline: none; }
.pb-cell:hover { border-color: var(--line); } .pb-cell:focus { border-color: var(--p); background: #fff; box-shadow: 0 0 0 2px rgba(124,111,247,.1); }
.pb-cell::placeholder { color: #C7C9D1; font-size: 10px; }
.pb-tbl-act { width: 34px; text-align: center; }
.pb-mod-spacer { flex: 1; }
.pb-kpi-fld { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t3); font-weight: 500; }
.pb-kpi-fld .pb-in.sm { width: 76px; } .pb-kpi-fld .pb-in.sm.wide { width: 150px; }
.pb-page { padding: 18px 24px 80px; max-width: 1100px; margin: 0 auto; }

.pb-card { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: 0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); margin-bottom: 16px; overflow: hidden; }
.pb-card-h { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.pb-step { width: 22px; height: 22px; border-radius: 7px; background: #F0EEFF; color: var(--p-deep); font-weight: 700; font-size: 12px; display: grid; place-items: center; }
.pb-card-t { font-size: 13.5px; font-weight: 600; color: #1E2A4A; }
.pb-card-cap { font-size: 11px; color: var(--t4); }
.pb-card-r { margin-left: auto; display: flex; gap: 8px; }
.pb-mini { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 11px inherit; padding: 5px 11px; border-radius: 8px; cursor: pointer; }
.pb-add { border: 1px solid rgba(124,111,247,.3); background: rgba(124,111,247,.06); color: var(--p-deep); font: 600 11.5px inherit; padding: 6px 12px; border-radius: 8px; cursor: pointer; }
.pb-add.sm { font-size: 11px; padding: 5px 10px; }
.pb-paste { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 11.5px inherit; padding: 6px 12px; border-radius: 8px; cursor: pointer; }

.pb-cos { display: flex; flex-wrap: wrap; gap: 7px; padding: 16px 18px; }
.pb-co { border: 1px solid var(--bd); background: #fff; color: #475569; font: 500 12px inherit; padding: 7px 13px; border-radius: 9px; cursor: pointer; transition: all .12s; }
.pb-co.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border-color: transparent; }

.pb-common { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; padding: 16px 18px; }
.pb-fld { display: flex; flex-direction: column; gap: 5px; } .pb-fld label { font-size: 11px; color: var(--t3); font-weight: 500; }
.pb-in { border: 1px solid var(--bd); border-radius: 9px; padding: 8px 11px; font-size: 12.5px; font-family: inherit; color: #1E2A4A; outline: none; background: #fff; }
.pb-in:focus { border-color: var(--p); box-shadow: 0 0 0 3px rgba(124,111,247,.12); }
.pb-in.sm { padding: 7px 9px; font-size: 12px; flex-shrink: 0; } .pb-in.title { flex: 1; font-weight: 500; }

.pb-empty { padding: 20px; text-align: center; color: var(--t4); font-size: 12.5px; }
.pb-proj { border-bottom: 1px solid var(--line); padding: 14px 18px; }
.pb-proj-head { display: flex; gap: 8px; align-items: center; }
.pb-tasks { margin: 10px 0 0 22px; padding-left: 14px; border-left: 2px solid var(--line); }
.pb-task { display: flex; gap: 8px; align-items: center; margin-bottom: 7px; }
.pb-task .pb-in:not(.sm) { flex: 1; }
.pb-task-dot { width: 6px; height: 6px; border-radius: 50%; background: #C7C9D1; flex-shrink: 0; }
.pb-task-actions { display: flex; gap: 8px; margin-top: 4px; }
.pb-task-wrap { margin-bottom: 7px; }
.pb-cmt-row { display: flex; gap: 8px; align-items: flex-start; margin: 6px 0 10px; }
.pb-cmt-row.sub { margin: 4px 0 8px 14px; }
.pb-cmt-tag { flex-shrink: 0; font-size: 9px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: #8B7FF0; background: rgba(124,111,247,.10); border: 1px solid rgba(124,111,247,.20); padding: 3px 7px; border-radius: 6px; margin-top: 4px; }
.pb-cmt { flex: 1; border: 1px solid var(--bd); border-radius: 8px; padding: 7px 9px; font: 12px inherit; color: #334155; outline: none; resize: vertical; background: #FCFCFE; line-height: 1.4; }
.pb-cmt:focus { border-color: var(--p); box-shadow: 0 0 0 3px rgba(124,111,247,.1); }
.pb-del { border: 0; background: transparent; color: var(--t4); cursor: pointer; padding: 5px; border-radius: 7px; flex-shrink: 0; }
.pb-del:hover { color: #E24B4A; background: #FCE7E7; }
.pb-summary { margin-top: 4px; padding: 14px 18px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.16); border-radius: 12px; font-size: 12.5px; color: var(--t3); }
.pb-summary b { color: #1E2A4A; }

.pb-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: var(--z-overlay, 9000); display: grid; place-items: center; padding: 24px; }
.pb-mod { width: min(520px,100%); background: #fff; border-radius: 18px; box-shadow: 0 24px 64px rgba(15,23,60,.22); overflow: hidden; }
.pb-mod-h { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--line); }
.pb-mod-t { font-size: 14px; font-weight: 600; color: #1E2A4A; }
.pb-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; }
.pb-mod-b { padding: 16px 20px; } .pb-mod-hint { font-size: 12px; color: var(--t3); margin: 0 0 10px; }
.pb-area { width: 100%; border: 1px solid var(--bd); border-radius: 10px; padding: 11px; font: 13px inherit; outline: none; resize: vertical; }
.pb-area:focus { border-color: var(--p); }
.pb-mod-f { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--line); background: #FAFAFD; }
.pb-cancel { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 12.5px inherit; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.pb-save { border: 0; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font: 600 12.5px inherit; padding: 9px 22px; border-radius: 10px; cursor: pointer; }
.pb-modal-enter-active,.pb-modal-leave-active { transition: opacity .2s; } .pb-modal-enter-from,.pb-modal-leave-to { opacity: 0; }

@media (max-width: 760px) { .pb-common { grid-template-columns: 1fr; } }
</style>
