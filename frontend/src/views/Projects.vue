<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useRouter, useRoute } from "vue-router";

import BadgeStatus from "@/components/BadgeStatus.vue";
import BadgePriority from "@/components/BadgePriority.vue";
import BadgeDeferred from "@/components/BadgeDeferred.vue";
import BadgeOverdue from "@/components/BadgeOverdue.vue";
import DirectionBadge from "@/components/DirectionBadge.vue";
import ChipFilter from "@/components/ChipFilter.vue";
import TaskModal from "@/components/TaskModal.vue";
import TaskProjectEditor from "@/components/TaskProjectEditor.vue";
import { useToast } from "@/composables/useToast";
import type { ProjectDetail } from "@/api/projects";

const router = useRouter();
const route = useRoute();

// ─── State ──────────────────────────────────────────────────────
const items = ref<any[]>([]);
const total = ref(0);
const byStatus = ref<Record<string, number>>({});
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Filters
const search = ref("");
const statusFilter = ref<string>("");
const directionFilter = ref<string>("");
const priorityFilter = ref<string>("");
const onlyOverdue = ref(false);
const hasEffectFilter = ref<boolean>(false); // Pack 7.33: проекты с эконом. эффектом
const portfolioYear = ref<number | null>(2025);
const sortBy = ref("num");
const sortDir = ref<"asc" | "desc">("asc");

const directionsList = ref<{ code: string; label: string; color: string }[]>([]);

// Modal state — used to create new project
const modalOpen = ref(false);
const modalProjectId = ref<string | null>(null);

// === v9.1 additions ===
const editorEntity = ref<ProjectDetail | null>(null);
const toast = useToast();
const editorReady = computed(() => {
  if (!modalOpen.value) return false;
  if (modalProjectId.value === null) return true;
  return editorEntity.value !== null && (editorEntity.value as any).id === modalProjectId.value;
});

watch(modalProjectId, async (id) => {
  if (id === null) {
    editorEntity.value = null;
    return;
  }
  try {
    const { data } = await api.get<ProjectDetail>(`/projects/${id}`);
    editorEntity.value = data;
  } catch (e: any) {
    toast.error("Ошибка загрузки проекта: " + (e?.message || ""));
    modalOpen.value = false;
  }
});

function onEditorSaved(id: string) {
  toast.success("Проект сохранён");
  modalOpen.value = false;
  if (typeof load === "function") load();
}
function onEditorClose() {
  modalOpen.value = false;
  if (typeof load === "function") load();
}

const STATUS_CHIPS = [
  { id: "new",       label: "Не начато",       accent: "#94A3B8", accentBg: "#F1F5F9" },
  { id: "init",      label: "Инициирование",   accent: "#64748B", accentBg: "#E2E8F0" },
  { id: "active",    label: "В процессе",      accent: "#3B82F6", accentBg: "rgba(55,138,221,.10)" },
  { id: "review",    label: "На согласовании", accent: "#F59E0B", accentBg: "#FEF9C3" },
  { id: "done",      label: "Завершено",       accent: "#10B981", accentBg: "#D1FAE5" },
  { id: "quarterly", label: "Ежеквартально",   accent: "#7E22CE", accentBg: "rgba(168,85,247,.13)" },
  { id: "monthly",   label: "Ежемесячно",      accent: "#4338CA", accentBg: "rgba(99,102,241,.13)" },
  { id: "ongoing",   label: "Постоянно",       accent: "#0E7490", accentBg: "rgba(6,182,212,.13)" },
];

// ─── URL sync ────────────────────────────────────────────────────
function syncFromQuery() {
  const q = route.query;
  if (q.status && typeof q.status === "string") statusFilter.value = q.status;
  if (q.direction && typeof q.direction === "string") directionFilter.value = q.direction;
  if (q.priority && typeof q.priority === "string") priorityFilter.value = q.priority;
  if (q.search && typeof q.search === "string") search.value = q.search;
  if (q.year && typeof q.year === "string") portfolioYear.value = parseInt(q.year);
  if (q.overdue === "1") onlyOverdue.value = true;
  if (q.has_effect === "1") hasEffectFilter.value = true; // Pack 7.33
  // Deep-link: ?open=<projectId> — авто-открытие in-place редактора проекта
  // (замена удалённой страницы /project/:id; используется drill-модалями)
  if (q.open && typeof q.open === "string") {
    modalProjectId.value = q.open;
    modalOpen.value = true;
  }
}

function syncToQuery() {
  const q: Record<string, string> = {};
  if (statusFilter.value) q.status = statusFilter.value;
  if (directionFilter.value) q.direction = directionFilter.value;
  if (priorityFilter.value) q.priority = priorityFilter.value;
  if (search.value) q.search = search.value;
  if (portfolioYear.value) q.year = String(portfolioYear.value);
  if (onlyOverdue.value) q.overdue = "1";
  if (hasEffectFilter.value) q.has_effect = "1"; // Pack 7.33
  router.replace({ query: q });
}

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: any = {
      limit: 200,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
    };
    if (statusFilter.value) params.status = statusFilter.value;
    if (directionFilter.value) params.direction = directionFilter.value;
    if (priorityFilter.value) params.priority = priorityFilter.value;
    if (search.value.trim()) params.search = search.value.trim();
    if (onlyOverdue.value) params.only_overdue = true;
    if (hasEffectFilter.value) params.has_economic_effect = true; // Pack 7.33
    if (portfolioYear.value) params.portfolio_year = portfolioYear.value;

    const r = await api.get<any>("/projects", { params });
    items.value = r.data.items || [];
    total.value = r.data.total || 0;
    byStatus.value = r.data.by_status || {};
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    items.value = [];
  } finally {
    loading.value = false;
  }
}

async function loadDirections() {
  try {
    const r = await api.get<any>("/directions");
    directionsList.value = r.data.directions || [];
  } catch (e) { /* ignore */ }
}

// ─── Helpers ─────────────────────────────────────────────────────
function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  return d.slice(0, 10).split("-").reverse().join(".");
}
function isOverdue(p: any): boolean {
  if (!p.due_date || p.status === "done") return false;
  return new Date(p.due_date) < new Date();
}
function daysUntil(d: string | null | undefined): number | null {
  if (!d) return null;
  return Math.floor((new Date(d).getTime() - Date.now()) / 86400000);
}
function progressColor(pct: number): string {
  if (pct >= 60) return "#1D9E75";
  if (pct >= 30) return "#D97706";
  return "#E24B4A";
}
function toggleStatus(s: string) { statusFilter.value = statusFilter.value === s ? "" : s; }
function toggleSort(col: string) {
  if (sortBy.value === col) sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  else { sortBy.value = col; sortDir.value = "asc"; }
}
function clearFilters() {
  statusFilter.value = "";
  directionFilter.value = "";
  priorityFilter.value = "";
  search.value = "";
  onlyOverdue.value = false;
  hasEffectFilter.value = false; // Pack 7.33
}
const hasFilters = computed(() =>
  !!(statusFilter.value || directionFilter.value || priorityFilter.value
     || search.value || onlyOverdue.value || hasEffectFilter.value)
);

function openCreate() {
  modalProjectId.value = null;
  modalOpen.value = true;
}

function openEdit(id: string, ev: Event) {
  ev.stopPropagation();  // prevent row click → /projects/<id> navigation
  modalProjectId.value = id;
  modalOpen.value = true;
}
function openProject(id: string) {
  // project-detail page удалён — проект открывается in-place редактором
  modalProjectId.value = id;
  modalOpen.value = true;
}

// ─── Watches ─────────────────────────────────────────────────────
watch([statusFilter, directionFilter, priorityFilter, onlyOverdue, portfolioYear, sortBy, sortDir],
      () => { syncToQuery(); load(); });

let searchTimer: number | null = null;
watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { syncToQuery(); load(); }, 250) as any;
});

onMounted(() => {
  syncFromQuery();
  loadDirections();
  load();
});

// Deep-link ?open=<id> теперь реактивен — страница больше не ремоунтится при
// смене query (key по route.path), поэтому открытие из уведомления/дрилл-модали
// на том же пути обрабатываем через watch, а не только в onMounted.
watch(() => route.query.open, (open) => {
  if (open && typeof open === "string") {
    modalProjectId.value = open;
    modalOpen.value = true;
  }
});
</script>

<template>
  <div class="projects-page">
    <!-- Header -->
    <div class="page-header">
      <div class="page-eyebrow">ПОРТФЕЛЬ <span style="color: #7F77DD;">{{ portfolioYear || "Все годы" }}</span></div>
      <h1 class="page-title">Проекты</h1>
      <div class="page-sub">
        <span style="font-variant-numeric: tabular-nums;">{{ total }}</span>
        <span style="color: var(--t3); margin-left: 6px;">{{
          total === 1 ? "проект" : (total < 5 ? "проекта" : "проектов")
        }}</span>
      </div>
    </div>

    <!-- Status chips row -->
    <div class="chip-row">
      <ChipFilter v-for="s in STATUS_CHIPS" :key="s.id"
                  :label="s.label"
                  :count="byStatus[s.id]"
                  :active="statusFilter === s.id"
                  :accent="s.accent"
                  :accent-bg="s.accentBg"
                  :animate-in="true"
                  @click="toggleStatus(s.id)" />
      <ChipFilter v-if="byStatus['deferred']"
                  label="Перенесено"
                  :count="byStatus['deferred']"
                  :active="statusFilter === 'deferred'"
                  accent="#7F77DD"
                  accent-bg="rgba(127,119,221,.10)"
                  :animate-in="true"
                  @click="toggleStatus('deferred')">
        <template #icon>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="5" y1="12" x2="19" y2="12"/>
            <polyline points="12 5 19 12 12 19"/>
          </svg>
        </template>
      </ChipFilter>

      <!-- Pack 7.33: чип «С эконом. эффектом» -->
      <ChipFilter
        label="С эконом. эффектом"
        :active="hasEffectFilter"
        accent="#1D9E75"
        accent-bg="rgba(29,158,117,.10)"
        :animate-in="true"
        @click="hasEffectFilter = !hasEffectFilter"
      >
        <template #icon>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 3v18h18" />
            <path d="M7 14l4-4 4 4 6-6" />
          </svg>
        </template>
      </ChipFilter>
    </div>

    <!-- Filter bar -->
    <div class="filter-bar">
      <input v-model="search" class="filter-search"
             placeholder="Поиск по номеру, названию, исполнителю…" />
      <select v-model="directionFilter" class="filter-select">
        <option value="">Все направления</option>
        <option v-for="d in directionsList" :key="d.code" :value="d.code">{{ d.label }}</option>
      </select>
      <select v-model="priorityFilter" class="filter-select">
        <option value="">Все приоритеты</option>
        <option value="high">Высокий</option>
        <option value="medium">Средний</option>
        <option value="low">Низкий</option>
      </select>
      <label class="filter-overdue">
        <input type="checkbox" v-model="onlyOverdue" />
        <span>Только просроченные</span>
      </label>
      <button v-if="hasFilters" class="btn-clear" @click="clearFilters">Очистить</button>
      <button class="btn-create" @click="openCreate">+ Проект</button>
    </div>

    <!-- States -->
    <div v-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>
    <div v-else-if="loading && items.length === 0" class="state-msg">Загрузка…</div>
    <div v-else-if="!loading && items.length === 0" class="state-msg">Ничего не найдено</div>

    <!-- Project list -->
    <div v-else class="project-list">
      <div class="list-header">
        <button class="col-num" @click="toggleSort('num')">
          № <span v-if="sortBy === 'num'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <button class="col-title" @click="toggleSort('title')">
          НАЗВАНИЕ <span v-if="sortBy === 'title'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <div class="col-progress">ПРОГРЕСС</div>
        <div class="col-status">СТАТУС</div>
        <button class="col-deadline" @click="toggleSort('due_date')">
          ДЕДЛАЙН <span v-if="sortBy === 'due_date'" class="sort-arr">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
        </button>
        <div class="col-actions"></div>
      </div>

      <div v-for="p in items" :key="p.id" class="project-row" @click="openProject(p.id)">
        <div class="col-num">
          <span class="num-pill">{{ p.num || "—" }}</span>
        </div>
        <div class="col-title">
          <div class="proj-title-text">{{ p.title }}</div>
          <div class="proj-meta">
            <DirectionBadge v-if="p.direction_meta"
                            :direction="p.direction_meta"
                            variant="bar" size="sm" />
            <BadgePriority v-if="p.priority && p.priority !== 'medium'"
                           :priority="p.priority" size="sm" />
            <BadgeDeferred v-if="p.linked_year" :linked-year="p.linked_year" size="sm" />
          </div>
        </div>
        <div class="col-progress">
          <div class="progress-wrap">
            <div class="progress-bar">
              <div class="progress-fill"
                   :style="{
                     width: (p.progress_percent || 0) + '%',
                     background: progressColor(p.progress_percent || 0)
                   }"></div>
            </div>
            <span class="progress-pct"
                  :style="{ color: progressColor(p.progress_percent || 0) }">
              {{ p.progress_percent || 0 }}%
            </span>
          </div>
          <div class="progress-counts">
            <span class="pc-num">{{ p.tasks_done || 0 }}/{{ p.tasks_total || 0 }}</span>
            <span class="pc-lbl">задач</span>
          </div>
        </div>
        <div class="col-status">
          <BadgeStatus :status="p.status" size="sm" />
        </div>
        <div class="col-deadline">
          <BadgeOverdue v-if="isOverdue(p)" size="sm" />
          <span v-else class="deadline-text"
                :class="{ 'soon': daysUntil(p.due_date) != null && daysUntil(p.due_date) <= 14 && daysUntil(p.due_date) >= 0 }">
            {{ formatDate(p.due_date) }}
          </span>
        </div>
        <div class="col-actions">
          <button class="row-edit-btn" :title="'Редактировать проект'"
                  @click="openEdit(p.id, $event)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- TaskModal in project mode -->
    <TaskProjectEditor v-if="editorReady"
                       :entity="editorEntity"
                       kind="project"
                       @close="onEditorClose"
                       @saved="onEditorSaved" />
  </div>
</template>

<style scoped>
.projects-page { padding: 24px 32px; max-width: 1800px; margin: 0 auto; }

.page-header { margin-bottom: 16px; }
.page-eyebrow {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--t3, var(--t3)); margin-bottom: 6px;
}
.page-title {
  font-size: 22px; font-weight: 500; letter-spacing: -0.01em;
  margin: 0 0 4px; color: var(--t1, #1E2A4A);
}
.page-sub { font-size: 13px; color: var(--t1, #1E2A4A); font-weight: 500; }

.chip-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }

.filter-bar {
  display: flex; gap: 8px; align-items: center; margin-bottom: 18px; flex-wrap: wrap;
}
.filter-search {
  flex: 1; min-width: 240px; padding: 8px 12px;
  border: 1px solid var(--border-input); border-radius: 11px;
  background: var(--bg1, #fff); font-size: 12px; color: var(--t1, #1E2A4A);
  outline: none; transition: border-color .12s, box-shadow .12s;
}
.filter-search:focus {
  border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.10);
}
.filter-select {
  padding: 8px 28px 8px 12px;
  border: 1px solid var(--border-input); border-radius: 11px;
  background-color: var(--bg1, #fff);
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5l3 3 3-3' fill='none' stroke='%239CA3AF' stroke-width='1.5' stroke-linecap='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: right 8px center;
  font-size: 12px; appearance: none; -webkit-appearance: none; cursor: pointer;
  outline: none; min-width: 180px; color: var(--t1, #1E2A4A);
}
.filter-overdue {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; color: var(--t2, #475569); cursor: pointer; user-select: none;
}
.btn-clear {
  padding: 6px 12px; background: transparent; border: 1px solid var(--border-input);
  border-radius: 11px; color: var(--t3, var(--t3)); font-size: 11px;
  cursor: pointer; transition: all .12s;
}
.btn-clear:hover { background: #F1F5F9; }
.btn-create {
  padding: 8px 14px; background: #7F77DD; color: #fff; border: none;
  border-radius: 11px; font-weight: 500; font-size: 12px; cursor: pointer;
  transition: background .12s; margin-left: auto;
}
.btn-create:hover { background: #6E66CC; }

.state-msg {
  padding: 32px; text-align: center; color: var(--t3, var(--t3)); font-size: 13px;
  background: var(--bg1, #fff); border-radius: 12px; border: 1px solid var(--border-input);
}
.state-msg.error { color: #993D3D; }

.project-list {
  background: var(--bg1, #fff); border-radius: 12px; border: 1px solid var(--border-input);
  overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
}

.list-header {
  display: grid;
  grid-template-columns: 80px 1.6fr 220px 130px 120px 40px;
  gap: 12px; padding: 10px 16px;
  border-bottom: 1px solid var(--border-input); background: var(--bg2, #FAFBFC);
  font-size: 9.5px; font-weight: 500; color: var(--t3, var(--t3));
  letter-spacing: 0.06em; text-transform: uppercase;
}
.list-header > * {
  text-align: left; background: transparent; border: none;
  font-weight: inherit; font-size: inherit; letter-spacing: inherit;
  color: inherit; cursor: default; font-family: inherit; padding: 0;
}
.list-header button { cursor: pointer; transition: color .12s; }
.list-header button:hover { color: var(--t1, #1E2A4A); }
.sort-arr { font-weight: 700; margin-left: 2px; }

.project-row {
  display: grid;
  grid-template-columns: 80px 1.6fr 220px 130px 120px 40px;
  gap: 12px; padding: 12px 16px;
  border-bottom: 1px solid #F1F5F9;
  align-items: flex-start;
  cursor: pointer; transition: background .12s;
}
.project-row:hover { background: var(--bg2, #FAFBFC); }
.project-row:last-child { border-bottom: none; }

.col-num { display: flex; align-items: flex-start; }
.num-pill {
  font-size: 10.5px; font-weight: 600; padding: 3px 7px;
  background: #F1F5F9; color: var(--t2, #475569);
  border-radius: 5px; letter-spacing: 0.02em;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}

.col-title { min-width: 0; }
.proj-title-text {
  color: var(--t1, #1E2A4A); font-size: 13px; font-weight: 500; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; overflow: hidden;
}
.proj-meta {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin-top: 5px; align-items: center;
}

.col-progress { align-self: center; min-width: 0; }
.progress-wrap {
  display: flex; align-items: center; gap: 8px; margin-bottom: 3px;
}
.progress-bar {
  flex: 1; height: 5px; border-radius: 3px;
  background: #F1F5F9; overflow: hidden; min-width: 60px;
}
.progress-fill {
  height: 100%; transition: width .5s var(--ease-standard);
}
.progress-pct {
  font-size: 11px; font-weight: 600;
  font-variant-numeric: tabular-nums; min-width: 36px; text-align: right;
}
.progress-counts {
  display: flex; align-items: baseline; gap: 4px;
}
.pc-num {
  font-size: 11px; font-weight: 500;
  color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums;
}
.pc-lbl { font-size: 9.5px; color: var(--t3, #94A3B8); }

.col-status, .col-deadline { align-self: center; }

.deadline-text {
  font-size: 11.5px; color: var(--t2, #475569); font-variant-numeric: tabular-nums;
}
.deadline-text.soon { color: #D97706; font-weight: 500; }

@media (max-width: 1100px) {
  .list-header, .project-row {
    grid-template-columns: 60px 1fr 130px 100px 40px;
  }
  .col-progress { display: none; }
}

/* ═══════════ MOBILE (Phase 2): строки → карточки ═══════════ */
@media (max-width: 768px) {
  .projects-page { padding: 14px 12px; }
  /* Тулбар: поиск на всю ширину, селекты переносятся */
  .filter-bar { flex-wrap: wrap; }
  .filter-search { flex: 1 1 100%; min-width: 0; }
  .filter-select { flex: 1 1 auto; }
}
@media (max-width: 640px) {
  .projects-page { padding-bottom: calc(64px + env(safe-area-inset-bottom)); }
  /* Колоночный заголовок не нужен в карточном виде */
  .list-header { display: none; }
  /* Строка → карточка: № + название сверху, статус/дедлайн в ряд, прогресс ниже */
  .project-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 10px;
    grid-template-columns: none;
    padding: 12px 14px;
  }
  .col-num { flex: 0 0 auto; }
  .col-title { flex: 1 1 60%; min-width: 0; }
  .col-status { flex: 0 0 auto; }
  .col-deadline { flex: 0 0 auto; margin-left: auto; align-self: center; }
  .col-progress { flex: 1 1 100%; display: block; align-self: stretch; }
}
</style>
