<script setup lang="ts">
/**
 * ESG Executive Cockpit — 1:1 port of legacy `showESGView` (index.html:52603).
 *
 * Layout:
 *   • Dark navy topbar with "X компаний · Y с рейтингом · Z агентств" + buttons
 *   • 4 KPI cards (clickable for drill): Покрытие · Лидер · Без рейтинга · Обновления
 *   • Mid 3-col grid: Donut (per-agency coverage) · Лидеры топ-5 · Последние обновления
 *   • Sector breakdown (5 mini-radials)
 *   • Filter bar: sector chips + search
 *   • Detailed table — 4 cols (Компания + 3 ESG agencies) with sector groups
 *
 * Data: backend `/esg/overview` now surfaces `ratings_by_agency[]` per company
 * (filled from `agency_ratings` table where `is_esg=True`), plus computed
 * `composite_esg_score` (0..10) and per-agency coverage stats.
 */
import { computed, onMounted, ref } from "vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useToast } from "@/composables/useToast";
import SidebarBurger from "@/components/SidebarBurger.vue";
import {
  esgApi,
  type AgencyRatingCell,
  type ESGCompanyScore,
  type ESGOverviewResponse,
} from "@/api/esg";
import ESGCompanyDetailModal from "@/components/ESG/ESGCompanyDetailModal.vue";
import RatingEditModal from "@/components/Ratings/RatingEditModal.vue";
import SignatureDonut, { type SignatureDonutEntry } from "@/components/UZA/SignatureDonut.vue";
import { useAuthStore } from "@/stores/auth";

// ───────────────────────────────────────────────────────────────
//   State
// ───────────────────────────────────────────────────────────────

const toast = useToast();

const overview = ref<ESGOverviewResponse | null>(null);
const year = useSavedFilter<number | null>("esg.year", null);
const sectorCode = useSavedFilter<string | null>("esg.sectorCode", null);
const searchQuery = ref<string>("");
const sortBy = useSavedFilter<"sector" | "name">("esg.sortBy", "sector");
const sortDesc = useSavedFilter<boolean>("esg.sortDesc", true);

const loading = ref(false);
const error = ref<string | null>(null);

const drillCompanyId = ref<string | null>(null);
const drillYear = ref<number | undefined>(undefined);

type KpiDrillType = "coverage" | "leader" | "unrated" | "updates";
const kpiDrill = ref<KpiDrillType | null>(null);

// ───────────────────────────────────────────────────────────────
//   Load
// ───────────────────────────────────────────────────────────────

async function load() {
  loading.value = true;
  error.value = null;
  try {
    overview.value = await esgApi.getOverview({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
      rankings_limit: 100,
    });
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить дашборд";
  } finally {
    loading.value = false;
  }
}

function setSectorFilter(code: string | null) {
  sectorCode.value = code;
  load();
}

function showRatingDetails(cell: AgencyRatingCell) {
  const parts = [`${cell.agency}: ${cell.rating}`];
  if (cell.outlook) parts.push(cell.outlook);
  if (cell.rating_date_text) parts.push(cell.rating_date_text);
  toast.info(parts.join(" · "));
}
function openDrill(id: string, yr: number | null) {
  drillCompanyId.value = id;
  drillYear.value = yr ?? undefined;
}
async function onDetailSaved() { await load(); }

// ─── Inline-редактирование рейтингов прямо из таблицы (переиспользуем редактор «Рейтингов») ───
const auth = useAuthStore();
const canEditRatings = computed(() =>
  auth.isOwner || (auth.userRoles || []).includes("admin") || (auth.userPermissions || []).includes("ratings.edit"),
);
const ratingEdit = ref<{ companyId: string; companyName: string; agency: string; existing: any | null } | null>(null);
function openRatingEdit(r: ESGCompanyScore, cell: AgencyRatingCell) {
  if (!canEditRatings.value) return;
  ratingEdit.value = {
    companyId: r.company_id,
    companyName: r.company_name || r.company_code,
    agency: cell.agency,
    existing: cell.rating_id ? {
      id: cell.rating_id, agency: cell.agency, rating: cell.rating, score: cell.score,
      outlook: cell.outlook, rating_date_text: cell.rating_date_text, rating_date: null,
      report_url: cell.report_url,
    } : null,
  };
}
async function onRatingSaved() { ratingEdit.value = null; await load(); }

// ───────────────────────────────────────────────────────────────
//   Score → letter helpers (1:1 legacy)
// ───────────────────────────────────────────────────────────────

function scoreToRating(s: number | null | undefined): string {
  if (s == null) return "—";
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
function scoreCls(s: number | null | undefined): string {
  if (s == null) return "mid";
  if (s >= 7)   return "good";
  if (s >= 5.2) return "bbb";
  if (s >= 3.4) return "mid";
  return "bad";
}

/** Legacy bSt(agency, rating) — colours for the agency rating badge. */
function badgeStyle(agency: string, rating: string | null | undefined): { bg: string; fg: string } {
  const rv = (rating || "").toUpperCase();
  if (!rv) return { bg: "#F1F5F9", fg: "#64748B" };
  if (agency === "Sustainable Fitch" || agency === "S&P ESG") {
    const n = parseInt(rv, 10);
    if (n >= 1 && n <= 5) {
      if (n <= 2) return { bg: "#DCFCE7", fg: "#1D9E75" };
      if (n === 3) return { bg: "#FEF9C3", fg: "#D97706" };
      return { bg: "#FEE2E2", fg: "#EF4444" };
    }
    if (n >= 6) {
      if (n >= 60) return { bg: "#DCFCE7", fg: "#1D9E75" };
      if (n >= 40) return { bg: "#FEF9C3", fg: "#D97706" };
      return { bg: "#FEE2E2", fg: "#EF4444" };
    }
    if (rv.startsWith("AA") || rv.startsWith("A")) return { bg: "#DCFCE7", fg: "#1D9E75" };
    if (rv.startsWith("BBB")) return { bg: "rgba(55,138,221,.10)", fg: "#378ADD" };
    if (rv.startsWith("BB") || rv.startsWith("B")) return { bg: "#FEF9C3", fg: "#D97706" };
    if (rv.startsWith("CCC") || rv === "D") return { bg: "#FEE2E2", fg: "#EF4444" };
  } else if (agency === "CDP") {
    if (rv === "A" || rv === "A-") return { bg: "#DCFCE7", fg: "#1D9E75" };
    if (rv === "B" || rv === "B-") return { bg: "rgba(55,138,221,.10)", fg: "#378ADD" };
    if (rv === "C" || rv === "C-") return { bg: "#FEF9C3", fg: "#D97706" };
    return { bg: "#FEE2E2", fg: "#EF4444" };
  }
  return { bg: "#F1F5F9", fg: "#64748B" };
}

// ───────────────────────────────────────────────────────────────
//   Derived data
// ───────────────────────────────────────────────────────────────

const ESG_AGENCIES = ["Sustainable Fitch", "S&P ESG", "CDP"];
const AGENCY_COLORS: Record<string, string> = {
  "Sustainable Fitch": "#1D9E75",
  "S&P ESG":           "#378ADD",
  "CDP":               "#EF9F27",
};

const k = computed(() => overview.value?.kpis);
const sectorBreakdown = computed(() => overview.value?.sector_breakdown ?? []);
const agencyCoverage = computed(() => overview.value?.agency_coverage ?? []);
const recentUpdates = computed(() => overview.value?.recent_updates ?? []);

function fallbackSectorColor(r: ESGCompanyScore): string {
  return r.sector_color || "#888780";
}

/** Rows for the detailed table (sector grouping or alpha sort). */
interface TableSection {
  sector_code: string;
  sector_label: string;
  sector_color: string;
  total: number;
  covered: number;
  rows: ESGCompanyScore[];
}

const tableSections = computed<TableSection[]>(() => {
  const rows = overview.value?.rankings ?? [];
  const filter = searchQuery.value.trim().toLowerCase();
  const filtered = filter
    ? rows.filter(r => (r.company_name || r.company_code).toLowerCase().includes(filter))
    : rows;

  if (sortBy.value === "name") {
    const sorted = [...filtered].sort((a, b) => {
      const an = a.company_name || a.company_code;
      const bn = b.company_name || b.company_code;
      return sortDesc.value
        ? bn.localeCompare(an, "ru")
        : an.localeCompare(bn, "ru");
    });
    return [{
      sector_code: "all",
      sector_label: "Все",
      sector_color: "#888780",
      total: sorted.length,
      covered: sorted.filter(r => r.has_any_rating).length,
      rows: sorted,
    }];
  }

  // Default: group by sector (using sector_breakdown for order)
  const order = (overview.value?.sector_breakdown ?? []).map(s => s.code);
  const groupMap: Record<string, ESGCompanyScore[]> = {};
  for (const r of filtered) {
    const key = r.sector_code || "other";
    (groupMap[key] = groupMap[key] || []).push(r);
  }
  // Sort each group by composite_esg_score desc
  for (const key of Object.keys(groupMap)) {
    groupMap[key].sort((a, b) => {
      const av = a.composite_esg_score ?? -1;
      const bv = b.composite_esg_score ?? -1;
      if (av === bv) {
        return (a.company_name || a.company_code).localeCompare(b.company_name || b.company_code, "ru");
      }
      return bv - av;
    });
  }
  return order
    .filter(code => groupMap[code]?.length)
    .map(code => {
      const sec = (overview.value?.sector_breakdown ?? []).find(s => s.code === code);
      const rs = groupMap[code];
      return {
        sector_code: code,
        sector_label: sec?.label || code,
        sector_color: sec?.color || "#888780",
        total: rs.length,
        covered: rs.filter(r => r.has_any_rating).length,
        rows: rs,
      };
    });
});

function toggleSort(by: "name") {
  if (sortBy.value === by) {
    sortDesc.value = !sortDesc.value;
  } else {
    sortBy.value = by;
    sortDesc.value = true;
  }
}
function resetSort() {
  sortBy.value = "sector";
  sortDesc.value = true;
}

// ───────────────────────────────────────────────────────────────
//   Donut (agency coverage) — SignatureDonut entries
// ───────────────────────────────────────────────────────────────

const donutEntries = computed<SignatureDonutEntry[]>(() => {
  const total = k.value?.total_companies ?? 0;
  const entries: SignatureDonutEntry[] = agencyCoverage.value.map(ag => ({
    label: ag.agency,
    color: ag.color,
    value: ag.count,
    sub: `${ag.count} из ${total}`,
  }));
  // Uncovered slice — neutral grey
  const covered = k.value?.covered_count ?? 0;
  const uncovered = total - covered;
  if (uncovered > 0) {
    entries.push({
      label: "Без рейтинга",
      color: "#E2E8F0",
      value: uncovered,
      sub: `${uncovered} из ${total}`,
    });
  }
  return entries;
});

function donutHoverFmt(e: SignatureDonutEntry): [string, string] {
  const total = (k.value?.total_companies ?? 0) || 1;
  const pct = Math.round((Math.abs(e.value) / total) * 100);
  return [`${pct}%`, e.label];
}

// ───────────────────────────────────────────────────────────────
//   KPI drill rows
// ───────────────────────────────────────────────────────────────

const kpiDrillTitle = computed<string>(() => {
  switch (kpiDrill.value) {
    case "coverage": return "Покрытие портфеля ESG-рейтингами";
    case "leader":   return "Лидеры портфеля";
    case "unrated":  return "Компании без ESG-рейтинга";
    case "updates":  return "Последние обновления рейтингов";
    default:         return "";
  }
});

interface KpiDrillRow {
  r: ESGCompanyScore;
  primary: string;
  primaryColor: string;
  secondary: string;
}

const kpiDrillRows = computed<KpiDrillRow[]>(() => {
  const rows = overview.value?.rankings ?? [];
  switch (kpiDrill.value) {
    case "coverage": {
      const sorted = [...rows].sort((a, b) =>
        (b.composite_esg_score ?? -1) - (a.composite_esg_score ?? -1),
      );
      return sorted.map(r => ({
        r,
        primary: r.composite_esg_score != null ? scoreToRating(r.composite_esg_score) : "—",
        primaryColor: r.composite_esg_score != null ? "#1D9E75" : "#94A3B8",
        secondary: r.has_any_rating
          ? `${r.ratings_by_agency.filter(c => c.rating).length} рейтинг(а)`
          : "нет рейтингов",
      }));
    }
    case "leader": {
      const sorted = [...rows]
        .filter(r => r.composite_esg_score != null)
        .sort((a, b) => (b.composite_esg_score ?? 0) - (a.composite_esg_score ?? 0))
        .slice(0, 10);
      return sorted.map(r => ({
        r,
        primary: scoreToRating(r.composite_esg_score),
        primaryColor: "#EF9F27",
        secondary: `${r.composite_esg_score?.toFixed(1)} / 10`,
      }));
    }
    case "unrated": {
      const f = rows.filter(r => !r.has_any_rating);
      return f.map(r => ({
        r,
        primary: "—",
        primaryColor: "#E24B4A",
        secondary: "нужны рейтинги",
      }));
    }
    case "updates": {
      return recentUpdates.value.map(u => {
        // Bridge from RecentRatingUpdate to a fake score row for click handler
        const fakeRow: ESGCompanyScore = {
          company_id: u.company_id, company_code: u.company_code, company_name: u.company_name,
          company_abbr: null, sector_code: u.sector_code, sector_color: u.sector_color,
          e_score: null, s_score: null, g_score: null, overall_score: null,
          metric_count: 0, issues_open: 0, issues_critical: 0,
          last_year_reported: null, rank: 0,
          ratings_by_agency: [], composite_esg_score: null,
          has_any_rating: true, recent_updates_count: 0,
        };
        const txt = u.score && u.score !== u.rating ? `${u.rating} · ${u.score}` : u.rating || "—";
        return {
          r: fakeRow,
          primary: txt,
          primaryColor: u.agency_color,
          secondary: `${u.agency}${u.rating_date_text ? " · " + u.rating_date_text : ""}`,
        };
      });
    }
  }
  return [];
});

// ───────────────────────────────────────────────────────────────
//   Mini-donut helpers (sector breakdown)
// ───────────────────────────────────────────────────────────────

const MINI_R = 16;
const MINI_C = 2 * Math.PI * MINI_R;
function miniDasharray(pct: number): string {
  const filled = (pct / 100) * MINI_C;
  return `${filled} ${MINI_C - filled}`;
}

// ───────────────────────────────────────────────────────────────
//   Lifecycle
// ───────────────────────────────────────────────────────────────

onMounted(() => { load(); });
</script>

<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=year. -->
  <div class="ev-view">

        <!-- ═══ Topbar (legacy dash-topbar, dark navy) ═══ -->
        <div class="ev-topbar">
          <SidebarBurger />
          <div class="ev-tb-l">
            <h1 class="ev-tb-title">ESG-рейтинги портфеля</h1>
            <div class="ev-tb-sub" v-if="k">
              <span><b>{{ k.total_companies }}</b> компаний</span>
              <span class="ev-dot">·</span>
              <span><b>{{ k.covered_count }}</b> с рейтингом</span>
              <span class="ev-dot">·</span>
              <span><b>{{ ESG_AGENCIES.length }}</b> агентств</span>
            </div>
          </div>
          <div class="ev-tb-r"></div>
        </div>

        <div v-if="loading && !overview" class="ev-loading">Загрузка...</div>
        <div v-else-if="error && !overview" class="ev-error">{{ error }}</div>

        <div v-else-if="overview && k" class="ev-body">

          <!-- ═══ 1. KPI strip (4 cells, clickable) ═══ -->
          <div class="ev-kpi-strip kpi-rail">

            <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#1D9E75; --kpi2-d:0ms" @click="kpiDrill = 'coverage'">
              <div class="ev-kpi-icn ok">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/></svg>
              </div>
              <div class="kpi2-lbl">Покрытие</div>
              <div class="kpi2-val">
                <span :data-countup="k.covered_count">{{ k.covered_count }}</span>
                <span class="unit"> / {{ k.total_companies }}</span>
              </div>
              <div class="kpi2-sub">с хотя бы одним <b>ESG-рейтингом · {{ k.coverage_pct }}%</b></div>
            </div>

            <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#EF9F27; --kpi2-d:80ms" @click="kpiDrill = 'leader'">
              <div class="ev-kpi-icn amber">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 010-5H6M18 9h1.5a2.5 2.5 0 000-5H18M4 22h16M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22M18 2H6v7a6 6 0 0012 0V2z"/></svg>
              </div>
              <div class="kpi2-lbl">Лидер</div>
              <div class="kpi2-val ev-kpi-name" :style="{
                fontSize: (k.leader_company_name && k.leader_company_name.length > 14) ? '22px'
                          : (k.leader_company_name && k.leader_company_name.length > 10) ? '26px' : '30px'
              }">
                {{ k.leader_company_name || "—" }}
              </div>
              <div class="kpi2-sub">
                <template v-if="k.leader_composite != null">
                  {{ k.leader_ratings_count }} рейтинга · <b>{{ k.leader_rating_letter }}</b>
                </template>
                <template v-else>нет данных</template>
              </div>
            </div>

            <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#E24B4A; --kpi2-d:160ms" @click="kpiDrill = 'unrated'">
              <div class="ev-kpi-icn red">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>
              </div>
              <div class="kpi2-lbl">Без рейтинга</div>
              <div class="kpi2-val">
                <span :data-countup="k.unrated_count">{{ k.unrated_count }}</span>
                <span class="unit"> компаний</span>
              </div>
              <div class="kpi2-sub">
                <span style="color:#EF4444"><b>{{ k.total_companies > 0 ? Math.round(k.unrated_count / k.total_companies * 100) : 0 }}%</b></span>
                портфеля · нужны рейтинги
              </div>
            </div>

            <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#7F77DD; --kpi2-d:240ms" @click="kpiDrill = 'updates'">
              <div class="ev-kpi-icn blue">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
              </div>
              <div class="kpi2-lbl">Обновления</div>
              <div class="kpi2-val">
                <span v-if="k.recent_updates_count > 0" style="color:#1D9E75">+</span>
                <span :data-countup="k.recent_updates_count">{{ k.recent_updates_count }}</span>
              </div>
              <div class="kpi2-sub">за <b>текущий и прошлый год</b></div>
            </div>
          </div>

          <!-- ═══ 2. Mid 3-col grid: Donut + Leaders + Updates ═══ -->
          <div class="ev-mid-grid">

            <!-- Donut Coverage (per agency) — uses canonical SignatureDonut -->
            <div class="ev-panel ev-donut-panel" style="--d:300ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
                  Покрытие портфеля
                </h3>
                <span class="ev-panel-meta">по агентствам</span>
              </div>
              <div class="ev-panel-body ev-donut-body">
                <SignatureDonut
                  :entries="donutEntries"
                  :center-value="`${k.coverage_pct}%`"
                  center-label="покрытие"
                  :size="160"
                  :hover-fmt="donutHoverFmt"
                  id-base="esg-coverage-donut"
                />
              </div>
            </div>

            <!-- Leaders (top-5) -->
            <div class="ev-panel" style="--d:360ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>
                  Лидеры портфеля
                </h3>
                <span class="ev-panel-meta">топ-5</span>
              </div>
              <div class="ev-panel-body ev-list-body">
                <div v-if="!overview.rankings.some(r => r.composite_esg_score != null)" class="ev-empty-inline">
                  Нет рейтингов в портфеле
                </div>
                <div
                  v-for="(r, i) in overview.rankings
                    .filter(x => x.composite_esg_score != null)
                    .slice(0, 5)"
                  :key="r.company_id"
                  class="ev-leader-row"
                  :style="{ animationDelay: (i * 60) + 'ms' }"
                  @click="openDrill(r.company_id, r.last_year_reported)"
                >
                  <div class="ev-leader-rank">{{ i + 1 }}</div>
                  <div class="ev-leader-abbr" :style="{ background: fallbackSectorColor(r) + '20', color: fallbackSectorColor(r) }">
                    {{ r.company_abbr || r.company_code }}
                  </div>
                  <div class="ev-leader-info">
                    <div class="ev-leader-name">{{ r.company_name || r.company_code }}</div>
                    <div class="ev-leader-sec">{{ overview.sectors.find(s => s.code === r.sector_code)?.code || r.sector_code || '—' }}</div>
                  </div>
                  <div class="ev-leader-rating" :class="scoreCls(r.composite_esg_score)">
                    {{ scoreToRating(r.composite_esg_score) }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Recent updates -->
            <div class="ev-panel" style="--d:420ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                  Последние обновления
                </h3>
                <span class="ev-panel-meta">{{ recentUpdates.length }} за период</span>
              </div>
              <div class="ev-panel-body ev-list-body">
                <div v-if="!recentUpdates.length" class="ev-empty-inline">Нет недавних обновлений</div>
                <div
                  v-for="(u, i) in recentUpdates.slice(0, 5)"
                  :key="u.company_id + u.agency"
                  class="ev-upd-row"
                  :style="{ animationDelay: (i * 60) + 'ms', '--ev-dot': u.agency_color }"
                  @click="openDrill(u.company_id, null)"
                >
                  <div class="ev-upd-dot"></div>
                  <div class="ev-upd-info">
                    <div class="ev-upd-text">
                      <b>{{ u.company_name }}</b> · {{ u.agency }}
                      {{ u.rating ? ' ' + u.rating : '' }}
                      <template v-if="u.score && u.score !== u.rating">· {{ u.score }}</template>
                    </div>
                    <div class="ev-upd-time">
                      {{ u.rating_date_text || '—' }}
                      <a v-if="u.report_url" :href="u.report_url" target="_blank" rel="noopener" @click.stop class="ev-upd-link">↗</a>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══ 3. Sector breakdown (mini-donuts) ═══ -->
          <div class="ev-panel ev-sector-panel" style="--d:480ms">
            <div class="ev-panel-h">
              <h3>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                Срез по секторам
              </h3>
              <span class="ev-panel-meta">{{ sectorBreakdown.length }} секторов</span>
            </div>
            <div class="ev-panel-body">
              <div class="ev-sector-row">
                <div
                  v-for="(sec, i) in sectorBreakdown"
                  :key="sec.code"
                  class="ev-sec-card"
                  :style="{ '--ev-sc': sec.color, animationDelay: (540 + i * 60) + 'ms' }"
                  @click="setSectorFilter(sec.code === sectorCode ? null : sec.code)"
                >
                  <div class="ev-sec-hd">
                    <div class="ev-sec-name">{{ sec.label }}</div>
                    <div class="ev-sec-count">{{ sec.covered }} / {{ sec.total }}</div>
                  </div>
                  <div class="ev-sec-body">
                    <div class="ev-sec-mini-donut">
                      <svg viewBox="0 0 40 40" style="width:40px;height:40px">
                        <circle cx="20" cy="20" r="16" fill="none" :stroke="sec.color" stroke-opacity=".18" stroke-width="3.5"/>
                        <circle cx="20" cy="20" r="16" fill="none"
                          :stroke="sec.color" stroke-width="3.5"
                          :stroke-dasharray="miniDasharray(sec.coverage_pct)"
                          stroke-linecap="round"
                          transform="rotate(-90 20 20)"/>
                      </svg>
                      <div class="ev-sec-mini-v" :style="{ color: sec.color }">{{ sec.coverage_pct }}%</div>
                    </div>
                    <div class="ev-sec-leader">
                      <div class="ev-sec-leader-l">Лидер</div>
                      <div class="ev-sec-leader-n" v-if="sec.leader_company_name">
                        {{ sec.leader_company_name.length > 16 ? sec.leader_company_name.slice(0, 15) + '…' : sec.leader_company_name }}
                      </div>
                      <div class="ev-sec-leader-n empty" v-else>—</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══ 4. Filter bar (sector chips + search) ═══ -->
          <div class="ev-filter-bar" style="--d:540ms">
            <div class="ev-filter-l">Сектор:</div>
            <div class="ev-chips">
              <button class="ev-chip" :class="{ active: !sectorCode }" @click="setSectorFilter(null)">Все секторы</button>
              <button
                v-for="sec in sectorBreakdown"
                :key="sec.code"
                class="ev-chip"
                :class="{ active: sectorCode === sec.code }"
                @click="setSectorFilter(sec.code)"
              >{{ sec.label }}</button>
            </div>
            <div class="ev-search">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#888780" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
              <input v-model="searchQuery" type="text" placeholder="Поиск компании…"/>
              <button v-if="searchQuery" class="ev-search-x" @click="searchQuery = ''">×</button>
            </div>
          </div>

          <!-- ═══ 5. Detailed table (4 cols: Компания + 3 ESG agencies) ═══ -->
          <div class="ev-panel ev-table-panel" style="--d:600ms">
            <div class="ev-panel-h">
              <h3>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
                Детализация — {{ sortBy === 'name' ? 'по алфавиту' : 'группировка по секторам' }}
              </h3>
              <div class="ev-panel-h-r">
                <button class="ev-mat-clear" v-if="sortBy !== 'sector'" @click="resetSort">× сбросить</button>
                <span class="ev-panel-meta">источник: модуль «Рейтинги»</span>
              </div>
            </div>
            <div class="ev-table-wrap">
              <table class="ev-rank-tbl">
                <thead>
                  <tr>
                    <th class="lt sortable" :class="{ on: sortBy === 'name' }" @click="toggleSort('name')">
                      Компания <span class="arr">{{ sortBy !== 'name' ? '▼' : (sortDesc ? '▼' : '▲') }}</span>
                    </th>
                    <th v-for="ag in ESG_AGENCIES" :key="ag" :style="{ color: AGENCY_COLORS[ag] }">{{ ag }}</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="sec in tableSections" :key="sec.sector_code">
                    <tr v-if="sortBy === 'sector'" class="sec-divider">
                      <td colspan="4">
                        <span class="sec-strip" :style="{ background: sec.sector_color }"></span>
                        <span class="sec-label">{{ sec.sector_label }}</span>
                        <span class="sec-meta">· {{ sec.total }} компаний · {{ sec.covered }} с рейтингом</span>
                      </td>
                    </tr>
                    <tr
                      v-for="(r, i) in sec.rows"
                      :key="r.company_id"
                      :style="{ animationDelay: (Math.min(i, 30) * 20) + 'ms' }"
                      @click="openDrill(r.company_id, r.last_year_reported)"
                    >
                      <td class="lt">
                        <div class="ev-rt-abbr" :style="{ background: fallbackSectorColor(r) + '20', color: fallbackSectorColor(r) }">
                          {{ r.company_abbr || r.company_code }}
                        </div>
                        <div class="ev-rt-info">
                          <div class="ev-rt-name" :class="{ unrated: !r.has_any_rating }">
                            {{ r.company_name || r.company_code }}
                          </div>
                          <div class="ev-rt-sub">
                            <span>{{ sec.sector_label }}</span>
                            <span v-if="!r.has_any_rating" class="ev-rt-warn">· нет рейтингов</span>
                            <span v-if="r.last_year_reported" class="ev-rt-yr">· FY{{ r.last_year_reported }}</span>
                          </div>
                        </div>
                      </td>
                      <td v-for="cell in r.ratings_by_agency" :key="cell.agency" class="num">
                        <span
                          v-if="cell.rating"
                          class="ev-badge"
                          :class="{ 'ev-badge-edit': canEditRatings }"
                          :style="{ background: badgeStyle(cell.agency, cell.rating).bg, color: badgeStyle(cell.agency, cell.rating).fg }"
                          :title="canEditRatings ? 'Редактировать рейтинг' : ''"
                          @click.stop="canEditRatings ? openRatingEdit(r, cell) : showRatingDetails(cell)"
                        >
                          {{ cell.score && cell.score !== cell.rating ? `${cell.rating} · ${cell.score}` : cell.rating }}
                          <span v-if="cell.is_recent" class="ev-badge-up">▲</span>
                        </span>
                        <span
                          v-else
                          class="ev-empty-cell"
                          :class="{ clickable: canEditRatings }"
                          :title="canEditRatings ? 'Добавить рейтинг' : 'Нет рейтинга'"
                          @click.stop="canEditRatings && openRatingEdit(r, cell)"
                        >+</span>
                      </td>
                    </tr>
                  </template>
                  <tr v-if="!tableSections.length || !tableSections[0].rows.length">
                    <td colspan="4" class="ev-empty-state">
                      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>
                      <div>Нет компаний по выбранному фильтру</div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

        </div>

        <!-- KPI drill modal -->
        <Transition name="uza-fade">
          <div v-if="kpiDrill" class="ev-modal-bg" @click.self="kpiDrill = null">
            <div class="ev-modal-card">
              <div class="ev-modal-h">
                <div>
                  <div class="ev-modal-t">{{ kpiDrillTitle }}</div>
                  <div class="ev-modal-s">{{ kpiDrillRows.length }} {{ kpiDrillRows.length === 1 ? 'запись' : 'записей' }}</div>
                </div>
                <button class="ev-modal-x" @click="kpiDrill = null">✕</button>
              </div>
              <div class="ev-modal-body">
                <table class="ev-modal-tbl">
                  <tbody>
                    <tr v-for="(row, i) in kpiDrillRows" :key="i"
                      @click="kpiDrill = null; openDrill(row.r.company_id, row.r.last_year_reported);">
                      <td class="lt">
                        <span class="ev-mat-sec" :style="{ background: fallbackSectorColor(row.r) }"></span>
                        {{ row.r.company_name || row.r.company_code }}
                      </td>
                      <td class="num big" :style="{ color: row.primaryColor }">{{ row.primary }}</td>
                      <td class="sub">{{ row.secondary }}</td>
                    </tr>
                    <tr v-if="!kpiDrillRows.length">
                      <td colspan="3" class="empty">Нет данных</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </Transition>

        <!-- Per-company drill modal (existing) -->
        <ESGCompanyDetailModal
          v-if="drillCompanyId"
          :company-id="drillCompanyId"
          :year="drillYear"
          @close="drillCompanyId = null"
          @saved="onDetailSaved"
        />

        <!-- Inline-редактор рейтинга (клик по ячейке агентства в таблице) -->
        <RatingEditModal
          v-if="ratingEdit"
          :company-id="ratingEdit.companyId"
          :company-name="ratingEdit.companyName"
          :agency="ratingEdit.agency"
          :existing="ratingEdit.existing"
          @close="ratingEdit = null"
          @saved="onRatingSaved"
        />
      </div>
</template>

<style scoped>
.ev-view { background: var(--bg, #F4F3F9); min-height: 100%; font-family: var(--font, system-ui); }

@keyframes evFadeSlideIn { 0% { opacity: 0; transform: translateY(4px); } 100% { opacity: 1; transform: translateY(0); } }
@keyframes evCardIn {
  0% { opacity: 0; transform: translateY(12px) scale(.98); }
  60% { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* ─── Topbar ─── */
.ev-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; flex-wrap: wrap;
}
.ev-tb-l { display: flex; flex-direction: column; gap: 2px; }
.ev-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; }
.ev-tb-sub {
  font-size: 11px; color: rgba(255,255,255,.55);
  display: flex; align-items: center; gap: 6px;
}
.ev-tb-sub b { color: rgba(255,255,255,.95); font-weight: 600; }
.ev-dot { opacity: .4; }
.ev-tb-r { display: flex; align-items: center; gap: 8px; }
.ev-in {
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 6px 10px; border-radius: 8px;
  font-size: 12px; font-family: inherit; cursor: pointer; outline: none;
}
.ev-in option { background: #1E2A4A; color: #fff; }
.ev-tb-btn {
  border: 0.5px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.10);
  color: rgba(255,255,255,.78);
  padding: 6px 11px; border-radius: 7px;
  font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  display: flex; align-items: center; gap: 5px;
  transition: all .15s;
}
.ev-tb-btn:hover { background: rgba(255,255,255,.18); color: #fff; }

.ev-loading, .ev-error { padding: 40px; text-align: center; color: var(--t3, var(--t-muted)); }
.ev-error { color: var(--sev-critical); }

.ev-body { padding: 16px 20px 24px; }

/* ─── KPI strip — uses global .kpi2 ─── */
.ev-kpi-strip {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
  margin-bottom: 14px;
}
.ev-kpi {
  position: relative;
  cursor: pointer;
  animation: kpiCardIn .5s var(--ease-standard) var(--kpi2-d, 0ms) both;
  transition: transform .15s, box-shadow .15s;
}
.ev-kpi:hover { transform: translateY(-1px); }
.ev-kpi-icn {
  position: absolute; top: 14px; right: 16px;
  width: 26px; height: 26px;
  border-radius: 7px;
  display: flex; align-items: center; justify-content: center;
}
.ev-kpi-icn.ok    { background: rgba(29, 158, 117, .12); color: var(--green); }
.ev-kpi-icn.amber { background: rgba(239, 159, 39, .12); color: var(--amber); }
.ev-kpi-icn.red   { background: rgba(226, 75, 74, .12); color: var(--sev-high); }
.ev-kpi-icn.blue  { background: rgba(127, 119, 221, .12); color: #7F77DD; }
.ev-kpi-name {
  font-weight: 500;
  letter-spacing: -.02em;
  line-height: 1.1;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.kpi2-val .unit {
  font-size: 14px; color: var(--t3, var(--t-muted)); margin-left: 4px; font-weight: 400;
}

@media (max-width: 1200px) { .ev-kpi-strip { grid-template-columns: repeat(2, 1fr); } }

/* ─── Mid grid + panels ─── */
.ev-mid-grid {
  display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
@media (max-width: 1100px) { .ev-mid-grid { grid-template-columns: 1fr; } }

.ev-panel {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  overflow: hidden;
  display: flex; flex-direction: column;
  animation: evCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.ev-panel-h {
  padding: 12px 18px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.ev-panel-h h3 {
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 0;
  display: flex; align-items: center; gap: 8px;
  text-transform: uppercase; letter-spacing: .04em;
}
.ev-panel-h h3 svg { color: var(--t3, var(--t-muted)); flex-shrink: 0; }
.ev-panel-h-r { display: flex; align-items: center; gap: 8px; }
.ev-panel-meta { font-size: 10.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.ev-panel-body { flex: 1; padding: 14px 18px; }
.ev-list-body { padding: 8px 18px; }

.ev-empty-inline {
  padding: 32px 16px; text-align: center;
  color: var(--t3, var(--t-muted)); font-size: 12px; font-style: italic;
}

/* Donut — uses SignatureDonut (canonical Chart.js doughnut, cutout 84%) */
.ev-donut-body { padding: 18px 18px 16px; }
.ev-donut-body :deep(.sig-donut) { --sd-size: 160px; }
.ev-donut-body :deep(.sd-leg-row) { padding: 5px 6px; }

/* Leaders */
.ev-leader-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0;
  cursor: pointer;
  animation: evFadeSlideIn .25s ease both;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  transition: background .15s;
}
.ev-leader-row:last-child { border-bottom: 0; }
.ev-leader-row:hover { background: rgba(127, 119, 221, .04); border-radius: 6px; }
.ev-leader-rank {
  width: 18px; flex-shrink: 0;
  font-size: 12px; color: var(--t3, var(--t-muted)); font-weight: 600;
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
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ev-leader-sec { font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 1px; }
.ev-leader-rating {
  padding: 3px 9px; border-radius: 5px;
  font-size: 12px; font-weight: 600;
  letter-spacing: .01em;
  flex-shrink: 0; min-width: 42px; text-align: center;
}
.ev-leader-rating.good { background: var(--green-l); color: var(--green); }
.ev-leader-rating.bbb  { background: rgba(55, 138, 221, .12); color: var(--blue); }
.ev-leader-rating.mid  { background: var(--orange-l); color: #D97706; }
.ev-leader-rating.bad  { background: var(--red-l); color: #EF4444; }

/* Updates */
.ev-upd-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 0;
  cursor: pointer;
  animation: evFadeSlideIn .25s ease both;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  transition: background .15s;
}
.ev-upd-row:last-child { border-bottom: 0; }
.ev-upd-row:hover { background: rgba(127, 119, 221, .04); border-radius: 6px; }
.ev-upd-dot {
  width: 9px; height: 9px; border-radius: 50%;
  background: var(--ev-dot, var(--green)); flex-shrink: 0;
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--ev-dot) 18%, transparent);
}
.ev-upd-info { flex: 1; min-width: 0; }
.ev-upd-text { font-size: 12px; color: var(--t3, #5F5E5A); line-height: 1.35; }
.ev-upd-text b { color: var(--t1, #1E2A4A); font-weight: 600; }
.ev-upd-time {
  font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 2px;
  display: flex; align-items: center; gap: 4px;
}
.ev-upd-link { color: var(--p-deep); text-decoration: none; font-size: 11px; }

/* Sector breakdown */
.ev-sector-panel { margin-bottom: 12px; }
.ev-sector-row {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;
}
.ev-sec-card {
  background: var(--bg2, #FAFAFC);
  border: 1px solid rgba(0, 0, 0, .04);
  border-radius: 10px;
  padding: 12px 14px;
  cursor: pointer;
  animation: evCardIn .5s var(--ease-standard) both;
  transition: border-color .15s, box-shadow .15s;
}
.ev-sec-card:hover {
  border-color: var(--ev-sc);
  box-shadow: 0 2px 12px color-mix(in srgb, var(--ev-sc) 18%, transparent);
}
.ev-sec-hd {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.ev-sec-name { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ev-sec-count {
  font-size: 10.5px; padding: 2px 7px;
  background: rgba(127, 119, 221, .08); color: var(--p-deep);
  border-radius: 9px; font-weight: 500; font-feature-settings: "tnum";
}
.ev-sec-body { display: flex; align-items: center; gap: 12px; }
.ev-sec-mini-donut {
  position: relative; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
}
.ev-sec-mini-v {
  position: absolute;
  font-size: 11px; font-weight: 600;
  font-feature-settings: "tnum";
}
.ev-sec-leader { flex: 1; min-width: 0; }
.ev-sec-leader-l {
  font-size: 9px; text-transform: uppercase;
  letter-spacing: .08em; color: var(--t3, var(--t-muted));
  font-weight: 500; margin-bottom: 2px;
}
.ev-sec-leader-n {
  font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ev-sec-leader-n.empty { color: var(--t3, var(--t-muted)); font-weight: 400; }

/* Filter bar */
.ev-filter-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 16px;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 10px;
  margin-bottom: 10px;
  animation: evCardIn .5s var(--ease-standard) var(--d, 0ms) both;
  flex-wrap: wrap;
}
.ev-filter-l { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.ev-chips { display: inline-flex; gap: 5px; flex-wrap: wrap; flex: 1; }
.ev-chip {
  background: rgba(127, 119, 221, .08);
  color: var(--t3, #5F5E5A);
  border: 0; padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  transition: all .12s;
}
.ev-chip:hover { background: rgba(127, 119, 221, .15); color: var(--t1, #1E2A4A); }
.ev-chip.active {
  background: #7F77DD; color: #fff;
  box-shadow: 0 2px 6px rgba(127, 119, 221, .35);
}
.ev-search {
  display: flex; align-items: center; gap: 6px;
  background: #F4F3F9;
  border-radius: 7px;
  padding: 5px 9px;
}
.ev-search input {
  background: transparent; border: 0;
  font-family: inherit; font-size: 12px;
  color: var(--t1, #1E2A4A);
  width: 140px;
  outline: none;
}
.ev-search input::placeholder { color: var(--t3, #94A3B8); }
.ev-search-x {
  background: rgba(226, 75, 74, .15); color: var(--sev-critical);
  border: 0; width: 16px; height: 16px;
  border-radius: 50%; font-size: 12px; line-height: 1;
  cursor: pointer; padding: 0;
  display: flex; align-items: center; justify-content: center;
}

/* Detailed table */
.ev-table-panel { overflow: hidden; }
.ev-mat-clear {
  background: #F4F3F9; border: 0.5px solid rgba(0, 0, 0, .08);
  color: var(--t3, #5F5E5A); font-size: 11px;
  padding: 3px 10px; border-radius: 6px;
  cursor: pointer; font-family: inherit;
}
.ev-mat-clear:hover { background: rgba(127, 119, 221, .1); color: var(--p-deep); }
.ev-table-wrap { overflow-x: auto; }
.ev-rank-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.ev-rank-tbl thead { background: #FAFAFA; }
.ev-rank-tbl thead th {
  padding: 8px 10px; text-align: center;
  font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
}
.ev-rank-tbl thead th.lt { text-align: left; padding-left: 18px; }
.ev-rank-tbl thead th.sortable {
  cursor: pointer; user-select: none;
  transition: color .15s, background .15s;
}
.ev-rank-tbl thead th.sortable:hover { color: var(--t1, #1E2A4A); background: rgba(127, 119, 221, .05); }
.ev-rank-tbl thead th.sortable.on { color: var(--p-deep); }
.ev-rank-tbl thead th .arr { font-size: 8px; opacity: .4; margin-left: 4px; }
.ev-rank-tbl thead th.on .arr { opacity: 1; }

.ev-rank-tbl tbody td {
  padding: 8px 10px; text-align: center;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A);
}
.ev-rank-tbl tbody td.lt {
  text-align: left; padding-left: 18px;
  display: flex; align-items: center; gap: 10px;
}
.ev-rank-tbl tbody tr {
  cursor: pointer;
  animation: evFadeSlideIn .25s ease both;
  transition: background .12s;
}
.ev-rank-tbl tbody tr:hover { background: rgba(127, 119, 221, .04); }
.ev-rank-tbl tbody tr.sec-divider {
  background: rgba(127, 119, 221, .04);
  cursor: default;
}
.ev-rank-tbl tbody tr.sec-divider:hover { background: rgba(127, 119, 221, .04); }
.ev-rank-tbl tbody tr.sec-divider td {
  padding: 6px 18px;
  font-size: 11px; color: var(--t3, #5F5E5A);
  font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em;
}
.sec-strip {
  display: inline-block; width: 3px; height: 12px;
  border-radius: 2px;
  margin-right: 6px;
  vertical-align: middle;
}
.sec-label { color: var(--t1, #1E2A4A); }
.sec-meta { color: var(--t3, var(--t-muted)); font-weight: 500; text-transform: none; letter-spacing: 0; margin-left: 6px; }

.ev-rt-abbr {
  font-size: 9.5px; font-weight: 700;
  padding: 4px 7px; border-radius: 5px;
  letter-spacing: .03em;
  flex-shrink: 0;
  min-width: 38px; text-align: center;
}
.ev-rt-info { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ev-rt-name {
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  display: flex; align-items: center; gap: 5px;
}
.ev-rt-name.unrated { color: var(--t3, var(--t-muted)); }
.ev-rt-sub {
  font-size: 10px; color: var(--t3, var(--t-muted));
  display: flex; gap: 6px;
}
.ev-rt-warn { color: var(--sev-high); font-weight: 500; }
.ev-rt-yr { color: var(--p-deep); font-weight: 500; }

.ev-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 5px;
  font-size: 11.5px; font-weight: 600;
  letter-spacing: .01em;
  cursor: pointer;
  transition: transform .12s;
}
.ev-badge:hover { transform: scale(1.03); }
.ev-badge-up { font-size: 9px; color: var(--green); }
.ev-empty-cell {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px;
  border-radius: 5px;
  background: #F4F3F9; color: var(--t3, #94A3B8);
  font-size: 12px; font-weight: 600;
  cursor: default;
}
.ev-empty-cell.clickable { cursor: pointer; }
.ev-empty-cell.clickable:hover { background: rgba(127, 119, 221, .12); color: var(--p-deep); }
.ev-badge-edit { cursor: pointer; }
.ev-badge-edit:hover { box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .14); }

.ev-empty-state {
  padding: 40px 20px !important;
  text-align: center !important; color: var(--t3, var(--t-muted));
  display: flex !important; flex-direction: column;
  align-items: center; gap: 8px;
  font-style: italic; font-size: 12px;
}
.ev-empty-state svg { opacity: .4; }

/* KPI drill modal */
.ev-modal-bg {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
}
.ev-modal-card {
  background: var(--bg1, #fff);
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(0, 0, 0, .22);
  width: 580px; max-width: 90vw;
  max-height: 80vh;
  display: flex; flex-direction: column;
}
.ev-modal-h {
  padding: 14px 20px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
}
.ev-modal-t { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ev-modal-s { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.ev-modal-x {
  border: 0; background: #F4F3F9;
  width: 28px; height: 28px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: var(--t3, var(--t-muted));
}
.ev-modal-x:hover { background: rgba(226, 75, 74, .12); color: var(--sev-critical); }
.ev-modal-body { flex: 1; overflow-y: auto; }
.ev-modal-tbl { width: 100%; border-collapse: collapse; }
.ev-modal-tbl tr {
  cursor: pointer;
  transition: background .12s;
  animation: evFadeSlideIn .2s ease both;
}
.ev-modal-tbl tr:hover { background: rgba(127, 119, 221, .04); }
.ev-modal-tbl td {
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-size: 13px;
  font-feature-settings: "tnum";
}
.ev-modal-tbl td.lt {
  font-weight: 500; color: var(--t1, #1E2A4A);
  display: flex; align-items: center; gap: 8px;
}
.ev-modal-tbl td.num { text-align: right; min-width: 60px; }
.ev-modal-tbl td.num.big { font-weight: 600; font-size: 14px; }
.ev-modal-tbl td.sub { text-align: right; color: var(--t3, var(--t-muted)); font-size: 11.5px; min-width: 140px; }
.ev-modal-tbl td.empty { text-align: center; padding: 32px; color: var(--t3, var(--t-muted)); font-style: italic; }
.ev-mat-sec { display: inline-block; width: 3px; height: 14px; border-radius: 2px; }

.ev-modal-enter-active, .ev-modal-leave-active { transition: opacity .2s, transform .2s; }
.ev-modal-enter-from, .ev-modal-leave-to { opacity: 0; transform: scale(.96); }

@media (max-width: 480px) {
  .ev-rank-tbl { font-size: 10.5px; }
  .ev-rank-tbl th, .ev-rank-tbl td { padding: 5px 6px; }
  .ev-modal-tbl td, .ev-modal-tbl th { padding: 5px 8px; }
}
</style>
