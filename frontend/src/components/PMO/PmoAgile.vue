<script setup lang="ts">
/**
 * PmoAgile — Scrum: бэклог + доска спринта (PMBOK 7 / Agile).
 *
 * Спринт группирует СУЩЕСТВУЮЩИЕ задачи (tasks.sprint_id) — переиспользуем
 * исполнителей/прогресс/связи с Ганттом/EVM. Бэклог = открытые задачи без
 * спринта; доска спринта = канбан по статусам с drag-and-drop.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useAuthStore } from "@/stores/auth";
import {
  pmoApi,
  type AgileResponse, type AgileTask, type Sprint, type SprintPayload, type SprintStatus,
} from "@/api/pmo";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t: tr } = useI18n();
const t = tr;


const props = defineProps<{ companyCode: string; canEdit?: boolean; year?: number }>();

const toast = useToast();
const { confirmDialog } = useConfirm();
const auth = useAuthStore();
const myId = computed(() => (auth.user as any)?.id || null);

// Приоритеты (как в Jira/ClickUp) — флаги
const PRIORITY: Record<string, { l: string; c: string }> = {
  high: { l: i18nKey("Высокий"), c: "#E24B4A" },
  medium: { l: i18nKey("Средний"), c: "#EF9F27" },
  low: { l: i18nKey("Низкий"), c: "#94A3B8" },
};
const PRI_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };
function pri(t: AgileTask) { return PRIORITY[t.priority] || PRIORITY.medium; }

// Фильтры доски/бэклога (исполнитель / приоритет / только мои)
const filterAssignee = ref<string | null>(null);
const filterPriority = ref<string | null>(null);
const onlyMine = ref(false);
function matchF(t: AgileTask): boolean {
  if (onlyMine.value && t.assignee_id !== myId.value) return false;
  if (filterAssignee.value && t.assignee_id !== filterAssignee.value) return false;
  if (filterPriority.value && t.priority !== filterPriority.value) return false;
  return true;
}
const hasFilters = computed(() => !!(filterAssignee.value || filterPriority.value || onlyMine.value));
function resetFilters() { filterAssignee.value = null; filterPriority.value = null; onlyMine.value = false; }

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<AgileResponse | null>(null);
const activeView = ref<string>("backlog"); // "backlog" | sprintId

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await pmoApi.getAgile(props.companyCode, props.year);
    // если активный спринт есть — открыть его по умолчанию
    if (activeView.value === "backlog") {
      const act = data.value.sprints.find(s => s.status === "active");
      if (act) activeView.value = act.id;
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || tr('Не удалось загрузить Agile-доску');
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => [props.companyCode, props.year], load);

const sprints = computed<Sprint[]>(() => data.value?.sprints || []);
const tasks = computed<AgileTask[]>(() => data.value?.tasks || []);

const SP_STATUS: Record<SprintStatus, { l: string; c: string }> = {
  planned: { l: i18nKey("Планируется"), c: "#94a3b8" },
  active: { l: i18nKey("Активный"), c: "#1D9E75" },
  done: { l: i18nKey("Завершён"), c: "#534AB7" },
};

const _CLOSED = ["done", "deferred"];
const backlog = computed(() =>
  tasks.value
    .filter(t => !t.sprint_id && !_CLOSED.includes(t.status) && matchF(t))
    .sort((a, b) => {
      const pa = PRI_ORDER[a.priority] ?? 1, pb = PRI_ORDER[b.priority] ?? 1;
      if (pa !== pb) return pa - pb;                       // приоритет ↓
      return (a.due_date || "9999").localeCompare(b.due_date || "9999"); // срок ↑
    }),
);
function sprintTasks(sid: string) { return tasks.value.filter(t => t.sprint_id === sid); }

// Исполнители для фильтра (по всем задачам)
const assigneesInView = computed(() => {
  const m = new Map<string, string>();
  for (const t of tasks.value) if (t.assignee_id && t.assignee_name) m.set(t.assignee_id, t.assignee_name);
  return Array.from(m, ([id, name]) => ({ id, name }));
});
const currentSprint = computed<Sprint | null>(() =>
  activeView.value === "backlog" ? null : sprints.value.find(s => s.id === activeView.value) || null,
);

function sumPoints(list: AgileTask[]) { return list.reduce((a, t) => a + (t.story_points || 0), 0); }
function sprintStat(sid: string) {
  const list = sprintTasks(sid);
  const committed = sumPoints(list);
  const done = sumPoints(list.filter(t => t.status === "done"));
  return { committed, done, total: list.length, pct: committed ? Math.round((done / committed) * 100) : 0 };
}

// ── Доска: колонки ──
const COLUMNS = [
  { key: "todo", label: i18nKey("К работе"), statuses: ["new", "init"], canonical: "new" },
  { key: "active", label: i18nKey("В работе"), statuses: ["active"], canonical: "active" },
  { key: "review", label: i18nKey("На согласовании"), statuses: ["review"], canonical: "review" },
  { key: "done", label: i18nKey("Готово"), statuses: ["done"], canonical: "done" },
];
function colTasks(sid: string, col: typeof COLUMNS[number]) {
  return sprintTasks(sid).filter(t => col.statuses.includes(t.status) && matchF(t));
}
function colPoints(sid: string, col: typeof COLUMNS[number]) {
  return sumPoints(colTasks(sid, col));
}

function avInitials(name?: string | null): string {
  const n = (name || "").trim();
  if (!n) return "?";
  const p = n.split(/\s+/).filter(Boolean);
  return ((p[0]?.[0] || "") + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() || "?";
}

// ── Patch задачи (drag / в спринт / story points) ──
const busy = ref(false);
async function patchTask(taskId: string, body: any) {
  busy.value = true;
  try {
    data.value = await pmoApi.patchTaskAgile(taskId, props.companyCode, body);
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || tr('Не удалось сохранить'));
    await load();
  } finally { busy.value = false; }
}
async function assignToSprint(t: AgileTask, sid: string | null) {
  await patchTask(t.id, { sprint_id: sid });
  if (sid) toast.success(tr('Задача в спринте')); else toast.success(tr('Возвращено в бэклог'));
}
async function setPoints(t: AgileTask, ev: Event) {
  const v = (ev.target as HTMLInputElement).value;
  const n = v === "" ? null : Math.max(0, parseInt(v, 10) || 0);
  if (n === t.story_points) return;
  await patchTask(t.id, { story_points: n });
}

// ── Drag ──
const dragId = ref<string | null>(null);
const dragOverCol = ref<string | null>(null);
function onDragStart(t: AgileTask) { dragId.value = t.id; }
function onDragEnd() { dragId.value = null; dragOverCol.value = null; }
async function onDrop(col: typeof COLUMNS[number]) {
  const id = dragId.value; dragOverCol.value = null; dragId.value = null;
  if (!id) return;
  const t = tasks.value.find(x => x.id === id);
  if (!t || col.statuses.includes(t.status)) return;
  await patchTask(id, { status: col.canonical });
}

// ── Спринт: модалка ──
const sprintOpen = ref(false);
const sprintEditId = ref<string | null>(null);
const sBlank = (): SprintPayload => ({ name: "", goal: "", start_date: null, end_date: null, status: "planned", capacity_points: null });
const sForm = ref<SprintPayload>(sBlank());
const saving = ref(false);
function sprintCreate() { sForm.value = sBlank(); sprintEditId.value = null; sprintOpen.value = true; }
function sprintEdit(s: Sprint) {
  sForm.value = { name: s.name, goal: s.goal || "", start_date: s.start_date, end_date: s.end_date, status: s.status, capacity_points: s.capacity_points };
  sprintEditId.value = s.id; sprintOpen.value = true;
}
async function sprintSave() {
  if (!sForm.value.name?.trim()) { toast.error(tr('Название спринта обязательно')); return; }
  saving.value = true;
  try {
    if (sprintEditId.value) await pmoApi.updateSprint(sprintEditId.value, sForm.value);
    else { const s = await pmoApi.createSprint(props.companyCode, sForm.value); activeView.value = s.id; }
    sprintOpen.value = false;
    await load();
    toast.success(sprintEditId.value ? tr('Спринт сохранён') : tr('Спринт создан'));
  } catch (e: any) { toast.error(e?.response?.data?.detail || tr('Не удалось сохранить')); }
  finally { saving.value = false; }
}
async function setSprintStatus(s: Sprint, status: SprintStatus) {
  try { await pmoApi.updateSprint(s.id, { status }); await load(); toast.success(tr('Статус спринта обновлён')); }
  catch (e: any) { toast.error(tr('Не удалось обновить')); }
}
async function sprintRemove(s: Sprint) {
  if (!(await confirmDialog({ message: tr('Удалить спринт «{value0}»? Задачи вернутся в бэклог.', { value0: s.name }), danger: true }))) return;
  try { await pmoApi.deleteSprint(s.id); if (activeView.value === s.id) activeView.value = "backlog"; await load(); toast.success(tr('Спринт удалён')); }
  catch (e: any) { toast.error(tr('Не удалось удалить')); }
}

const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString(getCurrentIntlLocale(), { day: "numeric", month: "short" }) : "—";
</script>

<template>
  <div class="ag">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />
    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка Agile-доски…')" />

    <template v-else>
      <!-- селектор: бэклог + спринты -->
      <div class="ag-bar">
        <div class="ag-chips">
          <button class="ag-chip" :class="{ on: activeView === 'backlog' }" @click="activeView = 'backlog'">
            {{ tr('Бэклог') }} <span class="ag-n">{{ backlog.length }}</span>
          </button>
          <button v-for="s in sprints" :key="s.id" class="ag-chip" :class="{ on: activeView === s.id }" @click="activeView = s.id">
            <span class="ag-dot" :style="{ background: SP_STATUS[s.status].c }"></span>
            {{ s.name }} <span class="ag-n">{{ sprintTasks(s.id).length }}</span>
          </button>
        </div>
        <button v-if="canEdit" class="ag-add" @click="sprintCreate">{{ tr('+ Спринт') }}</button>
      </div>

      <!-- фильтры (Jira/ClickUp-стиль): приоритет + исполнитель + мои -->
      <div v-if="tasks.length" class="ag-filters">
        <span class="ag-flabel">{{ tr('Приоритет') }}</span>
        <button class="ag-fchip" :class="{ on: !filterPriority }" @click="filterPriority = null">{{ tr('Все') }}</button>
        <button
          v-for="(p, k) in PRIORITY" :key="k"
          class="ag-fchip" :class="{ on: filterPriority === k }"
          :style="filterPriority === k ? { color: p.c, background: p.c + '1a', borderColor: p.c + '66' } : {}"
          @click="filterPriority = filterPriority === k ? null : k"
        ><span class="ag-flag" :style="{ background: p.c }"></span>{{ tr(p.l) }}</button>

        <span class="ag-fdiv"></span>
        <button v-if="myId" class="ag-fchip" :class="{ on: onlyMine }" @click="onlyMine = !onlyMine">{{ tr('Только мои') }}</button>
        <button
          v-for="a in assigneesInView" :key="a.id"
          class="ag-fav" :class="{ on: filterAssignee === a.id }" :title="a.name"
          @click="filterAssignee = filterAssignee === a.id ? null : a.id"
        >{{ avInitials(a.name) }}</button>

        <button v-if="hasFilters" class="ag-freset" @click="resetFilters">{{ tr('Сбросить') }}</button>
      </div>

      <!-- ── БЭКЛОГ ── -->
      <div v-if="activeView === 'backlog'">
        <UzaStateBlock v-if="!backlog.length" state="empty" variant="block" :title="tr('Бэклог пуст')" :text="t('Сюда попадают открытые задачи без спринта. Создайте задачи в разделе «Задачи» или снимите задачи со спринта.')" />
        <div v-else class="ag-list">
          <div v-for="(t, i) in backlog" :key="t.id" class="ag-bli" :style="{ animationDelay: Math.min(i*0.02, 0.3)+'s' }">
            <span class="ag-pflag" :style="{ background: pri(t).c }" :title="tr('Приоритет: {value0}', { value0: tr(pri(t).l) })"></span>
            <div class="ag-bli-main">
              <div class="ag-bli-title">{{ t.title }}</div>
              <div class="ag-bli-meta">
                <span v-if="t.project_title" class="ag-bli-proj">{{ t.project_title }}</span>
                <span v-if="t.assignee_name" class="ag-bli-assignee"><span class="ag-av">{{ avInitials(t.assignee_name) }}</span>{{ t.assignee_name }}</span>
                <span v-for="tag in t.tags" :key="tag" class="ag-tag">{{ tag }}</span>
              </div>
            </div>
            <div class="ag-bli-sp">
              <input v-if="canEdit" type="number" min="0" class="ag-sp-input" :value="t.story_points ?? ''" placeholder="SP" title="Story points" @change="setPoints(t, $event)" />
              <span v-else-if="t.story_points != null" class="ag-sp">{{ t.story_points }} SP</span>
            </div>
            <select v-if="canEdit && sprints.length" class="ag-bli-sel" :value="''" @change="assignToSprint(t, ($event.target as HTMLSelectElement).value || null)">
              <option value="">{{ tr('→ в спринт…') }}</option>
              <option v-for="s in sprints" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </div>
        </div>
        <div v-if="!sprints.length && canEdit" class="ag-hint">{{ tr('Создайте спринт, чтобы перетаскивать в него задачи из бэклога.') }}</div>
      </div>

      <!-- ── ДОСКА СПРИНТА ── -->
      <div v-else-if="currentSprint">
        <div class="ag-sprint-head">
          <div class="ag-sh-main">
            <div class="ag-sh-top">
              <span class="ag-sh-name">{{ currentSprint.name }}</span>
              <span class="ag-sh-status" :style="{ color: SP_STATUS[currentSprint.status].c, background: SP_STATUS[currentSprint.status].c + '1a' }">{{ tr(SP_STATUS[currentSprint.status].l) }}</span>
              <span class="ag-sh-dates">{{ fmtDate(currentSprint.start_date) }} — {{ fmtDate(currentSprint.end_date) }}</span>
            </div>
            <div v-if="currentSprint.goal" class="ag-sh-goal">{{ currentSprint.goal }}</div>
          </div>
          <div class="ag-sh-side">
            <div class="ag-sh-points">
              <span class="ag-sh-pn">{{ sprintStat(currentSprint.id).done }}<span class="ag-sh-pd">/{{ sprintStat(currentSprint.id).committed }}</span></span>
              <span class="ag-sh-pl">{{ tr('SP готово') }}<template v-if="currentSprint.capacity_points"> {{ tr('· ёмкость') }} {{ currentSprint.capacity_points }}</template></span>
              <div class="ag-sh-bar"><span class="ag-sh-bar-fill" :style="{ width: sprintStat(currentSprint.id).pct + '%' }"></span></div>
            </div>
            <div v-if="canEdit" class="ag-sh-actions">
              <button v-if="currentSprint.status === 'planned'" class="ag-sb ag-sb-ok" @click="setSprintStatus(currentSprint, 'active')">{{ tr('Старт') }}</button>
              <button v-else-if="currentSprint.status === 'active'" class="ag-sb ag-sb-ok" @click="setSprintStatus(currentSprint, 'done')">{{ tr('Завершить') }}</button>
              <button class="ag-sb" @click="sprintEdit(currentSprint)" :title="tr('Править')"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
              <button class="ag-sb ag-sb-del" @click="sprintRemove(currentSprint)" :title="tr('Удалить')"><svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button>
            </div>
          </div>
        </div>

        <div class="ag-board">
          <div
            v-for="col in COLUMNS" :key="col.key"
            class="ag-col" :class="{ over: dragOverCol === col.key }"
            @dragover.prevent="dragOverCol = col.key" @dragleave="dragOverCol = null" @drop.prevent="onDrop(col)"
          >
            <div class="ag-col-head"><span>{{ tr(col.label) }}</span><span v-if="colPoints(currentSprint.id, col)" class="ag-col-sp">{{ colPoints(currentSprint.id, col) }} SP</span><span class="ag-col-n">{{ colTasks(currentSprint.id, col).length }}</span></div>
            <div class="ag-col-body">
              <div
                v-for="t in colTasks(currentSprint.id, col)" :key="t.id"
                class="ag-card" :class="{ dragging: dragId === t.id }"
                :draggable="canEdit" @dragstart="onDragStart(t)" @dragend="onDragEnd"
              >
                <div v-if="t.priority !== 'medium' || t.tags.length" class="ag-card-tags">
                  <span v-if="t.priority !== 'medium'" class="ag-pchip" :style="{ color: pri(t).c, background: pri(t).c + '1a' }"><span class="ag-flag" :style="{ background: pri(t).c }"></span>{{ tr(pri(t).l) }}</span>
                  <span v-for="tag in t.tags.slice(0, 3)" :key="tag" class="ag-tag">{{ tag }}</span>
                </div>
                <div class="ag-card-title">{{ t.title }}</div>
                <div v-if="t.project_title" class="ag-card-proj">{{ t.project_title }}</div>
                <div class="ag-card-foot">
                  <span v-if="t.assignee_name" class="ag-av ag-av-sm" :title="t.assignee_name">{{ avInitials(t.assignee_name) }}</span>
                  <span v-else class="ag-av ag-av-sm ag-av-none">?</span>
                  <input v-if="canEdit" type="number" min="0" class="ag-sp-input ag-sp-card" :value="t.story_points ?? ''" placeholder="SP" title="Story points" @change="setPoints(t, $event)" @dragstart.stop @mousedown.stop />
                  <span v-else-if="t.story_points != null" class="ag-sp">{{ t.story_points }}</span>
                  <button v-if="canEdit" class="ag-card-back" :title="tr('В бэклог')" @click="assignToSprint(t, null)"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 14l-4-4 4-4"/><path d="M5 10h11a4 4 0 0 1 0 8h-1"/></svg></button>
                </div>
              </div>
              <div v-if="!colTasks(currentSprint.id, col).length" class="ag-col-empty">—</div>
            </div>
          </div>
        </div>
        <div v-if="canEdit" class="ag-hint">{{ tr('Перетаскивайте карточки между колонками, чтобы менять статус. Кнопка ↩ — вернуть задачу в бэклог.') }}</div>
      </div>
    </template>

    <!-- модалка спринта -->
    <Transition name="ag-modal">
      <div v-if="sprintOpen" class="ag-ov" @click.self="sprintOpen = false">
        <div class="ag-modal">
          <div class="ag-mh">{{ sprintEditId ? tr('Правка спринта') : tr('Новый спринт') }}</div>
          <div class="ag-mb">
            <div class="ag-f"><label>{{ tr('Название') }}</label><input v-model="sForm.name" :placeholder="tr('Например: Спринт 5')" /></div>
            <div class="ag-f"><label>{{ tr('Цель спринта') }}</label><textarea v-model="sForm.goal" rows="2" :placeholder="tr('Что хотим достичь')"></textarea></div>
            <div class="ag-f3">
              <div class="ag-f"><label>{{ tr('Старт') }}</label><input v-model="sForm.start_date" type="date" /></div>
              <div class="ag-f"><label>{{ tr('Финиш') }}</label><input v-model="sForm.end_date" type="date" /></div>
              <div class="ag-f"><label>{{ tr('Ёмкость (SP)') }}</label><input v-model.number="sForm.capacity_points" type="number" min="0" placeholder="0" /></div>
            </div>
            <div class="ag-f"><label>{{ tr('Статус') }}</label>
              <select v-model="sForm.status"><option value="planned">{{ tr('Планируется') }}</option><option value="active">{{ tr('Активный') }}</option><option value="done">{{ tr('Завершён') }}</option></select>
            </div>
          </div>
          <div class="ag-mf"><button class="ag-bg" @click="sprintOpen = false">{{ tr('Отмена') }}</button><button class="ag-b" :disabled="saving" @click="sprintSave">{{ saving ? tr('Сохраняю…') : tr('Сохранить') }}</button></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.ag { padding: 4px 2px 24px; }

.ag-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.ag-chips { display: inline-flex; gap: 6px; flex-wrap: wrap; }
.ag-chip { display: inline-flex; align-items: center; gap: 6px; padding: 7px 13px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 11px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 12px; font-weight: 500; font-family: inherit; cursor: pointer; transition: all .16s var(--ease-standard); }
.ag-chip:hover { border-color: rgba(124,111,247,.5); }
.ag-chip.on { background: rgba(124,111,247,.12); color: var(--p-deep, #534ab7); border-color: rgba(124,111,247,.4); }
.ag-dot { width: 7px; height: 7px; border-radius: 50%; }
.ag-n { font-size: 10px; font-weight: 700; opacity: .65; }
.ag-add { margin-left: auto; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: transform .15s; }
.ag-add:hover { transform: translateY(-1px); }

/* filters (Jira/ClickUp) */
.ag-filters { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border, rgba(99,102,180,.1)); }
.ag-flabel { font-size: 9px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); font-weight: 600; margin-right: 2px; }
.ag-fchip { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 14px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s; }
.ag-fchip:hover { border-color: rgba(124,111,247,.5); }
.ag-fchip.on { background: rgba(124,111,247,.12); color: var(--p-deep, #534ab7); border-color: rgba(124,111,247,.4); }
.ag-flag { width: 8px; height: 8px; border-radius: 2px; flex-shrink: 0; }
.ag-fdiv { width: 1px; height: 18px; background: var(--border, rgba(99,102,180,.16)); margin: 0 4px; }
.ag-fav { width: 26px; height: 26px; border-radius: 50%; border: 1.5px solid transparent; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 9px; font-weight: 700; cursor: pointer; font-family: inherit; transition: all .15s; }
.ag-fav:hover { transform: scale(1.08); }
.ag-fav.on { border-color: var(--p, #7c6ff7); box-shadow: 0 0 0 2px rgba(124,111,247,.25); }
.ag-freset { padding: 5px 11px; border: none; border-radius: 7px; background: transparent; color: var(--t3, #94a3b8); font-size: 11px; cursor: pointer; font-family: inherit; }
.ag-freset:hover { color: #e24b4a; }

/* priority flag + tags */
.ag-pflag { width: 9px; height: 9px; border-radius: 2px; flex-shrink: 0; }
.ag-pchip { display: inline-flex; align-items: center; gap: 4px; font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 6px; }
.ag-tag { font-size: 9.5px; font-weight: 500; padding: 1px 7px; border-radius: 8px; background: rgba(30,42,74,.06); color: var(--t2, #475569); }

/* backlog list */
.ag-list { display: flex; flex-direction: column; gap: 6px; }
.ag-bli { display: flex; align-items: center; gap: 11px; padding: 10px 13px; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 11px; background: var(--bg1, #fff); animation: agIn .35s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; transition: box-shadow .18s, transform .18s; }
.ag-bli:hover { box-shadow: 0 5px 14px rgba(15,23,60,.06); transform: translateY(-1px); }
.ag-bli-status { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: #94a3b8; }
.ag-bli-status[data-s="active"] { background: #7C6FF7; }
.ag-bli-status[data-s="review"] { background: #D97706; }
.ag-bli-status[data-s="new"], .ag-bli-status[data-s="init"] { background: #94a3b8; }
.ag-bli-main { flex: 1; min-width: 0; }
.ag-bli-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1e2a4a); }
.ag-bli-meta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 3px; }
.ag-bli-proj { font-size: 10px; font-weight: 600; padding: 1px 7px; border-radius: 9px; background: rgba(127,119,221,.1); color: var(--p-deep, #534ab7); }
.ag-bli-assignee { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--t3, #94a3b8); }
.ag-av { width: 18px; height: 18px; border-radius: 50%; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 700; flex-shrink: 0; }
.ag-av-sm { width: 20px; height: 20px; font-size: 8.5px; }
.ag-av-none { background: rgba(30,42,74,.12); color: var(--t3, #94a3b8); }
.ag-bli-sp { flex-shrink: 0; }
.ag-sp { font-size: 10.5px; font-weight: 700; color: var(--p-deep, #534ab7); }
.ag-sp-input { width: 46px; padding: 4px 6px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 7px; font-size: 11px; font-family: inherit; text-align: center; outline: none; color: var(--t1, #1e2a4a); background: var(--bg1, #fff); }
.ag-sp-input:focus { border-color: #7c6ff7; }
.ag-sp-card { width: 40px; padding: 2px 4px; margin-left: auto; }
.ag-bli-sel { flex-shrink: 0; padding: 6px 8px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; font-family: inherit; cursor: pointer; }
.ag-hint { margin-top: 12px; font-size: 10.5px; color: var(--t3, #94a3b8); }

/* sprint header */
.ag-sprint-head { display: flex; gap: 16px; justify-content: space-between; flex-wrap: wrap; padding: 14px 16px; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 13px; background: var(--bg1, #fff); margin-bottom: 14px; }
.ag-sh-main { min-width: 0; flex: 1; }
.ag-sh-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.ag-sh-name { font-size: 15px; font-weight: 600; color: var(--t1, #1e2a4a); }
.ag-sh-status { font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 7px; }
.ag-sh-dates { font-size: 11px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.ag-sh-goal { font-size: 12px; color: var(--t2, #475569); margin-top: 6px; line-height: 1.5; }
.ag-sh-side { display: flex; align-items: center; gap: 14px; }
.ag-sh-points { min-width: 130px; }
.ag-sh-pn { font-size: 20px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.ag-sh-pd { color: var(--t3, #94a3b8); font-size: 14px; }
.ag-sh-pl { display: block; font-size: 9px; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); margin: 1px 0 5px; }
.ag-sh-bar { height: 5px; border-radius: 3px; background: rgba(30,42,74,.08); overflow: hidden; }
.ag-sh-bar-fill { display: block; height: 100%; border-radius: 3px; background: linear-gradient(90deg, #7f77dd, #1d9e75); transition: width .5s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.ag-sh-actions { display: flex; gap: 5px; }
.ag-sb { display: inline-flex; align-items: center; padding: 6px 11px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s; }
.ag-sb:hover { border-color: #7c6ff7; color: #7c6ff7; }
.ag-sb-ok { background: linear-gradient(135deg, #1D9E75, #17916a); color: #fff; border-color: transparent; }
.ag-sb-ok:hover { color: #fff; transform: translateY(-1px); }
.ag-sb-del:hover { border-color: #e24b4a; color: #e24b4a; }

/* board */
.ag-board { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
.ag-col { background: var(--bg2, #fafafc); border: 1px solid var(--border, rgba(99,102,180,.08)); border-radius: 12px; padding: 8px; min-height: 120px; transition: background .16s, border-color .16s; }
.ag-col.over { background: rgba(124,111,247,.07); border-color: rgba(124,111,247,.4); }
.ag-col-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 6px 8px; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); }
.ag-col-sp { margin-left: auto; background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); border-radius: 8px; padding: 0 6px; font-size: 9px; font-weight: 700; }
.ag-col-n { background: rgba(30,42,74,.06); border-radius: 8px; padding: 0 6px; font-size: 9.5px; }
.ag-col-body { display: flex; flex-direction: column; gap: 7px; }
.ag-col-empty { text-align: center; color: var(--t3, #cbd5e1); font-size: 12px; padding: 10px 0; }
.ag-card { background: var(--bg1, #fff); border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 10px; padding: 9px 11px; cursor: grab; box-shadow: 0 1px 2px rgba(15,23,60,.03); transition: box-shadow .16s, transform .16s, opacity .16s; animation: agCardIn .3s var(--ease-out) both; }
.ag-card:hover { box-shadow: 0 5px 14px rgba(15,23,60,.09); transform: translateY(-1px); }
.ag-card.dragging { opacity: .4; cursor: grabbing; }
.ag-card-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.ag-card-title { font-size: 12px; font-weight: 500; color: var(--t1, #1e2a4a); line-height: 1.4; }
.ag-card-proj { font-size: 9.5px; color: var(--t3, #94a3b8); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ag-card-foot { display: flex; align-items: center; gap: 7px; margin-top: 8px; }
.ag-card-back { margin-left: 2px; background: none; border: none; cursor: pointer; color: var(--t3, #94a3b8); padding: 3px; border-radius: 6px; transition: all .14s; }
.ag-card-back:hover { background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); }

@keyframes agIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes agCardIn { from { opacity: 0; transform: scale(.97); } to { opacity: 1; transform: none; } }

/* modal */
.ag-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.ag-modal { background: var(--bg1, #fff); border-radius: 14px; width: min(520px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl); }
.ag-mh { padding: 14px 18px; font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.ag-mb { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 11px; }
.ag-f { display: flex; flex-direction: column; gap: 5px; }
.ag-f3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.ag-f label { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.ag-f input, .ag-f select, .ag-f textarea { padding: 8px 11px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: 12.5px; font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); transition: border-color .15s; }
.ag-f input:focus, .ag-f select:focus, .ag-f textarea:focus { border-color: #7c6ff7; }
.ag-f textarea { resize: vertical; }
.ag-mf { padding: 12px 18px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }
.ag-b { padding: 8px 16px; border-radius: 9px; border: none; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.ag-b:disabled { opacity: .5; }
.ag-bg { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--border, rgba(99,102,180,.18)); background: transparent; color: var(--t2, #475569); font-size: 11.5px; cursor: pointer; font-family: inherit; }
.ag-modal-enter-active { transition: opacity .2s ease; }
.ag-modal-enter-active .ag-modal { transition: transform .32s var(--ease-out, cubic-bezier(.16,1,.3,1)), opacity .2s ease; }
.ag-modal-leave-active { transition: opacity .16s ease; }
.ag-modal-enter-from { opacity: 0; }
.ag-modal-enter-from .ag-modal { transform: scale(.95) translateY(14px); opacity: 0; }
.ag-modal-leave-to { opacity: 0; }

@media (max-width: 1000px) { .ag-board { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 560px) { .ag-board { grid-template-columns: 1fr; } .ag-f3 { grid-template-columns: 1fr; } }
</style>
