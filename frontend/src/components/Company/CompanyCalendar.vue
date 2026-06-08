<script setup lang="ts">
/**
 * CompanyCalendar — премиальный месячный календарь дедлайнов компании.
 * Авто-агрегация: события тянутся из бэкенда (project/task.due_date), скоуп
 * по компании. Клик по событию → emit open-entity (workspace откроет редактор).
 */
import { ref, computed, onMounted, watch } from "vue";
import { calendarApi, type CalendarEvent } from "@/api/calendar";
import { notesApi, type Note } from "@/api/notes";

const props = defineProps<{ companyId?: string | null }>();
const emit = defineEmits<{ (e: "open-entity", payload: { entity_type: "project" | "task"; entity_id: string; company_id: string | null }): void }>();
const isGlobal = computed(() => !props.companyId);

const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];
const WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

const today = new Date();
const cur = ref(new Date(today.getFullYear(), today.getMonth(), 1));
const events = ref<CalendarEvent[]>([]);
const notes = ref<Note[]>([]);
const loading = ref(false);
const selectedKey = ref<string | null>(null);
const dir = ref(0); // направление анимации перелистывания

function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

// 6 недель × 7 дней, начиная с понедельника
const gridDays = computed(() => {
  const first = new Date(cur.value.getFullYear(), cur.value.getMonth(), 1);
  const offset = (first.getDay() + 6) % 7; // Пн=0
  const start = new Date(first);
  start.setDate(first.getDate() - offset);
  const days: { date: Date; key: string; inMonth: boolean; isToday: boolean }[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setDate(start.getDate() + i);
    days.push({
      date: d, key: ymd(d),
      inMonth: d.getMonth() === cur.value.getMonth(),
      isToday: ymd(d) === ymd(today),
    });
  }
  return days;
});

const eventsByDay = computed(() => {
  const m: Record<string, CalendarEvent[]> = {};
  for (const e of events.value) {
    if (!e.due_date) continue;
    const k = e.due_date.slice(0, 10);
    (m[k] ||= []).push(e);
  }
  return m;
});

async function load() {
  loading.value = true;
  // диапазон видимой сетки (с захватом соседних месяцев)
  const from = gridDays.value[0].key;
  const to = gridDays.value[41].key;
  try {
    const [ev, nt] = await Promise.all([
      calendarApi.events(from, to, props.companyId || undefined),
      props.companyId
        ? notesApi.list({ company_id: props.companyId, limit: 500 }).then((r) => r.items || []).catch(() => [])
        : Promise.resolve([] as Note[]),
    ]);
    events.value = ev;
    notes.value = nt;
  } catch { events.value = []; notes.value = []; } finally { loading.value = false; }
}

const notesByDay = computed(() => {
  const m: Record<string, Note[]> = {};
  for (const n of notes.value) {
    const d = n.event_date || n.due_date;
    if (!d) continue;
    const k = d.slice(0, 10);
    (m[k] ||= []).push(n);
  }
  return m;
});
onMounted(load);
watch(cur, load);
watch(() => props.companyId, load);

function go(delta: number) {
  dir.value = delta;
  cur.value = new Date(cur.value.getFullYear(), cur.value.getMonth() + delta, 1);
  selectedKey.value = null;
}
function goToday() {
  dir.value = today < cur.value ? -1 : 1;
  cur.value = new Date(today.getFullYear(), today.getMonth(), 1);
  selectedKey.value = ymd(today);
}

// Цвет события по состоянию дедлайна
function evState(e: CalendarEvent): "overdue" | "soon" | "done" | "future" {
  if (e.status === "done") return "done";
  if (!e.due_date) return "future";
  const due = new Date(e.due_date);
  const diff = Math.floor((due.getTime() - today.getTime()) / 86400000);
  if (diff < 0) return "overdue";
  if (diff <= 3) return "soon";
  return "future";
}
const STATE_COLOR: Record<string, string> = {
  overdue: "#E24B4A", soon: "#EF9F27", future: "#7F77DD", done: "#1D9E75",
};

const selectedEvents = computed(() => (selectedKey.value ? eventsByDay.value[selectedKey.value] || [] : []));
const selectedNotes = computed(() => (selectedKey.value ? notesByDay.value[selectedKey.value] || [] : []));
const selectedDate = computed(() => (selectedKey.value ? new Date(selectedKey.value) : null));

function pickDay(key: string) { selectedKey.value = selectedKey.value === key ? null : key; }
function openEvent(e: CalendarEvent) { emit("open-entity", { entity_type: e.entity_type, entity_id: e.entity_id, company_id: e.company_id }); }

const monthTotal = computed(() => events.value.filter((e) => e.due_date && e.due_date.slice(0, 7) === ymd(cur.value).slice(0, 7)).length);
const overdueTotal = computed(() => events.value.filter((e) => evState(e) === "overdue" && e.due_date && e.due_date.slice(0, 7) === ymd(cur.value).slice(0, 7)).length);
</script>

<template>
  <div class="cal-root">
    <!-- Топбар -->
    <div class="cal-top">
      <div class="cal-nav">
        <button class="cal-arrow" @click="go(-1)" aria-label="Предыдущий месяц">‹</button>
        <Transition :name="dir >= 0 ? 'cal-title-next' : 'cal-title-prev'" mode="out-in">
          <div class="cal-month" :key="ymd(cur).slice(0,7)">
            {{ MONTHS[cur.getMonth()] }} <span class="cal-year">{{ cur.getFullYear() }}</span>
          </div>
        </Transition>
        <button class="cal-arrow" @click="go(1)" aria-label="Следующий месяц">›</button>
        <button class="cal-today-btn" @click="goToday">Сегодня</button>
      </div>
      <div class="cal-stats">
        <span class="cal-stat"><b>{{ monthTotal }}</b> дедлайнов</span>
        <span v-if="overdueTotal" class="cal-stat cal-stat-over"><b>{{ overdueTotal }}</b> просрочено</span>
        <span class="cal-legend">
          <span class="cal-lg"><i style="background:#E24B4A"></i>просрочено</span>
          <span class="cal-lg"><i style="background:#EF9F27"></i>скоро</span>
          <span class="cal-lg"><i style="background:#7F77DD"></i>впереди</span>
          <span class="cal-lg"><i style="background:#1D9E75"></i>готово</span>
        </span>
      </div>
    </div>

    <!-- Дни недели -->
    <div class="cal-wd">
      <div v-for="w in WD" :key="w" class="cal-wd-cell" :class="{ 'cal-wd-we': w === 'Сб' || w === 'Вс' }">{{ w }}</div>
    </div>

    <!-- Сетка месяца -->
    <Transition :name="dir >= 0 ? 'cal-grid-next' : 'cal-grid-prev'" mode="out-in">
      <div class="cal-grid" :key="ymd(cur).slice(0,7)">
        <div
          v-for="(d, i) in gridDays"
          :key="d.key"
          class="cal-day"
          :class="{ 'cal-out': !d.inMonth, 'cal-today': d.isToday, 'cal-sel': d.key === selectedKey, 'cal-has': (eventsByDay[d.key] || []).length }"
          :style="{ '--di': (i % 7) * 0.012 + Math.floor(i / 7) * 0.03 + 's' }"
          @click="pickDay(d.key)"
        >
          <span v-if="(notesByDay[d.key] || []).length" class="cal-note-badge" :title="(notesByDay[d.key] || []).length + ' заметок'">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
            <span v-if="(notesByDay[d.key] || []).length > 1">{{ (notesByDay[d.key] || []).length }}</span>
          </span>
          <div class="cal-daynum"><span>{{ d.date.getDate() }}</span></div>
          <div class="cal-chips">
            <button
              v-for="(e, ci) in (eventsByDay[d.key] || []).slice(0, 3)"
              :key="e.entity_id"
              class="cal-chip"
              :class="'cal-' + evState(e)"
              :style="{ '--ec': STATE_COLOR[evState(e)], '--ci': ci * 0.05 + 's' }"
              :title="(e.num ? e.num + ' · ' : '') + e.title"
              @click.stop="openEvent(e)"
            >
              <span class="cal-chip-dot"></span>
              <span class="cal-chip-txt">{{ e.num ? e.num + ' ' : '' }}{{ e.title }}</span>
            </button>
            <div v-if="(eventsByDay[d.key] || []).length > 3" class="cal-more" @click.stop="pickDay(d.key)">
              +{{ (eventsByDay[d.key] || []).length - 3 }}
            </div>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Панель выбранного дня -->
    <Transition name="cal-panel">
      <div v-if="selectedKey && (selectedEvents.length || selectedNotes.length)" class="cal-sidepanel">
        <div class="cal-sp-head">
          <span class="cal-sp-date">{{ selectedDate?.getDate() }} {{ MONTHS[selectedDate!.getMonth()].toLowerCase() }} {{ selectedDate?.getFullYear() }}</span>
          <span class="cal-sp-n">{{ selectedEvents.length + selectedNotes.length }}</span>
          <button class="cal-sp-x" @click="selectedKey = null">×</button>
        </div>
        <div class="cal-sp-list">
          <div v-if="selectedEvents.length" class="cal-sp-gl">Дедлайны</div>
          <button v-for="e in selectedEvents" :key="e.entity_id" class="cal-sp-item" :style="{ '--ec': STATE_COLOR[evState(e)] }" @click="openEvent(e)">
            <span class="cal-sp-bar"></span>
            <div class="cal-sp-main">
              <div class="cal-sp-title"><span v-if="e.num" class="cal-sp-num">{{ e.num }}</span>{{ e.title }}</div>
              <div class="cal-sp-meta">{{ e.entity_type === 'project' ? 'Проект' : 'Задача' }}<template v-if="isGlobal && e.company_name"> · {{ e.company_name }}</template></div>
            </div>
          </button>
          <div v-if="selectedNotes.length" class="cal-sp-gl">Заметки</div>
          <div v-for="n in selectedNotes" :key="n.id" class="cal-sp-item cal-sp-note" style="--ec:#EF9F27">
            <span class="cal-sp-bar"></span>
            <div class="cal-sp-main">
              <div class="cal-sp-title">{{ n.title || (n.body || '').slice(0, 60) }}</div>
              <div v-if="n.title && n.body" class="cal-sp-meta">{{ n.body.slice(0, 80) }}</div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.cal-root { padding: 4px 2px 24px; position: relative; }

/* Топбар */
.cal-top { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
.cal-nav { display: flex; align-items: center; gap: 8px; }
.cal-arrow {
  width: 30px; height: 30px; border-radius: 9px; border: 1px solid rgba(15,23,60,.08);
  background: #fff; color: var(--t1, #1E2A4A); font-size: 18px; line-height: 1; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .14s, border-color .14s, transform .14s;
}
.cal-arrow:hover { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.3); transform: translateY(-1px); }
.cal-month { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); min-width: 168px; text-align: center; letter-spacing: -.01em; }
.cal-year { color: var(--t3, #94A3B8); font-weight: 400; }
.cal-today-btn {
  margin-left: 4px; font-size: 12px; font-weight: 500; color: var(--p-deep, #534AB7);
  background: rgba(127,119,221,.10); border: 1px solid rgba(127,119,221,.22);
  border-radius: 8px; padding: 6px 13px; cursor: pointer; transition: background .14s;
}
.cal-today-btn:hover { background: rgba(127,119,221,.18); }
.cal-stats { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--t3, #94A3B8); flex-wrap: wrap; }
.cal-stat b { color: var(--t1, #1E2A4A); font-weight: 600; }
.cal-stat-over b { color: #E24B4A; }
.cal-legend { display: flex; gap: 11px; }
.cal-lg { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; }
.cal-lg i { width: 8px; height: 8px; border-radius: 50%; }

/* Дни недели */
.cal-wd { display: grid; grid-template-columns: repeat(7, 1fr); gap: 7px; margin-bottom: 7px; }
.cal-wd-cell { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); text-align: center; }
.cal-wd-we { color: rgba(226,75,74,.55); }

/* Сетка */
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); grid-auto-rows: minmax(96px, 1fr); gap: 7px; }
.cal-day {
  position: relative; border-radius: 12px; padding: 6px 7px 7px;
  background: #fff; border: 1px solid rgba(15,23,60,.05);
  cursor: pointer; overflow: hidden;
  transition: box-shadow .16s, border-color .16s, transform .16s, background .16s;
  animation: cal-day-in .35s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--di);
}
@keyframes cal-day-in { from { opacity: 0; transform: translateY(8px) scale(.97); } to { opacity: 1; transform: none; } }
.cal-day:hover { box-shadow: 0 6px 18px rgba(15,23,60,.10); transform: translateY(-2px); border-color: rgba(127,119,221,.22); z-index: 2; }
.cal-out { background: rgba(15,23,60,.015); }
.cal-out .cal-daynum { color: var(--t3, #C7CCD9); }
.cal-today { border-color: rgba(127,119,221,.45); background: rgba(127,119,221,.04); }
.cal-sel { border-color: var(--p-deep, #534AB7); box-shadow: 0 0 0 1px var(--p-deep, #534AB7); }
.cal-note-badge {
  position: absolute; top: 6px; left: 7px; z-index: 2;
  display: inline-flex; align-items: center; gap: 2px;
  color: #B87600; background: rgba(239,159,39,.16); border-radius: 6px; padding: 1px 4px;
  font-size: 9px; font-weight: 700;
}
.cal-daynum { display: flex; justify-content: flex-end; font-size: 12px; font-weight: 500; color: var(--t2, #475569); margin-bottom: 4px; }
.cal-today .cal-daynum span {
  display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px;
  border-radius: 50%; background: var(--p-deep, #534AB7); color: #fff; font-weight: 600; padding: 0 4px;
}
.cal-chips { display: flex; flex-direction: column; gap: 3px; }
.cal-chip {
  display: flex; align-items: center; gap: 5px; width: 100%; text-align: left;
  background: color-mix(in srgb, var(--ec) 12%, transparent);
  border: none; border-left: 2.5px solid var(--ec); border-radius: 5px;
  padding: 2px 6px; cursor: pointer; font-family: inherit;
  animation: cal-chip-in .3s ease both; animation-delay: var(--ci);
  transition: background .12s, transform .12s;
}
.cal-chip:hover { background: color-mix(in srgb, var(--ec) 22%, transparent); transform: translateX(1px); }
@keyframes cal-chip-in { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }
.cal-chip-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--ec); flex-shrink: 0; }
.cal-chip-txt { font-size: 10.5px; font-weight: 500; color: rgba(30,42,74,.78); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cal-overdue .cal-chip-txt { color: #B91C1C; }
.cal-more { font-size: 10px; font-weight: 600; color: var(--p-deep, #534AB7); padding: 1px 6px; cursor: pointer; }

/* Панель дня */
.cal-sidepanel {
  position: absolute; top: 54px; right: 0; width: 290px; max-height: 70%;
  background: #fff; border: 1px solid rgba(15,23,60,.08); border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  z-index: 5; display: flex; flex-direction: column; overflow: hidden;
}
.cal-sp-head { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid rgba(15,23,60,.06); }
.cal-sp-date { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); flex: 1; }
.cal-sp-n { font-size: 11px; font-weight: 600; color: var(--p-deep, #534AB7); background: rgba(127,119,221,.12); border-radius: 999px; padding: 1px 8px; }
.cal-sp-x { width: 22px; height: 22px; border: none; background: transparent; color: var(--t3, #94A3B8); font-size: 17px; cursor: pointer; border-radius: 6px; }
.cal-sp-x:hover { background: rgba(15,23,60,.06); }
.cal-sp-list { overflow-y: auto; padding: 7px; display: flex; flex-direction: column; gap: 5px; }
.cal-sp-item { display: flex; align-items: stretch; gap: 9px; background: var(--bg-soft, #FAFAFC); border: 1px solid rgba(15,23,60,.05); border-radius: 9px; padding: 8px 10px; cursor: pointer; font-family: inherit; text-align: left; transition: background .12s, transform .12s; }
.cal-sp-item:hover { background: #fff; transform: translateY(-1px); box-shadow: 0 3px 10px rgba(15,23,60,.07); }
.cal-sp-gl { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); padding: 4px 4px 1px; }
.cal-sp-note { cursor: default; }
.cal-sp-bar { width: 3px; border-radius: 3px; background: var(--ec); flex-shrink: 0; }
.cal-sp-main { min-width: 0; }
.cal-sp-title { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); }
.cal-sp-num { font-size: 11px; color: var(--t3, #94A3B8); margin-right: 6px; }
.cal-sp-meta { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 2px; }

/* Переходы перелистывания */
.cal-grid-next-enter-active, .cal-grid-prev-enter-active, .cal-grid-next-leave-active, .cal-grid-prev-leave-active { transition: opacity .22s, transform .26s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.cal-grid-next-enter-from { opacity: 0; transform: translateX(24px); }
.cal-grid-next-leave-to { opacity: 0; transform: translateX(-24px); }
.cal-grid-prev-enter-from { opacity: 0; transform: translateX(-24px); }
.cal-grid-prev-leave-to { opacity: 0; transform: translateX(24px); }
.cal-title-next-enter-active, .cal-title-prev-enter-active, .cal-title-next-leave-active, .cal-title-prev-leave-active { transition: opacity .2s, transform .2s; }
.cal-title-next-enter-from { opacity: 0; transform: translateY(8px); }
.cal-title-next-leave-to { opacity: 0; transform: translateY(-8px); }
.cal-title-prev-enter-from { opacity: 0; transform: translateY(-8px); }
.cal-title-prev-leave-to { opacity: 0; transform: translateY(8px); }
.cal-panel-enter-active { transition: opacity .25s, transform .3s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)); }
.cal-panel-leave-active { transition: opacity .18s, transform .2s; }
.cal-panel-enter-from, .cal-panel-leave-to { opacity: 0; transform: translateX(16px) scale(.97); }

@media (max-width: 760px) {
  .cal-grid { grid-auto-rows: minmax(72px, 1fr); gap: 4px; }
  .cal-chip-txt { display: none; }
  .cal-chip { justify-content: center; padding: 3px; }
  .cal-sidepanel { position: fixed; left: 8px; right: 8px; top: auto; bottom: 8px; width: auto; max-height: 55%; }
  .cal-legend { display: none; }
}
</style>
