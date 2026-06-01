<script setup lang="ts">
/**
 * KpiTileDrillModal.vue — Pack 7.46
 * ─────────────────────────────────────────────────────────────────
 * Drill-down модалка для 6 KPI-плиток главного Dashboard.
 *
 * Стилистика и логика — 1:1 копия DirectionDrillModal:
 *   • Header: bucket-label + title + huge KPI + chip-summary + meta справа
 *   • 4 mini-KPI с верхней полоской-stripe
 *   • Список компаний, отсортированных по числу проектов/задач (по entity)
 *     ◦ Каждая строка collapsible — раскрывает projects/tasks этой компании в bucket
 *     ◦ Клик на название компании → /companies/:code/workspace (overview)
 *     ◦ Клик на проект/задачу → /companies/:code/workspace?tab=list
 *   • Кнопка "Показать ещё N компаний" — dashed
 *   • Footer: Закрыть · "Открыть список <entity>"
 *
 * Bucket: total | done | active | overdue | deferred
 * Entity: projects | tasks (определяет hero number + порядок сортировки)
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";

type Bucket = "total" | "done" | "active" | "overdue" | "deferred";
type Entity = "projects" | "tasks";

interface DrillItem {
  id: string;
  num: string | null;
  title: string;
  status: string;
  priority: string;
  due_date: string | null;
  is_overdue: boolean;
  days_overdue: number | null;
  progress_percent: number;
  assignee_name: string | null;
}
interface DrillCompany {
  company_id: string;
  company_code: string | null;
  company_name: string;
  sector: string;
  projects_count: number;
  tasks_count: number;
  projects_total: number;
  tasks_total: number;
  overdue_tasks: number;
  projects: DrillItem[];
  tasks: DrillItem[];
}
interface DrillSummary {
  projects_count: number;
  tasks_count: number;
  projects_total_all: number;
  tasks_total_all: number;
  companies_count: number;
  assignees_count: number;
  extra_value: number;
  extra_label: string;
}
interface DrillResponse {
  bucket: Bucket;
  entity: Entity;
  year: number | null;
  label: string;
  title: string;
  accent: string;
  sector_color_map: Record<string, string>;
  summary: DrillSummary;
  companies: DrillCompany[];
}

const props = withDefaults(
  defineProps<{
    bucket: Bucket;
    /** Какая сторона split-плитки кликнута: projects | tasks */
    initialEntity?: Entity;
    year?: number | null;
    sectorCode?: string | null;
    directionCode?: string | null;
  }>(),
  { initialEntity: "tasks", year: null, sectorCode: null, directionCode: null },
);

const emit = defineEmits<{ close: [] }>();
const router = useRouter();

const data = ref<DrillResponse | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Какие компании раскрыты (по company_id)
const expanded = ref<Set<string>>(new Set());
function toggleCompany(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
  expanded.value = new Set(expanded.value);
}

// Сколько items показывать в раскрытой компании
const ITEMS_VISIBLE = 5;
const tasksFullyShown = ref<Set<string>>(new Set());
const projectsFullyShown = ref<Set<string>>(new Set());
function showAllTasks(companyId: string) {
  tasksFullyShown.value.add(companyId);
  tasksFullyShown.value = new Set(tasksFullyShown.value);
}
function showAllProjects(companyId: string) {
  projectsFullyShown.value.add(companyId);
  projectsFullyShown.value = new Set(projectsFullyShown.value);
}

// Коллапс списка компаний — показываем первые 5
const companiesExpanded = ref(false);
const VISIBLE_COMPANIES = 5;
const visibleCompanies = computed<DrillCompany[]>(() => {
  if (!data.value) return [];
  if (companiesExpanded.value) return data.value.companies;
  return data.value.companies.slice(0, VISIBLE_COMPANIES);
});

// ─── Status icon helpers (idem DirectionDrillModal) ───
function statusIcon(item: DrillItem): { symbol: "check" | "clock" | "warn" | "circle"; color: string; label: string } {
  if (item.is_overdue) return { symbol: "warn", color: "#E24B4A", label: "просрочено" };
  if (item.status === "done") return { symbol: "check", color: "#1D9E75", label: "завершено" };
  if (item.status === "active" || item.status === "review") return { symbol: "clock", color: "#EF9F27", label: "в работе" };
  return { symbol: "circle", color: "#888780", label: "не начат" };
}
function statusTextColor(item: DrillItem): string {
  if (item.is_overdue) return "#A32D2D";
  if (item.status === "done") return "#0F6E56";
  if (item.status === "active" || item.status === "review") return "#854F0B";
  return "#888780";
}

// ─── Load ───
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: Record<string, unknown> = {
      bucket: props.bucket,
      entity: props.initialEntity,
    };
    if (props.year) params.year = props.year;
    if (props.sectorCode) params.sector_code = props.sectorCode;
    if (props.directionCode) params.direction_code = props.directionCode;
    const res = await api.get<DrillResponse>("/dashboard/kpi-drill", { params });
    data.value = res.data;
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string };
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить данные";
  } finally {
    loading.value = false;
  }
}

// ─── Close + navigation ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

function gotoCompany(c: DrillCompany) {
  if (!c.company_code) return;
  router.push({ name: "company-workspace", params: { code: c.company_code } });
  close();
}
function gotoTaskList(c: DrillCompany) {
  if (!c.company_code) return;
  router.push({
    name: "company-workspace",
    params: { code: c.company_code },
    query: { tab: "list" },
  });
  close();
}
function gotoListAll() {
  // Открыть полный список — global tasks / projects route, если они есть.
  const routeName = props.initialEntity === "projects" ? "projects" : "tasks";
  router.push({ name: routeName, query: props.year ? { year: String(props.year) } : {} });
  close();
}

let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
  void load();
});
onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});

// ─── Display constants ───
const HERO_VERB: Record<Bucket, string> = {
  total:    "всего",
  done:     "завершено",
  active:   "в работе",
  overdue:  "просрочено",
  deferred: "перенесено",
};

const _BUCKET_ACCENT: Record<Bucket, string> = {
  total: "#7F77DD",
  done: "#1D9E75",
  active: "#EF9F27",
  overdue: "#E24B4A",
  deferred: "#7F77DD",
};

// ─── Display helpers ───
const accent = computed(() => data.value?.accent || _BUCKET_ACCENT[props.bucket] || "#7F77DD");

const heroNum = computed(() => {
  if (!data.value) return 0;
  return props.initialEntity === "projects"
    ? data.value.summary.projects_count
    : data.value.summary.tasks_count;
});
const heroUnit = computed(() => {
  const action = HERO_VERB[props.bucket] || "";
  const noun = props.initialEntity === "projects" ? "проектов" : "задач";
  return action ? `${noun} ${action}` : `${noun} всего`;
});
const heroOf = computed(() => {
  if (!data.value) return "";
  const total = props.initialEntity === "projects"
    ? data.value.summary.projects_total_all
    : data.value.summary.tasks_total_all;
  if (props.bucket === "total" || total === 0) return "";
  return `из ${total}`;
});

// summary line under hero (chip-style purple)
const summaryChip = computed(() => {
  if (!data.value) return "";
  const s = data.value.summary;
  return `${s.companies_count} компаний · ${s.projects_count} из ${s.projects_total_all} проектов · ${s.tasks_count} из ${s.tasks_total_all} задач`;
});

function formatDate(d: string | null): string {
  if (!d) return "—";
  return d;
}
function pluralDays(n: number): string {
  const m = n % 100;
  if (m >= 11 && m <= 14) return "дней";
  const r = n % 10;
  if (r === 1) return "день";
  if (r >= 2 && r <= 4) return "дня";
  return "дней";
}
function overdueLabel(p: DrillItem): string {
  if (p.days_overdue && p.days_overdue > 0) return `просрочено ${p.days_overdue} ${pluralDays(p.days_overdue)}`;
  return formatDate(p.due_date);
}

function ctaLabel(): string {
  return props.initialEntity === "projects"
    ? "Открыть список проектов"
    : "Открыть список задач";
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div class="ddm-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div class="ddm-card" :style="{ '--sc': accent }">
          <div class="ddm-stripe" aria-hidden="true" />
          <div class="ddm-shim" aria-hidden="true" />
          <div class="ddm-glow" aria-hidden="true" />

          <button class="ddm-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" class="svg-ic" width="13" height="13"><path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/></svg>
          </button>

          <!-- Header -->
          <div class="ddm-sect ddm-row" style="--si:0; padding-top:20px;">
            <div class="ddm-h-top">
              <div>
                <div class="ddm-h-l">{{ data?.label || "Загрузка" }}</div>
                <div class="ddm-h-title">{{ data?.title || "&nbsp;" }}</div>
                <div v-if="data" class="ddm-h-v">
                  <span class="num">{{ heroNum }}</span>
                  <span class="unit">{{ heroUnit }} <span v-if="heroOf" class="of">· {{ heroOf }}</span></span>
                </div>
                <span v-if="data" class="ddm-h-d">{{ summaryChip }}</span>
              </div>
              <div v-if="data" class="ddm-h-right">
                <div>{{ data.summary.assignees_count }} ответственных</div>
                <div v-if="data.summary.extra_value > 0 && (bucket === 'overdue' || bucket === 'active')"
                     class="ddm-h-right-bad">
                  {{ data.summary.extra_value }} {{ data.summary.extra_label }}
                </div>
                <div v-else-if="bucket === 'overdue'" style="color: #1D9E75;">нет критичных</div>
                <div class="ddm-h-year">{{ year || "—" }} финансовый год</div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="ddm-sect ddm-loading">
            Загрузка данных…
          </div>

          <!-- Error -->
          <div v-else-if="errorMsg" class="ddm-sect ddm-alert">
            {{ errorMsg }}
          </div>

          <!-- Data: mini-KPIs + companies -->
          <template v-else-if="data">
            <div class="ddm-sect ddm-row" style="--si:1;">
              <div class="ddm-mini-grid">
                <div class="ddm-mini" style="--kc:#7F77DD; --ki:0;">
                  <div class="ddm-mk-l">Компаний затронуто</div>
                  <div class="ddm-mk-v">{{ data.summary.companies_count }}<span class="ddm-mk-u">с проектами или задачами</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:1;">
                  <div class="ddm-mk-l">{{ bucket === "total" ? "Проекты всего" : `Проекты ${HERO_VERB[bucket]}` }}</div>
                  <div class="ddm-mk-v">{{ data.summary.projects_count }}<span class="ddm-mk-u">из {{ data.summary.projects_total_all }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#EF9F27; --ki:2;">
                  <div class="ddm-mk-l">{{ bucket === "total" ? "Задачи всего" : `Задачи ${HERO_VERB[bucket]}` }}</div>
                  <div class="ddm-mk-v">{{ data.summary.tasks_count }}<span class="ddm-mk-u">из {{ data.summary.tasks_total_all }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:3;">
                  <div class="ddm-mk-l">{{ data.summary.extra_label || "—" }}</div>
                  <div class="ddm-mk-v">{{ data.summary.extra_value }}<span class="ddm-mk-u">{{ initialEntity === "projects" ? "проектов" : "задач" }}</span></div>
                </div>
              </div>
            </div>

            <!-- Companies list -->
            <div class="ddm-sect ddm-row" style="--si:2;">
              <div class="ddm-l-sec">
                <span>Компании · отсортированы по числу {{ initialEntity === "projects" ? "проектов" : "задач" }}</span>
                <span class="side">{{ data.summary.companies_count }} компаний</span>
              </div>

              <div v-if="!visibleCompanies.length" class="ddm-empty">
                Нет компаний с подходящими элементами
              </div>

              <div v-else class="ddm-co-list">
                <div
                  v-for="c in visibleCompanies"
                  :key="c.company_id"
                  class="ddm-co"
                  :class="{ expanded: expanded.has(c.company_id) }"
                >
                  <div class="ddm-co-hdr" @click="toggleCompany(c.company_id)">
                    <span class="ddm-co-chev">
                      <svg viewBox="0 0 14 14" class="svg-ic" width="11" height="11"><path d="M5 3l4 4-4 4"/></svg>
                    </span>
                    <span class="ddm-co-tick" :style="{ background: data.sector_color_map[c.sector] || '#888780' }" />
                    <span
                      class="ddm-co-name"
                      :title="'Открыть карточку компании «' + c.company_name + '»'"
                      @click.stop="gotoCompany(c)"
                    >{{ c.company_name }}</span>
                    <span class="ddm-co-stat" :title="'Проекты: ' + c.projects_count + ' в выборке из ' + c.projects_total">
                      <svg viewBox="0 0 14 14" class="ddm-co-stat-ico"><path d="M2.5 11V4l5-1.5 5 1.5v7M5 7h4M5 9.5h4"/></svg>
                      <span class="ddm-co-stat-num">{{ c.projects_count }}</span><span class="ddm-co-stat-tot">/{{ c.projects_total }}</span>
                    </span>
                    <span class="ddm-co-stat" :title="'Задачи: ' + c.tasks_count + ' в выборке из ' + c.tasks_total">
                      <svg viewBox="0 0 14 14" class="ddm-co-stat-ico"><path d="M3 7l3 3 5-6"/></svg>
                      <span class="ddm-co-stat-num">{{ c.tasks_count }}</span><span class="ddm-co-stat-tot">/{{ c.tasks_total }}</span>
                    </span>
                    <span class="ddm-co-overdue" v-if="c.overdue_tasks > 0" :title="c.overdue_tasks + ' просроченных задач'">
                      <svg viewBox="0 0 14 14" class="svg-ic" width="10" height="10" style="margin-right:2px"><path d="M7 2L1 12h12L7 2zM7 6v3M7 11h.01"/></svg>{{ c.overdue_tasks }}
                    </span>
                    <span v-else></span>
                  </div>

                  <div v-if="expanded.has(c.company_id)" class="ddm-co-body">
                    <!-- Projects -->
                    <div v-if="c.projects.length" class="ddm-co-section">
                      <div class="ddm-co-sub">
                        <span>
                          Проекты · {{ c.projects_count }}
                          <template v-if="!projectsFullyShown.has(c.company_id) && c.projects.length > ITEMS_VISIBLE">
                            · показано {{ ITEMS_VISIBLE }} из {{ c.projects.length }}
                          </template>
                        </span>
                        <span
                          v-if="!projectsFullyShown.has(c.company_id) && c.projects.length > ITEMS_VISIBLE"
                          class="ddm-co-sub-cta"
                          @click.stop="showAllProjects(c.company_id)"
                        >показать все →</span>
                      </div>
                      <div
                        v-for="p in projectsFullyShown.has(c.company_id) ? c.projects : c.projects.slice(0, ITEMS_VISIBLE)"
                        :key="p.id"
                        class="ddm-itm-row"
                        @click="gotoTaskList(c)"
                        :title="'Открыть список — ' + p.title"
                      >
                        <span class="ddm-itm-ico" :style="{ color: statusIcon(p).color }">
                          <svg v-if="statusIcon(p).symbol === 'check'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><path d="M3 7l2.5 2.5L11 4.5"/></svg>
                          <svg v-else-if="statusIcon(p).symbol === 'clock'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/><path d="M7 5v2l1.5 1"/></svg>
                          <svg v-else-if="statusIcon(p).symbol === 'warn'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/><path d="M7 4v3M7 9.5h.01"/></svg>
                          <svg v-else viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/></svg>
                        </span>
                        <span class="ddm-itm-name">{{ p.title }}</span>
                        <span class="ddm-itm-meta" :style="p.is_overdue ? { color: '#A32D2D' } : undefined">
                          {{ p.is_overdue ? overdueLabel(p) : formatDate(p.due_date) }}
                        </span>
                        <span class="ddm-itm-status" :style="{ color: statusTextColor(p) }">{{ statusIcon(p).label }}</span>
                      </div>
                    </div>
                    <div v-else class="ddm-co-empty">Проектов в этой выборке нет</div>

                    <!-- Tasks -->
                    <div v-if="c.tasks.length" class="ddm-co-section">
                      <div class="ddm-co-sub">
                        <span>
                          Задачи · {{ c.tasks_count }}
                          <template v-if="!tasksFullyShown.has(c.company_id) && c.tasks.length > ITEMS_VISIBLE">
                            · показано {{ ITEMS_VISIBLE }} из {{ c.tasks.length }}
                          </template>
                        </span>
                        <span
                          v-if="!tasksFullyShown.has(c.company_id) && c.tasks.length > ITEMS_VISIBLE"
                          class="ddm-co-sub-cta"
                          @click.stop="showAllTasks(c.company_id)"
                        >показать все задачи →</span>
                      </div>
                      <div
                        v-for="t in tasksFullyShown.has(c.company_id) ? c.tasks : c.tasks.slice(0, ITEMS_VISIBLE)"
                        :key="t.id"
                        class="ddm-itm-row"
                        @click="gotoTaskList(c)"
                        :title="'Открыть список — ' + t.title"
                      >
                        <span class="ddm-itm-ico" :style="{ color: statusIcon(t).color }">
                          <svg v-if="statusIcon(t).symbol === 'check'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><path d="M3 7l2.5 2.5L11 4.5"/></svg>
                          <svg v-else-if="statusIcon(t).symbol === 'clock'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/><path d="M7 5v2l1.5 1"/></svg>
                          <svg v-else-if="statusIcon(t).symbol === 'warn'" viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/><path d="M7 4v3M7 9.5h.01"/></svg>
                          <svg v-else viewBox="0 0 14 14" class="svg-ic" width="10" height="10"><circle cx="7" cy="7" r="4"/></svg>
                        </span>
                        <span class="ddm-itm-name">{{ t.title }}</span>
                        <span class="ddm-itm-meta" :style="t.is_overdue ? { color: '#A32D2D' } : undefined">
                          {{ t.assignee_name || (t.is_overdue ? overdueLabel(t) : formatDate(t.due_date)) }}
                        </span>
                        <span class="ddm-itm-status" :style="{ color: statusTextColor(t) }">{{ statusIcon(t).label }}</span>
                      </div>
                    </div>
                    <div v-else class="ddm-co-empty">Задач в этой выборке нет</div>
                  </div>
                </div>
              </div>

              <!-- Show more companies -->
              <button
                v-if="data.companies.length > VISIBLE_COMPANIES && !companiesExpanded"
                class="ddm-collapse-btn"
                @click="companiesExpanded = true"
              >
                <svg viewBox="0 0 14 14" class="svg-ic" width="11" height="11" style="color:#7F77DD;"><path d="M3.5 5l3.5 3.5L10.5 5"/></svg>
                Показать ещё {{ data.companies.length - VISIBLE_COMPANIES }} компаний
              </button>
              <button
                v-else-if="data.companies.length > VISIBLE_COMPANIES"
                class="ddm-collapse-btn"
                @click="companiesExpanded = false"
              >
                <svg viewBox="0 0 14 14" class="svg-ic" width="11" height="11" style="color:#7F77DD; transform:rotate(180deg);"><path d="M3.5 5l3.5 3.5L10.5 5"/></svg>
                Свернуть · показано {{ data.companies.length }}
              </button>
            </div>
          </template>

          <!-- Footer -->
          <div class="ddm-ftr ddm-row" style="--si:3;">
            <button class="ddm-btn ddm-btn-g" @click="close">Закрыть</button>
            <button class="ddm-btn ddm-btn-p" @click="gotoListAll">
              {{ ctaLabel() }}
              <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ddm-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.ddm-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 820px; overflow: hidden; animation: ddmIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) .08s both; }
.ddm-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: ddmStripe .75s cubic-bezier(0.34, 1.2, 0.64, 1) .2s both; z-index: 3; }
.ddm-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: ddmShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.ddm-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.ddm-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, #888780); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.ddm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.ddm-row { animation: ddmUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.ddm-sect { padding: 14px 22px; }
.ddm-sect + .ddm-sect { padding-top: 0; }

.ddm-h-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
.ddm-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .08em; }
.ddm-h-title { font-size: 19px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; letter-spacing: -.01em; }
.ddm-h-v { font-size: 42px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.ddm-h-v .unit { font-size: 13px; color: var(--t3, #888780); font-weight: 500; letter-spacing: 0; }
.ddm-h-v .of { color: #B4B2A9; font-weight: 400; }
.ddm-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; background: rgba(127, 119, 221, .08); color: #534AB7; }
.ddm-h-right { text-align: right; font-size: 11px; color: var(--t3, #888780); font-weight: 500; line-height: 1.7; }
.ddm-h-right-bad { color: #A32D2D; }
.ddm-h-year { color: var(--t1, #1E2A4A); }

.ddm-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.ddm-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; }
.ddm-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: ddmKpiTop .65s cubic-bezier(0.34, 1.2, 0.64, 1) calc(.78s + var(--ki) * .09s) forwards; }
.ddm-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .05em; line-height: 1.25; min-height: 22px; }
.ddm-mk-v { font-size: 15px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 4px; font-feature-settings: "tnum"; }
.ddm-mk-u { font-size: 9.5px; color: var(--t3, #888780); font-weight: 500; margin-left: 4px; letter-spacing: 0; }

.ddm-l-sec { font-size: 10px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.ddm-l-sec .side { font-size: 9.5px; color: #B4B2A9; text-transform: none; letter-spacing: .02em; font-weight: 400; }

.ddm-co-list { display: flex; flex-direction: column; gap: 6px; }
.ddm-co { border: 1px solid rgba(0, 0, 0, .05); border-radius: 9px; background: var(--bg1, #fff); overflow: hidden; transition: all .14s; }
.ddm-co:hover { border-color: rgba(127, 119, 221, .20); }
.ddm-co.expanded { border-color: rgba(127, 119, 221, .30); box-shadow: 0 4px 12px rgba(127, 119, 221, .08); }
.ddm-co-hdr { display: grid; grid-template-columns: 18px 4px 1fr 70px 70px 50px; gap: 10px; align-items: center; padding: 9px 12px; cursor: pointer; font-size: 11.5px; }
.ddm-co-chev { color: var(--t3, #888780); transition: transform .18s ease; display: flex; align-items: center; justify-content: center; }
.ddm-co.expanded .ddm-co-chev { transform: rotate(90deg); color: #7F77DD; }
.ddm-co-tick { width: 3px; height: 14px; border-radius: 1px; }
.ddm-co-name { color: var(--t1, #1E2A4A); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; border-bottom: 1px dashed transparent; transition: color .14s ease, border-color .14s ease; }
.ddm-co-name:hover { color: var(--sc); border-bottom-color: var(--sc); }
.ddm-co-stat { display: flex; align-items: center; gap: 4px; font-size: 11px; font-feature-settings: "tnum"; }
.ddm-co-stat-ico { width: 11px; height: 11px; color: #B4B2A9; stroke: currentColor; stroke-width: 1.5; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-co-stat-num { color: var(--t1, #1E2A4A); font-weight: 500; }
.ddm-co-stat-tot { color: var(--t3, #888780); }
.ddm-co-overdue { font-size: 10px; color: #A32D2D; font-weight: 500; text-align: right; display: inline-flex; align-items: center; justify-content: flex-end; stroke: currentColor; }
.ddm-co-body { padding: 0 12px 11px 34px; border-top: 1px solid rgba(0, 0, 0, .04); }
.ddm-co-section + .ddm-co-section { margin-top: 14px; }
.ddm-co-sub { font-size: 9.5px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin: 10px 0 6px; display: flex; justify-content: space-between; align-items: center; }
.ddm-co-sub-cta { font-size: 9.5px; color: #534AB7; text-transform: none; letter-spacing: .02em; font-weight: 500; cursor: pointer; }
.ddm-co-sub-cta:hover { text-decoration: underline; }
.ddm-co-empty { padding: 8px 0; font-size: 11px; color: #B4B2A9; font-style: italic; }

.ddm-itm-row { display: grid; grid-template-columns: 14px 1fr 110px 80px; gap: 8px; align-items: center; padding: 4px 6px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.ddm-itm-row:hover { background: rgba(127, 119, 221, .04); }
.ddm-itm-ico { display: flex; align-items: center; justify-content: center; }
.svg-ic { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-itm-name { color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.ddm-itm-meta { color: var(--t3, #888780); font-size: 10px; text-align: right; font-feature-settings: "tnum"; }
.ddm-itm-status { font-size: 10px; font-weight: 500; text-align: right; }

.ddm-collapse-btn { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 11px 14px; border-radius: 8px; border: 1px dashed rgba(127, 119, 221, .30); background: rgba(127, 119, 221, .04); color: #534AB7; font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; margin-top: 8px; }
.ddm-collapse-btn:hover { background: rgba(127, 119, 221, .08); }

.ddm-empty { padding: 30px 20px; text-align: center; color: #B4B2A9; font-size: 12px; font-style: italic; }
.ddm-loading { padding: 30px 20px; text-align: center; color: var(--t3, #888780); font-size: 12px; }
.ddm-alert { padding: 14px; background: rgba(226, 75, 74, .08); color: #A32D2D; border: 1px solid rgba(226, 75, 74, .18); border-radius: 8px; font-size: 12px; margin: 0 22px; }

.ddm-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.ddm-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.ddm-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.ddm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.ddm-btn-p { background: var(--sc); color: #fff; }
.ddm-btn-p:hover { filter: brightness(.93); }

.ddm-fade-enter-active, .ddm-fade-leave-active { transition: opacity .28s ease; }
.ddm-fade-enter-from, .ddm-fade-leave-to { opacity: 0; }

@keyframes ddmIn { 0% { opacity: 0; transform: translateY(22px) scale(.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes ddmStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes ddmShim { 0% { transform: translateX(-120%); } 60% { transform: translateX(220%); } 100% { transform: translateX(220%); } }
@keyframes ddmUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes ddmKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 640px) {
  .ddm-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .ddm-co-hdr { grid-template-columns: 18px 4px 1fr 60px 60px; }
  .ddm-co-overdue { display: none; }
  .ddm-itm-row { grid-template-columns: 14px 1fr 70px; }
  .ddm-itm-status { display: none; }
}
</style>
