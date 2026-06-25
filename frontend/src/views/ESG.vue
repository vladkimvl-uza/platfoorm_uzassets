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
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import {
  esgApi,
  type AgencyRatingCell,
  type ESGCompanyScore,
  type ESGOverviewResponse,
} from "@/api/esg";
import ESGCompanyDetailModal from "@/components/ESG/ESGCompanyDetailModal.vue";
import RatingEditModal from "@/components/Ratings/RatingEditModal.vue";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";
import Odometer from "@/components/Odometer.vue";
import ESGMaturityMatrix from "@/components/ESG/ESGMaturityMatrix.vue";
import ESGFunnel from "@/components/ESG/ESGFunnel.vue";
import ESGMaturityProfileModal from "@/components/ESG/ESGMaturityProfileModal.vue";
import ESGDrillModal, { type ESGDrillRow } from "@/components/ESG/ESGDrillModal.vue";
import ESGSwotEditor from "@/components/ESG/ESGSwotEditor.vue";
import { usePermissions } from "@/composables/usePermissions";
import { useAuthStore } from "@/stores/auth";
import { watch } from "vue";
import type { ESGMaturityHeatmap, ESGMaturityCompany, ESGSwotResponse, ESGSwotItemBrief } from "@/api/esg";

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

// ─── ESG Maturity Cockpit (вкладка «Зрелость») ───────────────────
const esgPerm = usePermissions("esg");
const canEditMaturity = computed(() => esgPerm.canEdit.value);
type EsgTab = "overview" | "maturity" | "swot";
const activeTab = useSavedFilter<EsgTab>("esg.tab", "maturity");
// Вкладки «Обзор» и «Выводы» удалены из UI (остался единый вид «Зрелость»).
// Сбрасываем ЛЮБОЕ сохранённое не-maturity значение, иначе у юзеров со старым
// сохранённым "swot"/"overview" тело страницы рендерится пустым.
if (activeTab.value !== "maturity") activeTab.value = "maturity";
const heatmap = ref<ESGMaturityHeatmap | null>(null);
const matLoading = ref(false);
const matSearch = ref("");
const swot = ref<ESGSwotResponse | null>(null);
const swotLoading = ref(false);

async function loadMaturity() {
  matLoading.value = true;
  try {
    heatmap.value = await esgApi.getMaturityHeatmap(year.value ?? undefined);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Матрица зрелости: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    matLoading.value = false;
  }
}
async function loadSwot() {
  swotLoading.value = true;
  try {
    swot.value = await esgApi.getSwot();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Выводы: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    swotLoading.value = false;
  }
}
function setTab(t: EsgTab) {
  activeTab.value = t;
  if (t === "maturity" && !heatmap.value) loadMaturity();
  if (t === "swot" && !swot.value) loadSwot();
}
watch(year, () => { if (activeTab.value === "maturity") loadMaturity(); });

// группировка по-компанийных выводов: company_code → {name, strengths[], weaknesses[]}
const swotByCompany = computed(() => {
  const map = new Map<string, { name: string; strengths: ESGSwotItemBrief[]; weaknesses: ESGSwotItemBrief[] }>();
  for (const it of (swot.value?.company_items || [])) {
    const key = it.company_code || it.company_id || "—";
    let g = map.get(key);
    if (!g) { g = { name: it.company_name || it.company_code || "—", strengths: [], weaknesses: [] }; map.set(key, g); }
    (it.kind === "strength" ? g.strengths : g.weaknesses).push(it);
  }
  return Array.from(map.values());
});

const climateStages = computed(() => {
  const f = heatmap.value?.climate_funnel || [0, 0, 0, 0];
  return [
    { label: "Оценка выбросов ПГ (Охват 1–2)", count: f[0] || 0 },
    { label: "Оценка климат-рисков", count: f[1] || 0 },
    { label: "План декарбонизации", count: f[2] || 0 },
    { label: "Реализация", count: f[3] || 0 },
  ];
});
const riskStages = computed(() => {
  const f = heatmap.value?.risk_funnel || [0, 0, 0];
  return [
    { label: "Double-materiality", count: f[0] || 0 },
    { label: "Количественная оценка", count: f[1] || 0 },
    { label: "Интеграция в ERM (СУР)", count: f[2] || 0 },
  ];
});
function agencyAbbr(a: string): string {
  const s = (a || "").toLowerCase();
  if (s.includes("fitch")) return "Fitch";
  if (s.includes("s&p") || s.includes("standard")) return "S&P";
  if (s.includes("cdp")) return "CDP";
  if (s.includes("msci")) return "MSCI";
  if (s.includes("moody")) return "Moody’s";
  if (s.includes("sustainalytics")) return "Sustainalytics";
  if (s.includes("iss")) return "ISS";
  return a.length > 14 ? a.slice(0, 13) + "…" : a;
}
// Покрытие ПО АГЕНТСТВАМ: сколько компаний имеет рейтинг каждого агентства
// (+ «без рейтинга»). Не нуждается / D3 «не требуется» — исключаем.
const AG_PALETTE = ["#1D9E75", "#378ADD", "#7C6FF7", "#EF9F27", "#0EA5A5", "#E24B4A"];
const matDonut = computed<DonutEntry[]>(() => {
  const h = heatmap.value;
  if (!h) return [];
  const cos = h.companies.filter((c) => !c.not_needed && !(c.dim_not_required || []).includes("D3"));
  const total = cos.length || 1;
  const byAg = new Map<string, number>();
  let none = 0;
  for (const c of cos) {
    const ags = new Set((c.ratings || []).map((r) => r.agency).filter(Boolean));
    if (!ags.size) { none++; continue; }
    for (const ag of ags) byAg.set(ag, (byAg.get(ag) || 0) + 1);
  }
  const out: DonutEntry[] = [...byAg.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([ag, n], i) => ({ label: agencyAbbr(ag), color: AG_PALETTE[i % AG_PALETTE.length],
                            value: n, sub: `${n} из ${total}` }));
  if (none) out.push({ label: "Без рейтинга", color: "#E2E8F0", value: none, sub: `${none} из ${total}` });
  return out;
});

// «Требует внимания» — вычисляемые алерты из heatmap (без бэкенда)
interface MatAlert {
  key: string; label: string; description: string; count: number; color: string;
  companies: ESGMaturityCompany[];
}
const matAlerts = computed<MatAlert[]>(() => {
  const cs = (heatmap.value?.companies || []).filter((c) => !c.not_needed);
  const out: MatAlert[] = [];
  const push = (key: string, label: string, description: string, color: string,
                pred: (c: ESGMaturityCompany) => boolean) => {
    const list = cs.filter(pred);
    if (list.length) out.push({ key, label, description, color, count: list.length, companies: list });
  };
  const nr = (c: ESGMaturityCompany, d: string) => (c.dim_not_required || []).includes(d);
  push("rt", "без независимого рейтинга",
    "Нет ни одного независимого ESG-рейтинга (Sustainable Fitch / S&P ESG / CDP). Рекомендуется инициировать присвоение.",
    "#D97706", (c) => !nr(c, "D3") && (c.rating_count || 0) === 0);
  push("iso", "без стандартов ISO",
    "Нет ни одной системы менеджмента ISO (14001 / 45001 / 50001).",
    "#378ADD", (c) => !nr(c, "D1") && (c.dim_stage?.D1 ?? 0) === 0);
  push("rep", "без ESG-отчётности",
    "Нет ESG-отчётности (GRI/SASB → IFRS SDS).",
    "#D97706", (c) => !nr(c, "D2") && (c.dim_stage?.D2 ?? 0) === 0);
  return out;
});
const matProfile = ref<ESGMaturityCompany | null>(null);

// ─── Единый premium drill-down (KPI / алерты / воронки) ───────────
function emsColor(e: number): string { return e >= 70 ? "#1D9E75" : e >= 40 ? "#D97706" : "#E24B4A"; }
const CLIMATE_STAGE_LBL = ["нет", "Scope 1–2", "+ риски", "+ план", "реализация"];
const RISK_STAGE_LBL = ["нет", "double-mat.", "оценка", "ERM"];
const ISO_STAGE_LBL = ["нет", "в процессе", "1 серт.", "2 серт.", "3 серт."];
const REP_STAGE_LBL = ["нет", "разовый", "регулярный", "IFRS SDS", "+ assurance"];
// Кол-во компаний с ESG-отчётностью уровня IFRS SDS и выше (D2 ≥ 3).
const ifrsSdsCount = computed(() => (heatmap.value?.companies || []).filter((c) => !c.not_needed && !(c.dim_not_required || []).includes("D2") && (c.dim_stage?.D2 ?? 0) >= 3).length);

// Знаменатель «применимых» компаний по измерению: вне «не нуждается» И вне «не требуется» этого измерения.
function dimTotal(dim: string): number {
  return (heatmap.value?.companies || []).filter((c) => !c.not_needed && !(c.dim_not_required || []).includes(dim)).length;
}
const totalD1 = computed(() => dimTotal("D1"));
const totalD2 = computed(() => dimTotal("D2"));
const totalD3 = computed(() => dimTotal("D3"));
const totalD4 = computed(() => dimTotal("D4"));
const totalD5 = computed(() => dimTotal("D5"));
const coveragePct = computed(() => Math.round((heatmap.value?.rated_count ?? 0) / Math.max(1, totalD3.value) * 100));

function baseRow(c: ESGMaturityCompany): ESGDrillRow {
  return { id: c.company_id, name: c.company_name || c.company_code,
           sector: c.sector_name, color: c.sector_color || "#7C6FF7", value: "" };
}

const drill = ref<{ title: string; subtitle?: string; description?: string; accent?: string; rows: ESGDrillRow[] } | null>(null);

function openKpiDrill(kind: "ifrssds" | "coverage" | "baskets" | "iso") {
  const cs = [...(heatmap.value?.companies || [])].filter((c) => !c.not_needed);
  const nr = (c: ESGMaturityCompany, d: string) => (c.dim_not_required || []).includes(d);
  if (kind === "ifrssds") {
    const list = cs.filter((c) => !nr(c, "D2") && (c.dim_stage?.D2 ?? 0) >= 3).sort((a, b) => (b.dim_stage?.D2 ?? 0) - (a.dim_stage?.D2 ?? 0));
    drill.value = { title: "Компании с IFRS SDS", subtitle: "ESG-отчётность по IFRS S2 (D2 ≥ IFRS SDS)", accent: "#7C6FF7",
      rows: list.map((c) => ({ ...baseRow(c), value: REP_STAGE_LBL[c.dim_stage?.D2 ?? 0], valueColor: "#1D9E75" })) };
  } else if (kind === "coverage") {
    const list = cs.filter((c) => !nr(c, "D3")).sort((a, b) => (b.rating_count || 0) - (a.rating_count || 0));
    drill.value = { title: "Покрытие рейтингами", subtitle: "независимые ESG-рейтинги по компаниям", accent: "#1D9E75",
      rows: list.map((c) => ({ ...baseRow(c),
        value: (c.rating_count || 0) > 0 ? `${c.rating_count} рейт.` : "нет",
        valueColor: (c.rating_count || 0) > 0 ? "#1D9E75" : "#E24B4A" })) };
  } else if (kind === "baskets") {
    cs.sort((a, b) => b.ems - a.ems);
    const basket = (e: number) => e >= 70 ? { t: "зрелая", c: "#1D9E75" } : e >= 40 ? { t: "развив.", c: "#D97706" } : { t: "начальн.", c: "#E24B4A" };
    drill.value = { title: "Корзины зрелости", subtitle: "зрелые ≥70 · развив. 40–69 · начальные <40", accent: "#378ADD",
      rows: cs.map((c) => { const b = basket(c.ems); return { ...baseRow(c), value: Math.round(c.ems), valueColor: emsColor(c.ems), badge: b.t, badgeColor: b.c }; }) };
  } else {
    const list = cs.filter((c) => !nr(c, "D1")).sort((a, b) => (b.dim_stage?.D1 ?? 0) - (a.dim_stage?.D1 ?? 0));
    drill.value = { title: "ISO-системы", subtitle: "системы менеджмента ISO (D1)", accent: "#EF9F27",
      rows: list.map((c) => { const s = c.dim_stage?.D1 ?? 0; return { ...baseRow(c), value: ISO_STAGE_LBL[s], valueColor: s >= 3 ? "#1D9E75" : s >= 1 ? "#D97706" : "#94A3B8" }; }) };
  }
}

function openAlertDrill(a: MatAlert) {
  drill.value = { title: a.label.charAt(0).toUpperCase() + a.label.slice(1), subtitle: `${a.count} компаний · требует внимания`,
    description: a.description, accent: a.color,
    rows: a.companies.map((c) => ({ ...baseRow(c), value: Math.round(c.ems), valueColor: emsColor(c.ems) })) };
}

function openFunnelDrill(scheme: "climate" | "risk", stageIdx: number) {
  const cs = (heatmap.value?.companies || []).filter((c) => !c.not_needed);
  const dim = scheme === "climate" ? "D4" : "D5";
  const need = stageIdx + 1;
  const list = cs.filter((c) => !(c.dim_not_required || []).includes(dim) && (c.dim_stage?.[dim] ?? 0) >= need);
  const labels = scheme === "climate" ? climateStages.value : riskStages.value;
  const max = scheme === "climate" ? 4 : 3;
  const stageLbl = scheme === "climate" ? CLIMATE_STAGE_LBL : RISK_STAGE_LBL;
  drill.value = {
    title: labels[stageIdx]?.label || "Стадия",
    subtitle: `${scheme === "climate" ? "Климат" : "ESG-риски"} · достигли стадии ≥ ${need}`,
    accent: scheme === "climate" ? "#1D9E75" : "#6C5CE7",
    rows: list.map((c) => { const s = c.dim_stage?.[dim] ?? 0; return { ...baseRow(c), value: `${s}/${max}`, valueColor: "#1E2A4A", badge: stageLbl[s], badgeColor: scheme === "climate" ? "#1D9E75" : "#6C5CE7" }; }),
  };
}

function onDrillOpenCompany(id: string) {
  drill.value = null;
  openMatProfile(id);
}
function openMatProfile(id: string) {
  matProfile.value = (heatmap.value?.companies || []).find((c) => c.company_id === id) || null;
}

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
// Компания, чей профиль надо переоткрыть после закрытия редактора рейтинга.
const ratingReopenId = ref<string | null>(null);

function reopenProfile() {
  const id = ratingReopenId.value;
  ratingReopenId.value = null;
  if (id && heatmap.value) {
    const found = (heatmap.value.companies || []).find((c) => c.company_id === id);
    if (found) matProfile.value = found;
  }
}

async function onRatingSaved() {
  ratingEdit.value = null;
  // Единый источник: рейтинг изменился → обновляем обзор И матрицу зрелости (D3/EMS),
  // затем переоткрываем профиль из свежих данных (перерисует Radar + список рейтингов).
  await load();
  if (heatmap.value) await loadMaturity();
  reopenProfile();
}

// Закрытие редактора без сохранения — просто вернуть профиль.
function onRatingEditClose() {
  ratingEdit.value = null;
  reopenProfile();
}

// ───────────────────────────────────────────────────────────────
//   Score helpers — ESG = баллы (0–10), без кредитных букв
// ───────────────────────────────────────────────────────────────

function esgScoreColor(s: number | null | undefined): string {
  if (s == null) return "#94A3B8";
  if (s >= 7)   return "#1D9E75";
  if (s >= 5)   return "#EF9F27";
  return "#E24B4A";
}
// Балл агентства (как он есть: Sustainable Fitch 61, S&P 72, CDP B), а не
// нормализованный композит. Берём основной (первый) рейтинг компании.
function esgPrimaryCell(r: ESGCompanyScore): AgencyRatingCell | null {
  return (r.ratings_by_agency || []).filter(c => c.score || c.rating)[0] || null;
}
function esgRatingValue(c: AgencyRatingCell | null): string {
  return c ? String(c.score || c.rating || "—") : "—";
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
// Балл лидера «как есть» (агентский), а не композит — для KPI-карточки «Лидер».
const leaderNativeScore = computed<string | null>(() => {
  const name = k.value?.leader_company_name;
  if (!name) return null;
  const co = (overview.value?.rankings || []).find(r => (r.company_name || r.company_code) === name);
  const c0 = co ? esgPrimaryCell(co) : null;
  return c0 ? esgRatingValue(c0) : null;
});
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
//   Donut (agency coverage) — CreditDonut entries
// ───────────────────────────────────────────────────────────────

const donutEntries = computed<DonutEntry[]>(() => {
  const total = k.value?.total_companies ?? 0;
  const entries: DonutEntry[] = agencyCoverage.value.map(ag => ({
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

function donutHoverFmt(e: DonutEntry): [string, string] {
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
      return sorted.map(r => {
        // Показываем балл агентства как он есть, не композит-«рейтинг».
        const c0 = esgPrimaryCell(r);
        const n = (r.ratings_by_agency || []).filter(c => c.score || c.rating).length;
        return {
          r,
          primary: esgRatingValue(c0),
          primaryColor: esgScoreColor(r.composite_esg_score),
          secondary: c0 ? `${c0.agency}${n > 1 ? ` +${n - 1}` : ""}` : "нет рейтингов",
        };
      });
    }
    case "leader": {
      const sorted = [...rows]
        .filter(r => r.composite_esg_score != null)
        .sort((a, b) => (b.composite_esg_score ?? 0) - (a.composite_esg_score ?? 0))
        .slice(0, 10);
      return sorted.map(r => {
        const c0 = esgPrimaryCell(r);
        return {
          r,
          primary: esgRatingValue(c0),
          primaryColor: esgScoreColor(r.composite_esg_score),
          secondary: c0 ? c0.agency : "—",
        };
      });
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

// Ссылки на отчёты агентств (report_url уже есть в данных рейтингов).
const AGENCY_SHORT: Record<string, string> = {
  "Sustainable Fitch": "SF",
  "S&P ESG": "S&P",
  "CDP": "CDP",
};
function reportLinks(r: ESGCompanyScore): AgencyRatingCell[] {
  return (r.ratings_by_agency || []).filter(c => !!c.report_url);
}
function agencyShort(a: string): string {
  return AGENCY_SHORT[a] || a;
}

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

onMounted(() => { load(); loadMaturity(); loadSwot(); });
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
        </div>

        <!-- ═══ Вкладка «Зрелость» — ESG Maturity Cockpit ═══ -->
        <div v-if="activeTab === 'maturity'" class="ev-body">
          <UzaStateBlock v-if="matLoading && !heatmap" state="loading" loadingText="Загрузка матрицы зрелости..." />
          <template v-else-if="heatmap">
            <!-- EMS KPI-rail -->
            <div class="ev-kpi-strip ev-mat-kpis kpi-rail">
              <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#7C6FF7; --kpi2-d:0ms" @click="openKpiDrill('ifrssds')">
                <div class="kpi2-lbl">Компании с IFRS SDS</div>
                <div class="kpi2-val"><Odometer :value="ifrsSdsCount" /><span class="ev-kpi-unit"> / {{ totalD2 }}</span></div>
                <div class="kpi2-sub">ESG-отчётность по IFRS S2</div>
              </div>
              <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#1D9E75; --kpi2-d:80ms" @click="openKpiDrill('coverage')">
                <div class="kpi2-lbl">Покрытие рейтингами</div>
                <div class="kpi2-val"><Odometer :value="heatmap.rated_count" /><span class="ev-kpi-unit"> / {{ totalD3 }}</span></div>
                <div class="kpi2-sub">{{ coveragePct }}% портфеля</div>
              </div>
              <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#378ADD; --kpi2-d:160ms" @click="openKpiDrill('baskets')">
                <div class="kpi2-lbl">Корзины зрелости</div>
                <div class="kpi2-val ev-baskets">
                  <span style="color:#1D9E75">{{ heatmap.baskets.mature }}</span><span class="ev-bsep">/</span><span style="color:#D97706">{{ heatmap.baskets.developing }}</span><span class="ev-bsep">/</span><span style="color:#E24B4A">{{ heatmap.baskets.starting }}</span>
                </div>
                <div class="kpi2-sub">зрелые · развив. · начин.</div>
              </div>
              <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#EF9F27; --kpi2-d:240ms" @click="openKpiDrill('iso')">
                <div class="kpi2-lbl">ISO-системы</div>
                <div class="kpi2-val"><Odometer :value="heatmap.iso_full_count" /><span class="ev-kpi-unit"> / {{ totalD1 }}</span></div>
                <div class="kpi2-sub">все три стандарта</div>
              </div>
            </div>

            <!-- Лента «Требует внимания» (вычисляется из матрицы) -->
            <div v-if="matAlerts.length" class="ev-alerts">
              <span class="ev-alerts-h">Требует внимания</span>
              <div v-for="a in matAlerts" :key="a.key" class="ev-alert">
                <button type="button" class="ev-alert-chip" :style="{ '--ac': a.color }"
                        :title="`Показать ${a.count} компаний`" @click="openAlertDrill(a)">
                  <span class="ev-alert-cnt" :style="{ background: a.color }">{{ a.count }}</span>{{ a.label }}
                </button>
              </div>
            </div>

            <!-- Воронки климата/рисков + покрытие -->
            <div class="ev-fn-row">
              <ESGFunnel title="Климатические стратегии" hint="Охват 1–2 → риски → план → реализация"
                         :stages="climateStages" :total="totalD4" scheme="climate"
                         @stage-click="(i) => openFunnelDrill('climate', i)" />
              <ESGFunnel title="Управление ESG-рисками" hint="double-materiality → оценка → ERM"
                         :stages="riskStages" :total="totalD5" scheme="risk"
                         @stage-click="(i) => openFunnelDrill('risk', i)" />
              <div class="ev-fn-donut">
                <div class="fn-don-h">Покрытие по агентствам</div>
                <CreditDonut :entries="matDonut" :center-value="coveragePct + '%'" center-label="покрытие" :size="128" />
              </div>
            </div>

            <div class="ev-mat-tools">
              <div class="ev-search">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>
                <input v-model="matSearch" type="text" placeholder="Поиск компании…" />
              </div>
              <div class="ev-legend">
                <span class="ev-lg"><i class="ev-lg-c" style="background:#DCFCE7;color:#1D9E75">✓</i>есть</span>
                <span class="ev-lg"><i class="ev-lg-c" style="background:#FEF9C3;color:#D97706">◐</i>в процессе</span>
                <span class="ev-lg"><i class="ev-lg-c" style="background:#F1F5F9;color:#94A3B8">—</i>нет</span>
                <span class="ev-lg ev-lg-edit" v-if="canEditMaturity">клик по ячейке → подтвердите ✓ (защита от случайной правки)</span>
              </div>
            </div>

            <ESGMaturityMatrix :heatmap="heatmap" :can-edit="canEditMaturity" :search="matSearch"
                               @saved="loadMaturity" @open-company="openMatProfile" />

            <!-- Выводы: портфель + редактируемая таблица по компаниям (перенесено вниз) -->
            <ESGSwotEditor :swot="swot" :companies="heatmap.companies" :can-edit="canEditMaturity" :year="heatmap.year" @saved="loadSwot" />
          </template>
        </div>

        <UzaStateBlock v-if="activeTab === 'overview' && loading && !overview" state="loading" loadingText="Загрузка..." />
        <UzaStateBlock v-else-if="activeTab === 'overview' && error && !overview" state="error" variant="block" :text="error" />

        <div v-else-if="activeTab === 'overview' && overview && k" class="ev-body">

          <!-- ═══ 1. KPI strip (4 cells, clickable) ═══ -->
          <div class="ev-kpi-strip kpi-rail">

            <div class="kpi2 fin-shimmer ev-kpi" style="--kpi2-accent:#1D9E75; --kpi2-d:0ms" @click="kpiDrill = 'coverage'">
              <div class="ev-kpi-icn ok">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9 12l2 2 4-4"/></svg>
              </div>
              <div class="kpi2-lbl">Покрытие</div>
              <div class="kpi2-val">
                <span :data-countup="k.covered_count"><Odometer :value="k.covered_count" /></span>
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
                  {{ k.leader_ratings_count }} рейтинга<template v-if="leaderNativeScore"> · <b>{{ leaderNativeScore }} балл</b></template>
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
                <span :data-countup="k.unrated_count"><Odometer :value="k.unrated_count" /></span>
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
                <span :data-countup="k.recent_updates_count"><Odometer :value="k.recent_updates_count" /></span>
              </div>
              <div class="kpi2-sub">за <b>текущий и прошлый год</b></div>
            </div>
          </div>

          <!-- ═══ 2. Покрытие портфеля (донат, по агентствам) ═══ -->
          <div class="ev-mid-grid ev-cover-only">

            <!-- Donut Coverage (per agency) — единый CreditDonut -->
            <div class="ev-panel ev-donut-panel" style="--d:300ms">
              <div class="ev-panel-h">
                <h3>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>
                  Покрытие портфеля
                </h3>
                <span class="ev-panel-meta">по агентствам</span>
              </div>
              <div class="ev-panel-body ev-donut-body">
                <CreditDonut
                  :entries="donutEntries"
                  :center-value="`${k.coverage_pct}%`"
                  center-label="покрытие"
                  :size="160"
                  :hover-fmt="donutHoverFmt"
                />
              </div>
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
                      <td class="ev-modal-rep">
                        <a v-for="c in reportLinks(row.r)" :key="c.agency"
                           :href="c.report_url!" target="_blank" rel="noopener"
                           class="ev-rep-link" :title="'Отчёт · ' + c.agency" @click.stop>
                          {{ agencyShort(c.agency) }}<span class="ev-rep-arr">↗</span>
                        </a>
                      </td>
                    </tr>
                    <tr v-if="!kpiDrillRows.length">
                      <td colspan="4" class="empty">Нет данных</td>
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
          @close="onRatingEditClose"
          @saved="onRatingSaved"
        />

        <!-- Профиль ESG-зрелости компании (клик по компании в матрице) -->
        <ESGMaturityProfileModal :company="matProfile" :can-edit="canEditMaturity"
                                 @close="matProfile = null" />

        <!-- Единый drill-down: KPI-карточки / алерты / ступени воронок -->
        <ESGDrillModal v-if="drill" :open="!!drill" :title="drill.title" :subtitle="drill.subtitle"
                       :description="drill.description" :accent="drill.accent" :rows="drill.rows"
                       @close="drill = null" @open-company="onDrillOpenCompany" />
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
.ev-tb-l { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
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

.ev-body { padding: 16px 20px 24px; }

/* ─── Вкладки + матрица зрелости ─── */
.ev-tabs { align-self: center; }
.ev-mat-kpis { margin-bottom: 16px; }
/* KPI-карточки в один ряд (специфичность выше базового .ev-kpi-strip) */
.ev-kpi-strip.ev-mat-kpis { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 1280px) { .ev-kpi-strip.ev-mat-kpis { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 760px)  { .ev-kpi-strip.ev-mat-kpis { grid-template-columns: repeat(2, 1fr); } }
.ev-kpi-unit { font-size: 14px; font-weight: 400; color: var(--t3, #94A3B8); letter-spacing: 0; }
.ev-baskets { display: inline-flex; align-items: baseline; gap: 2px; font-feature-settings: 'tnum'; }
.ev-bsep { color: #CBD2E0; font-weight: 300; margin: 0 1px; }
.ev-mat-tools { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-bottom: 10px; flex-wrap: wrap; }
.ev-search { display: inline-flex; align-items: center; gap: 7px; padding: 6px 12px; background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.1); border-radius: 9px; color: var(--t3, #94A3B8); min-width: 240px; }
.ev-search:focus-within { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 2px rgba(124,111,247,.15); }
.ev-search input { border: none; outline: none; background: transparent; font-family: inherit; font-size: 12.5px; color: var(--t1, #1E2A4A); width: 100%; }
.ev-legend { display: inline-flex; align-items: center; gap: 12px; font-size: 11px; color: var(--t3, var(--t-muted)); flex-wrap: wrap; }
.ev-lg { display: inline-flex; align-items: center; gap: 5px; }
.ev-lg-c { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 5px; font-size: 11px; font-weight: 700; }
.ev-lg-edit { font-style: italic; color: var(--p-deep, #5B53B8); }
/* Адаптив матрицы-вкладки: малые экраны (<14") → инструменты в колонку */
@media (max-width: 900px) {
  .ev-mat-tools { gap: 8px; align-items: stretch; }
  .ev-search { min-width: 100%; }
}
/* Большие дисплеи (60–75", 4K) — KPI и инструменты крупнее */
@media (min-width: 2200px) {
  .ev-mat-kpis .kpi2-val { font-size: clamp(40px, 2.6vw, 72px); }
  .ev-mat-kpis .kpi2-lbl { font-size: 13px; }
  .ev-mat-kpis .kpi2-sub { font-size: 14px; }
  .ev-kpi-unit { font-size: 22px; }
  .ev-search { min-width: 380px; font-size: 16px; padding: 9px 16px; }
  .ev-legend { font-size: 14px; gap: 18px; }
  .ev-lg-c { width: 24px; height: 24px; font-size: 14px; }
}

/* Лента «Требует внимания» */
.ev-alerts { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.ev-alerts-h { display: inline-flex; align-items: center; gap: 6px; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #C2410C; }
.ev-alert { position: relative; }
.ev-alert-chip { display: inline-flex; align-items: center; gap: 7px; padding: 5px 11px 5px 5px; border-radius: 999px; border: 1px solid color-mix(in srgb, var(--ac) 30%, transparent); background: color-mix(in srgb, var(--ac) 8%, #fff); color: var(--t2, #475569); font-size: 11.5px; font-weight: 500; font-family: inherit; cursor: pointer; transition: transform .12s, box-shadow .12s; }
.ev-alert-chip:hover { transform: translateY(-1px); box-shadow: 0 3px 10px color-mix(in srgb, var(--ac) 22%, transparent); }
.ev-alert-cnt { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; padding: 0 5px; border-radius: 999px; color: #fff; font-size: 11px; font-weight: 700; font-feature-settings: 'tnum'; }
.ev-alert-pop { position: absolute; top: calc(100% + 6px); left: 0; z-index: 20; min-width: 200px; max-width: 320px; max-height: 240px; overflow-y: auto; padding: 8px; background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.1); border-radius: 10px; box-shadow: 0 12px 32px rgba(15,23,60,.16); display: flex; flex-direction: column; gap: 2px; animation: fadeSlideIn .15s ease; }
.ev-alert-n { font-size: 11.5px; color: var(--t1, #1E2A4A); padding: 4px 8px; border-radius: 6px; }
.ev-alert-n:hover { background: var(--bg2, #F4F3F9); }
@media (min-width: 2200px) { .ev-alerts-h { font-size: 13px; } .ev-alert-chip { font-size: 14px; } .ev-alert-cnt { min-width: 24px; height: 24px; font-size: 13px; } }

/* Воронки климата/рисков + донат покрытия */
.ev-fn-row { display: grid; grid-template-columns: 1fr 1fr 280px; gap: 14px; margin-bottom: 16px; }
.ev-fn-donut { background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.06); border-radius: 14px; padding: 14px 16px; display: flex; flex-direction: column; }
.fn-don-h { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--t1, #1E2A4A); margin-bottom: 10px; }
@media (max-width: 1200px) { .ev-fn-row { grid-template-columns: 1fr 1fr; } .ev-fn-donut { grid-column: 1 / 3; } }
@media (max-width: 760px) { .ev-fn-row { grid-template-columns: 1fr; } .ev-fn-donut { grid-column: auto; } }
@media (min-width: 2200px) { .ev-fn-row { grid-template-columns: 1fr 1fr 360px; gap: 20px; } .fn-don-h { font-size: 15px; } }

/* ─── Вкладка «Выводы» (SWOT) — Apple-style: воздух, ясность, спокойствие ─── */
.ev-swot { max-width: 1320px; }
.sw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.sw-col { display: flex; flex-direction: column; gap: 12px; }
.sw-col-h { display: flex; align-items: center; gap: 9px; font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; padding: 2px 2px 4px; }
.sw-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.sw-dot-pos { background: #1D9E75; box-shadow: 0 0 0 4px rgba(29,158,117,.12); }
.sw-dot-neg { background: #EF9F27; box-shadow: 0 0 0 4px rgba(239,159,39,.12); }
.sw-count { margin-left: auto; font-size: 11px; font-weight: 700; color: var(--t3, #94A3B8); background: var(--bg2, #F4F3F9); border-radius: 999px; padding: 1px 9px; }
.sw-card { position: relative; display: flex; gap: 13px; padding: 16px 17px; background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05); border-radius: 14px; box-shadow: 0 1px 2px rgba(16,24,64,.03); animation: swIn .5s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) var(--d, 0ms) backwards; transition: box-shadow .18s, transform .18s; }
.sw-card::before { content: ''; position: absolute; top: 0; left: 17px; right: 17px; height: 2px; border-radius: 0 0 2px 2px; }
.sw-pos::before { background: linear-gradient(90deg, #1D9E75, rgba(29,158,117,.18)); }
.sw-neg::before { background: linear-gradient(90deg, #EF9F27, rgba(239,159,39,.18)); }
.sw-card:hover { box-shadow: 0 6px 22px rgba(16,24,64,.07); transform: translateY(-1px); }
@keyframes swIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: translateY(0); } }
.sw-marker { flex-shrink: 0; width: 24px; height: 24px; border-radius: 8px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; }
.sw-marker-pos { background: #DCFCE7; color: #1D9E75; }
.sw-marker-neg { background: #FEF3D9; color: #C2410C; }
.sw-body { margin: 2px 0 0; font-size: 12.5px; line-height: 1.55; color: var(--t2, #3a4256); }

.sw-companies { margin-top: 32px; }
.sw-sec-h { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: var(--p-deep, #5B53B8); margin-bottom: 14px; }
.sw-co-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(430px, 1fr)); gap: 16px; }
.sw-co-card { background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05); border-radius: 16px; padding: 17px 19px; box-shadow: 0 1px 2px rgba(16,24,64,.03); }
.sw-co-name { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); margin-bottom: 13px; letter-spacing: -0.01em; }
.sw-co-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.sw-co-side-h { display: flex; align-items: center; gap: 6px; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; color: var(--t3, #94A3B8); margin-bottom: 9px; }
.sw-co-item { position: relative; margin: 0 0 9px; padding-left: 14px; font-size: 11.5px; line-height: 1.5; color: var(--t2, #3a4256); }
.sw-co-item::before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; border-radius: 50%; }
.sw-pos-item::before { background: #1D9E75; }
.sw-neg-item::before { background: #EF9F27; }
.sw-co-empty { color: #CBD2E0; font-size: 12px; padding-left: 14px; margin: 0; }

@media (max-width: 900px) { .sw-grid { grid-template-columns: 1fr; } .sw-co-cols { grid-template-columns: 1fr; gap: 14px; } .sw-co-grid { grid-template-columns: 1fr; } }
@media (min-width: 2200px) {
  .ev-swot { max-width: 1840px; }
  .sw-col-h { font-size: 16px; } .sw-body { font-size: 15px; } .sw-marker { width: 30px; height: 30px; font-size: 15px; }
  .sw-co-name { font-size: 17px; } .sw-co-item { font-size: 14px; } .sw-co-side-h { font-size: 13px; }
}

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
/* Когда оставлен только донат покрытия — компактная одиночная карточка. */
.ev-cover-only { grid-template-columns: minmax(0, 360px); }
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

/* Donut — uses CreditDonut (единый Chart.js doughnut, cutout 84%) */
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
.ev-modal-rep { text-align: right; white-space: nowrap; min-width: 96px; }
.ev-rep-link {
  display: inline-flex; align-items: center; gap: 1px;
  margin-left: 5px; padding: 2px 7px; border-radius: 6px;
  background: rgba(127, 119, 221, .10); color: var(--p-deep, #534AB7);
  font-size: 10.5px; font-weight: 600; text-decoration: none;
  transition: background .14s;
}
.ev-rep-link:hover { background: rgba(127, 119, 221, .2); }
.ev-rep-arr { font-size: 9px; opacity: .8; }
.ev-mat-sec { display: inline-block; width: 3px; height: 14px; border-radius: 2px; }

.ev-modal-enter-active, .ev-modal-leave-active { transition: opacity .2s, transform .2s; }
.ev-modal-enter-from, .ev-modal-leave-to { opacity: 0; transform: scale(.96); }

@media (max-width: 480px) {
  .ev-rank-tbl { font-size: 10.5px; }
  .ev-rank-tbl th, .ev-rank-tbl td { padding: 5px 6px; }
  .ev-modal-tbl td, .ev-modal-tbl th { padding: 5px 8px; }
}
</style>
