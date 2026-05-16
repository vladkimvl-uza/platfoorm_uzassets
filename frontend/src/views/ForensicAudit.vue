<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { api } from "@/api/client";
import { useSectorMeta } from "@/utils/sectorMeta";

// ─── Types ───────────────────────────────────────────────────────
interface YearRow {
  y: number;
  plan?: number | null;
  fact?: number | null;
  n9p?: number | null;
  n9f?: number | null;
  q1p?: number | null;
  q1f?: number | null;
  q2p?: number | null;
  q2f?: number | null;
  q3p?: number | null;
  q3f?: number | null;
  q4p?: number | null;
  q4f?: number | null;
}

interface ForensicCompany {
  n: string;            // display name
  k: string;            // code
  s: string;            // sector
  sector_color: string;
  yP24?: number | null; yF24?: number | null;
  nP24?: number | null; nF24?: number | null;
  yP25?: number | null; yF25?: number | null;
  nP25?: number | null; nF25?: number | null;
  yP26?: number | null;
  plan?: string;
  forensic?: string;
  auditor?: string;
  aYears?: string;
  years?: YearRow[];
}

interface Kpis {
  total_companies: number;
  plan_approved: number;
  forensic_done: number;
  with_auditor: number;
}

// ─── State ───────────────────────────────────────────────────────
const companies = ref<ForensicCompany[]>([]);
const kpis = ref<Kpis>({ total_companies: 0, plan_approved: 0, forensic_done: 0, with_auditor: 0 });
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Filters
const sectorFilter = ref<string>("");
const yearFilter = ref<number>(2025);
const periodFilter = ref<"year" | "9m" | "q1" | "q2" | "q3" | "q4">("9m");

// ─── Computed ────────────────────────────────────────────────────
// Pack 7.20: sector labels come from companies store via useSectorMeta —
// admin edits in Companies admin → propagate here automatically.
const secMeta = useSectorMeta();
const sectorNames = computed<Record<string, string>>(() => {
  const result: Record<string, string> = { "": "Все секторы" };
  for (const code of secMeta.SECTOR_ORDER) {
    result[code] = secMeta.byCodeMap.value[code].label;
  }
  return result;
});

const filteredCompanies = computed(() =>
  sectorFilter.value
    ? companies.value.filter(c => c.s === sectorFilter.value)
    : companies.value
);

function getYr(c: ForensicCompany, year: number): YearRow | null {
  if (Array.isArray(c.years)) {
    return c.years.find(y => y.y === year) || null;
  }
  return null;
}

function getPlan(c: ForensicCompany): number | null {
  const yr = getYr(c, yearFilter.value);
  if (yr) {
    if (periodFilter.value === "year") return yr.plan ?? null;
    if (periodFilter.value === "9m")   return yr.n9p ?? null;
    const k = `${periodFilter.value}p` as keyof YearRow;
    return (yr[k] as number | null | undefined) ?? null;
  }
  // Legacy fallback for companies without years[]
  if (yearFilter.value === 2024)
    return periodFilter.value === "year" ? (c.yP24 ?? null)
         : periodFilter.value === "9m"   ? (c.nP24 ?? null) : null;
  if (yearFilter.value === 2025)
    return periodFilter.value === "year" ? (c.yP25 ?? null)
         : periodFilter.value === "9m"   ? (c.nP25 ?? null) : null;
  if (yearFilter.value === 2026)
    return periodFilter.value === "year" ? (c.yP26 ?? null) : null;
  return null;
}

function getFact(c: ForensicCompany): number | null {
  const yr = getYr(c, yearFilter.value);
  if (yr) {
    if (periodFilter.value === "year") return yr.fact ?? null;
    if (periodFilter.value === "9m")   return yr.n9f ?? null;
    const k = `${periodFilter.value}f` as keyof YearRow;
    return (yr[k] as number | null | undefined) ?? null;
  }
  if (yearFilter.value === 2024)
    return periodFilter.value === "year" ? (c.yF24 ?? null)
         : periodFilter.value === "9m"   ? (c.nF24 ?? null) : null;
  if (yearFilter.value === 2025)
    return periodFilter.value === "year" ? (c.yF25 ?? null)
         : periodFilter.value === "9m"   ? (c.nF25 ?? null) : null;
  return null;
}

function getPct(c: ForensicCompany): number | null {
  const p = getPlan(c);
  const f = getFact(c);
  return p && f ? Math.round((f / p) * 1000) / 10 : null;
}

// Formatting helpers
function fmtNum(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return Math.round(v).toLocaleString("ru-RU");
  if (v < 10)    return v.toFixed(1);
  return Math.round(v).toLocaleString("ru-RU");
}

function pctColor(p: number | null): string {
  if (p == null) return "var(--t3)";
  if (p >= 80) return "#1D9E75";
  if (p >= 50) return "#D97706";
  return "#993D3D";
}

function planBadge(plan: string | undefined): { text: string; bg: string; fg: string } {
  if (!plan) return { text: "—", bg: "var(--bg3)", fg: "var(--t3)" };
  if (plan.startsWith("Утверждён")) return { text: "Утверждён", bg: "rgba(29,158,117,.12)", fg: "#1D9E75" };
  return { text: plan, bg: "rgba(226,75,74,.08)", fg: "#993D3D" };
}

function forensicBadge(f: string | undefined): { text: string; bg: string; fg: string } {
  if (!f) return { text: "—", bg: "var(--bg3)", fg: "var(--t3)" };
  if (f === "Завершён")    return { text: "Завершён",   bg: "rgba(29,158,117,.12)", fg: "#1D9E75" };
  if (f === "В процессе")  return { text: "В процессе", bg: "rgba(55,138,221,.10)", fg: "#378ADD" };
  if (f.startsWith("Тендер")) return { text: f, bg: "rgba(239,159,39,.10)", fg: "#D97706" };
  return { text: f, bg: "rgba(226,75,74,.08)", fg: "#993D3D" };
}

const auditorColors: Record<string, string> = {
  KPMG: "#378ADD", PwC: "#D85A30", Deloitte: "#1D9E75", "E&Y": "#D97706",
};

function cleanAud(a: string | undefined): string {
  return a ? a.replace(/\s*до\s+\d{2}\.\d{2}\.\d{4}/, "") : "—";
}

function audColor(a: string | undefined): string {
  if (!a) return "var(--t3)";
  const k = cleanAud(a).trim();
  return auditorColors[k] || "var(--t2)";
}

// Sort by % execution desc
const sortedCompanies = computed(() => {
  return filteredCompanies.value.slice().sort((a, b) => {
    const pa = getPct(a) ?? -1;
    const pb = getPct(b) ?? -1;
    return pb - pa;
  });
});

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const { data } = await api.get<{ companies: ForensicCompany[]; kpis: Kpis }>(
      "/forensic/overview"
    );
    companies.value = data.companies || [];
    kpis.value = data.kpis || { total_companies: 0, plan_approved: 0, forensic_done: 0, with_auditor: 0 };
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail || e?.message || "Ошибка загрузки";
    companies.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="forensic-page">
    <!-- Header -->
    <div class="page-header">
      <div class="page-eyebrow">UZASSETS · ЗАКУПКИ</div>
      <h1 class="page-title">Закупки и форензик-аудит</h1>
      <div class="page-sub">
        План закупок и статус форензик-аудита по {{ kpis.total_companies }} компаниям портфеля
      </div>
    </div>

    <!-- Filters -->
    <div class="filters-row">
      <div class="filter-group">
        <label class="filter-label">Сектор</label>
        <select v-model="sectorFilter" class="filter-select">
          <option v-for="(name, code) in sectorNames" :key="code" :value="code">{{ name }}</option>
        </select>
      </div>
      <div class="filter-group">
        <label class="filter-label">Год</label>
        <div class="filter-pills">
          <button v-for="y in [2024, 2025, 2026]" :key="y"
                  :class="['pill', { active: yearFilter === y }]"
                  @click="yearFilter = y">{{ y }}</button>
        </div>
      </div>
      <div class="filter-group">
        <label class="filter-label">Период</label>
        <div class="filter-pills">
          <button v-for="p in (['year', '9m', 'q1', 'q2', 'q3', 'q4'] as const)" :key="p"
                  :class="['pill', { active: periodFilter === p }]"
                  @click="periodFilter = p">
            {{ p === "year" ? "Год" : p === "9m" ? "9 мес" : p.toUpperCase() }}
          </button>
        </div>
      </div>
    </div>

    <!-- KPI strip -->
    <div class="kpi-strip">
      <div class="kpi-card" style="--kpi-accent: #7F77DD">
        <div class="kpi-label">КОМПАНИЙ В ПОРТФЕЛЕ</div>
        <div class="kpi-value">{{ kpis.total_companies }}</div>
      </div>
      <div class="kpi-card" style="--kpi-accent: #1D9E75">
        <div class="kpi-label">ПЛАН УТВЕРЖДЁН</div>
        <div class="kpi-value">{{ kpis.plan_approved }}<span class="kpi-of">/{{ kpis.total_companies }}</span></div>
      </div>
      <div class="kpi-card" style="--kpi-accent: #378ADD">
        <div class="kpi-label">ФОРЕНЗИК ЗАВЕРШЁН</div>
        <div class="kpi-value">{{ kpis.forensic_done }}<span class="kpi-of">/{{ kpis.total_companies }}</span></div>
      </div>
      <div class="kpi-card" style="--kpi-accent: #EF9F27">
        <div class="kpi-label">С НАЗНАЧЕННЫМ АУДИТОРОМ</div>
        <div class="kpi-value">{{ kpis.with_auditor }}<span class="kpi-of">/{{ kpis.total_companies }}</span></div>
      </div>
    </div>

    <!-- Loading / Error -->
    <div v-if="loading" class="state-msg">Загрузка…</div>
    <div v-else-if="errorMsg" class="state-msg error">⚠ {{ errorMsg }}</div>
    <div v-else-if="!sortedCompanies.length" class="state-msg">Нет данных</div>

    <!-- Companies table -->
    <div v-else class="table-card">
      <table class="data-table">
        <thead>
          <tr>
            <th class="col-co">КОМПАНИЯ</th>
            <th class="col-num">ПЛАН</th>
            <th class="col-num">ФАКТ</th>
            <th class="col-bar">% ИСПОЛНЕНИЯ</th>
            <th class="col-status">ПЛАН ЗАКУПОК</th>
            <th class="col-status">ФОРЕНЗИК</th>
            <th class="col-aud">АУДИТОР</th>
            <th class="col-years">ПЕРИОД АУДИТА</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in sortedCompanies" :key="c.k"
              :style="{ borderLeft: `3px solid ${c.sector_color}` }">
            <td class="col-co">
              <div class="co-name">{{ c.n }}</div>
              <div class="co-sec">{{ sectorNames[c.s] || "—" }}</div>
            </td>
            <td class="col-num num">{{ fmtNum(getPlan(c)) }}</td>
            <td class="col-num num">{{ fmtNum(getFact(c)) }}</td>
            <td class="col-bar">
              <div class="bar-wrap">
                <div class="bar-bg">
                  <div class="bar-fill"
                       :style="{
                         width: `${Math.min(100, getPct(c) ?? 0)}%`,
                         background: pctColor(getPct(c)),
                       }"></div>
                </div>
                <div class="bar-pct" :style="{ color: pctColor(getPct(c)) }">
                  {{ getPct(c) != null ? `${getPct(c)}%` : "—" }}
                </div>
              </div>
            </td>
            <td class="col-status">
              <span class="badge"
                    :style="{ background: planBadge(c.plan).bg, color: planBadge(c.plan).fg }">
                {{ planBadge(c.plan).text }}
              </span>
            </td>
            <td class="col-status">
              <span class="badge"
                    :style="{ background: forensicBadge(c.forensic).bg, color: forensicBadge(c.forensic).fg }">
                {{ forensicBadge(c.forensic).text }}
              </span>
            </td>
            <td class="col-aud">
              <span class="aud-pill" :style="{ color: audColor(c.auditor) }">
                {{ cleanAud(c.auditor) }}
              </span>
            </td>
            <td class="col-years muted">{{ c.aYears || "—" }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.forensic-page { padding: 24px 32px; }

.page-header { margin-bottom: 24px; }
.page-eyebrow {
  font-size: 10px; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--t3); margin-bottom: 8px;
}
.page-title {
  font-size: 22px; font-weight: 500; letter-spacing: -0.01em;
  margin: 0 0 6px; color: var(--t1);
}
.page-sub { font-size: 13px; color: var(--t3); }

.filters-row {
  display: flex; flex-wrap: wrap; gap: 24px; margin-bottom: 24px;
  padding: 16px 20px; background: var(--bg2); border-radius: 12px;
}
.filter-group { display: flex; flex-direction: column; gap: 6px; }
.filter-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--t3);
}
.filter-select {
  padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border1);
  background: var(--bg1); color: var(--t1); font-size: 13px;
}
.filter-pills { display: flex; gap: 4px; }
.pill {
  padding: 4px 12px; font-size: 12px; font-weight: 500;
  border-radius: 11px; border: 1px solid var(--border1);
  background: var(--bg1); color: var(--t2); cursor: pointer;
  transition: all .15s;
}
.pill:hover { background: var(--bg3); }
.pill.active { background: #7F77DD; color: white; border-color: #7F77DD; }

.kpi-strip {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px;
}
.kpi-card {
  background: var(--bg1); padding: 16px 18px; border-radius: 12px;
  border: 1px solid var(--border1);
  border-left: 3px solid var(--kpi-accent);
  box-shadow: 0 4px 12px rgba(15,23,60,.04);
}
.kpi-label {
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--t3); margin-bottom: 8px;
}
.kpi-value {
  font-size: 22px; font-weight: 400; letter-spacing: -0.025em; color: var(--t1);
}
.kpi-of { font-size: 13px; color: var(--t3); margin-left: 4px; }

.state-msg {
  padding: 32px; text-align: center; color: var(--t3); font-size: 13px;
}
.state-msg.error { color: #993D3D; }

.table-card {
  background: var(--bg1); border-radius: 12px;
  border: 1px solid var(--border1); overflow: hidden;
  box-shadow: 0 4px 12px rgba(15,23,60,.04);
}
.data-table { width: 100%; border-collapse: collapse; }
.data-table thead {
  background: var(--bg2);
  border-bottom: 1px solid var(--border1);
}
.data-table th {
  padding: 10px 14px; text-align: left;
  font-size: 10px; font-weight: 500; letter-spacing: 0.06em;
  color: var(--t3); text-transform: uppercase; white-space: nowrap;
}
.data-table th.col-num,
.data-table td.col-num { text-align: right; }
.data-table tbody tr {
  border-bottom: 1px solid var(--border1);
  transition: background .12s;
}
.data-table tbody tr:hover { background: var(--bg2); }
.data-table tbody tr:last-child { border-bottom: none; }
.data-table td {
  padding: 12px 14px; font-size: 13px; color: var(--t1);
  vertical-align: middle;
}
.col-co { min-width: 180px; }
.col-num { min-width: 90px; }
.col-bar { min-width: 180px; }
.col-status { min-width: 130px; }
.col-aud { min-width: 90px; }
.col-years { min-width: 110px; }
.num { font-variant-numeric: tabular-nums; }
.co-name { font-weight: 500; }
.co-sec { font-size: 11px; color: var(--t3); margin-top: 2px; }
.bar-wrap { display: flex; align-items: center; gap: 10px; }
.bar-bg {
  flex: 1; height: 6px; background: var(--bg3); border-radius: 3px; overflow: hidden;
}
.bar-fill { height: 100%; transition: width .3s ease; }
.bar-pct { font-size: 12px; font-weight: 500; min-width: 44px; text-align: right; font-variant-numeric: tabular-nums; }
.badge {
  display: inline-block; font-size: 10px; font-weight: 600;
  padding: 3px 9px; border-radius: 4px; white-space: nowrap;
}
.aud-pill { font-size: 12px; font-weight: 500; }
.muted { color: var(--t3); font-size: 12px; }
</style>
