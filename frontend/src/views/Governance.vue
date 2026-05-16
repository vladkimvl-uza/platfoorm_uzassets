<script setup lang="ts">
/**
 *
 *  1. KPI strip (6 cells): Средний балл / Лучший балл / Независ.директоров% /
 *     Женщин в НС% / Без независимых / Заседаний суммарно
 *  2. 2-col grid (~520px min-height):
 *     • Left: Рейтинг КУ (animated bars per company, score / 100)
 *     • Right: Tabbed card (Независимые директора | Заседания НС)
 *  3. 2-col grid:
 *     • Left: Состав НС (matrix table, sortable columns)
 *     • Right: Комитеты при НС (✓ badges per company × 4 committees)
 *
 *  • Vacant seats недоступно — KPI "Без независимых" (= кол-во компаний с indep=0)
 *  • 4 комитета (audit/strategy/remuneration/nomination) вместо 7
 */
import { computed, onMounted, ref } from "vue";
import {
  governanceApi,
  scoreColor,
  type GovernanceCompanyScore,
  type GovernanceOverviewResponse,
} from "@/api/governance";
import GovCompanyDetailModal from "@/components/Governance/GovCompanyDetailModal.vue";

const overview = ref<GovernanceOverviewResponse | null>(null);
const year = ref<number | null>(null);
const sectorCode = ref<string | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const drillCompanyId = ref<string | null>(null);

type MatrixSort = "score" | "members" | "indep" | "meetings" | "women" | "age";
const matrixSort = ref<MatrixSort>("score");
const matrixDir = ref<"asc" | "desc">("desc");
const indepTab = ref<"indep" | "meetings">("indep");

async function load() {
  loading.value = true;
  error.value = null;
  try {
    overview.value = await governanceApi.getOverview({
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
function openDetail(id: string) { drillCompanyId.value = id; }
async function onDetailSaved() { await load(); }

const headerSub = computed(() => {
  if (!overview.value) return "";
  const k = overview.value.kpis;
  const parts: string[] = [];
  parts.push(year.value ? `FY ${year.value}` : "все годы");
  if (sectorCode.value) parts.push(`сектор ${sectorCode.value}`);
  parts.push(`${k.companies_with_data} из ${k.total_companies} компаний с данными`);
  return parts.join(" · ");
});

// ──────────────────────────────────────────────────────────────────
//   Sector color resolution (from overview.sectors)
// ──────────────────────────────────────────────────────────────────

const SECTOR_PALETTE: Record<string, string> = {
  mining: "#7F77DD", oil_gas: "#EF9F27", energy: "#378ADD",
  transport: "#1D9E75", telecom: "#D4537E", finance: "#534AB7",
  chemical: "#A855F7", construction: "#888780",
};
function sectorColor(code: string | null): string {
  if (!code) return "#888780";
  return SECTOR_PALETTE[code.toLowerCase().replace(/-/g, "_")] || "#888780";
}

// ──────────────────────────────────────────────────────────────────
//   KPI strip (6 cells, computed from rankings)
// ──────────────────────────────────────────────────────────────────

interface KpiCell {
  id: string;
  label: string;
  value: string;
  sub: string;
  accent: string;
  severity: "ok" | "warn" | "bad" | "neutral";
  delay: number;
}

const kpiStrip = computed<KpiCell[]>(() => {
  const rows = overview.value?.rankings ?? [];
  const k = overview.value?.kpis;

  const scores = rows.map(r => r.governance_score).filter((v): v is number => v != null);
  const avgScore = scores.length ? scores.reduce((s, v) => s + v, 0) / scores.length : null;

  const indepPct = k?.avg_independent_pct ?? null;
  const womenPct = k?.avg_women_pct ?? null;
  const totalMembers = rows.reduce((s, r) => s + (r.board_size ?? 0), 0);
  const totalIndep   = rows.reduce((s, r) => s + (r.independent_count ?? 0), 0);
  const totalWomen   = rows.reduce((s, r) => s + (r.women_count ?? 0), 0);
  const totalMeetings = rows.reduce((s, r) => s + (r.meetings_per_year ?? 0), 0);
  const cosWithAll4 = rows.filter(r => r.has_all_4_committees).length;
  const cosCount    = rows.length;

  function sev(v: number | null, ok: number, warn: number): KpiCell["severity"] {
    if (v == null) return "neutral";
    if (v >= ok) return "ok";
    if (v >= warn) return "warn";
    return "bad";
  }

  return [
    {
      id: "avg",
      label: "Средний балл",
      value: avgScore != null ? avgScore.toFixed(0) : "—",
      sub: avgScore != null ? "оценка корп. упр. / 100" : "нет данных",
      accent: "#7F77DD",
      severity: sev(avgScore, 75, 50),
      delay: 40,
    },
    {
      id: "indep",
      label: "Независимые директора",
      value: indepPct != null ? indepPct.toFixed(0) + "%" : "—",
      sub: totalMembers > 0 ? `${totalIndep} из ${totalMembers} членов НС` : "цель 33%+",
      accent: "#1D9E75",
      severity: sev(indepPct, 33, 20),
      delay: 90,
    },
    {
      id: "members",
      label: "Всего членов НС",
      value: String(totalMembers),
      sub: `${cosCount} компаний`,
      accent: "#378ADD",
      severity: "neutral",
      delay: 140,
    },
    {
      id: "meet",
      label: "Заседаний в год",
      value: String(totalMeetings),
      sub: cosCount > 0 ? `в среднем ${Math.round(totalMeetings / cosCount)} на компанию` : "—",
      accent: "#EF9F27",
      severity: "neutral",
      delay: 190,
    },
    {
      id: "women",
      label: "Женщины в НС",
      value: womenPct != null ? womenPct.toFixed(0) + "%" : "—",
      sub: totalMembers > 0 ? `${totalWomen} из ${totalMembers} членов НС` : "цель 20%+",
      accent: "#D4537E",
      severity: sev(womenPct, 20, 10),
      delay: 240,
    },
    {
      id: "all4",
      label: "Полный набор комитетов",
      value: `${cosWithAll4}/${cosCount}`,
      sub: cosCount > 0 ? "Аудит · Стратегия · Возн. · Номин." : "нет данных",
      accent: "#534AB7",
      severity: cosCount === 0 ? "neutral" : cosWithAll4 === cosCount ? "ok" : cosWithAll4 >= cosCount / 2 ? "warn" : "bad",
      delay: 290,
    },
  ];
});

// ──────────────────────────────────────────────────────────────────
//   Rating bars (ranked by score)
// ──────────────────────────────────────────────────────────────────

const ratingRows = computed(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  rows.sort((a, b) => (b.governance_score ?? -1) - (a.governance_score ?? -1));
  return rows;
});

function scoreBg(s: number | null | undefined): string {
  if (s == null) return "#94A3B8";
  if (s >= 75) return "#1D9E75";
  if (s >= 58) return "#378ADD";
  if (s >= 50) return "#EF9F27";
  return "#E24B4A";
}

// ──────────────────────────────────────────────────────────────────
//   Independent / Meetings rows (sortable in tab content)
// ──────────────────────────────────────────────────────────────────

const indepRows = computed(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  rows.sort((a, b) => {
    const ai = a.independent_count ?? 0;
    const bi = b.independent_count ?? 0;
    if (bi !== ai) return bi - ai;
    return (b.independent_pct ?? 0) - (a.independent_pct ?? 0);
  });
  return rows;
});

const meetingsRows = computed(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  rows.sort((a, b) => (b.meetings_per_year ?? 0) - (a.meetings_per_year ?? 0));
  return rows;
});

const maxMeetings = computed(() => {
  const rows = overview.value?.rankings ?? [];
  return Math.max(1, ...rows.map(r => r.meetings_per_year ?? 0));
});

function indepColor(pct: number | null): string {
  if (pct == null) return "#94A3B8";
  if (pct >= 40) return "#1D9E75";
  if (pct >= 25) return "#378ADD";
  return "#E24B4A";
}

function meetingsColor(n: number | null): string {
  if (n == null) return "#94A3B8";
  if (n >= 15) return "#7F77DD";
  if (n >= 8) return "#378ADD";
  return "#E24B4A";
}

// ──────────────────────────────────────────────────────────────────
//   Composition matrix (sortable)
// ──────────────────────────────────────────────────────────────────

interface MatrixRow {
  r: GovernanceCompanyScore;
  score: number | null;
  members: number | null;
  indep: number | null;
  indepPct: number | null;
  meetings: number | null;
  women: number | null;
  womenPct: number | null;
  age: number | null;
}

const matrixRows = computed<MatrixRow[]>(() => {
  const rows = (overview.value?.rankings ?? []).map(r => ({
    r,
    score: r.governance_score,
    members: r.board_size,
    indep: r.independent_count,
    indepPct: r.independent_pct,
    meetings: r.meetings_per_year,
    women: r.women_count,
    womenPct: r.women_pct,
    age: null as number | null, // not in current API; placeholder
  }));

  const key = matrixSort.value;
  const dir = matrixDir.value === "desc" ? -1 : 1;
  rows.sort((a, b) => {
    const va = (a as Record<string, number | null>)[key];
    const vb = (b as Record<string, number | null>)[key];
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return ((va as number) - (vb as number)) * dir;
  });
  return rows;
});

function matrixSortBy(k: MatrixSort) {
  if (matrixSort.value === k) {
    matrixDir.value = matrixDir.value === "desc" ? "asc" : "desc";
  } else {
    matrixSort.value = k;
    matrixDir.value = "desc";
  }
}

function sortArrow(k: MatrixSort): string {
  if (matrixSort.value !== k) return "▼";
  return matrixDir.value === "desc" ? "▼" : "▲";
}

// ──────────────────────────────────────────────────────────────────
//   Committee matrix (current API has 4: audit/remuneration/nomination/strategy)
//   We need per-company committee flags — those are in CompanyDetail, not overview.
//   For now show committees_count as proxy + drill via company_detail (TODO future)
// ──────────────────────────────────────────────────────────────────

const committeeRows = computed(() => {
  // Sort alphabetically for stable visual
  const rows = [...(overview.value?.rankings ?? [])];
  rows.sort((a, b) => (a.company_name ?? a.company_code).localeCompare(b.company_name ?? b.company_code, "ru"));
  return rows;
});

const committeeTotals = computed(() => {
  const rows = committeeRows.value;
  return {
    audit:     rows.filter(r => r.has_audit_committee).length,
    strategy:  rows.filter(r => r.has_strategy_committee).length,
    remun:     rows.filter(r => r.has_remuneration_committee).length,
    nomin:     rows.filter(r => r.has_nomination_committee).length,
  };
});

// ──────────────────────────────────────────────────────────────────
//   Lifecycle
// ──────────────────────────────────────────────────────────────────

onMounted(() => { load(); });
</script>

<template>
  <Transition name="uza-fade" mode="out-in">
    <div :key="String(year ?? '_')">
      <div class="gv-view">

        <!-- ═══ Topbar (dark navy gradient, как KPI/BP) ═══ -->
        <div class="gv-topbar">
          <div class="gv-tb-l">
            <div class="gv-tb-eyebrow">UzAssets · Корпоративное управление</div>
            <div class="gv-tb-title">Дашборд КУ · {{ overview?.rankings?.length || 0 }} компаний</div>
            <div class="gv-tb-sub">{{ headerSub }}</div>
          </div>
          <div class="gv-tb-r">
            <select :value="String(year || '')" @change="onYearChange" class="gv-in">
              <option value="">Все годы</option>
              <option v-for="y in (overview?.available_years || [])" :key="y" :value="y">{{ y }}</option>
            </select>
            <select :value="sectorCode || ''" @change="onSectorChange" class="gv-in">
              <option value="">Все сектора</option>
              <option v-for="s in (overview?.sectors || [])" :key="s.code" :value="s.code">
                {{ s.code }} ({{ s.count }})
              </option>
            </select>
          </div>
        </div>

        <div v-if="loading && !overview" class="gv-loading">Загрузка...</div>
        <div v-else-if="error && !overview" class="gv-error">{{ error }}</div>

        <div v-else-if="overview" class="gv-body">

          <!-- ═══ 1. KPI strip (6 cells) ═══ -->
          <div class="gv-kpi-strip">
            <div
              v-for="cell in kpiStrip"
              :key="cell.id"
              class="kpi2 fin-shimmer gv-kpi-cell"
              :class="cell.severity"
              :style="{ '--kpi2-accent': cell.accent, '--kpi2-d': cell.delay + 'ms', '--d': cell.delay + 'ms' }"
            >
              <div class="kpi2-lbl gv-kpi-lbl">{{ cell.label }}</div>
              <div class="kpi2-val gv-kpi-val">{{ cell.value }}</div>
              <div class="kpi2-sub gv-kpi-sub">{{ cell.sub }}</div>
            </div>
          </div>

          <!-- ═══ 2. Rating bars + Tabbed indep/meetings ═══ -->
          <div class="gv-mid-grid">

            <!-- Left: Rating bars -->
            <div class="gv-card gv-rating" style="--d:380ms">
              <div class="gv-card-hd">
                <span class="gv-card-ttl">Рейтинг корпоративного управления</span>
                <span class="gv-card-meta">Баллы / 100</span>
              </div>
              <div class="gv-rating-body">
                <div
                  v-for="(r, i) in ratingRows"
                  :key="r.company_id"
                  class="gv-rt-row"
                  :style="{ '--d': (Math.min(i, 30) * 25) + 'ms' }"
                  @click="openDetail(r.company_id)"
                >
                  <span class="gv-rt-sec" :style="{ background: sectorColor(r.sector_code) }"></span>
                  <span class="gv-rt-name">{{ r.company_name || r.company_code }}</span>
                  <span class="gv-rt-score" :style="{ color: scoreBg(r.governance_score) }">
                    {{ r.governance_score != null ? r.governance_score.toFixed(0) : "—" }}
                  </span>
                  <div class="gv-rt-bar-wrap">
                    <div
                      class="gv-rt-bar-fill"
                      :style="{
                        '--w': Math.max(2, Math.min(100, r.governance_score ?? 0)) + '%',
                        background: scoreBg(r.governance_score),
                      }"
                    ></div>
                  </div>
                </div>
                <div v-if="!ratingRows.length" class="gv-empty-inline">Нет данных</div>
              </div>
            </div>

            <!-- Right: Tabbed independent / meetings -->
            <div class="gv-card gv-tabbed" style="--d:430ms">
              <div class="gv-card-hd">
                <div class="gv-seg">
                  <button :class="{ on: indepTab === 'indep' }" @click="indepTab = 'indep'">Независимые директора</button>
                  <button :class="{ on: indepTab === 'meetings' }" @click="indepTab = 'meetings'">Заседания НС</button>
                </div>
                <span class="gv-card-meta">{{ indepTab === 'indep' ? 'Доля от НС' : 'Количество в год' }}</span>
              </div>

              <div v-if="indepTab === 'indep'" class="gv-rating-body">
                <div
                  v-for="(r, i) in indepRows"
                  :key="r.company_id"
                  class="gv-tab-row"
                  :style="{ '--d': (Math.min(i, 30) * 25) + 'ms' }"
                  @click="openDetail(r.company_id)"
                >
                  <span class="gv-rt-sec" :style="{ background: sectorColor(r.sector_code) }"></span>
                  <span class="gv-tab-name" :class="{ 'zero-indep': r.independent_count === 0 }">{{ r.company_name || r.company_code }}</span>
                  <span class="gv-tab-val" :style="{ color: indepColor(r.independent_pct) }">
                    {{ r.independent_count ?? 0 }} / {{ r.board_size ?? '—' }}
                  </span>
                  <div class="gv-rt-bar-wrap">
                    <div
                      class="gv-rt-bar-fill"
                      :style="{
                        '--w': Math.max(2, Math.min(100, r.independent_pct ?? 0)) + '%',
                        background: indepColor(r.independent_pct),
                      }"
                    ></div>
                  </div>
                </div>
              </div>

              <div v-else class="gv-rating-body">
                <div
                  v-for="(r, i) in meetingsRows"
                  :key="r.company_id"
                  class="gv-tab-row"
                  :style="{ '--d': (Math.min(i, 30) * 25) + 'ms' }"
                  @click="openDetail(r.company_id)"
                >
                  <span class="gv-rt-sec" :style="{ background: sectorColor(r.sector_code) }"></span>
                  <span class="gv-tab-name" :class="{ 'zero-indep': (r.meetings_per_year ?? 0) < 5 }">{{ r.company_name || r.company_code }}</span>
                  <span class="gv-tab-val" :style="{ color: meetingsColor(r.meetings_per_year) }">
                    {{ r.meetings_per_year ?? '—' }}
                  </span>
                  <div class="gv-rt-bar-wrap">
                    <div
                      class="gv-rt-bar-fill"
                      :style="{
                        '--w': Math.max(2, Math.min(100, ((r.meetings_per_year ?? 0) / maxMeetings) * 100)) + '%',
                        background: meetingsColor(r.meetings_per_year),
                      }"
                    ></div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- ═══ 3. Composition matrix + Committees ═══ -->
          <div class="gv-bot-grid">

            <!-- Left: Composition matrix -->
            <div class="gv-card gv-matrix" style="--d:480ms">
              <div class="gv-card-hd">
                <span class="gv-card-ttl">Состав наблюдательных советов</span>
              </div>
              <div class="gv-matrix-wrap">
                <table class="gv-mat-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th @click="matrixSortBy('score')" class="sortable">Балл <span class="arr">{{ sortArrow('score') }}</span></th>
                      <th @click="matrixSortBy('members')" class="sortable">Члены <span class="arr">{{ sortArrow('members') }}</span></th>
                      <th @click="matrixSortBy('indep')" class="sortable">Независ. <span class="arr">{{ sortArrow('indep') }}</span></th>
                      <th @click="matrixSortBy('meetings')" class="sortable">Заседания <span class="arr">{{ sortArrow('meetings') }}</span></th>
                      <th @click="matrixSortBy('women')" class="sortable">Женщины <span class="arr">{{ sortArrow('women') }}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(m, i) in matrixRows"
                      :key="m.r.company_id"
                      :style="{ '--d': (Math.min(i, 30) * 20) + 'ms' }"
                      @click="openDetail(m.r.company_id)"
                    >
                      <td class="lt">
                        <span class="gv-mat-sec" :style="{ background: sectorColor(m.r.sector_code) }"></span>
                        <span class="gv-mat-name">{{ m.r.company_name || m.r.company_code }}</span>
                      </td>
                      <td class="num">
                        <span class="gv-score-pill" :style="{ background: scoreBg(m.score) + '20', color: scoreBg(m.score) }">
                          {{ m.score != null ? m.score.toFixed(0) : '—' }}
                        </span>
                      </td>
                      <td class="num">{{ m.members ?? '—' }}</td>
                      <td class="num">
                        <span :style="{ color: indepColor(m.indepPct) }">{{ m.indep ?? '—' }}</span>
                        <span v-if="m.indepPct != null" class="gv-mat-pct">({{ m.indepPct.toFixed(0) }}%)</span>
                      </td>
                      <td class="num">{{ m.meetings ?? '—' }}</td>
                      <td class="num">
                        <span :style="{ color: m.women && m.women > 0 ? '#D4537E' : '#888780' }">{{ m.women ?? '—' }}</span>
                        <span v-if="m.womenPct != null && m.women && m.women > 0" class="gv-mat-pct">({{ m.womenPct.toFixed(0) }}%)</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="gv-mat-legend">
                <span><span class="dot" style="background:#1D9E75"></span> 75+</span>
                <span><span class="dot" style="background:#378ADD"></span> 58–75</span>
                <span><span class="dot" style="background:#EF9F27"></span> 50–58</span>
                <span><span class="dot" style="background:#E24B4A"></span> &lt; 50</span>
              </div>
            </div>

            <!-- Right: Committees per-committee table (4 cols) -->
            <div class="gv-card gv-committees" style="--d:530ms">
              <div class="gv-card-hd">
                <span class="gv-card-ttl">Комитеты при наблюдательном совете</span>
                <span class="gv-card-meta">
                  Аудит {{ committeeTotals.audit }}/{{ committeeRows.length }} ·
                  Стратегия {{ committeeTotals.strategy }}/{{ committeeRows.length }}
                </span>
              </div>
              <div class="gv-cm-wrap">
                <table class="gv-cm-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th>Аудит</th>
                      <th>Стратегия</th>
                      <th>Возн.</th>
                      <th>Номин.</th>
                      <th>Всего</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(r, i) in committeeRows"
                      :key="r.company_id"
                      :style="{ '--d': (Math.min(i, 30) * 20) + 'ms' }"
                      @click="openDetail(r.company_id)"
                    >
                      <td class="lt">
                        <span class="gv-mat-sec" :style="{ background: sectorColor(r.sector_code) }"></span>
                        <span class="gv-mat-name">{{ r.company_name || r.company_code }}</span>
                      </td>
                      <td class="num">
                        <span v-if="r.has_audit_committee" class="gv-cm-check yes" title="Есть"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.5 2.5L9.5 3.5"/></svg></span>
                        <span v-else class="gv-cm-check no" title="Нет">—</span>
                      </td>
                      <td class="num">
                        <span v-if="r.has_strategy_committee" class="gv-cm-check yes"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.5 2.5L9.5 3.5"/></svg></span>
                        <span v-else class="gv-cm-check no">—</span>
                      </td>
                      <td class="num">
                        <span v-if="r.has_remuneration_committee" class="gv-cm-check yes"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.5 2.5L9.5 3.5"/></svg></span>
                        <span v-else class="gv-cm-check no">—</span>
                      </td>
                      <td class="num">
                        <span v-if="r.has_nomination_committee" class="gv-cm-check yes"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.5 2.5L9.5 3.5"/></svg></span>
                        <span v-else class="gv-cm-check no">—</span>
                      </td>
                      <td class="num">
                        <span class="gv-cm-count" :class="{ full: r.has_all_4_committees, none: r.committees_count === 0 }">
                          {{ r.committees_count }}/4
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

        </div>

        <!-- Drill modal -->
        <GovCompanyDetailModal
          v-if="drillCompanyId"
          :company-id="drillCompanyId"
          :year="year ?? undefined"
          @close="drillCompanyId = null"
          @saved="onDetailSaved"
        />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.gv-view { background: #F4F3F9; min-height: 100%; font-family: var(--font, system-ui); }

/* ─── Premium animations (1:1 KPI/BP pattern) ─── */
@keyframes gvCardIn {
  0% { opacity: 0; transform: translateY(12px) scale(.98); }
  60% { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes gvStripeIn { 0% { transform: scaleX(0); } 100% { transform: scaleX(1); } }
@keyframes gvBarFill { 0% { width: 0; } 100% { width: var(--w, 100%); } }
@keyframes gvShimmer { 0% { left: -60%; } 100% { left: 160%; } }
@keyframes gvNumIn {
  0% { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes gvRowIn {
  0% { opacity: 0; transform: translateX(-4px); }
  100% { opacity: 1; transform: translateX(0); }
}

/* ─── Topbar ─── */
.gv-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}
.gv-tb-l { display: flex; flex-direction: column; gap: 2px; }
.gv-tb-eyebrow { font-size: 10px; font-weight: 500; color: rgba(255, 255, 255, .55); letter-spacing: .08em; text-transform: uppercase; }
.gv-tb-title { font-size: 16px; font-weight: 500; color: #fff; letter-spacing: -.005em; }
.gv-tb-sub { font-size: 11px; font-weight: 500; color: rgba(255, 255, 255, .65); }
.gv-tb-r { display: flex; gap: 8px; align-items: center; }
.gv-in {
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  outline: none;
}
.gv-in option { background: #1E2A4A; color: #fff; }

.gv-loading, .gv-error { padding: 40px; text-align: center; color: #888780; }
.gv-error { color: #A32D2D; }

.gv-body { padding: 20px 22px 28px; }

/* ─── KPI strip ─── */
.gv-kpi-strip {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
  margin-bottom: 14px;
}
.gv-kpi-cell {
  background: rgba(255, 255, 255, .92);
  border: 1px solid rgba(255, 255, 255, .7);
  border-radius: 12px;
  padding: 14px 16px 12px;
  position: relative; overflow: hidden;
  animation: gvCardIn .5s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
  box-shadow: 0 2px 8px rgba(15, 23, 60, .06);
}
.gv-kpi-cell::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--kpi2-accent, #7F77DD);
  transform-origin: left;
  animation: gvStripeIn .8s cubic-bezier(.4,0,.2,1) var(--kpi2-d, 0ms) both;
}
.gv-kpi-cell.fin-shimmer::after {
  content: ""; position: absolute; top: 0; left: -60%;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(127, 119, 221, .07), transparent);
  animation: gvShimmer 1.1s ease-out calc(var(--d, 0ms) + 200ms) forwards;
  pointer-events: none; z-index: 2;
}
.gv-kpi-cell.ok      { --kpi2-accent: #1D9E75; }
.gv-kpi-cell.warn    { --kpi2-accent: #EF9F27; }
.gv-kpi-cell.bad     { --kpi2-accent: #E24B4A; }
.gv-kpi-cell.neutral { /* keeps original accent */ }
.gv-kpi-lbl {
  font-size: 10.5px; color: #888780; text-transform: uppercase;
  letter-spacing: .06em; font-weight: 500; margin-bottom: 8px;
  animation: gvNumIn .4s ease calc(var(--d, 0ms) + 50ms) both;
}
.gv-kpi-val {
  font-size: 30px; font-weight: 400;
  color: var(--kpi2-accent, #1E2A4A);
  letter-spacing: -.035em; line-height: 1;
  font-feature-settings: "tnum"; margin: 0;
  animation: gvNumIn .5s ease calc(var(--d, 0ms) + 200ms) both;
}
.gv-kpi-sub {
  font-size: 11px; color: #888780;
  margin-top: 6px; font-weight: 500;
  animation: gvNumIn .4s ease calc(var(--d, 0ms) + 300ms) both;
}

/* ─── Cards (generic) ─── */
.gv-card {
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  overflow: hidden;
  display: flex; flex-direction: column;
  animation: gvCardIn .65s cubic-bezier(.34,1.2,.64,1) var(--d, 0ms) both;
}
.gv-card-hd {
  padding: 12px 16px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
}
.gv-card-ttl {
  font-size: 11px; font-weight: 500; color: #888780;
  text-transform: uppercase; letter-spacing: .07em;
}
.gv-card-meta { font-size: 10.5px; color: #888780; font-weight: 500; }

/* ─── Mid grid (rating + tabs) ─── */
.gv-mid-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
}
.gv-rating, .gv-tabbed { min-height: 520px; }

.gv-rating-body {
  flex: 1; overflow-y: auto;
  scrollbar-width: thin;
}
.gv-rating-body::-webkit-scrollbar { width: 6px; }
.gv-rating-body::-webkit-scrollbar-thumb {
  background: rgba(127, 119, 221, .25); border-radius: 3px;
}
.gv-rt-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  animation: gvRowIn .25s ease var(--d, 0ms) both;
  transition: background .15s;
}
.gv-rt-row:hover { background: rgba(127, 119, 221, .04); }
.gv-rt-sec {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; flex-shrink: 0;
}
.gv-rt-name {
  font-size: 12.5px; font-weight: 500; color: #1E2A4A;
  min-width: 180px; max-width: 220px;
  flex-shrink: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.gv-rt-score {
  font-size: 13px; font-weight: 500;
  min-width: 44px; text-align: right;
  font-feature-settings: "tnum"; flex-shrink: 0;
}
.gv-rt-bar-wrap {
  flex: 1; height: 6px;
  background: rgba(0, 0, 0, .05);
  border-radius: 3px; overflow: hidden;
}
.gv-rt-bar-fill {
  height: 100%; border-radius: 3px; opacity: .55;
  animation: gvBarFill .9s cubic-bezier(.22,.61,.36,1) calc(var(--d, 0ms) + 200ms) both;
}

/* ─── Tabbed (indep / meetings) ─── */
.gv-seg {
  display: inline-flex;
  background: rgba(0, 0, 0, .04);
  border-radius: 7px;
  padding: 2px;
}
.gv-seg button {
  background: transparent; border: 0;
  font-size: 11px; padding: 4px 12px;
  border-radius: 5px;
  color: #888780; cursor: pointer;
  font-family: inherit; font-weight: 500;
  transition: all .15s;
}
.gv-seg button:hover { color: #1E2A4A; }
.gv-seg button.on {
  background: #fff; color: #1E2A4A;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .08);
}

.gv-tab-row {
  display: grid;
  grid-template-columns: 3px 200px 70px 1fr;
  align-items: center; gap: 8px;
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  animation: gvRowIn .25s ease var(--d, 0ms) both;
  transition: background .15s;
}
.gv-tab-row:hover { background: rgba(127, 119, 221, .04); }
.gv-tab-name {
  font-size: 12.5px; font-weight: 500; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gv-tab-name.zero-indep { color: #E24B4A; }
.gv-tab-val {
  font-size: 12px; font-weight: 500;
  text-align: right; font-feature-settings: "tnum";
  white-space: nowrap;
}

.gv-empty-inline {
  text-align: center; color: #888780;
  font-size: 12px; padding: 40px 20px; font-style: italic;
}

/* ─── Bottom grid (matrix + committees) ─── */
.gv-bot-grid {
  display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px;
}

.gv-matrix-wrap, .gv-cm-wrap {
  flex: 1; overflow: auto;
  scrollbar-width: thin;
}
.gv-mat-tbl, .gv-cm-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.gv-mat-tbl thead, .gv-cm-tbl thead {
  background: #FAFAFA;
  position: sticky; top: 0;
}
.gv-mat-tbl thead th, .gv-cm-tbl thead th {
  padding: 8px 8px; text-align: center;
  font-size: 11px; font-weight: 500; color: #888780;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
  text-transform: none; letter-spacing: 0;
}
.gv-mat-tbl thead th.lt, .gv-cm-tbl thead th.lt {
  text-align: left; padding-left: 12px;
}
.gv-mat-tbl thead th.sortable {
  cursor: pointer; user-select: none;
  transition: color .15s, background .15s;
}
.gv-mat-tbl thead th.sortable:hover { color: #1E2A4A; background: rgba(127, 119, 221, .05); }
.gv-mat-tbl thead th .arr { font-size: 8px; opacity: .4; margin-left: 3px; }

.gv-mat-tbl tbody td, .gv-cm-tbl tbody td {
  padding: 8px 8px; text-align: center;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-feature-settings: "tnum";
  color: #1E2A4A;
}
.gv-mat-tbl tbody td.lt, .gv-cm-tbl tbody td.lt {
  text-align: left; padding-left: 12px;
  display: flex; align-items: center; gap: 8px;
}
.gv-mat-tbl tbody td.num, .gv-cm-tbl tbody td.num { text-align: center; }
.gv-mat-tbl tbody tr, .gv-cm-tbl tbody tr {
  cursor: pointer;
  animation: gvRowIn .25s ease var(--d, 0ms) both;
  transition: background .15s;
}
.gv-mat-tbl tbody tr:hover, .gv-cm-tbl tbody tr:hover {
  background: rgba(127, 119, 221, .04);
}

.gv-mat-sec {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; flex-shrink: 0;
}
.gv-mat-name {
  font-size: 12px; font-weight: 500; color: #1E2A4A;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gv-mat-pct {
  font-size: 10px; color: #888780; font-weight: 500;
  margin-left: 2px;
}
.gv-score-pill {
  display: inline-block; padding: 2px 7px;
  border-radius: 4px; font-size: 11px; font-weight: 500;
  font-feature-settings: "tnum";
}

.gv-mat-legend {
  padding: 6px 14px; display: flex; gap: 12px;
  font-size: 10.5px; color: #888780;
  border-top: 0.5px solid rgba(0, 0, 0, .06);
}
.gv-mat-legend .dot {
  display: inline-block; width: 7px; height: 7px;
  border-radius: 50%; margin-right: 4px; vertical-align: middle;
}

.gv-cm-count {
  display: inline-block; padding: 3px 9px;
  border-radius: 11px; font-size: 11px; font-weight: 500;
  font-feature-settings: "tnum";
  background: rgba(127, 119, 221, .12); color: #534AB7;
}
.gv-cm-count.full { background: rgba(29, 158, 117, .15); color: #0F6E56; }
.gv-cm-count.none { background: rgba(226, 75, 74, .12); color: #A32D2D; }

.gv-cm-check {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 5px;
  font-size: 11px; font-weight: 500;
}
.gv-cm-check.yes { background: rgba(29, 158, 117, .12); color: #0F6E56; }
.gv-cm-check.no  { background: #F4F3F9; color: #94A3B8; }

.gv-cm-note {
  padding: 8px 14px;
  font-size: 11px; color: #5F5E5A;
  border-top: 0.5px solid rgba(0, 0, 0, .06);
  line-height: 1.4;
}

/* ─── Responsive ─── */
@media (max-width: 1200px) {
  .gv-kpi-strip { grid-template-columns: repeat(3, 1fr); }
  .gv-mid-grid, .gv-bot-grid { grid-template-columns: 1fr; }
  .gv-rating, .gv-tabbed { min-height: 380px; }
}
@media (max-width: 720px) {
  .gv-kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .gv-body { padding: 14px 12px; }
  .gv-tab-row { grid-template-columns: 3px 1fr 70px 80px; }
}
</style>
