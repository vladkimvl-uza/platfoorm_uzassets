<script setup lang="ts">
/**
 * Governance dashboard — 1:1 port of legacy `showGovView` (index.html:35149).
 *
 * Layout mirrors the legacy exactly:
 *   • dark navy topbar with edit-menu (▤) and notifications
 *   • 6 KPI cells (Avg score /1200 · Indep% · Members · Vacant · Women% · D&O)
 *   • mid grid: Rating bars (left) + Tabbed Indep/Meetings (right)
 *   • bottom grid: Composition matrix (7 cols, sortable) + Committees (7 commits)
 *   • KPI cell click → drill-down modal (`_govKpiDetail`)
 *   • zoom-card button (4-corner SVG) → fullscreen overlay
 *   • count-up animation on all KPI numbers (`useCountUpScan`)
 *
 * Data: backend `/governance/overview` surfaces both the computed 0..100 score
 * and the legacy raw `governance_score_1200`. Vue prefers the raw score so
 * thresholds 900 / 700 / 600 match the legacy exactly.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import SidebarBurger from "@/components/SidebarBurger.vue";
import { useSavedFilter } from "@/composables/useSavedFilter";
import {
  governanceApi,
  type CommitteeMeetingField,
  type CommitteeMeetingPeriod,
  type CommitteeMeetingsResponse,
  type GovernanceCompanyScore,
  type GovernanceOverviewResponse,
} from "@/api/governance";
import GovCompanyDetailModal from "@/components/Governance/GovCompanyDetailModal.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useCountUpScan } from "@/composables/useCountUp";
import { useCompaniesStore } from "@/stores/companies";
import { usePermissions } from "@/composables/usePermissions";
import { useToast } from "@/composables/useToast";

const companiesStore = useCompaniesStore();
const companiesPerm = usePermissions("companies");
const toast = useToast();

// ───────────────────────────────────────────────────────────────
//   State
// ───────────────────────────────────────────────────────────────

const overview = ref<GovernanceOverviewResponse | null>(null);
const year = useSavedFilter<number | null>("governance.year", null);
const sectorCode = useSavedFilter<string | null>("governance.sectorCode", null);
const loading = ref(false);
const error = ref<string | null>(null);

// Per-company drill modal (existing component, reused).
const drillCompanyId = ref<string | null>(null);

// KPI drill (legacy _govKpiDetail).
type KpiDrillType = "score" | "indep" | "members" | "vacant" | "women" | "dno" | "meetings";
const kpiDrill = ref<KpiDrillType | null>(null);

// Matrix sort (legacy _govMatFilter).
type MatrixCol = "score" | "members" | "indep" | "meetings" | "women" | "age";
const matrixSort = ref<MatrixCol | null>(null);
const matrixDir = ref<-1 | 1>(-1);

// Zoom-card (legacy zoomCard).
const zoomed = ref<string | null>(null);

// Container ref for count-up scan.
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 40, stagger: 80 });

// ───────────────────────────────────────────────────────────────
//   Load
// ───────────────────────────────────────────────────────────────

async function load() {
  loading.value = true;
  error.value = null;
  try {
    overview.value = await governanceApi.getOverview({
      year: year.value ?? undefined,
      sector_code: sectorCode.value ?? undefined,
      rankings_limit: 100,
    });
    await nextTick();
    rescan();
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

// ───────────────────────────────────────────────────────────────
//   Headline subtext
// ───────────────────────────────────────────────────────────────

const headerSub = computed(() => {
  if (!overview.value) return "";
  const k = overview.value.kpis;
  const parts: string[] = [];
  parts.push(year.value ? `FY ${year.value}` : "все годы");
  if (sectorCode.value) parts.push(`сектор ${sectorCode.value}`);
  parts.push(`${k.companies_with_data} из ${k.total_companies} компаний с данными`);
  return parts.join(" · ");
});

// ───────────────────────────────────────────────────────────────
//   Derived: rows
// ───────────────────────────────────────────────────────────────

/** Use legacy score (0..1200) when present, otherwise fall back to computed (0..100). */
function rowScore(r: GovernanceCompanyScore): number | null {
  return r.governance_score_1200 ?? r.governance_score;
}

// ───────────────────────────────────────────────────────────────
//   Color helpers — legacy thresholds (on 0..1200 scale)
// ───────────────────────────────────────────────────────────────

function scoreColor(s: number | null): string {
  if (s == null) return "#888780";
  if (s >= 900) return "#1D9E75";
  if (s >= 700) return "#378ADD";
  if (s >= 600) return "#EF9F27";
  return "#E24B4A";
}
function meetColor(n: number | null): string {
  if (n == null) return "#888780";
  if (n >= 15) return "#7F77DD";
  if (n >= 8)  return "#378ADD";
  return "#E24B4A";
}
function fallbackSectorColor(r: GovernanceCompanyScore): string {
  return r.sector_color || "#888780";
}

// ───────────────────────────────────────────────────────────────
//   KPI strip totals (legacy showGovView lines 35156-35167)
// ───────────────────────────────────────────────────────────────

const totals = computed(() => {
  const rows = overview.value?.rankings ?? [];
  const scores = rows.map(rowScore).filter((v): v is number => v != null);
  const avgScore = scores.length ? Math.round(scores.reduce((s, v) => s + v, 0) / scores.length) : 0;

  const totalMembers = rows.reduce((s, r) => s + (r.board_size ?? 0), 0);
  const totalIndep   = rows.reduce((s, r) => s + (r.independent_count ?? 0), 0);
  const totalVacant  = rows.reduce((s, r) => s + (r.vacant_seats ?? 0), 0);
  const vacantCos    = rows.filter(r => (r.vacant_seats ?? 0) > 0).length;
  const totalWomen   = rows.reduce((s, r) => s + (r.women_count ?? 0), 0);
  const dnoCount     = rows.filter(r => !!r.has_dno_insurance).length;
  const cosCount     = rows.length;
  const weightedWomenPct = totalMembers > 0 ? Math.round(totalWomen / totalMembers * 100) : 0;
  const indepPct = totalMembers > 0 ? Math.round(totalIndep / totalMembers * 100) : 0;

  // Заседания НС — суммарно и в среднем на компанию (по компаниям с данными).
  const meetingCos    = rows.filter(r => (r.meetings_per_year ?? 0) > 0).length;
  const totalMeetings = rows.reduce((s, r) => s + (r.meetings_per_year ?? 0), 0);
  const avgMeetings   = meetingCos > 0 ? Math.round(totalMeetings / meetingCos) : 0;

  return {
    avgScore, totalMembers, totalIndep, totalVacant, vacantCos,
    totalWomen, dnoCount, cosCount, weightedWomenPct, indepPct,
    meetingCos, totalMeetings, avgMeetings,
  };
});

// ───────────────────────────────────────────────────────────────
//   Matrix sort (legacy _govMatFilter)
// ───────────────────────────────────────────────────────────────

function matrixField(r: GovernanceCompanyScore, c: MatrixCol): number | null {
  switch (c) {
    case "score":    return rowScore(r);
    case "members":  return r.board_size;
    case "indep":    return r.independent_count;
    case "meetings": return r.meetings_per_year;
    case "women":    return r.women_count;
    case "age":      return r.age_avg;
  }
}

const matrixRows = computed(() => {
  const rows = [...(overview.value?.rankings ?? [])];
  if (!matrixSort.value) {
    rows.sort((a, b) => (rowScore(b) ?? -1) - (rowScore(a) ?? -1));
    return rows;
  }
  const col = matrixSort.value;
  const dir = matrixDir.value;
  rows.sort((a, b) => {
    const va = matrixField(a, col);
    const vb = matrixField(b, col);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va - vb) * dir;
  });
  return rows;
});

function setMatrixSort(c: MatrixCol) {
  if (matrixSort.value === c) {
    matrixDir.value = (matrixDir.value * -1) as -1 | 1;
  } else {
    matrixSort.value = c;
    matrixDir.value = -1;
  }
}
function clearMatrixSort() {
  matrixSort.value = null;
  matrixDir.value = -1;
}
function sortIcon(c: MatrixCol): string {
  if (matrixSort.value !== c) return "▼";
  return matrixDir.value === -1 ? "▼" : "▲";
}

// ───────────────────────────────────────────────────────────────
//   Комитеты при НС — КОЛИЧЕСТВО заседаний по периодам
// ───────────────────────────────────────────────────────────────

// 4 столбца-комитета: подпись → поле в ячейке.
// Колонки наблюдательного совета (заседания + решения) — идут первыми.
const SB_COLS: { key: CommitteeMeetingField; label: string }[] = [
  { key: "sb_meetings",  label: "Заседания НС" },
  { key: "sb_decisions", label: "Количество решений, принятых по итогам заседания и оформленных протоколом" },
];
const COMMITTEE_COLS: { key: CommitteeMeetingField; label: string }[] = [
  { key: "audit_mtg",    label: "Аудит" },
  { key: "strategy_mtg", label: "Стратегия" },
  { key: "anticorr_mtg", label: "Антикор." },
  { key: "nomrem_mtg",   label: "Комитет по назначениям и вознаграждениям" },
];
// Все колонки таблицы: НС → комитеты.
const ALL_CM_COLS = [...SB_COLS, ...COMMITTEE_COLS];

const committeeData = ref<CommitteeMeetingsResponse | null>(null);
const committeeLoading = ref(false);
const committeeError = ref<string | null>(null);

// Локально добавленные (ещё пустые) периоды — живут в state до первого PUT.
const localPeriods = ref<CommitteeMeetingPeriod[]>([]);

// Ключ активного периода ("<year>:<quarter|0>").
const activeCommitteeKey = ref<string>("");

// Inline-picker нового периода.
const periodPickerOpen = ref(false);
const pickerYear = ref<number>(new Date().getFullYear());
const pickerQuarter = ref<string>("0"); // "0" = годовой, "1".."4" = квартал

// Закрытие пикера «+ период» по Escape и клику вне него.
const periodAddwrapEl = ref<HTMLElement | null>(null);
function onPickerDocClick(e: MouseEvent) {
  if (!periodPickerOpen.value) return;
  const el = periodAddwrapEl.value;
  if (el && !el.contains(e.target as Node)) periodPickerOpen.value = false;
}
function onPickerDocKey(e: KeyboardEvent) {
  if (e.key === "Escape" && periodPickerOpen.value) periodPickerOpen.value = false;
}
watch(periodPickerOpen, (open) => {
  if (open) {
    document.addEventListener("click", onPickerDocClick, true);
    document.addEventListener("keydown", onPickerDocKey);
  } else {
    document.removeEventListener("click", onPickerDocClick, true);
    document.removeEventListener("keydown", onPickerDocKey);
  }
});
onBeforeUnmount(() => {
  document.removeEventListener("click", onPickerDocClick, true);
  document.removeEventListener("keydown", onPickerDocKey);
});

// Inline-редактирование ячейки.
const editingCell = ref<string | null>(null); // "<company_id>:<field>"
const editValue = ref<string>("");
// Пульс-подсветка после успешного сохранения.
const savedPulse = ref<string | null>(null);   // "<company_id>:<field>"

function periodKey(p: { year: number; quarter: number | null }): string {
  return `${p.year}:${p.quarter || 0}`;
}

function committeeSectorColor(sectorCode: string | null): string {
  if (!sectorCode) return "#888780";
  const sec = companiesStore.findSectorByCode(sectorCode);
  return sec?.color_hex || "#888780";
}

const canEditCommittees = computed(() => companiesPerm.canEdit.value);

// Все периоды: с бэка (есть строки/дефолтные) ∪ локально добавленные.
const committeePeriods = computed<CommitteeMeetingPeriod[]>(() => {
  const map = new Map<string, CommitteeMeetingPeriod>();
  for (const p of committeeData.value?.periods ?? []) map.set(periodKey(p), p);
  for (const p of localPeriods.value) {
    const k = periodKey(p);
    if (!map.has(k)) map.set(k, p);
  }
  return [...map.values()].sort(
    (a, b) => a.year - b.year || (a.quarter || 0) - (b.quarter || 0),
  );
});

const activePeriod = computed<CommitteeMeetingPeriod | null>(() => {
  const list = committeePeriods.value;
  if (!list.length) return null;
  return list.find((p) => periodKey(p) === activeCommitteeKey.value) || list[list.length - 1];
});

// Строки таблицы (по названию) — все компании портфеля.
const committeeRows = computed(() => {
  const rows = [...(committeeData.value?.companies ?? [])];
  rows.sort((a, b) =>
    (a.name || a.name_short || "").localeCompare(b.name || b.name_short || "", "ru"),
  );
  return rows;
});

/** Значение ячейки одного комитета за активный период (или null). */
function committeeCellValue(companyId: string, field: CommitteeMeetingField): number | null {
  const p = activePeriod.value;
  if (!p) return null;
  const row = committeeData.value?.companies.find((c) => c.company_id === companyId);
  const cell = row?.cells[periodKey(p)];
  const v = cell?.[field];
  return v == null ? null : v;
}

// Σ заседаний 4 комитетов по всем компаниям за активный период.
const committeeSum = computed<number>(() => {
  const p = activePeriod.value;
  if (!p) return 0;
  let sum = 0;
  for (const c of committeeData.value?.companies ?? []) {
    const cell = c.cells[periodKey(p)];
    if (!cell) continue;
    for (const col of COMMITTEE_COLS) sum += cell[col.key] ?? 0;
  }
  return sum;
});

async function loadCommittees() {
  committeeLoading.value = true;
  committeeError.value = null;
  try {
    const data = await governanceApi.getCommitteeMeetings();
    committeeData.value = data;
    // Активный период по умолчанию — последний доступный.
    if (!activeCommitteeKey.value && committeePeriods.value.length) {
      const list = committeePeriods.value;
      activeCommitteeKey.value = periodKey(list[list.length - 1]);
    }
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    committeeError.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить комитеты";
  } finally {
    committeeLoading.value = false;
  }
}

function selectPeriod(p: CommitteeMeetingPeriod) {
  activeCommitteeKey.value = periodKey(p);
  cancelEdit();
}

async function addPeriod() {
  const year = Math.trunc(Number(pickerYear.value));
  if (!year || year < 2000 || year > 2100) {
    toast.error("Укажите корректный год (2000–2100)");
    return;
  }
  const q = pickerQuarter.value === "0" ? null : Number(pickerQuarter.value);
  const newP: CommitteeMeetingPeriod = {
    year,
    quarter: q,
    label: q ? `${year} · Q${q}` : `${year}`,
  };
  const k = periodKey(newP);
  if (committeePeriods.value.some((p) => periodKey(p) === k)) {
    toast.info("Такой период уже есть");
    activeCommitteeKey.value = k;
    periodPickerOpen.value = false;
    return;
  }
  try {
    await governanceApi.addCommitteePeriod(year, q);
  } catch {
    // Бэкенд только валидирует — провал не критичен, период добавляем локально.
  }
  localPeriods.value = [...localPeriods.value, newP];
  activeCommitteeKey.value = k;
  periodPickerOpen.value = false;
}

function cellEditKey(companyId: string, field: CommitteeMeetingField): string {
  return `${companyId}:${field}`;
}

function startEdit(companyId: string, field: CommitteeMeetingField) {
  if (!canEditCommittees.value) return;
  const v = committeeCellValue(companyId, field);
  editingCell.value = cellEditKey(companyId, field);
  editValue.value = v == null ? "" : String(v);
  nextTick(() => {
    const el = document.querySelector<HTMLInputElement>(".gv-cell-input");
    el?.focus();
    el?.select();
  });
}

function cancelEdit() {
  editingCell.value = null;
  editValue.value = "";
}

async function commitEdit(companyId: string, field: CommitteeMeetingField) {
  const key = cellEditKey(companyId, field);
  // Только если редактируем именно эту ячейку (защита от двойного коммита).
  if (editingCell.value !== key) return;

  const p = activePeriod.value;
  if (!p) { cancelEdit(); return; }

  const raw = editValue.value.trim();
  const newVal: number | null = raw === "" ? null : Math.max(0, Math.trunc(Number(raw)));
  const oldVal = committeeCellValue(companyId, field);

  // Закрываем edit-mode ДО async-сохранения.
  cancelEdit();

  if (raw !== "" && Number.isNaN(newVal as number)) {
    toast.error("Не сохранено: введите число");
    return;
  }
  if (newVal === oldVal) return; // без изменений

  // Оптимистично обновляем ячейку.
  setCellLocal(companyId, p, field, newVal);

  try {
    await governanceApi.putCommitteeMeeting({
      company_id: companyId,
      year: p.year,
      quarter: p.quarter,
      field,
      value: newVal,
    });
    toast.success("Сохранено");
    // Пульс-подсветка.
    savedPulse.value = key;
    setTimeout(() => { if (savedPulse.value === key) savedPulse.value = null; }, 900);
  } catch (e: unknown) {
    // Откат при ошибке.
    setCellLocal(companyId, p, field, oldVal);
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error(`Не сохранено: ${err?.response?.data?.detail || err?.message || "ошибка сети"}`);
  }
}

/** Записать значение в локальный кэш ответа (оптимистично/откат). */
function setCellLocal(
  companyId: string,
  p: CommitteeMeetingPeriod,
  field: CommitteeMeetingField,
  value: number | null,
) {
  const data = committeeData.value;
  if (!data) return;
  const row = data.companies.find((c) => c.company_id === companyId);
  if (!row) return;
  const k = periodKey(p);
  const cell = row.cells[k] ?? {
    sb_meetings: null, sb_decisions: null,
    audit_mtg: null, strategy_mtg: null, nomrem_mtg: null, anticorr_mtg: null,
  };
  cell[field] = value;
  row.cells[k] = cell;
}

// ───────────────────────────────────────────────────────────────
//   KPI drill rows (legacy _govKpiDetail)
// ───────────────────────────────────────────────────────────────

interface DrillRow {
  r: GovernanceCompanyScore;
  primary: string;       // big value (e.g. "685")
  primaryColor: string;
  secondary: string;     // small note (e.g. "/ 1200")
}

const kpiDrillTitle = computed<string>(() => {
  switch (kpiDrill.value) {
    case "score":   return "Оценка корпоративного управления";
    case "indep":   return "Независимые директора";
    case "members": return "Состав наблюдательных советов";
    case "meetings": return "Заседания наблюдательного совета";
    case "vacant":  return "Вакантные позиции в НС";
    case "women":   return "Женщины в наблюдательных советах";
    case "dno":     return "Страхование D&O";
    default:        return "";
  }
});

const kpiDrillRows = computed<DrillRow[]>(() => {
  if (!kpiDrill.value) return [];
  const rows = [...(overview.value?.rankings ?? [])];
  switch (kpiDrill.value) {
    case "score": {
      rows.sort((a, b) => (rowScore(b) ?? -1) - (rowScore(a) ?? -1));
      return rows.map(r => {
        const s = rowScore(r);
        return { r, primary: s != null ? String(s) : "—", primaryColor: scoreColor(s), secondary: "/ 1200" };
      });
    }
    case "indep": {
      rows.sort((a, b) => {
        const ap = a.board_size ? (a.independent_count ?? 0) / a.board_size : 0;
        const bp = b.board_size ? (b.independent_count ?? 0) / b.board_size : 0;
        return bp - ap;
      });
      return rows.map(r => {
        const i = r.independent_count ?? 0;
        const bs = r.board_size ?? 0;
        const pct = bs ? Math.round((i / bs) * 100) : 0;
        return {
          r,
          primary: String(i),
          primaryColor: i === 0 ? "#E24B4A" : "#1E2A4A",
          secondary: `из ${bs} (${pct}%)`,
        };
      });
    }
    case "members": {
      rows.sort((a, b) => (b.board_size ?? 0) - (a.board_size ?? 0));
      return rows.map(r => ({
        r,
        primary: String(r.board_size ?? 0),
        primaryColor: "#1E2A4A",
        secondary: `${r.independent_count ?? 0} независимых / ${r.nonexec_count ?? r.board_size ?? 0} неисполнительных`,
      }));
    }
    case "meetings": {
      rows.sort((a, b) => (b.meetings_per_year ?? 0) - (a.meetings_per_year ?? 0));
      return rows.map(r => ({
        r,
        primary: r.meetings_per_year != null ? String(r.meetings_per_year) : "—",
        primaryColor: meetColor(r.meetings_per_year),
        secondary: "заседаний за год",
      }));
    }
    case "vacant": {
      const f = rows.filter(r => (r.vacant_seats ?? 0) > 0)
        .sort((a, b) => (b.vacant_seats ?? 0) - (a.vacant_seats ?? 0));
      return f.map(r => ({
        r,
        primary: String(r.vacant_seats ?? 0),
        primaryColor: "#E24B4A",
        secondary: `из ${r.board_size ?? 0} позиций`,
      }));
    }
    case "women": {
      rows.sort((a, b) => (b.women_count ?? 0) - (a.women_count ?? 0));
      return rows.map(r => {
        const w = r.women_count ?? 0;
        const bs = r.board_size ?? 0;
        const pct = bs ? Math.round((w / bs) * 100) : 0;
        return {
          r,
          primary: String(w),
          primaryColor: w > 0 ? "#EF9F27" : "#888780",
          secondary: bs ? `из ${bs} (${pct}%)` : "—",
        };
      });
    }
    case "dno": {
      const f = rows.filter(r => !!r.has_dno_insurance)
        .sort((a, b) => (a.company_name ?? a.company_code).localeCompare(b.company_name ?? b.company_code, "ru"));
      return f.map(r => ({ r, primary: "✓", primaryColor: "#1D9E75", secondary: "застрахован" }));
    }
  }
  return [];
});

// ───────────────────────────────────────────────────────────────
//   Lifecycle
// ───────────────────────────────────────────────────────────────

onMounted(() => { load(); loadCommittees(); void companiesStore.ensureLoaded(); });
</script>

<template>
  <!-- 2026-05-26: убран outer <Transition mode=out-in> + :key=year. -->
  <div class="gv-view">

        <!-- ═══ Topbar (dark navy, легаси dash-topbar) ═══ -->
        <div class="gv-topbar">
          <SidebarBurger />
          <div class="gv-tb-l">
            <h1 class="gv-tb-title">Корпоративное управление</h1>
            <span class="gv-tb-sub">UzAssets Corp Management · {{ headerSub }}</span>
          </div>
          <div class="gv-tb-r">
            <select :value="String(year || '')" @change="onYearChange" class="gv-in">
              <option value="">Все годы</option>
              <option v-for="y in (overview?.available_years || [])" :key="y" :value="y">{{ y }}</option>
            </select>
            <select :value="sectorCode || ''" @change="onSectorChange" class="gv-in">
              <option value="">Все сектора</option>
              <option v-for="s in (overview?.sectors || [])" :key="s.code" :value="s.code">
                {{ companiesStore.getSectorName(s.code) }} ({{ s.count }})
              </option>
            </select>

            <!-- Действия редактирования вынесены в карточку компании (кнопка
                 «Редактировать» в детальной модалке) — верхнее ⋮-меню убрано. -->
          </div>
        </div>

        <!-- ═══ Body / scroll container ═══ -->
        <UzaStateBlock v-if="loading && !overview" state="loading" variant="text" text="Загрузка..." />
        <UzaStateBlock v-else-if="error && !overview" state="error" variant="block" :text="error" />
        <div v-else-if="overview" ref="scanRoot" class="dash-scroll gv-body">

          <!-- ═══ 1. KPI strip — 7 cells ═══ -->
          <div class="kpi-row gv-kpi-row kpi-rail">

            <!-- 1. Средний балл -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#7F77DD; --kpi2-d: 0ms" @click="kpiDrill = 'score'">
              <div class="kpi2-lbl">Средний балл</div>
              <div class="kpi2-val">
                <span :data-countup="totals.avgScore">{{ totals.avgScore }}</span>
                <span class="unit"> / 1200</span>
              </div>
              <div class="kpi2-sub">Оценка корпоративного управления</div>
            </div>

            <!-- 2. Заседания НС -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#6E66D6; --kpi2-d: 80ms" @click="kpiDrill = 'meetings'">
              <div class="kpi2-lbl">Заседания НС<template v-if="year"> {{ year }}</template></div>
              <div class="kpi2-val">
                <span :data-countup="totals.totalMeetings">{{ totals.totalMeetings }}</span>
              </div>
              <div class="kpi2-sub">ср. {{ totals.avgMeetings }} на компанию · {{ totals.meetingCos }} комп.</div>
            </div>

            <!-- 3. Независимые директора % -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#1D9E75; --kpi2-d: 160ms" @click="kpiDrill = 'indep'">
              <div class="kpi2-lbl">Независимые директора</div>
              <div class="kpi2-val">
                <span :data-countup="totals.indepPct">{{ totals.indepPct }}</span><span class="unit-pct">%</span>
              </div>
              <div class="kpi2-sub">{{ totals.totalIndep }} из {{ totals.totalMembers }} членов НС</div>
            </div>

            <!-- 4. Всего членов НС -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#378ADD; --kpi2-d: 240ms" @click="kpiDrill = 'members'">
              <div class="kpi2-lbl">Всего членов НС</div>
              <div class="kpi2-val">
                <span :data-countup="totals.totalMembers">{{ totals.totalMembers }}</span>
              </div>
              <div class="kpi2-sub">{{ totals.cosCount }} компаний</div>
            </div>

            <!-- 5. Вакансии -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#E24B4A; --kpi2-d: 320ms" @click="kpiDrill = 'vacant'">
              <div class="kpi2-lbl">Вакансии</div>
              <div class="kpi2-val" style="color:#E24B4A">
                <span :data-countup="totals.totalVacant">{{ totals.totalVacant }}</span>
              </div>
              <div class="kpi2-sub">в {{ totals.vacantCos }} компаниях</div>
            </div>

            <!-- 6. Женщины в НС -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#EF9F27; --kpi2-d: 400ms" @click="kpiDrill = 'women'">
              <div class="kpi2-lbl">Женщины в НС</div>
              <div class="kpi2-val" style="color:#EF9F27">
                <span :data-countup="totals.weightedWomenPct">{{ totals.weightedWomenPct }}</span><span class="unit-pct">%</span>
              </div>
              <div class="kpi2-sub">{{ totals.totalWomen }} из {{ totals.totalMembers }} членов НС</div>
            </div>

            <!-- 7. Страхование D&O -->
            <div class="kpi2 fin-shimmer gv-kpi" style="--kpi2-accent:#378ADD; --kpi2-d: 480ms" @click="kpiDrill = 'dno'">
              <div class="kpi2-lbl">Страхование D&amp;O</div>
              <div class="kpi2-val">
                <span :data-countup="totals.dnoCount">{{ totals.dnoCount }}</span>
                <span class="unit"> / {{ totals.cosCount }}</span>
              </div>
              <div class="kpi2-sub">компаний со страховкой</div>
            </div>
          </div>

          <!-- ═══ 2. Bottom grid: Composition matrix + Committees ═══ -->
          <div class="gv-bot-grid">

            <!-- LEFT: Composition matrix -->
            <div class="gv-cc gv-matrix" style="--d:600ms" :class="{ 'gv-zoomed': zoomed === 'matrix' }">
              <div class="gv-cc-h">
                <span class="gv-cc-t">Состав наблюдательных советов</span>
                <div class="gv-cc-rt">
                  <button
                    v-if="matrixSort"
                    class="gv-mat-clear"
                    @click="clearMatrixSort()"
                  >× сбросить</button>
                  <button class="gv-zoom-btn" @click="zoomed = zoomed === 'matrix' ? null : 'matrix'" title="Zoom">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>
              <div class="gv-mat-wrap">
                <table class="gv-mat-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th @click="setMatrixSort('score')" class="sortable" :class="{ on: matrixSort === 'score' }">
                        Балл <span class="arr">{{ sortIcon('score') }}</span>
                      </th>
                      <th @click="setMatrixSort('members')" class="sortable" :class="{ on: matrixSort === 'members' }">
                        Члены <span class="arr">{{ sortIcon('members') }}</span>
                      </th>
                      <th @click="setMatrixSort('indep')" class="sortable" :class="{ on: matrixSort === 'indep' }">
                        Независимые <span class="arr">{{ sortIcon('indep') }}</span>
                      </th>
                      <th @click="setMatrixSort('meetings')" class="sortable" :class="{ on: matrixSort === 'meetings' }">
                        Заседания <span class="arr">{{ sortIcon('meetings') }}</span>
                      </th>
                      <th @click="setMatrixSort('women')" class="sortable" :class="{ on: matrixSort === 'women' }">
                        Женщины <span class="arr">{{ sortIcon('women') }}</span>
                      </th>
                      <th @click="setMatrixSort('age')" class="sortable" :class="{ on: matrixSort === 'age' }">
                        Средний возраст <span class="arr">{{ sortIcon('age') }}</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(r, i) in matrixRows"
                      :key="r.company_id"
                      :style="{ animationDelay: (Math.min(i, 30) * 20) + 'ms' }"
                      @click="openDetail(r.company_id)"
                    >
                      <td class="lt">
                        <span class="gv-mat-sec" :style="{ background: fallbackSectorColor(r) }"></span>
                        <span class="gv-mat-name">{{ r.company_name || r.company_abbr || r.company_code }}</span>
                      </td>
                      <td class="num" :style="{ color: scoreColor(rowScore(r)), fontWeight: 600 }">
                        {{ rowScore(r) ?? "—" }}
                      </td>
                      <td class="num">{{ r.board_size ?? "—" }}</td>
                      <td class="num" :style="{
                        color: (r.independent_count ?? 0) === 0 ? '#E24B4A'
                               : (r.independent_count ?? 0) >= 3 ? '#1D9E75' : '#888780',
                        fontWeight: 500
                      }">{{ r.independent_count ?? "—" }}</td>
                      <td class="num" :style="{
                        color: (r.meetings_per_year ?? 99) <= 5 ? '#E24B4A' : '#888780',
                        fontWeight: 500
                      }">{{ r.meetings_per_year ?? "—" }}</td>
                      <td class="num" :style="{ color: (r.women_count ?? 0) > 0 ? '#1D9E75' : '#888780' }">
                        <template v-if="(r.women_count ?? 0) > 0">
                          {{ r.women_count }}
                          <span class="gv-mat-pct">({{ r.women_pct != null ? Math.round(r.women_pct) : 0 }}%)</span>
                        </template>
                        <span v-else>—</span>
                      </td>
                      <td class="num">
                        <template v-if="r.age_avg != null">
                          {{ r.age_avg }}<span class="gv-mat-pct">лет</span>
                        </template>
                        <span v-else>—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div class="gv-mat-legend">
                <span><span class="dot" style="background:#1D9E75"></span> Более 900</span>
                <span><span class="dot" style="background:#378ADD"></span> 700-900</span>
                <span><span class="dot" style="background:#EF9F27"></span> 600-700</span>
                <span><span class="dot" style="background:#E24B4A"></span> Менее 600</span>
              </div>
            </div>

            <!-- RIGHT: Committees — кол-во заседаний по периодам -->
            <div class="gv-cc gv-committees" style="--d:650ms" :class="{ 'gv-zoomed': zoomed === 'committees' }">
              <div class="gv-cc-h">
                <span class="gv-cc-t">Информация о заседаниях, проведённых Наблюдательным советом и комитетами</span>
                <div class="gv-cc-rt">
                  <button class="gv-zoom-btn" @click="zoomed = zoomed === 'committees' ? null : 'committees'" title="Zoom">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                      <path d="M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4"
                        stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
                    </svg>
                  </button>
                </div>
              </div>

              <!-- Чипы периодов + добавление -->
              <div class="gv-cm-periods">
                <button
                  v-for="p in committeePeriods"
                  :key="`${p.year}:${p.quarter || 0}`"
                  class="gv-cm-chip"
                  :class="{ on: activePeriod && (activePeriod.year === p.year && (activePeriod.quarter || 0) === (p.quarter || 0)) }"
                  @click="selectPeriod(p)"
                >{{ p.label }}</button>

                <div class="gv-cm-addwrap" ref="periodAddwrapEl">
                  <button
                    v-if="canEditCommittees"
                    class="gv-cm-chip gv-cm-add"
                    :class="{ on: periodPickerOpen }"
                    @click="periodPickerOpen = !periodPickerOpen"
                  >+ период</button>
                  <Transition name="uza-fade">
                    <div v-if="periodPickerOpen" class="gv-cm-picker" @click.stop>
                      <input
                        v-model="pickerYear"
                        type="number" min="2000" max="2100"
                        class="gv-cm-pin" placeholder="Год"
                      />
                      <select v-model="pickerQuarter" class="gv-cm-psel">
                        <option value="0">Год</option>
                        <option value="1">Q1</option>
                        <option value="2">Q2</option>
                        <option value="3">Q3</option>
                        <option value="4">Q4</option>
                      </select>
                      <button class="gv-cm-pbtn" @click="addPeriod">Добавить</button>
                    </div>
                  </Transition>
                </div>
              </div>

              <UzaStateBlock v-if="committeeLoading && !committeeData" state="loading" variant="text" text="Загрузка..." />
              <UzaStateBlock v-else-if="committeeError && !committeeData" state="error" variant="block" :text="committeeError" />

              <div v-else class="gv-mat-wrap">
                <table class="gv-mat-tbl gv-cm-tbl">
                  <thead>
                    <tr>
                      <th class="lt">Компания</th>
                      <th v-for="col in ALL_CM_COLS" :key="col.key" :title="col.label" :class="{ 'gv-cm-sep': col.key === 'audit_mtg' }">{{ col.label }}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(r, i) in committeeRows"
                      :key="r.company_id"
                      :style="{ animationDelay: (Math.min(i, 30) * 20) + 'ms' }"
                    >
                      <td class="lt" @click="openDetail(r.company_id)">
                        <span class="gv-mat-sec" :style="{ background: committeeSectorColor(r.sector_code) }"></span>
                        <span class="gv-mat-name">{{ r.name || r.name_short || '—' }}</span>
                      </td>
                      <td
                        v-for="col in ALL_CM_COLS"
                        :key="col.key"
                        class="num gv-cm-cell"
                        :class="{
                          editable: canEditCommittees,
                          editing: editingCell === `${r.company_id}:${col.key}`,
                          pulse: savedPulse === `${r.company_id}:${col.key}`,
                          'gv-cm-sep': col.key === 'audit_mtg',
                        }"
                        @click="startEdit(r.company_id, col.key)"
                      >
                        <input
                          v-if="editingCell === `${r.company_id}:${col.key}`"
                          v-model="editValue"
                          type="number" min="0"
                          class="gv-cell-input"
                          @click.stop
                          @keydown.enter.prevent="commitEdit(r.company_id, col.key)"
                          @keydown.esc.prevent="cancelEdit"
                          @blur="commitEdit(r.company_id, col.key)"
                        />
                        <template v-else>
                          <span v-if="committeeCellValue(r.company_id, col.key) != null" class="gv-cm-num">
                            {{ committeeCellValue(r.company_id, col.key) }}
                          </span>
                          <span v-else class="gv-cm-empty">—</span>
                        </template>
                      </td>
                    </tr>
                    <tr v-if="!committeeRows.length">
                      <td :colspan="ALL_CM_COLS.length + 1" class="empty">Нет компаний</td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="gv-mat-legend">
                <span v-if="canEditCommittees" class="gv-cm-hint">Клик по ячейке — правка количества заседаний</span>
                <span class="gv-mat-legend-meta">
                  Σ заседаний комитетов за {{ activePeriod ? activePeriod.label : '—' }}: <b>{{ committeeSum }}</b>
                </span>
              </div>
            </div>

          </div>

        </div>

        <!-- ═══ KPI drill modal (legacy _govKpiDetail) ═══ -->
        <Transition name="uza-fade">
          <div v-if="kpiDrill" class="gv-modal-bg" @click.self="kpiDrill = null">
            <div class="gv-modal-card">
              <div class="gv-modal-h">
                <div>
                  <div class="gv-modal-t">{{ kpiDrillTitle }}</div>
                  <div class="gv-modal-s">{{ kpiDrillRows.length }} {{ kpiDrillRows.length === 1 ? 'компания' : 'компаний' }}</div>
                </div>
                <button class="gv-modal-x" @click="kpiDrill = null">✕</button>
              </div>
              <div class="gv-modal-body">
                <table class="gv-modal-tbl">
                  <tbody>
                    <tr
                      v-for="row in kpiDrillRows"
                      :key="row.r.company_id"
                      @click="kpiDrill = null; openDetail(row.r.company_id);"
                    >
                      <td class="lt">
                        <span class="gv-mat-sec" :style="{ background: fallbackSectorColor(row.r) }"></span>
                        {{ row.r.company_name || row.r.company_abbr || row.r.company_code }}
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

        <!-- Per-company drill modal (existing component) -->
        <GovCompanyDetailModal
          v-if="drillCompanyId"
          :company-id="drillCompanyId"
          :year="year ?? undefined"
          @close="drillCompanyId = null"
          @saved="onDetailSaved"
        />
      </div>
</template>

<style scoped>
.gv-view { background: var(--bg, #F4F3F9); min-height: 100%; font-family: var(--font, system-ui); }

/* ─── Local keyframes (mirror legacy finKpiIn / fadeSlideIn) ─── */
@keyframes finKpiIn {
  0% { opacity: 0; transform: translateY(12px) scale(.97); }
  60% { opacity: 1; transform: translateY(-2px) scale(1.01); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes fadeSlideIn {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes gvBarGrow {
  0% { width: 0; }
  100% { /* width controlled inline */ }
}

/* ─── Topbar (1:1 legacy dash-topbar) ─── */
.gv-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 12px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
}
.gv-tb-l { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.gv-tb-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; letter-spacing: -.005em; }
.gv-tb-sub { font-size: 11px; color: rgba(255, 255, 255, .55); font-weight: 500; }
.gv-tb-r { display: flex; gap: 8px; align-items: center; position: relative; }
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

/* Верхнее ⋮-меню удалено — редактирование через карточку компании. */

/* ─── Body / dash-scroll surrogate ─── */
.gv-body { padding: 16px 20px; }

/* ─── KPI strip (overrides on the global .kpi-row / .kpi2) ─── */
.gv-kpi-row { grid-template-columns: repeat(7, minmax(0, 1fr)); margin-bottom: 12px; }
@media (max-width: 1280px) { .gv-kpi-row { grid-template-columns: repeat(4, 1fr); } }
@media (max-width: 720px)  { .gv-kpi-row { grid-template-columns: repeat(2, 1fr); } }
.gv-kpi {
  cursor: pointer;
  animation: kpiCardIn .5s var(--ease-standard) var(--kpi2-d, 0ms) both;
  transition: transform .15s, box-shadow .15s;
}
.gv-kpi:hover { transform: translateY(-1px); }
.kpi2-val .unit { font-size: 14px; color: var(--t3, var(--t-muted)); margin-left: 4px; font-weight: 400; }
.kpi2-val .unit-pct { font-size: 16px; color: var(--t3, var(--t-muted)); font-weight: 400; margin-left: 2px; }

/* ─── Cards (cc surrogate) ─── */
.gv-cc {
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px;
  overflow: hidden;
  display: flex; flex-direction: column;
  animation: finKpiIn .5s var(--ease-standard) var(--d, 0ms) both;
}
.gv-cc-h {
  padding: 10px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
  flex-shrink: 0;
}
.gv-cc-t {
  font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A);
  text-transform: uppercase; letter-spacing: .06em;
}
.gv-cc-rt { display: flex; align-items: center; gap: 8px; }
.gv-cc-meta { font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.gv-zoom-btn {
  background: transparent; border: 0;
  width: 24px; height: 24px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  transition: background .15s, color .15s;
}
.gv-zoom-btn:hover { background: #F4F3F9; color: var(--t1, #1E2A4A); }
.gv-mat-clear {
  background: #F4F3F9;
  border: 0.5px solid rgba(0, 0, 0, .08);
  color: var(--t3, #5F5E5A);
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
}
.gv-mat-clear:hover { background: rgba(127, 119, 221, .1); color: var(--p-deep); }

/* Zoom-card overlay */
.gv-zoomed {
  position: fixed !important;
  inset: 24px;
  z-index: 200;
  background: var(--bg1, #fff);
  box-shadow: 0 24px 64px rgba(15, 23, 60, .25);
  overflow: hidden;
}
.gv-zoomed .gv-rating-body,
.gv-zoomed .gv-tab-body,
.gv-zoomed .gv-mat-wrap { flex: 1; }

/* ─── Mid-grid layout ─── */
.gv-mid-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  margin-bottom: 12px;
  min-height: 520px;
}
.gv-rating, .gv-tabbed { min-height: 520px; }
@media (max-width: 1100px) { .gv-mid-grid { grid-template-columns: 1fr; min-height: auto; } }

/* Rating bars body */
.gv-rating-body, .gv-tab-body {
  flex: 1; overflow-y: auto; scrollbar-width: thin;
}
.gv-rating-body::-webkit-scrollbar,
.gv-tab-body::-webkit-scrollbar { width: 6px; }
.gv-rating-body::-webkit-scrollbar-thumb,
.gv-tab-body::-webkit-scrollbar-thumb {
  background: rgba(127, 119, 221, .25); border-radius: 3px;
}

.gv-rt-row {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  animation: fadeSlideIn .25s ease both;
  transition: background .15s;
}
.gv-rt-row:hover { background: rgba(127, 119, 221, .04); }
.gv-rt-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  /* 2026-05-25: fixed width — раньше min/max + flex-shrink:0 давало
     плавающую ширину под контент → колонка score сдвигалась per row. */
  width: 220px;
  flex-shrink: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.gv-rt-score {
  font-size: 13px; font-weight: 600;
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
  transition: width .9s cubic-bezier(.22,.61,.36,1);
}

/* Tabbed (seg-ctrl surrogate) */
.gv-seg {
  display: inline-flex;
  background: rgba(0, 0, 0, .04);
  border-radius: 7px;
  padding: 2px;
}
.gv-seg button {
  background: transparent; border: 0;
  font-size: 12px; padding: 4px 12px;
  border-radius: 5px;
  color: var(--t3, var(--t-muted)); cursor: pointer;
  font-family: inherit; font-weight: 500;
  transition: all .15s;
}
.gv-seg button:hover { color: var(--t1, #1E2A4A); }
.gv-seg button.on {
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A);
  box-shadow: 0 1px 3px rgba(0, 0, 0, .08);
}

.gv-tab-row {
  display: grid;
  /* 2026-05-25: было `3px 170px 60px 1fr` (4 col), но в template только
     3 child'а — name попадал в 3px колонку → видна была одна буква.
     Убран лишний 3px, расширены первые две под имена и значения "X / Y". */
  grid-template-columns: 200px 70px 1fr;
  align-items: center; gap: 8px;
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  cursor: pointer;
  animation: fadeSlideIn .25s ease both;
  transition: background .15s;
}
.gv-tab-row:hover { background: rgba(127, 119, 221, .04); }
.gv-tab-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gv-tab-name.gv-zero { color: var(--sev-high); }
.gv-tab-val {
  font-size: 12px; font-weight: 500;
  /* 2026-05-25: было text-align:right → 2-digit знаменатель ("11")
     визуально сдвигал число влево относительно 1-digit ("7"). Left +
     tabular-nums даёт стабильную колонку, в которой все числители "X"
     стоят в одной вертикали. */
  text-align: left; font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* ─── Bottom grid (matrix + committees) ─── */
.gv-bot-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
}
@media (max-width: 1100px) { .gv-bot-grid { grid-template-columns: 1fr; } }

.gv-mat-wrap { flex: 1; overflow: auto; scrollbar-width: thin; }
.gv-mat-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.gv-mat-tbl thead {
  background: #FAFAFA;
  position: sticky; top: 0; z-index: 1;
}
.gv-mat-tbl thead th {
  padding: 8px 6px; text-align: center;
  font-size: 11px; font-weight: 600; color: var(--t3, var(--t-muted));
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
}
.gv-mat-tbl thead th.lt {
  text-align: left; padding-left: 12px; min-width: 120px;
}
.gv-mat-tbl thead th.sortable {
  cursor: pointer; user-select: none;
  transition: color .15s, background .15s;
}
.gv-mat-tbl thead th.sortable:hover { color: var(--t1, #1E2A4A); background: rgba(127, 119, 221, .05); }
.gv-mat-tbl thead th.sortable.on {
  background: #7F77DD; color: #fff;
}
.gv-mat-tbl thead th.sortable.on .arr { opacity: 1; }
.gv-mat-tbl thead th .arr { font-size: 8px; opacity: .4; margin-left: 3px; }

.gv-mat-tbl tbody td {
  padding: 6px 8px; text-align: center;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A);
}
.gv-mat-tbl tbody td.lt {
  text-align: left; padding-left: 12px;
  display: flex; align-items: center; gap: 8px;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gv-mat-tbl tbody td.num { text-align: center; font-size: 12px; }
.gv-mat-tbl tbody tr {
  cursor: pointer;
  animation: fadeSlideIn .25s ease both;
  transition: background .12s;
}
.gv-mat-tbl tbody tr:hover { background: rgba(127, 119, 221, .04); }

.gv-mat-sec {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; flex-shrink: 0;
}
.gv-mat-name {
  font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.gv-mat-pct {
  font-size: 10px; color: var(--t3, var(--t-muted)); font-weight: 500;
  margin-left: 2px;
}

.gv-mat-legend {
  padding: 6px 14px; display: flex; gap: 12px;
  font-size: 11px; color: var(--t3, var(--t-muted));
  border-top: 0.5px solid rgba(0, 0, 0, .06);
  flex-wrap: wrap;
}
.gv-mat-legend .dot {
  display: inline-block; width: 7px; height: 7px;
  border-radius: 50%; margin-right: 4px; vertical-align: middle;
}
.gv-mat-legend-meta { margin-left: auto; }

/* Committee checks (legacy ck()) */
.gv-ck {
  display: inline-block; width: 16px; height: 16px;
  line-height: 16px; text-align: center;
  font-size: 11px; font-weight: 600;
  border-radius: 4px;
  font-feature-settings: "tnum";
}
.gv-ck.yes { background: var(--green-l); color: var(--green); }
.gv-ck.no  { background: var(--red-l); color: #EF4444; }
.gv-ck.small { width: 14px; height: 14px; line-height: 14px; font-size: 10px; }

/* ─── Committee meetings — периоды (премиум-чипы) ─── */
.gv-cm-periods {
  display: flex; align-items: center; flex-wrap: wrap; gap: 7px;
  padding: 10px 14px 6px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
}
.gv-cm-chip {
  appearance: none; border: 1px solid rgba(127, 119, 221, .28);
  background: var(--bg1, #fff); color: var(--t2, #5B6478);
  font-size: 11.5px; font-weight: 600; letter-spacing: .01em;
  padding: 5px 12px; border-radius: 999px; cursor: pointer;
  transition: background .2s ease, color .2s ease, border-color .2s ease,
              box-shadow .2s ease, transform .14s cubic-bezier(.2, .8, .3, 1.2);
  white-space: nowrap;
}
.gv-cm-chip:hover { border-color: rgba(127, 119, 221, .55); color: var(--t1, #1E2A4A); transform: translateY(-1px); }
.gv-cm-chip.on {
  background: linear-gradient(95deg, #6E66D6 0%, #7F77DD 100%);
  border-color: transparent; color: #fff;
  box-shadow: 0 4px 12px rgba(127, 119, 221, .35);
}
.gv-cm-add { border-style: dashed; color: #7F77DD; }
.gv-cm-add.on { background: linear-gradient(95deg, #6E66D6 0%, #7F77DD 100%); color: #fff; border-style: solid; }

.gv-cm-addwrap { position: relative; display: inline-flex; }
.gv-cm-picker {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 30;
  display: flex; align-items: center; gap: 6px;
  background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .1); border-radius: 10px;
  padding: 8px; box-shadow: 0 10px 30px rgba(30, 42, 74, .18);
}
.gv-cm-pin {
  width: 72px; padding: 5px 8px; font-size: 12px;
  border: 1px solid rgba(0, 0, 0, .14); border-radius: 7px;
  font-feature-settings: "tnum"; color: var(--t1, #1E2A4A);
}
.gv-cm-psel {
  padding: 5px 8px; font-size: 12px;
  border: 1px solid rgba(0, 0, 0, .14); border-radius: 7px;
  color: var(--t1, #1E2A4A); background: var(--bg1, #fff);
}
.gv-cm-pbtn {
  appearance: none; border: none; cursor: pointer;
  background: #7F77DD; color: #fff; font-size: 12px; font-weight: 600;
  padding: 6px 12px; border-radius: 7px; transition: background .15s;
}
.gv-cm-pbtn:hover { background: #6E66D6; }

/* ─── Committee meetings — таблица счётчиков ─── */
.gv-cm-tbl tbody td.num { font-size: 13px; font-weight: 500; }
.gv-cm-cell { position: relative; transition: background .12s ease; }
.gv-cm-cell.editable { cursor: pointer; }
.gv-cm-cell.editable:hover { background: rgba(127, 119, 221, .08); box-shadow: inset 0 0 0 1px rgba(127, 119, 221, .25); }
.gv-cm-cell.editing { background: rgba(127, 119, 221, .06); }
.gv-cm-num { color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; }
.gv-cm-empty { color: var(--t3, var(--t-muted)); }
/* визуальный разделитель: НС (заседания/решения) | комитеты */
.gv-cm-tbl th.gv-cm-sep, .gv-cm-tbl td.gv-cm-sep { border-left: 1px solid rgba(127, 119, 221, .2); }
.gv-cm-cell.pulse { animation: gvCellPulse .85s ease; }
@keyframes gvCellPulse {
  0% { background: rgba(29, 158, 117, .42); }
  100% { background: transparent; }
}
.gv-cell-input {
  width: 56px; max-width: 100%;
  padding: 3px 6px; text-align: center;
  border: 1px solid #7F77DD; border-radius: 6px;
  font-size: 13px; font-weight: 600; font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A); background: var(--bg1, #fff);
  outline: none; box-shadow: 0 0 0 3px rgba(127, 119, 221, .18);
}
/* Без горизонтального скролла: фикс. раскладка 100%. ВАЖНО: матрица задаёт
   .gv-mat-tbl thead th{white-space:nowrap} и td.lt{overflow:hidden;…} с равной
   спец-ю — поэтому переопределяем ИМЕННО через thead th / tbody td.lt (иначе
   заголовки не переносились → наложение текста, а имена компаний обрезались). */
.gv-cm-tbl { table-layout: fixed; width: 100%; }
.gv-cm-tbl thead th { white-space: normal; word-break: break-word; vertical-align: bottom; line-height: 1.2; }
.gv-cm-tbl thead th:not(.lt) { font-size: 10px; }
.gv-cm-tbl tbody td.lt { max-width: none; overflow: visible; white-space: normal; }
.gv-cm-tbl tbody td.lt .gv-mat-name {
  white-space: normal; overflow: visible; text-overflow: clip; line-height: 1.22; min-width: 0; flex: 1;
}
.gv-cm-tbl th:nth-child(1), .gv-cm-tbl td:nth-child(1) { width: 17%; }
.gv-cm-tbl th:nth-child(2), .gv-cm-tbl td:nth-child(2) { width: 9%; }
.gv-cm-tbl th:nth-child(3), .gv-cm-tbl td:nth-child(3) { width: 23%; }
.gv-cm-tbl th:nth-child(4), .gv-cm-tbl td:nth-child(4),
.gv-cm-tbl th:nth-child(5), .gv-cm-tbl td:nth-child(5),
.gv-cm-tbl th:nth-child(6), .gv-cm-tbl td:nth-child(6) { width: 8%; }
.gv-cm-tbl th:nth-child(7), .gv-cm-tbl td:nth-child(7) { width: 27%; }
.gv-cm-hint { font-style: italic; opacity: .8; }
.gv-cm-tbl tbody td.empty { padding: 18px; text-align: center; color: var(--t3, var(--t-muted)); }

/* ─── KPI drill modal ─── */
.gv-modal-bg {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
}
.gv-modal-card {
  background: var(--bg1, #fff);
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(0, 0, 0, .22);
  width: 580px; max-width: 90vw;
  max-height: 80vh;
  display: flex; flex-direction: column;
}
.gv-modal-h {
  padding: 14px 20px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
}
.gv-modal-t { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.gv-modal-s { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.gv-modal-x {
  border: 0; background: #F4F3F9;
  width: 28px; height: 28px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: var(--t3, var(--t-muted));
  transition: background .12s;
}
.gv-modal-x:hover { background: rgba(226, 75, 74, .12); color: var(--sev-critical); }

.gv-modal-body { flex: 1; overflow-y: auto; }
.gv-modal-tbl { width: 100%; border-collapse: collapse; }
.gv-modal-tbl tr {
  cursor: pointer;
  transition: background .12s;
  animation: fadeSlideIn .2s ease both;
}
.gv-modal-tbl tr:hover { background: rgba(127, 119, 221, .04); }
.gv-modal-tbl td {
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  font-size: 13px;
  font-feature-settings: "tnum";
}
.gv-modal-tbl td.lt {
  font-weight: 500; color: var(--t1, #1E2A4A);
  display: flex; align-items: center; gap: 8px;
}
.gv-modal-tbl td.num { text-align: right; min-width: 60px; }
.gv-modal-tbl td.num.big { font-weight: 600; font-size: 14px; }
.gv-modal-tbl td.sub { text-align: right; color: var(--t3, var(--t-muted)); font-size: 11.5px; min-width: 140px; }
.gv-modal-tbl td.empty { text-align: center; padding: 32px; color: var(--t3, var(--t-muted)); font-style: italic; }

.gv-modal-enter-active, .gv-modal-leave-active { transition: opacity .2s, transform .2s; }
.gv-modal-enter-from, .gv-modal-leave-to { opacity: 0; transform: scale(.96); }

@media (max-width: 480px) {
  .gv-mat-tbl { font-size: 10.5px; }
  .gv-mat-tbl th, .gv-mat-tbl td { padding: 5px 6px; }
  .gv-rt-name { width: 130px; }
  .gv-modal-tbl td, .gv-modal-tbl th { padding: 5px 8px; }
}
</style>
