<script setup lang="ts">
/**
 * NotesCalendar.vue — Month-view calendar with UZ holidays + notes badges.
 *
 * Embedded into CompanyNotesTab. Used to:
 *   - browse notes by date (click a day → emit "select" with ISO date)
 *   - see which days have notes (count badge per day)
 *   - see UZ public/religious/transferred holidays at a glance (colored dot)
 *   - quick-create a new note for any day (click action → emit "create")
 *
 * Holidays data comes from @/api/holidays (UZ_HOLIDAYS 2025-2027).
 */
import { ref, computed } from "vue";
import type { Note } from "@/api/notes";
import {
  getHoliday,
  toIsoDate,
  HOLIDAY_KIND_COLORS,
  type UzHoliday,
} from "@/api/holidays";

const props = defineProps<{
  notes: Note[];
  selectedDate?: string | null;
}>();

const emit = defineEmits<{
  (e: "select", iso: string): void;
  (e: "create", iso: string): void;
  (e: "clear"): void;
}>();

// =====================================================================
// State
// =====================================================================
const todayIso = toIsoDate(new Date());
const cursor = ref<Date>(new Date());

function shiftMonth(delta: number): void {
  const d = new Date(cursor.value);
  d.setDate(1);
  d.setMonth(d.getMonth() + delta);
  cursor.value = d;
}
function jumpToday(): void {
  cursor.value = new Date();
}

// =====================================================================
// Build 6×7 grid (Monday-first)
// =====================================================================
interface CellInfo {
  iso: string;
  date: Date;
  day: number;
  inMonth: boolean;
  isToday: boolean;
  isWeekend: boolean;
  holiday: UzHoliday | null;
  noteCount: number;
  notesByKind: Record<string, number>;
}

const grid = computed<CellInfo[]>(() => {
  const first = new Date(cursor.value.getFullYear(), cursor.value.getMonth(), 1);
  // Monday-first: getDay()==0=Sun → shift to 6, otherwise day-1
  const startOffset = (first.getDay() + 6) % 7;
  const startDate = new Date(first);
  startDate.setDate(first.getDate() - startOffset);

  // Index notes by date for O(1) lookup
  const noteIndex = new Map<string, { count: number; byKind: Record<string, number> }>();
  for (const n of props.notes) {
    const iso = (n.event_date || n.due_date || n.created_at).slice(0, 10);
    if (!iso) continue;
    let entry = noteIndex.get(iso);
    if (!entry) {
      entry = { count: 0, byKind: {} };
      noteIndex.set(iso, entry);
    }
    entry.count++;
    entry.byKind[n.kind] = (entry.byKind[n.kind] || 0) + 1;
  }

  const cells: CellInfo[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(startDate);
    d.setDate(startDate.getDate() + i);
    const iso = toIsoDate(d);
    const dow = d.getDay();
    const entry = noteIndex.get(iso);
    cells.push({
      iso,
      date: d,
      day: d.getDate(),
      inMonth: d.getMonth() === cursor.value.getMonth(),
      isToday: iso === todayIso,
      isWeekend: dow === 0 || dow === 6,
      holiday: getHoliday(d),
      noteCount: entry ? entry.count : 0,
      notesByKind: entry ? entry.byKind : {},
    });
  }
  return cells;
});

const monthLabel = computed(() => {
  const fmt = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" });
  return fmt.format(cursor.value);
});

const holidaysThisMonth = computed<UzHoliday[]>(() => {
  return grid.value
    .filter((c) => c.inMonth && c.holiday)
    .map((c) => c.holiday!)
    .filter((h, idx, arr) => arr.findIndex((x) => x.date === h.date) === idx);
});

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function pickCell(c: CellInfo) {
  if (props.selectedDate === c.iso) {
    emit("clear");
  } else {
    emit("select", c.iso);
  }
}
</script>

<template>
  <div class="nc-root">
    <div class="nc-hd">
      <button class="nc-nav-btn" @click="shiftMonth(-1)" title="Предыдущий месяц">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="10 4 6 8 10 12"/>
        </svg>
      </button>
      <div class="nc-month">{{ monthLabel }}</div>
      <button class="nc-nav-btn" @click="shiftMonth(1)" title="Следующий месяц">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 4 10 8 6 12"/>
        </svg>
      </button>
      <button class="nc-today-btn" @click="jumpToday" title="К сегодняшнему дню">
        Сегодня
      </button>
      <button
        v-if="selectedDate"
        class="nc-clear-btn"
        @click="emit('clear')"
        title="Сбросить выбор"
      >× Сброс</button>
    </div>

    <!-- Weekday header row -->
    <div class="nc-wk-row">
      <div
        v-for="(w, i) in WEEKDAYS"
        :key="w"
        class="nc-wk"
        :class="{ 'nc-wk-weekend': i >= 5 }"
      >{{ w }}</div>
    </div>

    <!-- 6×7 day grid -->
    <div class="nc-grid">
      <div
        v-for="c in grid"
        :key="c.iso"
        class="nc-cell"
        :class="{
          'nc-cell-out': !c.inMonth,
          'nc-cell-today': c.isToday,
          'nc-cell-weekend': c.isWeekend,
          'nc-cell-selected': selectedDate === c.iso,
          'nc-cell-dayoff': c.holiday && c.holiday.is_dayoff,
          'nc-cell-has-notes': c.noteCount > 0,
        }"
        :title="
          (c.holiday ? c.holiday.title_ru + (c.holiday.is_dayoff ? ' · нерабочий' : '') : '') +
          (c.noteCount > 0 ? (c.holiday ? '\n' : '') + c.noteCount + ' ' + (c.noteCount === 1 ? 'запись' : c.noteCount < 5 ? 'записи' : 'записей') : '')
        "
        @click="pickCell(c)"
      >
        <div class="nc-cell-head">
          <span class="nc-cell-day">{{ c.day }}</span>
          <span v-if="c.noteCount > 0" class="nc-cell-count">{{ c.noteCount }}</span>
        </div>
        <div
          v-if="c.holiday"
          class="nc-cell-holiday"
          :style="{ background: HOLIDAY_KIND_COLORS[c.holiday.kind] }"
        ></div>
        <button
          v-if="c.inMonth"
          class="nc-cell-add"
          @click.stop="emit('create', c.iso)"
          title="Создать запись на этот день"
        >+</button>
      </div>
    </div>

    <!-- Holidays legend for current month -->
    <div v-if="holidaysThisMonth.length > 0" class="nc-legend">
      <div
        v-for="h in holidaysThisMonth"
        :key="h.date"
        class="nc-legend-item"
        :style="{ '--h-color': HOLIDAY_KIND_COLORS[h.kind] }"
      >
        <span class="nc-legend-dot"></span>
        <span class="nc-legend-d">{{ Number(h.date.slice(8, 10)) }}</span>
        <span class="nc-legend-t">{{ h.title_ru }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nc-root {
  background: white;
  border: 1px solid rgba(30, 42, 74, 0.08);
  border-radius: 12px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.04);
}

/* Header */
.nc-hd {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nc-nav-btn,
.nc-today-btn,
.nc-clear-btn {
  background: transparent;
  border: 1px solid rgba(30, 42, 74, 0.10);
  border-radius: 7px;
  width: 26px;
  height: 26px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: rgba(30, 42, 74, 0.65);
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.nc-today-btn {
  width: auto;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 500;
}
.nc-clear-btn {
  width: auto;
  padding: 0 10px;
  font-size: 11px;
  font-weight: 500;
  color: var(--sev-high);
  border-color: rgba(226, 75, 74, 0.30);
  margin-left: auto;
}
.nc-nav-btn:hover,
.nc-today-btn:hover {
  background: rgba(127, 119, 221, 0.08);
  border-color: rgba(127, 119, 221, 0.30);
  color: var(--p-deep);
}
.nc-clear-btn:hover {
  background: rgba(226, 75, 74, 0.10);
}
.nc-month {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  letter-spacing: -0.01em;
  text-transform: capitalize;
  text-align: center;
}

/* Weekday header */
.nc-wk-row {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.nc-wk {
  text-align: center;
  font-size: 10px;
  font-weight: 700;
  color: rgba(30, 42, 74, 0.45);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 4px 0;
}
.nc-wk-weekend {
  color: rgba(226, 75, 74, 0.50);
}

/* Day grid */
.nc-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 4px;
}
.nc-cell {
  position: relative;
  min-height: 44px;
  border-radius: 7px;
  border: 0.5px solid rgba(30, 42, 74, 0.05);
  background: rgba(248, 250, 252, 0.40);
  padding: 4px 6px;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s, transform 0.12s;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.nc-cell:hover {
  background: rgba(127, 119, 221, 0.07);
  border-color: rgba(127, 119, 221, 0.25);
  transform: translateY(-1px);
}
.nc-cell:hover .nc-cell-add {
  opacity: 1;
}
.nc-cell-out {
  background: transparent;
  border-color: transparent;
}
.nc-cell-out .nc-cell-day {
  color: rgba(30, 42, 74, 0.25);
}
.nc-cell-today {
  background: rgba(127, 119, 221, 0.10);
  border-color: rgba(127, 119, 221, 0.45);
}
.nc-cell-today .nc-cell-day {
  color: var(--p-deep);
  font-weight: 700;
}
.nc-cell-weekend:not(.nc-cell-out) .nc-cell-day {
  color: rgba(226, 75, 74, 0.80);
}
.nc-cell-dayoff:not(.nc-cell-out) {
  background: rgba(226, 75, 74, 0.06);
}
.nc-cell-dayoff:not(.nc-cell-out) .nc-cell-day {
  color: var(--sev-high);
  font-weight: 700;
}
.nc-cell-has-notes:not(.nc-cell-out) {
  border-color: rgba(127, 119, 221, 0.35);
}
.nc-cell-selected {
  background: rgba(127, 119, 221, 0.20) !important;
  border-color: #7F77DD !important;
  box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.20);
}

.nc-cell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.nc-cell-day {
  font-size: 12px;
  font-weight: 500;
  color: rgba(30, 42, 74, 0.85);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}
.nc-cell-count {
  font-size: 9.5px;
  font-weight: 700;
  color: var(--p-deep);
  background: rgba(127, 119, 221, 0.18);
  padding: 1px 5px;
  border-radius: 8px;
  font-variant-numeric: tabular-nums;
  line-height: 1.3;
}
.nc-cell-holiday {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-top: auto;
  align-self: flex-start;
}
.nc-cell-add {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: none;
  background: rgba(127, 119, 221, 0.18);
  color: var(--p-deep);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  font-weight: 700;
  opacity: 0;
  transition: opacity 0.12s, background 0.12s;
  display: flex;
  align-items: center;
  justify-content: center;
}
.nc-cell-add:hover {
  background: #7F77DD;
  color: white;
}

/* Legend */
.nc-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding-top: 8px;
  border-top: 0.5px solid rgba(30, 42, 74, 0.08);
}
.nc-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: rgba(30, 42, 74, 0.80);
  --h-color: #888;
}
.nc-legend-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--h-color);
  flex-shrink: 0;
}
.nc-legend-d {
  font-size: 10.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgba(30, 42, 74, 0.55);
  min-width: 14px;
  text-align: right;
}
.nc-legend-t {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.80);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 160px;
}
</style>
