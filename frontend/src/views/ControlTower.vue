<script setup lang="ts">
/**
 * ControlTower.vue — «Прогресс-хаб · Обзор».
 *
 * Всегда показывает ЖИВОЕ текущее состояние (в фильтре период: год/квартал/
 * месяц): прогресс % + «должно быть к сегодня» % + план по кварталам +
 * компании. Плюс «Что изменилось» (было→стало) когда есть срезы.
 * Срезы можно фиксировать (вручную/авто) и удалять. Клик по компании →
 * модалка с лентой изменений.
 */
import { ref, computed, onMounted, onUnmounted, watch } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import EptLogo from "@/components/EptLogo.vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";

interface Quarter { q: number; label: string; plan_pct: number; fact_pct: number; }
interface Co { company_id: string; code: string; name: string; sector: string; color: string; badge: string; score: number | null; prog?: number; plan?: number; tasks_done: number; tasks_total: number; projects_done: number; projects_total: number; comments: number; tasks_done_snap?: number; projects_done_snap?: number; comments_snap?: number; }
interface Current { label: string; at: string; period: string; score: number; fact_now: number; plan_now: number; tasks_done: number; tasks_total: number; overdue: number; quarters: Quarter[]; companies: Co[]; snap_label?: string; snap_at?: string; }
interface CoDelta { company_id: string; code: string; name: string; sector: string; color: string; badge: string; from: number; to: number; delta: number; tasks_from: number; tasks_to: number; projects_from: number; projects_to: number; tasks_total: number; projects_total: number; comments_from: number; comments_to: number; projects_closed?: number; }
interface ClosedProject { company_id: string | null; company: string; sector: string | null; color: string; badge: string | null; num: string | null; title: string; }
interface Comparison { from: { label: string; at: string; score: number }; to: { label: string; at: string; score: number }; portfolio_delta: number | null; improved: CoDelta[]; fell: CoDelta[]; tasks_closed: number; comments_added: number; projects_closed?: number; closed_projects?: ClosedProject[]; }
interface SnapRef { id: string; label: string; at: string; score: number; }
interface Digest { year: number; period: string; available_years: number[]; has_baseline: boolean; current: Current; comparison: Comparison | null; snapshots: SnapRef[]; }
interface TrailItem { ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; is_critical: boolean; }

const toast = useToast();
const { confirmDialog } = useConfirm();
const digest = ref<Digest | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const freezing = ref(false);

const year = ref(new Date().getFullYear());
const period = ref("all");
// доступные годы — из бэкенда (data-driven), новый год появляется сам
const years = computed(() => digest.value?.available_years || [year.value]);
const PERIODS = [
  { v: "all", l: "Весь год" },
  { v: "q1", l: "I квартал" }, { v: "q2", l: "II квартал" }, { v: "q3", l: "III квартал" }, { v: "q4", l: "IV квартал" },
  { v: "m1", l: "Январь" }, { v: "m2", l: "Февраль" }, { v: "m3", l: "Март" }, { v: "m4", l: "Апрель" },
  { v: "m5", l: "Май" }, { v: "m6", l: "Июнь" }, { v: "m7", l: "Июль" }, { v: "m8", l: "Август" },
  { v: "m9", l: "Сентябрь" }, { v: "m10", l: "Октябрь" }, { v: "m11", l: "Ноябрь" }, { v: "m12", l: "Декабрь" },
];

const fromId = ref("");
const toId = ref("");
const showSnaps = ref(false);

async function load(silent = false) {
  if (!silent) { loading.value = true; error.value = null; }
  try {
    const params: any = { period: period.value };
    if (fromId.value) params.from_id = fromId.value;
    if (toId.value) params.to_id = toId.value;
    const { data } = await api.get<Digest>(`/monitoring/digest/${year.value}`, { params });
    digest.value = data;
  } catch (e: any) {
    if (!silent) error.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
  } finally { if (!silent) loading.value = false; }
}
onMounted(() => load());
watch([year, period, fromId, toId], () => load());

async function freeze() {
  if (freezing.value) return;
  freezing.value = true;
  try {
    const { data } = await api.post("/monitoring/snapshot", { year: year.value });
    toast.success(`Срез зафиксирован · прогресс ${data.score}%`, 3500);
    fromId.value = ""; toId.value = "";
    await load();
  } catch (e: any) {
    toast.error("Не удалось зафиксировать: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { freezing.value = false; }
}
async function delSnap(s: SnapRef) {
  if (!(await confirmDialog({ message: `Удалить срез «${s.label}»?`, danger: true }))) return;
  try {
    await api.delete(`/monitoring/snapshot/${s.id}`);
    toast.success("Срез удалён");
    if (fromId.value === s.id) fromId.value = "";
    if (toId.value === s.id) toId.value = "";
    await load();
  } catch (e: any) {
    toast.error("Не удалось удалить: " + (e?.response?.data?.detail || e?.message || ""));
  }
}

// ─── AI Executive Brief ───────────────────────────────────────
const brief = ref("");
const briefLoading = ref(false);
const briefError = ref("");
async function generateBrief() {
  if (briefLoading.value) return;
  briefLoading.value = true; briefError.value = "";
  try {
    const { data } = await api.post(`/monitoring/brief/${year.value}`, undefined, {
      params: { period: period.value },
    });
    brief.value = data.brief || "";
  } catch (e: any) {
    briefError.value = e?.response?.data?.detail || e?.message || "Ошибка генерации брифа";
  } finally { briefLoading.value = false; }
}
// лёгкий рендер: **жирный** + абзацы
function briefHtml(t: string): string {
  return t
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/^### (.+)$/gm, "<h4>$1</h4>")
    .replace(/^## (.+)$/gm, "<h4>$1</h4>")
    .replace(/\n{2,}/g, "</p><p>")
    .replace(/\n/g, "<br>");
}

// ─── helpers ───────────────────────────────────────────────────
// Цвет компании — по ОТСТАВАНИЮ от её плана-графика (fact − plan), а не по
// абсолюту: зелёный = в графике/опережение, янтарь = лёгкое отставание (≤15 пп),
// красный = заметное. Абсолютные пороги 80/60/40 красили весь портфель «критично».
function gapColor(fact: number | null | undefined, plan: number | null | undefined): string {
  if (fact == null) return "#94A3B8";
  const g = fact - (plan ?? 0);
  if (g >= 0) return "#1D9E75";
  if (g >= -15) return "#EF9F27";
  return "#E24B4A";
}
function coColor(c: { score: number | null; plan?: number }): string {
  return gapColor(c.score, c.plan);
}
// нейтральная «прогресс-интенсивность» (бренд-фиолет) — для накопительной динамики
// и снимков: это РОСТ во времени, а не оценка «плохо/хорошо».
const PROG = "#7C6FF7";
function progColor(_v?: number | null): string { return PROG; }
function behind(c: { score: number | null; plan?: number }): number {
  return (c.plan ?? 0) - (c.score ?? 0);  // насколько отстаёт от своего графика, пп
}
function fmtDate(s: string | undefined): string {
  if (!s) return "—"; if (s === "Сейчас") return s;
  return new Date(s).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}
const cur = computed(() => digest.value?.current);
const cmp = computed(() => digest.value?.comparison);
const hasSnap = computed(() => !!digest.value?.has_baseline);
// Дельта прогресса (пп) по компании из сравнения — для бейджа «+N пп» в таблице.
const coDeltaMap = computed<Record<string, number>>(() => {
  const m: Record<string, number> = {};
  for (const c of (cmp.value?.improved || [])) m[c.company_id] = c.delta;
  for (const c of (cmp.value?.fell || [])) m[c.company_id] = c.delta;
  return m;
});
// Сводный счётчик закрытых проектов в окне (для шапки «Улучшились»).
const projectsClosed = computed(() => cmp.value?.projects_closed ?? 0);
const closedProjects = computed(() => cmp.value?.closed_projects || []);
const gap = computed(() => cur.value ? cur.value.fact_now - cur.value.plan_now : 0); // факт − план(должно)

// ─── редизайн: статус, зоны риска, сортировка ───
const periodLabel = computed(() => PERIODS.find(p => p.v === period.value)?.l || "");
// Статус портфеля — по разрыву факт vs «должно быть к сегодня» (план), а не абсолют.
const statusClass = computed(() => {
  const c = cur.value;
  if (!c || c.fact_now == null) return "na";
  const g = c.fact_now - (c.plan_now ?? 0);
  if (g >= 0) return "ok"; if (g >= -10) return "good"; if (g >= -25) return "warn"; return "crit";
});
const statusWord = computed(() => {
  const c = cur.value;
  if (!c || c.fact_now == null) return "—";
  const g = c.fact_now - (c.plan_now ?? 0);
  if (g >= 0) return "в графике"; if (g >= -10) return "почти в графике"; if (g >= -25) return "отставание"; return "сильное отставание";
});
// «Зона риска» = заметно отстаёт от собственного графика (план − факт > 25 пп).
const RISK_BEHIND = 25;
const riskCount = computed(() => (cur.value?.companies || []).filter(c => behind(c) > RISK_BEHIND).length);
// сортировка компаний: худшие первыми (зоны риска видны сразу), null — в конец
const coSort = ref<"worst" | "best" | "name">("worst");
const sortedCompanies = computed(() => {
  const arr = [...(cur.value?.companies || [])];
  if (coSort.value === "name") return arr.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  return arr.sort((a, b) => {
    const sa = a.score == null ? 1000 : a.score;
    const sb = b.score == null ? 1000 : b.score;
    return coSort.value === "worst" ? sa - sb : sb - sa;
  });
});
function min100(v: number) { return Math.min(100, Math.max(0, v)); }

// ─── ДИНАМИКА: НАКОПИТЕЛЬНЫЙ прогресс по кварталам/месяцам ───
// % выполнено от ВСЕГО портфеля к концу периода (растёт); delta = прирост.
interface CumPeriod {
  key: number; label: string; label_full: string;
  cum_done: number; cum_pct: number; total: number;
  done_in_period: number; overdue: number; delta: number | null; is_future: boolean;
}
const granularity = ref<"quarter" | "month">("quarter");
const dynCompany = ref<string>("");   // "" = весь портфель, иначе company_id
const cumulative = ref<{ total: number; periods: CumPeriod[] } | null>(null);
const tlLoading = ref(false);
async function loadCumulative(silent = false) {
  if (!silent) tlLoading.value = true;
  try {
    const { data } = await api.get(`/monitoring/cumulative/${year.value}`, {
      params: { granularity: granularity.value, company_id: dynCompany.value || undefined },
    });
    cumulative.value = data;
  } catch (e: any) {
    if (!silent) { cumulative.value = null; toast.error("Не удалось загрузить динамику: " + (e?.response?.data?.detail || e?.message || "")); }
  } finally { if (!silent) tlLoading.value = false; }
}
const nowPeriodKey = computed(() => {
  const now = new Date();
  if (now.getFullYear() !== Number(year.value)) return -1;  // не текущий год — нет «сейчас»
  const m = now.getMonth() + 1;
  return granularity.value === "month" ? m : Math.ceil(m / 3);
});
const cumPeriods = computed(() =>
  (cumulative.value?.periods || [])
    .filter(p => !p.is_future)  // будущие периоды не показываем, пока не наступили
    .map(p => ({ ...p, isNow: p.key === nowPeriodKey.value })),
);
// масштаб баров — ЧЕСТНЫЙ, к 100% (раньше нормировали к локальному максимуму →
// линия «взлетала», хотя реальный % мог быть ничтожным).
const maxPct = computed(() => 100);
const dynName = computed(() => {
  if (!dynCompany.value) return "Весь портфель";
  return cur.value?.companies.find(c => c.company_id === dynCompany.value)?.name || "Компания";
});
// тренд: прирост за последний прошедший/текущий период
const trend = computed(() => {
  const past = cumPeriods.value.filter(p => !p.is_future);
  const last = past[past.length - 1];
  const d = last?.delta ?? 0;
  return { dir: (d > 0 ? "up" : d < 0 ? "down" : "flat") as "up" | "down" | "flat", delta: d };
});
const trendWord = computed(() => ({ up: "прогресс растёт", down: "прогресс снижается", flat: "без прироста" }[trend.value.dir]));

// Sparkline накопительной линии (растущая траектория)
const spark = computed(() => {
  const ps = cumPeriods.value;
  const n = ps.length;
  const mp = maxPct.value || 1;
  const pts = ps.map((p, i) => ({
    x: ((i + 0.5) / n) * 100,
    y: 100 - (p.cum_pct / mp) * 100,
    pct: p.cum_pct, isFuture: p.is_future, isNow: p.isNow,
  }));
  if (!pts.length) return { line: "", area: "", dots: [] as typeof pts, hasData: false };
  const line = pts.map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const area = `M${pts[0].x.toFixed(1)} 100 ` + pts.map(p => `L${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ") + ` L${pts[pts.length - 1].x.toFixed(1)} 100 Z`;
  return { line, area, dots: pts, hasData: true };
});

// ─── Дрилл периода: завершённые/просроченные задачи по направлениям ───
interface PTask { num: string | null; title: string; due_date: string | null; company: string; direction: string; }
const expandedPeriod = ref<number | null>(null);
const periodDetails = ref<{ completed: PTask[]; overdue: PTask[] } | null>(null);
const detailsLoading = ref(false);
async function togglePeriod(key: number) {
  const p = cumPeriods.value.find(x => x.key === key);
  if (p?.is_future) return;  // будущий период ещё не наступил — детали недоступны
  if (expandedPeriod.value === key) { expandedPeriod.value = null; return; }
  expandedPeriod.value = key;
  periodDetails.value = null; detailsLoading.value = true;
  try {
    const { data } = await api.get(`/monitoring/period-tasks/${year.value}`, {
      params: { period: key, granularity: granularity.value, company_id: dynCompany.value || undefined },
    });
    periodDetails.value = data;
  } catch (e: any) {
    periodDetails.value = { completed: [], overdue: [] };
    toast.error("Не удалось загрузить детали периода: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { detailsLoading.value = false; }
}
// группировка задач по направлению
function byDirection(tasks: PTask[]): { dir: string; items: PTask[] }[] {
  const m = new Map<string, PTask[]>();
  for (const t of tasks) { if (!m.has(t.direction)) m.set(t.direction, []); m.get(t.direction)!.push(t); }
  return [...m.entries()].map(([dir, items]) => ({ dir, items })).sort((a, b) => b.items.length - a.items.length);
}

onMounted(loadCumulative);
watch([year, granularity, dynCompany], () => { expandedPeriod.value = null; loadCumulative(); });

// Нормализуем выбранную компанию (Co из списка ИЛИ CoDelta из улучшились/провалились)
const modalNums = computed(() => {
  const c: any = modalCo.value;
  if (!c) return null;
  if (c.tasks_to !== undefined) {  // CoDelta
    return {
      tasks_now: c.tasks_to, tasks_snap: c.tasks_from, tasks_total: c.tasks_total,
      projects_now: c.projects_to, projects_snap: c.projects_from, projects_total: c.projects_total,
      comments_now: c.comments_to, comments_snap: c.comments_from,
    };
  }
  return {  // Co (live-список)
    tasks_now: c.tasks_done, tasks_snap: c.tasks_done_snap, tasks_total: c.tasks_total,
    projects_now: c.projects_done, projects_snap: c.projects_done_snap, projects_total: c.projects_total,
    comments_now: c.comments, comments_snap: c.comments_snap,
  };
});

// ─── модалка + trail ──────────────────────────────────────────
const modalCo = ref<any | null>(null);
const trail = ref<TrailItem[]>([]);
const trailLoading = ref(false);
const trailError = ref<string | null>(null);
async function openCompany(c: any) {
  modalCo.value = c;
  trail.value = []; trailError.value = null; trailLoading.value = true;
  try {
    const { data } = await api.get<{ items: TrailItem[] }>(`/companies/${c.code}/activity`, { params: { limit: 40, days: 120 } });
    trail.value = data.items || [];
  } catch (e: any) {
    trailError.value = e?.response?.status === 403 ? "Нет доступа к ленте" : "Не удалось загрузить ленту";
  } finally { trailLoading.value = false; }
}
function closeModal() { modalCo.value = null; }
function trailTime(ts: string): string { return new Date(ts).toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }); }
function actionRu(a: string): string { return ({ status_changed: "сменил статус", field_updated: "обновил", created: "создал", archived: "архивировал" } as any)[a] || a; }

// ─── Live: тихое авто-обновление (как в журнале аудита) ───
let pollTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (!document.hidden && !modalCo.value && !loading.value) { load(true); loadCumulative(true); }
  }, 30000);
});
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer); });
</script>

<template>
  <div class="ph">
    <!-- TOPBAR -->
    <div class="ph-top">
      <div class="ph-brand">
        <div class="ph-logo"><EptLogo :size="22" /></div>
        <div><div class="ph-eyebrow">ЕДИНЫЙ МОНИТОРИНГ</div><div class="ph-tt">Execution Summary</div></div>
      </div>
      <div class="ph-top-r">
        <select v-model="period" class="ph-sel">
          <option v-for="p in PERIODS" :key="p.v" :value="p.v">{{ p.l }}</option>
        </select>
        <select v-model.number="year" class="ph-sel"><option v-for="y in years" :key="y" :value="y">FY {{ y }}</option></select>
      </div>
    </div>

    <div class="ph-page">
      <UzaStateBlock v-if="loading" state="loading" variant="text" minHeight="180px" />
      <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" minHeight="180px" />

      <template v-else-if="cur">
        <!-- HERO: исполнение vs план -->
        <div class="ph-hero" :class="statusClass">
          <div class="ph-hero-l">
            <div class="ph-hero-eyebrow">Исполнение портфеля · {{ periodLabel }} · FY {{ year }}</div>
            <div class="ph-hero-num">{{ cur.fact_now }}<small>%</small>
              <span class="ph-hero-chip">{{ statusWord }}</span>
            </div>
            <div class="ph-hero-sub">
              взвешенный прогресс по статусам · {{ cur.tasks_done }} из {{ cur.tasks_total }} задач полностью завершено
              <span v-if="period === 'all'" class="ph-hero-trend" :class="trend.dir">
                {{ trend.dir === 'up' ? '↑' : trend.dir === 'down' ? '↓' : '→' }} {{ trendWord }}
              </span>
            </div>
          </div>
          <div class="ph-hero-r">
            <div class="ph-gap-head"><span>Должно быть к сегодня</span><b>{{ cur.plan_now }}%</b></div>
            <div class="ph-gap-bar">
              <div class="ph-gap-fill" :style="{ width: min100(cur.fact_now) + '%' }" />
              <div class="ph-gap-target" :style="{ left: min100(cur.plan_now) + '%' }"><i /><span>план</span></div>
            </div>
            <div class="ph-gap-foot">
              <span class="ph-gap-delta" :class="gap >= 0 ? 'ok' : 'bad'">
                {{ gap >= 0 ? '↑ опережение ' + gap + ' пп' : '↓ отставание ' + Math.abs(gap) + ' пп' }}
              </span>
              <span class="ph-gap-over"><b>{{ cur.overdue }}</b> просрочено</span>
            </div>
          </div>
        </div>

        <!-- KEY TILES -->
        <div class="ph-tiles">
          <div class="ph-tile"><div class="ph-tile-n">{{ cur.tasks_done }}<em>/{{ cur.tasks_total }}</em></div><div class="ph-tile-l">задач полностью завершено</div></div>
          <div class="ph-tile" :class="{ on: cur.overdue > 0 }" data-tone="danger"><div class="ph-tile-n">{{ cur.overdue }}</div><div class="ph-tile-l">просрочено сейчас</div></div>
          <div class="ph-tile" :class="{ on: riskCount > 0 }" data-tone="warn"><div class="ph-tile-n">{{ riskCount }}</div><div class="ph-tile-l">компаний в зоне риска</div></div>
          <div class="ph-tile"><div class="ph-tile-n">{{ cur.companies.length }}</div><div class="ph-tile-l">компаний в портфеле</div></div>
        </div>

        <!-- AI EXECUTIVE BRIEF -->
        <div class="ph-brief">
          <div class="ph-brief-h">
            <div class="ph-brief-tl">
              <span class="ph-brief-spark">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/><path d="M19 14l.7 1.8L21.5 16.5l-1.8.7L19 19l-.7-1.8L16.5 16.5l1.8-.7z"/></svg>
              </span>
              <div>
                <div class="ph-brief-eyebrow">AI EXECUTIVE BRIEF</div>
                <div class="ph-brief-sub">Сводка для Совета директоров на основе реальных цифр</div>
              </div>
            </div>
            <button class="ph-brief-btn" @click="generateBrief" :disabled="briefLoading">
              <svg v-if="!briefLoading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/></svg>
              {{ briefLoading ? 'Генерирую…' : (brief ? 'Обновить' : 'Сгенерировать') }}
            </button>
          </div>
          <div v-if="briefError" class="ph-brief-err">{{ briefError }}</div>
          <div v-else-if="briefLoading && !brief" class="ph-brief-empty">Анализирую исполнение портфеля…</div>
          <div v-else-if="brief" class="ph-brief-body" v-html="'<p>' + briefHtml(brief) + '</p>'"></div>
          <div v-else class="ph-brief-empty">Нажмите «Сгенерировать» — ИИ соберёт executive-бриф: статус, риски, траектория, рекомендации.</div>
        </div>

        <!-- ДИНАМИКА ИСПОЛНЕНИЯ (накопительная) -->
        <div class="ph-card">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">ДИНАМИКА ИСПОЛНЕНИЯ</span><span class="ph-card-cap">накопительный % выполнено от портфеля · стрелка — прирост за период · клик — детали</span></div>
            <div class="ph-dyn-ctl">
              <select v-model="dynCompany" class="ph-dyn-co">
                <option value="">Весь портфель</option>
                <option v-for="c in cur.companies" :key="c.company_id" :value="c.company_id">{{ c.name }}</option>
              </select>
              <div class="ph-sortsw">
                <button :class="{ on: granularity === 'quarter' }" @click="granularity = 'quarter'">Кварталы</button>
                <button :class="{ on: granularity === 'month' }" @click="granularity = 'month'">Месяцы</button>
              </div>
            </div>
          </div>

          <UzaStateBlock v-if="tlLoading" state="loading" variant="text" minHeight="120px" />
          <template v-else>
            <!-- SPARKLINE накопительной траектории -->
            <div v-if="spark.hasData" class="ph-spark">
              <svg class="ph-spark-svg" viewBox="0 0 100 100" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="ph-spark-g" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="#7C6FF7" stop-opacity="0.20" />
                    <stop offset="100%" stop-color="#7C6FF7" stop-opacity="0" />
                  </linearGradient>
                </defs>
                <path :d="spark.area" fill="url(#ph-spark-g)" />
                <path :d="spark.line" fill="none" stroke="#7C6FF7" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round" />
              </svg>
              <span v-for="(d, i) in spark.dots" :key="i" class="ph-spark-dot" :class="{ now: d.isNow, fut: d.isFuture }"
                    :style="{ left: d.x + '%', top: d.y + '%', background: progColor(d.pct) }" :title="d.pct + '%'" />
            </div>

            <div class="ph-dyn" :class="granularity">
              <div v-for="p in cumPeriods" :key="p.key" class="ph-dynp"
                   :class="{ now: p.isNow, fut: p.is_future, open: expandedPeriod === p.key }"
                   @click="togglePeriod(p.key)">
                <div class="ph-dynp-top">
                  <span v-if="p.is_future" class="ph-dynp-delta fl ph-dynp-first">не наступил</span>
                  <span v-else-if="p.delta != null" class="ph-dynp-delta" :class="p.delta > 0 ? 'up' : p.delta < 0 ? 'dn' : 'fl'">
                    {{ p.delta > 0 ? '↑+' + p.delta : p.delta < 0 ? '↓' + p.delta : '→ 0' }}<em>пп</em>
                  </span>
                  <span v-else class="ph-dynp-delta fl ph-dynp-first">старт</span>
                </div>
                <div class="ph-dynp-track">
                  <span class="ph-dynp-fill" :style="{ height: Math.max(4, Math.round(p.cum_pct / maxPct * 100)) + '%', background: progColor(p.cum_pct) }" />
                </div>
                <div class="ph-dynp-pct" :style="{ color: progColor(p.cum_pct) }">{{ p.cum_pct }}%</div>
                <div class="ph-dynp-cnt">{{ p.cum_done }}/{{ p.total }}</div>
                <div class="ph-dynp-sub"><span v-if="p.is_future" class="fu">—</span><template v-else><span class="ok">+{{ p.done_in_period }}</span><span v-if="p.overdue" class="od">{{ p.overdue }} проср.</span></template></div>
                <div class="ph-dynp-lbl" :class="{ now: p.isNow }">{{ granularity === 'quarter' ? p.label + ' кв' : p.label }}</div>
              </div>
            </div>

            <!-- ДЕТАЛИ ПЕРИОДА (дрилл по направлениям) -->
            <div v-if="expandedPeriod" class="ph-pdrill">
              <div v-if="detailsLoading" style="padding:14px 16px"><UzaSkeleton variant="rows" :rows="4" rowHeight="34px" /></div>
              <template v-else-if="periodDetails">
                <div class="ph-pdrill-cols">
                  <div class="ph-pdrill-col">
                    <div class="ph-pdrill-h ok">Завершено в периоде<span>{{ periodDetails.completed.length }}</span></div>
                    <div v-if="!periodDetails.completed.length" class="ph-pdrill-e">нет завершённых</div>
                    <div v-for="g in byDirection(periodDetails.completed)" :key="'c'+g.dir" class="ph-pdrill-g">
                      <div class="ph-pdrill-dir">{{ g.dir }}<span>{{ g.items.length }}</span></div>
                      <div v-for="(t,i) in g.items.slice(0,8)" :key="i" class="ph-pdrill-t">
                        <span class="ph-pdrill-bar ok"></span>
                        <span class="ph-pdrill-tt"><b v-if="t.num">{{ t.num }}</b> {{ t.title }}</span>
                        <span class="ph-pdrill-co">{{ t.company }}</span>
                      </div>
                      <div v-if="g.items.length > 8" class="ph-pdrill-more">+{{ g.items.length - 8 }} ещё</div>
                    </div>
                  </div>
                  <div class="ph-pdrill-col">
                    <div class="ph-pdrill-h od">Просрочено в периоде<span>{{ periodDetails.overdue.length }}</span></div>
                    <div v-if="!periodDetails.overdue.length" class="ph-pdrill-e">нет просроченных</div>
                    <div v-for="g in byDirection(periodDetails.overdue)" :key="'o'+g.dir" class="ph-pdrill-g">
                      <div class="ph-pdrill-dir">{{ g.dir }}<span>{{ g.items.length }}</span></div>
                      <div v-for="(t,i) in g.items.slice(0,8)" :key="i" class="ph-pdrill-t">
                        <span class="ph-pdrill-bar od"></span>
                        <span class="ph-pdrill-tt"><b v-if="t.num">{{ t.num }}</b> {{ t.title }}</span>
                        <span class="ph-pdrill-co">{{ t.company }}</span>
                      </div>
                      <div v-if="g.items.length > 8" class="ph-pdrill-more">+{{ g.items.length - 8 }} ещё</div>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </template>
          <div class="ph-dyn-foot">
            <span class="ph-dyn-trend" :class="trend.dir">
              {{ trend.dir === 'up' ? '↑' : trend.dir === 'down' ? '↓' : '→' }}
              {{ dynName }} · {{ trendWord }}<template v-if="trend.delta"> ({{ trend.delta > 0 ? '+' : '' }}{{ trend.delta }} пп за период)</template>
            </span>
            <span class="ph-dyn-hint">% = задач завершено накопительно / портфель (без ежемес./постоянных) · по дате завершения, для задач без неё — по плановому сроку · клик — детали</span>
          </div>
        </div>

        <!-- ЧТО ИЗМЕНИЛОСЬ (если есть срез) -->
        <div v-if="cmp" class="ph-card ph-change">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">ЧТО ИЗМЕНИЛОСЬ</span><span class="ph-card-cap">{{ fmtDate(cmp.from.at) }} → {{ fmtDate(cmp.to.at) }}</span></div>
            <div class="ph-change-delta" :class="(cmp.portfolio_delta||0) > 0 ? 'up' : (cmp.portfolio_delta||0) < 0 ? 'dn' : 'fl'">
              {{ cmp.from.score }}% → {{ cmp.to.score }}%
              <b>{{ (cmp.portfolio_delta||0) > 0 ? '+' : '' }}{{ cmp.portfolio_delta }} пп</b>
            </div>
          </div>
          <div class="ph-cols">
            <div class="ph-col">
              <div class="ph-col-h up">Улучшились<span>{{ cmp.improved.length }}</span></div>
              <div v-if="cmp.improved.length" class="ph-col-list">
                <div v-for="c in cmp.improved" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m">
                    <div class="ph-co-n">{{ c.name }}<span v-if="(c.projects_closed || 0) > 0" class="ph-pc-chip" :title="c.projects_closed + ' проект(ов) закрыто'">+{{ c.projects_closed }} пр.</span></div>
                    <div class="ph-co-s">{{ c.sector }}</div>
                  </div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: progColor(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d up">+{{ c.delta }}</div>
                </div>
              </div>
              <div v-else-if="!closedProjects.length" class="ph-col-e">Никто не вырос</div>

              <!-- Какие именно проекты закрыли в окне -->
              <div v-if="closedProjects.length" class="ph-closed">
                <div class="ph-closed-h">Закрыто проектов<span>{{ projectsClosed }}</span></div>
                <div v-for="(p, i) in closedProjects" :key="i" class="ph-closed-row">
                  <span class="ph-closed-dot" :style="{ background: p.color }" />
                  <span class="ph-closed-t"><b v-if="p.num">{{ p.num }}</b> {{ p.title }}</span>
                  <span class="ph-closed-co">{{ p.company }}</span>
                </div>
              </div>
            </div>
            <div class="ph-col">
              <div class="ph-col-h dn">Провалились<span>{{ cmp.fell.length }}</span></div>
              <div v-if="cmp.fell.length" class="ph-col-list">
                <div v-for="c in cmp.fell" :key="c.company_id" class="ph-co" @click="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m"><div class="ph-co-n">{{ c.name }}</div><div class="ph-co-s">{{ c.sector }}</div></div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: progColor(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d dn">{{ c.delta }}</div>
                </div>
              </div>
              <div v-else class="ph-col-e">Никто не провалился — хорошо</div>
            </div>
          </div>
          <div class="ph-change-meta">
            <span><b :style="{ color: cmp.tasks_closed>0 ? '#1D9E75' : '#1E2A4A' }">{{ cmp.tasks_closed>0 ? '+'+cmp.tasks_closed : cmp.tasks_closed }}</b> задач закрыто</span>
            <span class="dot">·</span>
            <span><b :style="{ color: projectsClosed>0 ? '#1D9E75' : '#1E2A4A' }">{{ projectsClosed>0 ? '+'+projectsClosed : 0 }}</b> проектов закрыто</span>
            <span class="dot">·</span>
            <span><b :style="{ color: cmp.comments_added ? '#7C6FF7' : '#1E2A4A' }">{{ cmp.comments_added }}</b> комментариев</span>
          </div>
        </div>
        <div v-else class="ph-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
          Зафиксируйте срез — и здесь появится «было → стало»: кто вырос, кто провалился. Срезы фиксируются и автоматически (раз в день).
        </div>

        <!-- КОМПАНИИ (live, отсортированы по риску) -->
        <div class="ph-card">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">ПО КОМПАНИЯМ</span><span class="ph-card-cap">{{ cur.companies.length }} · клик — лента изменений</span></div>
            <div class="ph-sortsw">
              <button :class="{ on: coSort === 'worst' }" @click="coSort = 'worst'">Сначала риск</button>
              <button :class="{ on: coSort === 'best' }" @click="coSort = 'best'">Лучшие</button>
              <button :class="{ on: coSort === 'name' }" @click="coSort = 'name'">По имени</button>
            </div>
          </div>
          <div class="ph-co-list2">
            <div v-for="c in sortedCompanies" :key="c.company_id" class="ph-co2"
                 :class="{ risk: behind(c) > RISK_BEHIND }" @click="openCompany(c)">
              <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
              <div class="ph-co-m">
                <div class="ph-co-n">{{ c.name }}<span v-if="behind(c) > RISK_BEHIND" class="ph-risk-tag">риск</span><span v-if="coDeltaMap[c.company_id]" class="ph-co-delta" :class="coDeltaMap[c.company_id] > 0 ? 'up' : 'dn'">{{ coDeltaMap[c.company_id] > 0 ? '+' : '' }}{{ coDeltaMap[c.company_id] }} пп</span></div>
                <div class="ph-co-nums">
                  <span>задачи <b>{{ c.tasks_done }}</b>/{{ c.tasks_total }}<i v-if="hasSnap && (c.tasks_done - (c.tasks_done_snap||0)) > 0" class="up">+{{ c.tasks_done - (c.tasks_done_snap||0) }}</i></span>
                  <span>проекты <b>{{ c.projects_done }}</b>/{{ c.projects_total }}<i v-if="hasSnap && (c.projects_done - (c.projects_done_snap||0)) > 0" class="up">+{{ c.projects_done - (c.projects_done_snap||0) }}</i></span>
                  <span v-if="c.comments"><b>{{ c.comments }}</b> комм.<i v-if="hasSnap && (c.comments - (c.comments_snap||0)) > 0" class="up">+{{ c.comments - (c.comments_snap||0) }}</i></span>
                </div>
              </div>
              <div class="ph-co-track"><span :style="{ width: Math.min(100, c.score || 0) + '%', background: coColor(c) }" /></div>
              <span class="ph-co-pct" :style="{ color: coColor(c) }">{{ c.score ?? '—' }}<template v-if="c.score!=null">%</template></span>
            </div>
          </div>
        </div>

        <!-- СРЕЗЫ (инструмент — внизу, сворачиваемо) -->
        <div class="ph-snapcard">
          <div class="ph-snapcard-h">
            <div class="ph-snapbar-l">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
              <span><b>{{ digest!.snapshots.length }}</b> срез{{ digest!.snapshots.length === 1 ? '' : digest!.snapshots.length < 5 && digest!.snapshots.length ? 'а' : 'ов' }} прогресса</span>
              <button v-if="digest!.snapshots.length" class="ph-link" :aria-expanded="showSnaps" @click="showSnaps = !showSnaps">{{ showSnaps ? 'скрыть' : 'управлять' }}</button>
            </div>
            <button class="ph-freeze sm" @click="freeze" :disabled="freezing">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
              {{ freezing ? "Фиксирую…" : "Зафиксировать срез" }}
            </button>
          </div>
          <div v-if="showSnaps && digest!.snapshots.length" class="ph-snaplist flat">
            <div v-for="s in digest!.snapshots" :key="s.id" class="ph-snaprow">
              <span class="ph-snap-dot" :style="{ background: progColor(s.score) }" />
              <span class="ph-snap-lbl">{{ s.label }}</span>
              <span class="ph-snap-score" :style="{ color: progColor(s.score) }">{{ s.score }}%</span>
              <span class="ph-snap-at">{{ fmtDate(s.at) }}</span>
              <button class="ph-snap-del" @click="delSnap(s)" title="Удалить срез">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- МОДАЛКА -->
    <Teleport to="body">
      <Transition name="ph-modal">
        <div v-if="modalCo" class="ph-back" @click.self="closeModal">
          <div class="ph-mod">
            <div class="ph-mod-head" :style="{ '--accent': modalCo.color }">
              <div class="cmpcell"><div class="av lg" :style="{ background: modalCo.color }">{{ modalCo.badge }}</div><div><div class="ph-mod-name">{{ modalCo.name }}</div><div class="ph-mod-sec">{{ modalCo.sector }}</div></div></div>
              <button class="ph-x" @click="closeModal"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
            </div>
            <div v-if="modalCo.delta != null" class="ph-mod-ab">
              <div class="ph-ab-c"><div class="ph-ab-l">Было</div><div class="ph-ab-v" :style="{ color: progColor(modalCo.from) }">{{ modalCo.from }}%</div></div>
              <div class="ph-ab-d" :class="modalCo.delta > 0 ? 'up' : modalCo.delta < 0 ? 'dn' : 'fl'"><div>{{ modalCo.delta > 0 ? '+' : '' }}{{ modalCo.delta }}</div><small>пп</small></div>
              <div class="ph-ab-c"><div class="ph-ab-l">Стало</div><div class="ph-ab-v" :style="{ color: progColor(modalCo.to) }">{{ modalCo.to }}%</div></div>
            </div>
            <div v-else class="ph-mod-ab single">
              <div class="ph-ab-c"><div class="ph-ab-l">Взвешенный прогресс</div><div class="ph-ab-v" :style="{ color: progColor(modalCo.score) }">{{ modalCo.score ?? '—' }}<template v-if="modalCo.score!=null">%</template></div></div>
            </div>

            <!-- конкретные цифры: завершено на момент среза vs сейчас -->
            <div v-if="modalNums" class="ph-mod-nums">
              <div class="ph-mn">
                <span class="ph-mn-l">Задачи завершено</span>
                <div class="ph-mn-v"><b>{{ modalNums.tasks_now }}</b><em>из {{ modalNums.tasks_total }}</em>
                  <i v-if="hasSnap && modalNums.tasks_snap != null">было {{ modalNums.tasks_snap }}<u v-if="modalNums.tasks_now - modalNums.tasks_snap > 0"> +{{ modalNums.tasks_now - modalNums.tasks_snap }}</u></i>
                </div>
              </div>
              <div class="ph-mn">
                <span class="ph-mn-l">Проекты завершено</span>
                <div class="ph-mn-v"><b>{{ modalNums.projects_now }}</b><em>из {{ modalNums.projects_total }}</em>
                  <i v-if="hasSnap && modalNums.projects_snap != null">было {{ modalNums.projects_snap }}<u v-if="modalNums.projects_now - modalNums.projects_snap > 0"> +{{ modalNums.projects_now - modalNums.projects_snap }}</u></i>
                </div>
              </div>
              <div class="ph-mn">
                <span class="ph-mn-l">Комментарии</span>
                <div class="ph-mn-v"><b>{{ modalNums.comments_now || 0 }}</b>
                  <i v-if="hasSnap && modalNums.comments_snap != null">было {{ modalNums.comments_snap }}<u v-if="(modalNums.comments_now||0) - modalNums.comments_snap > 0"> +{{ (modalNums.comments_now||0) - modalNums.comments_snap }}</u></i>
                </div>
              </div>
            </div>

            <div class="ph-trail-head">Лента изменений<span>последние 120 дней</span></div>
            <div class="ph-trail">
              <UzaStateBlock v-if="trailLoading" state="loading" variant="text" />
              <UzaStateBlock v-else-if="trailError" state="error" variant="block" :text="trailError" />
              <UzaStateBlock v-else-if="!trail.length" state="empty" variant="inline" text="Изменений нет." />
              <div v-for="(it,i) in trail" :key="i" class="ph-tr">
                <div class="ph-tr-rail"><div class="ph-tr-dot" :style="{ background: it.is_critical ? '#E24B4A' : '#7C6FF7' }" /></div>
                <div class="ph-tr-b">
                  <div class="ph-tr-l"><b>{{ it.actor }}</b> {{ actionRu(it.action) }}<template v-if="it.field"> <span class="fld">{{ it.field }}</span></template></div>
                  <div v-if="it.old_value || it.new_value" class="ph-tr-c"><span class="o">{{ it.old_value || '—' }}</span><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 12h14M13 6l6 6-6 6"/></svg><span class="n">{{ it.new_value || '—' }}</span></div>
                  <div class="ph-tr-meta">{{ it.title }}</div>
                </div>
                <div class="ph-tr-t">{{ trailTime(it.ts) }}</div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.ph { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); --ease-out:cubic-bezier(.22,1,.36,1); --sh-sm:0 1px 2px rgba(15,23,60,.05); --sh:0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); --sh-lg:0 24px 64px rgba(15,23,60,.2),0 8px 24px rgba(15,23,60,.08); color:#0F172A; }
.ph-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.ph-brand { display: flex; align-items: center; gap: 12px; }
.ph-logo { width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12); display: grid; place-items: center; }
.ph-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .12em; color: #9A8FFF; }
.ph-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.ph-top-r { margin-left: auto; display: flex; gap: 9px; }
.ph-sel { background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); color: rgba(255,255,255,.82); font: 600 12px inherit; padding: 8px 13px; border-radius: 10px; cursor: pointer; outline: none; }
.ph-sel option { color: #1E2A4A; }
.ph-page { padding: 18px 32px 80px; max-width: 1480px; margin: 0 auto; }

/* snapbar */
.ph-snapbar { display: flex; align-items: center; justify-content: space-between; padding: 11px 16px; background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 12px; box-shadow: var(--sh-sm); margin-bottom: 14px; }
.ph-snapbar-l { display: flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--t3); }
.ph-snapbar-l svg { color: var(--p-deep); } .ph-snapbar-l b { color: #1E2A4A; }
.ph-link { border: 0; background: transparent; color: var(--p-deep); font: 600 11.5px inherit; cursor: pointer; text-decoration: underline; }
.ph-freeze { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 15px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); transition: transform .16s var(--ease); }
.ph-freeze:hover:not(:disabled) { transform: translateY(-1px); } .ph-freeze:disabled { opacity: .6; cursor: default; }
.ph-snaplist { background: #fff; border: 1px solid var(--bd); border-radius: 12px; box-shadow: var(--sh-sm); margin-bottom: 14px; overflow: hidden; }
.ph-snaprow { display: grid; grid-template-columns: 10px 1fr auto auto 30px; align-items: center; gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--line); }
.ph-snaprow:last-child { border-bottom: 0; }
.ph-snap-dot { width: 9px; height: 9px; border-radius: 50%; }
.ph-snap-lbl { font-size: 12.5px; font-weight: 500; color: #1E2A4A; }
.ph-snap-score { font-size: 12.5px; font-weight: 700; font-variant-numeric: tabular-nums; }
.ph-snap-at { font-size: 11px; color: var(--t4); }
.ph-snap-del { border: 0; background: transparent; color: var(--t4); cursor: pointer; padding: 4px; border-radius: 7px; }
.ph-snap-del:hover { color: #E24B4A; background: #FCE7E7; }

/* ─── HERO ─── */
.ph-hero { display: grid; grid-template-columns: 1fr 1.5fr; gap: 0; border-radius: 18px; overflow: hidden; margin-bottom: 14px; border: 1px solid var(--bd); box-shadow: var(--sh); position: relative; }
.ph-hero::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 4px; }
.ph-hero.crit::before { background: #E24B4A; } .ph-hero.warn::before { background: #EF9F27; } .ph-hero.good::before { background: #7C6FF7; } .ph-hero.ok::before { background: #1D9E75; } .ph-hero.na::before { background: #94A3B8; }
.ph-hero-l { padding: 22px 28px; background: linear-gradient(135deg,#fff,#FBFAFF); border-right: 1px solid var(--line); }
.ph-hero.crit .ph-hero-l { background: linear-gradient(135deg,#FFF6F6,#FFF0F0); }
.ph-hero.warn .ph-hero-l { background: linear-gradient(135deg,#FFFBF3,#FEF6E9); }
.ph-hero-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-hero-num { font-size: 60px; font-weight: 400; letter-spacing: -.045em; line-height: 1; margin-top: 10px; font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 12px; }
.ph-hero.crit .ph-hero-num { color: #E24B4A; } .ph-hero.warn .ph-hero-num { color: #C77A0A; } .ph-hero.good .ph-hero-num { color: #6C5CE7; } .ph-hero.ok .ph-hero-num { color: #1D9E75; } .ph-hero.na .ph-hero-num { color: #64748B; }
.ph-hero-num small { font-size: 26px; }
.ph-hero-chip { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; letter-spacing: .01em; align-self: center; }
.ph-hero.crit .ph-hero-chip { background: rgba(226,75,74,.12); color: #C0392B; } .ph-hero.warn .ph-hero-chip { background: rgba(239,159,39,.14); color: #C77A0A; } .ph-hero.good .ph-hero-chip { background: rgba(124,111,247,.12); color: #534AB7; } .ph-hero.ok .ph-hero-chip { background: rgba(29,158,117,.12); color: #0F6E56; } .ph-hero.na .ph-hero-chip { background: #F1F2F6; color: #64748B; }
.ph-hero-sub { font-size: 12.5px; color: var(--t3); margin-top: 12px; }
.ph-hero-r { padding: 22px 28px; display: flex; flex-direction: column; justify-content: center; gap: 12px; background: #fff; }
.ph-gap-head { display: flex; align-items: baseline; justify-content: space-between; }
.ph-gap-head span { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3); }
.ph-gap-head b { font-size: 22px; font-weight: 700; color: #1E2A4A; font-variant-numeric: tabular-nums; }
.ph-gap-bar { position: relative; height: 12px; border-radius: 7px; background: #F0F1F6; }
.ph-gap-fill { position: absolute; left: 0; top: 0; height: 100%; border-radius: 7px; background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%); transition: width .8s var(--ease-out); }
.ph-hero.crit .ph-gap-fill { background-color: #E2807F; } .ph-hero.warn .ph-gap-fill { background-color: #EFB373; } .ph-hero.good .ph-gap-fill { background-color: #7C6FF7; } .ph-hero.ok .ph-gap-fill { background-color: #5DC093; } .ph-hero.na .ph-gap-fill { background-color: #B8B7B0; }
.ph-gap-target { position: absolute; top: -5px; bottom: -5px; width: 0; z-index: 2; transition: left .8s var(--ease-out); }
.ph-gap-target i { position: absolute; left: -1.5px; top: 0; bottom: 0; width: 3px; border-radius: 2px; background: #1E2A4A; }
.ph-gap-target span { position: absolute; top: -16px; left: 50%; transform: translateX(-50%); font-size: 9px; font-weight: 600; color: #1E2A4A; white-space: nowrap; }
.ph-gap-foot { display: flex; align-items: center; justify-content: space-between; }
.ph-gap-delta { font-size: 13px; font-weight: 700; } .ph-gap-delta.ok { color: #0F6E56; } .ph-gap-delta.bad { color: #B23434; }
.ph-gap-over { font-size: 12px; color: var(--t3); } .ph-gap-over b { color: #E24B4A; font-weight: 700; font-variant-numeric: tabular-nums; }

/* ─── TILES ─── */
.ph-tiles { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 16px; }
.ph-tile { background: #fff; border: 1px solid var(--bd); border-radius: 14px; padding: 16px 18px; box-shadow: var(--sh-sm); position: relative; overflow: hidden; }
.ph-tile::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: #E2E5EE; }
.ph-tile[data-tone="danger"].on::after { background: #E24B4A; } .ph-tile[data-tone="warn"].on::after { background: #EF9F27; }
.ph-tile-n { font-size: 26px; font-weight: 400; letter-spacing: -.03em; color: #1E2A4A; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-tile-n em { font-size: 15px; font-weight: 600; color: var(--t4); font-style: normal; }
.ph-tile[data-tone="danger"].on .ph-tile-n { color: #E24B4A; } .ph-tile[data-tone="warn"].on .ph-tile-n { color: #C77A0A; }
.ph-tile-l { font-size: 11px; font-weight: 500; color: var(--t3); margin-top: 8px; }

/* ─── sort switch ─── */
.ph-sortsw { display: inline-flex; background: #F1F2F6; border-radius: 9px; padding: 2px; }
.ph-sortsw button { border: 0; background: transparent; font: 600 11px inherit; color: var(--t3); padding: 5px 11px; border-radius: 7px; cursor: pointer; transition: all .14s; }
.ph-sortsw button.on { background: #fff; color: var(--p-deep); box-shadow: var(--sh-sm); }
.ph-risk-tag { margin-left: 7px; font-size: 9px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: #C0392B; background: rgba(226,75,74,.10); padding: 1px 6px; border-radius: 5px; vertical-align: middle; }
.ph-co2.risk { background: linear-gradient(90deg, rgba(226,75,74,.035), transparent 40%); }

/* ─── snapshot card (bottom) ─── */
.ph-snapcard { background: #fff; border: 1px solid var(--bd); border-radius: 14px; box-shadow: var(--sh-sm); margin-bottom: 16px; overflow: hidden; }
.ph-snapcard-h { display: flex; align-items: center; justify-content: space-between; padding: 13px 18px; }
.ph-freeze.sm { padding: 8px 13px; box-shadow: 0 3px 12px rgba(108,92,231,.26); }
.ph-snaplist.flat { border: 0; border-top: 1px solid var(--line); border-radius: 0; box-shadow: none; margin: 0; }

/* verdict */
.ph-verdict { display: grid; grid-template-columns: 1fr 1.4fr; gap: 0; background: linear-gradient(135deg,#fff,#FBFAFF); border: 1px solid var(--bd); border-radius: 16px; box-shadow: var(--sh); overflow: hidden; margin-bottom: 16px; }
.ph-vd-main { padding: 22px 26px; border-right: 1px solid var(--line); }
.ph-vd-label { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-vd-num { font-size: 56px; font-weight: 700; letter-spacing: -.045em; line-height: 1; margin-top: 8px; font-variant-numeric: tabular-nums; }
.ph-vd-num small { font-size: 24px; }
.ph-vd-sub { font-size: 12px; color: var(--t3); margin-top: 8px; }
.ph-vd-plan { padding: 22px 26px; display: flex; flex-direction: column; justify-content: center; gap: 10px; }
.ph-plan-row { display: flex; align-items: baseline; justify-content: space-between; }
.ph-plan-cap { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3); }
.ph-plan-val { font-size: 22px; font-weight: 700; color: #1E2A4A; font-variant-numeric: tabular-nums; }
.ph-plan-bar { position: relative; height: 10px; border-radius: 6px; background: #F0F1F6; overflow: visible; }
.ph-plan-fact { position: absolute; left: 0; top: 0; height: 100%; border-radius: 6px; transition: width .7s var(--ease-out); }
.ph-plan-target { position: absolute; top: -3px; bottom: -3px; width: 3px; border-radius: 2px; background: #1E2A4A; transition: left .7s var(--ease-out); z-index: 2; }
.ph-plan-gap { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 700; }
.ph-plan-gap.ok { color: #0F6E56; } .ph-plan-gap.bad { color: #B23434; }
.ph-plan-status { margin-left: auto; font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 9px; }
.ph-plan-over { font-size: 11.5px; color: var(--t3); } .ph-plan-over b { font-variant-numeric: tabular-nums; }

/* cards */
.ph-card { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: var(--sh); margin-bottom: 16px; overflow: hidden; }
.ph-card-h { display: flex; align-items: center; justify-content: space-between; padding: 15px 20px; border-bottom: 1px solid var(--line); }
.ph-eyebrow2 { font-size: 10px; font-weight: 600; letter-spacing: .07em; color: var(--p-deep); }
.ph-card-cap { font-size: 11px; color: var(--t4); margin-left: 10px; }

/* AI Brief */
.ph-brief { margin-bottom: 16px; border-radius: 16px; border: 1px solid rgba(124,111,247,.22); box-shadow: var(--sh); overflow: hidden; background: linear-gradient(135deg, #FBFAFF 0%, #F4F2FF 100%); }
.ph-brief-h { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 16px 20px; border-bottom: 1px solid rgba(124,111,247,.14); }
.ph-brief-tl { display: flex; align-items: center; gap: 12px; }
.ph-brief-spark { width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center; color: #fff; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); box-shadow: 0 4px 14px rgba(108,92,231,.35); flex-shrink: 0; }
.ph-brief-eyebrow { font-size: 10px; font-weight: 700; letter-spacing: .08em; color: var(--p-deep); }
.ph-brief-sub { font-size: 11.5px; color: var(--t3); margin-top: 2px; }
.ph-brief-btn { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 16px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); transition: transform .16s var(--ease); flex-shrink: 0; }
.ph-brief-btn:hover:not(:disabled) { transform: translateY(-1px); } .ph-brief-btn:disabled { opacity: .65; cursor: default; }
.ph-brief-err { padding: 16px 20px; color: #B23434; font-size: 12.5px; }
.ph-brief-empty { padding: 20px; color: var(--t3); font-size: 12.5px; text-align: center; }
.ph-brief-body { padding: 18px 22px; font-size: 13px; line-height: 1.65; color: #28324A; background: #fff; }
.ph-brief-body :deep(p) { margin: 0 0 12px; } .ph-brief-body :deep(p:last-child) { margin-bottom: 0; }
.ph-brief-body :deep(b) { color: #1E2A4A; font-weight: 600; }
.ph-brief-body :deep(h4) { font-size: 12.5px; font-weight: 700; color: var(--p-deep); margin: 16px 0 7px; text-transform: none; }

/* quarters */
.ph-qs { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; padding: 18px 24px 8px; }
.ph-q { display: flex; flex-direction: column; align-items: center; }
.ph-q-bars { position: relative; width: 100%; max-width: 80px; height: 110px; display: flex; align-items: flex-end; justify-content: center; gap: 6px; }
.ph-q-plan { width: 22px; border-radius: 6px 6px 3px 3px; background: repeating-linear-gradient(135deg,#D7D9E0 0 4px,#EAEBEF 4px 8px); transition: height .7s var(--ease-out); }
.ph-q-fact { width: 22px; border-radius: 6px 6px 3px 3px; transition: height .7s var(--ease-out); }
.ph-q-vals { margin-top: 8px; font-size: 11.5px; font-variant-numeric: tabular-nums; } .ph-q-vals b { font-weight: 700; } .ph-q-vals span { color: var(--t4); }
.ph-q-lbl { font-size: 11px; font-weight: 500; color: var(--t3); margin-top: 2px; }
.ph-q-legend { display: flex; gap: 18px; padding: 10px 24px 16px; font-size: 11px; color: var(--t3); }
.ph-q-legend span { display: inline-flex; align-items: center; gap: 6px; }
.ph-q-legend i { width: 11px; height: 11px; border-radius: 3px; } .lg-plan { background: repeating-linear-gradient(135deg,#D7D9E0 0 3px,#EAEBEF 3px 6px); } .lg-fact { background: #7C6FF7; }

/* ─── ДИНАМИКА ─── */
.ph-hero-trend { margin-left: 10px; font-size: 11px; font-weight: 600; padding: 2px 9px; border-radius: 999px; }
.ph-hero-trend.up { color: #0F6E56; background: rgba(29,158,117,.10); } .ph-hero-trend.down { color: #B23434; background: rgba(226,75,74,.10); } .ph-hero-trend.flat { color: var(--t3); background: #F1F2F6; }
.ph-spark { position: relative; height: 48px; margin: 16px 24px 0; }
.ph-spark-svg { width: 100%; height: 100%; display: block; overflow: visible; }
.ph-spark-dot { position: absolute; width: 7px; height: 7px; border-radius: 50%; transform: translate(-50%,-50%); box-shadow: 0 0 0 2px #fff; transition: left .6s var(--ease-out), top .6s var(--ease-out); }
.ph-spark-dot.now { width: 10px; height: 10px; box-shadow: 0 0 0 2px #fff, 0 0 0 4px rgba(124,111,247,.25); }
.ph-dyn { display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; padding: 14px 24px 8px; }
.ph-dyn.month { grid-template-columns: repeat(12,minmax(56px,1fr)); gap: 6px; overflow-x: auto; padding-bottom: 12px; }
.ph-dynp { display: flex; flex-direction: column; align-items: center; gap: 6px; border-radius: 12px; padding: 8px 6px 10px; transition: background .14s, box-shadow .14s; cursor: pointer; }
.ph-dynp:hover { background: rgba(124,111,247,.05); }
.ph-dynp.now { background: rgba(124,111,247,.06); box-shadow: inset 0 0 0 1px rgba(124,111,247,.22); }
.ph-dynp.open { background: rgba(124,111,247,.10); box-shadow: inset 0 0 0 1.5px rgba(124,111,247,.4); }
.ph-dynp.fut { opacity: .45; cursor: default; }
.ph-dynp.fut:hover { background: transparent; }
.ph-dynp-sub .fu { color: var(--t4); font-weight: 500; }
.ph-dynp-sub { display: flex; gap: 8px; font-size: 9.5px; font-variant-numeric: tabular-nums; }
.ph-dynp-sub .ok { color: #0F6E56; font-weight: 600; }
.ph-dynp-sub .od { color: #B23434; font-weight: 600; }
.ph-dyn-ctl { display: flex; align-items: center; gap: 9px; }
.ph-dyn-co { font: 600 12px inherit; color: #1E2A4A; background: #fff; border: 1px solid var(--bd); border-radius: 9px; padding: 6px 10px; cursor: pointer; outline: none; max-width: 200px; }
.ph-spark-dot.fut { opacity: .45; }

/* Дрилл периода */
.ph-pdrill { padding: 4px 18px 14px; }
.ph-pdrill-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.ph-pdrill-col { background: #FAFAFD; border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; min-height: 60px; }
.ph-pdrill-h { display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 600; padding-bottom: 8px; border-bottom: 1px solid var(--line); margin-bottom: 8px; }
.ph-pdrill-h.ok { color: #0F6E56; } .ph-pdrill-h.od { color: #B23434; }
.ph-pdrill-h span { margin-left: auto; font-size: 10.5px; background: #fff; border: 1px solid var(--line); border-radius: 8px; padding: 1px 9px; color: var(--t3); }
.ph-pdrill-e { font-size: 11.5px; color: var(--t4); padding: 8px 2px; }
.ph-pdrill-g { margin-bottom: 9px; }
.ph-pdrill-dir { display: flex; align-items: center; gap: 7px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep); margin: 6px 0 4px; }
.ph-pdrill-dir span { font-size: 9.5px; color: var(--t4); background: rgba(124,111,247,.10); border-radius: 7px; padding: 0 6px; }
.ph-pdrill-t { display: flex; align-items: center; gap: 8px; padding: 4px 0; }
.ph-pdrill-bar { width: 3px; height: 16px; border-radius: 2px; flex-shrink: 0; } .ph-pdrill-bar.ok { background: #5DC093; } .ph-pdrill-bar.od { background: #E2807F; }
.ph-pdrill-tt { flex: 1; min-width: 0; font-size: 11.5px; color: #28324A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .ph-pdrill-tt b { color: var(--t3); font-weight: 600; margin-right: 4px; }
.ph-pdrill-co { font-size: 10px; color: var(--t4); white-space: nowrap; flex-shrink: 0; max-width: 110px; overflow: hidden; text-overflow: ellipsis; }
.ph-pdrill-more { font-size: 10.5px; color: var(--p-deep); padding: 3px 0 0 11px; }
.ph-dynp-top { height: 20px; display: flex; align-items: center; }
.ph-dynp-delta { font-size: 11px; font-weight: 700; padding: 2px 7px; border-radius: 999px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ph-dynp-delta em { font-style: normal; font-weight: 500; font-size: 8.5px; opacity: .7; margin-left: 2px; }
.ph-dynp-delta.up { color: #0F6E56; background: #E3F8EE; } .ph-dynp-delta.dn { color: #B23434; background: #FCE7E7; } .ph-dynp-delta.fl { color: var(--t3); background: #F1F2F6; }
.ph-dynp-first { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.ph-dynp-track { width: 100%; max-width: 64px; height: 92px; background: #F4F5F9; border-radius: 8px; display: flex; align-items: flex-end; overflow: hidden; }
.ph-dynp-fill { width: 100%; border-radius: 7px 7px 0 0; transition: height .7s var(--ease-out); }
.ph-dynp-pct { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.ph-dyn.month .ph-dynp-pct { font-size: 13px; }
.ph-dynp-cnt { font-size: 10px; color: var(--t4); font-variant-numeric: tabular-nums; }
.ph-dynp-lbl { font-size: 11px; font-weight: 500; color: var(--t3); }
.ph-dyn.month .ph-dynp-lbl { font-size: 10px; }
.ph-dynp-lbl.now { color: var(--p-deep); font-weight: 700; }
.ph-dyn-foot { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 24px 16px; flex-wrap: wrap; }
.ph-dyn-trend { font-size: 13px; font-weight: 700; } .ph-dyn-trend.up { color: #0F6E56; } .ph-dyn-trend.down { color: #B23434; } .ph-dyn-trend.flat { color: var(--t3); }
.ph-dyn-hint { font-size: 10.5px; color: var(--t4); margin-left: auto; }

/* change */
.ph-change-delta { font-size: 13px; font-weight: 500; color: var(--t3); font-variant-numeric: tabular-nums; }
.ph-change-delta b { margin-left: 8px; padding: 3px 9px; border-radius: 8px; }
.ph-change-delta.up b { background: #E3F8EE; color: #0F6E56; } .ph-change-delta.dn b { background: #FCE7E7; color: #B23434; } .ph-change-delta.fl b { background: #F1F2F6; color: var(--t3); }
.ph-cols { display: grid; grid-template-columns: 1fr 1fr; }
.ph-col { border-right: 1px solid var(--line); } .ph-col:last-child { border-right: 0; }
.ph-col-h { display: flex; align-items: center; gap: 8px; padding: 12px 18px; font-size: 12px; font-weight: 600; border-bottom: 1px solid var(--line); }
.ph-col-h.up { color: #0F6E56; } .ph-col-h.dn { color: #B23434; }
.ph-col-h span { margin-left: auto; font-size: 11px; background: #F1F2F6; color: var(--t3); padding: 2px 9px; border-radius: 8px; }
.ph-co { display: grid; grid-template-columns: 28px 1fr auto auto; align-items: center; gap: 10px; padding: 9px 18px; cursor: pointer; transition: background .12s; }
.ph-co:hover { background: #FAFAFF; }
.av { width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; font-size: 8.5px; font-weight: 700; color: #fff; box-shadow: inset 0 1px 1px rgba(255,255,255,.25),0 2px 6px rgba(15,23,60,.12); }
.av.lg { width: 44px; height: 44px; border-radius: 13px; font-size: 13px; }
.ph-co-m { min-width: 0; } .ph-co-n { font-size: 12px; font-weight: 500; color: #1E2A4A; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .ph-co-s { font-size: 10px; color: var(--t4); }
.ph-co-p { display: flex; align-items: baseline; gap: 6px; font-variant-numeric: tabular-nums; } .ph-co-p .f { font-size: 10.5px; color: var(--t4); text-decoration: line-through; } .ph-co-p .t { font-size: 13px; font-weight: 700; }
.ph-co-d { font-size: 12.5px; font-weight: 700; min-width: 32px; text-align: right; font-variant-numeric: tabular-nums; } .ph-co-d.up { color: #0F6E56; } .ph-co-d.dn { color: #B23434; }
.ph-col-e { padding: 24px; text-align: center; color: var(--t4); font-size: 12px; }
.ph-change-meta { display: flex; align-items: center; gap: 10px; padding: 13px 20px; border-top: 1px solid var(--line); font-size: 12.5px; color: var(--t3); } .ph-change-meta b { font-variant-numeric: tabular-nums; } .ph-change-meta .dot { color: var(--t4); }

.ph-hint { display: flex; align-items: center; gap: 9px; margin-bottom: 16px; padding: 13px 16px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.16); border-radius: 12px; font-size: 12px; color: var(--t3); } .ph-hint svg { color: var(--p); flex-shrink: 0; }

/* companies live */
.ph-co-list2 { padding: 4px 0; }
.ph-co2 { display: grid; grid-template-columns: 30px 1fr 130px 46px; align-items: center; gap: 14px; padding: 11px 20px; border-bottom: 1px solid var(--line); cursor: pointer; transition: background .12s; }
.ph-co-nums { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 3px; font-size: 10.5px; color: var(--t4); }
.ph-co-nums b { color: #475569; font-weight: 600; font-variant-numeric: tabular-nums; }
.ph-co-nums i { font-style: normal; color: #0F6E56; font-weight: 600; margin-left: 3px; }
/* modal concrete numbers */
.ph-mod-nums { margin: 14px 22px 0; border: 1px solid var(--line); border-radius: 13px; overflow: hidden; }
.ph-mn { display: flex; align-items: center; justify-content: space-between; padding: 11px 16px; border-bottom: 1px solid var(--line); }
.ph-mn:last-child { border-bottom: 0; }
.ph-mn-l { font-size: 11.5px; color: var(--t3); }
.ph-mn-v { display: flex; align-items: baseline; gap: 6px; font-variant-numeric: tabular-nums; }
.ph-mn-v b { font-size: 18px; font-weight: 700; color: #1E2A4A; }
.ph-mn-v em { font-size: 11px; color: var(--t4); font-style: normal; }
.ph-mn-v i { font-size: 10.5px; color: var(--t4); font-style: normal; margin-left: 6px; }
.ph-mn-v i u { color: #0F6E56; font-weight: 600; text-decoration: none; }
.ph-co2:hover { background: #FAFAFF; } .ph-co2:last-child { border-bottom: 0; }
.ph-co-track { height: 7px; border-radius: 5px; background: #F0F1F6; overflow: hidden; } .ph-co-track > span { display: block; height: 100%; border-radius: 5px; transition: width .7s var(--ease-out); }
.ph-co-pct { font-size: 13px; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }
.ph-co-cnt { font-size: 10.5px; color: var(--t4); text-align: right; font-variant-numeric: tabular-nums; }

/* modal */
.ph-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: var(--z-overlay, 9000); display: grid; place-items: center; padding: 24px; }
.ph-mod { width: min(580px,100%); max-height: calc(100dvh - 48px); background: #fff; border-radius: 18px; box-shadow: var(--sh-lg); display: flex; flex-direction: column; overflow: hidden; }
.ph-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 22px; border-bottom: 1px solid var(--line); background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 9%, #fff), #fff 70%); }
.cmpcell { display: flex; align-items: center; gap: 12px; }
.ph-mod-name { font-size: 16px; font-weight: 600; color: #1E2A4A; } .ph-mod-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.ph-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; } .ph-x:hover { background: rgba(127,119,221,.12); color: var(--p-deep); }
.ph-mod-ab { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; padding: 18px 22px; margin: 16px 22px 0; background: #FAFAFD; border: 1px solid var(--line); border-radius: 13px; }
.ph-mod-ab.single { grid-template-columns: 1fr; }
.ph-ab-c { text-align: center; } .ph-ab-l { font-size: 9.5px; text-transform: uppercase; letter-spacing: .05em; color: var(--t4); } .ph-ab-l2 { font-size: 11px; color: var(--t3); margin-top: 4px; }
.ph-ab-v { font-size: 34px; font-weight: 700; letter-spacing: -.035em; margin-top: 5px; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-ab-d { text-align: center; font-size: 19px; font-weight: 700; padding: 8px 14px; border-radius: 11px; font-variant-numeric: tabular-nums; } .ph-ab-d.up { background: #E3F8EE; color: #0F6E56; } .ph-ab-d.dn { background: #FCE7E7; color: #B23434; } .ph-ab-d.fl { background: #F1F2F6; color: var(--t3); } .ph-ab-d small { display: block; font-size: 8.5px; text-transform: uppercase; opacity: .7; }
.ph-trail-head { display: flex; align-items: baseline; justify-content: space-between; padding: 18px 22px 10px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); } .ph-trail-head span { font-size: 10px; font-weight: 500; color: var(--t4); text-transform: none; letter-spacing: 0; }
.ph-trail { overflow-y: auto; padding: 0 22px 20px; }
.ph-tr { display: flex; gap: 12px; padding: 12px 0; }
.ph-tr-rail { position: relative; display: flex; justify-content: center; width: 8px; flex-shrink: 0; }
.ph-tr-rail::before { content: ""; position: absolute; top: 14px; bottom: -12px; width: 1.5px; background: var(--line); } .ph-tr:last-child .ph-tr-rail::before { display: none; }
.ph-tr-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 4px; box-shadow: 0 0 0 3px #fff; }
.ph-tr-b { flex: 1; min-width: 0; }
.ph-tr-l { font-size: 12.5px; color: #334155; } .ph-tr-l b { font-weight: 600; color: #1E2A4A; } .fld { color: var(--p-deep); font-weight: 600; }
.ph-tr-c { display: inline-flex; align-items: center; gap: 8px; margin-top: 5px; font-size: 11.5px; } .ph-tr-c .o { color: var(--t4); text-decoration: line-through; } .ph-tr-c .n { color: #0F6E56; font-weight: 600; } .ph-tr-c svg { color: var(--t4); }
.ph-tr-meta { font-size: 10.5px; color: var(--t4); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ph-tr-t { font-size: 10.5px; color: var(--t4); white-space: nowrap; }
.ph-modal-enter-active,.ph-modal-leave-active { transition: opacity .22s ease; } .ph-modal-enter-from,.ph-modal-leave-to { opacity: 0; } .ph-modal-enter-active .ph-mod { transition: transform .4s var(--ease); } .ph-modal-enter-from .ph-mod { transform: scale(.94) translateY(12px); }

@media (max-width: 820px) {
  .ph-hero { grid-template-columns: 1fr; } .ph-hero-l { border-right: 0; border-bottom: 1px solid var(--line); }
  .ph-tiles { grid-template-columns: repeat(2,1fr); }
  .ph-cols { grid-template-columns: 1fr; } .ph-col { border-right: 0; border-bottom: 1px solid var(--line); }
  .ph-card-h { flex-wrap: wrap; gap: 8px; }
  .ph-pdrill-cols { grid-template-columns: 1fr; }
}

/* ─── Телефоны ─────────────────────────────────────────────────── */
@media (max-width: 600px) {
  .ph-top { padding: 0 14px; height: auto; min-height: 56px; flex-wrap: wrap; gap: 8px; padding-top: 8px; padding-bottom: 8px; }
  .ph-top-r { gap: 6px; flex-wrap: wrap; width: 100%; }
  .ph-sel { padding: 8px 10px; font-size: 11px; flex: 1 1 auto; min-height: 38px; }
  .ph-page { padding: 14px 12px 64px; }
  .ph-hero-num { font-size: 44px; } .ph-hero-num small { font-size: 19px; }
  .ph-spark { margin-left: 12px !important; margin-right: 12px !important; }
  .ph-dyn { padding: 12px 12px 8px; gap: 6px; }
  .ph-dyn-hint { font-size: 11px; }
  /* Список компаний: убираем 130px-трек, оставляем номер · название · % */
  .ph-co2 { grid-template-columns: 26px 1fr 44px; gap: 10px; padding: 10px 14px; }
  .ph-co-track { display: none; }
  .ph-co-pct { font-size: 13px; }
}
/* Добавочные стили апгрейда (always-on) */
@media (min-width: 0px) {
  /* чип «+N пр.» у улучшившейся компании */
  .ph-pc-chip { display: inline-block; margin-left: 7px; font-size: 10px; font-weight: 700; color: #0F6E56; background: rgba(29,158,117,.12); border-radius: 5px; padding: 1px 6px; vertical-align: middle; }
  /* «+N пп» в таблице компаний */
  .ph-co-delta { display: inline-block; margin-left: 7px; font-size: 10px; font-weight: 700; border-radius: 5px; padding: 1px 6px; vertical-align: middle; font-variant-numeric: tabular-nums; }
  .ph-co-delta.up { color: #0F6E56; background: rgba(29,158,117,.12); }
  .ph-co-delta.dn { color: #B23434; background: rgba(226,75,74,.10); }
  /* список «какие проекты закрыли» */
  .ph-closed { margin-top: 8px; border-top: 1px dashed var(--line); padding-top: 8px; }
  .ph-closed-h { display: flex; align-items: center; gap: 7px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #0F6E56; padding: 2px 4px 7px; }
  .ph-closed-h span { font-size: 10px; background: rgba(29,158,117,.14); color: #0F6E56; border-radius: 999px; padding: 1px 7px; }
  .ph-closed-row { display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: 8px; }
  .ph-closed-row:hover { background: #F7F6FD; }
  .ph-closed-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .ph-closed-t { flex: 1; min-width: 0; font-size: 12.5px; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ph-closed-t b { color: #0F6E56; font-weight: 700; margin-right: 3px; }
  .ph-closed-co { font-size: 11px; color: var(--t3); white-space: nowrap; flex-shrink: 0; }
}
@media (max-width: 430px) {
  .ph-tiles { grid-template-columns: 1fr 1fr; gap: 8px; }
  .ph-hero-num { font-size: 38px; } .ph-hero-num small { font-size: 17px; }
  .ph-dyn { gap: 4px; }
  .ph-dynp-track { height: 76px; }
}
</style>
