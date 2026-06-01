<script setup lang="ts">
/**
 * CompanyTileDrillModal.vue — Pack 7.47
 * ─────────────────────────────────────────────────────────────────
 * Drill-down модалка для строки компании в блоке «Проекты по
 * компаниям» главного Dashboard.
 *
 * Триггеры (Dashboard.vue):
 *   • Клик на progress bar / progress % / projects-cell / tasks-cell
 *     / на код-бейдж → открывает этот модал
 *   • Клик на co-text (имя компании) → /companies/:code/workspace
 *     (НЕ открывает модал)
 *
 * Стиль — 1:1 DirectionDrillModal (ddm-*).
 *
 * Props:
 *   companyCode  — короткий код (e.g. "NUR")
 *   year         — финансовый год
 *   initialTab   — "projects" | "tasks" (какая секция активна)
 *
 * Footer CTA:
 *   • Список задач → /companies/:code/workspace?tab=list
 *   • Открыть карточку компании → /companies/:code/workspace
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";

type ItemFilter = "all" | "active" | "overdue";

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

interface CompanyMeta {
  code: string;
  name: string;
  sector: string;
  sector_label: string;
  sector_color: string;
}

interface Summary {
  progress_pct: number;
  projects_total: number;
  projects_done: number;
  projects_active: number;
  projects_overdue: number;
  tasks_total: number;
  tasks_done: number;
  tasks_active: number;
  tasks_overdue: number;
  assignees_count: number;
}

interface DrillResponse {
  company: CompanyMeta;
  year: number | null;
  accent: string;
  summary: Summary;
  projects: DrillItem[];
  tasks: DrillItem[];
}

const props = withDefaults(
  defineProps<{
    companyCode: string;
    year?: number | null;
    initialTab?: "projects" | "tasks";
  }>(),
  { year: null, initialTab: "projects" },
);

const emit = defineEmits<{ close: [] }>();
const router = useRouter();

const data = ref<DrillResponse | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Status filter (per-section, client-side)
const projectsFilter = ref<ItemFilter>("all");
const tasksFilter = ref<ItemFilter>("all");

// Pagination caps
const PROJECTS_VISIBLE = 5;
const TASKS_VISIBLE = 8;
const projectsFullyShown = ref(false);
const tasksFullyShown = ref(false);

// ─── Constants ───
const ACCENT_FALLBACK = "#7F77DD";

// ─── Filtered lists ───
function applyFilter(list: DrillItem[], f: ItemFilter): DrillItem[] {
  if (f === "all") return list;
  if (f === "overdue") return list.filter((it) => it.is_overdue);
  if (f === "active") return list.filter((it) => it.status === "active" || it.status === "review");
  return list;
}

const filteredProjects = computed<DrillItem[]>(() =>
  data.value ? applyFilter(data.value.projects, projectsFilter.value) : []
);
const filteredTasks = computed<DrillItem[]>(() =>
  data.value ? applyFilter(data.value.tasks, tasksFilter.value) : []
);

const visibleProjects = computed<DrillItem[]>(() => {
  const list = filteredProjects.value;
  return projectsFullyShown.value ? list : list.slice(0, PROJECTS_VISIBLE);
});
const visibleTasks = computed<DrillItem[]>(() => {
  const list = filteredTasks.value;
  return tasksFullyShown.value ? list : list.slice(0, TASKS_VISIBLE);
});

// ─── Status icon (idem DDM) ───
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
function rowBorderColor(it: DrillItem): string {
  return statusIcon(it).color;
}

// ─── Load ───
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const params: Record<string, unknown> = { company_code: props.companyCode };
    if (props.year) params.year = props.year;
    const res = await api.get<DrillResponse>("/dashboard/company-drill", { params });
    data.value = res.data;
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } }; message?: string };
    errorMsg.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить данные компании";
  } finally {
    loading.value = false;
  }
}

// ─── Close + navigation ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

function gotoWorkspace() {
  router.push({ name: "company-workspace", params: { code: props.companyCode } });
  close();
}
function gotoTaskList() {
  router.push({
    name: "company-workspace",
    params: { code: props.companyCode },
    query: { tab: "list" },
  });
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

// ─── Display helpers ───
const accent = computed(() => data.value?.accent || ACCENT_FALLBACK);

const summaryChip = computed(() => {
  if (!data.value) return "";
  const s = data.value.summary;
  return `${s.projects_total} проектов · ${s.tasks_total} задач · ${s.projects_done} проектов завершено · ${s.tasks_done} из ${s.tasks_total} задач`;
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
                <div v-if="data" class="ddm-h-l-row">
                  <span class="ddm-code-badge"
                        :style="{ background: 'rgba(127,119,221,.10)', color: '#534AB7' }">
                    {{ data.company.code }}
                  </span>
                  <span class="ddm-h-l">
                    Компания · <span :style="{ color: data.company.sector_color }">{{ data.company.sector_label }}</span>
                  </span>
                </div>
                <div v-else class="ddm-h-l">Загрузка</div>
                <div class="ddm-h-title">{{ data?.company.name || "—" }}</div>
                <div v-if="data" class="ddm-h-v">
                  <span class="num" :style="{ color: accent }">{{ data.summary.progress_pct }}</span>
                  <span class="unit">процентов выполнения · по задачам</span>
                </div>
                <span v-if="data" class="ddm-h-d">{{ summaryChip }}</span>
              </div>
              <div v-if="data" class="ddm-h-right">
                <div>{{ data.summary.assignees_count }} ответственных</div>
                <div v-if="data.summary.tasks_overdue > 0" class="ddm-h-right-bad">
                  {{ data.summary.tasks_overdue }} задач просрочено
                </div>
                <div v-else style="color: #1D9E75;">нет просроченных задач</div>
                <div class="ddm-h-year">{{ year || "—" }} финансовый год</div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="ddm-sect ddm-loading">
            Загрузка данных компании…
          </div>

          <!-- Error -->
          <div v-else-if="errorMsg" class="ddm-sect ddm-alert">
            {{ errorMsg }}
          </div>

          <!-- Data -->
          <template v-else-if="data">
            <!-- 4 mini-KPIs -->
            <div class="ddm-sect ddm-row" style="--si:1;">
              <div class="ddm-mini-grid">
                <div class="ddm-mini" style="--kc:#7F77DD; --ki:0;">
                  <div class="ddm-mk-l">Прогресс портфеля</div>
                  <div class="ddm-mk-v">{{ data.summary.progress_pct }}<span class="ddm-mk-u">% · средневзв.</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:1;">
                  <div class="ddm-mk-l">Проекты завершены</div>
                  <div class="ddm-mk-v">{{ data.summary.projects_done }}<span class="ddm-mk-u">из {{ data.summary.projects_total }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#EF9F27; --ki:2;">
                  <div class="ddm-mk-l">Задачи завершены</div>
                  <div class="ddm-mk-v">{{ data.summary.tasks_done }}<span class="ddm-mk-u">из {{ data.summary.tasks_total }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:3;">
                  <div class="ddm-mk-l">Просрочено</div>
                  <div class="ddm-mk-v">{{ data.summary.tasks_overdue }}<span class="ddm-mk-u">задач</span></div>
                </div>
              </div>
            </div>

            <!-- ─── Projects section ─── -->
            <div class="ddm-sect ddm-row" style="--si:2;">
              <div class="ddm-l-sec">
                <span>
                  Проекты компании · {{ filteredProjects.length }}
                  <template v-if="filteredProjects.length !== data.projects.length">
                    из {{ data.projects.length }}
                  </template>
                </span>
                <div class="ddm-fltr">
                  <span :class="['ddm-fltr-chip', { active: projectsFilter === 'all' }]"
                        @click="projectsFilter = 'all'">Все</span>
                  <span :class="['ddm-fltr-chip', { active: projectsFilter === 'active' }]"
                        @click="projectsFilter = 'active'">В работе</span>
                  <span :class="['ddm-fltr-chip', { active: projectsFilter === 'overdue' }]"
                        @click="projectsFilter = 'overdue'">Просрочено</span>
                </div>
              </div>

              <div v-if="!visibleProjects.length" class="ddm-empty">
                <template v-if="projectsFilter === 'overdue'">Просроченных проектов нет</template>
                <template v-else-if="projectsFilter === 'active'">Проектов в работе нет</template>
                <template v-else>У компании нет проектов</template>
              </div>

              <div v-else class="ddm-items">
                <div
                  v-for="p in visibleProjects"
                  :key="p.id"
                  class="ddm-bord-row uza-side-stripe uza-side-stripe-tight"
                  :style="{ '--stripe-color': rowBorderColor(p) }"
                  @click="gotoTaskList"
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

              <div v-if="!projectsFullyShown && filteredProjects.length > PROJECTS_VISIBLE"
                   class="ddm-show-more" @click="projectsFullyShown = true">
                показать ещё {{ filteredProjects.length - PROJECTS_VISIBLE }} проектов →
              </div>
            </div>

            <!-- ─── Tasks section ─── -->
            <div class="ddm-sect ddm-row" style="--si:3;">
              <div class="ddm-l-sec">
                <span>
                  Задачи компании · {{ filteredTasks.length }}
                  <template v-if="filteredTasks.length !== data.tasks.length">
                    из {{ data.tasks.length }}
                  </template>
                  <template v-if="!tasksFullyShown && filteredTasks.length > TASKS_VISIBLE">
                    · показано {{ TASKS_VISIBLE }} из {{ filteredTasks.length }}
                  </template>
                </span>
                <div class="ddm-fltr">
                  <span :class="['ddm-fltr-chip', { active: tasksFilter === 'all' }]"
                        @click="tasksFilter = 'all'">Все</span>
                  <span :class="['ddm-fltr-chip', { active: tasksFilter === 'active' }]"
                        @click="tasksFilter = 'active'">В работе</span>
                  <span :class="['ddm-fltr-chip', { active: tasksFilter === 'overdue' }]"
                        @click="tasksFilter = 'overdue'">Просрочено</span>
                </div>
              </div>

              <div v-if="!visibleTasks.length" class="ddm-empty">
                <template v-if="tasksFilter === 'overdue'">Просроченных задач нет</template>
                <template v-else-if="tasksFilter === 'active'">Задач в работе нет</template>
                <template v-else>У компании нет задач</template>
              </div>

              <div v-else class="ddm-items">
                <div
                  v-for="t in visibleTasks"
                  :key="t.id"
                  class="ddm-bord-row uza-side-stripe uza-side-stripe-tight"
                  :style="{ '--stripe-color': rowBorderColor(t) }"
                  @click="gotoTaskList"
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

              <div v-if="!tasksFullyShown && filteredTasks.length > TASKS_VISIBLE"
                   class="ddm-show-more" @click="tasksFullyShown = true">
                показать ещё {{ filteredTasks.length - TASKS_VISIBLE }} задач →
              </div>
            </div>
          </template>

          <!-- Footer -->
          <div class="ddm-ftr ddm-row" style="--si:4;">
            <button class="ddm-btn ddm-btn-g" @click="close">Закрыть</button>
            <button class="ddm-btn ddm-btn-w" @click="gotoTaskList">
              Список задач
              <svg viewBox="0 0 14 14" class="svg-ic" width="12" height="12"><path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/></svg>
            </button>
            <button class="ddm-btn ddm-btn-p" @click="gotoWorkspace">
              Открыть карточку компании
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
.ddm-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 820px; overflow: hidden; animation: ddmIn .55s var(--ease-standard) .08s both; }
.ddm-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: ddmStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.ddm-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: ddmShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.ddm-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.ddm-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.ddm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.ddm-row { animation: ddmUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.ddm-sect { padding: 14px 22px; }
.ddm-sect + .ddm-sect { padding-top: 0; }

.ddm-h-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
.ddm-h-l-row { display: flex; align-items: center; gap: 10px; margin-bottom: 3px; }
.ddm-code-badge { display: inline-flex; align-items: center; justify-content: center; font-size: 9.5px; font-weight: 500; padding: 2px 8px; border-radius: 999px; letter-spacing: .04em; font-feature-settings: "tnum"; }
.ddm-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.ddm-h-title { font-size: 19px; font-weight: 500; color: var(--t1, #1E2A4A); margin-top: 3px; letter-spacing: -.01em; }
.ddm-h-v { font-size: 42px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.ddm-h-v .unit { font-size: 13px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.ddm-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; background: rgba(127, 119, 221, .08); color: var(--p-deep); }
.ddm-h-right { text-align: right; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; line-height: 1.7; }
.ddm-h-right-bad { color: var(--sev-critical); }
.ddm-h-year { color: var(--t1, #1E2A4A); }

.ddm-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.ddm-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; }
.ddm-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: ddmKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards; }
.ddm-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .05em; line-height: 1.25; min-height: 22px; }
.ddm-mk-v { font-size: 15px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 4px; font-feature-settings: "tnum"; }
.ddm-mk-u { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-left: 4px; letter-spacing: 0; }

.ddm-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; gap: 12px; }

.ddm-fltr { display: flex; gap: 4px; }
.ddm-fltr-chip { padding: 2px 8px; border-radius: 999px; font-size: 10px; letter-spacing: 0; text-transform: none; cursor: pointer; font-weight: 500; color: var(--t3, var(--t-muted)); background: transparent; transition: all .14s; }
.ddm-fltr-chip:hover { color: var(--t1, #1E2A4A); }
.ddm-fltr-chip.active { background: rgba(127, 119, 221, .10); color: var(--p-deep); }

.ddm-items { display: flex; flex-direction: column; gap: 4px; }
.ddm-bord-row { display: grid; grid-template-columns: 14px 1fr 110px 80px; gap: 8px; align-items: center; padding: 7px 10px 7px 16px; border-radius: 6px; font-size: 11px; cursor: pointer; background: rgba(15, 23, 60, .015); transition: all .14s; }
.ddm-bord-row:hover { background: rgba(127, 119, 221, .04); transform: translateX(2px); }
.ddm-itm-ico { display: flex; align-items: center; justify-content: center; }
.svg-ic { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-itm-name { color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.ddm-itm-meta { color: var(--t3, var(--t-muted)); font-size: 10px; text-align: right; font-feature-settings: "tnum"; }
.ddm-itm-status { font-size: 10px; font-weight: 500; text-align: right; }

.ddm-show-more { text-align: center; padding: 8px 0 0; font-size: 10.5px; color: var(--p-deep); cursor: pointer; font-weight: 500; transition: color .14s; }
.ddm-show-more:hover { color: #3C3489; }

.ddm-empty { padding: 18px 20px; text-align: center; color: #B4B2A9; font-size: 12px; font-style: italic; background: var(--bg2, #FAFAFC); border-radius: 8px; }
.ddm-loading { padding: 30px 20px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 12px; }
.ddm-alert { padding: 14px; background: rgba(226, 75, 74, .08); color: var(--sev-critical); border: 1px solid rgba(226, 75, 74, .18); border-radius: 8px; font-size: 12px; margin: 0 22px; }

.ddm-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.ddm-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.ddm-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.ddm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.ddm-btn-w { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); border-color: rgba(0, 0, 0, 0.10); }
.ddm-btn-w:hover { background: #F5F4F9; }
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
  .ddm-bord-row { grid-template-columns: 14px 1fr 70px; }
  .ddm-itm-status { display: none; }
}
</style>
