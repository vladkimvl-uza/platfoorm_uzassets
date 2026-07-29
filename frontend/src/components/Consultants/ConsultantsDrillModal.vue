<script setup lang="ts">
/**
 * ConsultantsDrillModal.vue — universal drill modal for /consultants page.
 *
 * Three modes via `kind` prop:
 *   • consultant  — shows summary + companies + directions + tasks for one consultant
 *   • cell        — shows tasks at intersection (company × consultant) from heatmap
 *   • direction   — shows summary + consultants + tasks for one direction
 *
 * All data filtered client-side from the overview payload (consulted_tasks list).
 * Task rows emit @openTask(id) — parent opens TaskProjectEditor.
 */
import { computed } from "vue";
import Odometer from "@/components/Odometer.vue";

interface ConsultantInfo {
  id: string;
  code: string;
  name: string;
  abbr: string | null;
  color: string | null;
  is_big4: boolean;
  tasks_total?: number;
  tasks_done?: number;
  tasks_overdue?: number;
  completion_pct?: number;
}

interface DirInfo {
  id: string;
  label: string;
  color: string;
  tasks_total: number;
  tasks_done: number;
  tasks_overdue: number;
  completion_pct: number;
  consultant_codes: string[];
}

interface BoardInfo {
  id: string;
  name: string;
  sector_color: string;
}

interface TaskRow {
  id: string;
  num: string | null;
  title: string;
  board_id: string | null;
  board_name: string | null;
  company_id: string | null;
  company_name: string | null;
  status: string;
  due_date: string | null;
  direction_id: string | null;
  direction_label: string | null;
  consultants: { id?: string; code: string; abbr: string | null; color: string | null }[];
}

const props = defineProps<{
  kind: "consultant" | "cell" | "direction";
  // For 'consultant' mode:
  consultant?: ConsultantInfo | null;
  // For 'cell' mode:
  cellBoard?: BoardInfo | null;
  cellConsultant?: ConsultantInfo | null;
  cellCount?: number;
  // For 'direction' mode:
  direction?: DirInfo | null;
  // All consulted tasks (client-side filter source):
  allTasks: TaskRow[];
  // Lookup tables for stats:
  consultantsByCode: Record<string, ConsultantInfo>;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "openTask", id: string): void;
}>();

// ─── Filter tasks based on kind ──────────────────────────────────
const filteredTasks = computed<TaskRow[]>(() => {
  if (props.kind === "consultant" && props.consultant) {
    const code = props.consultant.code;
    return props.allTasks.filter(t => t.consultants.some(c => c.code === code));
  }
  if (props.kind === "cell" && props.cellBoard && props.cellConsultant) {
    // heatmap теперь агрегирован по КОМПАНИИ: cellBoard.id = company_id, а не board_id.
    // task.company_id уже разрешён на бэке (прямой ИЛИ через доску) → фильтруем по нему,
    // иначе задачи без доски (и других досок той же компании) выпали бы из ячейки.
    const cid = props.cellBoard.id;
    const code = props.cellConsultant.code;
    return props.allTasks.filter(
      t => t.company_id === cid && t.consultants.some(c => c.code === code),
    );
  }
  if (props.kind === "direction" && props.direction) {
    const did = props.direction.id;
    return props.allTasks.filter(t => t.direction_id === did);
  }
  return [];
});

// ─── Stats for header pane ───────────────────────────────────────
const companiesCovered = computed<{ name: string; count: number; sector_color: string | null }[]>(() => {
  if (props.kind !== "consultant") return [];
  // Дедуп по company_id (раньше по board_name → компания с N досок считалась
  // как N «компаний», расходясь с KPI companies_covered). Fallback на имя.
  const m = new Map<string, { name: string; count: number; sector_color: string | null }>();
  for (const t of filteredTasks.value) {
    const key = t.company_id || t.company_name;
    if (!key) continue;
    if (!m.has(key)) m.set(key, { name: t.company_name || "—", count: 0, sector_color: null });
    m.get(key)!.count++;
  }
  return Array.from(m.values()).sort((a, b) => b.count - a.count);
});

const directionsCovered = computed<{ id: string | null; label: string; count: number }[]>(() => {
  if (props.kind !== "consultant") return [];
  const m = new Map<string, { id: string | null; label: string; count: number }>();
  for (const t of filteredTasks.value) {
    const key = t.direction_label || i18nKey("Без направления");
    if (!m.has(key)) m.set(key, { id: t.direction_id, label: key, count: 0 });
    m.get(key)!.count++;
  }
  return Array.from(m.values()).sort((a, b) => b.count - a.count);
});

const consultantsForDirection = computed<{ code: string; consultant: ConsultantInfo | null; count: number }[]>(() => {
  if (props.kind !== "direction") return [];
  const m = new Map<string, number>();
  for (const t of filteredTasks.value) {
    for (const c of t.consultants) {
      m.set(c.code, (m.get(c.code) || 0) + 1);
    }
  }
  return Array.from(m.entries())
    .map(([code, count]) => ({ code, consultant: props.consultantsByCode[code] || null, count }))
    .sort((a, b) => b.count - a.count);
});

// ─── Helpers ─────────────────────────────────────────────────────
function fmtDate(s: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
}

const STATUS_DOT: Record<string, string> = {
  done: "#1D9E75", active: "#378ADD", overdue: "#E24B4A",
  init: "#7F77DD", new: "#94A3B8", review: "#EF9F27",
  quarterly: "#A855F7", monthly: "#6366F1", ongoing: "#06B6D4",
};
const STATUS_LABEL: Record<string, string> = {
  done: i18nKey("Завершено"), active: i18nKey("В процессе"), init: i18nKey("Инициирование"),
  new: i18nKey("Не начато"), review: i18nKey("На согласовании"),
  quarterly: i18nKey("Ежеквартально"), monthly: i18nKey("Ежемесячно"), ongoing: i18nKey("Постоянно"),
};

function isOverdue(t: TaskRow): boolean {
  if (!t.due_date) return false;
  if (t.status === "done") return false;
  if (["quarterly", "monthly", "ongoing"].includes(t.status)) return false;
  return new Date(t.due_date).getTime() < Date.now();
}

// ─── Header title ────────────────────────────────────────────────
const headerTitle = computed(() => {
  if (props.kind === "consultant") return props.consultant?.name || tr("Консультант");
  if (props.kind === "cell") return `${props.cellBoard?.name || "—"} × ${props.cellConsultant?.name || "—"}`;
  if (props.kind === "direction") return props.direction?.label || tr("Направление");
  return tr("Детали");
});
const headerAccentColor = computed(() => {
  if (props.kind === "consultant") return props.consultant?.color || "#7F77DD";
  if (props.kind === "cell") return props.cellConsultant?.color || "#7F77DD";
  if (props.kind === "direction") return props.direction?.color || "#7F77DD";
  return "#7F77DD";
});

const headerKind = computed(() => {
  if (props.kind === "consultant") return i18nKey("Консультант");
  if (props.kind === "cell") return i18nKey("Связка компания × консультант");
  return i18nKey("Направление");
});

// ─── Esc to close ────────────────────────────────────────────────
import { onMounted, onBeforeUnmount } from "vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t: tr } = useI18n();

function onKeydown(e: KeyboardEvent) { if (e.key === "Escape") emit("close"); }
onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div class="cdm-backdrop" @click.self="emit('close')">
    <div class="cdm-shell">

      <!-- ─── Header ─── -->
      <header class="cdm-header" :style="{ '--accent': headerAccentColor }">
        <div class="cdm-h-l">
          <span class="cdm-kind-pill">{{ headerKind }}</span>
          <h2 class="cdm-title">{{ headerTitle }}</h2>
        </div>
        <button class="cdm-close" @click="emit('close')" :aria-label="tr('Закрыть')">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M18 6L6 18M6 6l12 12"/>
          </svg>
        </button>
      </header>

      <!-- ─── Stats strip ─── -->
      <section class="cdm-stats kpi-rail">
        <!-- Consultant mode -->
        <template v-if="kind === 'consultant' && consultant">
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Прогресс') }}</div>
            <div class="cdm-stat-val" :style="{ color: (consultant.completion_pct || 0) >= 60 ? '#1D9E75' : (consultant.completion_pct || 0) >= 30 ? '#D97706' : '#993D3D' }">
              <Odometer :value="consultant.completion_pct || 0" />%
            </div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Задач всего') }}</div>
            <div class="cdm-stat-val"><Odometer :value="consultant.tasks_total || 0" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Завершено') }}</div>
            <div class="cdm-stat-val" style="color: #1D9E75"><Odometer :value="consultant.tasks_done || 0" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Просрочено') }}</div>
            <div class="cdm-stat-val" :style="{ color: (consultant.tasks_overdue || 0) > 0 ? '#E24B4A' : '#94A3B8' }">
              <Odometer :value="consultant.tasks_overdue || 0" />
            </div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Компаний') }}</div>
            <div class="cdm-stat-val"><Odometer :value="companiesCovered.length" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Направлений') }}</div>
            <div class="cdm-stat-val"><Odometer :value="directionsCovered.length" /></div>
          </div>
        </template>

        <!-- Cell mode -->
        <template v-else-if="kind === 'cell'">
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Задач связки') }}</div>
            <div class="cdm-stat-val" style="color: var(--accent)"><Odometer :value="cellCount || filteredTasks.length" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Завершено') }}</div>
            <div class="cdm-stat-val" style="color: #1D9E75">
              <Odometer :value="filteredTasks.filter(t => t.status === 'done').length" />
            </div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Просрочено') }}</div>
            <div class="cdm-stat-val" style="color: #E24B4A">
              <Odometer :value="filteredTasks.filter(isOverdue).length" />
            </div>
          </div>
        </template>

        <!-- Direction mode -->
        <template v-else-if="kind === 'direction' && direction">
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Прогресс') }}</div>
            <div class="cdm-stat-val" :style="{ color: direction.completion_pct >= 60 ? '#1D9E75' : direction.completion_pct >= 30 ? '#D97706' : '#993D3D' }">
              <Odometer :value="direction.completion_pct" />%
            </div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Задач всего') }}</div>
            <div class="cdm-stat-val"><Odometer :value="direction.tasks_total" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Завершено') }}</div>
            <div class="cdm-stat-val" style="color: #1D9E75"><Odometer :value="direction.tasks_done" /></div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Просрочено') }}</div>
            <div class="cdm-stat-val" :style="{ color: direction.tasks_overdue > 0 ? '#E24B4A' : '#94A3B8' }">
              <Odometer :value="direction.tasks_overdue" />
            </div>
          </div>
          <div class="cdm-stat">
            <div class="cdm-stat-lbl">{{ tr('Консультантов') }}</div>
            <div class="cdm-stat-val"><Odometer :value="consultantsForDirection.length" /></div>
          </div>
        </template>
      </section>

      <!-- ─── Side-by-side: breakdown (left) + tasks list (right) ─── -->
      <div class="cdm-body">
        <!-- Left: breakdown column (only for consultant + direction) -->
        <aside v-if="kind !== 'cell'" class="cdm-aside">
          <!-- Consultant mode: companies + directions list -->
          <template v-if="kind === 'consultant'">
            <section class="cdm-sec">
              <div class="cdm-sec-lbl">{{ tr('Компании (') }}{{ companiesCovered.length }})</div>
              <div v-for="(c, i) in companiesCovered" :key="`co-${i}`" class="cdm-mini-row">
                <span class="cdm-mini-name">{{ c.name }}</span>
                <span class="cdm-mini-num">{{ c.count }}</span>
              </div>
              <div v-if="!companiesCovered.length" class="cdm-empty">—</div>
            </section>
            <section class="cdm-sec">
              <div class="cdm-sec-lbl">{{ tr('Направления (') }}{{ directionsCovered.length }})</div>
              <div v-for="(d, i) in directionsCovered" :key="`dir-${i}`" class="cdm-mini-row">
                <span class="cdm-mini-name">{{ tr(d.label) }}</span>
                <span class="cdm-mini-num">{{ d.count }}</span>
              </div>
              <div v-if="!directionsCovered.length" class="cdm-empty">—</div>
            </section>
          </template>

          <!-- Direction mode: consultants list -->
          <template v-else-if="kind === 'direction'">
            <section class="cdm-sec">
              <div class="cdm-sec-lbl">{{ tr('Консультанты (') }}{{ consultantsForDirection.length }})</div>
              <div v-for="(c, i) in consultantsForDirection" :key="`c-${i}`" class="cdm-mini-row">
                <span
                  v-if="c.consultant"
                  class="cdm-cons-badge"
                  :style="{ background: (c.consultant.color || '#888') + '18', color: c.consultant.color || '#888' }"
                >{{ c.consultant.abbr || c.code }}</span>
                <span v-else class="cdm-cons-badge cdm-cons-badge-stub">{{ c.code }}</span>
                <span class="cdm-mini-name">{{ c.consultant?.name || c.code }}</span>
                <span class="cdm-mini-num">{{ c.count }}</span>
              </div>
              <div v-if="!consultantsForDirection.length" class="cdm-empty">—</div>
            </section>
          </template>
        </aside>

        <!-- Right: full-width task list -->
        <main class="cdm-main">
          <div class="cdm-main-h">
            <span class="cdm-main-h-t">{{ tr('Задачи ·') }} {{ filteredTasks.length }}</span>
          </div>
          <div class="cdm-task-list">
            <div
              v-for="t in filteredTasks"
              :key="t.id"
              class="cdm-task-row"
              @click="emit('openTask', t.id)"
            >
              <span class="cdm-task-dot" :style="{ background: STATUS_DOT[t.status] || '#94A3B8' }"></span>
              <div class="cdm-task-main">
                <div class="cdm-task-title">{{ t.title }}</div>
                <div class="cdm-task-meta">
                  <span v-if="t.board_name">{{ t.board_name }}</span>
                  <span v-if="t.num"> · #{{ t.num }}</span>
                  <span v-if="t.direction_label"> · {{ tr(t.direction_label) }}</span>
                  <span v-if="t.due_date" :class="{ 'cdm-overdue': isOverdue(t) }"> · {{ fmtDate(t.due_date) }}</span>
                  <span class="cdm-status-mini">· {{ STATUS_LABEL[t.status] || t.status }}</span>
                </div>
              </div>
              <div class="cdm-task-cons">
                <span
                  v-for="c in t.consultants.slice(0, 3)"
                  :key="c.code"
                  class="cdm-cons-pill"
                  :style="{ background: (c.color || '#888') + '18', color: c.color || '#888' }"
                >{{ c.abbr || c.code }}</span>
                <span v-if="t.consultants.length > 3" class="cdm-cons-pill cdm-cons-pill-extra">+{{ t.consultants.length - 3 }}</span>
              </div>
              <svg class="cdm-task-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="9 6 15 12 9 18"/>
              </svg>
            </div>
            <div v-if="!filteredTasks.length" class="cdm-empty">{{ tr('Нет задач') }}</div>
          </div>
        </main>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cdm-backdrop {
  position: fixed; inset: 0; z-index: 1100;
  background: rgba(15, 18, 40, 0.55);
  -webkit-backdrop-filter: blur(6px);
  backdrop-filter: blur(6px);
  display: flex; align-items: flex-start; justify-content: center;
  overflow-y: auto;
  padding: 36px 20px;
  animation: cdmFadeIn 200ms ease;
}
@keyframes cdmFadeIn { from { opacity: 0; } to { opacity: 1; } }

.cdm-shell {
  width: 100%; max-width: 1080px;
  background: var(--bg1, #fff);
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18), 0 8px 24px rgba(15, 23, 60, .08);
  display: flex; flex-direction: column;
  overflow: hidden;
  max-height: calc(100dvh - 72px);
  animation: cdmIn 320ms var(--ease-standard);
}
@keyframes cdmIn {
  from { opacity: 0; transform: translateY(14px) scale(0.985); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}

/* ─── Header ─── */
.cdm-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 22px;
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  color: #fff;
  border-bottom: 3px solid var(--accent, #7F77DD);
}
.cdm-h-l { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.cdm-kind-pill {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.85);
  width: fit-content;
}
.cdm-title {
  font-size: 18px; font-weight: 600; color: #fff;
  margin: 0; letter-spacing: -0.01em;
  overflow: hidden; text-overflow: ellipsis;
}
.cdm-close {
  background: rgba(255, 255, 255, .1);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 6px; border-radius: 7px;
  cursor: pointer;
  transition: background .15s;
}
.cdm-close:hover { background: rgba(255, 255, 255, .22); }

/* ─── Stats strip ─── */
.cdm-stats {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(0, 1fr);
  gap: 0;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  background: var(--bg2, #FAFAFC);
}
.cdm-stat {
  display: flex; flex-direction: column; gap: 4px;
  padding: 4px 14px;
  border-right: 1px solid rgba(0, 0, 0, .06);
}
.cdm-stat:last-child { border-right: none; }
.cdm-stat-lbl {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted)); text-transform: uppercase;
}
.cdm-stat-val {
  font-size: 22px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

/* ─── Body ─── */
.cdm-body {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  flex: 1; min-height: 0;
  overflow: hidden;
}
.cdm-body:has(.cdm-aside:empty),
.cdm-body:not(:has(.cdm-aside)) {
  grid-template-columns: 1fr;
}
/* Fallback: cell mode → no aside → fill width */
.cdm-body > .cdm-main:only-child { grid-column: 1 / -1; }

/* ─── Aside ─── */
.cdm-aside {
  padding: 16px 16px 18px;
  border-right: 1px solid rgba(0, 0, 0, .06);
  background: var(--bg2, #FAFAFC);
  overflow-y: auto;
  display: flex; flex-direction: column; gap: 16px;
}
.cdm-sec {
  display: flex; flex-direction: column; gap: 2px;
}
.cdm-sec-lbl {
  font-size: 10px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, var(--t-muted)); text-transform: uppercase;
  margin-bottom: 4px;
}
.cdm-mini-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  transition: background .12s;
}
.cdm-mini-row:hover { background: rgba(127, 119, 221, .06); }
.cdm-mini-name {
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cdm-mini-num {
  font-size: 11px; font-weight: 600;
  font-variant-numeric: tabular-nums;
  background: rgba(0, 0, 0, .05);
  padding: 1px 7px; border-radius: 8px;
  color: rgba(30, 42, 74, 0.65);
  flex-shrink: 0;
}
.cdm-cons-badge {
  font-size: 10px; font-weight: 700;
  padding: 2px 6px; border-radius: 4px;
  flex-shrink: 0;
  white-space: nowrap;
}
.cdm-cons-badge-stub { background: #F1F1F1; color: #555; }

/* ─── Main task list ─── */
.cdm-main {
  display: flex; flex-direction: column;
  min-width: 0;
  overflow: hidden;
}
.cdm-main-h {
  padding: 12px 18px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  background: var(--bg1, #fff);
  flex-shrink: 0;
}
.cdm-main-h-t {
  font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.cdm-task-list {
  flex: 1; overflow-y: auto;
  padding: 4px 0;
}
.cdm-task-row {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 18px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .05);
  cursor: pointer;
  transition: background .12s;
}
.cdm-task-row:hover { background: rgba(127, 119, 221, .04); }
.cdm-task-dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cdm-task-main { flex: 1; min-width: 0; }
.cdm-task-title {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cdm-task-meta {
  font-size: 11px; color: var(--t3, var(--t-muted));
  margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cdm-status-mini { font-weight: 500; }
.cdm-overdue { color: var(--sev-high); font-weight: 600; }
.cdm-task-cons { display: flex; gap: 3px; flex-shrink: 0; }
.cdm-cons-pill {
  font-size: 10px; font-weight: 700;
  padding: 1.5px 5px;
  border-radius: 3px;
  white-space: nowrap;
}
.cdm-cons-pill-extra { background: #F1F1F1; color: var(--t3, var(--t-muted)); }
.cdm-task-chev {
  color: rgba(0, 0, 0, .25);
  flex-shrink: 0;
}
.cdm-empty {
  padding: 28px 18px;
  text-align: center; font-style: italic;
  color: var(--t3, var(--t-muted)); font-size: 12px;
}

@media (max-width: 860px) {
  .cdm-body { grid-template-columns: 1fr; }
  .cdm-aside { border-right: none; border-bottom: 1px solid rgba(0, 0, 0, .06); }
  .cdm-stats { grid-auto-flow: row; grid-auto-columns: unset; grid-template-columns: repeat(2, 1fr); }
  .cdm-stat { border-right: none; border-bottom: 1px solid rgba(0, 0, 0, .05); }
}
</style>
