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
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { useFormatters } from "@/composables/useFormatters";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useAiFeatureAccess } from "@/composables/useAiFeatureAccess";
import EptLogo from "@/components/EptLogo.vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import CtPeriodDrill from "@/components/ControlTower/CtPeriodDrill.vue";
import CtCompanyModal from "@/components/ControlTower/CtCompanyModal.vue";
import { i18nKey } from "@/locale/keys";


interface Co { company_id: string; code: string; name: string; sector: string; color: string; badge: string; score: number | null; prog?: number; plan?: number; oblig?: number | null; due?: number; due_done?: number; tasks_done: number; tasks_total: number; projects_done: number; projects_total: number; comments: number; tasks_done_snap?: number; projects_done_snap?: number; comments_snap?: number; }
interface Current { label: string; at: string; period: string; score: number; fact_now: number | null; due_done: number; due_total: number; progress_now: number; plan_now: number; tasks_done: number; tasks_total: number; overdue: number; companies: Co[]; snap_label?: string; snap_at?: string; }
interface CoDelta { company_id: string; code: string; name: string; sector: string; color: string; badge: string; from: number; to: number; delta: number; tasks_from: number; tasks_to: number; projects_from: number; projects_to: number; tasks_total: number; projects_total: number; comments_from: number; comments_to: number; projects_closed?: number; }
interface ClosedProject { company_id: string | null; company: string; sector: string | null; color: string; badge: string | null; num: string | null; title: string; }
interface Comparison { from: { label: string; at: string; score: number }; to: { label: string; at: string; score: number }; portfolio_delta: number | null; improved: CoDelta[]; fell: CoDelta[]; tasks_closed: number; comments_added: number; projects_closed?: number; closed_projects?: ClosedProject[]; }
interface SnapRef { id: string; label: string; at: string; score: number; }
interface Digest { year: number; period: string; available_years: number[]; has_baseline: boolean; current: Current; comparison: Comparison | null; snapshots: SnapRef[]; }
interface TrailItem { ts: string; actor: string; action: string; field: string | null; old_value?: string | null; new_value?: string | null; title: string; is_critical: boolean; }

const toast = useToast();
const { confirmDialog } = useConfirm();
const { t } = useI18n();
const formatters = useFormatters();
// Область доступа: при единственной компании селектор компаний в «Динамике» не нужен.
const scope = useCompanyScope();
const { canUseAi } = useAiFeatureAccess();
const digest = ref<Digest | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const freezing = ref(false);

const year = ref(new Date().getFullYear());
const period = ref("all");
// доступные годы — из бэкенда (data-driven), новый год появляется сам
const years = computed(() => digest.value?.available_years || [year.value]);
const PERIODS = [
  { v: "all", l: i18nKey("Весь год") },
  { v: "q1", l: i18nKey("I квартал") }, { v: "q2", l: i18nKey("II квартал") }, { v: "q3", l: i18nKey("III квартал") }, { v: "q4", l: i18nKey("IV квартал") },
  { v: "m1", l: i18nKey("Январь") }, { v: "m2", l: i18nKey("Февраль") }, { v: "m3", l: i18nKey("Март") }, { v: "m4", l: i18nKey("Апрель") },
  { v: "m5", l: i18nKey("Май") }, { v: "m6", l: i18nKey("Июнь") }, { v: "m7", l: i18nKey("Июль") }, { v: "m8", l: i18nKey("Август") },
  { v: "m9", l: i18nKey("Сентябрь") }, { v: "m10", l: i18nKey("Октябрь") }, { v: "m11", l: i18nKey("Ноябрь") }, { v: "m12", l: i18nKey("Декабрь") },
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
    if (!silent) error.value = e?.response?.data?.detail || e?.message || t("Ошибка загрузки");
  } finally { if (!silent) loading.value = false; }
}
onMounted(() => load());
watch([year, period, fromId, toId], () => load());

async function freeze() {
  if (freezing.value) return;
  freezing.value = true;
  try {
    const { data } = await api.post("/monitoring/snapshot", { year: year.value });
    toast.success(t("Срез зафиксирован · прогресс {n}%", { n: data.score }), 3500);
    fromId.value = ""; toId.value = "";
    await load();
  } catch (e: any) {
    toast.error(t("Не удалось зафиксировать: {err}", { err: e?.response?.data?.detail || e?.message || "" }));
  } finally { freezing.value = false; }
}
async function delSnap(s: SnapRef) {
  if (!(await confirmDialog({ message: t("Удалить срез «{label}»?", { label: s.label }), danger: true }))) return;
  try {
    await api.delete(`/monitoring/snapshot/${s.id}`);
    toast.success(t("Срез удалён"));
    if (fromId.value === s.id) fromId.value = "";
    if (toId.value === s.id) toId.value = "";
    await load();
  } catch (e: any) {
    toast.error(t("Не удалось удалить: {err}", { err: e?.response?.data?.detail || e?.message || "" }));
  }
}

// ─── AI Executive Brief ───────────────────────────────────────
const brief = ref("");
const briefLoading = ref(false);
const briefError = ref("");
async function generateBrief() {
  if (briefLoading.value || !canUseAi.value) return;
  briefLoading.value = true; briefError.value = "";
  try {
    const { data } = await api.post(`/monitoring/brief/${year.value}`, undefined, {
      params: { period: period.value },
    });
    brief.value = data.brief || "";
  } catch (e: any) {
    briefError.value = e?.response?.data?.detail || e?.message || t("Ошибка генерации брифа");
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
// ЕДИНАЯ band-функция «исполнения обязательств» (0-100) — одна для hero и
// per-company, чтобы не было двух систем порогов и «двух цветов» у одной цифры.
function bandClass(v: number | null | undefined): "ok" | "good" | "warn" | "crit" | "na" {
  if (v == null) return "na";
  if (v >= 90) return "ok"; if (v >= 75) return "good"; if (v >= 50) return "warn"; return "crit";
}
const BAND_HEX: Record<string, string> = { ok: "#1D9E75", good: "#3FA36F", warn: "#EF9F27", crit: "#E24B4A", na: "#94A3B8" };
const BAND_WORD: Record<string, string> = {
  ok: i18nKey("обязательства выполняются"), good: i18nKey("в целом по графику"),
  warn: i18nKey("отставание"), crit: i18nKey("сильное отставание"), na: i18nKey("нет наступивших сроков"),
};
function bandColor(v: number | null | undefined): string { return BAND_HEX[bandClass(v)]; }
function coColor(c: { oblig?: number | null }): string { return bandColor(c.oblig); }
// нейтральная «прогресс-интенсивность» (бренд-фиолет) — для накопительной динамики
// и снимков: это РОСТ во времени (movement), а не оценка состояния «плохо/хорошо».
const PROG = "#7C6FF7";
function progColor(_v?: number | null): string { return PROG; }
function fmtDate(s: string | undefined): string {
  if (!s) return "—"; if (s === "Сейчас") return t("Сейчас"); // i18n-exempt: canonical API snapshot label
  return formatters.fmtDateTime(s);
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
// Не выполнено обязательств (наступившие сроки без факта) — для правой части hero.
const obligUnmet = computed(() => cur.value ? Math.max(0, cur.value.due_total - cur.value.due_done) : 0);

// ─── редизайн: статус, зоны риска, сортировка ───
const periodLabel = computed(() => PERIODS.find(p => p.v === period.value)?.l || "");
// Статус/подпись портфеля — по «исполнению обязательств» через единую band.
const statusClass = computed(() => bandClass(cur.value?.fact_now));
const statusWord = computed(() => t(BAND_WORD[bandClass(cur.value?.fact_now)]));
// «Зона риска» компании = исполнение обязательств ниже 60% (заметно позади).
const RISK_OBLIG = 60;
function isRisk(c: Co): boolean { return c.oblig != null && c.oblig < RISK_OBLIG; }
const riskCount = computed(() => (cur.value?.companies || []).filter(isRisk).length);
// сортировка компаний: худшие по обязательствам первыми (риск виден сразу),
// «нет наступивших сроков» (oblig=null) — в конец.
const coSort = ref<"worst" | "best" | "name">("worst");
const sortedCompanies = computed(() => {
  const arr = [...(cur.value?.companies || [])];
  if (coSort.value === "name") return arr.sort((a, b) => a.name.localeCompare(b.name, getCurrentIntlLocale()));
  return arr.sort((a, b) => {
    const sa = a.oblig == null ? 1000 : a.oblig;
    const sb = b.oblig == null ? 1000 : b.oblig;
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
// "" = весь портфель, иначе company_id. Если селектор компаний скрыт (пользователь
// ограничен одной компанией) — сразу подставляем её, чтобы подпись и данные были её.
const dynCompany = ref<string>(scope.showCompanyPicker.value ? "" : (scope.defaultCompanyId.value || ""));
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
    if (!silent) { cumulative.value = null; toast.error(t("Не удалось загрузить динамику: {err}", { err: e?.response?.data?.detail || e?.message || "" })); }
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
  if (!dynCompany.value) return t("Весь портфель");
  return cur.value?.companies.find(c => c.company_id === dynCompany.value)?.name || t("Компания");
});
// тренд: прирост за последний прошедший/текущий период
const trend = computed(() => {
  const past = cumPeriods.value.filter(p => !p.is_future);
  const last = past[past.length - 1];
  const d = last?.delta ?? 0;
  return { dir: (d > 0 ? "up" : d < 0 ? "down" : "flat") as "up" | "down" | "flat", delta: d };
});
const TREND_WORD = { up: i18nKey("прогресс растёт"), down: i18nKey("прогресс снижается"), flat: i18nKey("без прироста") };
const trendWord = computed(() => t(TREND_WORD[trend.value.dir]));

// Тренд для HERO — ВСЕГДА по всему портфелю, независимо от фильтра компании в
// «Динамике» (иначе большое портфельное число сопровождалось трендом одной
// выбранной компании). Отдельная портфель-only накопительная серия.
const portfolioCum = ref<{ total: number; periods: CumPeriod[] } | null>(null);
async function loadPortfolioCum(silent = false) {
  try {
    const { data } = await api.get(`/monitoring/cumulative/${year.value}`, {
      params: { granularity: granularity.value },
    });
    portfolioCum.value = data;
  } catch { if (!silent) portfolioCum.value = null; }
}
const heroTrend = computed(() => {
  const past = (portfolioCum.value?.periods || []).filter(p => !p.is_future);
  const d = past[past.length - 1]?.delta ?? 0;
  return { dir: (d > 0 ? "up" : d < 0 ? "down" : "flat") as "up" | "down" | "flat", delta: d };
});
const heroTrendWord = computed(() => t(TREND_WORD[heroTrend.value.dir]));

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
    toast.error(t("Не удалось загрузить детали периода: {err}", { err: e?.response?.data?.detail || e?.message || "" }));
  } finally { detailsLoading.value = false; }
}
// группировка задач по направлению

onMounted(() => { loadCumulative(); loadPortfolioCum(); });
watch([year, granularity, dynCompany], () => { expandedPeriod.value = null; loadCumulative(); });
watch([year, granularity], () => loadPortfolioCum());

// Нормализуем выбранную компанию (Co из списка ИЛИ CoDelta из улучшились/провалились)
// ─── модалка + trail (сам UI — в CtCompanyModal.vue) ──────────
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
    trailError.value = e?.response?.status === 403 ? t("Нет доступа к ленте") : t("Не удалось загрузить ленту");
  } finally { trailLoading.value = false; }
}
function closeModal() { modalCo.value = null; }

// ─── Live: тихое авто-обновление (как в журнале аудита) ───
let pollTimer: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (!document.hidden && !modalCo.value && !loading.value) { load(true); loadCumulative(true); loadPortfolioCum(true); }
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
        <div><div class="ph-eyebrow">{{ t("ЕДИНЫЙ МОНИТОРИНГ") }}</div><div class="ph-tt">Execution Summary</div></div>
      </div>
      <div class="ph-top-r">
        <select v-model="period" class="ph-sel">
          <option v-for="p in PERIODS" :key="p.v" :value="p.v">{{ t(p.l) }}</option>
        </select>
        <select v-model.number="year" class="ph-sel"><option v-for="y in years" :key="y" :value="y">FY {{ y }}</option></select>
      </div>
    </div>

    <div class="ph-page">
      <UzaStateBlock v-if="loading" state="loading" variant="text" minHeight="180px" />
      <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" minHeight="180px" />

      <template v-else-if="cur">
        <!-- HERO: исполнение обязательств (из наступивших сроков сколько выполнено) -->
        <div class="ph-hero" :class="statusClass">
          <div class="ph-hero-l">
            <div class="ph-hero-eyebrow">{{ t("Исполнение обязательств") }} · {{ t(periodLabel) }} · FY {{ year }}</div>
            <div class="ph-hero-num">{{ cur.fact_now ?? '—' }}<small v-if="cur.fact_now != null">%</small>
              <span class="ph-hero-chip">{{ statusWord }}</span>
            </div>
            <div class="ph-hero-sub">
              <template v-if="cur.due_total">{{ t("выполнено {done} из {total} задач с наступившим сроком", { done: cur.due_done, total: cur.due_total }) }}</template>
              <template v-else>{{ t("сроков ещё не наступало · {n} задач в работе", { n: cur.tasks_total }) }}</template>
              <span v-if="obligUnmet > 0" class="ph-hero-muted">· {{ t("{n} не в срок", { n: obligUnmet }) }}</span>
            </div>
          </div>
          <div class="ph-hero-r">
            <div class="ph-hero-eyebrow alt">{{ t("Взвешенный прогресс") }}</div>
            <div class="ph-hero-num alt">{{ cur.progress_now }}<small>%</small>
              <span v-if="period === 'all'" class="ph-hero-trend" :class="heroTrend.dir">
                {{ heroTrend.dir === 'up' ? '↑' : heroTrend.dir === 'down' ? '↓' : '→' }} {{ heroTrendWord }}
              </span>
            </div>
            <div class="ph-gap-bar">
              <div class="ph-gap-fill prog" :style="{ width: min100(cur.progress_now) + '%' }" />
            </div>
            <div class="ph-hero-sub alt">
              {{ t("учитывает задачи в работе (нач. 25% · в работе 50% · проверка 75%)") }} · <b>{{ cur.overdue }}</b> {{ t("просрочено") }}
            </div>
          </div>
        </div>

        <!-- KEY TILES -->
        <div class="ph-tiles">
          <div class="ph-tile"><div class="ph-tile-n">{{ cur.tasks_done }}<em>/{{ cur.tasks_total }}</em></div><div class="ph-tile-l">{{ t("задач полностью завершено") }}</div></div>
          <div class="ph-tile" :class="{ on: cur.overdue > 0 }" data-tone="danger"><div class="ph-tile-n">{{ cur.overdue }}</div><div class="ph-tile-l">{{ t("просрочено сейчас") }}</div></div>
          <div class="ph-tile" :class="{ on: riskCount > 0 }" data-tone="warn"><div class="ph-tile-n">{{ riskCount }}</div><div class="ph-tile-l">{{ t("компаний в зоне риска") }}</div></div>
          <div class="ph-tile"><div class="ph-tile-n">{{ cur.companies.length }}</div><div class="ph-tile-l">{{ t("компаний в портфеле") }}</div></div>
        </div>

        <!-- AI EXECUTIVE BRIEF -->
        <div v-if="canUseAi" class="ph-brief">
          <div class="ph-brief-h">
            <div class="ph-brief-tl">
              <span class="ph-brief-spark">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/><path d="M19 14l.7 1.8L21.5 16.5l-1.8.7L19 19l-.7-1.8L16.5 16.5l1.8-.7z"/></svg>
              </span>
              <div>
                <div class="ph-brief-eyebrow">AI EXECUTIVE BRIEF</div>
                <div class="ph-brief-sub">{{ t("Сводка для Совета директоров на основе реальных цифр") }}</div>
              </div>
            </div>
            <button class="ph-brief-btn" @click="generateBrief" :disabled="briefLoading">
              <svg v-if="!briefLoading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3l1.9 4.6L18.5 9.5l-4.6 1.9L12 16l-1.9-4.6L5.5 9.5l4.6-1.9z"/></svg>
              {{ briefLoading ? t('Генерирую…') : (brief ? t('Обновить') : t('Сгенерировать')) }}
            </button>
          </div>
          <div v-if="briefError" class="ph-brief-err">{{ briefError }}</div>
          <div v-else-if="briefLoading && !brief" class="ph-brief-empty">{{ t("Анализирую исполнение портфеля…") }}</div>
          <div v-else-if="brief" class="ph-brief-body" v-html="'<p>' + briefHtml(brief) + '</p>'"></div>
          <div v-else class="ph-brief-empty">{{ t("Нажмите «Сгенерировать» — ИИ соберёт executive-бриф: статус, риски, траектория, рекомендации.") }}</div>
        </div>

        <!-- ДИНАМИКА ИСПОЛНЕНИЯ (накопительная) -->
        <div class="ph-card">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">{{ t("ДИНАМИКА ИСПОЛНЕНИЯ") }}</span><span class="ph-card-cap">{{ t("накопительный % выполнено от портфеля · стрелка — прирост за период · клик — детали") }}</span></div>
            <div class="ph-dyn-ctl">
              <select v-if="scope.showCompanyPicker.value" v-model="dynCompany" class="ph-dyn-co">
                <option value="">{{ t("Весь портфель") }}</option>
                <option v-for="c in cur.companies" :key="c.company_id" :value="c.company_id">{{ c.name }}</option>
              </select>
              <div class="uza-seg">
                <button class="uza-seg-btn" :class="{ on: granularity === 'quarter' }" @click="granularity = 'quarter'">{{ t("Кварталы") }}</button>
                <button class="uza-seg-btn" :class="{ on: granularity === 'month' }" @click="granularity = 'month'">{{ t("Месяцы") }}</button>
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
                   role="button" tabindex="0" :aria-expanded="expandedPeriod === p.key"
                   :aria-label="t('Детали периода {p}', { p: t(p.label_full) })"
                   @click="togglePeriod(p.key)" @keydown.enter="togglePeriod(p.key)" @keydown.space.prevent="togglePeriod(p.key)">
                <div class="ph-dynp-top">
                  <span v-if="p.is_future" class="ph-dynp-delta fl ph-dynp-first">{{ t("не наступил") }}</span>
                  <span v-else-if="p.delta != null" class="ph-dynp-delta" :class="p.delta > 0 ? 'up' : p.delta < 0 ? 'dn' : 'fl'">
                    {{ p.delta > 0 ? '↑+' + p.delta : p.delta < 0 ? '↓' + p.delta : '→ 0' }}<em>{{ t("пп") }}</em>
                  </span>
                  <span v-else class="ph-dynp-delta fl ph-dynp-first">{{ t("старт") }}</span>
                </div>
                <div class="ph-dynp-track">
                  <span class="ph-dynp-fill" :style="{ height: Math.max(4, Math.round(p.cum_pct / maxPct * 100)) + '%', background: progColor(p.cum_pct) }" />
                </div>
                <div class="ph-dynp-pct" :style="{ color: progColor(p.cum_pct) }">{{ p.cum_pct }}%</div>
                <div class="ph-dynp-cnt">{{ p.cum_done }}/{{ p.total }}</div>
                <div class="ph-dynp-sub"><span v-if="p.is_future" class="fu">—</span><template v-else><span class="ok">+{{ p.done_in_period }}</span><span v-if="p.overdue" class="od">{{ t("{n} проср.", { n: p.overdue }) }}</span></template></div>
                <div class="ph-dynp-lbl" :class="{ now: p.isNow }">{{ granularity === 'quarter' ? t("{n} кв", { n: p.label }) : t(p.label) }}</div>
              </div>
            </div>

            <!-- ДЕТАЛИ ПЕРИОДА (дрилл по направлениям) -->
            <CtPeriodDrill v-if="expandedPeriod" :details="periodDetails" :loading="detailsLoading" />
          </template>
          <div class="ph-dyn-foot">
            <span class="ph-dyn-trend" :class="trend.dir">
              {{ trend.dir === 'up' ? '↑' : trend.dir === 'down' ? '↓' : '→' }}
              {{ dynName }} · {{ trendWord }}<template v-if="trend.delta"> ({{ trend.delta > 0 ? '+' : '' }}{{ trend.delta }} {{ t("пп за период") }})</template>
            </span>
            <span class="ph-dyn-hint">{{ t("% = задач завершено накопительно / портфель (без ежемес./постоянных) · по дате завершения, для задач без неё — по плановому сроку · клик — детали") }}</span>
          </div>
        </div>

        <!-- ЧТО ИЗМЕНИЛОСЬ (если есть срез) -->
        <div v-if="cmp" class="ph-card ph-change">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">{{ t("ЧТО ИЗМЕНИЛОСЬ") }}</span><span class="ph-card-cap">{{ fmtDate(cmp.from.at) }} → {{ fmtDate(cmp.to.at) }}</span></div>
            <div class="ph-change-delta" :class="(cmp.portfolio_delta||0) > 0 ? 'up' : (cmp.portfolio_delta||0) < 0 ? 'dn' : 'fl'">
              {{ cmp.from.score }}% → {{ cmp.to.score }}%
              <b>{{ (cmp.portfolio_delta||0) > 0 ? '+' : '' }}{{ cmp.portfolio_delta }} {{ t("пп") }}</b>
            </div>
          </div>
          <div class="ph-cols">
            <div class="ph-col">
              <div class="ph-col-h up">{{ t("Улучшились") }}<span>{{ cmp.improved.length }}</span></div>
              <div v-if="cmp.improved.length" class="ph-col-list">
                <div v-for="c in cmp.improved" :key="c.company_id" class="ph-co" role="button" tabindex="0" :aria-label="t('Лента изменений: {name}', { name: c.name })" @click="openCompany(c)" @keydown.enter="openCompany(c)" @keydown.space.prevent="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m">
                    <div class="ph-co-n">{{ c.name }}<span v-if="(c.projects_closed || 0) > 0" class="ph-pc-chip" :title="t('{n} проект(ов) закрыто', { n: c.projects_closed })">{{ t("+{n} пр.", { n: c.projects_closed }) }}</span></div>
                    <div class="ph-co-s">{{ c.sector }}</div>
                  </div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: progColor(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d up">+{{ c.delta }}</div>
                </div>
              </div>
              <div v-else-if="!closedProjects.length" class="ph-col-e">{{ t("Никто не вырос") }}</div>

              <!-- Какие именно проекты закрыли в окне -->
              <div v-if="closedProjects.length" class="ph-closed">
                <div class="ph-closed-h">{{ t("Закрыто проектов") }}<span>{{ projectsClosed }}</span></div>
                <div v-for="(p, i) in closedProjects" :key="i" class="ph-closed-row">
                  <span class="ph-closed-dot" :style="{ background: p.color }" />
                  <span class="ph-closed-t"><b v-if="p.num">{{ p.num }}</b> {{ p.title }}</span>
                  <span class="ph-closed-co">{{ p.company }}</span>
                </div>
              </div>
            </div>
            <div class="ph-col">
              <div class="ph-col-h dn">{{ t("Провалились") }}<span>{{ cmp.fell.length }}</span></div>
              <div v-if="cmp.fell.length" class="ph-col-list">
                <div v-for="c in cmp.fell" :key="c.company_id" class="ph-co" role="button" tabindex="0" :aria-label="t('Лента изменений: {name}', { name: c.name })" @click="openCompany(c)" @keydown.enter="openCompany(c)" @keydown.space.prevent="openCompany(c)">
                  <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
                  <div class="ph-co-m"><div class="ph-co-n">{{ c.name }}</div><div class="ph-co-s">{{ c.sector }}</div></div>
                  <div class="ph-co-p"><span class="f">{{ c.from }}</span><span class="t" :style="{ color: progColor(c.to) }">{{ c.to }}%</span></div>
                  <div class="ph-co-d dn">{{ c.delta }}</div>
                </div>
              </div>
              <div v-else class="ph-col-e">{{ t("Никто не провалился — хорошо") }}</div>
            </div>
          </div>
          <div class="ph-change-meta">
            <span><b :style="{ color: cmp.tasks_closed>0 ? '#1D9E75' : '#1E2A4A' }">{{ cmp.tasks_closed>0 ? '+'+cmp.tasks_closed : cmp.tasks_closed }}</b> {{ t("задач закрыто") }}</span>
            <span class="dot">·</span>
            <span><b :style="{ color: projectsClosed>0 ? '#1D9E75' : '#1E2A4A' }">{{ projectsClosed>0 ? '+'+projectsClosed : 0 }}</b> {{ t("проектов закрыто") }}</span>
            <span class="dot">·</span>
            <span><b :style="{ color: cmp.comments_added ? '#7C6FF7' : '#1E2A4A' }">{{ cmp.comments_added }}</b> {{ t("комментариев") }}</span>
          </div>
        </div>
        <div v-else class="ph-hint">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
          {{ t("Зафиксируйте срез — и здесь появится «было → стало»: кто вырос, кто провалился. Срезы фиксируются и автоматически (раз в день).") }}
        </div>

        <!-- КОМПАНИИ (live, отсортированы по риску) -->
        <div class="ph-card">
          <div class="ph-card-h">
            <div><span class="ph-eyebrow2">{{ t("ПО КОМПАНИЯМ") }}</span><span class="ph-card-cap">{{ cur.companies.length }} · {{ t("клик — лента изменений") }}</span></div>
            <div class="uza-seg">
              <button class="uza-seg-btn" :class="{ on: coSort === 'worst' }" @click="coSort = 'worst'">{{ t("Сначала риск") }}</button>
              <button class="uza-seg-btn" :class="{ on: coSort === 'best' }" @click="coSort = 'best'">{{ t("Лучшие") }}</button>
              <button class="uza-seg-btn" :class="{ on: coSort === 'name' }" @click="coSort = 'name'">{{ t("По имени") }}</button>
            </div>
          </div>
          <div class="ph-co-list2">
            <UzaStateBlock v-if="!sortedCompanies.length" state="empty" variant="inline"
                           :text="t('Нет компаний с данными за этот период.')" />
            <div v-for="c in sortedCompanies" :key="c.company_id" class="ph-co2"
                 :class="{ risk: isRisk(c) }" role="button" tabindex="0"
                 :aria-label="t('Лента изменений: {name}', { name: c.name })"
                 @click="openCompany(c)" @keydown.enter="openCompany(c)" @keydown.space.prevent="openCompany(c)">
              <div class="av" :style="{ background: c.color }">{{ c.badge }}</div>
              <div class="ph-co-m">
                <div class="ph-co-n">{{ c.name }}<span v-if="isRisk(c)" class="ph-risk-tag">{{ t("риск") }}</span><span v-if="coDeltaMap[c.company_id]" class="ph-co-delta" :class="coDeltaMap[c.company_id] > 0 ? 'up' : 'dn'">{{ coDeltaMap[c.company_id] > 0 ? '+' : '' }}{{ coDeltaMap[c.company_id] }} {{ t("пп") }}</span></div>
                <div class="ph-co-nums">
                  <span>{{ t("задачи") }} <b>{{ c.tasks_done }}</b>/{{ c.tasks_total }}<i v-if="hasSnap && (c.tasks_done - (c.tasks_done_snap||0)) > 0" class="up">+{{ c.tasks_done - (c.tasks_done_snap||0) }}</i></span>
                  <span>{{ t("проекты") }} <b>{{ c.projects_done }}</b>/{{ c.projects_total }}<i v-if="hasSnap && (c.projects_done - (c.projects_done_snap||0)) > 0" class="up">+{{ c.projects_done - (c.projects_done_snap||0) }}</i></span>
                  <span v-if="c.comments"><b>{{ c.comments }}</b> {{ t("комм.") }}<i v-if="hasSnap && (c.comments - (c.comments_snap||0)) > 0" class="up">+{{ c.comments - (c.comments_snap||0) }}</i></span>
                </div>
              </div>
              <div class="ph-co-track"><span :style="{ width: Math.min(100, c.oblig ?? 0) + '%', background: coColor(c) }" /></div>
              <span class="ph-co-pct" :style="{ color: coColor(c) }">{{ c.oblig ?? '—' }}<template v-if="c.oblig!=null">%</template></span>
            </div>
          </div>
        </div>

        <!-- СРЕЗЫ (инструмент — внизу, сворачиваемо) -->
        <div class="ph-snapcard">
          <div class="ph-snapcard-h">
            <div class="ph-snapbar-l">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 5h14a1 1 0 011 1v13a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1zM4 10h16M8 3v4M16 3v4"/></svg>
              <span><b>{{ digest!.snapshots.length }}</b> {{ t(digest!.snapshots.length === 1 ? t('срез прогресса') : (digest!.snapshots.length < 5 && digest!.snapshots.length ? t('среза прогресса') : t('срезов прогресса'))) }}</span>
              <button v-if="digest!.snapshots.length" class="ph-link" :aria-expanded="showSnaps" @click="showSnaps = !showSnaps">{{ showSnaps ? t('скрыть') : t('управлять') }}</button>
            </div>
            <button class="ph-freeze sm" @click="freeze" :disabled="freezing">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
              {{ freezing ? t("Фиксирую…") : t("Зафиксировать срез") }}
            </button>
          </div>
          <div v-if="showSnaps && digest!.snapshots.length" class="ph-snaplist flat">
            <div v-for="s in digest!.snapshots" :key="s.id" class="ph-snaprow">
              <span class="ph-snap-dot" :style="{ background: progColor(s.score) }" />
              <span class="ph-snap-lbl">{{ t(s.label) }}</span>
              <span class="ph-snap-score" :style="{ color: progColor(s.score) }">{{ s.score }}%</span>
              <span class="ph-snap-at">{{ fmtDate(s.at) }}</span>
              <button class="ph-snap-del" @click="delSnap(s)" :title="t('Удалить срез')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- МОДАЛКА КОМПАНИИ — вынесена в CtCompanyModal.vue (a11y через ModalShell) -->
    <CtCompanyModal :co="modalCo" :has-snap="hasSnap" :trail="trail"
                    :loading="trailLoading" :error="trailError" @close="closeModal" />
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
/* Полоска — градиент: цвет обязательств (слева) → фиолет прогресса (справа):
   визуально обе метрики, а не только «тревожная» строгая. */
.ph-hero.crit::before { background: linear-gradient(90deg, #E24B4A 0 38%, #7C6FF7 82%); }
.ph-hero.warn::before { background: linear-gradient(90deg, #EF9F27 0 38%, #7C6FF7 82%); }
.ph-hero.good::before { background: linear-gradient(90deg, #6C5CE7 0 38%, #7C6FF7 82%); }
.ph-hero.ok::before { background: linear-gradient(90deg, #1D9E75 0 38%, #7C6FF7 82%); }
.ph-hero.na::before { background: linear-gradient(90deg, #94A3B8 0 38%, #7C6FF7 82%); }
.ph-hero-l { padding: 22px 28px; background: linear-gradient(135deg,#fff,#FBFAFF); border-right: 1px solid var(--line); }
.ph-hero.crit .ph-hero-l { background: linear-gradient(135deg,#FFF6F6,#FFF0F0); }
.ph-hero.warn .ph-hero-l { background: linear-gradient(135deg,#FFFBF3,#FEF6E9); }
.ph-hero-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3); }
.ph-hero-num { font-size: clamp(40px, 6vw, 60px); font-weight: 400; letter-spacing: -.045em; line-height: 1; margin-top: 10px; font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 12px; }
.ph-hero.crit .ph-hero-num { color: #E24B4A; } .ph-hero.warn .ph-hero-num { color: #C77A0A; } .ph-hero.good .ph-hero-num { color: #6C5CE7; } .ph-hero.ok .ph-hero-num { color: #1D9E75; } .ph-hero.na .ph-hero-num { color: #64748B; }
.ph-hero-num small { font-size: 26px; }
.ph-hero-chip { font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 999px; letter-spacing: .01em; align-self: center; }
.ph-hero.crit .ph-hero-chip { background: rgba(226,75,74,.12); color: #C0392B; } .ph-hero.warn .ph-hero-chip { background: rgba(239,159,39,.14); color: #C77A0A; } .ph-hero.good .ph-hero-chip { background: rgba(124,111,247,.12); color: #534AB7; } .ph-hero.ok .ph-hero-chip { background: rgba(29,158,117,.12); color: #0F6E56; } .ph-hero.na .ph-hero-chip { background: #F1F2F6; color: #64748B; }
.ph-hero-sub { font-size: 12.5px; color: var(--t3); margin-top: 12px; }
.ph-hero-r { padding: 22px 28px; display: flex; flex-direction: column; justify-content: center; gap: 12px; background: #fff; }
.ph-gap-bar { position: relative; height: 12px; border-radius: 7px; background: #F0F1F6; }
.ph-gap-fill { position: absolute; left: 0; top: 0; height: 100%; border-radius: 7px; background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%); transition: width .8s var(--ease-out); }
.ph-hero.crit .ph-gap-fill { background-color: #E2807F; } .ph-hero.warn .ph-gap-fill { background-color: #EFB373; } .ph-hero.good .ph-gap-fill { background-color: #7C6FF7; } .ph-hero.ok .ph-gap-fill { background-color: #5DC093; } .ph-hero.na .ph-gap-fill { background-color: #B8B7B0; }
/* Правая метрика hero — взвешенный прогресс (крупно, всегда бренд-фиолет,
   независимо от статуса обязательств): «не всё так плохо — общий прогресс 40%». */
.ph-hero-r { justify-content: center; gap: 8px; }
.ph-hero-eyebrow.alt { color: #6C5CE7; }
.ph-hero-r .ph-hero-num.alt { font-size: 46px; color: #6C5CE7; margin-top: 4px; }
.ph-hero-r .ph-hero-num.alt small { font-size: 22px; color: #6C5CE7; }
.ph-hero-r .ph-gap-fill.prog { background-color: #7C6FF7; }
.ph-hero-sub.alt { margin-top: 4px; }
.ph-hero-sub.alt b { color: #E24B4A; font-weight: 700; }
.ph-hero-muted { color: var(--t4); margin-left: 6px; }
/* a11y: видимые фокус-кольца на нативных селектах (у них outline:none) + строках */
.ph-sel:focus-visible, .ph-dyn-co:focus-visible { outline: 2px solid #7C6FF7; outline-offset: 2px; }
.ph-co2:focus-visible, .ph-dynp:focus-visible, .ph-co:focus-visible { outline: 2px solid #7C6FF7; outline-offset: -2px; border-radius: 12px; }
@media (prefers-reduced-motion: reduce) {
  .ph-gap-fill, .ph-dynp-fill, .ph-co-track span, .ph-hero-num, .ph-spark-dot { transition: none !important; animation: none !important; }
}

/* ─── TILES ─── */
.ph-tiles { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 16px; }
.ph-tile { background: #fff; border: 1px solid var(--bd); border-radius: 14px; padding: 16px 18px; box-shadow: var(--sh-sm); position: relative; overflow: hidden; }
.ph-tile::after { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 3px; background: #E2E5EE; border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0; }
.ph-tile[data-tone="danger"].on::after { background: #E24B4A; } .ph-tile[data-tone="warn"].on::after { background: #EF9F27; }
.ph-tile-n { font-size: 26px; font-weight: 400; letter-spacing: -.03em; color: #1E2A4A; font-variant-numeric: tabular-nums; line-height: 1; }
.ph-tile-n em { font-size: 15px; font-weight: 600; color: var(--t4); font-style: normal; }
.ph-tile[data-tone="danger"].on .ph-tile-n { color: #E24B4A; } .ph-tile[data-tone="warn"].on .ph-tile-n { color: #C77A0A; }
.ph-tile-l { font-size: 11px; font-weight: 500; color: var(--t3); margin-top: 8px; }

/* ─── sort switch ─── */
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
.ph-vd-num { font-size: 56px; font-weight: 400; letter-spacing: -.045em; line-height: 1; margin-top: 8px; font-variant-numeric: tabular-nums; }
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
.ph-hero-trend { margin-left: 10px; font-size: 11px; font-weight: 600; letter-spacing: normal; white-space: nowrap; padding: 2px 9px; border-radius: 999px; align-self: center; }
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

/* Дрилл периода — вынесен в CtPeriodDrill.vue */
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
.ph-co2:hover { background: #FAFAFF; } .ph-co2:last-child { border-bottom: 0; }
.ph-co-track { height: 7px; border-radius: 5px; background: #F0F1F6; overflow: hidden; } .ph-co-track > span { display: block; height: 100%; border-radius: 5px; transition: width .7s var(--ease-out); }
.ph-co-pct { font-size: 13px; font-weight: 700; text-align: right; font-variant-numeric: tabular-nums; }
.ph-co-cnt { font-size: 10.5px; color: var(--t4); text-align: right; font-variant-numeric: tabular-nums; }

/* модалка компании — вынесена в CtCompanyModal.vue */

@media (max-width: 1024px) {
  .ph-tiles { grid-template-columns: repeat(2,1fr); }
  .ph-pdrill-cols { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .ph-hero { grid-template-columns: 1fr; } .ph-hero-l { border-right: 0; border-bottom: 1px solid var(--line); }
  .ph-cols { grid-template-columns: 1fr; } .ph-col { border-right: 0; border-bottom: 1px solid var(--line); }
  .ph-card-h { flex-wrap: wrap; gap: 8px; }
}

/* ─── Телефоны ─────────────────────────────────────────────────── */
@media (max-width: 640px) {
  .ph-top { padding: 0 14px; height: auto; min-height: 56px; flex-wrap: wrap; gap: 8px; padding-top: 8px; padding-bottom: 8px; }
  .ph-top-r { gap: 6px; flex-wrap: wrap; width: 100%; }
  .ph-sel { padding: 8px 10px; font-size: 11px; flex: 1 1 auto; min-height: 38px; }
  .ph-page { padding: 14px 12px 64px; }
  .ph-hero-num small { font-size: 19px; }
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
@media (max-width: 480px) {
  .ph-tiles { grid-template-columns: 1fr 1fr; gap: 8px; }
  .ph-hero-num small { font-size: 17px; }
  .ph-dyn { gap: 4px; }
  .ph-dynp-track { height: 76px; }
}
</style>
