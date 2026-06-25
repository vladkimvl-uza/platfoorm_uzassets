<script setup lang="ts">
/**
 * DirectionDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Drill-down модалка для блока «По направлениям» (Row 3 left).
 *
 * Открывается кликом на строку направления (ESG, Цифровизация, и т.д.).
 * Структура:
 *   • Header: название направления + общий процент выполнения по задачам
 *   • 4 mini-KPI: компаний / проектов / задач / просрочено
 *   • Список компаний, отсортированных по числу проектов desc
 *     ◦ Каждая строка collapsible — клик раскрывает проекты и задачи этой
 *       компании в этом направлении
 *     ◦ Иконка статуса: ✓ done / ⏳ active|review / ⏰ overdue / ○ new|init
 *   • CTA → /projects?direction={code}
 *
 * Data: load on-mount through fetchDirectionDrill(code, year). Если данных
 * нет (404 или пустой ответ) — empty state.
 *
 * Pack 7.36
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";
import { SECTOR_COLORS } from "@/utils/sectorMeta";
import { useRouter } from "vue-router";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import {
  fetchDirectionDrill,
  type ExecDirectionDrillCompany,
  type ExecDirectionDrillProject,
  type ExecDirectionDrillResponse,
  type ExecDirectionDrillTask,
} from "@/api/executiveDashboard";

interface Props {
  directionCode: string;
  year: number;
  /** Fallback label/color if backend request fails — берём из ExecDirectionRow на странице */
  fallbackLabel?: string;
  fallbackColor?: string;
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();

const data = ref<ExecDirectionDrillResponse | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Какие компании раскрыты (по company_id)
const expanded = ref<Set<string>>(new Set());
function toggleCompany(id: string) {
  if (expanded.value.has(id)) expanded.value.delete(id);
  else expanded.value.add(id);
  // Force reactivity (Set is non-reactive in Vue 3 by default for .add/.delete)
  expanded.value = new Set(expanded.value);
}

// Сколько задач показывать по умолчанию в раскрытой компании
const TASKS_VISIBLE = 5;
const tasksFullyShown = ref<Set<string>>(new Set());
function showAllTasks(companyId: string) {
  tasksFullyShown.value.add(companyId);
  tasksFullyShown.value = new Set(tasksFullyShown.value);
}

// Коллапс списка компаний — показываем первые 5
const companiesExpanded = ref(false);
const VISIBLE_COMPANIES = 5;

const visibleCompanies = computed<ExecDirectionDrillCompany[]>(() => {
  if (!data.value) return [];
  if (companiesExpanded.value) return data.value.companies;
  return data.value.companies.slice(0, VISIBLE_COMPANIES);
});

const sectorColor = SECTOR_COLORS as Record<string, string>;

// ─── Status icon + label helpers ───
function statusIcon(item: ExecDirectionDrillProject | ExecDirectionDrillTask): {
  symbol: "check" | "clock" | "warn" | "circle";
  color: string;
  label: string;
} {
  if (item.is_overdue) {
    return { symbol: "warn", color: "#E24B4A", label: "просрочено" };
  }
  if (item.status === "done") {
    return { symbol: "check", color: "#1D9E75", label: "завершено" };
  }
  if (item.status === "active" || item.status === "review") {
    return { symbol: "clock", color: "#EF9F27", label: "в работе" };
  }
  return { symbol: "circle", color: "#888780", label: "не начат" };
}

function statusTextColor(item: ExecDirectionDrillProject | ExecDirectionDrillTask): string {
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
    data.value = await fetchDirectionDrill(props.directionCode, props.year);
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail
      || err?.message
      || "Не удалось загрузить данные направления";
  } finally {
    loading.value = false;
  }
}

// ─── Close + navigation ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

// a11y: фокус-трап диалога + возврат фокуса при закрытии
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function gotoProjects() {
  router.push({ name: "projects", query: { direction: props.directionCode } });
  close();
}
function gotoProject(projectId: string) {
  // project-detail page удалён — открываем проект in-place в списке «Проекты»
  if (projectId) router.push({ name: "projects", query: { open: projectId } });
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
const directionColor = computed(() => data.value?.direction_color || props.fallbackColor || "#7F77DD");
const directionLabel = computed(() => data.value?.direction_label || props.fallbackLabel || props.directionCode);

function formatDate(d: string | null): string {
  if (!d) return "—";
  return d; // ISO date is already readable, e.g. "2025-12-31"
}
function overdueLabel(p: ExecDirectionDrillTask | ExecDirectionDrillProject): string {
  if (!p.due_date) return "—";
  const today = new Date();
  const due = new Date(p.due_date);
  const days = Math.floor((today.getTime() - due.getTime()) / 86400000);
  if (days > 0) return `просрочено ${days} ${pluralDays(days)}`;
  return p.due_date;
}
function pluralDays(n: number): string {
  const m = n % 100;
  if (m >= 11 && m <= 14) return "дней";
  const r = n % 10;
  if (r === 1) return "день";
  if (r >= 2 && r <= 4) return "дня";
  return "дней";
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div class="ddm-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div ref="cardEl" tabindex="-1" class="ddm-card" :style="{ '--sc': directionColor }">
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
                <div class="ddm-h-l">Направление</div>
                <div class="ddm-h-title">{{ directionLabel }}</div>
                <div v-if="data" class="ddm-h-v">
                  <span class="num">{{ data.progress_pct }}</span>
                  <span class="unit">процентов выполнения · по задачам</span>
                </div>
                <span v-if="data" class="ddm-h-d">
                  {{ data.companies_count }} компаний · {{ data.projects_done }} из {{ data.projects_total }} проектов завершено · {{ data.tasks_done }} из {{ data.tasks_total }} задач
                </span>
              </div>
              <div v-if="data" class="ddm-h-right">
                <div>{{ data.assignees_count }} ответственных</div>
                <div v-if="data.tasks_overdue > 0" class="ddm-h-right-bad">
                  {{ data.tasks_overdue }} задач просрочено
                </div>
                <div v-else style="color: #1D9E75;">нет просроченных задач</div>
                <div class="ddm-h-year">{{ year }} финансовый год</div>
              </div>
            </div>
          </div>

          <!-- Loading -->
          <UzaStateBlock v-if="loading" class="ddm-sect" state="loading" text="Загрузка данных направления…" />

          <!-- Error -->
          <div v-else-if="errorMsg" class="ddm-sect">
            <UzaStateBlock state="error" variant="block" :text="errorMsg" />
          </div>

          <!-- Data: mini-KPIs + companies -->
          <template v-else-if="data">
            <div class="ddm-sect ddm-row" style="--si:1;">
              <div class="ddm-mini-grid">
                <div class="ddm-mini" style="--kc:#7F77DD; --ki:0;">
                  <div class="ddm-mk-l">Компаний с активностью</div>
                  <div class="ddm-mk-v">{{ data.companies_count }}<span class="ddm-mk-u">с проектами или задачами</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#1D9E75; --ki:1;">
                  <div class="ddm-mk-l">Проекты завершены</div>
                  <div class="ddm-mk-v">{{ data.projects_done }}<span class="ddm-mk-u">из {{ data.projects_total }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#EF9F27; --ki:2;">
                  <div class="ddm-mk-l">Задачи завершены</div>
                  <div class="ddm-mk-v">{{ data.tasks_done }}<span class="ddm-mk-u">из {{ data.tasks_total }}</span></div>
                </div>
                <div class="ddm-mini" style="--kc:#E24B4A; --ki:3;">
                  <div class="ddm-mk-l">Просрочено</div>
                  <div class="ddm-mk-v">{{ data.tasks_overdue }}<span class="ddm-mk-u">задач</span></div>
                </div>
              </div>
            </div>

            <!-- Companies list -->
            <div class="ddm-sect ddm-row" style="--si:2;">
              <div class="ddm-l-sec">
                <span>Компании в направлении · отсортированы по числу проектов</span>
                <span class="side">{{ data.companies_count }} компаний</span>
              </div>

              <UzaStateBlock
                v-if="!visibleCompanies.length"
                state="empty"
                variant="inline"
                text="Нет компаний с проектами или задачами в этом направлении"
              />

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
                    <span class="ddm-co-tick" :style="{ background: sectorColor[c.sector] || '#888780' }" />
                    <span class="ddm-co-name" :title="c.company_name">{{ c.company_name }}</span>
                    <span class="ddm-co-stat" :title="'Проекты: ' + c.projects_done + ' завершено из ' + c.projects_total">
                      <svg viewBox="0 0 14 14" class="ddm-co-stat-ico"><path d="M2.5 11V4l5-1.5 5 1.5v7M5 7h4M5 9.5h4"/></svg>
                      <span class="ddm-co-stat-num">{{ c.projects_done }}</span><span class="ddm-co-stat-tot">/{{ c.projects_total }}</span>
                    </span>
                    <span class="ddm-co-stat" :title="'Задачи: ' + c.tasks_done + ' завершено из ' + c.tasks_total">
                      <svg viewBox="0 0 14 14" class="ddm-co-stat-ico"><path d="M3 7l3 3 5-6"/></svg>
                      <span class="ddm-co-stat-num">{{ c.tasks_done }}</span><span class="ddm-co-stat-tot">/{{ c.tasks_total }}</span>
                    </span>
                    <span class="ddm-co-overdue" v-if="c.tasks_overdue > 0" :title="c.tasks_overdue + ' просроченных задач'">
                      ⚠ {{ c.tasks_overdue }}
                    </span>
                    <span v-else></span>
                  </div>

                  <div v-if="expanded.has(c.company_id)" class="ddm-co-body">
                    <!-- Projects -->
                    <div v-if="c.projects.length" class="ddm-co-section">
                      <div class="ddm-co-sub">
                        <span>Проекты · {{ c.projects_total }}</span>
                        <span class="ddm-co-sub-hint">клик — открыть проект</span>
                      </div>
                      <div
                        v-for="p in c.projects"
                        :key="p.id"
                        class="ddm-itm-row"
                        @click="gotoProject(p.id)"
                        :title="'Открыть проект «' + p.title + '»'"
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
                    <div v-else class="ddm-co-empty">Проектов в этом направлении нет</div>

                    <!-- Tasks -->
                    <div v-if="c.tasks.length" class="ddm-co-section">
                      <div class="ddm-co-sub">
                        <span>
                          Задачи · {{ c.tasks_total }}
                          <template v-if="!tasksFullyShown.has(c.company_id) && c.tasks.length > TASKS_VISIBLE">
                            · показано {{ TASKS_VISIBLE }} из {{ c.tasks.length }}
                          </template>
                        </span>
                        <span
                          v-if="!tasksFullyShown.has(c.company_id) && c.tasks.length > TASKS_VISIBLE"
                          class="ddm-co-sub-cta"
                          @click.stop="showAllTasks(c.company_id)"
                        >
                          показать все задачи →
                        </span>
                      </div>
                      <div
                        v-for="t in tasksFullyShown.has(c.company_id) ? c.tasks : c.tasks.slice(0, TASKS_VISIBLE)"
                        :key="t.id"
                        class="ddm-itm-row"
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
                    <div v-else class="ddm-co-empty">Задач в этом направлении нет</div>
                  </div>
                </div>
              </div>

              <!-- Show more companies -->
              <button
                v-if="data.companies_count > VISIBLE_COMPANIES && !companiesExpanded"
                class="ddm-collapse-btn"
                @click="companiesExpanded = true"
              >
                <svg viewBox="0 0 14 14" class="svg-ic" width="11" height="11" style="color:#7F77DD;"><path d="M3.5 5l3.5 3.5L10.5 5"/></svg>
                Показать ещё {{ data.companies_count - VISIBLE_COMPANIES }} компаний направления
              </button>
              <button
                v-else-if="data.companies_count > VISIBLE_COMPANIES"
                class="ddm-collapse-btn"
                @click="companiesExpanded = false"
              >
                <svg viewBox="0 0 14 14" class="svg-ic" width="11" height="11" style="color:#7F77DD; transform:rotate(180deg);"><path d="M3.5 5l3.5 3.5L10.5 5"/></svg>
                Свернуть · показано {{ data.companies_count }}
              </button>
            </div>
          </template>

          <!-- Footer -->
          <div class="ddm-ftr ddm-row" style="--si:3;">
            <button class="ddm-btn ddm-btn-g" @click="close">Закрыть</button>
            <button class="ddm-btn ddm-btn-p" @click="gotoProjects">
              Перейти к проектам направления
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
.ddm-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 760px; overflow: hidden; animation: ddmIn .55s var(--ease-standard) .08s both; }
.ddm-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: ddmStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.ddm-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: ddmShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.ddm-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.ddm-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.ddm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.ddm-row { animation: ddmUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.ddm-sect { padding: 14px 22px; }
.ddm-sect + .ddm-sect { padding-top: 0; }

.ddm-h-top { display: flex; justify-content: space-between; align-items: flex-end; gap: 18px; flex-wrap: wrap; }
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

.ddm-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.ddm-l-sec .side { font-size: 9.5px; color: #6B6A66; text-transform: none; letter-spacing: .02em; font-weight: 400; }

.ddm-co-list { display: flex; flex-direction: column; gap: 6px; }
.ddm-co { border: 1px solid rgba(0, 0, 0, .05); border-radius: 9px; background: var(--bg1, #fff); overflow: hidden; transition: all .14s; }
.ddm-co:hover { border-color: rgba(127, 119, 221, .20); }
.ddm-co.expanded { border-color: rgba(127, 119, 221, .30); box-shadow: 0 4px 12px rgba(127, 119, 221, .08); }
.ddm-co-hdr { display: grid; grid-template-columns: 18px 4px 1fr 70px 70px 50px; gap: 10px; align-items: center; padding: 9px 12px; cursor: pointer; font-size: 11.5px; }
.ddm-co-chev { color: var(--t3, var(--t-muted)); transition: transform .18s ease; display: flex; align-items: center; justify-content: center; }
.ddm-co.expanded .ddm-co-chev { transform: rotate(90deg); color: #7F77DD; }
.ddm-co-tick { width: 3px; height: 14px; border-radius: 1px; }
.ddm-co-name { color: var(--t1, #1E2A4A); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ddm-co-stat { display: flex; align-items: center; gap: 4px; font-size: 11px; font-feature-settings: "tnum"; }
.ddm-co-stat-ico { width: 11px; height: 11px; color: #6B6A66; stroke: currentColor; stroke-width: 1.5; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-co-stat-num { color: var(--t1, #1E2A4A); font-weight: 500; }
.ddm-co-stat-tot { color: var(--t3, var(--t-muted)); }
.ddm-co-overdue { font-size: 10px; color: var(--sev-critical); font-weight: 500; text-align: right; }
.ddm-co-body { padding: 0 12px 11px 34px; border-top: 1px solid rgba(0, 0, 0, .04); }
.ddm-co-section + .ddm-co-section { margin-top: 14px; }
.ddm-co-sub { font-size: 9.5px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin: 10px 0 6px; display: flex; justify-content: space-between; align-items: center; }
.ddm-co-sub-hint { font-size: 9px; color: #6B6A66; text-transform: none; letter-spacing: .02em; font-weight: 400; }
.ddm-co-sub-cta { font-size: 9.5px; color: var(--p-deep); text-transform: none; letter-spacing: .02em; font-weight: 500; cursor: pointer; }
.ddm-co-sub-cta:hover { text-decoration: underline; }
.ddm-co-empty { padding: 8px 0; font-size: 11px; color: #6B6A66; font-style: italic; }

.ddm-itm-row { display: grid; grid-template-columns: 14px 1fr 110px 80px; gap: 8px; align-items: center; padding: 4px 6px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.ddm-itm-row:hover { background: rgba(127, 119, 221, .04); }
.ddm-itm-ico { display: flex; align-items: center; justify-content: center; }
.svg-ic { stroke: currentColor; stroke-width: 1.9; fill: none; stroke-linecap: round; stroke-linejoin: round; }
.ddm-itm-name { color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 500; }
.ddm-itm-meta { color: var(--t3, var(--t-muted)); font-size: 10px; text-align: right; font-feature-settings: "tnum"; }
.ddm-itm-status { font-size: 10px; font-weight: 500; text-align: right; }

.ddm-collapse-btn { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 11px 14px; border-radius: 8px; border: 1px dashed rgba(127, 119, 221, .30); background: rgba(127, 119, 221, .04); color: var(--p-deep); font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; margin-top: 8px; }
.ddm-collapse-btn:hover { background: rgba(127, 119, 221, .08); }

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
