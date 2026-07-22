<script setup lang="ts">
/**
 * Закупки и Форензик аудит — 1:1 port of legacy `showProcurementView`
 * (index.html:19854). Backend `/forensic/overview` already returns
 * legacy-shape rows (PROCUREMENT_DATA), no schema changes needed.
 *
 * Layout:
 *   • Dark navy topbar: title + year badge + period segmented + edit menu (▤)
 *   • 3 KPI cards row (3fr : 1fr : 1fr):
 *       — Composite: План трлн | Факт трлн | Исполнение %
 *       — Планы утверждены  N / total
 *       — Аудит завершён    N / total
 *   • Chart card: «Исполнение плана закупок, {period}» + sector segmented +
 *       Chart.js bar chart (Plan ghost + Fact filled) + legend
 *   • 2-col grid:
 *       — «План закупок» table + plan-status filter
 *       — «Форензик аудит» table + auditor breakdown (KPMG/PwC/Deloitte/E&Y)
 *           + status filter
 */
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from "vue";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { api } from "@/api/client";
import { useCountUpScan } from "@/composables/useCountUp";
import { downloadForensicTemplate } from "@/utils/forensicTemplate";
import ForensicUploadModal from "@/components/Procurement/ForensicUploadModal.vue";
import ForensicEditModal from "@/components/Procurement/ForensicEditModal.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import BadgeConsultant from "@/components/BadgeConsultant.vue";
import { useFormatters } from "@/composables/useFormatters";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
// M-6: единый канон цвета/зоны исполнения (тот же порог, что был локально в
// таблице; редактор ForensicEditModal импортирует тот же helper — конец расхождения).
import { execCol as pctCol, execZone as pctZone } from "@/utils/execBand";

const fmt = useFormatters();
const toast = useToast();
const { confirmDialog } = useConfirm();

// ─── Types ───────────────────────────────────────────────────────
interface YearRow {
  y: number;
  plan?: number | null;
  fact?: number | null;
  n9p?: number | null;
  n9f?: number | null;
  q1p?: number | null; q1f?: number | null;
  q2p?: number | null; q2f?: number | null;
  q3p?: number | null; q3f?: number | null;
  q4p?: number | null; q4f?: number | null;
}

interface ProcCompany {
  n: string;            // display name
  k: string;            // code (lowercase)
  s: string;            // sector
  sector_color: string;

  // Legacy fallback fields (2024/2025/2026)
  yP24?: number | null; yF24?: number | null;
  nP24?: number | null; nF24?: number | null;
  yP25?: number | null; yF25?: number | null;
  nP25?: number | null; nF25?: number | null;
  q1P25?: number | null; q1F25?: number | null;
  q2P25?: number | null; q2F25?: number | null;
  q3P25?: number | null; q3F25?: number | null;
  q4P25?: number | null; q4F25?: number | null;
  yP26?: number | null;

  plan?: string | number | null;   // строковый статус ИЛИ (7 флагманов) числовая сумма плана
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

type Period = "year" | "9m" | "q1" | "q2" | "q3" | "q4";

// ─── State ───────────────────────────────────────────────────────
const companies = ref<ProcCompany[]>([]);
const kpis = ref<Kpis>({ total_companies: 0, plan_approved: 0, forensic_done: 0, with_auditor: 0 });
const loading = ref(true);
const errorMsg = ref<string | null>(null);

// Filters (legacy _proc* state)
const sectorFilter = ref<string>("");                  // '' | mining | oilgas | energy | transport | other
const yearFilter = ref<number>(new Date().getFullYear());  // по умолчанию текущий год
const periodFilter = ref<Period>("9m");
const planFilter = ref<"" | "Утверждён" | "Не утверждён">("");
const forFilter = ref<"" | "Завершён" | "В процессе" | "Тендер" | "Не начат">("");
const audFilter = ref<"" | "KPMG" | "PwC" | "Deloitte" | "E&Y">("");
const editMenuOpen = ref(false);

const SECTOR_LABELS_RU: Record<string, string> = {
  "": "Все секторы",
  mining: "Горнодобывающий",
  oilgas: "Нефтегазовый",
  energy: "Энергетика",
  transport: "Транспорт",
  other: "Прочие",
};
// Цвета аудиторов 1:1 с /consultants (seed consultants.json): KPMG #0033A0,
// PwC #0066CC, EY #008A00, Deloitte #222222 — единый бренд-палитр по всей платформе.
const AUDITOR_COLORS: Record<string, string> = {
  KPMG: "#0033A0", PwC: "#0066CC", Deloitte: "#222222", "E&Y": "#008A00",
};

// ─── Period/Year accessors (1:1 legacy gP, gF, gPct, _getYr) ───
function _getYr(c: ProcCompany, year: number): YearRow | null {
  if (Array.isArray(c.years)) {
    return c.years.find(y => y.y === year) || null;
  }
  return null;
}

/** Period→years[] field map. Used to pull the exact stored value first. */
const _PLAN_FIELD: Record<Period, keyof YearRow> = {
  year: "plan", "9m": "n9p", q1: "q1p", q2: "q2p", q3: "q3p", q4: "q4p",
};
const _FACT_FIELD: Record<Period, keyof YearRow> = {
  year: "fact", "9m": "n9f", q1: "q1f", q2: "q2f", q3: "q3f", q4: "q4f",
};

/** Period-scale factor: how much of the annual figure a period represents
 *  when only the annual number is known and we need to derive a finer split. */
const _PER_FRACTION: Record<Period, number> = {
  year: 1, "9m": 0.75, q1: 0.25, q2: 0.25, q3: 0.25, q4: 0.25,
};

// Возвращает план И признак «оценка» — значение синтезировано из годового × долю
// периода (квартальный/9-мес план НЕ заведён). M-4: такую оценку нельзя показывать
// как заведённый квартальный план (руководство приняло бы прикидку за факт-план).
function _plan(c: ProcCompany): { v: number | null; est: boolean } {
  const yr = yearFilter.value, per = periodFilter.value;
  const yObj = _getYr(c, yr);
  // 1) Точное сохранённое значение периода из years[]
  if (yObj) {
    const v = yObj[_PLAN_FIELD[per]] as number | null | undefined;
    if (v != null) return { v, est: false };
  }
  // 2) Legacy per-year поля (старые снапшоты) — тоже точные
  if (yr === 2024) {
    if (per === "year" && c.yP24 != null) return { v: c.yP24, est: false };
    if (per === "9m"   && c.nP24 != null) return { v: c.nP24, est: false };
  } else if (yr === 2025) {
    if (per === "year" && c.yP25 != null) return { v: c.yP25, est: false };
    if (per === "9m"   && c.nP25 != null) return { v: c.nP25, est: false };
    if (per === "q1"   && c.q1P25 != null) return { v: c.q1P25, est: false };
    if (per === "q2"   && c.q2P25 != null) return { v: c.q2P25, est: false };
    if (per === "q3"   && c.q3P25 != null) return { v: c.q3P25, est: false };
    if (per === "q4"   && c.q4P25 != null) return { v: c.q4P25, est: false };
  } else if (yr === 2026) {
    if (per === "year" && c.yP26 != null) return { v: c.yP26, est: false };
  }
  // 3) Оценка: годовой × доля периода (квартальной/9-мес разбивки нет).
  const annual = (yObj?.plan as number | null | undefined) ??
                 (yr === 2024 ? c.yP24 : yr === 2025 ? c.yP25 : yr === 2026 ? c.yP26 : null);
  if (annual != null && per !== "year") {
    return { v: Math.round(annual * _PER_FRACTION[per]), est: true };
  }
  return { v: null, est: false };
}
function gP(c: ProcCompany): number | null {
  return _plan(c).v;
}
// M-4: true, когда план — синтетическая оценка (год ÷ период), не заведённый квартальный.
function gPisEstimate(c: ProcCompany): boolean {
  return _plan(c).est;
}

function gF(c: ProcCompany): number | null {
  const yr = yearFilter.value, per = periodFilter.value;
  const yObj = _getYr(c, yr);
  // 1) Exact stored value
  if (yObj) {
    const v = yObj[_FACT_FIELD[per]] as number | null | undefined;
    if (v != null) return v;
  }
  // 2) Legacy fact fields
  if (yr === 2024) {
    if (per === "year" && c.yF24 != null) return c.yF24;
    if (per === "9m"   && c.nF24 != null) return c.nF24;
  } else if (yr === 2025) {
    if (per === "year" && c.yF25 != null) return c.yF25;
    if (per === "9m"   && c.nF25 != null) return c.nF25;
    if (per === "q1"   && c.q1F25 != null) return c.q1F25;
    if (per === "q2"   && c.q2F25 != null) return c.q2F25;
    if (per === "q3"   && c.q3F25 != null) return c.q3F25;
    if (per === "q4"   && c.q4F25 != null) return c.q4F25;
  }
  // 3) DON'T auto-derive fact from annual — fact only counts when actually
  //    recorded. Returning null lets hasFact reflect reality.
  return null;
}

function gPct(c: ProcCompany): number | null {
  const p = gP(c), f = gF(c);
  // H-4: факт=0 при плане>0 → 0% (провал, красным), а не «—» (нет данных).
  // null только когда плана нет / факта нет / план=0 (деление на ноль).
  if (p == null || f == null || p === 0) return null;
  return Math.round(f / p * 1000) / 10;
}
// H-4: состояние ячейки исполнения — различаем «нет плана» / «план есть, факта нет» / «%».
function gPctState(c: ProcCompany): "pct" | "nofact" | "noplan" {
  const p = gP(c), f = gF(c);
  if (p == null || p === 0) return "noplan";
  if (f == null) return "nofact";
  return "pct";
}


// H-1/H-2/H-3: честные признаки (зеркалят бэкенд forensic/service.py) — единый
// источник для карточек и топбара (раньше карта считала строгий === «Утверждён»,
// топбар — backend .startswith → два разных числа «Планы утверждены» на экране).
function _isNum(v: unknown): boolean {
  if (v == null || v === "") return false;
  return Number.isFinite(Number(String(v).replace(/\s/g, "").replace(",", ".")));
}
const _AFFIRMATIVE_PLAN = "утверждён";
function planApproved(plan: unknown): boolean {
  // Зеркалит backend _plan_approved: план УТВЕРЖДЁН = число>0 в поле plan (7
  // флагманов держат сумму в статус-поле) ИЛИ строковый статус, начинающийся с
  // «Утверждён» (в т.ч. «Утверждён №9/25.03.2025»). yP24/25/26 и years[].plan —
  // это СУММЫ плана (сколько), НЕ признак утверждения.
  if (_isNum(plan)) return Number(String(plan).replace(/\s/g, "").replace(",", ".")) > 0;
  return typeof plan === "string" && plan.trim().toLowerCase().startsWith(_AFFIRMATIVE_PLAN);
}
function forensicDone(c: ProcCompany): boolean {
  return c.forensic === "Завершён" && !!(c.auditor || "").trim() && !!(c.aYears || "").trim();
}

// ─── Derived data (sector-filtered) ──────────────────────────────
const D = computed(() => {
  if (!sectorFilter.value) return companies.value;
  return companies.value.filter(c => c.s === sectorFilter.value);
});

const sortedD = computed(() => {
  return D.value.slice().sort((a, b) => (gPct(b) ?? -1) - (gPct(a) ?? -1));
});

const chartData = computed(() => sortedD.value.filter(c => gP(c) != null));

const hasFact = computed(() => D.value.some(c => gF(c) != null));

// M-4: текущий срез (квартал/9-мес) содержит синтетические планы (год÷период) →
// пометить агрегат, чтобы сводная цифра не читалась как заведённый план.
const anyEstimatedPlan = computed(
  () => periodFilter.value !== "year" && D.value.some(c => gPisEstimate(c)),
);

// Totals
const totals = computed(() => {
  // H-4: считаем среднее исполнение по тем же строкам, что показывают %:
  // план>0 И факт заведён (в т.ч. факт=0 → 0%). Прежний `gP(c) && gF(c)` ронял
  // строки с записанным фактом 0 (в таблице красное 0%, а из среднего пропадали →
  // среднее было завышено). Теперь дисплей и агрегат сходятся.
  const wd = D.value.filter(c => gPctState(c) === "pct");
  const tP = wd.reduce((s, c) => s + (gP(c) || 0), 0);
  const tF = wd.reduce((s, c) => s + (gF(c) || 0), 0);
  const avgP = tP ? Math.round(tF / tP * 1000) / 10 : 0;
  const tPall = D.value.reduce((s, c) => s + (gP(c) || 0), 0);
  const kPlan = Math.round((hasFact.value ? tP : tPall) / 1000);
  const kFact = hasFact.value ? Math.round(tF / 1000) : 0;
  const appr = D.value.filter(c => planApproved(c.plan)).length;   // H-7: тот же предикат, что бейдж/фильтр/бэкенд
  const fDn  = D.value.filter(forensicDone).length;
  const withAud = D.value.filter(c => (c.auditor || "").trim()).length;
  return { tP, tF, avgP, kPlan, kFact, appr, fDn, withAud, count: D.value.length };
});

// Человекочитаемая метка среза (год+период) — общая для computed и тоста fallback.
function fmtPeriod(yr: number, per: Period): string {
  if (per === "year") return `годовой ${yr}`;
  if (per === "9m")   return `9 мес ${yr}`;
  if (per.startsWith("q")) return `${per.toUpperCase()} ${yr}`;
  return String(yr);
}

const periodLabel = computed(() => fmtPeriod(yearFilter.value, periodFilter.value));

const availableYears = computed<number[]>(() => {
  const yrs = new Set<number>([2024, 2025, 2026]);
  for (const c of companies.value) {
    if (Array.isArray(c.years)) {
      for (const y of c.years) if (y.y) yrs.add(y.y);
    }
  }
  return [...yrs].sort((a, b) => a - b);
});

// ─── Plan / Forensic table data with filters ─────────────────────
const planRows = computed(() => {
  let rows = sortedD.value;
  // Один предикат с бейджем/KPI: «Утверждён» = planApproved; «Не утверждён» =
  // есть статус-значение, но не утверждён (компании без плана «—» не попадают ни в один).
  if (planFilter.value === "Утверждён") {
    rows = rows.filter(c => planApproved(c.plan));
  } else if (planFilter.value === "Не утверждён") {
    rows = rows.filter(c => c.plan != null && c.plan !== "" && !planApproved(c.plan));
  }
  return rows;
});

const forRows = computed(() => {
  let rows = sortedD.value;
  if (forFilter.value) {
    rows = rows.filter(c => forFilter.value === "Тендер"
      ? (c.forensic || "").indexOf("Тендер") >= 0
      : c.forensic === forFilter.value);
  }
  if (audFilter.value) rows = rows.filter(c => (c.auditor || "").indexOf(audFilter.value) >= 0);
  return rows;
});

// Per-auditor breakdown (KPMG/PwC/Deloitte/E&Y)
const auditorStats = computed(() => {
  const keys: Array<"KPMG" | "PwC" | "Deloitte" | "E&Y"> = ["KPMG", "PwC", "Deloitte", "E&Y"];
  return keys.map(k => {
    const cos = D.value.filter(c => (c.auditor || "").indexOf(k) >= 0);
    return { key: k, cos, color: AUDITOR_COLORS[k] };
  }).filter(x => x.cos.length > 0);
});

// ─── Format / badge helpers (legacy bdg/fN/pctCol/cleanAud) ────
function fN(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1000) return fmt.fmtNumber(Math.round(v));
  if (v < 10)    return fmt.fmtNumber(v, { decimals: 1 });
  return fmt.fmtNumber(Math.round(v));
}
function cleanAud(a: string | undefined): string {
  return a ? a.replace(/\s*до\s+\d{2}\.\d{2}\.\d{4}/, "") : "—";
}
function auditorColor(a: string | undefined): string {
  if (!a) return "#888780";
  const cleaned = cleanAud(a).trim();
  for (const k of Object.keys(AUDITOR_COLORS)) {
    if (a.indexOf(k) >= 0) return AUDITOR_COLORS[k];
  }
  return AUDITOR_COLORS[cleaned] || "#64748B";
}

interface BadgeStyle { bg: string; fg: string }
const BADGE_STYLES: Record<string, BadgeStyle> = {
  done:        { bg: "rgba(29,158,117,.12)", fg: "#1D9E75" },
  progress:    { bg: "rgba(55,138,221,.10)", fg: "#378ADD" },
  tender:      { bg: "rgba(239,159,39,.10)", fg: "#D97706" },
  none:        { bg: "rgba(226,75,74,.08)",  fg: "#993D3D" },
  approved:    { bg: "rgba(29,158,117,.12)", fg: "#1D9E75" },
  notApproved: { bg: "rgba(226,75,74,.08)",  fg: "#993D3D" },
  noplan:      { bg: "var(--bg3)",           fg: "var(--t3)" },
};

function planBadge(plan: string | number | undefined | null): { text: string; style: BadgeStyle } {
  if (plan == null || plan === "") return { text: "—", style: BADGE_STYLES.noplan };
  if (planApproved(plan)) {
    // сохраняем номер приказа, если он есть в строковом статусе («Утверждён №9/…»)
    const text = typeof plan === "string" && plan.trim().length > "Утверждён".length
      ? plan.trim() : "Утверждён";
    return { text, style: BADGE_STYLES.approved };
  }
  return { text: "Не утверждён", style: BADGE_STYLES.notApproved };
}
function forensicBadge(f: string | undefined): { text: string; style: BadgeStyle } {
  if (!f) return { text: "—", style: BADGE_STYLES.noplan };
  if (f === "Завершён")    return { text: "Завершён",   style: BADGE_STYLES.done };
  if (f === "В процессе")  return { text: "В процессе", style: BADGE_STYLES.progress };
  if (f.indexOf("Тендер") >= 0) return { text: f, style: BADGE_STYLES.tender };
  return { text: f, style: BADGE_STYLES.none };
}

function toggleAuditor(k: "KPMG" | "PwC" | "Deloitte" | "E&Y") {
  audFilter.value = audFilter.value === k ? "" : k;
}

// Zoom card (mirrors legacy zoomCard pattern; same UX as Governance gv-zoomed)
type ZoomKey = "chart" | "plan" | "forensic";
const zoomed = ref<ZoomKey | null>(null);
async function toggleZoom(k: ZoomKey) {
  zoomed.value = zoomed.value === k ? null : k;
  // Resize chart so it fills the new viewport (zoomed cards change layout box)
  await nextTick();
  await renderChart();
}

// Edit-menu modals state
const showUploadModal = ref(false);
const showEditModal = ref(false);
const yearMenuOpen = ref(false);

function closeMenus() {
  editMenuOpen.value = false;
  yearMenuOpen.value = false;
}

async function editAction(action: "import" | "template" | "report" | "edit" | "clear") {
  editMenuOpen.value = false;
  switch (action) {
    case "import":
      showUploadModal.value = true;
      return;
    case "template":
      downloadForensicTemplate(companies.value.map(c => ({ n: c.n, k: c.k, s: c.s })), yearFilter.value);
      return;
    case "edit":
      showEditModal.value = true;
      return;
    case "clear":
      if (await confirmDialog({ message: `Удалить данные по закупкам за ${yearFilter.value}? Это действие нельзя отменить.`, danger: true })) {
        api.delete(`/forensic/data`, { params: { year: yearFilter.value } })
          .then(r => {
            const cleared = (r.data as { cleared?: number })?.cleared ?? 0;
            toast.success(`Удалено ${cleared} year-записей.`);
            load();
          })
          .catch((e: { response?: { data?: { detail?: string } }; message?: string }) => {
            toast.error("Ошибка: " + (e?.response?.data?.detail || e?.message || "—"));
          });
      }
      return;
    case "report":
      toast.info("Конструктор отчётов — отдельный модуль (планируется отдельно).");
      return;
  }
}

async function onEditSaved(patches: { company: ProcCompany; year: number }[]) {
  if (!patches.length) { showEditModal.value = false; return; }
  let saved = 0, queued = 0, failed = 0;
  for (const { company, year } of patches) {
    const yr = company.years?.find(y => y.y === year);
    const payload: Record<string, unknown> = {
      year,
      // Data-safety: 7 флагманов держат ЧИСЛОВУЮ сумму плана в поле plan. Никогда
      // не отправляем число как plan_status (строка) — иначе бэк 422'ит (тихий
      // failed++) либо затирает сумму статус-строкой. Число → null (не трогаем поле).
      plan_status:     typeof company.plan === "string" ? company.plan : null,
      forensic_status: company.forensic ?? null,
      auditor:         company.auditor ?? null,
      audit_years:     company.aYears ?? null,
    };
    if (yr) {
      payload.year_fields = {
        plan: yr.plan, fact: yr.fact, n9p: yr.n9p, n9f: yr.n9f,
        q1p: yr.q1p, q1f: yr.q1f, q2p: yr.q2p, q2f: yr.q2f,
        q3p: yr.q3p, q3f: yr.q3f, q4p: yr.q4p, q4f: yr.q4f,
      };
    }
    try {
      const r = await api.put(`/forensic/companies/${encodeURIComponent(company.k)}`, payload);
      // 202 → moderation queued; 200 → applied
      if (r.status === 202 || (r.data as { queued?: boolean })?.queued) {
        queued++;
      } else {
        saved++;
      }
    } catch {
      failed++;
    }
  }
  const parts = [`Сохранено: ${saved}`];
  if (queued)  parts.push(`на модерации: ${queued}`);
  if (failed)  parts.push(`ошибок: ${failed}`);
  if (failed) toast.error(parts.join(" · "));
  else        toast.success(parts.join(" · "));
  showEditModal.value = false;
  await load();
}

async function onUploaded() {
  await load();  // refresh from backend
}

// ─── Chart.js bar (Plan vs Fact) ─────────────────────────────────
const chartCanvas = ref<HTMLCanvasElement | null>(null);
let chartInstance: { destroy: () => void; resize: () => void; update: (mode?: string) => void } | null = null;
let resizeObs: ResizeObserver | null = null;

function barColSec(s: string): string {
  const m: Record<string, string> = {
    mining: "rgba(155,142,196,.50)", oilgas: "rgba(29,158,117,.50)",
    energy: "rgba(239,159,39,.50)",  transport: "rgba(55,138,221,.50)",
    other:  "rgba(136,135,128,.50)",
  };
  return m[s] || m.other;
}

async function renderChart() {
  await nextTick();
  let cv = chartCanvas.value;
  for (let i = 0; i < 10; i++) {
    cv = chartCanvas.value;
    const w = cv?.parentElement?.getBoundingClientRect().width ?? 0;
    if (cv && w > 0) break;
    await new Promise<void>(r => requestAnimationFrame(() => r()));
  }
  if (!cv) return;
  // No data — destroy any prior instance and stop (the watch will re-run when
  // data arrives). Without this, an empty rect canvas leaks between renders.
  if (!chartData.value.length) {
    if (chartInstance) { try { chartInstance.destroy(); } catch { /* swallow */ } chartInstance = null; }
    return;
  }
  const w = window as unknown as {
    Chart?: { getChart?: (cv: HTMLCanvasElement) => { destroy: () => void; resize: () => void; update: (mode?: string) => void } | undefined } &
             (new (cv: HTMLCanvasElement, cfg: unknown) => { destroy: () => void; resize: () => void; update: (mode?: string) => void });
  };
  const ChartGlobal = w.Chart;
  if (!ChartGlobal) {
    console.warn("[ForensicAudit] window.Chart not available — bar chart skipped");
    return;
  }

  // Destroy previous instance attached to canvas
  const existing = ChartGlobal.getChart && ChartGlobal.getChart(cv);
  if (existing) { try { existing.destroy(); } catch { /* swallow */ } }
  if (chartInstance) { try { chartInstance.destroy(); } catch { /* swallow */ } chartInstance = null; }

  const labels = chartData.value.map(c => c.n);
  const plans  = chartData.value.map(c => gP(c) || 0);
  const facts  = chartData.value.map(c => gF(c) || 0);
  const colorsFact = chartData.value.map(c => barColSec(c.s));
  const colorsPlan = chartData.value.map(c => barColSec(c.s).replace(/[\d.]+\)$/, "0.18)"));

  const datasets: unknown[] = hasFact.value
    ? [
        { label: "План", data: plans, backgroundColor: colorsPlan, borderRadius: 4, barPercentage: 0.85, categoryPercentage: 0.7, order: 2 },
        { label: "Факт", data: facts, backgroundColor: colorsFact, borderRadius: 4, barPercentage: 0.85, categoryPercentage: 0.7, order: 2 },
      ]
    : [
        { data: plans, backgroundColor: colorsFact, borderRadius: 4, barPercentage: 0.72 },
      ];

  const barLabelPlugin = {
    id: "procBarLabels",
    afterDraw(chart: { ctx: CanvasRenderingContext2D; data: { datasets: { data: number[] }[] }; getDatasetMeta: (i: number) => { data: { x: number; y: number }[] } }) {
      const ctx = chart.ctx;
      ctx.save();
      chart.data.datasets.forEach((ds, di) => {
        const meta = chart.getDatasetMeta(di);
        meta.data.forEach((bar, i) => {
          const v = ds.data[i];
          if (!v) return;
          const label = fmt.fmtNumber(Math.round(v));
          ctx.fillStyle = di === 1 ? "#5F5E5A" : "#94A3B8";
          ctx.font = (di === 1 ? "600" : "500") + " 9px var(--font, system-ui)";
          ctx.textAlign = "center";
          ctx.textBaseline = "bottom";
          ctx.fillText(label, bar.x, bar.y - 3);
        });
      });
      ctx.restore();
    },
  };

  // Observe the wrap container — if the user toggles zoom / sidebar / etc.,
  // ResizeObserver fires and we tell Chart.js to recompute its canvas.
  if (resizeObs) { resizeObs.disconnect(); resizeObs = null; }
  if (typeof ResizeObserver !== "undefined" && cv.parentElement) {
    resizeObs = new ResizeObserver(() => {
      if (chartInstance) {
        try { chartInstance.resize(); } catch { /* swallow */ }
      }
    });
    resizeObs.observe(cv.parentElement);
  }

  // Safety: schedule resize triggers AFTER chart instance is created.
  // The parent card has `animation: prCardIn .5s` with transform+opacity,
  // and Chart.js sometimes initialises with the pre-animation 0-sized canvas
  // — bars only become visible after the user interacts (e.g. zoom toggle
  // triggers the ResizeObserver). These deferred resize() calls force the
  // canvas to remeasure once the animation settles.
  const scheduleResize = () => {
    if (chartInstance) {
      try {
        chartInstance.resize();
        chartInstance.update("none");   // force redraw without animation
      } catch { /* swallow */ }
    }
  };
  requestAnimationFrame(() => requestAnimationFrame(scheduleResize));
  setTimeout(scheduleResize, 100);
  setTimeout(scheduleResize, 350);
  setTimeout(scheduleResize, 700);   // post-animation (prCardIn = 500ms)

  chartInstance = new ChartGlobal(cv, {
    type: "bar",
    data: { labels, datasets },
    plugins: [barLabelPlugin],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 600, easing: "easeOutQuart" },
      scales: {
        x: { grid: { display: false }, border: { display: false },
             ticks: { font: { size: 10 }, color: "#94A3B8", maxRotation: 55, minRotation: 25 } },
        y: { grid: { color: "rgba(0,0,0,.04)" }, border: { display: false },
             ticks: { font: { size: 10 }, color: "#94A3B8",
                      callback: (v: number) => `${fmt.fmtNumber(Math.round(v))} млрд` } },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0F172A", titleColor: "#F8FAFC", bodyColor: "#CBD5E1",
          padding: 12, cornerRadius: 10,
          callbacks: {
            label: (ctx: { dataIndex: number }) => {
              const c = chartData.value[ctx.dataIndex];
              const pct = gPct(c);
              return hasFact.value
                ? ` План: ${fN(gP(c))} / Факт: ${fN(gF(c))} (${pct != null ? pct + "%" : "—"})`
                : ` ${fN(gP(c))} млрд`;
            },
          },
        },
      },
    },
  } as unknown);
}

watch([chartData, hasFact, yearFilter, periodFilter, sectorFilter], () => {
  renderChart();
}, { flush: "post" });

// Safety net: if the canvas element appears (remount) while we have data,
// kick off render — covers any future Transition/v-if induced remounts.
watch(chartCanvas, (next) => {
  if (next && chartData.value.length) {
    renderChart();
  }
});

// ─── Count-up scan root ──────────────────────────────────────────
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 60, stagger: 80 });

watch([totals, hasFact], async () => {
  await nextTick();
  rescan();
});

// ─── Load ────────────────────────────────────────────────────────
async function load() {
  loading.value = true;
  errorMsg.value = null;
  try {
    const { data } = await api.get<{ companies: ProcCompany[]; kpis: Kpis }>(
      "/forensic/overview"
    );
    companies.value = data.companies || [];
    kpis.value = data.kpis || { total_companies: 0, plan_approved: 0, forensic_done: 0, with_auditor: 0 };

    // Auto-fallback: if default (2025/9m) has no plan data for any company,
    // pick the first (year, period) combo that actually has data so the chart
    // isn't empty on first paint. Tries the user's current year first, then
    // walks through available years from newest to oldest.
    if (!chartData.value.length) {
      const prevYear = yearFilter.value, prevPer = periodFilter.value;
      const yrsToTry = [yearFilter.value, ...availableYears.value.slice().reverse().filter(y => y !== yearFilter.value)];
      const pers: Period[] = ["year", "9m", "q4", "q3", "q2", "q1"];
      outer: for (const y of yrsToTry) {
        for (const p of pers) {
          const probe = (c: ProcCompany) => {
            const yObj = _getYr(c, y);
            if (yObj) {
              if (p === "year") return yObj.plan != null;
              if (p === "9m")   return yObj.n9p  != null;
              return (yObj as unknown as Record<string, number | null | undefined>)[`${p}p`] != null;
            }
            // legacy fallback
            if (y === 2024) return p === "year" ? c.yP24 != null : p === "9m" ? c.nP24 != null : false;
            if (y === 2025) {
              if (p === "year") return c.yP25 != null;
              if (p === "9m")   return c.nP25 != null;
              return (c as unknown as Record<string, number | null | undefined>)[`${p.toUpperCase()}25`] != null;
            }
            if (y === 2026) return p === "year" ? c.yP26 != null : false;
            return false;
          };
          if (companies.value.some(probe)) {
            yearFilter.value = y;
            periodFilter.value = p;
            break outer;
          }
        }
      }
      // M-12 ([[feedback_everywhere_rule]]): не менять срез молча — чипы года/периода
      // «прыгнули» бы без объяснения. Явно сообщаем о подмене.
      if (yearFilter.value !== prevYear || periodFilter.value !== prevPer) {
        toast.info(`Нет данных за ${fmtPeriod(prevYear, prevPer)} — показан ${fmtPeriod(yearFilter.value, periodFilter.value)}`);
      }
    }

    await nextTick();
    await renderChart();
    rescan();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    errorMsg.value = err?.response?.data?.detail || err?.message || "Ошибка загрузки";
    companies.value = [];
  } finally {
    loading.value = false;
  }
}

onMounted(load);
onBeforeUnmount(() => {
  if (resizeObs) { try { resizeObs.disconnect(); } catch { /* swallow */ } resizeObs = null; }
  if (chartInstance) { try { chartInstance.destroy(); } catch { /* swallow */ } chartInstance = null; }
});
</script>

<template>
  <!-- NB: removed <Transition mode="out-in"> wrapper with :key=filters —
       it caused the chart canvas to unmount/remount on every filter change,
       leaving Chart.js init with a null ref ("FAIL: canvas null after 10 frames").
       Filter changes now mutate the same DOM without re-mount. -->
  <div>
    <div>
      <div class="pr-view">

        <!-- ═══ Topbar (dark navy) ═══ -->
        <div class="pr-topbar">
          <SidebarBurger />
          <div class="pr-tb-l">
            <h1 class="pr-tb-title">Закупки и Форензик аудит</h1>
            <div class="pr-tb-sub" v-if="kpis.total_companies">
              <span><b>{{ kpis.total_companies }}</b> компаний</span>
              <span class="pr-dot">·</span>
              <span><b>{{ kpis.plan_approved }}</b> план утверждён</span>
              <span class="pr-dot">·</span>
              <span><b>{{ kpis.forensic_done }}</b> форензик завершён</span>
            </div>
          </div>
          <div class="pr-tb-r" @click="closeMenus()">

            <!-- Year switcher — единый степпер FY (как везде, UzaYearStepper) -->
            <UzaYearStepper v-model="yearFilter" :years="availableYears" prefix="FY " tone="dark" />

            <!-- Period segmented -->
            <div class="pr-seg">
              <button :class="{ on: periodFilter === 'year' }" @click="periodFilter = 'year'">Год</button>
              <button :class="{ on: periodFilter === '9m'   }" @click="periodFilter = '9m'  ">9 мес</button>
              <button v-for="q in (['q1','q2','q3','q4'] as const)" :key="q"
                :class="{ on: periodFilter === q }" @click="periodFilter = q">{{ q.toUpperCase() }}</button>
            </div>

            <!-- Edit menu (▤) -->
            <div class="pr-edit-wrap" @click.stop>
              <button class="pr-edit-btn" @click="editMenuOpen = !editMenuOpen" title="Действия">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="3" r="1.4" fill="currentColor"/>
                  <circle cx="8" cy="8" r="1.4" fill="currentColor"/>
                  <circle cx="8" cy="13" r="1.4" fill="currentColor"/>
                </svg>
              </button>
              <div v-if="editMenuOpen" class="pr-edit-menu">
                <button @click="editAction('edit')"><span class="pr-em-ico"></span>Редактировать данные</button>
                <div class="pr-em-sep"></div>
                <button class="danger" @click="editAction('clear')"><span class="pr-em-ico">×</span>Очистить все данные</button>
              </div>
            </div>
          </div>
        </div>

        <!-- ═══ Body / scroll container ═══ -->
        <UzaStateBlock v-if="loading && !companies.length" state="loading" variant="text" loadingText="Загрузка..." />
        <UzaStateBlock v-else-if="errorMsg && !companies.length" state="error" variant="block" :text="errorMsg" />

        <div v-else ref="scanRoot" class="pr-body" @click="editMenuOpen = false">

          <!-- ═══ 1. KPI strip (3 cells) ═══ -->
          <div class="pr-kpi-strip kpi-rail">

            <!-- Composite: План | Факт | Исполнение -->
            <div
              class="kpi2 fin-shimmer pr-kpi-composite"
              :style="{ '--kpi2-accent': hasFact ? pctCol(totals.avgP) : '#7F77DD', '--kpi2-d': '0ms' }"
            >
              <div class="pr-comp-grid">
                <div class="pr-comp-cell">
                  <div class="kpi2-lbl">План</div>
                  <div class="kpi2-val"><span :data-countup="totals.kPlan">{{ totals.kPlan }}</span></div>
                  <div class="pr-comp-unit"
                       :title="anyEstimatedPlan ? 'Включает оценочные квартальные планы (год÷период): квартальная разбивка заведена не по всем компаниям' : ''">
                    <span v-if="anyEstimatedPlan">≈ </span>трлн сум
                  </div>
                </div>
                <div class="pr-comp-divider"></div>
                <div class="pr-comp-cell">
                  <div class="kpi2-lbl">{{ hasFact ? 'Факт' : '—' }}</div>
                  <div class="kpi2-val"><span :data-countup="totals.kFact">{{ totals.kFact }}</span></div>
                  <div class="pr-comp-unit">{{ hasFact ? 'трлн сум' : '' }}</div>
                </div>
                <div class="pr-comp-divider"></div>
                <div class="pr-comp-cell">
                  <div class="kpi2-lbl">Исполнение</div>
                  <div class="kpi2-val pr-comp-pct" :style="{ color: hasFact ? pctCol(totals.avgP) : 'var(--t3)' }">
                    <span :data-countup="hasFact ? totals.avgP : 0">{{ hasFact ? totals.avgP : 0 }}</span><span class="pr-comp-pct-sign">%</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- Планы утверждены -->
            <div class="kpi2 fin-shimmer" style="--kpi2-accent:#7F77DD; --kpi2-d:80ms">
              <div class="kpi2-lbl">Планы утверждены</div>
              <div class="kpi2-val">
                <span :data-countup="totals.appr">{{ totals.appr }}</span>
                <span class="pr-of"> / {{ totals.count }}</span>
              </div>
            </div>

            <!-- Аудит завершён (H-3: только «Завершён» + аудитор + годы) -->
            <div class="kpi2 fin-shimmer" style="--kpi2-accent:#1D9E75; --kpi2-d:160ms">
              <div class="kpi2-lbl">Аудит завершён</div>
              <div class="kpi2-val">
                <span :data-countup="totals.fDn">{{ totals.fDn }}</span>
                <span class="pr-of"> / {{ totals.count }}</span>
              </div>
              <div class="pr-kpi-sub" title="Компаний, у которых указан аудитор">с аудитором: {{ totals.withAud }}</div>
            </div>
          </div>

          <!-- ═══ 2. Bar chart (Plan vs Fact) ═══ -->
          <div class="pr-cc pr-chart-card" :class="{ 'pr-zoomed': zoomed === 'chart' }" style="--d:200ms">
            <div class="pr-cc-h">
              <div class="pr-cc-t">Исполнение плана закупок, {{ periodLabel }}</div>
              <div class="pr-cc-rt">
                <div class="pr-seg">
                  <button :class="{ on: !sectorFilter }" @click="sectorFilter = ''">Все</button>
                  <button
                    v-for="sid in (['mining','oilgas','energy','transport','other'] as const)"
                    :key="sid"
                    :class="{ on: sectorFilter === sid }"
                    @click="sectorFilter = sid"
                  >{{ SECTOR_LABELS_RU[sid] }}</button>
                </div>
                <button class="pr-zoom-btn" @click="toggleZoom('chart')" :title="zoomed === 'chart' ? 'Свернуть' : 'Развернуть'">
                  <svg v-if="zoomed !== 'chart'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                  <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                    <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                      stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                  </svg>
                </button>
              </div>
            </div>
            <div class="pr-chart-wrap" :style="{ height: Math.max(320, chartData.length * 28 + 60) + 'px' }">
              <canvas ref="chartCanvas"></canvas>
              <!-- Empty-state overlay when no data for current filter -->
              <div v-if="!chartData.length" class="pr-chart-empty">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#94A3B8" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="20" x2="18" y2="10"/>
                  <line x1="12" y1="20" x2="12" y2="4"/>
                  <line x1="6"  y1="20" x2="6"  y2="14"/>
                </svg>
                <div class="pr-empty-t">Нет данных за {{ periodLabel }}</div>
                <div class="pr-empty-s">
                  Ни у одной из {{ D.length }} компаний нет плана за этот период.
                  <template v-if="periodFilter !== 'year'">
                    Попробуй переключиться на «Год» или другой квартал —
                    <button class="pr-empty-link" @click="periodFilter = 'year'">переключить на «Год»</button>.
                  </template>
                </div>
              </div>
            </div>
            <div v-if="hasFact && chartData.length" class="pr-chart-legend">
              <span><span class="pr-leg-dot" style="background: rgba(127,119,221,.15)"></span> План</span>
              <span><span class="pr-leg-dot" style="background: rgba(127,119,221,.50)"></span> Факт</span>
            </div>
          </div>

          <!-- ═══ 3. 2-col: Plan table + Forensic table ═══ -->
          <div class="pr-bot-grid">

            <!-- LEFT: Plan -->
            <div class="pr-cc" :class="{ 'pr-zoomed': zoomed === 'plan' }" style="--d:280ms">
              <div class="pr-cc-h">
                <div class="pr-cc-t">План закупок</div>
                <div class="pr-cc-rt">
                  <div class="pr-seg">
                    <button :class="{ on: planFilter === '' }" @click="planFilter = ''">Все</button>
                    <button :class="{ on: planFilter === 'Утверждён' }" @click="planFilter = 'Утверждён'">Утверждён</button>
                    <button :class="{ on: planFilter === 'Не утверждён' }" @click="planFilter = 'Не утверждён'">Не утверждён</button>
                  </div>
                  <button class="pr-zoom-btn" @click="toggleZoom('plan')" :title="zoomed === 'plan' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'plan'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>
              <div class="pr-tbl-wrap">
                <table class="pr-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th>Статус</th>
                      <th class="rt">План, млрд</th>
                      <th class="rt">Факт, млрд</th>
                      <th class="rt">%</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(c, i) in planRows" :key="c.k" :style="{ animationDelay: (Math.min(i, 30) * 18) + 'ms' }">
                      <td class="lt">
                        <CompanyAvatar :name="c.n" :color="c.sector_color || '#888780'" :size="20" />
                        <span class="pr-co-name">{{ c.n }}</span>
                      </td>
                      <td class="center">
                        <span class="pr-badge"
                          :style="{ background: planBadge(c.plan).style.bg, color: planBadge(c.plan).style.fg }">
                          {{ planBadge(c.plan).text }}
                        </span>
                      </td>
                      <td class="rt num muted"
                          :title="gPisEstimate(c) ? 'Оценка: годовой план ÷ доля периода (квартальный план не заведён)' : ''">
                        <span v-if="gPisEstimate(c)" style="color:var(--t3);font-weight:400" title="оценка">≈</span>{{ fN(gP(c)) }}
                      </td>
                      <td class="rt num muted">{{ fN(gF(c)) }}</td>
                      <td class="rt num" :style="{ color: pctCol(gPct(c)), fontWeight: 600 }"
                          :title="pctZone(gPct(c)) + (gPisEstimate(c) && gPctState(c) === 'pct' ? ' · % от оценочного плана (год÷период)' : '')">
                        <!-- H-4: 0% (факт=0 при плане) красным; «факт —» когда план есть, а факта нет; «—» когда плана нет -->
                        <template v-if="gPctState(c) === 'pct'">{{ gPct(c) }}%</template>
                        <span v-else-if="gPctState(c) === 'nofact'" class="pr-nofact" title="План есть, факт не заведён">факт —</span>
                        <span v-else style="color:var(--t3)">—</span>
                      </td>
                    </tr>
                    <tr v-if="!planRows.length"><td colspan="5"><UzaStateBlock state="empty" variant="inline" text="Нет компаний" /></td></tr>
                  </tbody>
                </table>
              </div>
            </div>

            <!-- RIGHT: Forensic + auditor breakdown -->
            <div class="pr-cc" :class="{ 'pr-zoomed': zoomed === 'forensic' }" style="--d:330ms">
              <div class="pr-cc-h">
                <div class="pr-cc-t">Форензик аудит</div>
                <div class="pr-cc-rt">
                  <div class="pr-seg">
                    <button :class="{ on: forFilter === '' }" @click="forFilter = ''">Все</button>
                    <button :class="{ on: forFilter === 'Завершён' }"  @click="forFilter = 'Завершён'">Завершён</button>
                    <button :class="{ on: forFilter === 'В процессе' }" @click="forFilter = 'В процессе'">В процессе</button>
                    <button :class="{ on: forFilter === 'Тендер' }"   @click="forFilter = 'Тендер'">Тендер</button>
                    <button :class="{ on: forFilter === 'Не начат' }"  @click="forFilter = 'Не начат'">Не начат</button>
                  </div>
                  <button class="pr-zoom-btn" @click="toggleZoom('forensic')" :title="zoomed === 'forensic' ? 'Свернуть' : 'Развернуть'">
                    <svg v-if="zoomed !== 'forensic'" width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                    <svg v-else width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M6 2v4H2M10 6h4V2M10 14v-4h4M6 10H2v4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>

              <!-- Auditor breakdown -->
              <div v-if="auditorStats.length" class="pr-aud-block">
                <div class="pr-aud-title">По аудиторам</div>
                <div v-for="ag in auditorStats" :key="ag.key" class="pr-aud-row uza-side-stripe-host" :class="{ on: audFilter === ag.key }" @click="toggleAuditor(ag.key)">
                  <span class="uza-stripe-el" :style="{ '--stripe-color': ag.color }" />
                  <span class="pr-aud-legend">
                    <span class="pr-aud-name">{{ ag.key }}</span>
                    <span class="pr-big4" :style="{ background: ag.color + '15', color: ag.color, borderColor: ag.color + '25' }">Big 4</span>
                  </span>
                  <div class="pr-aud-bar">
                    <div class="pr-aud-bar-fill" :style="{ width: Math.round(ag.cos.length / totals.count * 100) + '%', background: ag.color }"></div>
                  </div>
                  <span class="pr-aud-cnt">{{ ag.cos.length }}</span>
                  <svg class="pr-aud-chev" :class="{ open: audFilter === ag.key }" width="11" height="11" viewBox="0 0 12 12" fill="none">
                    <path d="M2.5 4.5l3.5 3 3.5-3" :stroke="ag.color" stroke-width="1.5" stroke-linecap="round"/>
                  </svg>
                  <div v-if="audFilter === ag.key" class="pr-aud-cos">
                    <span v-for="c in ag.cos" :key="c.k" class="pr-aud-co" :style="{ background: ag.color + '0D', color: ag.color }">{{ c.n }}</span>
                  </div>
                </div>
              </div>

              <div class="pr-tbl-wrap">
                <table class="pr-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th>Статус</th>
                      <th class="lt-sub">Аудитор</th>
                      <th class="lt-sub">Период</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(c, i) in forRows" :key="c.k" :style="{ animationDelay: (Math.min(i, 30) * 18) + 'ms' }">
                      <td class="lt">
                        <CompanyAvatar :name="c.n" :color="c.sector_color || '#888780'" :size="20" />
                        <span class="pr-co-name">{{ c.n }}</span>
                      </td>
                      <td class="center">
                        <span class="pr-badge"
                          :style="{ background: forensicBadge(c.forensic).style.bg, color: forensicBadge(c.forensic).style.fg }">
                          {{ forensicBadge(c.forensic).text }}
                        </span>
                      </td>
                      <td>
                        <span v-if="c.auditor" class="pr-aud-cell">
                          <BadgeConsultant size="sm" :consultants="[{ id: c.auditor, abbr: cleanAud(c.auditor), color: auditorColor(c.auditor) }]" />
                          <span class="pr-big4" :style="{ background: auditorColor(c.auditor) + '15', color: auditorColor(c.auditor), borderColor: auditorColor(c.auditor) + '25' }">Big 4</span>
                        </span>
                        <span v-else class="muted">—</span>
                      </td>
                      <td class="muted">{{ c.aYears || '—' }}</td>
                    </tr>
                    <tr v-if="!forRows.length"><td colspan="4"><UzaStateBlock state="empty" variant="inline" text="Нет компаний" /></td></tr>
                  </tbody>
                </table>
              </div>
            </div>

          </div>

        </div>

        <!-- Edit-menu modals -->
        <ForensicUploadModal
          v-if="showUploadModal"
          :year="yearFilter"
          @close="showUploadModal = false"
          @uploaded="onUploaded"
        />
        <ForensicEditModal
          v-if="showEditModal"
          :companies="companies"
          :year="yearFilter"
          @close="showEditModal = false"
          @saved="onEditSaved"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pr-view { background: var(--bg, #F4F3F9); min-height: 100%; font-family: var(--font, system-ui); }

@keyframes prFadeUp {
  0%   { opacity: 0; transform: translateY(8px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes prCardIn {
  0%   { opacity: 0; transform: translateY(12px) scale(.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}

/* ─── Topbar ─── */
.pr-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex; align-items: center; justify-content: space-between;
  gap: 14px; flex-wrap: wrap;
}
.pr-tb-l { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.pr-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; }
.pr-tb-sub {
  font-size: 11px; color: rgba(255,255,255,.55);
  display: flex; align-items: center; gap: 6px;
}
.pr-tb-sub b { color: rgba(255,255,255,.95); font-weight: 600; }
.pr-dot { opacity: .4; }
.pr-tb-r { display: flex; align-items: center; gap: 8px; }

/* ─── Year badge (golden-text dropdown, 1:1 legacy yearBadgeHtml) ─── */
.pr-badge-wrap { position: relative; }
.pr-badge {
  display: flex; align-items: center; gap: 6px;
  background: rgba(255, 255, 255, .08);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  padding: 5px 11px;
  border-radius: 8px;
  font-size: 12px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: background .12s;
}
.pr-badge:hover { background: rgba(255, 255, 255, .15); }
.pr-chev { transition: transform .15s; flex-shrink: 0; }
.pr-chev.open { transform: rotate(180deg); }
.pr-dd {
  position: absolute; top: calc(100% + 4px); right: 0;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  min-width: 120px;
  padding: 4px;
  z-index: 100;
  animation: prFadeUp .15s ease;
}
.pr-dd-item {
  padding: 7px 10px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  transition: background .1s;
  font-feature-settings: 'tnum';
}
.pr-dd-item:hover { background: #F4F3F9; }
.pr-dd-item.active { background: rgba(127, 119, 221, .12); color: var(--p-deep); font-weight: 600; }

/* Segmented control (legacy .seg-ctrl) — works in both topbar and body */
.pr-seg {
  display: inline-flex;
  background: rgba(0, 0, 0, .04);
  border-radius: 7px;
  padding: 2px;
}
.pr-topbar .pr-seg { background: rgba(255, 255, 255, .12); }
.pr-seg button {
  background: transparent; border: 0;
  font-size: 11px; padding: 4px 10px;
  border-radius: 5px;
  color: rgba(255, 255, 255, .65);
  cursor: pointer;
  font-family: inherit; font-weight: 500;
  transition: all .12s;
}
.pr-body .pr-seg button { color: var(--t3, var(--t-muted)); }
.pr-seg button:hover { color: #fff; }
.pr-body .pr-seg button:hover { color: var(--t1, #1E2A4A); }
.pr-seg button.on {
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .12);
}
.pr-body .pr-seg button.on { box-shadow: 0 1px 3px rgba(0, 0, 0, .08); }

/* Edit menu */
.pr-edit-wrap { position: relative; }
.pr-edit-btn {
  background: rgba(255, 255, 255, .12);
  border: 1px solid rgba(255, 255, 255, .15);
  color: #fff;
  width: 32px; height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.pr-edit-btn:hover { background: rgba(255, 255, 255, .2); }
.pr-edit-menu {
  position: absolute; top: 38px; right: 0;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .08);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(15, 23, 60, .14);
  min-width: 220px;
  padding: 6px;
  z-index: 100;
  animation: prFadeUp .15s ease;
}
.pr-edit-menu button {
  display: flex; align-items: center; gap: 8px;
  width: 100%;
  background: transparent; border: 0;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  transition: background .12s;
}
.pr-edit-menu button:hover { background: #F4F3F9; }
.pr-edit-menu button.danger { color: var(--sev-critical); }
.pr-edit-menu button.danger:hover { background: rgba(226, 75, 74, .08); }
.pr-em-ico { width: 14px; text-align: center; color: var(--t3, var(--t-muted)); font-weight: 600; }
.pr-em-sep { height: 1px; background: rgba(0, 0, 0, .06); margin: 4px 0; }

.pr-body { padding: 16px 20px 24px; }

/* ─── KPI strip ─── */
.pr-kpi-strip {
  display: grid;
  grid-template-columns: minmax(0, 3fr) minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  margin-bottom: 14px;
}
.kpi2.pr-kpi-composite { padding: 16px 20px; }
.pr-comp-grid { display: flex; align-items: stretch; }
.pr-comp-cell { flex: 1; padding: 0 16px; }
.pr-comp-cell:first-child { padding-left: 0; }
.pr-comp-cell:last-child { padding-right: 0; }
.pr-comp-divider { width: 1px; background: rgba(0, 0, 0, .08); margin: 4px 0; }
.pr-comp-unit { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.pr-comp-pct { font-size: 40px; }
.pr-comp-pct-sign { font-size: 20px; }
.pr-of { font-size: 16px; color: var(--t3, var(--t-muted)); margin-left: 2px; font-weight: 500; }
.pr-kpi-sub { font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 3px; font-weight: 500; letter-spacing: .01em; }
.pr-nofact { font-size: 11.5px; color: var(--t3, var(--t-muted)); font-weight: 500; font-style: italic; }

@media (max-width: 1100px) { .pr-kpi-strip { grid-template-columns: 1fr; } }
@media (max-width: 720px)  { .pr-comp-grid { flex-direction: column; gap: 8px; } .pr-comp-divider { display: none; } }

/* ─── Cards (cc) ─── */
.pr-cc {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  padding: 14px 16px 12px;
  margin-bottom: 12px;
  animation: prCardIn .5s var(--ease-standard) var(--d, 0ms) both;
}
.pr-cc-h {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px;
  flex-wrap: wrap;
}
.pr-cc-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.pr-cc-rt { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

/* Zoom card overlay (mirrors legacy zoomCard, same UX as Governance gv-zoomed) */
.pr-zoom-btn {
  background: transparent; border: 0;
  width: 26px; height: 26px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  transition: background .15s, color .15s;
  flex-shrink: 0;
}
.pr-zoom-btn:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.pr-zoomed {
  position: fixed !important;
  inset: 24px !important;
  z-index: 200 !important;
  background: var(--bg1, #fff) !important;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .25) !important;
  margin: 0 !important;
  overflow: auto !important;
  display: flex; flex-direction: column;
}
.pr-zoomed .pr-tbl-wrap { max-height: none; flex: 1; }
.pr-zoomed .pr-chart-wrap { flex: 1; min-height: 400px; }

/* ─── Chart card ─── */
.pr-chart-card { padding-bottom: 14px; }
.pr-chart-wrap { position: relative; }

/* Empty-state overlay when chartData is empty (typically when user filters
 * to a period that has no data — e.g. 2026 Q1 if snapshot doesn't have it). */
.pr-chart-empty {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  text-align: center;
  padding: 20px;
  color: var(--t3, #5F5E5A);
}
.pr-chart-empty svg { opacity: .5; margin-bottom: 10px; }
.pr-empty-t {
  font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A);
  margin-bottom: 6px;
}
.pr-empty-s { font-size: 12px; color: var(--t3, #5F5E5A); max-width: 480px; line-height: 1.5; }
.pr-empty-link {
  background: transparent; border: 0;
  color: var(--p-deep); text-decoration: underline; cursor: pointer;
  font: inherit; padding: 0;
}
.pr-empty-link:hover { color: var(--t1, #1E2A4A); }
.pr-chart-legend {
  display: flex; gap: 16px;
  padding-top: 8px;
  margin-top: 6px;
  border-top: 0.5px solid rgba(0, 0, 0, .06);
}
.pr-chart-legend span {
  font-size: 11px; color: var(--t3, var(--t-muted));
  display: flex; align-items: center; gap: 4px;
}
.pr-leg-dot { width: 10px; height: 10px; border-radius: 3px; }

/* ─── Bottom grid ─── */
.pr-bot-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
@media (max-width: 1200px) { .pr-bot-grid { grid-template-columns: 1fr; } }

/* ─── Tables ─── */
.pr-tbl-wrap { max-height: 420px; overflow-y: auto; scrollbar-width: thin; }
.pr-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pr-tbl thead {
  background: #FAFAFA;
  position: sticky; top: 0; z-index: 1;
}
.pr-tbl thead th {
  padding: 7px 10px; text-align: center;
  font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
  text-transform: none;
}
.pr-tbl thead th.lt    { text-align: left; padding-left: 10px; }
.pr-tbl thead th.lt-sub{ text-align: left; }
.pr-tbl thead th.rt    { text-align: right; }
.pr-tbl tbody td {
  padding: 7px 10px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A);
}
.pr-tbl tbody td.lt    { display: flex; align-items: center; gap: 7px; }
.pr-tbl tbody td.rt    { text-align: right; }
.pr-tbl tbody td.center{ text-align: center; }
.pr-tbl tbody td.num   { font-feature-settings: "tnum"; }
.pr-tbl tbody td.muted, .pr-tbl tbody td .muted { color: var(--t3, var(--t-muted)); font-size: 11px; }
.pr-tbl tbody tr {
  transition: background .12s;
  animation: prFadeUp .25s ease both;
}
.pr-tbl tbody tr:hover { background: rgba(127, 119, 221, .04); }

/* Имя компании — общий CompanyAvatar (как в Ratings/Fin таблицах) + имя */
/* Аудитор 1:1 как /consultants: боковая полоска + тёмное имя + бейдж «Big 4» */
.pr-aud-legend, .pr-aud-cell { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
.pr-aud-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pr-big4 {
  font-size: 9px; font-weight: 700; letter-spacing: .03em;
  padding: 1px 5px; border-radius: 3px; border: 0.5px solid;
  white-space: nowrap; flex-shrink: 0; line-height: 1.5;
}
.pr-co-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

.pr-badge {
  display: inline-block;
  font-size: 10px; font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

/* ─── Auditor breakdown ─── */
.pr-aud-block {
  margin-bottom: 10px;
  padding: 8px 10px;
  background: var(--bg2, #FAFAFC);
  border-radius: 8px;
  border: 0.5px solid rgba(0, 0, 0, .06);
}
.pr-aud-title {
  font-size: 10px; font-weight: 600; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
  padding: 0 4px 4px;
}
.pr-aud-row {
  display: grid;
  grid-template-columns: 120px 1fr 32px 12px;
  align-items: center;
  gap: 8px;
  padding: 7px 6px 7px 18px;
  border-radius: 6px;
  cursor: pointer;
  transition: background .12s;
}
.pr-aud-row:hover, .pr-aud-row.on { background: rgba(127, 119, 221, .06); }
.pr-aud-pill {
  font-size: 10px; font-weight: 700;
  padding: 3px 8px;
  border-radius: 4px;
  text-align: center;
  letter-spacing: .02em;
}
.pr-aud-bar {
  height: 8px;
  background: rgba(0, 0, 0, .05);
  border-radius: 4px;
  overflow: hidden;
}
.pr-aud-bar-fill { height: 100%; border-radius: 4px; transition: width .3s ease; }
.pr-aud-cnt {
  text-align: right;
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
}
.pr-aud-chev { transition: transform .2s ease; }
.pr-aud-chev.open { transform: rotate(180deg); }
.pr-aud-cos {
  grid-column: 1 / -1;
  padding: 6px 4px 2px 68px;
  display: flex; flex-wrap: wrap; gap: 4px;
}
.pr-aud-co {
  font-size: 10px; font-weight: 500;
  padding: 3px 8px;
  border-radius: 4px;
}

@media (max-width: 480px) {
  .pr-seg { flex-wrap: wrap; gap: 4px; }
  .pr-seg button { font-size: 10px; padding: 4px 9px; }
  .pr-tbl { font-size: 10px; }
  .pr-tbl th, .pr-tbl td { padding: 5px 5px; }
}
</style>
