<script setup lang="ts">
/**
 *
 * Карточка задачи/проекта для kanban-доски:
 *   - drag-handle полоска сверху (видна на hover)
 *   - card-top: title + edit-кнопка (3-dots)
 *   - status-специфичные badges (quarterly / monthly / ongoing)
 *   - consultant badges (если есть)
 *   - direction tag (с цветной полоской)
 *   - footer: priority icon + date range + assignee avatar
 *
 * TaskBrief не содержит description / start_date — эти поля рендерятся
 * только в карточках детальной модалки, не в kanban-картах.
 */
import { computed } from "vue";
import type { TaskBrief } from "@/api/tasks";
import { useFormatters } from "@/composables/useFormatters";

const props = defineProps<{
  task: TaskBrief;
  overdue: boolean;
}>();
defineEmits<{ (e: "click"): void }>();

const fmt = useFormatters();

const DIRS: Record<string, { label: string; color: string }> = {
  strategy:    { label: "Стратегическое управление",  color: "#1e2787" },
  finance:     { label: "Финансы / риски / аудит",    color: "#D97706" },
  procurement: { label: "Система закупок",            color: "#3B6D11" },
  orgdev:      { label: "Организационное развитие",   color: "#534AB7" },
  digital:     { label: "Цифровизация",               color: "#1D9E75" },
  operations:  { label: "Операционная эффективность", color: "#EF4444" },
  governance:  { label: "Корпоративное управление",   color: "#72243E" },
  esg:         { label: "ESG",                        color: "#1D9E75" },
  pr:          { label: "Связи с общественностью",    color: "#D4537E" },
  pmo:         { label: "PMO",                        color: "#2563EB" },
  analytics:   { label: "Сводный отдел",              color: "#7C3AED" },
};

const dir = computed(() => {
  const d = (props.task as any).direction;
  if (!d) return null;
  return DIRS[String(d).toLowerCase()] || null;
});

// Consultant codes (string | array | null) — show up to 2
const consultantCodes = computed<string[]>(() => {
  const c = (props.task as any).consultant;
  if (!c) return [];
  if (Array.isArray(c)) return c.slice(0, 2).map((x) => String(x));
  return [String(c)];
});

// Assignee avatar color (deterministic from name hash)
const _AV_COLORS = ["#5B8DEF", "#34A853", "#D97706", "#AF52DE", "#00BCD4", "#E67E22", "#1ABC9C", "#8E44AD", "#2ECC71", "#3498DB"];
const avatarColor = computed(() => {
  const n = props.task.assignee_name || props.task.assignee_email || "?";
  let h = 0;
  for (let i = 0; i < n.length; i++) h = (h * 31 + n.charCodeAt(i)) | 0;
  return _AV_COLORS[Math.abs(h) % _AV_COLORS.length];
});
const avatarInitials = computed(() => {
  const n = props.task.assignee_name || props.task.assignee_email || "?";
  return n.split(/\s+/).map((w) => w[0] || "").join("").slice(0, 2).toUpperCase();
});

function isQuarterlyAllDone(t: any): boolean {
  const q = t.quarters;
  return !!q && !!q.q1 && !!q.q2 && !!q.q3 && !!q.q4;
}
function quarterlyDoneCount(t: any): number {
  const q = t.quarters;
  if (!q) return 0;
  return ["q1", "q2", "q3", "q4"].filter((k) => q[k]).length;
}

// Priority pill class
function prioCls(p: string | null): string {
  if (p === "high")   return "kc-prio kc-prio-h";
  if (p === "medium") return "kc-prio kc-prio-m";
  if (p === "low")    return "kc-prio kc-prio-l";
  return "kc-prio kc-prio-n";
}
function prioLabel(p: string | null): string {
  if (p === "high")   return "Высокий";
  if (p === "medium") return "Средний";
  if (p === "low")    return "Низкий";
  return "Без приоритета";
}
</script>

<template>
  <div
    class="card"
    :class="{ 'proj-card': task.is_project }"
    @click="$emit('click')"
  >
    <div class="card-drag-handle" title="Перетащите для смены статуса"></div>

    <div class="card-top">
      <div class="card-title">{{ task.title }}</div>
      <button class="card-btn" draggable="false" title="Редактировать">
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <circle cx="3" cy="8" r="1.3"/>
          <circle cx="8" cy="8" r="1.3"/>
          <circle cx="13" cy="8" r="1.3"/>
        </svg>
      </button>
    </div>

    <!-- Quarterly progress badge -->
    <div v-if="task.status === 'quarterly'" class="card-status-badge"
         :class="{ 'card-status-quart-done': isQuarterlyAllDone(task) }">
      <template v-if="isQuarterlyAllDone(task)">
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="3 8 7 12 13 5"/>
        </svg>
        <span>Ежекв · 4/4 ✓</span>
      </template>
      <template v-else>
        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round">
          <rect x="2" y="3" width="12" height="11" rx="1.5"/>
          <path d="M2 7h12M5.5 3v2M10.5 3v2"/>
        </svg>
        <span>Ежекв · {{ quarterlyDoneCount(task) }}/4</span>
      </template>
      <div class="card-q-bar">
        <div
          v-for="q in [1, 2, 3, 4]"
          :key="q"
          class="card-q-segment"
          :class="{ 'card-q-segment-on': isQuarterlyAllDone(task) || ((task as any).quarters && (task as any).quarters['q' + q]) }"
        ></div>
      </div>
    </div>

    <div v-else-if="task.status === 'monthly'" class="card-status-badge card-status-monthly">
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round">
        <circle cx="8" cy="8" r="5.5"/>
        <path d="M8 5v3l2 1.5"/>
      </svg>
      <span>Ежемесячно</span>
    </div>

    <div v-else-if="task.status === 'ongoing'" class="card-status-badge card-status-ongoing">
      <svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor"
           stroke-width="1.5" stroke-linecap="round">
        <path d="M2 8a4 4 0 014-4h4a4 4 0 010 8H6a4 4 0 01-4-4z"/>
      </svg>
      <span>Постоянно</span>
    </div>

    <!-- Consultant badges -->
    <div v-if="consultantCodes.length > 0" class="card-cons-row">
      <span
        v-for="code in consultantCodes"
        :key="code"
        class="card-cons-badge"
      >{{ code }}</span>
    </div>

    <!-- Direction tag (с цветной левой полоской) -->
    <div v-if="dir" class="card-dir-row">
      <span class="card-dir" :style="{ borderLeftColor: dir.color }">
        {{ dir.label }}
      </span>
    </div>

    <!-- Footer: priority icon + date + assignee avatar -->
    <div class="card-ft">
      <span :class="prioCls(task.priority)" :title="prioLabel(task.priority)">
        <svg v-if="task.priority === 'high'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 10V3M3 6l3-3 3 3"/>
        </svg>
        <svg v-else-if="task.priority === 'medium'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <path d="M2.5 6h7"/>
        </svg>
        <svg v-else-if="task.priority === 'low'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 2v7M3 6l3 3 3-3"/>
        </svg>
        <svg v-else viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="6" cy="6" r="3"/>
        </svg>
      </span>
      <div class="card-meta">
        <span v-if="task.due_date" class="card-date" :class="{ 'card-date-od': overdue }">
          {{ fmt.fmtDateNumeric(task.due_date) }}
        </span>
        <div v-if="task.assignee_name || task.assignee_email" class="card-av"
             :style="{ background: avatarColor }"
             :title="task.assignee_name || task.assignee_email || ''">
          {{ avatarInitials }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════ */
/* ═══════════════════════════════════════════════════════════════ */
.card {
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(12px) saturate(1.4);
  -webkit-backdrop-filter: blur(12px) saturate(1.4);
  border-radius: 12px;
  padding: 12px;
  cursor: pointer;
  border: 1px solid rgba(255, 255, 255, 0.65);
  box-shadow:
    0 2px 8px rgba(15, 23, 60, 0.06),
    0 1px 2px rgba(15, 23, 60, 0.04),
    0 0 0 0.5px rgba(255, 255, 255, 0.5) inset;
  transition: box-shadow 0.2s, transform 0.2s, border-color 0.2s, background 0.2s;
  position: relative;
}
.card:hover {
  background: rgba(255, 255, 255, 0.92);
  box-shadow:
    0 8px 28px rgba(15, 23, 60, 0.12),
    0 2px 8px rgba(15, 23, 60, 0.07),
    0 0 0 1px rgba(124, 111, 247, 0.15) inset;
  transform: translateY(-2px);
  border-color: rgba(124, 111, 247, 0.30);
}
.card:hover .card-btn {
  opacity: 1;
}

.card-drag-handle {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 24px;
  cursor: grab;
  border-radius: 12px 12px 0 0;
  z-index: 2;
}
.card-drag-handle::before {
  content: "";
  position: absolute;
  top: 6px;
  left: 50%;
  transform: translateX(-50%);
  width: 24px;
  height: 3px;
  border-radius: 2px;
  background: rgba(30, 42, 74, 0.20);
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, width 0.15s;
}
.card:hover .card-drag-handle::before {
  opacity: 0.55;
  background: rgba(124, 111, 247, 0.35);
  width: 30px;
}
.card-drag-handle:hover::before {
  opacity: 0.9;
  background: #7F77DD;
  width: 34px;
}

.card-top {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 5px;
  position: relative;
  z-index: 1;
}
.card-title {
  font-size: 13px;
  font-weight: 600;
  color: #1E2A4A;
  line-height: 1.45;
  flex: 1;
  letter-spacing: -0.01em;
}
.proj-card .card-title {
  font-weight: 700;
}
.card-btn {
  background: none;
  border: none;
  cursor: pointer;
  color: rgba(30, 42, 74, 0.45);
  font-size: 14px;
  opacity: 0;
  padding: 3px 5px;
  border-radius: 6px;
  transition: all 0.1s;
  flex-shrink: 0;
}
.card-btn:hover {
  color: #7F77DD;
  background: rgba(124, 111, 247, 0.10);
}

/* Status-specific badges (quarterly, monthly, ongoing) */
.card-status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 5px 0 4px;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 600;
  background: rgba(168, 85, 247, 0.10);
  color: #7E22CE;
}
.card-status-quart-done {
  background: rgba(29, 158, 117, 0.12);
  color: #0E7A58;
}
.card-status-monthly {
  display: inline-flex;
  background: rgba(99, 102, 241, 0.10);
  color: #4338CA;
  padding: 3px 8px;
}
.card-status-ongoing {
  display: inline-flex;
  background: rgba(6, 182, 212, 0.10);
  color: #0E7490;
  padding: 3px 8px;
}
.card-q-bar {
  flex: 1;
  display: flex;
  gap: 2px;
}
.card-q-segment {
  flex: 1;
  height: 3px;
  border-radius: 1.5px;
  background: rgba(168, 85, 247, 0.18);
}
.card-q-segment-on {
  background: #A855F7;
}
.card-status-quart-done .card-q-segment {
  background: #1D9E75;
}

/* Consultant row */
.card-cons-row {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin: 4px 0 6px;
}
.card-cons-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(127, 119, 221, 0.14);
  color: #534AB7;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

/* Direction tag */
.card-dir-row {
  margin-bottom: 6px;
}
.card-dir {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 7px 2px 6px;
  border-radius: 0 4px 4px 0;
  background: rgba(30, 42, 74, 0.05);
  color: rgba(30, 42, 74, 0.75);
  border-left: 2px solid currentColor;
  letter-spacing: 0.02em;
}

/* Footer */
.card-ft {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.kc-prio {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kc-prio svg {
  width: 11px;
  height: 11px;
}
.kc-prio-h {
  background: rgba(239, 68, 68, 0.12);
  color: #E24B4A;
  border: 1px solid rgba(239, 68, 68, 0.20);
}
.kc-prio-m {
  background: rgba(217, 119, 6, 0.12);
  color: #D97706;
  border: 1px solid rgba(217, 119, 6, 0.20);
}
.kc-prio-l {
  background: rgba(5, 150, 105, 0.12);
  color: #059669;
  border: 1px solid rgba(5, 150, 105, 0.20);
}
.kc-prio-n {
  background: rgba(30, 42, 74, 0.06);
  color: rgba(30, 42, 74, 0.45);
  border: 1px solid rgba(30, 42, 74, 0.10);
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.card-date {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.55);
  font-variant-numeric: tabular-nums;
}
.card-date-od {
  color: #E24B4A;
  font-weight: 700;
  background: rgba(239, 68, 68, 0.08);
  padding: 1px 5px;
  border-radius: 5px;
}
.card-av {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
</style>
