<script setup lang="ts">
/**
 * ReportingWizard — мастер управленческого отчёта по компании на A4 (альбом).
 *
 * Два типа листов:
 *  1) «Направление» (нарратив): направление + ключевые проекты + «Текущий статус»
 *     и «Предложения по дальнейшим шагам» (две колонки).
 *  2) «Статус по ключевым направлениям» (матрица по мотиву слайда «Ожидания
 *     акционера»): строки-направления × статус. Кредитный рейтинг и ESG
 *     подставляются автоматически из рейтингов компании, остальные — поля.
 *     Строки полностью настраиваемые (быстрые пресеты + своя строка).
 *
 * Хранения нет (печать-онли). Всё гибкое: textarea авто-растут, на печати текст
 * переносится (pre-wrap, break-word) и при необходимости перетекает на доп. лист —
 * ничего не обрезается. Глобальное скрытие #app на печати гейтится классом
 * body.rw-printing — чтобы не ломать другие печати в приложении.
 */
import { ref, computed, onMounted, watch, nextTick } from "vue";
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";
import { directionsApi, type DirectionBrief } from "@/api/directions";
import { ratingsApi, type CompanyRatingsResponse } from "@/api/ratings";
import { projectsApi, type ProjectBrief } from "@/api/projects";
import type { TaskBrief } from "@/api/tasks";
import { reportWizardApi } from "@/api/reportWizard";
import { useToast } from "@/composables/useToast";

const props = defineProps<{
  companyName: string;
  companyCode: string;
  sectorName?: string | null;
  year?: number | null;
  projects: ProjectBrief[];
}>();

const directions = ref<DirectionBrief[]>([]);
const ratings = ref<CompanyRatingsResponse | null>(null);
onMounted(async () => {
  try { directions.value = await directionsApi.list(); } catch { /* каталог опционален */ }
  try { ratings.value = await ratingsApi.getCompanyRatings(props.companyCode); } catch { /* рейтинги опциональны */ }
});

// авто-значения для матрицы: кредит (грейд+outlook) и ESG (балл)
const creditDisplay = computed(() =>
  (ratings.value?.credit || []).map(r => `${r.agency} ${r.rating ?? ""}${r.outlook ? " (" + r.outlook + ")" : ""}`.trim()).join(" · ") || "—"
);
const esgDisplay = computed(() =>
  (ratings.value?.esg || []).map(r => `${r.agency} ${r.score ?? r.rating ?? ""}`.trim()).join(" · ") || "—"
);
function autoValue(auto: "credit" | "esg" | null): string {
  return auto === "credit" ? creditDisplay.value : auto === "esg" ? esgDisplay.value : "";
}

type SheetType = "narrative" | "matrix";
interface MatrixRow { id: number; label: string; auto: "credit" | "esg" | null; value: string; }
interface KeyProj { id: string; taskIds: string[]; }
interface ReportPage {
  id: number;
  type: SheetType;
  // narrative
  directionId: string;
  keyProjects: KeyProj[];
  status: string;
  nextSteps: string;
  // matrix
  matrixTitle: string;
  rows: MatrixRow[];
}
let _seq = 1, _rseq = 1;
function base(type: SheetType): ReportPage {
  return { id: _seq++, type, directionId: "", keyProjects: [], status: "", nextSteps: "", matrixTitle: "", rows: [] };
}

// кеш задач проектов (lazy-load по выбору проекта)
const tasksByProject = ref<Record<string, TaskBrief[]>>({});
const tasksLoading = ref<Set<string>>(new Set());
async function loadTasks(pid: string): Promise<TaskBrief[]> {
  if (pid in tasksByProject.value) return tasksByProject.value[pid];
  tasksLoading.value.add(pid); tasksLoading.value = new Set(tasksLoading.value);
  try { tasksByProject.value[pid] = await projectsApi.getTasks(pid); }
  catch { tasksByProject.value[pid] = []; }
  finally { tasksLoading.value.delete(pid); tasksLoading.value = new Set(tasksLoading.value); }
  return tasksByProject.value[pid];
}
function blankNarrative(): ReportPage { return base("narrative"); }
function blankMatrix(): ReportPage {
  const p = base("matrix");
  p.matrixTitle = "Статус по ключевым направлениям";
  return p;
}
const pages = ref<ReportPage[]>([blankNarrative()]);
function addNarrative() { pages.value.push(blankNarrative()); }
function addMatrix() { pages.value.push(blankMatrix()); }
function removePage(id: number) {
  pages.value = pages.value.filter(p => p.id !== id);
  if (!pages.value.length) pages.value = [blankNarrative()];
}

// ── Сохранение в БД (по компании+году) + загрузка при открытии ──
const toast = useToast();
const wizYear = computed(() => props.year || new Date().getFullYear());
const saving = ref(false);
const loadError = ref(false);   // сбой загрузки → не давать «Сохранить» (иначе затрём реальный отчёт пустой страницей)
const savedBy = ref<string | null>(null);
const savedAt = ref<string | null>(null);
// Полный конфиг строки (company,year): визард владеет только ключом `pages`,
// но в той же строке живёт блок projects_status_report — его нельзя затирать.
const loadedConfig = ref<Record<string, any>>({});

async function loadSaved() {
  loadError.value = false;
  try {
    const r = await reportWizardApi.get(props.companyCode, wizYear.value);
    loadedConfig.value = (r.config && typeof r.config === "object") ? { ...(r.config as any) } : {};
    const cfg = r.config as { pages?: ReportPage[] } | undefined;
    if (cfg?.pages && Array.isArray(cfg.pages) && cfg.pages.length) {
      pages.value = cfg.pages.map(p => ({ ...p, keyProjects: p.keyProjects || [], rows: p.rows || [] }));
      // защита от коллизий id при добавлении новых листов/строк
      let maxP = 0, maxR = 0;
      for (const p of pages.value) {
        if (p.id > maxP) maxP = p.id;
        for (const rr of (p.rows || [])) if (rr.id > maxR) maxR = rr.id;
      }
      _seq = maxP + 1; _rseq = maxR + 1;
    }
    savedBy.value = r.updated_by_name || null;
    savedAt.value = r.updated_at || null;
  } catch (e: unknown) {
    // Бэкенд при ОТСУТСТВИИ конфига отдаёт 200 c config={} (НЕ исключение).
    // Значит сюда попадают только РЕАЛЬНЫЕ сбои (сеть/5xx/403/404) — при них
    // нельзя дать «Сохранить», иначе пустая страница затрёт сохранённый отчёт.
    loadError.value = true;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось загрузить сохранённый отчёт: " + (err?.response?.data?.detail || err?.message || "ошибка") + ". Не сохраняйте — нажмите «Повторить».");
  }
}
onMounted(loadSaved);
// Смена компании/года → перечитываем отчёт нужного года (иначе сохраняли
// устаревшие страницы не в тот год и не грузили реальный отчёт года).
watch(() => [props.companyCode, props.year], () => { pages.value = [blankNarrative()]; loadSaved(); });

async function saveReport() {
  if (saving.value) return;
  if (loadError.value) { toast.error("Загрузка не удалась — сохранение заблокировано, чтобы не затереть отчёт. Нажмите «Повторить»."); return; }
  saving.value = true;
  try {
    // Сохраняем СВОЙ ключ `pages`, не затирая соседний projects_status_report.
    const cfg = { ...loadedConfig.value, pages: JSON.parse(JSON.stringify(pages.value)) };
    const r = await reportWizardApi.save(props.companyCode, wizYear.value, cfg);
    loadedConfig.value = cfg;
    savedBy.value = r.updated_by_name || null;
    savedAt.value = r.updated_at || null;
    // Тост убран: статус сохранения уже виден в нижней панели «Сохранено: … · дата»
    // (тост «Отчёт сохранён» попадал на печатный лист сводного отчёта).
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось сохранить: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    saving.value = false;
  }
}
function fmtSavedAt(): string {
  if (!savedAt.value) return "";
  const d = new Date(savedAt.value);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// ── narrative: направление → проекты → задачи ──
function dirName(id: string): string {
  return directions.value.find(d => d.id === id)?.label || "—";
}
function projectsForDir(dirId: string): ProjectBrief[] {
  if (!dirId) return [];
  return props.projects.filter(p => p.direction_id === dirId);
}
function isProjSel(page: ReportPage, pid: string): boolean {
  return page.keyProjects.some(k => k.id === pid);
}
async function toggleProj(page: ReportPage, pid: string) {
  const i = page.keyProjects.findIndex(k => k.id === pid);
  if (i >= 0) { page.keyProjects.splice(i, 1); return; }
  // подгружаем задачи; по умолчанию НИ ОДНА не выбрана — выбираются гибко по одной
  page.keyProjects.push({ id: pid, taskIds: [] });
  await loadTasks(pid);
}
function allTasksSel(page: ReportPage, pid: string): boolean {
  const kp = page.keyProjects.find(k => k.id === pid);
  const tasks = tasksByProject.value[pid] || [];
  return !!kp && tasks.length > 0 && kp.taskIds.length === tasks.length;
}
function toggleAllTasks(page: ReportPage, pid: string) {
  const kp = page.keyProjects.find(k => k.id === pid);
  if (!kp) return;
  const tasks = tasksByProject.value[pid] || [];
  kp.taskIds = kp.taskIds.length === tasks.length ? [] : tasks.map(t => t.id);
}
function isTaskSel(page: ReportPage, pid: string, tid: string): boolean {
  const kp = page.keyProjects.find(k => k.id === pid);
  return !!kp && kp.taskIds.includes(tid);
}
function toggleTask(page: ReportPage, pid: string, tid: string) {
  const kp = page.keyProjects.find(k => k.id === pid);
  if (!kp) return;
  const i = kp.taskIds.indexOf(tid);
  if (i >= 0) kp.taskIds.splice(i, 1); else kp.taskIds.push(tid);
}
// для печати: выбранные проекты с выбранными задачами
function selProjects(page: ReportPage): { p: ProjectBrief; tasks: TaskBrief[] }[] {
  return page.keyProjects.map(kp => {
    const p = props.projects.find(x => x.id === kp.id);
    if (!p) return null;
    const tasks = (tasksByProject.value[kp.id] || []).filter(t => kp.taskIds.includes(t.id));
    return { p, tasks };
  }).filter(Boolean) as { p: ProjectBrief; tasks: TaskBrief[] }[];
}

// ── matrix: строки ──
const PRESETS: { label: string; auto: "credit" | "esg" | null }[] = [
  { label: "Кредитный рейтинг", auto: "credit" },
  { label: "ESG рейтинг", auto: "esg" },
  { label: "МСФО отчётность", auto: null },
  { label: "Форензик аудит", auto: null },
  { label: "Внутренний аудит", auto: null },
];
function addRow(page: ReportPage, preset?: { label: string; auto: "credit" | "esg" | null }) {
  page.rows.push({ id: _rseq++, label: preset?.label ?? "", auto: preset?.auto ?? null, value: "" });
}
function removeRow(page: ReportPage, rid: number) { page.rows = page.rows.filter(r => r.id !== rid); }

function fmtDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "2-digit" });
}
const todayStr = new Date().toLocaleDateString("ru-RU");
const fy = computed(() => props.year || new Date().getFullYear());

const printablePages = computed(() => pages.value.filter(p =>
  p.type === "narrative"
    ? (p.directionId || p.status.trim() || p.nextSteps.trim() || p.keyProjects.length)
    : p.rows.some(r => r.label || r.value || r.auto)
));

function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function printReport() {
  if (!printablePages.value.length) return;
  document.body.classList.add("rw-printing");
  const cleanup = () => { document.body.classList.remove("rw-printing"); window.removeEventListener("afterprint", cleanup); };
  window.addEventListener("afterprint", cleanup);
  nextTick(() => window.print());
}
</script>

<template>
  <div class="rw">
    <div class="rw-head">
      <div class="rw-head-t">
        <h2 class="rw-title">Мастер отчёта</h2>
        <p class="rw-desc">Соберите управленческий отчёт по компании на листах A4 (альбом): лист на направление с нарративом или «Статус по ключевым направлениям» матрицей. Заполните и распечатайте с фирменной шапкой.</p>
      </div>
      <div class="rw-head-actions">
        <button class="rw-btn" @click="addNarrative">+ Направление</button>
        <button class="rw-btn" @click="addMatrix">+ Статус-матрица</button>
        <button v-if="loadError" class="rw-btn rw-btn-retry" @click="loadSaved" title="Перезагрузить сохранённый отчёт">↻ Повторить</button>
        <button class="rw-btn rw-btn-save" :disabled="saving || loadError" @click="saveReport">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
        <button class="rw-btn rw-btn-print" :disabled="!printablePages.length" @click="printReport">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
          Печать отчёта<template v-if="printablePages.length"> ({{ printablePages.length }})</template>
        </button>
      </div>
    </div>

    <TransitionGroup tag="div" name="rwpage" class="rw-pages" appear>
      <div v-for="(page, i) in pages" :key="page.id" class="rw-pg" :style="{ '--d': i * 50 + 'ms' }">
        <div class="rw-pg-top">
          <span class="rw-pg-n" :class="{ mx: page.type === 'matrix' }">Лист {{ i + 1 }} · {{ page.type === 'matrix' ? 'Статус-матрица' : 'Направление' }}</span>
          <select v-if="page.type === 'narrative'" v-model="page.directionId" class="rw-select">
            <option value="" disabled>Выберите направление…</option>
            <option v-for="d in directions" :key="d.id" :value="d.id">{{ d.label }}</option>
          </select>
          <input v-else v-model="page.matrixTitle" class="rw-input rw-grow" placeholder="Заголовок матрицы…" />
          <button v-if="pages.length > 1" class="rw-rm" @click="removePage(page.id)">Удалить лист</button>
        </div>

        <!-- ── narrative ── -->
        <template v-if="page.type === 'narrative'">
          <div v-if="page.directionId" class="rw-field">
            <label class="rw-label">Ключевые проекты и задачи</label>
            <div class="rw-projlist">
              <div v-for="p in projectsForDir(page.directionId)" :key="p.id" class="rw-pj" :class="{ on: isProjSel(page, p.id) }">
                <button class="rw-pj-head" @click="toggleProj(page, p.id)">
                  <span class="rw-pick-ck"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
                  <span class="rw-pj-t">{{ p.title }}</span>
                  <span class="rw-pj-d">{{ fmtDate(p.due_date) }}</span>
                </button>
                <div v-if="isProjSel(page, p.id)" class="rw-pj-tasks">
                  <div v-if="tasksLoading.has(p.id)" class="rw-empty rw-empty-sm">Загрузка задач…</div>
                  <template v-else>
                    <div v-if="(tasksByProject[p.id] || []).length" class="rw-tk-head">
                      <span class="rw-tk-head-l">Задачи — отметьте нужные</span>
                      <button class="rw-tk-all" @click="toggleAllTasks(page, p.id)">{{ allTasksSel(page, p.id) ? 'Снять все' : 'Выбрать все' }}</button>
                    </div>
                    <button v-for="t in (tasksByProject[p.id] || [])" :key="t.id"
                      class="rw-tk" :class="{ on: isTaskSel(page, p.id, t.id) }" @click="toggleTask(page, p.id, t.id)">
                      <span class="rw-pick-ck rw-ck-sm"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
                      <span class="rw-tk-t">{{ t.title }}</span>
                      <span class="rw-tk-d">{{ fmtDate(t.due_date) }}</span>
                    </button>
                    <span v-if="!(tasksByProject[p.id] || []).length" class="rw-empty rw-empty-sm">У проекта нет задач</span>
                  </template>
                </div>
              </div>
              <span v-if="!projectsForDir(page.directionId).length" class="rw-empty">В этом направлении пока нет проектов</span>
            </div>
          </div>
          <div class="rw-two">
            <div class="rw-field">
              <label class="rw-label">Текущий статус</label>
              <textarea v-model="page.status" class="rw-ta" rows="5" @input="autoGrow" placeholder="Опишите словами текущее положение по направлению…"></textarea>
            </div>
            <div class="rw-field">
              <label class="rw-label">Предложения по дальнейшим шагам</label>
              <textarea v-model="page.nextSteps" class="rw-ta" rows="5" @input="autoGrow" placeholder="Опишите предлагаемые следующие шаги…"></textarea>
            </div>
          </div>
        </template>

        <!-- ── matrix ── -->
        <template v-else>
          <div class="rw-field">
            <label class="rw-label">Быстрое добавление направлений</label>
            <div class="rw-presets">
              <button v-for="pr in PRESETS" :key="pr.label" class="rw-preset" @click="addRow(page, pr)">
                + {{ pr.label }}<span v-if="pr.auto" class="rw-auto-tag">авто</span>
              </button>
            </div>
          </div>
          <TransitionGroup tag="div" name="rwrow" class="rw-rows">
            <div v-for="(r, ri) in page.rows" :key="r.id" class="rw-row">
              <span class="rw-row-n">{{ ri + 1 }}</span>
              <input v-model="r.label" class="rw-input rw-row-label" placeholder="Направление…" />
              <div class="rw-row-val">
                <div v-if="r.auto" class="rw-auto-val"><span class="rw-auto-tag rw-auto-tag-on">авто</span>{{ autoValue(r.auto) }}</div>
                <textarea v-else v-model="r.value" class="rw-ta rw-row-ta" rows="1" @input="autoGrow" placeholder="Статус / значение…"></textarea>
              </div>
              <button class="rw-row-rm" @click="removeRow(page, r.id)" title="Удалить строку">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
              </button>
            </div>
          </TransitionGroup>
          <button class="rw-addrow" @click="addRow(page)">+ Своя строка</button>
        </template>
      </div>
    </TransitionGroup>

    <!-- ── Нижняя панель сохранения ── -->
    <div class="rw-savebar">
      <span class="rw-saved-info">
        <template v-if="savedBy || savedAt">Сохранено: <b>{{ savedBy || '—' }}</b><template v-if="savedAt"> · {{ fmtSavedAt() }}</template></template>
        <template v-else>Черновик ещё не сохранён</template>
      </span>
      <button class="rw-btn rw-btn-save rw-savebar-btn" :disabled="saving || loadError" @click="saveReport">
        {{ saving ? 'Сохранение…' : 'Сохранить отчёт' }}
      </button>
    </div>

    <!-- ── Печатный портал: A4-альбом, единая шапка + блоки направлений/матриц
         ТЕКУТ (несколько на лист), break-inside avoid — блок не рвётся по странице ── -->
    <Teleport to="body">
      <div class="rw-print-portal">
        <div class="rw-pp-page">
          <div class="rw-pp-head">
            <div class="rw-pp-toprow">
              <img :src="minfinLogoUrl" class="rw-pp-imv-img" alt="Иқтисодиёт ва молия вазирлиги" />
              <div class="rw-pp-brand">
                <svg class="rw-pp-logo" viewBox="0 0 240 220" width="26" height="24" aria-hidden="true">
                  <path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" fill="#534AB7" />
                  <g fill="#7F77DD"><rect x="56" y="50" width="8" height="8" /><rect x="42" y="64" width="7" height="7" /><rect x="50" y="96" width="7" height="7" /><rect x="36" y="116" width="7" height="7" /><rect x="48" y="150" width="7" height="7" /></g>
                </svg>
                <span class="rw-pp-brand-txt">Единая платформа<br />трансформации</span>
              </div>
              <img :src="uzassetsLogoUrl" class="rw-pp-uza-img" alt="UzAssets" />
            </div>
            <div class="rw-pp-titlerow">
              <h2>{{ companyName }}</h2>
              <span class="rw-pp-doc">Отчёт о ходе</span>
            </div>
            <div class="rw-pp-sub">FY {{ fy }}<template v-if="sectorName"> · {{ sectorName }}</template> · на {{ todayStr }}</div>
          </div>

          <div v-for="page in printablePages" :key="'rwpp_' + page.id" class="rw-pp-block">
            <div class="rw-pp-block-h">{{ page.type === 'matrix' ? (page.matrixTitle || 'Статус по ключевым направлениям') : dirName(page.directionId) }}</div>

            <!-- narrative -->
            <template v-if="page.type === 'narrative'">
              <div v-if="selProjects(page).length" class="rw-pp-keys">
                <div class="rw-pp-keys-l">Ключевые проекты</div>
                <div v-for="sp in selProjects(page)" :key="'k_' + sp.p.id" class="rw-pp-keyproj">
                  <div class="rw-pp-keyp-t">{{ sp.p.title }}<span class="rw-pp-key-d"> — {{ fmtDate(sp.p.due_date) }}</span></div>
                  <div v-for="t in sp.tasks" :key="'kt_' + t.id" class="rw-pp-keyt">— {{ t.title }}<span class="rw-pp-key-d"> · {{ fmtDate(t.due_date) }}</span></div>
                </div>
              </div>
              <div class="rw-pp-cols">
                <div class="rw-pp-col">
                  <div class="rw-pp-col-h">Текущий статус</div>
                  <div class="rw-pp-col-b">{{ page.status || '—' }}</div>
                </div>
                <div class="rw-pp-col">
                  <div class="rw-pp-col-h">Предложения по дальнейшим шагам</div>
                  <div class="rw-pp-col-b">{{ page.nextSteps || '—' }}</div>
                </div>
              </div>
            </template>

            <!-- matrix -->
            <table v-else class="rw-pp-mx">
              <thead>
                <tr><th class="rw-pp-mx-dir">Ключевое направление</th><th class="rw-pp-mx-vh">Статус</th></tr>
              </thead>
              <tbody>
                <tr v-for="(r, ri) in page.rows.filter(x => x.label || x.value || x.auto)" :key="'mr_' + r.id">
                  <td class="rw-pp-mx-dir"><span class="rw-pp-mx-n">{{ ri + 1 }}</span>{{ r.label || '—' }}</td>
                  <td class="rw-pp-mx-v">{{ r.auto ? autoValue(r.auto) : (r.value || '—') }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.rw { animation: rwIn .35s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.rw-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.rw-title { font-size: 17px; font-weight: 600; color: var(--t1, #1e2a4a); margin: 0; letter-spacing: -.01em; }
.rw-desc { font-size: 12.5px; color: var(--t3, #94a3b8); margin: 4px 0 0; max-width: 620px; line-height: 1.45; }
.rw-head-actions { display: flex; gap: 8px; flex-shrink: 0; flex-wrap: wrap; }
.rw-btn { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 9px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 12.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .14s; }
.rw-btn:hover { border-color: var(--p, #7f77dd); color: var(--p-deep, #534ab7); transform: translateY(-1px); }
.rw-btn-print { background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; border-color: transparent; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.rw-btn-print:hover { color: #fff; }
.rw-btn-print:disabled { opacity: .5; cursor: default; transform: none; box-shadow: none; }
.rw-btn-save { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.25); color: var(--p-deep, #5B53B8); font-weight: 600; }
.rw-btn-save:hover:not(:disabled) { background: #7f77dd; color: #fff; border-color: #7f77dd; }
.rw-btn-save:disabled { opacity: .6; cursor: default; }
.rw-btn-retry { color: #C5352F; border-color: rgba(226,75,74,.4); }
.rw-btn-retry:hover { background: rgba(226,75,74,.06); }
.rw-savebar { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; margin-top: 16px; padding: 12px 16px; border: 1px solid var(--border, rgba(99,102,180,.14)); border-radius: 12px; background: var(--bg2, #FAFBFC); }
.rw-saved-info { font-size: 12px; color: var(--t3, var(--t-muted)); }
.rw-saved-info b { color: var(--t1, #1E2A4A); font-weight: 600; }
.rw-savebar-btn { height: 38px; padding: 0 22px; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; border-color: transparent; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.rw-savebar-btn:hover:not(:disabled) { color: #fff; }

.rw-pages { display: flex; flex-direction: column; gap: 14px; position: relative; }
.rw-pg { position: relative; overflow: hidden; border: 1px solid var(--border, rgba(99,102,180,.14)); border-radius: 14px; background: var(--bg1, #fff); padding: 16px 18px; box-shadow: 0 1px 3px rgba(15,23,60,.03); transition: box-shadow .22s, border-color .22s, transform .22s; }
.rw-pg::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, #7f77dd, #6b62cc); transform: scaleX(0); transform-origin: left; transition: transform .3s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rw-pg:hover { box-shadow: 0 6px 20px -8px rgba(15,23,60,.12); }
.rw-pg:focus-within { box-shadow: 0 10px 30px -10px rgba(127,119,221,.3); border-color: rgba(127,119,221,.4); }
.rw-pg:focus-within::before { transform: scaleX(1); }
.rwpage-enter-active { transition: all .42s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rwpage-leave-active { transition: all .3s cubic-bezier(.4,0,1,1); position: absolute; left: 0; right: 0; }
.rwpage-enter-from { opacity: 0; transform: translateY(-14px) scale(.98); }
.rwpage-leave-to { opacity: 0; transform: translateX(-18px) scale(.97); }
.rwpage-move { transition: transform .42s var(--ease-out, cubic-bezier(.16,1,.3,1)); }

.rw-pg-top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rw-pg-n { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); background: rgba(127,119,221,.1); border-radius: 7px; padding: 3px 9px; flex-shrink: 0; }
.rw-pg-n.mx { color: #0f766e; background: rgba(20,184,166,.12); }
.rw-select, .rw-input { height: 36px; padding: 0 12px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 9px; background: var(--bg1, #fff); font-size: 13px; font-weight: 500; color: var(--t1, #1e2a4a); font-family: inherit; }
.rw-select { flex: 1; min-width: 220px; cursor: pointer; }
.rw-grow { flex: 1; min-width: 220px; }
.rw-select:focus, .rw-input:focus { outline: none; border-color: var(--p, #7f77dd); box-shadow: 0 0 0 3px rgba(127,119,221,.1); }
.rw-rm { height: 32px; padding: 0 12px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t3, #94a3b8); font-size: 12px; cursor: pointer; font-family: inherit; flex-shrink: 0; transition: all .14s; }
.rw-rm:hover { border-color: #E24B4A; color: #E24B4A; }

.rw-field { margin-top: 14px; }
.rw-label { display: block; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep, #534ab7); margin-bottom: 7px; }
.rw-picks { display: flex; flex-wrap: wrap; gap: 7px; }
.rw-pick { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; padding: 6px 11px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 9px; background: var(--bg1, #fff); cursor: pointer; font-family: inherit; transition: all .14s; text-align: left; }
.rw-pick:hover { border-color: var(--p, #7f77dd); }
.rw-pick.on { background: rgba(127,119,221,.1); border-color: var(--p, #7f77dd); }
.rw-pick:active { transform: scale(.96); }
.rw-pick-ck { width: 0; height: 15px; overflow: hidden; display: inline-flex; align-items: center; justify-content: center; color: var(--p-deep, #534ab7); transition: width .22s var(--ease-out, cubic-bezier(.16,1,.3,1)); flex-shrink: 0; }
.rw-pick-ck svg { width: 13px; height: 13px; transform: scale(0); transition: transform .28s var(--bounce, cubic-bezier(.34,1.56,.64,1)); }
.rw-pick.on .rw-pick-ck { width: 16px; }
.rw-pick.on .rw-pick-ck svg { transform: scale(1); }
.rw-pick-t { font-size: 12.5px; color: var(--t1, #1e2a4a); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; }
.rw-pick.on .rw-pick-t { color: var(--p-deep, #534ab7); }
.rw-pick-d { font-size: 10.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.rw-empty { font-size: 12px; color: var(--t3, #94a3b8); padding: 4px 2px; }
.rw-empty-sm { font-size: 11px; padding: 3px 2px; }

/* проект → задачи (выбор) */
.rw-projlist { display: flex; flex-direction: column; gap: 7px; }
.rw-pj { border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 10px; overflow: hidden; transition: border-color .14s, background .14s; }
.rw-pj.on { border-color: var(--p, #7f77dd); background: rgba(127,119,221,.04); }
.rw-pj-head { display: flex; align-items: center; gap: 9px; width: 100%; padding: 9px 12px; background: transparent; border: none; cursor: pointer; font-family: inherit; text-align: left; }
.rw-pj-t { font-size: 13px; font-weight: 500; color: var(--t1, #1e2a4a); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rw-pj.on .rw-pj-t { color: var(--p-deep, #534ab7); }
.rw-pj-d { font-size: 10.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.rw-pj.on .rw-pick-ck { width: 16px; }
.rw-pj.on .rw-pick-ck svg { transform: scale(1); }
.rw-pj-tasks { display: flex; flex-direction: column; gap: 1px; padding: 0 10px 9px 30px; }
.rw-tk { display: flex; align-items: center; gap: 8px; width: 100%; padding: 5px 9px; background: transparent; border: none; border-radius: 7px; cursor: pointer; font-family: inherit; text-align: left; transition: background .12s; }
.rw-tk:hover { background: rgba(127,119,221,.06); }
.rw-tk-t { font-size: 12px; color: var(--t2, #475569); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rw-tk.on .rw-tk-t { color: var(--t1, #1e2a4a); font-weight: 500; }
.rw-tk-d { font-size: 10px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.rw-tk.on .rw-pick-ck { width: 15px; }
.rw-tk.on .rw-pick-ck svg { transform: scale(1); }
.rw-ck-sm { height: 13px; }
.rw-ck-sm svg { width: 11px; height: 11px; }
.rw-tk-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 3px 9px 4px; }
.rw-tk-head-l { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94a3b8); }
.rw-tk-all { border: none; background: transparent; color: var(--p-deep, #534ab7); font-size: 11px; font-weight: 600; cursor: pointer; font-family: inherit; padding: 2px 4px; }
.rw-tk-all:hover { text-decoration: underline; }

.rw-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 14px; }
@media (max-width: 760px) { .rw-two { grid-template-columns: 1fr; } }
.rw-ta { width: 100%; min-height: 96px; padding: 11px 13px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 10px; background: var(--bg2, #fafafc); font-size: 13px; line-height: 1.5; color: var(--t1, #1e2a4a); font-family: inherit; resize: vertical; box-sizing: border-box; transition: border-color .14s, background .14s; }
.rw-ta:focus { outline: none; border-color: var(--p, #7f77dd); background: #fff; box-shadow: 0 0 0 3px rgba(127,119,221,.1); }
.rw-ta::placeholder { color: var(--t3, #b4b7c9); }

/* matrix form */
.rw-presets { display: flex; flex-wrap: wrap; gap: 7px; }
.rw-preset { position: relative; display: inline-flex; align-items: center; gap: 6px; padding: 6px 11px; border: 1px dashed var(--border, rgba(99,102,180,.3)); border-radius: 9px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .14s; }
.rw-preset:hover { border-style: solid; border-color: var(--p, #7f77dd); color: var(--p-deep, #534ab7); transform: translateY(-1px); }
.rw-auto-tag { font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #0f766e; background: rgba(20,184,166,.14); border-radius: 5px; padding: 1px 5px; }
.rw-auto-tag-on { margin-right: 7px; }
.rw-rows { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.rw-row { display: flex; align-items: flex-start; gap: 9px; }
.rw-row-n { flex-shrink: 0; width: 22px; height: 22px; margin-top: 7px; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; color: #fff; background: linear-gradient(135deg, #7f77dd, #6b62cc); border-radius: 50%; }
.rw-row-label { height: 38px; flex: 0 0 32%; min-width: 150px; }
.rw-row-val { flex: 1; min-width: 0; }
.rw-row-ta { min-height: 38px; }
.rw-auto-val { display: flex; align-items: center; min-height: 38px; padding: 8px 12px; border: 1px solid rgba(20,184,166,.3); border-radius: 10px; background: rgba(20,184,166,.06); font-size: 13px; color: var(--t1, #1e2a4a); line-height: 1.4; }
.rw-row-rm { flex-shrink: 0; width: 30px; height: 30px; margin-top: 4px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t3, #94a3b8); cursor: pointer; transition: all .14s; }
.rw-row-rm:hover { border-color: #E24B4A; color: #E24B4A; }
.rw-addrow { margin-top: 10px; height: 34px; padding: 0 14px; border: 1px dashed var(--border, rgba(99,102,180,.3)); border-radius: 9px; background: transparent; color: var(--p-deep, #534ab7); font-size: 12.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .14s; }
.rw-addrow:hover { border-style: solid; border-color: var(--p, #7f77dd); background: rgba(127,119,221,.05); }
.rwrow-enter-active, .rwrow-leave-active { transition: all .3s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rwrow-leave-active { position: absolute; }
.rwrow-enter-from { opacity: 0; transform: translateX(-12px); }
.rwrow-leave-to { opacity: 0; transform: translateX(-12px); }
.rwrow-move { transition: transform .3s var(--ease-out, cubic-bezier(.16,1,.3,1)); }

@keyframes rwIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
</style>

<!-- Глобальные стили печати: фирменный лист A4 (альбом), вне scoped (Teleport в body). -->
<style>
.rw-print-portal { display: none; }

@media print {
  body.rw-printing #app { display: none !important; }
  /* Тосты телепортируются в <body> (вне #app) → без этого попадали на печатный лист */
  body.rw-printing .uza-toast-container { display: none !important; }
  body.rw-printing .rw-print-portal { display: block !important; }

  @page { size: A4 landscape; margin: 0; }

  .rw-print-portal {
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    color: #1a1f3c;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .rw-pp-page { padding: 11mm 13mm; box-sizing: border-box; }
  /* блок направления/матрицы — НЕ рвём по странице, несколько блоков на лист */
  .rw-pp-block { break-inside: avoid; page-break-inside: avoid; margin-top: 9px; padding-top: 9px; border-top: .6pt solid #e7e7f0; }
  .rw-pp-block:first-of-type { margin-top: 4px; padding-top: 0; border-top: none; }
  .rw-pp-block-h { font-size: 10.5pt; font-weight: 700; color: #534AB7; margin-bottom: 6px; padding-bottom: 3px; border-bottom: 1pt solid #534AB7; }

  /* фирменная шапка: IMV слева · ЕПТ по центру · UzAssets справа */
  .rw-pp-head { border-bottom: 1.5pt solid #534AB7; padding-bottom: 9px; margin-bottom: 12px; }
  .rw-pp-toprow { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 9px; }
  .rw-pp-imv-img { height: 42px; width: auto; flex-shrink: 0; }
  .rw-pp-uza-img { height: 27px; width: auto; flex-shrink: 0; }
  .rw-pp-brand { display: flex; align-items: center; gap: 9px; }
  .rw-pp-logo { display: block; flex-shrink: 0; }
  .rw-pp-brand-txt { font-size: 8.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: #534AB7; line-height: 1.25; }
  .rw-pp-titlerow { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .rw-pp-head h2 { font-size: 18pt; font-weight: 600; margin: 0; letter-spacing: -.01em; color: #161b33; }
  .rw-pp-doc { font-size: 8.5pt; color: #8A90A8; font-weight: 500; }
  .rw-pp-sub { font-size: 8.5pt; color: #6b7088; margin-top: 4px; font-variant-numeric: tabular-nums; }

  /* narrative */
  .rw-pp-keys { font-size: 8.5pt; color: #1a1f3c; line-height: 1.55; margin-bottom: 11px; }
  .rw-pp-keys-l { display: block; font-weight: 700; color: #534AB7; text-transform: uppercase; font-size: 8pt; letter-spacing: .04em; margin-bottom: 4px; }
  .rw-pp-keyproj { margin-bottom: 4px; break-inside: avoid; }
  .rw-pp-keyp-t { font-size: 8.5pt; color: #1a1f3c; font-weight: 600; line-height: 1.4; }
  .rw-pp-keyt { font-size: 8pt; color: #5a6072; padding-left: 13px; line-height: 1.4; }
  .rw-pp-key-d { color: #6b7088; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .rw-pp-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; align-items: start; }
  .rw-pp-col-h { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #534AB7; background: rgba(127,119,221,.1); padding: 3px 8px; border-radius: 3px; margin-bottom: 6px; }
  .rw-pp-col-b { font-size: 9.5pt; line-height: 1.5; color: #1a1f3c; white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }

  /* matrix — таблица направление × статус, гибкая, без обрезки */
  .rw-pp-mx { border-collapse: collapse; width: 100%; }
  .rw-pp-mx thead th { font-size: 8pt; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #fff; background: #534AB7; padding: 5px 9px; text-align: left; }
  .rw-pp-mx th.rw-pp-mx-dir { width: 32%; border-right: 1pt solid rgba(255,255,255,.25); }
  .rw-pp-mx tbody td { border: .5pt solid #d7d9e6; padding: 6px 9px; vertical-align: top; font-size: 9.5pt; line-height: 1.45; }
  .rw-pp-mx tbody tr:nth-child(even) td { background: #f7f7fb; }
  .rw-pp-mx-dir { font-weight: 600; color: #161b33; }
  .rw-pp-mx-n { display: inline-flex; align-items: center; justify-content: center; width: 14pt; height: 14pt; margin-right: 6px; font-size: 7pt; font-weight: 700; color: #fff; background: #7F77DD; border-radius: 50%; }
  .rw-pp-mx-v { color: #1a1f3c; white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }
  .rw-pp-mx tbody tr { break-inside: avoid; }
}
</style>
