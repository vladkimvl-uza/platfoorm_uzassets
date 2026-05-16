<!--
  CompanyOverviewExtras.vue -- 6 блоков для Overview tab Company Workspace.

  Заменяет placeholder-секции (строки 1988-2026 в CompanyWorkspace.vue v8).

  Блоки:
    1. ЭКОНОМ. ЭФФЕКТ -- агрегаты по проектам (count, active, completed, avg progress)
    2. ПО НАПРАВЛЕНИЯМ -- группировка проектов по direction
    3. SECTOR RANKING -- top компаний сектора по composite_score
    4. ВНИМАНИЕ -- overdue badge (получает через prop)
    5. АКТИВНОСТЬ -- последние 5 обновлённых задач (тк audit_logs нет в БД)
    6. KPI · {year} -- managers с прогресс-барами (weighted average)
    7. БП · {year} -- выручка/прибыль план/факт

  Defensive: каждый блок в try/catch, graceful fallback при ошибке/empty.
-->
<script setup lang="ts">
import { ref, reactive, watch, onMounted } from "vue";
import { api } from "@/api/client";

interface Props {
  companyId: string;
  companyCode?: string;
  sectorId?: string;
  sectorName?: string;
  year: number;
  overdue?: number;
}
const props = withDefaults(defineProps<Props>(), {
  overdue: 0,
  sectorName: "Сектор",
});

// ============================================================
// STATE
// ============================================================
const loading = reactive({
  effect: true,
  dirs: true,
  sector: true,
  activity: true,
  kpi: true,
  bp: true,
});

const errors = reactive<Record<string, string | null>>({
  effect: null,
  dirs: null,
  sector: null,
  activity: null,
  kpi: null,
  bp: null,
});

interface EffectProject {
  id: string;
  title: string;
  plannedUzs: number;
  realizedUzs: number;
  source: string;
}
interface EffectData {
  plannedTotal: number; // UZS
  realizedTotal: number; // UZS
  projectsWithEffect: number;
  totalProjects: number;
  topProjects: EffectProject[];
}
const effectData = ref<EffectData | null>(null);

interface DirRow {
  direction: string;
  count: number;
}
const dirsData = ref<DirRow[]>([]);

interface SectorRow {
  code: string;
  name: string;
  score: number;
  grade: string;
  isMine: boolean;
}
const sectorRanking = ref<SectorRow[]>([]);

interface ActivityRow {
  type: string;
  title: string;
  iso: string;
  status?: string;
}
const activityData = ref<ActivityRow[]>([]);

interface KpiManagerRow {
  title: string;
  role?: string;
  progress: number;
  hasFact: boolean;
  indicators: number;
}
interface KpiData {
  managers: KpiManagerRow[];
  overallProgress: number; // 0-100
  totalManagers: number;
  totalIndicators: number;
  attentionCount: number; // r<0.90 AND weight>=15
  hasAnyFact: boolean;
}
const kpiData = ref<KpiData | null>(null);

interface BpMetric {
  plan: number | null;
  fact: number | null;
  expect: number | null;
  hasPlan: boolean;
  hasFact: boolean;
}
interface BpData {
  revenue: BpMetric;
  opProfit: BpMetric;
  profit: BpMetric;
  hasData: boolean;
}
const bpData = ref<BpData | null>(null);

// ============================================================
// HELPERS
// ============================================================
function _num(x: any): number {
  if (x === null || x === undefined || x === "") return 0;
  const n = Number(x);
  return isNaN(n) ? 0 : n;
}

function _arr(x: any): any[] {
  if (Array.isArray(x)) return x;
  if (x && typeof x === "object") {
    if (Array.isArray(x.items)) return x.items;
    if (Array.isArray(x.data)) return x.data;
    if (Array.isArray(x.results)) return x.results;
    if (Array.isArray(x.records)) return x.records;
  }
  return [];
}

function fmtMoney(n: number, addUnit = true): string {
  if (!n || isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e12) return (n / 1e12).toFixed(1) + (addUnit ? " трлн" : "");
  if (abs >= 1e9) return (n / 1e9).toFixed(1) + (addUnit ? " млрд" : "");
  if (abs >= 1e6) return (n / 1e6).toFixed(1) + (addUnit ? " млн" : "");
  if (abs >= 1e3) return (n / 1e3).toFixed(0) + (addUnit ? " тыс" : "");
  return n.toFixed(0);
}

function fmtTimeAgo(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  const diffMin = Math.floor((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "только что";
  if (diffMin < 60) return `${diffMin} мин`;
  const h = Math.floor(diffMin / 60);
  if (h < 24) return `${h} ч`;
  const days = Math.floor(h / 24);
  if (days < 31) return `${days} дн`;
  const months = Math.floor(days / 30);
  return `${months} мес`;
}

function pctClass(pct: number): string {
  if (pct >= 100) return "cox-pct-green";
  if (pct >= 80) return "cox-pct-blue";
  if (pct >= 50) return "cox-pct-amber";
  return "cox-pct-red";
}

function pctClassBp(pct: number): string {
  if (pct >= 95) return "cox-pct-green";
  if (pct >= 80) return "cox-pct-amber";
  return "cox-pct-red";
}

function pctClassKpi(pct: number): string {
  if (pct >= 70) return "cox-pct-green";
  if (pct >= 35) return "cox-pct-amber";
  return "cox-pct-red";
}

function fmtBp(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const av = Math.abs(v);
  if (av >= 10000) return (v / 1000).toFixed(1).replace(/\.0$/, "") + " трлн";
  if (av >= 100) return Math.round(v).toLocaleString("ru-RU") + " млрд";
  if (av >= 1) return v.toFixed(1).replace(/\.0$/, "") + " млрд";
  return v.toFixed(2).replace(/\.?0+$/, "") + " млрд";
}

// ============================================================
// LOADERS
// ============================================================
// TODO: брать из year_registry endpoint когда будет
const USD_RATES: Record<number, number> = {
  2024: 12700,
  2025: 12750,
  2026: 13000,
  2027: 13200,
};
const _SANITY_CAP_PER_TASK = 100e12; // 100 трлн UZS

function _getUsdRate(year: number): number {
  return USD_RATES[year] || 12800;
}

function _extractEffect(
  proj: any,
  year: number,
): { plannedUzs: number; realizedUzs: number; source: string } {
  if (!proj) return { plannedUzs: 0, realizedUzs: 0, source: "none" };

  // economicEffect может быть в proj.economicEffect или proj.extra.economicEffect
  const ov =
    (proj.economicEffect && typeof proj.economicEffect === "object"
      ? proj.economicEffect
      : null) ||
    (proj.extra &&
    typeof proj.extra === "object" &&
    proj.extra.economicEffect &&
    typeof proj.extra.economicEffect === "object"
      ? proj.extra.economicEffect
      : null);

  if (!ov) return { plannedUzs: 0, realizedUzs: 0, source: "none" };

  let plannedRaw = parseFloat(ov.plannedValue);
  let realizedRaw = parseFloat(ov.realizedValue);

  // Legacy миграция: value + kind
  if (!isFinite(plannedRaw) && !isFinite(realizedRaw)) {
    const legacy = parseFloat(ov.value);
    if (isFinite(legacy) && legacy > 0) {
      if (ov.kind === "planned") {
        plannedRaw = legacy;
        realizedRaw = 0;
      } else {
        realizedRaw = legacy;
        plannedRaw = 0;
      }
    }
  }

  const planned = isFinite(plannedRaw) ? plannedRaw : 0;
  const realized = isFinite(realizedRaw) ? realizedRaw : 0;

  if (planned <= 0 && realized <= 0) {
    return { plannedUzs: 0, realizedUzs: 0, source: "none" };
  }

  // Unit multiplier
  const mult =
    ov.unit === "трлн"
      ? 1e12
      : ov.unit === "млрд"
        ? 1e9
        : ov.unit === "млн"
          ? 1e6
          : 1;

  let plannedUzs = planned * mult;
  let realizedUzs = realized * mult;

  // USD → UZS
  if (ov.currency === "USD") {
    const rate = _getUsdRate(year);
    plannedUzs *= rate;
    realizedUzs *= rate;
  }

  // Sanity cap
  const maxVal = Math.max(plannedUzs, realizedUzs);
  if (maxVal > _SANITY_CAP_PER_TASK) {
    return { plannedUzs: 0, realizedUzs: 0, source: "sanity_capped" };
  }

  return { plannedUzs, realizedUzs, source: "manual" };
}

// Формат для UZS чисел из эффекта
function fmtEffectUzs(v: number): string {
  if (!v || isNaN(v)) return "—";
  const av = Math.abs(v);
  if (av >= 1e12) return (v / 1e12).toFixed(1).replace(/\.0$/, "") + " трлн";
  if (av >= 1e9) return (v / 1e9).toFixed(1).replace(/\.0$/, "") + " млрд";
  if (av >= 1e6) return Math.round(v / 1e6) + " млн";
  return Math.round(v).toLocaleString("ru-RU");
}

async function loadEffect() {
  loading.effect = true;
  errors.effect = null;
  try {
    const r = await api.get(
      `/projects?company_id=${props.companyId}&limit=500`,
    );
    let projects = _arr(r.data);

    // Year filter через portfolio_year
    if (props.year) {
      projects = projects.filter((p: any) => {
        const py = p.portfolio_year;
        return py == null || py === props.year;
      });
    }

    const totalProjects = projects.length;

    // Извлекаем эффект из каждого проекта (только manual)
    const withEffect: EffectProject[] = [];
    let plannedTotal = 0;
    let realizedTotal = 0;

    for (const p of projects) {
      const eff = _extractEffect(p, props.year);
      if (eff.source === "manual" && (eff.plannedUzs > 0 || eff.realizedUzs > 0)) {
        withEffect.push({
          id: p.id,
          title: p.title || p.name || "—",
          plannedUzs: eff.plannedUzs,
          realizedUzs: eff.realizedUzs,
          source: eff.source,
        });
        plannedTotal += eff.plannedUzs;
        realizedTotal += eff.realizedUzs;
      }
    }

    // Top 5 по планируемому эффекту
    const topProjects = [...withEffect]
      .sort((a, b) => b.plannedUzs - a.plannedUzs)
      .slice(0, 5);

    effectData.value = {
      plannedTotal,
      realizedTotal,
      projectsWithEffect: withEffect.length,
      totalProjects,
      topProjects,
    };
  } catch (e: any) {
    errors.effect = e?.message || "Ошибка";
    effectData.value = {
      plannedTotal: 0,
      realizedTotal: 0,
      projectsWithEffect: 0,
      totalProjects: 0,
      topProjects: [],
    };
  } finally {
    loading.effect = false;
  }
}

async function loadDirs() {
  loading.dirs = true;
  errors.dirs = null;
  try {
    const r = await api.get(
      `/projects?company_id=${props.companyId}&limit=500`,
    );
    let projects = _arr(r.data);

    // Year filter
    if (props.year) {
      projects = projects.filter((p: any) => {
        const py = p.portfolio_year;
        return py == null || py === props.year;
      });
    }

    const map = new Map<string, number>();
    for (const p of projects) {
      const d =
        p.direction_name ||
        (p.direction && (p.direction.name_ru || p.direction.name)) ||
        p.direction ||
        p.direction_ru ||
        "Без направления";
      const key = String(d);
      map.set(key, (map.get(key) || 0) + 1);
    }
    dirsData.value = Array.from(map, ([direction, count]) => ({ direction, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 6);
  } catch (e: any) {
    errors.dirs = e?.message || "Ошибка";
  } finally {
    loading.dirs = false;
  }
}

async function loadSector() {
  loading.sector = true;
  errors.sector = null;
  try {
    const r = await api.get(`/companies`);
    const allCompanies = _arr(r.data);

    const sectorMatches = allCompanies.filter((c: any) => {
      if (props.sectorId && c.sector_id) return c.sector_id === props.sectorId;
      const myComp = allCompanies.find((cc: any) => cc.id === props.companyId);
      if (!myComp) return false;
      return c.sector_id === myComp.sector_id || c.sector === myComp.sector;
    });

    if (sectorMatches.length === 0) {
      sectorRanking.value = [];
      return;
    }

    const limited = sectorMatches.slice(0, 12);
    const settled = await Promise.allSettled(
      limited.map(async (c: any) => {
        try {
          const rr = await api.get(`/companies/${c.code}/ratings`);
          const list = _arr(rr.data);
          // Latest -- сортируем по year/quarter если есть, или берём первый
          const sorted = [...list].sort((a: any, b: any) => {
            const ya = _num(a.year);
            const yb = _num(b.year);
            if (ya !== yb) return yb - ya;
            return _num(b.quarter) - _num(a.quarter);
          });
          const latest = sorted[0] || null;
          // ВАЖНО: парсим overall_score (схема ratings table)
          const score = _num(
            latest?.overall_score ??
              latest?.composite_score ??
              latest?.score ??
              0,
          );
          const grade = String(latest?.overall_grade || "");
          return {
            code: c.code,
            name: c.name_short || c.name_ru || c.code,
            score,
            grade,
            isMine: c.id === props.companyId,
          };
        } catch {
          return {
            code: c.code,
            name: c.name_short || c.name_ru || c.code,
            score: 0,
            grade: "",
            isMine: c.id === props.companyId,
          };
        }
      }),
    );
    sectorRanking.value = settled
      .filter((x) => x.status === "fulfilled")
      .map((x: any) => x.value)
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);
  } catch (e: any) {
    errors.sector = e?.message || "Ошибка";
  } finally {
    loading.sector = false;
  }
}

async function loadActivity() {
  loading.activity = true;
  errors.activity = null;
  try {
    // Tasks (активность через updated_at; audit_logs не существует)
    const r = await api.get(`/tasks?company_id=${props.companyId}`);
    const tasks = _arr(r.data);
    const sorted = [...tasks].sort((a: any, b: any) => {
      const ta = new Date(a.updated_at || a.created_at || 0).getTime();
      const tb = new Date(b.updated_at || b.created_at || 0).getTime();
      return tb - ta;
    });
    activityData.value = sorted.slice(0, 5).map((t: any) => ({
      type: "Задача",
      title: t.title || t.name || "Без названия",
      iso: t.updated_at || t.created_at || "",
      status: t.status,
    }));
  } catch (e: any) {
    errors.activity = e?.message || "Ошибка";
  } finally {
    loading.activity = false;
  }
}

async function loadKpi() {
  loading.kpi = true;
  errors.kpi = null;
  try {
    const r = await api.get(`/kpi/${props.companyId}/${props.year}`);
    const data = r.data;
    let managers: any[] = [];
    if (data?.managers) managers = _arr(data.managers);
    else if (Array.isArray(data)) managers = data;
    else managers = _arr(data);

    let totW = 0;
    let wSum = 0;
    let totalInd = 0;
    let attCount = 0;
    const mgrs: KpiManagerRow[] = [];

    for (const m of managers) {
      const indicators = _arr(m.indicators);
      let mW = 0;
      let mS = 0;
      let mHasFact = false;

      for (const i of indicators) {
        const p = i.plan_year != null ? _num(i.plan_year) : null;
        const f = i.fact_year != null ? _num(i.fact_year) : null;
        const w = _num(i.weight);
        totalInd++;

        if (p != null && p !== 0 && f != null) {
          const r = Math.min(2, f / p);
          wSum += r * w;
          totW += w;
          mS += r * w;
          mW += w;
          mHasFact = true;
          if (r < 0.9 && w >= 15) attCount++;
        } else if (p != null) {
          totW += w;
          mW += w;
        }
      }

      mgrs.push({
        title: m.short_title || m.title || "—",
        role: m.role,
        progress: mW ? Math.round((mS / mW) * 100) : 0,
        hasFact: mHasFact,
        indicators: indicators.length,
      });
    }

    const overallProgress = totW ? Math.round((wSum / totW) * 100) : 0;
    const hasAnyFact = mgrs.some((m) => m.hasFact);

    kpiData.value = {
      managers: mgrs.slice(0, 6),
      overallProgress,
      totalManagers: mgrs.length,
      totalIndicators: totalInd,
      attentionCount: attCount,
      hasAnyFact,
    };
  } catch (e: any) {
    errors.kpi = e?.message || "Ошибка";
    kpiData.value = {
      managers: [],
      overallProgress: 0,
      totalManagers: 0,
      totalIndicators: 0,
      attentionCount: 0,
      hasAnyFact: false,
    };
  } finally {
    loading.kpi = false;
  }
}

async function loadBp() {
  loading.bp = true;
  errors.bp = null;
  try {
    const r = await api.get(`/bp/raw/${props.companyId}/${props.year}`);
    const data = r.data;
    const items = _arr(data);

    const yearItems = items.filter(
      (x: any) => String(x.period || "").toUpperCase() === "Y",
    );

    // Точные ключи метрик из БД (camelCase): revenue, opProfit, profit
    function getMetric(metricKey: string): BpMetric {
      const it = yearItems.find(
        (x: any) => String(x.metric || "") === metricKey,
      );
      if (!it) {
        return { plan: null, fact: null, expect: null, hasPlan: false, hasFact: false };
      }
      const plan = it.plan != null ? _num(it.plan) : null;
      const fact = it.fact != null ? _num(it.fact) : null;
      const expect = it.expect != null ? _num(it.expect) : null;
      return {
        plan,
        fact,
        expect,
        hasPlan: plan != null,
        hasFact: fact != null,
      };
    }

    const revenue = getMetric("revenue");
    const opProfit = getMetric("opProfit");
    const profit = getMetric("profit");

    let overallPct: number | null = null;
    if (
      revenue.plan != null &&
      revenue.plan !== 0 &&
      revenue.fact != null
    ) {
      overallPct = Math.round((revenue.fact / revenue.plan) * 100);
    }

    const hasData =
      revenue.hasPlan ||
      revenue.hasFact ||
      opProfit.hasPlan ||
      opProfit.hasFact ||
      profit.hasPlan ||
      profit.hasFact;

    bpData.value = {
      revenue,
      opProfit,
      profit,
      overallPct,
      hasData,
    };
  } catch (e: any) {
    errors.bp = e?.message || "Ошибка";
    bpData.value = {
      revenue: { plan: null, fact: null, expect: null, hasPlan: false, hasFact: false },
      opProfit: { plan: null, fact: null, expect: null, hasPlan: false, hasFact: false },
      profit: { plan: null, fact: null, expect: null, hasPlan: false, hasFact: false },
      overallPct: null,
      hasData: false,
    };
  } finally {
    loading.bp = false;
  }
}

// ============================================================
// LIFECYCLE
// ============================================================
async function loadAll() {
  await Promise.allSettled([
    loadEffect(),
    loadDirs(),
    loadSector(),
    loadActivity(),
    loadKpi(),
    loadBp(),
  ]);
}

onMounted(loadAll);
watch(
  () => [props.companyId, props.year],
  () => {
    if (props.companyId) loadAll();
  },
);
</script>

<template>
  <div class="cox-root">
    <!-- ============================================================ -->
    <!-- 1. ЭКОНОМ. ЭФФЕКТ -- из ручного ввода в карточках проектов -->
    <!-- ============================================================ -->
    <section class="cox-section cox-effect">
      <div class="cox-section-label">
        Эконом. эффект · {{ year }}
        <span
          v-if="effectData && effectData.projectsWithEffect > 0"
          class="cox-card-sub"
        >
          {{ effectData.projectsWithEffect }} / {{ effectData.totalProjects }}
          проектов с эффектом
        </span>
      </div>
      <div v-if="loading.effect" class="cox-loading">
        <div class="cox-spinner-sm"></div>
        <span>Извлечение эффекта из карточек проектов...</span>
      </div>
      <!-- Есть эффект -->
      <div
        v-else-if="effectData && effectData.projectsWithEffect > 0"
        class="cox-effect-block"
      >
        <div class="cox-effect-stats">
          <div class="cox-effect-stat">
            <div class="cox-effect-stat-cap">План</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.plannedTotal) }}
            </div>
          </div>
          <div class="cox-effect-stat" data-color="green">
            <div class="cox-effect-stat-cap">Факт</div>
            <div class="cox-effect-stat-num">
              {{ fmtEffectUzs(effectData.realizedTotal) }}
            </div>
          </div>
          <div
            v-if="effectData.plannedTotal > 0"
            class="cox-effect-stat"
            data-color="purple"
          >
            <div class="cox-effect-stat-cap">Выполнение</div>
            <div
              class="cox-effect-stat-num"
              :class="
                pctClassBp(
                  Math.round((effectData.realizedTotal / effectData.plannedTotal) * 100),
                )
              "
            >
              {{ Math.round((effectData.realizedTotal / effectData.plannedTotal) * 100) }}%
            </div>
          </div>
        </div>
        <!-- Top-5 проектов по эффекту -->
        <div v-if="effectData.topProjects.length" class="cox-effect-tops">
          <div class="cox-effect-tops-label">Топ проектов по эффекту:</div>
          <div
            v-for="p in effectData.topProjects"
            :key="p.id"
            class="cox-effect-top-row"
          >
            <span class="cox-effect-top-title">{{ p.title }}</span>
            <span class="cox-effect-top-vals">
              <span class="cox-effect-top-val">
                <span class="cox-effect-top-cap">план</span>
                {{ fmtEffectUzs(p.plannedUzs) }}
              </span>
              <span v-if="p.realizedUzs > 0" class="cox-effect-top-val">
                <span class="cox-effect-top-cap">факт</span>
                {{ fmtEffectUzs(p.realizedUzs) }}
              </span>
            </span>
          </div>
        </div>
      </div>
      <!-- Нет проектов с введённым эффектом -->
      <div
        v-else-if="effectData && effectData.totalProjects > 0"
        class="cox-effect-empty"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <path d="M3 17l6-6 4 4 8-8" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="3" cy="17" r="1.5" fill="currentColor" />
          <circle cx="21" cy="7" r="1.5" fill="currentColor" />
        </svg>
        <div>
          <div class="cox-effect-empty-title">
            Нет проектов с введённым эффектом
          </div>
          <div class="cox-effect-empty-hint">
            Эконом. эффект указывается вручную в карточке проекта/задачи
            ({{ effectData.totalProjects }}
            {{
              effectData.totalProjects === 1 ? "проект" : effectData.totalProjects < 5 ? "проекта" : "проектов"
            }} в {{ year }} году)
          </div>
        </div>
      </div>
      <div v-else class="cox-empty-line">Нет проектов за {{ year }} год</div>
    </section>

    <!-- ============================================================ -->
    <!-- 2-5. Grid 4: По направлениям | Sector | Внимание | Активность -->
    <!-- ============================================================ -->
    <section class="cox-grid-4">
      <!-- 2. По направлениям -->
      <div class="cox-card">
        <div class="cox-card-label">По направлениям</div>
        <div v-if="loading.dirs" class="cox-loading-line">Загрузка...</div>
        <div v-else-if="dirsData.length > 0" class="cox-dirs-list">
          <div
            v-for="(d, i) in dirsData"
            :key="i"
            class="cox-dir-row"
          >
            <span class="cox-dir-name">{{ d.direction }}</span>
            <span class="cox-dir-count">{{ d.count }}</span>
          </div>
        </div>
        <div v-else class="cox-empty-line">Нет направлений</div>
      </div>

      <!-- 3. Sector ranking -->
      <div class="cox-card">
        <div class="cox-card-label">{{ sectorName }}</div>
        <div v-if="loading.sector" class="cox-loading-line">Загрузка...</div>
        <div v-else-if="sectorRanking.length > 0" class="cox-rank-list">
          <div
            v-for="(s, i) in sectorRanking"
            :key="s.code"
            class="cox-rank-row"
            :class="{ 'cox-rank-mine': s.isMine }"
          >
            <span class="cox-rank-pos">{{ i + 1 }}</span>
            <span class="cox-rank-name">{{ s.name }}</span>
            <span
              v-if="s.grade"
              class="cox-rank-grade"
              :class="pctClass(s.score)"
            >
              {{ s.grade }}
            </span>
            <span
              v-else
              class="cox-rank-score"
              :class="pctClass(s.score)"
            >
              {{ s.score > 0 ? s.score.toFixed(1) : '—' }}
            </span>
          </div>
        </div>
        <div v-else class="cox-empty-line">Нет данных по сектору</div>
      </div>

      <!-- 4. Требуют внимания -->
      <div class="cox-card">
        <div class="cox-card-label">
          Требуют внимания
          <span v-if="overdue" class="cox-attention-badge">{{ overdue }}</span>
        </div>
        <div v-if="overdue" class="cox-attention-text">
          <div class="cox-attention-num">{{ overdue }}</div>
          <div class="cox-attention-cap">просрочено</div>
        </div>
        <div v-else class="cox-empty-line">Просроченных нет</div>
      </div>

      <!-- 5. Активность -->
      <div class="cox-card">
        <div class="cox-card-label">Активность</div>
        <div v-if="loading.activity" class="cox-loading-line">Загрузка...</div>
        <div
          v-else-if="activityData.length > 0"
          class="cox-activity-list"
        >
          <div
            v-for="(a, i) in activityData"
            :key="i"
            class="cox-activity-row"
          >
            <div class="cox-activity-title">{{ a.title }}</div>
            <div class="cox-activity-meta">
              <span>{{ a.type }}</span>
              <span class="cox-activity-time">{{ fmtTimeAgo(a.iso) }}</span>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">Нет активности</div>
      </div>
    </section>

    <!-- ============================================================ -->
    <!-- 6-7. Grid 2: KPI · {year} | Бизнес-план · {year} -->
    <!-- ============================================================ -->
    <section class="cox-grid-2">
      <!-- 6. KPI -->
      <div class="cox-card cox-card-tall">
        <div class="cox-card-label">
          KPI · {{ year }}
          <span
            v-if="kpiData && kpiData.totalManagers > 0"
            class="cox-card-sub"
          >
            {{ kpiData.totalManagers }} рук. ·
            {{ kpiData.totalIndicators }} показателей
            <span
              v-if="kpiData.attentionCount > 0"
              class="cox-attention-inline"
            >
              · {{ kpiData.attentionCount }} требуют внимания
            </span>
          </span>
        </div>
        <div v-if="loading.kpi" class="cox-loading-line">Загрузка KPI...</div>
        <div
          v-else-if="kpiData && kpiData.managers.length > 0"
          class="cox-kpi-block"
        >
          <div
            v-if="kpiData.hasAnyFact"
            class="cox-kpi-summary"
          >
            <div
              class="cox-kpi-summary-num"
              :class="pctClassKpi(kpiData.overallProgress)"
            >
              {{ kpiData.overallProgress }}%
            </div>
            <div class="cox-kpi-summary-cap">общий прогресс</div>
          </div>
          <div v-else class="cox-kpi-no-fact">
            Факт не введён ни по одному показателю
          </div>
          <div class="cox-kpi-managers">
            <div
              v-for="(m, i) in kpiData.managers"
              :key="i"
              class="cox-kpi-manager"
              :style="{ animationDelay: `${i * 50}ms` }"
            >
              <div class="cox-kpi-manager-head">
                <span class="cox-kpi-manager-title">{{ m.title }}</span>
                <span
                  v-if="m.hasFact"
                  class="cox-kpi-manager-pct"
                  :class="pctClassKpi(m.progress)"
                >
                  {{ m.progress }}%
                </span>
                <span v-else class="cox-kpi-manager-pct cox-kpi-empty">—</span>
              </div>
              <div class="cox-kpi-bar-track">
                <div
                  v-if="m.hasFact"
                  class="cox-kpi-bar-fill"
                  :class="pctClassKpi(m.progress)"
                  :style="{ width: Math.min(100, m.progress) + '%' }"
                ></div>
              </div>
              <div v-if="m.role" class="cox-kpi-manager-role">{{ m.role }}</div>
            </div>
          </div>
        </div>
        <div v-else class="cox-empty-line">
          Нет KPI данных за {{ year }}
        </div>
      </div>

      <!-- 7. Бизнес-план -->
      <div class="cox-card cox-card-tall">
        <div class="cox-card-label">
          Бизнес-план · {{ year }}
          <span
            v-if="bpData && bpData.overallPct != null"
            class="cox-card-sub-pct"
            :class="pctClassBp(bpData.overallPct)"
          >
            {{ bpData.overallPct }}%
          </span>
        </div>
        <div v-if="loading.bp" class="cox-loading-line">Загрузка БП...</div>
        <div
          v-else-if="bpData && bpData.hasData"
          class="cox-bp-block"
        >
          <!-- 3 строки: Выручка / Опер. прибыль / Чистая прибыль -->
          <template v-for="m in [
              { label: 'Выручка', d: bpData.revenue },
              { label: 'Опер. прибыль', d: bpData.opProfit },
              { label: 'Чистая прибыль', d: bpData.profit },
            ]" :key="m.label">
            <div class="cox-bp-row">
              <div class="cox-bp-row-head">
                <span class="cox-bp-row-label">{{ m.label }}</span>
                <span
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-row-pct"
                  :class="pctClassBp(Math.round((m.d.fact / m.d.plan) * 100))"
                >
                  {{ Math.round((m.d.fact / m.d.plan) * 100) }}%
                </span>
                <span v-else class="cox-bp-row-pct cox-bp-empty">—</span>
              </div>
              <div class="cox-bp-vals">
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">план</span>
                  <span class="cox-bp-val-num" :class="{ 'cox-bp-empty': !m.d.hasPlan }">
                    {{ m.d.hasPlan ? fmtBp(m.d.plan) : '—' }}
                  </span>
                </div>
                <div class="cox-bp-val">
                  <span class="cox-bp-val-cap">факт</span>
                  <span class="cox-bp-val-num cox-bp-fact" :class="{ 'cox-bp-empty': !m.d.hasFact }">
                    {{ m.d.hasFact ? fmtBp(m.d.fact) : '—' }}
                  </span>
                </div>
                <div v-if="m.d.expect != null" class="cox-bp-val">
                  <span class="cox-bp-val-cap">ожид.</span>
                  <span class="cox-bp-val-num">{{ fmtBp(m.d.expect) }}</span>
                </div>
              </div>
              <div class="cox-bp-bar-track">
                <div
                  v-if="m.d.hasPlan && m.d.hasFact && m.d.plan !== 0"
                  class="cox-bp-bar-fill"
                  :class="pctClassBp(Math.round((m.d.fact / m.d.plan) * 100))"
                  :style="{ width: Math.min(100, Math.max(0, Math.round((m.d.fact / m.d.plan) * 100))) + '%' }"
                ></div>
              </div>
            </div>
          </template>
        </div>
        <div v-else class="cox-empty-line">
          Бизнес-план на {{ year }} год не заполнен
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ============================================================ */
/* ROOT */
/* ============================================================ */
.cox-root {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 8px;
}

/* ============================================================ */
/* SECTION LABELS */
/* ============================================================ */
.cox-section-label,
.cox-card-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: rgba(30, 42, 74, 0.55);
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cox-card-sub {
  font-size: 9.5px;
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: rgba(30, 42, 74, 0.4);
  margin-left: auto;
}

/* ============================================================ */
/* CARDS */
/* ============================================================ */
.cox-card {
  background: #ffffff;
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.04);
  transition:
    transform 0.22s cubic-bezier(0.34, 1.2, 0.64, 1),
    box-shadow 0.22s ease;
}
.cox-card:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(15, 23, 60, 0.08);
}
.cox-card-tall {
  min-height: 280px;
}

/* ============================================================ */
/* GRIDS */
/* ============================================================ */
.cox-grid-4 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}
.cox-grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
@media (max-width: 1100px) {
  .cox-grid-4 {
    grid-template-columns: repeat(2, 1fr);
  }
}
@media (max-width: 720px) {
  .cox-grid-4,
  .cox-grid-2 {
    grid-template-columns: 1fr;
  }
}

/* ============================================================ */
/* 1. ЭКОНОМ. ЭФФЕКТ */
/* ============================================================ */
.cox-effect {
  background: linear-gradient(
    135deg,
    rgba(127, 119, 221, 0.04) 0%,
    rgba(29, 158, 117, 0.03) 100%
  );
  border: 1px solid rgba(30, 42, 74, 0.06);
  border-radius: 10px;
  padding: 14px 18px;
}
.cox-effect-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cox-effect-stats {
  display: flex;
  gap: 32px;
  flex-wrap: wrap;
}
.cox-effect-stat {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 100px;
}
.cox-effect-stat-cap {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.5);
}
.cox-effect-stat-num {
  font-size: 20px;
  font-weight: 500;
  letter-spacing: -0.025em;
  color: #1e2a4a;
  line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.cox-effect-stat[data-color="green"] .cox-effect-stat-num {
  color: #1d9e75;
}
.cox-effect-stat[data-color="purple"] .cox-effect-stat-num {
  color: #7f77dd;
}
.cox-effect-tops {
  padding-top: 10px;
  border-top: 1px dashed rgba(30, 42, 74, 0.08);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-effect-tops-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.5);
  margin-bottom: 4px;
}
.cox-effect-top-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-size: 12px;
}
.cox-effect-top-title {
  flex: 1;
  color: #1e2a4a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cox-effect-top-vals {
  display: flex;
  gap: 14px;
  flex-shrink: 0;
}
.cox-effect-top-val {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
  color: #1e2a4a;
}
.cox-effect-top-cap {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: rgba(30, 42, 74, 0.4);
  margin-right: 4px;
  font-weight: 500;
}
.cox-effect-empty {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 8px 4px;
  color: rgba(30, 42, 74, 0.55);
}
.cox-effect-empty-title {
  font-size: 13px;
  color: #1e2a4a;
  font-weight: 500;
  margin-bottom: 2px;
}
.cox-effect-empty-hint {
  font-size: 11.5px;
  line-height: 1.5;
  color: rgba(30, 42, 74, 0.55);
}

/* ============================================================ */
/* 2. ПО НАПРАВЛЕНИЯМ */
/* ============================================================ */
.cox-dirs-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cox-dir-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  font-size: 12px;
  border-bottom: 1px dashed rgba(30, 42, 74, 0.06);
}
.cox-dir-row:last-child {
  border-bottom: none;
}
.cox-dir-name {
  color: rgba(30, 42, 74, 0.78);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.cox-dir-count {
  font-weight: 500;
  color: #7f77dd;
  background: rgba(127, 119, 221, 0.08);
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 11px;
}

/* ============================================================ */
/* 3. SECTOR RANKING */
/* ============================================================ */
.cox-rank-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-rank-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  transition: background 0.18s;
}
.cox-rank-mine {
  background: rgba(127, 119, 221, 0.1);
  font-weight: 500;
}
.cox-rank-pos {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(30, 42, 74, 0.08);
  color: rgba(30, 42, 74, 0.65);
  border-radius: 50%;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.cox-rank-mine .cox-rank-pos {
  background: #7f77dd;
  color: #ffffff;
}
.cox-rank-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #1e2a4a;
}
.cox-rank-score {
  font-weight: 600;
  font-size: 11.5px;
}

/* ============================================================ */
/* 4. ВНИМАНИЕ */
/* ============================================================ */
.cox-attention-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: 8px;
  background: #e24b4a;
  color: #ffffff;
  font-size: 10px;
  font-weight: 600;
  text-transform: none;
  letter-spacing: 0;
}
.cox-attention-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
}
.cox-attention-num {
  font-size: 28px;
  font-weight: 400;
  color: #e24b4a;
  letter-spacing: -0.025em;
  line-height: 1;
}
.cox-attention-cap {
  font-size: 11px;
  color: rgba(226, 75, 74, 0.7);
}

/* ============================================================ */
/* 5. АКТИВНОСТЬ */
/* ============================================================ */
.cox-activity-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.cox-activity-row {
  padding: 5px 0;
  border-bottom: 1px dashed rgba(30, 42, 74, 0.06);
  animation: coxFadeUp 0.4s both;
}
.cox-activity-row:last-child {
  border-bottom: none;
}
.cox-activity-title {
  font-size: 11.5px;
  color: #1e2a4a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 2px;
}
.cox-activity-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: rgba(30, 42, 74, 0.5);
}
.cox-activity-time {
  font-weight: 500;
}

/* ============================================================ */
/* 6. KPI */
/* ============================================================ */
.cox-kpi-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.cox-kpi-summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(127, 119, 221, 0.05);
  border-left: 3px solid #7f77dd;
  border-radius: 6px;
}
.cox-kpi-summary-num {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  line-height: 1;
}
.cox-kpi-summary-cap {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.6);
}

.cox-kpi-managers {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 230px;
  overflow-y: auto;
}
.cox-kpi-manager {
  display: flex;
  flex-direction: column;
  gap: 3px;
  animation: coxFadeUp 0.4s both;
}
.cox-kpi-manager-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 11.5px;
}
.cox-kpi-manager-title {
  color: #1e2a4a;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}
.cox-kpi-manager-pct {
  font-weight: 600;
  font-size: 11px;
  flex-shrink: 0;
}
.cox-kpi-bar-track {
  height: 5px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 3px;
  overflow: hidden;
}
.cox-kpi-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.7s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cox-kpi-bar-fill.cox-pct-green {
  background: linear-gradient(90deg, #1d9e75, #2cb98a);
}
.cox-kpi-bar-fill.cox-pct-blue {
  background: linear-gradient(90deg, #378add, #5ba4e3);
}
.cox-kpi-bar-fill.cox-pct-amber {
  background: linear-gradient(90deg, #ef9f27, #f5b54e);
}
.cox-kpi-bar-fill.cox-pct-red {
  background: linear-gradient(90deg, #e24b4a, #f06866);
}
.cox-kpi-manager-role {
  font-size: 10px;
  color: rgba(30, 42, 74, 0.4);
  margin-top: 1px;
}

/* ============================================================ */
/* 7. БП */
/* ============================================================ */
.cox-bp-block {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cox-bp-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.cox-bp-row-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.cox-bp-row-label {
  font-size: 12px;
  font-weight: 500;
  color: #1e2a4a;
}
.cox-bp-row-pct {
  font-weight: 600;
  font-size: 13px;
}
.cox-bp-vals {
  display: flex;
  gap: 14px;
  font-size: 11px;
  flex-wrap: wrap;
}
.cox-bp-val {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.cox-bp-val-cap {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(30, 42, 74, 0.45);
}
.cox-bp-val-num {
  font-weight: 500;
  color: #1e2a4a;
  font-size: 12.5px;
}
.cox-bp-bar-track {
  height: 6px;
  background: rgba(30, 42, 74, 0.05);
  border-radius: 3px;
  overflow: hidden;
}
.cox-bp-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.7s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.cox-bp-bar-fill.cox-pct-green {
  background: linear-gradient(90deg, #1d9e75, #2cb98a);
}
.cox-bp-bar-fill.cox-pct-blue {
  background: linear-gradient(90deg, #378add, #5ba4e3);
}
.cox-bp-bar-fill.cox-pct-amber {
  background: linear-gradient(90deg, #ef9f27, #f5b54e);
}
.cox-bp-bar-fill.cox-pct-red {
  background: linear-gradient(90deg, #e24b4a, #f06866);
}

/* ============================================================ */
/* PCT COLORS (text) */
/* ============================================================ */
.cox-pct-green {
  color: #1d9e75;
}
.cox-pct-blue {
  color: #378add;
}
.cox-pct-amber {
  color: #ef9f27;
}
.cox-pct-red {
  color: #e24b4a;
}

/* === Дополнительные элементы v8.2 === */
.cox-attention-inline {
  color: #e24b4a;
  font-weight: 600;
}
.cox-card-sub-pct {
  font-size: 14px;
  font-weight: 500;
  margin-left: auto;
  text-transform: none;
  letter-spacing: 0;
}
.cox-rank-grade {
  font-weight: 600;
  font-size: 12px;
  padding: 1px 7px;
  border-radius: 5px;
  background: rgba(30, 42, 74, 0.04);
}
.cox-bp-empty,
.cox-kpi-empty {
  color: rgba(30, 42, 74, 0.35) !important;
  font-style: italic;
  font-weight: 400 !important;
}
.cox-kpi-no-fact {
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.5);
  font-style: italic;
  padding: 6px 10px;
  background: rgba(30, 42, 74, 0.03);
  border-radius: 6px;
}
.cox-bp-fact {
  font-weight: 600 !important;
}

/* ============================================================ */
/* LOADING / EMPTY */
/* ============================================================ */
.cox-loading,
.cox-loading-line {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.4);
  padding: 8px 0;
}
.cox-spinner-sm {
  width: 12px;
  height: 12px;
  border: 1.5px solid rgba(127, 119, 221, 0.2);
  border-top-color: #7f77dd;
  border-radius: 50%;
  animation: coxSpin 0.7s linear infinite;
}
.cox-empty-line {
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.35);
  font-style: italic;
  padding: 12px 0;
  text-align: center;
}

/* ============================================================ */
/* ANIMATIONS */
/* ============================================================ */
@keyframes coxFadeUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@keyframes coxSpin {
  to {
    transform: rotate(360deg);
  }
}
</style>
