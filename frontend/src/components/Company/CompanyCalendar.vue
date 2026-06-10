<script setup lang="ts">
/**
 * CompanyCalendar — премиальный календарь дедлайнов (Месяц / Неделя / Повестка).
 * Авто-агрегация из project/task.due_date, scoped по компании (или все — global).
 * Фильтры: статус, только просроченные, только отслеживаемые. Клик по событию →
 * emit open-entity. Заметки с датой видны в company-режиме.
 */
import { ref, computed, onMounted, watch } from "vue";
import { calendarApi, type CalendarEvent } from "@/api/calendar";
import { notesApi, type Note } from "@/api/notes";
import { watchesApi } from "@/api/watches";
import { useEntityEditor } from "@/composables/useEntityEditor";

const entityEditor = useEntityEditor();
const props = defineProps<{ companyId?: string | null }>();
const emit = defineEmits<{ (e: "open-entity", payload: { entity_type: "project" | "task"; entity_id: string; company_id: string | null }): void }>();
const isGlobal = computed(() => !props.companyId);

const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const today = new Date();
const cur = ref(new Date(today.getFullYear(), today.getMonth(), today.getDate())); // якорь
const events = ref<CalendarEvent[]>([]);
const notes = ref<Note[]>([]);
const watchedSet = ref<Set<string>>(new Set());
const loading = ref(false);
const selectedKey = ref<string | null>(null);
const dir = ref(0);

const view = ref<"month" | "week" | "agenda">("month");
const fStatus = ref<string | null>(null);
const fOverdue = ref(false);
const fWatched = ref(false);

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function monKey(d: Date) { return ymd(d).slice(0, 7); }

// ─── Загрузка (широкий диапазон — все виды фильтруют один набор) ───
async function load() {
  loading.value = true;
  const from = ymd(new Date(today.getFullYear(), today.getMonth() - 3, 1));
  const to = ymd(new Date(today.getFullYear() + 1, today.getMonth() + 2, 0));
  try {
    const [ev, nt, w] = await Promise.all([
      calendarApi.events(from, to, props.companyId || undefined),
      props.companyId
        ? notesApi.list({ company_id: props.companyId, limit: 500 }).then((r) => r.items || []).catch(() => [])
        : Promise.resolve([] as Note[]),
      watchesApi.mine().then((items) => new Set(items.map((i) => `${i.entity_type}:${i.entity_id}`))).catch(() => new Set<string>()),
    ]);
    events.value = ev; notes.value = nt; watchedSet.value = w;
  } catch { events.value = []; notes.value = []; } finally { loading.value = false; }
}
onMounted(load);
watch(() => props.companyId, load);

// ─── Состояние дедлайна → цвет ───
function evState(e: CalendarEvent): "overdue" | "soon" | "done" | "future" {
  if (e.status === "done") return "done";
  if (!e.due_date) return "future";
  const diff = Math.floor((new Date(e.due_date).getTime() - today.getTime()) / 86400000);
  if (diff < 0) return "overdue";
  if (diff <= 3) return "soon";
  return "future";
}
const STATE_COLOR: Record<string, string> = { overdue: "#E24B4A", soon: "#EF9F27", future: "#7F77DD", done: "#1D9E75" };

const STATUS_OPTS = [
  { v: "active", l: "В процессе" }, { v: "review", l: "На проверке" }, { v: "done", l: "Завершено" },
  { v: "init", l: "Инициировано" }, { v: "new", l: "Не начато" }, { v: "deferred", l: "Отложено" },
];

const filteredEvents = computed(() => events.value.filter((e) => {
  if (fStatus.value && e.status !== fStatus.value) return false;
  if (fOverdue.value && evState(e) !== "overdue") return false;
  if (fWatched.value && !watchedSet.value.has(`${e.entity_type}:${e.entity_id}`)) return false;
  return true;
}));

const eventsByDay = computed(() => {
  const m: Record<string, CalendarEvent[]> = {};
  for (const e of filteredEvents.value) {
    if (!e.due_date) continue;
    (m[e.due_date.slice(0, 10)] ||= []).push(e);
  }
  return m;
});
const notesByDay = computed(() => {
  const m: Record<string, Note[]> = {};
  for (const n of notes.value) {
    const d = n.event_date || n.due_date;
    if (!d) continue;
    (m[d.slice(0, 10)] ||= []).push(n);
  }
  return m;
});

// ─── Месяц ───
const gridDays = computed(() => {
  const first = new Date(cur.value.getFullYear(), cur.value.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7;
  const start = new Date(first); start.setDate(first.getDate() - offset);
  const days = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    days.push({ date: d, key: ymd(d), inMonth: d.getMonth() === cur.value.getMonth(), isToday: ymd(d) === ymd(today) });
  }
  return days;
});

// ─── Неделя ───
const weekDays = computed(() => {
  const offset = (cur.value.getDay() + 6) % 7;
  const start = new Date(cur.value); start.setDate(cur.value.getDate() - offset);
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    days.push({ date: d, key: ymd(d), isToday: ymd(d) === ymd(today), wd: WD[i] });
  }
  return days;
});

// ─── Повестка (от сегодня вперёд) ───
const agendaGroups = computed(() => {
  const upcoming = filteredEvents.value
    .filter((e) => e.due_date && e.due_date.slice(0, 10) >= ymd(today))
    .sort((a, b) => (a.due_date! < b.due_date! ? -1 : 1));
  const groups: { key: string; date: Date; items: CalendarEvent[] }[] = [];
  const map: Record<string, CalendarEvent[]> = {};
  for (const e of upcoming) {
    const k = e.due_date!.slice(0, 10);
    if (!map[k]) { map[k] = []; groups.push({ key: k, date: new Date(k), items: map[k] }); }
    map[k].push(e);
  }
  return groups;
});

// ─── Заголовок + навигация ───
const titleText = computed(() => {
  if (view.value === "week") {
    const w = weekDays.value;
    const a = w[0].date, b = w[6].date;
    return `${a.getDate()} ${MONTHS[a.getMonth()].slice(0, 3).toLowerCase()} — ${b.getDate()} ${MONTHS[b.getMonth()].slice(0, 3).toLowerCase()} ${b.getFullYear()}`;
  }
  if (view.value === "agenda") return "Повестка";
  return `${MONTHS[cur.value.getMonth()]} ${cur.value.getFullYear()}`;
});
function go(delta: number) {
  dir.value = delta;
  const d = new Date(cur.value);
  if (view.value === "week") d.setDate(d.getDate() + delta * 7);
  else d.setMonth(d.getMonth() + delta);
  cur.value = d; selectedKey.value = null;
}
function goToday() { dir.value = 0; cur.value = new Date(today.getFullYear(), today.getMonth(), today.getDate()); selectedKey.value = ymd(today); }

const selectedEvents = computed(() => (selectedKey.value ? eventsByDay.value[selectedKey.value] || [] : []));
const selectedNotes = computed(() => (selectedKey.value ? notesByDay.value[selectedKey.value] || [] : []));
const selectedDate = computed(() => (selectedKey.value ? new Date(selectedKey.value) : null));
function pickDay(key: string) { selectedKey.value = selectedKey.value === key ? null : key; }
function openEvent(e: CalendarEvent) { emit("open-entity", { entity_type: e.entity_type, entity_id: e.entity_id, company_id: e.company_id }); }

// ─── Day-drawer: сводка дня + быстрое создание ───
const WEEKDAYS_FULL = ["воскресенье", "понедельник", "вторник", "среда", "четверг", "пятница", "суббота"];
const daySummary = computed(() => {
  const evs = selectedEvents.value;
  const s = { overdue: 0, soon: 0, future: 0, done: 0 };
  for (const e of evs) { const st = evState(e); (s as any)[st]++; }
  return s;
});
const selectedIsPast = computed(() => {
  if (!selectedKey.value) return false;
  return selectedKey.value < ymd(today);
});
const selectedWeekday = computed(() => (selectedDate.value ? WEEKDAYS_FULL[selectedDate.value.getDay()] : ""));
const pendingCreate = ref(false);
function createOnDay(kind: "task" | "project") {
  if (!selectedKey.value) return;
  pendingCreate.value = true;
  if (kind === "project") entityEditor.createProject({ due: selectedKey.value, companyId: props.companyId || null });
  else entityEditor.createTask({ due: selectedKey.value, companyId: props.companyId || null });
}
// После закрытия редактора создания — обновить календарь (подхватить новое событие).
watch(() => entityEditor.state.open, (open) => {
  if (!open && pendingCreate.value) { pendingCreate.value = false; load(); }
});

const monthTotal = computed(() => filteredEvents.value.filter((e) => e.due_date && e.due_date.slice(0, 7) === monKey(cur.value)).length);
const overdueTotal = computed(() => filteredEvents.value.filter((e) => evState(e) === "overdue").length);

function fmtFull(d: Date) { return `${d.getDate()} ${MONTHS[d.getMonth()].toLowerCase()} ${d.getFullYear()}`; }
function overdueDays(e: CalendarEvent): number {
  if (!e.due_date) return 0;
  const diff = Math.floor((today.getTime() - new Date(e.due_date).getTime()) / 86400000);
  return diff > 0 ? diff : 0;
}
</script>

<template>
  <div class="cal-root">
    <!-- Топбар -->
    <div class="cal-top">
      <div class="cal-nav">
        <button v-if="view !== 'agenda'" class="cal-arrow" @click="go(-1)" title="Назад">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
        </button>
        <div class="cal-month">{{ titleText }}</div>
        <button v-if="view !== 'agenda'" class="cal-arrow" @click="go(1)" title="Вперёд">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
        <button class="cal-today-btn" @click="goToday">Сегодня</button>
      </div>
      <div class="cal-controls">
        <!-- Виды -->
        <div class="cal-viewsw" :data-active="view">
          <span class="cal-viewsw-ind"></span>
          <button v-for="v in (['month','week','agenda'] as const)" :key="v"
                  class="cal-vbtn" :class="{ on: view === v }" @click="view = v">
            {{ v === 'month' ? 'Месяц' : v === 'week' ? 'Неделя' : 'Повестка' }}
          </button>
        </div>
        <!-- Фильтры -->
        <select v-model="fStatus" class="cal-fselect">
          <option :value="null">Все статусы</option>
          <option v-for="s in STATUS_OPTS" :key="s.v" :value="s.v">{{ s.l }}</option>
        </select>
        <button class="cal-fchip" :class="{ on: fOverdue }" @click="fOverdue = !fOverdue">Просроченные</button>
        <button class="cal-fchip" :class="{ on: fWatched }" @click="fWatched = !fWatched">Отслеживаемые</button>
      </div>
    </div>

    <div class="cal-legend-row">
      <span class="cal-stat"><b>{{ filteredEvents.length }}</b> событий</span>
      <span v-if="overdueTotal" class="cal-stat cal-stat-over"><b>{{ overdueTotal }}</b> просрочено</span>
      <span class="cal-legend">
        <span class="cal-lg"><i style="background:#E24B4A"></i>просрочено</span>
        <span class="cal-lg"><i style="background:#EF9F27"></i>скоро</span>
        <span class="cal-lg"><i style="background:#7F77DD"></i>впереди</span>
        <span class="cal-lg"><i style="background:#1D9E75"></i>готово</span>
      </span>
    </div>

    <!-- ═══ МЕСЯЦ ═══ -->
    <template v-if="view === 'month'">
      <div class="cal-wd">
        <div v-for="w in WD" :key="w" class="cal-wd-cell" :class="{ 'cal-wd-we': w === 'Сб' || w === 'Вс' }">{{ w }}</div>
      </div>
      <Transition :name="dir >= 0 ? 'cal-grid-next' : 'cal-grid-prev'" mode="out-in">
        <div class="cal-grid" :key="monKey(cur)">
          <div v-for="(d, i) in gridDays" :key="d.key" class="cal-day"
               :class="{ 'cal-out': !d.inMonth, 'cal-today': d.isToday, 'cal-sel': d.key === selectedKey, 'cal-has': (eventsByDay[d.key] || []).length }"
               :style="{ '--di': (i % 7) * 0.012 + Math.floor(i / 7) * 0.03 + 's' }" @click="pickDay(d.key)">
            <span v-if="(notesByDay[d.key] || []).length" class="cal-note-badge" :title="(notesByDay[d.key] || []).length + ' заметок'">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
              <span v-if="(notesByDay[d.key] || []).length > 1">{{ (notesByDay[d.key] || []).length }}</span>
            </span>
            <div class="cal-daynum"><span>{{ d.date.getDate() }}</span></div>
            <div class="cal-chips">
              <button v-for="(e, ci) in (eventsByDay[d.key] || []).slice(0, 3)" :key="e.entity_id"
                      class="cal-chip" :class="'cal-' + evState(e)" :style="{ '--ec': STATE_COLOR[evState(e)], '--ci': ci * 0.05 + 's' }"
                      :title="(e.num ? e.num + ' · ' : '') + e.title" @click.stop="openEvent(e)">
                <span class="cal-chip-dot"></span><span class="cal-chip-txt">{{ e.num ? e.num + ' ' : '' }}{{ e.title }}</span>
              </button>
              <div v-if="(eventsByDay[d.key] || []).length > 3" class="cal-more" @click.stop="pickDay(d.key)">+{{ (eventsByDay[d.key] || []).length - 3 }}</div>
            </div>
          </div>
        </div>
      </Transition>
    </template>

    <!-- ═══ НЕДЕЛЯ ═══ -->
    <template v-else-if="view === 'week'">
      <Transition :name="dir >= 0 ? 'cal-grid-next' : 'cal-grid-prev'" mode="out-in">
        <div class="cal-week" :key="weekDays[0].key">
          <div v-for="d in weekDays" :key="d.key" class="cal-wcol" :class="{ 'cal-today': d.isToday }">
            <div class="cal-wcol-h"><span class="cal-wcol-wd">{{ d.wd }}</span><span class="cal-wcol-num">{{ d.date.getDate() }}</span></div>
            <div class="cal-wcol-body">
              <button v-for="e in (eventsByDay[d.key] || [])" :key="e.entity_id" class="cal-wev" :style="{ '--ec': STATE_COLOR[evState(e)] }"
                      :title="e.title" @click="openEvent(e)">
                <span class="cal-wev-bar"></span>
                <span class="cal-wev-txt">{{ e.num ? e.num + ' ' : '' }}{{ e.title }}</span>
                <span v-if="isGlobal && e.company_name" class="cal-wev-co">{{ e.company_name }}</span>
              </button>
              <div v-if="!(eventsByDay[d.key] || []).length" class="cal-wempty">—</div>
            </div>
          </div>
        </div>
      </Transition>
    </template>

    <!-- ═══ ПОВЕСТКА ═══ -->
    <template v-else>
      <div class="cal-agenda">
        <div v-if="!agendaGroups.length" class="cal-ag-empty">Нет предстоящих дедлайнов</div>
        <div v-for="(g, gi) in agendaGroups" :key="g.key" class="cal-ag-group" :style="{ '--gi': gi }">
          <div class="cal-ag-date" :class="{ 'cal-ag-today': g.key === ymd(today) }">{{ fmtFull(g.date) }}<span v-if="g.key === ymd(today)" class="cal-ag-badge">сегодня</span></div>
          <button v-for="(e, ei) in g.items" :key="e.entity_id" class="cal-ag-item" :style="{ '--ec': STATE_COLOR[evState(e)], '--ai': ei }" @click="openEvent(e)">
            <span class="cal-ag-bar"></span>
            <div class="cal-ag-main">
              <div class="cal-ag-title"><span v-if="e.num" class="cal-ag-num">{{ e.num }}</span>{{ e.title }}</div>
              <div class="cal-ag-meta">{{ e.entity_type === 'project' ? 'Проект' : 'Задача' }}<template v-if="isGlobal && e.company_name"> · {{ e.company_name }}</template></div>
            </div>
            <span v-if="evState(e) === 'overdue'" class="cal-ag-over">просрочено {{ overdueDays(e) }} дн</span>
          </button>
        </div>
      </div>
    </template>

    <!-- Day-drawer (месяц/неделя): сводка дня + события + быстрое создание -->
    <Transition name="cal-panel">
      <div v-if="view !== 'agenda' && selectedKey" class="cal-sidepanel">
        <div class="cal-sp-head">
          <div class="cal-sp-head-l">
            <div class="cal-sp-date">{{ selectedDate?.getDate() }} {{ MONTHS[selectedDate!.getMonth()].toLowerCase() }}</div>
            <div class="cal-sp-wd">{{ selectedWeekday }}<template v-if="selectedKey === ymd(today)"> · сегодня</template></div>
          </div>
          <button class="cal-sp-x" @click="selectedKey = null" aria-label="Закрыть">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>
          </button>
        </div>

        <!-- Сводка по статусам -->
        <div v-if="selectedEvents.length" class="cal-sp-summary">
          <span v-if="daySummary.overdue" class="cal-sp-sum over"><b>{{ daySummary.overdue }}</b> просрочено</span>
          <span v-if="daySummary.soon" class="cal-sp-sum soon"><b>{{ daySummary.soon }}</b> скоро</span>
          <span v-if="daySummary.future" class="cal-sp-sum fut"><b>{{ daySummary.future }}</b> впереди</span>
          <span v-if="daySummary.done" class="cal-sp-sum done"><b>{{ daySummary.done }}</b> готово</span>
        </div>

        <div class="cal-sp-list">
          <template v-if="selectedEvents.length">
            <div class="cal-sp-gl">Дедлайны · {{ selectedEvents.length }}</div>
            <button v-for="e in selectedEvents" :key="e.entity_id" class="cal-sp-item" :style="{ '--ec': STATE_COLOR[evState(e)] }" @click="openEvent(e)">
              <span class="cal-sp-bar"></span>
              <div class="cal-sp-main">
                <div class="cal-sp-title"><span v-if="e.num" class="cal-sp-num">{{ e.num }}</span>{{ e.title }}</div>
                <div class="cal-sp-meta">
                  {{ e.entity_type === 'project' ? 'Проект' : 'Задача' }}<template v-if="isGlobal && e.company_name"> · {{ e.company_name }}</template>
                  <span v-if="evState(e) === 'overdue'" class="cal-sp-od">просрочено {{ overdueDays(e) }} дн</span>
                </div>
              </div>
              <svg class="cal-sp-go" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
          </template>
          <template v-if="selectedNotes.length">
            <div class="cal-sp-gl">Заметки · {{ selectedNotes.length }}</div>
            <div v-for="n in selectedNotes" :key="n.id" class="cal-sp-item cal-sp-note" style="--ec:#EF9F27">
              <span class="cal-sp-bar"></span>
              <div class="cal-sp-main">
                <div class="cal-sp-title">{{ n.title || (n.body || '').slice(0, 60) }}</div>
                <div v-if="n.title && n.body" class="cal-sp-meta">{{ n.body.slice(0, 80) }}</div>
              </div>
            </div>
          </template>
          <!-- Пустой день -->
          <div v-if="!selectedEvents.length && !selectedNotes.length" class="cal-sp-empty">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#C7CCD9" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
            <span>На этот день дедлайнов нет</span>
            <em v-if="selectedIsPast">прошедшая дата</em>
          </div>
        </div>

        <!-- Быстрое создание на этот день -->
        <div class="cal-sp-create">
          <button class="cal-sp-cbtn task" @click="createOnDay('task')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Задача
          </button>
          <button class="cal-sp-cbtn proj" @click="createOnDay('project')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            Проект
          </button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.cal-root { padding: 4px 2px 24px; position: relative; }
.cal-top { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 10px; flex-wrap: wrap; }
.cal-nav { display: flex; align-items: center; gap: 8px; }
.cal-arrow { width: 30px; height: 30px; border-radius: 9px; border: 1px solid rgba(15,23,60,.08); background: #fff; color: var(--t2, #475569); cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .14s, border-color .14s, transform .14s, color .14s; }
.cal-arrow:active { transform: scale(.92); }
.cal-arrow:hover { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.3); transform: translateY(-1px); }
.cal-month { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); min-width: 150px; text-align: center; letter-spacing: -.01em; }
.cal-today-btn { margin-left: 4px; font-size: 12px; font-weight: 500; color: var(--p-deep, #534AB7); background: rgba(127,119,221,.10); border: 1px solid rgba(127,119,221,.22); border-radius: 8px; padding: 6px 13px; cursor: pointer; transition: background .14s; }
.cal-today-btn:hover { background: rgba(127,119,221,.18); }
.cal-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.cal-viewsw { position: relative; display: inline-flex; background: rgba(15,23,60,.05); border-radius: 9px; padding: 2px; }
.cal-viewsw-ind { position: absolute; top: 2px; bottom: 2px; width: calc((100% - 4px) / 3); background: #fff; border-radius: 7px; box-shadow: 0 1px 3px rgba(15,23,60,.10); transition: transform .3s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); left: 2px; }
.cal-viewsw[data-active="month"] .cal-viewsw-ind { transform: translateX(0); }
.cal-viewsw[data-active="week"] .cal-viewsw-ind { transform: translateX(100%); }
.cal-viewsw[data-active="agenda"] .cal-viewsw-ind { transform: translateX(200%); }
.cal-vbtn { position: relative; z-index: 1; font-size: 12px; font-weight: 500; color: var(--t2, #475569); background: transparent; border: none; border-radius: 7px; padding: 5px 12px; cursor: pointer; transition: color .2s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.cal-vbtn.on { color: var(--p-deep, #534AB7); font-weight: 600; }
.cal-fselect { font-size: 12px; color: var(--t1, #1E2A4A); background: #fff; border: 1px solid rgba(15,23,60,.10); border-radius: 8px; padding: 6px 9px; cursor: pointer; font-family: inherit; }
.cal-fchip { font-size: 12px; font-weight: 500; color: var(--t2, #475569); background: #fff; border: 1px solid rgba(15,23,60,.10); border-radius: 999px; padding: 5px 12px; cursor: pointer; font-family: inherit; transition: all .14s; }
.cal-fchip.on { background: rgba(127,119,221,.10); border-color: rgba(127,119,221,.4); color: var(--p-deep, #534AB7); }
.cal-legend-row { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--t3, #94A3B8); flex-wrap: wrap; margin-bottom: 12px; }
.cal-stat b { color: var(--t1, #1E2A4A); font-weight: 600; }
.cal-stat-over b { color: #E24B4A; }
.cal-legend { display: flex; gap: 11px; }
.cal-lg { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; }
.cal-lg i { width: 8px; height: 8px; border-radius: 50%; }

.cal-wd { display: grid; grid-template-columns: repeat(7, 1fr); gap: 7px; margin-bottom: 7px; }
.cal-wd-cell { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); text-align: center; }
.cal-wd-we { color: rgba(226,75,74,.55); }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); grid-auto-rows: minmax(96px, 1fr); gap: 7px; }
.cal-day { position: relative; border-radius: 12px; padding: 6px 7px 7px; background: #fff; border: 1px solid rgba(15,23,60,.05); cursor: pointer; overflow: hidden; transition: box-shadow .16s, border-color .16s, transform .16s; animation: cal-day-in .35s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both; animation-delay: var(--di); }
@keyframes cal-day-in { from { opacity: 0; transform: translateY(8px) scale(.97); } to { opacity: 1; transform: none; } }
.cal-day:hover { box-shadow: 0 6px 18px rgba(15,23,60,.10); transform: translateY(-2px); border-color: rgba(127,119,221,.22); z-index: 2; }
.cal-out { background: rgba(15,23,60,.015); }
.cal-out .cal-daynum { color: var(--t3, #C7CCD9); }
.cal-today { border-color: rgba(127,119,221,.45); background: rgba(127,119,221,.04); }
.cal-sel { border-color: var(--p-deep, #534AB7); box-shadow: 0 0 0 1px var(--p-deep, #534AB7); }
.cal-note-badge { position: absolute; top: 6px; left: 7px; z-index: 2; display: inline-flex; align-items: center; gap: 2px; color: #B87600; background: rgba(239,159,39,.16); border-radius: 6px; padding: 1px 4px; font-size: 9px; font-weight: 700; }
.cal-daynum { display: flex; justify-content: flex-end; font-size: 12px; font-weight: 500; color: var(--t2, #475569); margin-bottom: 4px; }
.cal-today .cal-daynum span { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; border-radius: 50%; background: var(--p-deep, #534AB7); color: #fff; font-weight: 600; padding: 0 4px; }
.cal-chips { display: flex; flex-direction: column; gap: 3px; }
.cal-chip { display: flex; align-items: center; gap: 5px; width: 100%; text-align: left; background: color-mix(in srgb, var(--ec) 12%, transparent); border: none; border-left: 2.5px solid var(--ec); border-radius: 5px; padding: 2px 6px; cursor: pointer; font-family: inherit; animation: cal-chip-in .3s ease both; animation-delay: var(--ci); transition: background .12s, transform .12s; }
.cal-chip:hover { background: color-mix(in srgb, var(--ec) 22%, transparent); transform: translateX(1px); }
@keyframes cal-chip-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }
.cal-chip-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--ec); flex-shrink: 0; }
.cal-chip-txt { font-size: 10.5px; font-weight: 500; color: rgba(30,42,74,.78); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cal-overdue .cal-chip-txt { color: #B91C1C; }
.cal-more { font-size: 10px; font-weight: 600; color: var(--p-deep, #534AB7); padding: 1px 6px; cursor: pointer; }

/* Неделя */
.cal-week { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; }
.cal-wcol { background: #fff; border: 1px solid rgba(15,23,60,.06); border-radius: 12px; min-height: 320px; display: flex; flex-direction: column; overflow: hidden; }
.cal-wcol.cal-today { border-color: rgba(127,119,221,.45); }
.cal-wcol-h { display: flex; align-items: center; justify-content: space-between; padding: 9px 11px; border-bottom: 1px solid rgba(15,23,60,.06); }
.cal-wcol-wd { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.cal-wcol-num { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); }
.cal-today .cal-wcol-num { color: var(--p-deep, #534AB7); }
.cal-wcol-body { padding: 8px; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; flex: 1; }
.cal-wev { display: flex; flex-direction: column; gap: 2px; text-align: left; background: color-mix(in srgb, var(--ec) 10%, transparent); border: none; border-left: 3px solid var(--ec); border-radius: 7px; padding: 6px 9px; cursor: pointer; font-family: inherit; transition: background .12s, transform .12s; position: relative; }
.cal-wev:hover { background: color-mix(in srgb, var(--ec) 20%, transparent); transform: translateY(-1px); }
.cal-wev-txt { font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A); line-height: 1.3; }
.cal-wev-co { font-size: 10px; color: var(--t3, #94A3B8); }
.cal-wempty { font-size: 12px; color: var(--t3, #C7CCD9); text-align: center; padding: 14px 0; }

/* Повестка */
.cal-agenda { max-width: 720px; }
.cal-ag-empty { text-align: center; color: var(--t3, #94A3B8); padding: 40px; font-size: 13px; }
.cal-ag-group { margin-bottom: 16px; }
.cal-ag-date { font-size: 12px; font-weight: 600; color: var(--t2, #475569); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.cal-ag-today { color: var(--p-deep, #534AB7); }
.cal-ag-badge { font-size: 10px; font-weight: 600; background: rgba(127,119,221,.12); color: var(--p-deep, #534AB7); border-radius: 999px; padding: 1px 8px; }
.cal-ag-item { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; background: #fff; border: 1px solid rgba(15,23,60,.06); border-radius: 11px; padding: 11px 14px; cursor: pointer; font-family: inherit; margin-bottom: 6px; transition: box-shadow .16s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)), transform .16s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)), border-color .16s; animation: cal-ag-in .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) backwards; animation-delay: calc(var(--gi, 0) * 0.05s + var(--ai, 0) * 0.035s); }
.cal-ag-item:hover { box-shadow: 0 6px 18px rgba(15,23,60,.10); transform: translateY(-2px); border-color: rgba(127,119,221,.22); }
@keyframes cal-ag-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.cal-ag-bar { width: 3px; align-self: stretch; border-radius: 3px; background: var(--ec); }
.cal-ag-main { flex: 1; min-width: 0; }
.cal-ag-title { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); }
.cal-ag-num { font-size: 11px; color: var(--t3, #94A3B8); margin-right: 6px; }
.cal-ag-meta { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 2px; }
.cal-ag-over { font-size: 10.5px; font-weight: 600; color: #E24B4A; white-space: nowrap; }

/* Панель дня */
.cal-sidepanel { position: absolute; top: 92px; right: 0; width: 320px; max-height: 78%; background: #fff; border: 1px solid rgba(15,23,60,.08); border-radius: 16px; box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08); z-index: 5; display: flex; flex-direction: column; overflow: hidden; }
.cal-sp-head { display: flex; align-items: center; gap: 8px; padding: 13px 16px; border-bottom: 1px solid rgba(15,23,60,.06); }
.cal-sp-head-l { flex: 1; min-width: 0; }
.cal-sp-date { font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.cal-sp-wd { font-size: 11px; color: var(--t3, #94A3B8); margin-top: 1px; text-transform: capitalize; }
.cal-sp-x { width: 28px; height: 28px; border: none; background: transparent; color: var(--t3, #94A3B8); cursor: pointer; border-radius: 8px; display: flex; align-items: center; justify-content: center; transition: background .14s, color .14s; flex-shrink: 0; }
.cal-sp-x:hover { background: rgba(15,23,60,.06); color: var(--t1, #1E2A4A); }
.cal-sp-summary { display: flex; flex-wrap: wrap; gap: 6px; padding: 11px 16px 4px; }
.cal-sp-sum { font-size: 10.5px; font-weight: 500; padding: 3px 9px; border-radius: 999px; }
.cal-sp-sum b { font-weight: 700; }
.cal-sp-sum.over { color: #C0392B; background: rgba(226,75,74,.10); }
.cal-sp-sum.soon { color: #C77A0A; background: rgba(239,159,39,.12); }
.cal-sp-sum.fut { color: #534AB7; background: rgba(127,119,221,.10); }
.cal-sp-sum.done { color: #0F6E56; background: rgba(29,158,117,.10); }
.cal-sp-list { overflow-y: auto; padding: 8px; display: flex; flex-direction: column; gap: 5px; flex: 1; }
.cal-sp-gl { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); padding: 6px 4px 2px; }
.cal-sp-note { cursor: default; }
.cal-sp-item { display: flex; align-items: center; gap: 9px; background: var(--bg-soft, #FAFAFC); border: 1px solid rgba(15,23,60,.05); border-radius: 10px; padding: 9px 11px; cursor: pointer; font-family: inherit; text-align: left; transition: background .12s, transform .12s, box-shadow .12s; }
.cal-sp-item:hover { background: #fff; transform: translateY(-1px); box-shadow: 0 3px 10px rgba(15,23,60,.07); }
.cal-sp-bar { width: 3px; align-self: stretch; border-radius: 3px; background: var(--ec); flex-shrink: 0; }
.cal-sp-main { min-width: 0; flex: 1; }
.cal-sp-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cal-sp-num { font-size: 11px; color: var(--t3, #94A3B8); margin-right: 6px; }
.cal-sp-meta { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 2px; display: flex; align-items: center; gap: 7px; }
.cal-sp-od { color: #C0392B; font-weight: 600; }
.cal-sp-go { color: var(--t3, #C7CCD9); flex-shrink: 0; }
.cal-sp-item:hover .cal-sp-go { color: var(--p-deep, #534AB7); }
.cal-sp-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 32px 16px; color: var(--t3, #94A3B8); font-size: 12px; text-align: center; }
.cal-sp-empty em { font-size: 10.5px; color: var(--t4, #B0B6C3); font-style: normal; }
.cal-sp-create { display: flex; gap: 8px; padding: 11px 16px; border-top: 1px solid rgba(15,23,60,.06); }
.cal-sp-cbtn { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; font-size: 12px; font-weight: 500; font-family: inherit; border-radius: 9px; padding: 8px 10px; cursor: pointer; transition: transform .14s, box-shadow .14s, background .14s; }
.cal-sp-cbtn.task { color: #fff; background: linear-gradient(135deg, #534AB7, #7F77DD); border: none; box-shadow: 0 3px 12px rgba(83,74,183,.26); }
.cal-sp-cbtn.task:hover { transform: translateY(-1px); box-shadow: 0 6px 16px rgba(83,74,183,.34); }
.cal-sp-cbtn.proj { color: var(--p-deep, #534AB7); background: rgba(127,119,221,.10); border: 1px solid rgba(127,119,221,.28); }
.cal-sp-cbtn.proj:hover { background: rgba(127,119,221,.18); transform: translateY(-1px); }

.cal-grid-next-enter-active, .cal-grid-prev-enter-active, .cal-grid-next-leave-active, .cal-grid-prev-leave-active { transition: opacity .22s, transform .26s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.cal-grid-next-enter-from { opacity: 0; transform: translateX(24px); }
.cal-grid-next-leave-to { opacity: 0; transform: translateX(-24px); }
.cal-grid-prev-enter-from { opacity: 0; transform: translateX(-24px); }
.cal-grid-prev-leave-to { opacity: 0; transform: translateX(24px); }
.cal-panel-enter-active { transition: opacity .25s, transform .3s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.cal-panel-leave-active { transition: opacity .18s, transform .2s; }
.cal-panel-enter-from, .cal-panel-leave-to { opacity: 0; transform: translateX(16px) scale(.97); }

@media (max-width: 760px) {
  .cal-grid { grid-auto-rows: minmax(72px, 1fr); gap: 4px; }
  .cal-chip-txt { display: none; }
  .cal-chip { justify-content: center; padding: 3px; }
  .cal-week { grid-template-columns: 1fr; }
  .cal-sidepanel { position: fixed; left: 8px; right: 8px; top: auto; bottom: 8px; width: auto; max-height: 55%; }
  .cal-legend { display: none; }
}
</style>
