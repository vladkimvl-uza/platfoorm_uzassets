<script setup lang="ts">
/**
 * KanbanCard.vue — compact flat card with status-stripe.
 *
 * Refactor 2026-05-26: A + C + D from rework menu.
 *   • Flat surface (white + 1px border) — removes glassmorphism.
 *   • Status-as-stripe (3px left color-bar).
 *   • Compact 2-row layout (~62-80px height).
 *   • Quarterly progress as inline 4 dots ● ● ○ ○ + "Кв N/4" pill.
 *   • Monthly/Ongoing get visible status pills ("Ежемесячная" / "Постоянная").
 *   • Overdue = red stripe + tinted bg over the whole card.
 *
 * Drag-and-drop: emits @dragstart when `draggable` prop is true (default).
 * Parent handles the actual drop logic.
 */
import { computed } from "vue";
import type { TaskBrief } from "@/api/tasks";
import { useFormatters } from "@/composables/useFormatters";

const props = withDefaults(defineProps<{
  task: TaskBrief;
  overdue: boolean;
  draggable?: boolean;
}>(), {
  draggable: true,
});
const emit = defineEmits<{
  (e: "click"): void;
  (e: "dragstart", task: TaskBrief, ev: DragEvent): void;
}>();

const fmt = useFormatters();

// ── Direction metadata (1:1 legacy const DIRS) ──────────────────────
const DIRS: Record<string, { label: string; short: string; color: string }> = {
  strategy:    { label: "Стратегическое управление",  short: "STRG",  color: "#1e2787" },
  finance:     { label: "Финансы / риски / аудит",    short: "FIN",   color: "#D97706" },
  procurement: { label: "Система закупок",            short: "PROC",  color: "#3B6D11" },
  orgdev:      { label: "Организационное развитие",   short: "ORG",   color: "#534AB7" },
  digital:     { label: "Цифровизация",               short: "DIG",   color: "#1D9E75" },
  operations:  { label: "Операционная эффективность", short: "OPS",   color: "#EF4444" },
  governance:  { label: "Корпоративное управление",   short: "GOV",   color: "#72243E" },
  esg:         { label: "ESG",                        short: "ESG",   color: "#1D9E75" },
  pr:          { label: "Связи с общественностью",    short: "PR",    color: "#D4537E" },
  pmo:         { label: "PMO",                        short: "PMO",   color: "#2563EB" },
  analytics:   { label: "Сводный отдел",              short: "ANL",   color: "#7C3AED" },
};

const dir = computed(() => {
  const d = (props.task as any).direction;
  if (!d) return null;
  return DIRS[String(d).toLowerCase()] || null;
});

// ── Status → stripe color ─────────────────────────────────────────────
const STATUS_STRIPE: Record<string, string> = {
  init:      "#94A3B8",
  new:       "#94A3B8",
  active:    "#378ADD",
  review:    "#EF9F27",
  done:      "#1D9E75",
  quarterly: "#A855F7",
  monthly:   "#6366F1",
  ongoing:   "#06B6D4",
  deferred:  "#888780",
};
const stripeColor = computed(() => {
  if (props.overdue) return "#E24B4A";
  return STATUS_STRIPE[props.task.status || "init"] || "#94A3B8";
});

// ── Consultant codes ──────────────────────────────────────────────────
const consultantCodes = computed<string[]>(() => {
  const c = (props.task as any).consultant;
  if (!c) return [];
  if (Array.isArray(c)) return c.map((x) => String(x));
  return [String(c)];
});

// ── Assignee avatar ───────────────────────────────────────────────────
const avatarInitials = computed(() => {
  const n = props.task.assignee_name || props.task.assignee_email || "?";
  return n.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase();
});

// ── Quarterly progress dots ───────────────────────────────────────────
const quarterDots = computed<boolean[]>(() => {
  const q = (props.task as any).quarters;
  if (!q) return [false, false, false, false];
  return [!!q.q1, !!q.q2, !!q.q3, !!q.q4];
});
const quarterDoneCount = computed(() => quarterDots.value.filter(Boolean).length);
const isQuarterly = computed(() => props.task.status === "quarterly");
const isMonthly = computed(() => props.task.status === "monthly");
const isOngoing = computed(() => props.task.status === "ongoing");
const isAllQuartersDone = computed(() => quarterDoneCount.value === 4);

// ── Transfer badges ───────────────────────────────────────────────────
// linked_year on the task = the source year this task was carried over FROM.
// If set, show "← FY2025" (or similar). linked_task_id = points to the task
// in another year — if set without linked_year, this task was the "source"
// of a carry-over forward (shown as "↗").
const transferFromLabel = computed<string | null>(() => {
  const ly = (props.task as any).linked_year;
  const py = props.task.portfolio_year;
  if (ly && ly !== py) return `← FY${String(ly).slice(-2)}`;
  return null;
});
const hasLinkedTask = computed<boolean>(() => {
  const lid = (props.task as any).linked_task_id;
  return !!lid && !transferFromLabel.value;
});

// ── Priority pip ──────────────────────────────────────────────────────
const prioColor = computed(() => {
  switch (props.task.priority) {
    case "high":   return "#E24B4A";
    case "medium": return "#D97706";
    case "low":    return "#059669";
    default:       return "transparent";
  }
});
const prioLabel = computed(() => {
  switch (props.task.priority) {
    case "high":   return "Высокий приоритет";
    case "medium": return "Средний приоритет";
    case "low":    return "Низкий приоритет";
    default:       return "Без приоритета";
  }
});

// ── Drag handler ──────────────────────────────────────────────────────
function onDragStart(ev: DragEvent) {
  if (!props.draggable) return;
  if (ev.dataTransfer) {
    ev.dataTransfer.effectAllowed = "move";
    try { ev.dataTransfer.setData("text/plain", props.task.id); } catch {}
  }
  emit("dragstart", props.task, ev);
}
</script>

<template>
  <div
    class="kc"
    :class="{
      'kc--proj': task.is_project,
      'kc--overdue': overdue,
      'kc--done': task.status === 'done',
      'kc--draggable': draggable,
    }"
    :style="{ '--stripe': stripeColor }"
    :draggable="draggable"
    @click="$emit('click')"
    @dragstart="onDragStart"
  >
    <!-- left status-stripe -->
    <span class="kc-stripe" aria-hidden="true"></span>

    <!-- main content -->
    <div class="kc-body">
      <div class="kc-row-title">
        <span
          v-if="task.priority"
          class="kc-prio"
          :style="{ background: prioColor }"
          :title="prioLabel"
        ></span>
        <span class="kc-title">{{ task.title }}</span>

        <!-- Transfer badges (carry-over markers) -->
        <span
          v-if="transferFromLabel"
          class="kc-transfer-pill kc-transfer-from"
          :title="`Перенесена из FY${(task as any).linked_year}`"
        >{{ transferFromLabel }}</span>
        <span
          v-else-if="hasLinkedTask"
          class="kc-transfer-pill kc-transfer-to"
          title="Перенесена на следующий год"
        >↗</span>

        <!-- Recurring/quarterly status pill (visible label) -->
        <span
          v-if="isMonthly"
          class="kc-status-pill kc-status-monthly"
          title="Ежемесячная задача — вне процентного учёта"
        >Ежемесячная</span>
        <span
          v-else-if="isOngoing"
          class="kc-status-pill kc-status-ongoing"
          title="Постоянная задача — вне процентного учёта"
        >Постоянная</span>
        <span
          v-else-if="isQuarterly"
          class="kc-status-pill"
          :class="isAllQuartersDone ? 'kc-status-q-done' : 'kc-status-quarterly'"
          :title="`Кварталы: ${quarterDoneCount}/4`"
        >{{ isAllQuartersDone ? '✓ Все кв.' : `Кв ${quarterDoneCount}/4` }}</span>
      </div>

      <!-- meta row: direction · consultant · quarterly-dots · date · avatar -->
      <div class="kc-row-meta">
        <span v-if="dir" class="kc-dir" :title="dir.label">
          <span class="kc-dir-bullet" :style="{ background: dir.color }"></span>
          {{ dir.short }}
        </span>

        <span
          v-if="consultantCodes.length"
          class="kc-cons"
          :title="consultantCodes.join(', ')"
        >{{ consultantCodes[0] }}{{ consultantCodes.length > 1 ? ` +${consultantCodes.length - 1}` : '' }}</span>

        <span v-if="isQuarterly" class="kc-qdots" :title="`${quarterDoneCount}/4 кварталов`">
          <span
            v-for="(on, i) in quarterDots"
            :key="i"
            class="kc-qdot"
            :class="{ 'kc-qdot--on': on }"
          ></span>
        </span>

        <span class="kc-spacer"></span>

        <span
          v-if="task.due_date"
          class="kc-date"
          :class="{ 'kc-date--od': overdue }"
        >{{ fmt.fmtDateNumeric(task.due_date) }}</span>

        <span
          v-if="task.assignee_name || task.assignee_email"
          class="kc-av"
          :title="task.assignee_name || task.assignee_email || ''"
        >{{ avatarInitials }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════ */
/* KanbanCard — flat + left status-stripe + compact (2-row).       */
/* ═══════════════════════════════════════════════════════════════ */
.kc {
  position: relative;
  background: var(--bg1, #FFFFFF);
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color .15s, box-shadow .15s, transform .15s, background .15s;
  overflow: hidden;
  user-select: none;
}
.kc--draggable {
  cursor: grab;
}
.kc--draggable:active {
  cursor: grabbing;
}
.kc:hover {
  border-color: rgba(127, 119, 221, .35);
  box-shadow: 0 4px 12px rgba(15, 23, 60, .08);
  transform: translateY(-1px);
}
.kc--overdue {
  background: #FEF6F6;
  border-color: rgba(226, 75, 74, .25);
}
.kc--done {
  background: #FAFAFB;
}
.kc--done .kc-title {
  color: rgba(30, 42, 74, .55);
  text-decoration: line-through;
  text-decoration-color: rgba(30, 42, 74, .35);
}

/* top color accent (эталон: верхняя полоса, не левая) */
.kc-stripe {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--stripe);
  border-top-left-radius: 8px;
  border-top-right-radius: 8px;
}

.kc-body {
  padding: 11px 11px 9px 11px;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* ── Title row ───────────────────────────────────────────────── */
.kc-row-title {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  min-width: 0;
}
.kc-prio {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 5px;
}
.kc-title {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  line-height: 1.35;
  letter-spacing: -0.005em;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.kc--proj .kc-title {
  font-weight: 600;
}

/* Status pill (top-right of title row) */
.kc-status-pill {
  flex-shrink: 0;
  font-size: 9.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
  letter-spacing: 0.01em;
  align-self: flex-start;
  margin-top: 1px;
}
.kc-status-monthly   { background: rgba(99, 102, 241, .12);  color: #4338CA; }
.kc-status-ongoing   { background: rgba(6, 182, 212, .12);   color: #0E7490; }
.kc-status-quarterly { background: rgba(168, 85, 247, .12);  color: #7E22CE; }
.kc-status-q-done    { background: rgba(29, 158, 117, .14);  color: #0E7A58; }

/* Transfer-pill (carry-over marker) */
.kc-transfer-pill {
  flex-shrink: 0;
  font-size: 9.5px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
  letter-spacing: 0.02em;
  align-self: flex-start;
  margin-top: 1px;
  font-variant-numeric: tabular-nums;
}
.kc-transfer-from {
  background: rgba(239, 159, 39, .14);
  color: #B87600;
  border: 0.5px solid rgba(239, 159, 39, .35);
}
.kc-transfer-to {
  background: rgba(127, 119, 221, .14);
  color: var(--p-deep);
  border: 0.5px solid rgba(127, 119, 221, .35);
}

/* ── Meta row ────────────────────────────────────────────────── */
.kc-row-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10.5px;
  color: rgba(30, 42, 74, .55);
  min-width: 0;
}
.kc-dir {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  flex-shrink: 0;
  color: var(--t2, #4B5468);   /* нейтральный текст; цвет направления — в буллете */
}
.kc-dir-bullet {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kc-cons {
  font-size: 9.5px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(127, 119, 221, .12);
  color: var(--p-deep);
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  flex-shrink: 0;
}

/* quarterly progress as 4 dots */
.kc-qdots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
}
.kc-qdot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(168, 85, 247, .25);
}
.kc-qdot--on {
  background: #A855F7;
}

.kc-spacer {
  flex: 1;
  min-width: 4px;
}

.kc-date {
  font-size: 10.5px;
  color: rgba(30, 42, 74, .55);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.kc-date--od {
  color: var(--sev-high);
  font-weight: 700;
}

.kc-av {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  /* Единый пурпур-лёд градиент (эталон аватаров), без радужного хэша. */
  background: linear-gradient(135deg, #8B7FF0, #7F77DD 55%, #6C5CE7);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 9.5px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0;
  flex-shrink: 0;
}

/* ── Reduced motion ──────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .kc {
    transition: none !important;
  }
  .kc:hover {
    transform: none !important;
  }
}
</style>
