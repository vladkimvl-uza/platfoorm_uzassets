<script setup lang="ts">
/**
 *
 * Layout 1:1:
 *  Topbar: "ESG-рейтинги портфеля" · X компаний · Y с рейтингом · Z секторов
 *  KPI strip (4 cells с corner icons): Покрытие / Лидер / Без рейтинга / Обновления
 *  Mid 3-col: Donut (multi-segment по секторам) + Лидеры топ-5 + Зона внимания
 *  Sector breakdown — мини-доноты per sector
 *  Rankings table (детализация)
 *
 * хранит только E/S/G + overall_score 0-100. Letter rating восстанавливаем через
 * _esgScoreToRating. Donut агрегируем по секторам (вместо агентств).
 */
import { computed, onMounted, ref } from "vue";
import {
  esgApi,
  type ESGCompanyScore,
  type ESGOverviewResponse,
  type Pillar,
} from "@/api/esg";
import ESGCompanyDetailModal from "@/components/ESG/ESGCompanyDetailModal.vue";

const overview = ref<ESGOverviewResponse | null>(null);
const year = ref<number | null>(null);
const sectorCode = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const drillCompanyId = ref<string | null>(null);
const drillYear = ref<number | undefined>(undefined);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    overview.value = await esgApi.getOverview({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
      rankings_limit: 50,
    });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить дашборд";
  } finally {
    loading.value = false;
  }
}

function onYearChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value;
  year.value = v ? parseInt(v, 10) : null;
  load();
}
function onSectorChange(e: Event) {
  sectorCode.value = (e.target as HTMLSelectElement).value || null;
  load();
}
function openDrill(id: string, yr: number | null) {
  drillCompanyId.value = id;
  drillYear.value = yr ?? undefined;
}
async function onDetailSaved() { await load(); }

// ──────────────────────────────────────────────────────────────────
//   Backend дает 0-100 → нормализуем /10
// ──────────────────────────────────────────────────────────────────

function scoreToRating(score: number | null | undefined): string {
  if (score == null) return "—";
  const s = score / 10; // backend 0-100 → 0-10
  if (s >= 9.3) return "AA";
  if (s >= 8.5) return "AA-";
  if (s >= 8.0) return "A+";
  if (s >= 7.5) return "A";
  if (s >= 7.0) return "A-";
  if (s >= 6.5) return "BBB+";
  if (s >= 5.8) return "BBB";
  if (s >= 5.2) return "BBB-";
  if (s >= 4.6) return "BB+";
  if (s >= 4.0) return "BB";
  if (s >= 3.4) return "BB-";
  if (s >= 3.0) return "B+";
  if (s >= 2.5) return "B";
  if (s >= 2.0) return "B-";
  if (s >= 1.6) return "CCC+";
  if (s >= 1.2) return "CCC";
  if (s >= 0.8) return "CCC-";
  if (s >= 0.4) return "CC";
  return "C";
}

function ratingBg(score: number | null | undefined): { bg: string; fg: string } {
  if (score == null) return { bg: "#F1F5F9", fg: "#64748B" };
  const s = score / 10;
  if (s >= 7.0)  return { bg: "#DCFCE7", fg: "#1D9E75" };  // A range
  if (s >= 5.2)  return { bg: "rgba(55,138,221,.10)", fg: "#378ADD" }; // BBB
  if (s >= 3.4)  return { bg: "#FEF9C3", fg: "#D97706" }; // BB / B
  return { bg: "#FEE2E2", fg: "#EF4444" };  // CCC / D
}

// Company abbreviation (UGE, NGMK, AGMK style)
function abbr(co: ESGCompanyScore): string {
  if (co.company_code && co.company_code.length <= 6) {
    return co.company_code.toUpperCase();
  }
  const n = (co.company_name || co.company_code || "?").replace(/АО\s*«?|»|\s+/g, " ").trim();
  return n.split(" ").map(w => w[0] || "").join("").toUpperCase().slice(0, 4);
}

function shortName(n: string): string {
  return n.length > 22 ? n.slice(0, 20) + "…" : n;
}

// ──────────────────────────────────────────────────────────────────
//   Sector colors + meta
// ──────────────────────────────────────────────────────────────────

const SECTOR_COLORS: Record<string, string> = {
  mining: "#9B8EC4", oil_gas: "#1D9E75", oilgas: "#1D9E75",
  energy: "#EF9F27", transport: "#378ADD", telecom: "#D4537E",
  finance: "#534AB7", chemical: "#A855F7", other: "#888780",
};
function sectorColor(code: string | null): string {
  if (!code) return "#888780";
  return SECTOR_COLORS[code.toLowerCase().replace(/-/g, "_")] || "#888780";
}

const SECTOR_LABELS: Record<string, string> = {
  mining: "Горнодобыча", oil_gas: "Нефтегаз", oilgas: "Нефтегаз",
  energy: "Энергетика", transport: "Транспорт", telecom: "Телеком",
  finance: "Финансы", chemical: "Химия", other: "Другие",
};
function sectorLabel(code: string | null): string {
  if (!code) return "Другие";
  return SECTOR_LABELS[code.toLowerCase().replace(/-/g, "_")] || code;
}

// ──────────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────────

const ratedCount = computed(() => {
  const rows = overview.value?.rankings ?? [];
  return rows.filter(r => r.overall_score != null).length;
});

const totalCos = computed(() => overview.value?.kpis.total_companies ?? 0);
const noRatingCount = computed(() => totalCos.value - ratedCount.value);
const coveragePct = computed(() => totalCos.value > 0 ? Math.round((ratedCount.value / totalCos.value) * 100) : 0);

const topCompany = computed<ESGCompanyScore | null>(() => {
  const rows = overview.value?.rankings ?? [];
  const rated = rows.filter(r => r.overall_score != null);
  if (!rated.length) return null;
  return rated.reduce((b, c) => (c.overall_score ?? 0) > (b.overall_score ?? 0) ? c : b, rated[0]);
});

const updatesCount = computed(() => {
  const rows = overview.value?.rankings ?? [];
  return rows.filter(r => r.last_year_reported != null).length;
});

// ──────────────────────────────────────────────────────────────────
//   Donut: multi-segment by sector (proxy for agency split since
//   backend doesn't store agency data) + uncovered slice
// ──────────────────────────────────────────────────────────────────

const DONUT_R = 70;
const DONUT_C = 2 * Math.PI * DONUT_R;

interface DonutSeg {
  label: string;
  color: string;
  count: number;
  pct: number;
  len: number;
  offset: number;
}

const donutSegs = computed<DonutSeg[]>(() => {
  const rows = overview.value?.rankings ?? [];
  const total = totalCos.value;
  if (total === 0) return [];

  const bySec: Record<string, number> = {};
  for (const r of rows) {
    if (r.overall_score == null) continue;
    const code = r.sector_code || "other";
    bySec[code] = (bySec[code] || 0) + 1;
  }

  const segs: DonutSeg[] = [];
  let offset = 0;
  for (const [code, count] of Object.entries(bySec).sort((a, b) => b[1] - a[1])) {
    const pct = Math.round((count / total) * 100);
    const len = (count / total) * DONUT_C;
    segs.push({
      label: sectorLabel(code),
      color: sectorColor(code),
      count,
      pct,
      len,
      offset: -offset,
    });
    offset += len;
  }
  // Uncovered slice
  if (noRatingCount.value > 0) {
    const pct = Math.round((noRatingCount.value / total) * 100);
    const len = (noRatingCount.value / total) * DONUT_C;
    segs.push({
      label: "Без рейтинга",
      color: "#E2E8F0",
      count: noRatingCount.value,
      pct,
      len,
      offset: -offset,
    });
  }
  return segs;
});

// ──────────────────────────────────────────────────────────────────
//   Leaders (top-5 by overall_score)
// ──────────────────────────────────────────────────────────────────

const leaders = computed<ESGCompanyScore[]>(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  return rows
    .filter(r => r.overall_score != null)
    .sort((a, b) => (b.overall_score ?? -1) - (a.overall_score ?? -1))
    .slice(0, 5);
});

// ──────────────────────────────────────────────────────────────────
//   Updates / attention (use recent-year-reported as proxy)
// ──────────────────────────────────────────────────────────────────

interface UpdateItem {
  co: ESGCompanyScore;
  year: number;
  rating: string;
  score: number | null;
}

const recentUpdates = computed<UpdateItem[]>(() => {
  const rows = overview.value?.rankings ?? [];
  return rows
    .filter(r => r.last_year_reported != null && r.overall_score != null)
    .sort((a, b) => (b.last_year_reported ?? 0) - (a.last_year_reported ?? 0))
    .slice(0, 5)
    .map(r => ({
      co: r,
      year: r.last_year_reported as number,
      rating: scoreToRating(r.overall_score),
      score: r.overall_score,
    }));
});

// ──────────────────────────────────────────────────────────────────
//   E/S/G pillars
// ──────────────────────────────────────────────────────────────────

const PILLAR_META: Record<Pillar, { label: string; color: string }> = {
  E: { label: "Environmental", color: "#1D9E75" },
  S: { label: "Social", color: "#378ADD" },
  G: { label: "Governance", color: "#7F77DD" },
};

// ──────────────────────────────────────────────────────────────────
//   Sector breakdown (mini-donuts)
// ──────────────────────────────────────────────────────────────────

interface SectorBlock {
  code: string;
  label: string;
  color: string;
  total: number;
  rated: number;
  ratedPct: number;
  topName: string | null;
  topScore: number | null;
}

const sectorBreakdown = computed<SectorBlock[]>(() => {
  const rows = overview.value?.rankings ?? [];
  const allCos = overview.value?.kpis.total_companies ?? 0;
  // Group by sector
  const bySec: Record<string, ESGCompanyScore[]> = {};
  for (const r of rows) {
    const code = r.sector_code || "other";
    if (!bySec[code]) bySec[code] = [];
    bySec[code].push(r);
  }
  // We don't have full company list per sector (only those with data) - approximate
  return Object.entries(bySec).map(([code, list]) => {
    const rated = list.filter(r => r.overall_score != null);
    const total = list.length;
    const top = rated.length ? rated.reduce((b, c) => (c.overall_score ?? 0) > (b.overall_score ?? 0) ? c : b, rated[0]) : null;
    return {
      code,
      label: sectorLabel(code),
      color: sectorColor(code),
      total,
      rated: rated.length,
      ratedPct: total > 0 ? Math.round((rated.length / total) * 100) : 0,
      topName: top ? (top.company_name || top.company_code) : null,
      topScore: top?.overall_score ?? null,
    };
  }).sort((a, b) => b.ratedPct - a.ratedPct);
});

// Mini-donut SVG dasharray helper
const MINI_R = 22;
const MINI_C = 2 * Math.PI * MINI_R;
function miniDonutDasharray(pct: number): string {
  const filled = (pct / 100) * MINI_C;
  return `${filled} ${MINI_C - filled}`;
}

// ──────────────────────────────────────────────────────────────────
//   Rankings (full table)
// ──────────────────────────────────────────────────────────────────

type RankSort = "overall" | "e" | "s" | "g" | "issues";
const rankSort = ref<RankSort>("overall");

const sortedRankings = computed<ESGCompanyScore[]>(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  const k = rankSort.value;
  const getter: Record<RankSort, (r: ESGCompanyScore) => number> = {
    overall: r => r.overall_score ?? -1,
    e: r => r.e_score ?? -1,
    s: r => r.s_score ?? -1,
    g: r => r.g_score ?? -1,
    issues: r => -((r.issues_critical || 0) * 10 + (r.issues_open || 0)),
  };
  rows.sort((a, b) => getter[k](b) - getter[k](a));
  return rows;
});

const pillarStats = computed(() => overview.value?.pillars ?? []);

onMounted(() => { load(); });
</script>

<template>
  <Transition name="uza-fade" mode="out-in">
    <div :key="String(year ?? '_')">
      <div class="ev-view">

        <!-- ═══ Topbar (dark navy gradient) ═══ -->
        <div class="ev-topbar">
          <div class="ev-tb-l">
            <div class="ev-tb-title">ESG-рейтинги портфеля</div>
            <div class="ev-tb-sub">
              <span><b>{{ totalCos }}</b> компаний</span>
              <span class="dot">·</span>
              <span><b>{{ ratedCount }}</b> с рейтингом</span>
              <span class="dot">·</span>
              <span><b>{{ overview?.sectors?.length || 0 }}</b> секторов</span>
            </div>
          </div>
          <div class="ev-tb-r">
            <select :value="String(year || '')" @change="onYearChange" class="ev-in">
              <option value="">Все годы</option>
              <option v-for="y in (overview?.available_years || [])" :key="y" :value="y">{{ y }}</option>
            </select>
            <select :value="sectorCode || ''" @change="onSectorChange" class="ev-in">
              <option value="">Все сектора</option>
              <option v-for="s in (overview?.sectors || [])" :key="s.code" :value="s.code">
                {{ s.code }} ({{ s.count }})
              </option>
            </select>
          </div>
        </div>

        <div v-if="loading && !overview" class="ev-loading">Загрузка...</div>
        <div v-else-if="error && !overview" class="ev-error">{{ error }}</div>

        <div v-else-if="overview" class="ev-body">

          <div class="ev-kpi-strip">
            <div class="ev-kpi-cell ev-kpi-cov" style="--d:40ms">
              <div class="ev-kpi-head">
                <span class="ev-kpi-lbl">Покрытие</span>
                <span class="ev-kpi-icn ok">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8.5l3 3 7-7"/></svg>
                </span>
              </div>
              <div class="ev-kpi-vw">
                <span class="ev-kpi-v">{{ ratedCount }}</span>
                <span class="ev-kpi-of">/{{ totalCos }}</span>
              </div>
              <div class="ev-kpi-sub">с хотя бы одним <b>рейтингом · {{ coveragePct }}%</b></div>
            </div>

            <div class="ev-kpi-cell ev-kpi-leader" style="--d:90ms">
              <div class="ev-kpi-head">
                <span class="ev-kpi-lbl">Лидер</span>
                <span class="ev-kpi-icn amber">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 2h6v3a3 3 0 01-3 3 3 3 0 01-3-3V2zM8 8v3M5 14h6"/><path d="M11 3h2v2a2 2 0 01-2 2M5 3H3v2a2 2 0 002 2"/></svg>
                </span>
              </div>
              <div class="ev-kpi-leader-name">{{ topCompany ? shortName(topCompany.company_name || topCompany.company_code) : "—" }}</div>
              <div class="ev-kpi-sub" v-if="topCompany && topCompany.overall_score != null">
                <span :style="{ color: ratingBg(topCompany.overall_score).fg }">
                  <b>{{ scoreToRating(topCompany.overall_score) }}</b>
                </span> · {{ topCompany.overall_score.toFixed(0) }} баллов
              </div>
              <div class="ev-kpi-sub" v-else>нет данных</div>
            </div>

            <div class="ev-kpi-cell ev-kpi-norating" style="--d:140ms">
              <div class="ev-kpi-head">
                <span class="ev-kpi-lbl">Без рейтинга</span>
                <span class="ev-kpi-icn red">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 1l7 13H1L8 1z"/><path d="M8 6v3M8 11h.01"/></svg>
                </span>
              </div>
              <div class="ev-kpi-vw">
                <span class="ev-kpi-v">{{ noRatingCount }}</span>
                <span class="ev-kpi-of-text">компаний</span>
              </div>
              <div class="ev-kpi-sub">
                <span style="color:#EF4444"><b>{{ totalCos > 0 ? Math.round(noRatingCount / totalCos * 100) : 0 }}%</b></span> портфеля · нужны рейтинги
              </div>
            </div>

            <div class="ev-kpi-cell ev-kpi-updates" style="--d:190ms">
              <div class="ev-kpi-head">
                <span class="ev-kpi-lbl">Обновления</span>
                <span class="ev-kpi-icn blue">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2 11 5 8 8 11 14 5"/><polyline points="10 5 14 5 14 9"/></svg>
                </span>
              </div>
              <div class="ev-kpi-vw">
                <span class="ev-kpi-v" style="color:#1D9E75">+{{ updatesCount }}</span>
              </div>
              <div class="ev-kpi-sub">за <b>текущий и прошлый год</b></div>
            </div>
          </div>

          <!-- ═══ 2. Mid 3-col grid: Donut + Leaders + Updates ═══ -->
          <div class="ev-mid-grid">

            <!-- Donut Coverage -->
            <div class="ev-panel" style="--d:340ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
                  Покрытие портфеля
                </h3>
                <span class="ev-panel-meta">по секторам</span>
              </div>
              <div class="ev-panel-body">
                <div class="ev-donut-wrap">
                  <div class="ev-donut-cv-wrap">
                    <svg viewBox="0 0 180 180" style="width:150px;height:150px">
                      <circle cx="90" cy="90" r="70" fill="none" stroke="#F4F3F9" stroke-width="14"/>
                      <circle v-for="(s, i) in donutSegs" :key="i"
                        cx="90" cy="90" r="70" fill="none"
                        :stroke="s.color" stroke-width="14"
                        :stroke-dasharray="`${s.len} ${DONUT_C - s.len}`"
                        :stroke-dashoffset="s.offset"
                        stroke-linecap="butt"
                        transform="rotate(-90 90 90)"/>
                    </svg>
                    <div class="ev-donut-center">
                      <div class="ev-donut-v">{{ coveragePct }}%</div>
                      <div class="ev-donut-l">ПОКРЫТИЕ</div>
                    </div>
                  </div>
                  <div class="ev-donut-legend">
                    <div v-for="(s, i) in donutSegs" :key="i" class="ev-donut-leg-row">
                      <span class="ev-leg-bullet" :style="{ background: s.color }"></span>
                      <span class="ev-leg-lbl">{{ s.label }}</span>
                      <span class="ev-leg-cnt">{{ s.count }}</span>
                      <span class="ev-leg-pct">· {{ s.pct }}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- Leaders -->
            <div class="ev-panel" style="--d:390ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                  Лидеры портфеля
                </h3>
                <span class="ev-panel-meta">топ-5</span>
              </div>
              <div class="ev-panel-body" style="padding:8px 18px">
                <div v-if="!leaders.length" class="ev-empty-inline">Нет рейтингов в портфеле</div>
                <div
                  v-for="(r, i) in leaders"
                  :key="r.company_id"
                  class="ev-leader-row"
                  :style="{ '--d': (i * 60) + 'ms' }"
                  @click="openDrill(r.company_id, r.last_year_reported)"
                >
                  <div class="ev-leader-rank">{{ i + 1 }}</div>
                  <div class="ev-leader-abbr" :style="{ background: sectorColor(r.sector_code) + '20', color: sectorColor(r.sector_code) }">
                    {{ abbr(r) }}
                  </div>
                  <div class="ev-leader-info">
                    <div class="ev-leader-name">{{ r.company_name || r.company_code }}</div>
                    <div class="ev-leader-sec">{{ sectorLabel(r.sector_code) }}</div>
                  </div>
                  <div class="ev-leader-rating" :style="{ background: ratingBg(r.overall_score).bg, color: ratingBg(r.overall_score).fg }">
                    {{ scoreToRating(r.overall_score) }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Updates -->
            <div class="ev-panel" style="--d:440ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  Последние обновления
                </h3>
                <span class="ev-panel-meta">{{ recentUpdates.length }} за период</span>
              </div>
              <div class="ev-panel-body" style="padding:8px 18px">
                <div v-if="!recentUpdates.length" class="ev-empty-inline">Нет недавних обновлений</div>
                <div
                  v-for="(u, i) in recentUpdates"
                  :key="u.co.company_id"
                  class="ev-upd-row"
                  :style="{ '--d': (i * 60) + 'ms', '--esg-dot': sectorColor(u.co.sector_code) }"
                  @click="openDrill(u.co.company_id, u.year)"
                >
                  <div class="ev-upd-dot"></div>
                  <div class="ev-upd-info">
                    <div class="ev-upd-text">
                      <b>{{ shortName(u.co.company_name || u.co.company_code) }}</b>
                      · ESG {{ u.rating }}
                      <span v-if="u.score != null">· {{ u.score.toFixed(0) }}</span>
                    </div>
                    <div class="ev-upd-time">FY {{ u.year }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══ 3. Sector breakdown (mini-donuts) ═══ -->
          <div class="ev-panel ev-sector-panel" style="--d:520ms">
            <div class="ev-panel-h">
              <h3>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                Срез по секторам
              </h3>
              <span class="ev-panel-meta">{{ sectorBreakdown.length }} секторов</span>
            </div>
            <div class="ev-panel-body">
              <div class="ev-sector-row">
                <div v-for="(sec, i) in sectorBreakdown" :key="sec.code" class="ev-sec-card" :style="{ '--d': (i * 60) + 'ms' }">
                  <div class="ev-sec-hd">
                    <span class="ev-sec-name">{{ sec.label }}</span>
                    <span class="ev-sec-count">{{ sec.rated }} / {{ sec.total }}</span>
                  </div>
                  <div class="ev-sec-body">
                    <div class="ev-sec-mini-donut">
                      <svg viewBox="0 0 60 60" style="width:54px;height:54px">
                        <circle cx="30" cy="30" r="22" fill="none" stroke="#F4F3F9" stroke-width="6"/>
                        <circle cx="30" cy="30" r="22" fill="none"
                          :stroke="sec.color" stroke-width="6"
                          :stroke-dasharray="miniDonutDasharray(sec.ratedPct)"
                          stroke-dashoffset="0" stroke-linecap="round"
                          transform="rotate(-90 30 30)"/>
                      </svg>
                      <div class="ev-sec-mini-v">{{ sec.ratedPct }}%</div>
                    </div>
                    <div class="ev-sec-leader">
                      <div class="ev-sec-leader-l">ЛИДЕР</div>
                      <div class="ev-sec-leader-n" v-if="sec.topName">{{ shortName(sec.topName) }}</div>
                      <div class="ev-sec-leader-n" v-else style="color:#888780">—</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══ 4. E/S/G pillars row ═══ -->
          <div v-if="pillarStats.length" class="ev-pillars-row">
            <div
              v-for="(p, i) in pillarStats"
              :key="p.pillar"
              class="ev-pillar-card"
              :style="{ '--d': (580 + i * 50) + 'ms', '--ac': PILLAR_META[p.pillar].color }"
            >
              <div class="ev-pillar-head">
                <span class="ev-pillar-letter" :style="{ background: PILLAR_META[p.pillar].color }">{{ p.pillar }}</span>
                <div class="ev-pillar-h-info">
                  <div class="ev-pillar-h-ttl">{{ PILLAR_META[p.pillar].label }}</div>
                  <div class="ev-pillar-h-meta">{{ p.metric_count }} метрик · {{ p.company_count }} компаний</div>
                </div>
              </div>
              <div class="ev-pillar-stat">
                <div class="ev-pillar-stat-l">Средн. достижение цели</div>
                <div class="ev-pillar-stat-v" :style="{ color: PILLAR_META[p.pillar].color }">
                  {{ p.avg_target_attainment != null ? p.avg_target_attainment.toFixed(0) + "%" : "—" }}
                </div>
              </div>
              <div class="ev-pillar-bar-wrap">
                <div class="ev-pillar-bar-fill" :style="{ '--w': (p.avg_target_attainment ?? 0) + '%', background: PILLAR_META[p.pillar].color }"></div>
              </div>
              <div class="ev-pillar-foot">
                <span class="ev-pillar-foot-ok">{{ p.on_target_count }} на цели</span>
                ·
                <span class="ev-pillar-foot-bad">{{ p.behind_count }} ниже</span>
              </div>
            </div>
          </div>

          <!-- ═══ 5. Rankings table (детализация) ═══ -->
          <div class="ev-panel" style="--d:740ms">
            <div class="ev-panel-h">
              <h3>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                Детализация — группировка по секторам
              </h3>
              <div class="ev-rank-seg">
                <button :class="{ on: rankSort === 'overall' }" @click="rankSort = 'overall'">Общий</button>
                <button :class="{ on: rankSort === 'e' }" @click="rankSort = 'e'">E</button>
                <button :class="{ on: rankSort === 's' }" @click="rankSort = 's'">S</button>
                <button :class="{ on: rankSort === 'g' }" @click="rankSort = 'g'">G</button>
                <button :class="{ on: rankSort === 'issues' }" @click="rankSort = 'issues'">Вопросы</button>
              </div>
            </div>
            <div class="ev-rank-body">
              <table class="ev-rank-tbl">
                <thead>
                  <tr>
                    <th class="lt">Компания</th>
                    <th>E</th>
                    <th>S</th>
                    <th>G</th>
                    <th>Общий</th>
                    <th>Рейтинг</th>
                    <th>Метрик</th>
                    <th>Вопросов</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(r, i) in sortedRankings"
                    :key="r.company_id"
                    :style="{ '--d': (Math.min(i, 30) * 20) + 'ms' }"
                    @click="openDrill(r.company_id, r.last_year_reported)"
                  >
                    <td class="lt">
                      <div class="ev-rt-abbr" :style="{ background: sectorColor(r.sector_code) + '20', color: sectorColor(r.sector_code) }">
                        {{ abbr(r) }}
                      </div>
                      <div class="ev-rt-name-wrap">
                        <div class="ev-rt-name">{{ r.company_name || r.company_code }}</div>
                        <div class="ev-rt-sub">
                          <span>{{ sectorLabel(r.sector_code) }}</span>
                          <span v-if="r.last_year_reported" class="ev-rt-yr">FY{{ r.last_year_reported }}</span>
                        </div>
                      </div>
                    </td>
                    <td class="num"><span :style="{ color: ratingBg(r.e_score).fg }">{{ r.e_score != null ? r.e_score.toFixed(0) : '—' }}</span></td>
                    <td class="num"><span :style="{ color: ratingBg(r.s_score).fg }">{{ r.s_score != null ? r.s_score.toFixed(0) : '—' }}</span></td>
                    <td class="num"><span :style="{ color: ratingBg(r.g_score).fg }">{{ r.g_score != null ? r.g_score.toFixed(0) : '—' }}</span></td>
                    <td class="num">
                      <span class="ev-score-num" :style="{ color: ratingBg(r.overall_score).fg }">
                        {{ r.overall_score != null ? r.overall_score.toFixed(0) : '—' }}
                      </span>
                    </td>
                    <td class="num">
                      <span class="ev-rating-pill" :style="{ background: ratingBg(r.overall_score).bg, color: ratingBg(r.overall_score).fg }">
                        {{ scoreToRating(r.overall_score) }}
                      </span>
                    </td>
                    <td class="num">{{ r.metric_count }}</td>
                    <td class="num">
                      <span v-if="r.issues_critical" class="ev-iss-c">{{ r.issues_critical }}</span>
                      <span v-else-if="r.issues_open" class="ev-iss-o">{{ r.issues_open }}</span>
                      <span v-else class="ev-iss-none">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

        </div>

        <ESGCompanyDetailModal
          v-if="drillCompanyId"
          :company-id="drillCompanyId"
          :year="drillYear"
          @close="drillCompanyId = null"
          @saved="onDetailSaved"
        />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.ev-view { background: #F4F3F9; min-height: 100%; font-family: var(--font, system-ui); }

/* Animations */
@keyframes evCardIn {
  0% { opacity: 0; transform: translateY(12px) scale(.98); }
  60% { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes evStripeIn { 0% { transform: scaleX(0); } 100% { transform: scaleX(1); } }
@keyframes evBarFill { 0% { width: 0; } 100% { width: var(--w, 100%); } }
@keyframes evRowIn { 0% { opacity: 0; transform: translateX(-4px); } 100% { opacity: 1; transform: translateX(0); } }

/* ═══ Topbar ═══ */
.ev-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 16px 24px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 18px; flex-wrap: wrap;
}
.ev-tb-l { display: flex; flex-direction: column; gap: 4px; }
.ev-tb-title {
  font-size: 18px; font-weight: 500; color: #fff;
  letter-spacing: -.005em;
}
.ev-tb-sub {
  font-size: 12px; color: rgba(255,255,255,.65);
  display: flex; align-items: center; gap: 8px;
}
.ev-tb-sub b { color: rgba(255,255,255,.95); font-weight: 500; }
.ev-tb-sub .dot { opacity: .4; }
.ev-tb-r { display: flex; gap: 8px; align-items: center; }
.ev-in {
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 6px 12px; border-radius: 8px;
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.ev-in option { background: #1E2A4A; color: #fff; }

.ev-loading, .ev-error { padding: 40px; text-align: center; color: #888780; }
.ev-error { color: #A32D2D; }

.ev-body { padding: 20px 22px 28px; }

/* ═══ KPI strip (4 cells, corner icons) ═══ */
.ev-kpi-strip {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-bottom: 14px;
}
.ev-kpi-cell {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 14px;
  padding: 16px 18px 14px;
  position: relative; overflow: hidden;
  animation: evCardIn .5s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
  box-shadow: 0 2px 8px rgba(15, 23, 60, .04);
}
.ev-kpi-cell::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; transform-origin: left;
  animation: evStripeIn .8s cubic-bezier(.4,0,.2,1) var(--d, 0ms) both;
}
.ev-kpi-cov::before     { background: #1D9E75; }
.ev-kpi-leader::before  { background: #EF9F27; }
.ev-kpi-norating::before{ background: #E24B4A; }
.ev-kpi-updates::before { background: #378ADD; }

.ev-kpi-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.ev-kpi-lbl {
  font-size: 10.5px; color: #888780; text-transform: uppercase;
  letter-spacing: .07em; font-weight: 500;
}
.ev-kpi-icn {
  width: 28px; height: 28px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ev-kpi-icn.ok    { background: rgba(29, 158, 117, .12); color: #1D9E75; }
.ev-kpi-icn.amber { background: rgba(239, 159, 39, .12); color: #EF9F27; }
.ev-kpi-icn.red   { background: rgba(226, 75, 74, .12); color: #E24B4A; }
.ev-kpi-icn.blue  { background: rgba(55, 138, 221, .12); color: #378ADD; }

.ev-kpi-vw { display: flex; align-items: baseline; gap: 6px; }
.ev-kpi-v {
  font-size: 36px; font-weight: 400; color: #1E2A4A;
  letter-spacing: -.035em; line-height: 1;
  font-feature-settings: "tnum";
}
.ev-kpi-of {
  font-size: 16px; color: #888780; font-weight: 500;
  letter-spacing: -.02em;
}
.ev-kpi-of-text {
  font-size: 11px; color: #888780; font-weight: 500;
  margin-left: 2px;
}
.ev-kpi-leader-name {
  font-size: 22px; font-weight: 500; color: #1E2A4A;
  letter-spacing: -.02em; line-height: 1.1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ev-kpi-sub {
  font-size: 11px; color: #5F5E5A; font-weight: 500;
  margin-top: 8px;
}
.ev-kpi-sub b { color: #1E2A4A; font-weight: 500; }

/* ═══ Mid grid panels (donut/leaders/updates) ═══ */
.ev-mid-grid {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
.ev-panel {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 14px;
  overflow: hidden;
  display: flex; flex-direction: column;
  animation: evCardIn .65s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
}
.ev-panel-h {
  padding: 14px 18px 12px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.ev-panel-h h3 {
  font-size: 13px; font-weight: 500; color: #1E2A4A;
  margin: 0;
  display: flex; align-items: center; gap: 8px;
}
.ev-panel-h h3 svg { color: #888780; flex-shrink: 0; }
.ev-panel-meta { font-size: 10.5px; color: #888780; font-weight: 500; }
.ev-panel-body { flex: 1; padding: 14px 18px; }

/* Donut */
.ev-donut-wrap {
  display: flex; align-items: center; gap: 16px;
}
.ev-donut-cv-wrap {
  position: relative;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.ev-donut-center {
  position: absolute; text-align: center;
}
.ev-donut-v {
  font-size: 22px; font-weight: 400; color: #1E2A4A;
  letter-spacing: -.025em; line-height: 1;
  font-feature-settings: "tnum";
}
.ev-donut-l {
  font-size: 9px; color: #888780; text-transform: uppercase;
  letter-spacing: .08em; font-weight: 500; margin-top: 3px;
}
.ev-donut-legend {
  flex: 1; display: flex; flex-direction: column; gap: 6px;
  min-width: 0;
}
.ev-donut-leg-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 11.5px; color: #1E2A4A;
}
.ev-leg-bullet {
  width: 8px; height: 8px;
  border-radius: 50%; flex-shrink: 0;
}
.ev-leg-lbl {
  flex: 1; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
  color: #5F5E5A;
}
.ev-leg-cnt { font-weight: 500; color: #1E2A4A; font-feature-settings: "tnum"; }
.ev-leg-pct { color: #888780; font-size: 10.5px; }

/* Leaders */
.ev-leader-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0;
  cursor: pointer;
  animation: evRowIn .25s ease var(--d, 0ms) both;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  transition: background .15s;
}
.ev-leader-row:last-child { border-bottom: 0; }
.ev-leader-row:hover { background: rgba(127, 119, 221, .04); border-radius: 6px; margin: 0 -8px; padding: 8px 8px; }
.ev-leader-rank {
  width: 18px; flex-shrink: 0;
  font-size: 12px; color: #888780; font-weight: 500;
  text-align: center;
}
.ev-leader-abbr {
  font-size: 9.5px; font-weight: 600;
  padding: 4px 7px;
  border-radius: 5px;
  letter-spacing: .03em;
  flex-shrink: 0;
  min-width: 38px; text-align: center;
}
.ev-leader-info { flex: 1; min-width: 0; }
.ev-leader-name {
  font-size: 12.5px; font-weight: 500; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ev-leader-sec {
  font-size: 10.5px; color: #888780;
  margin-top: 1px;
}
.ev-leader-rating {
  padding: 3px 9px;
  border-radius: 5px;
  font-size: 12px; font-weight: 600;
  letter-spacing: .01em;
  flex-shrink: 0;
  min-width: 42px; text-align: center;
}

/* Updates */
.ev-upd-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 0;
  cursor: pointer;
  animation: evRowIn .25s ease var(--d, 0ms) both;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  transition: background .15s;
}
.ev-upd-row:last-child { border-bottom: 0; }
.ev-upd-row:hover { background: rgba(127, 119, 221, .04); border-radius: 6px; margin: 0 -8px; padding: 8px 8px; }
.ev-upd-dot {
  width: 9px; height: 9px;
  border-radius: 50%;
  background: var(--esg-dot, #1D9E75);
  flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--esg-dot) 18%, transparent);
}
.ev-upd-info { flex: 1; min-width: 0; }
.ev-upd-text {
  font-size: 12px; color: #5F5E5A;
  line-height: 1.35;
}
.ev-upd-text b { color: #1E2A4A; font-weight: 500; }
.ev-upd-time {
  font-size: 10.5px; color: #888780;
  margin-top: 2px;
}

.ev-empty-inline {
  padding: 32px 16px;
  text-align: center;
  color: #888780; font-size: 12px; font-style: italic;
}

/* ═══ Sector breakdown (mini-donuts) ═══ */
.ev-sector-panel { margin-bottom: 12px; }
.ev-sector-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.ev-sec-card {
  background: #FAFAFC;
  border: 1px solid rgba(0, 0, 0, .04);
  border-radius: 10px;
  padding: 12px 14px;
  animation: evCardIn .5s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
}
.ev-sec-hd {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.ev-sec-name { font-size: 13px; font-weight: 500; color: #1E2A4A; }
.ev-sec-count {
  font-size: 10.5px; padding: 2px 7px;
  background: rgba(127, 119, 221, .08); color: #534AB7;
  border-radius: 9px; font-weight: 500;
  font-feature-settings: "tnum";
}
.ev-sec-body { display: flex; align-items: center; gap: 12px; }
.ev-sec-mini-donut {
  position: relative; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.ev-sec-mini-v {
  position: absolute;
  font-size: 12.5px; font-weight: 500; color: #1E2A4A;
  font-feature-settings: "tnum";
}
.ev-sec-leader { flex: 1; min-width: 0; }
.ev-sec-leader-l {
  font-size: 9px; text-transform: uppercase;
  letter-spacing: .08em; color: #888780;
  font-weight: 500; margin-bottom: 2px;
}
.ev-sec-leader-n {
  font-size: 12px; font-weight: 500; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ═══ E/S/G pillars ═══ */
.ev-pillars-row {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
.ev-pillar-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 14px;
  padding: 16px 18px;
  animation: evCardIn .65s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
}
.ev-pillar-head { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.ev-pillar-letter {
  width: 36px; height: 36px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 18px; font-weight: 500;
  letter-spacing: -.02em; flex-shrink: 0;
  box-shadow: 0 4px 12px var(--ac, rgba(127, 119, 221, .25));
}
.ev-pillar-h-info { flex: 1; min-width: 0; }
.ev-pillar-h-ttl { font-size: 13px; font-weight: 500; color: #1E2A4A; }
.ev-pillar-h-meta { font-size: 10.5px; color: #888780; margin-top: 1px; }
.ev-pillar-stat {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 8px;
}
.ev-pillar-stat-l { font-size: 11px; color: #888780; }
.ev-pillar-stat-v {
  font-size: 22px; font-weight: 400;
  letter-spacing: -.025em; font-feature-settings: "tnum";
}
.ev-pillar-bar-wrap {
  height: 5px; background: rgba(0, 0, 0, .04);
  border-radius: 3px; overflow: hidden; margin-bottom: 10px;
}
.ev-pillar-bar-fill {
  height: 100%; border-radius: 3px;
  animation: evBarFill .9s cubic-bezier(.22,.61,.36,1) calc(var(--d, 0ms) + 250ms) both;
}
.ev-pillar-foot { font-size: 11px; color: #5F5E5A; }
.ev-pillar-foot-ok { color: #0F6E56; font-weight: 500; }
.ev-pillar-foot-bad { color: #933632; font-weight: 500; }

/* ═══ Rankings table ═══ */
.ev-rank-seg {
  display: inline-flex;
  background: rgba(0, 0, 0, .04);
  border-radius: 7px;
  padding: 2px;
}
.ev-rank-seg button {
  background: transparent; border: 0;
  font-size: 11px; padding: 4px 12px;
  border-radius: 5px;
  color: #888780; cursor: pointer;
  font-family: inherit; font-weight: 500;
  transition: all .15s;
}
.ev-rank-seg button:hover { color: #1E2A4A; }
.ev-rank-seg button.on {
  background: #fff; color: #1E2A4A;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .08);
}
.ev-rank-body { padding: 0; overflow: auto; }
.ev-rank-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.ev-rank-tbl thead {
  background: #FAFAFA;
  position: sticky; top: 0;
}
.ev-rank-tbl thead th {
  padding: 8px 10px; text-align: center;
  font-size: 11px; font-weight: 500; color: #888780;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
}
.ev-rank-tbl thead th.lt { text-align: left; padding-left: 18px; }
.ev-rank-tbl tbody td {
  padding: 9px 10px; text-align: center;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-feature-settings: "tnum";
  color: #1E2A4A;
}
.ev-rank-tbl tbody td.lt {
  text-align: left; padding-left: 18px;
  display: flex; align-items: center; gap: 10px;
}
.ev-rank-tbl tbody tr {
  cursor: pointer;
  animation: evRowIn .25s ease var(--d, 0ms) both;
  transition: background .15s;
}
.ev-rank-tbl tbody tr:hover { background: rgba(127, 119, 221, .04); }
.ev-rt-abbr {
  font-size: 9.5px; font-weight: 600;
  padding: 4px 7px;
  border-radius: 5px;
  letter-spacing: .03em;
  flex-shrink: 0;
  min-width: 38px; text-align: center;
}
.ev-rt-name-wrap { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ev-rt-name {
  font-size: 12.5px; font-weight: 500; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ev-rt-sub {
  font-size: 10px; color: #888780;
  display: flex; gap: 6px;
}
.ev-rt-yr { color: #534AB7; font-weight: 500; }
.ev-score-num { font-weight: 500; }
.ev-rating-pill {
  display: inline-block; padding: 3px 9px;
  border-radius: 5px;
  font-size: 11.5px; font-weight: 600;
  letter-spacing: .02em;
}
.ev-iss-c { color: #A32D2D; font-weight: 500; }
.ev-iss-o { color: #A36500; font-weight: 500; }
.ev-iss-none { color: #888780; }

/* Responsive */
@media (max-width: 1300px) {
  .ev-kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .ev-mid-grid { grid-template-columns: 1fr; }
  .ev-pillars-row { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .ev-body { padding: 14px 12px; }
}
</style>
