<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, inject, watch, nextTick } from 'vue';
import { useSavedFilter } from "@/composables/useSavedFilter";
import { useAiPageContext } from "@/composables/useAiPageContext";
import { NGMK_SEED, type InvestProjectsCompanyData, type ProjectRow } from '@/data/ngmk-invest-seed';
import { loadCompanyInvestData, saveCompanyInvestData, deleteCompanyInvestData } from '@/api/investProjectsStorage';
import { downloadInvestTemplate, parseInvestTemplate } from '@/utils/investProjectsTemplate';

/** Empty placeholder used for companies that don't have real invest-project
 * data in the system yet. Shows zeros everywhere and triggers the "Нет
 * данных" empty state in subviews.
 *
 * IMPORTANT: do NOT spread NGMK_SEED into this — that copied the entire
 * NGMK capex/financials structure, so a freshly imported company shared
 * a stale reference to those nested objects until Vue diffed them. Building
 * a fully-fresh skeleton makes reactive swaps deterministic. */
const EMPTY_INVEST_DATA: InvestProjectsCompanyData = {
  company: '',
  company_short_name: '',
  company_full_name: '',
  fiscal_year: NGMK_SEED.fiscal_year,
  reporting_period: 'Q1',
  currency: 'USD',
  ceo: '',
  projects: [],
  capex: {
    annual_plan_mln: 0, annual_actual_ytd_mln: 0, annual_exec_rate: 0,
    prev_year_plan_mln: 0, prev_year_actual_mln: 0, prev_year_exec_rate: 0,
    fte_approved: 0, fte_deployed: 0,
    current_year_quarters: [
      { q: 'Q1', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q2', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q3', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q4', plan_mln: 0, actual_mln: null, exec_rate: null },
    ],
    prev_year_quarters: [
      { q: 'Q1', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q2', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q3', plan_mln: 0, actual_mln: null, exec_rate: null },
      { q: 'Q4', plan_mln: 0, actual_mln: null, exec_rate: null },
    ],
  },
  financials: [],
} as InvestProjectsCompanyData;
import ProjectDrillModal from '@/components/InvestProjects/ProjectDrillModal.vue';
import KpiDrillModal, { type KpiType } from '@/components/InvestProjects/KpiDrillModal.vue';
import CapexQuarterlyModal from '@/components/InvestProjects/CapexQuarterlyModal.vue';
import CreditDonut, { type DonutEntry } from '@/components/CreditPortfolio/CreditDonut.vue';
import { useCompaniesStore } from '@/stores/companies';
import { useFormatters } from '@/composables/useFormatters';
import { usePermissions } from '@/composables/usePermissions';
const _perm = usePermissions('invest');
const fmt = useFormatters();

/** Embedded mode: rendered inside CompanyWorkspace tab.
 *   embedded=true        → hide own topbar (workspace already has one)
 *   companyName=<name>   → preselect company; hide picker dropdown
 */
const props = defineProps<{ embedded?: boolean; companyName?: string }>();

// ─── Sidebar toggle (injected from AppShell) ──────────────
const toggleSidebar = inject<() => void>('toggleSidebar', () => {});

// ─── State ──────────────────────────────────────────────
// `data` is currently NGMK_SEED for any selected company because the
// backend doesn't yet have per-company invest-project data. The company
// *picker* is driven by the live Companies store (Pack 148 Stage C) so
// new companies appear immediately; the data swap waits on a backend.
const data = ref<InvestProjectsCompanyData>(EMPTY_INVEST_DATA);

/** Only НГМК has real seed data; everyone else gets empty placeholder
 * + "Нет данных" в UI пока бэкенд не отдаёт per-company invest projects. */
function _resolveDataForCompany(name: string): InvestProjectsCompanyData {
  if (!name) return EMPTY_INVEST_DATA;
  if (/нгмк|navoiy/i.test(name)) return NGMK_SEED;
  return EMPTY_INVEST_DATA;
}
const editMenuOpen = ref(false);
const companiesStore = useCompaniesStore();
const selectedCompany = useSavedFilter<string>("invest.selectedCompany", '');

/** Resolve company code from selected name via companies store. Required for
 *  backend namespace path companies/<code>/invest_data. Returns "" if no match. */
function _codeForName(name: string): string {
  if (!name) return '';
  const co = companiesStore.companies.find(
    (c) => (c.name_short || c.name_ru || '').trim() === name.trim(),
  );
  return (co?.code || '').toLowerCase();
}

// Swap data when selectedCompany changes:
//   1) try backend storage (per-company saved data)
//   2) fall back to NGMK seed for NGMK only
//   3) otherwise empty placeholder
watch(
  () => selectedCompany.value,
  async (name) => {
    if (!name) { data.value = EMPTY_INVEST_DATA; return; }
    const code = _codeForName(name);
    if (code) {
      try {
        const stored = await loadCompanyInvestData(code);
        if (stored) { data.value = stored; return; }
      } catch (e) {
        console.warn('[invest] loadCompanyInvestData failed:', e);
      }
    }
    data.value = _resolveDataForCompany(name);
  },
);

// Pack 136: pipeline expand toggle (show top-5 or all)
const pipelineExpanded = useSavedFilter<boolean>("invest.pipelineExpanded", false);

// Pack 7.9e: AI Bubble context
useAiPageContext({
  key: "invest-projects",
  label: "Инвестпроекты",
  describeState: () => selectedCompany.value
    ? `компания: ${selectedCompany.value}; pipeline: ${pipelineExpanded.value ? "все" : "top-5"}`
    : `pipeline: ${pipelineExpanded.value ? "все" : "top-5"}`,
  quickActions: [
    { label: "NPV-лидеры портфеля", icon: "💰",
      prompt: "Найди топ-5 CAPEX-проектов по NPV в портфеле. По каким компаниям. Сделай вывод где деньги работают эффективнее." },
    { label: "Просроченные проекты", icon: "⏰",
      prompt: "Используй list_overdue_tasks + get_project_details для топ-проектов которые срываются. Анализ root-cause через комментарии." },
    { label: "CAPEX-сводка", icon: "🏗️",
      prompt: "Дай сводку CAPEX-инвестиций по портфелю: общий объём, по секторам, по компаниям. Используй list_companies + tools проектов." },
    { label: "IPO-готовность проектов", icon: "🎯",
      prompt: "Какие инвестпроекты критичны для IPO-roadmap из UzNIF плана 2025-2027? Где блокеры? Используй get_project_details." },
  ],
});

// Pack 136: CAPEX quarterly drill-down modal
const capexModalOpen = ref(false);

// Pack 136: functional company dropdown in topbar
const companyDdOpen = ref(false);
// Pack 148 C: list now comes from companies store (was hardcoded ['НГМК']).
const availableCompanies = computed<string[]>(() =>
  companiesStore.companies
    .slice()
    .sort((a, b) => (a.sort_order ?? 9999) - (b.sort_order ?? 9999))
    .map(c => c.name_short || c.name_ru)
    .filter(Boolean)
);
function toggleCompanyDd() {
  companyDdOpen.value = !companyDdOpen.value;
  if (companyDdOpen.value) editMenuOpen.value = false;
}
function pickCompany(name: string) {
  selectedCompany.value = name;
  companyDdOpen.value = false;
}
function closeCompanyDdOnClickOutside(e: MouseEvent) {
  if (!companyDdOpen.value) return;
  const target = e.target as HTMLElement;
  if (!target.closest('.ip-glass-select') && !target.closest('.ip-co-pop')) {
    companyDdOpen.value = false;
  }
}

// ─── Modal state ────────────────────────────────────────
const selectedProject = ref<ProjectRow | null>(null);
const selectedKpi = ref<KpiType | null>(null);

function openProjectDrill(project: ProjectRow): void {
  selectedProject.value = project;
}
function closeProjectDrill(): void {
  selectedProject.value = null;
}
function onProjectUpdated(updated: ProjectRow): void {
  // Replace the matching row in data.projects, keep modal open showing fresh values.
  const idx = data.value.projects.findIndex(p => p.num === updated.num);
  if (idx >= 0) data.value.projects[idx] = updated;
  selectedProject.value = updated;
}
function openKpiDrill(kpiType: KpiType): void {
  selectedKpi.value = kpiType;
}
function closeKpiDrill(): void {
  selectedKpi.value = null;
}

// ─── Computed metrics ───────────────────────────────────
// 2026-05-26: Number-coerce — backend numeric/decimal приходят строками
// (Postgres numeric → JSON string). `0 + "500"` = "0500" (concat) →
// все суммы становятся гигантскими строками вместо чисел.
const toNum = (v: unknown): number => Number(v ?? 0);

const totalInvestment = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.total_investment_mln), 0)
);
const expansionInvestment = computed(() =>
  data.value.projects.filter(p => p.kind === 'expansion').reduce((s, p) => s + toNum(p.total_investment_mln), 0)
);
const modernizationInvestment = computed(() =>
  data.value.projects.filter(p => p.kind === 'modernization').reduce((s, p) => s + toNum(p.total_investment_mln), 0)
);
const funding2026 = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.funding_2026_mln), 0)
);
const disbursedYTD = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.disbursed_ytd_mln), 0)
);
const disbursementRate = computed(() =>
  funding2026.value > 0 ? (disbursedYTD.value / funding2026.value) * 100 : 0
);
const totalNPV = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.npv_mln), 0)
);
// Counts for KPI-card sub-labels (Pack 154: were hardcoded to NGMK's "6" / "8").
const npvCount = computed(() =>
  data.value.projects.filter(p => p.npv_mln != null && p.npv_mln !== 0).length
);
const paybackCount = computed(() =>
  data.value.projects.filter(p => p.payback_years != null && p.payback_years > 0).length
);
const expansionCount = computed(() =>
  data.value.projects.filter(p => p.kind === 'expansion').length
);
const modernizationCount = computed(() =>
  data.value.projects.filter(p => p.kind === 'modernization').length
);

// Filter `> 0` (not just != null) so 0-placeholders coming from xlsx cells
// that the user left blank don't tank the weighted average / arithmetic mean.
const weightedIRR = computed(() => {
  const items = data.value.projects.filter(p => p.irr_pct != null && toNum(p.irr_pct) > 0);
  const totalW = items.reduce((s, p) => s + toNum(p.total_investment_mln), 0);
  if (totalW === 0) return 0;
  return items.reduce((s, p) => s + toNum(p.irr_pct) * toNum(p.total_investment_mln), 0) / totalW;
});
const avgPayback = computed(() => {
  const items = data.value.projects.filter(p => p.payback_years != null && toNum(p.payback_years) > 0);
  if (items.length === 0) return 0;
  return items.reduce((s, p) => s + toNum(p.payback_years), 0) / items.length;
});
const totalNewJobs = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.new_jobs), 0)
);
const annualRevenueImpact = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.revenue_impact_mln), 0)
);
const totalEnergy = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.energy_mkwh), 0)
);
const totalWater = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.water_mm3), 0)
);
const totalGas = computed(() =>
  data.value.projects.reduce((s, p) => s + toNum(p.gas_mm3), 0)
);
const capexExecRate = computed(() => data.value.capex.annual_exec_rate * 100);

// Pipeline projects sorted by NPV descending (top expansion projects shown)
const pipelineProjects = computed<ProjectRow[]>(() =>
  [...data.value.projects].sort(
    (a, b) => (b.npv_mln ?? 0) - (a.npv_mln ?? 0)
  )
);

// Sector breakdown for donut. Pack 154: was hardcoded to NGMK project names
// (Мурунтау, Зармитан, ГМЗ-7, etc.) so any other imported company showed all
// zeros except «Модернизация». Now universal: split by kind + infrastructure
// flag, which every parsed file carries. Empty buckets are filtered out so
// the donut shows only categories that actually have data.
const sectorBreakdown = computed(() => {
  const total = totalInvestment.value || 1;
  // Expansion split into "infrastructure" vs "core production"
  const expansionCore = data.value.projects
    .filter(p => p.kind === 'expansion' && !p.infrastructure)
    .reduce((s, p) => s + toNum(p.total_investment_mln), 0);
  const expansionInfra = data.value.projects
    .filter(p => p.kind === 'expansion' && p.infrastructure)
    .reduce((s, p) => s + toNum(p.total_investment_mln), 0);
  const modern = modernizationInvestment.value;
  const buckets = [
    { name: 'Расширение (производство)', value: expansionCore,  color: '#1D9E75' },
    { name: 'Расширение (инфраструктура)', value: expansionInfra, color: '#7F77DD' },
    { name: 'Модернизация',               value: modern,          color: '#EF9F27' },
  ];
  return buckets
    .filter(b => b.value > 0)
    .map(b => ({ ...b, pct: (b.value / total) * 100 }));
});

// Donut entries for CreditDonut component (cpRenderSignatureDonut port)
const donutEntries = computed<DonutEntry[]>(() =>
  sectorBreakdown.value.map(s => ({
    label: s.name,
    color: s.color,
    value: s.value,
    sub: fmt.fmtMoneyCompact(s.value * 1e6, "USD", { decimals: 0 }),
  }))
);
const donutCenterValue = computed(() => fmt.fmtMoneyCompact(totalInvestment.value * 1e6, "USD", { decimals: 1 }));
const donutCenterLabel = 'всего';

// ─── Project lifecycle timeline (gantt) ─────────────────
const TIMELINE_START = 2017;
const TIMELINE_END = 2033;
const TIMELINE_SPAN = TIMELINE_END - TIMELINE_START;
const CURRENT_YEAR = 2026;

const timelineProjects = computed(() =>
  data.value.projects.map((p, idx) => {
    const startY = new Date(p.period_start).getFullYear();
    const endY = new Date(p.period_end).getFullYear();
    const startPct = ((startY - TIMELINE_START) / TIMELINE_SPAN) * 100;
    const widthPct = ((endY - startY) / TIMELINE_SPAN) * 100;
    let color = '#1D9E75'; // реализуется
    let bgColor = '#E1F5EE';
    let label = 'реализ';
    let textColor = '#085041';
    if (p.status === 'Планируется') {
      color = '#378ADD'; bgColor = '#E6F1FB'; label = 'план'; textColor = '#0C447C';
    } else if (p.status === 'В процессе') {
      color = '#EF9F27'; bgColor = '#FAEEDA'; label = 'в проц'; textColor = '#854F0B';
    }
    return {
      ...p,
      idx,
      startY,
      endY,
      startPct,
      widthPct,
      color,
      bgColor,
      label,
      textColor,
      shortName: p.name.length > 36 ? p.name.substring(0, 34) + '…' : p.name,
    };
  })
);

const currentYearPct = ((CURRENT_YEAR - TIMELINE_START) / TIMELINE_SPAN) * 100;
const yearTicks = Array.from({ length: 9 }, (_, i) => TIMELINE_START + i * 2);

// ─── Quarterly bars max for scaling ─────────────────────
const maxQuarterPlan = computed(() =>
  Math.max(...data.value.capex.current_year_quarters.map(q => q.plan_mln))
);

// ─── Format helpers ─────────────────────────────────────
function fmtMln(n: number, decimals = 0): string {
  if (Math.abs(n) >= 1000) {
    return fmt.fmtNumber(n / 1000, { decimals: decimals === 0 ? 2 : decimals }) + ' млрд $';
  }
  return fmt.fmtNumber(n, { decimals });
}
function fmtPct(n: number, decimals = 1): string {
  return fmt.fmtPercent(n, { decimals });
}
function fmtInt(n: number): string {
  return fmt.fmtNumber(n);
}

onMounted(async () => {
  await companiesStore.ensureLoaded();
  // Embedded mode: preselect from prop, ignore last-selected
  if (props.companyName) {
    selectedCompany.value = props.companyName;
    return;
  }
  if (!selectedCompany.value) {
    // Prefer NGMK (only company with seed data), fall back to first available.
    const ngmk = availableCompanies.value.find(n => /нгмк/i.test(n));
    selectedCompany.value = ngmk || availableCompanies.value[0] || '';
  }
});

onMounted(() => {
  document.addEventListener('click', closeCompanyDdOnClickOutside);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', closeCompanyDdOnClickOutside);
});
onMounted(() => {
  document.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (!target.closest('.ip-edit-menu-wrap')) {
      editMenuOpen.value = false;
    }
  });
});

function toggleEditMenu() {
  editMenuOpen.value = !editMenuOpen.value;
}

// ─── Pack 154: Excel import / template download ────────────
const fileInputRef = ref<HTMLInputElement | null>(null);
const importBusy = ref(false);

async function onDownloadTemplate() {
  editMenuOpen.value = false;
  try {
    // Empty template by default — fewer surprises than seeded with NGMK data.
    // User can re-download with example by holding Alt while clicking (future enhancement).
    await downloadInvestTemplate(
      selectedCompany.value || 'company',
      data.value.fiscal_year || new Date().getFullYear(),
      { includeExample: false },
    );
  } catch (e) {
    console.error('[invest] template download failed:', e);
    alert('Не удалось сформировать шаблон Excel');
  }
}

function onClickImport() {
  editMenuOpen.value = false;
  fileInputRef.value?.click();
}

async function onDeleteCompanyData() {
  editMenuOpen.value = false;
  if (!selectedCompany.value) {
    alert('Сначала выберите компанию');
    return;
  }
  const code = _codeForName(selectedCompany.value);
  if (!code) {
    alert('Не удалось определить код компании');
    return;
  }
  if (!confirm(
    `Удалить ВСЕ инвест-данные компании «${selectedCompany.value}»?\n\n` +
    'Это сотрёт проекты, CAPEX и финпоказатели на сервере. ' +
    'Операция необратима. Файл xlsx у вас остаётся.'
  )) return;

  importBusy.value = true;
  try {
    const res = await deleteCompanyInvestData(code);
    // Reset UI to empty placeholder + NGMK seed if applicable.
    data.value = EMPTY_INVEST_DATA;
    await nextTick();
    data.value = _resolveDataForCompany(selectedCompany.value);
    alert(res.removed ? 'Данные удалены.' : 'Данных не было — нечего удалять.');
  } catch (e: any) {
    console.error('[invest] delete failed:', e);
    alert('Удаление не удалось: ' + (e?.response?.data?.detail || e?.message || 'ошибка'));
  } finally {
    importBusy.value = false;
  }
}

async function onImportFile(ev: Event) {
  const input = ev.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';  // reset so re-picking same file fires change
  if (!file) return;

  if (!selectedCompany.value) {
    alert('Сначала выберите компанию в выпадающем списке наверху');
    return;
  }
  const code = _codeForName(selectedCompany.value);
  if (!code) {
    alert(`Не удалось определить код компании для «${selectedCompany.value}». Проверьте справочник компаний.`);
    return;
  }

  importBusy.value = true;
  try {
    const parsed = await parseInvestTemplate(file);
    // Force the company name from selection — meta sheet is informational,
    // but the source of truth is the company chosen in the topbar.
    parsed.company = selectedCompany.value;
    await saveCompanyInvestData(code, parsed);

    // Hard refresh of the reactive ref:
    //   1) blank the data first so all `data.value.capex.*` / `.projects.*`
    //      child object references diff cleanly,
    //   2) then assign the freshly-parsed payload.
    // Without step (1), KPI cards / quarterly chart sometimes kept stale
    // refs to the previous company's nested arrays because the spread came
    // from the same source object (EMPTY_INVEST_DATA used to share refs
    // with NGMK_SEED before this pack).
    data.value = EMPTY_INVEST_DATA;
    await nextTick();
    data.value = parsed;
    await nextTick();

    alert(`Импорт выполнен: ${parsed.projects.length} проектов, ${parsed.financials.length} лет финпоказателей.\n\nЕсли карточки не обновились — обновите страницу (F5).`);
  } catch (e: any) {
    console.error('[invest] import failed:', e);
    alert('Импорт не удался: ' + (e?.message || 'неизвестная ошибка. Проверьте формат шаблона.'));
  } finally {
    importBusy.value = false;
  }
}
</script>

<template>
  <div class="ip-root">
    <!-- ─── TOPBAR ─────────────────────────────────────── -->
    <div v-if="!props.embedded" class="ip-topbar">
      <div class="ip-tb-l">
        <button class="ip-sb-toggle" @click="toggleSidebar()" title="Скрыть/показать сайдбар" aria-label="toggle sidebar">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </button>
        <button class="ip-glass-select" :class="{ open: companyDdOpen }" @click.stop="toggleCompanyDd">
          <span class="ip-co-dot" style="background:#9B8EC4"></span>
          <span class="ip-co-name">{{ selectedCompany }}</span>
          <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" :style="{ transform: companyDdOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform .15s' }"><path d="M2 4.5l4 4 4-4"/></svg>
        </button>
        <div
          v-if="companyDdOpen"
          class="ip-co-pop"
          @click.stop
          style="position:absolute; top:44px; left:56px; z-index:100; min-width:240px; background:#1E2A4A; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:4px; display:flex; flex-direction:column; gap:1px; box-shadow:0 12px 32px rgba(15,23,60,.4), 0 4px 12px rgba(15,23,60,.2);"
        >
          <button
            v-for="co in availableCompanies"
            :key="co"
            class="ip-co-pop-item"
            :class="{ on: co === selectedCompany }"
            @click="pickCompany(co)"
            :style="{
              display: 'flex',
              alignItems: 'center',
              gap: '9px',
              padding: '8px 11px',
              background: co === selectedCompany ? 'rgba(155,142,196,.18)' : 'transparent',
              border: 'none',
              color: '#fff',
              fontSize: '12px',
              fontWeight: '500',
              cursor: 'pointer',
              borderRadius: '6px',
              textAlign: 'left',
              width: '100%',
            }"
          >
            <span :style="{ width: '7px', height: '7px', borderRadius: '50%', flexShrink: 0, background: co === selectedCompany ? '#9B8EC4' : '#D1D5DB' }"></span>
            <span style="flex:1; text-align:left;">{{ co }}</span>
            <svg v-if="co === selectedCompany" width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="2 6 5 9 10 3"/></svg>
          </button>
        </div>
      </div>
      <div class="ip-tb-c">
        <div class="ip-tb-title">Инвест-проекты · {{ selectedCompany }}</div>
        <div class="ip-tb-sub">{{ data.fiscal_year }} · FY · {{ data.projects.length }} ПРОЕКТОВ · {{ fmtMln(totalInvestment) }} МЛН</div>
      </div>
      <div class="ip-tb-r">
        <div v-if="_perm.canEdit.value || _perm.canExport.value" class="ip-edit-menu-wrap">
          <button class="ip-edit-btn" :class="{ open: editMenuOpen }" @click.stop="toggleEditMenu" aria-label="menu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="2"/><circle cx="12" cy="5" r="2"/><circle cx="12" cy="19" r="2"/></svg>
          </button>
          <div class="ip-edit-dd" :class="{ show: editMenuOpen }">
            <button v-if="_perm.canEdit.value" @click="onDownloadTemplate">↓ Скачать шаблон Excel</button>
            <button v-if="_perm.canEdit.value" :disabled="importBusy" @click="onClickImport">
              {{ importBusy ? '… Импорт…' : '↑ Импорт шаблона Excel' }}
            </button>
            <button v-if="_perm.canExport.value">↑ Экспорт Excel</button>
            <button v-if="_perm.canEdit.value">Редактор проектов</button>
            <div v-if="_perm.canEdit.value" class="sep"></div>
            <button v-if="_perm.canEdit.value">↺ Восстановить из черновика</button>
            <button v-if="_perm.canExport.value">↓ Экспорт PDF для НС</button>
            <div v-if="_perm.canEdit.value" class="sep"></div>
            <button v-if="_perm.canEdit.value" :disabled="importBusy" @click="onDeleteCompanyData"
                    style="color:#C53030">✕ Удалить данные компании</button>
          </div>
        </div>
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          style="display:none"
          @change="onImportFile"
        />
      </div>
    </div>

    <!-- ─── BODY ───────────────────────────────────────── -->
    <div class="ip-body">

      <!-- KPI band: 8 cards в 4×2 -->
      <div class="ip-kpi-row">
        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#7F77DD;--kpi2-d:0ms" @click="openKpiDrill('total-investment')">
          <div class="kpi2-lbl">Всего инвестиций</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtMln(totalInvestment) }}</span><span class="kpi2-unit">млн&nbsp;$</span></div>
          <div class="kpi2-sub">расш {{ fmtMln(expansionInvestment) }} + модерн {{ fmtMln(modernizationInvestment) }}</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#1D9E75;--kpi2-d:80ms" @click="openKpiDrill('disbursement')">
          <div class="kpi2-lbl">Освоение портфеля</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtPct(disbursementRate) }}</span></div>
          <div class="ip-progress"><div class="ip-progress-fill" :style="{ width: Math.min(disbursementRate, 100) + '%', background: '#1D9E75' }"></div></div>
          <div class="kpi2-sub">${{ fmtMln(disbursedYTD, 1) }} / ${{ fmtMln(funding2026, 1) }} млн (план 2026)</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#378ADD;--kpi2-d:160ms" @click="openKpiDrill('npv')">
          <div class="kpi2-lbl">NPV портфеля</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtMln(totalNPV) }}</span><span class="kpi2-unit">млн&nbsp;$</span></div>
          <div class="kpi2-sub">{{ npvCount }} {{ npvCount === 1 ? 'проект' : (npvCount >= 2 && npvCount <= 4 ? 'проекта' : 'проектов') }} с расчётом</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#EF9F27;--kpi2-d:240ms" @click="openKpiDrill('irr')">
          <div class="kpi2-lbl">IRR средний</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtPct(weightedIRR) }}</span></div>
          <div class="kpi2-sub">взвешенный по объёму</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#9B8EC4;--kpi2-d:320ms" @click="openKpiDrill('payback')">
          <div class="kpi2-lbl">Payback</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ avgPayback.toFixed(1).replace('.', ',') }}</span><span class="kpi2-unit">лет</span></div>
          <div class="kpi2-sub">avg по {{ paybackCount }} {{ paybackCount === 1 ? 'проекту' : 'проектам' }}</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#1D9E75;--kpi2-d:400ms" @click="openKpiDrill('jobs')">
          <div class="kpi2-lbl">Новые раб. места</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtInt(totalNewJobs) }}</span><span class="kpi2-unit">чел</span></div>
          <div class="kpi2-sub">{{ expansionCount }} расш + {{ modernizationCount }} модерн</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#E24B4A;--kpi2-d:480ms" @click="openKpiDrill('capex-exec')">
          <div class="kpi2-lbl">CAPEX 2026 exec</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtPct(capexExecRate) }}</span></div>
          <div class="ip-progress"><div class="ip-progress-fill" :style="{ width: Math.min(capexExecRate, 100) + '%', background: '#E24B4A' }"></div></div>
          <div class="kpi2-sub">${{ fmtMln(data.capex.annual_actual_ytd_mln, 1) }} / план ${{ fmtMln(data.capex.annual_plan_mln, 1) }}M</div>
        </div>

        <div class="kpi2 fin-shimmer ip-kpi-click" style="--kpi2-accent:#EF9F27;--kpi2-d:560ms" @click="openKpiDrill('revenue')">
          <div class="kpi2-lbl">Доход в год (steady)</div>
          <div class="kpi2-val-row"><span class="kpi2-val">{{ fmtMln(annualRevenueImpact, 1) }}</span><span class="kpi2-unit">млн&nbsp;$</span></div>
          <div class="kpi2-sub">по выходу проектов на мощность</div>
        </div>
      </div>

      <!-- Pipeline + Sector donut -->
      <div class="ip-row" style="grid-template-columns:2fr 1fr">
        <div class="ip-card" style="--ip-d:640ms">
          <div class="ip-card-ttl">
            <div class="ip-card-ttl-l">Pipeline проектов</div>
            <div class="ip-card-ttl-r">Все типы · {{ pipelineProjects.length }} шт</div>
          </div>
          <div class="ip-pipe">
            <div v-for="(p, i) in (pipelineExpanded ? pipelineProjects : pipelineProjects.slice(0, 5))" :key="p.num" class="ip-pipe-row ip-pipe-click" :style="{ '--pp-d': (i*80)+'ms' }" @click="openProjectDrill(p)">
              <div class="ip-pipe-name">
                <div class="ip-pipe-title">{{ p.name }}</div>
                <div class="ip-pipe-meta">{{ fmtMln(p.total_investment_mln, 1) }}M · {{ p.capacity.substring(0, 35) }}{{ p.capacity.length > 35 ? '…' : '' }}</div>
              </div>
              <div class="ip-pipe-stat">
                <div class="ip-pipe-stat-lbl">NPV</div>
                <div class="ip-pipe-stat-val" :style="{ color: p.npv_mln ? '#1D9E75' : '#888780' }">{{ p.npv_mln ? fmtMln(p.npv_mln, 0) : '—' }}</div>
              </div>
              <div class="ip-pipe-stat">
                <div class="ip-pipe-stat-lbl">IRR</div>
                <div class="ip-pipe-stat-val" :style="{ color: p.irr_pct ? (p.irr_pct >= 20 ? '#1D9E75' : '#EF9F27') : '#888780' }">{{ p.irr_pct ? fmt.fmtPercent(p.irr_pct, { decimals: 1 }) : '—' }}</div>
              </div>
              <div class="ip-pill" :style="{ background: p.status === 'Реализуется' ? '#E1F5EE' : '#EAF3DE', color: p.status === 'Реализуется' ? '#085041' : '#3B6D11' }">
                {{ p.status === 'Реализуется' ? 'реализ' : p.status === 'Планируется' ? 'план' : 'в проц' }}
              </div>
            </div>
            <button
              v-if="pipelineProjects.length > 5"
              class="ip-pipe-more ip-pipe-more-btn"
              @click="pipelineExpanded = !pipelineExpanded"
            >
              <svg width='10' height='10' viewBox='0 0 12 12' fill='none' stroke='currentColor' stroke-width='2' stroke-linecap='round' :style="{ transform: pipelineExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }"><path d='M3 5l3 3 3-3'/></svg> {{ pipelineExpanded ? 'Свернуть' : 'Показать ещё ' + (pipelineProjects.length - 5) + ' проектов' }}
            </button>
          </div>
        </div>

        <div class="ip-card" style="--ip-d:720ms">
          <div class="ip-card-ttl"><div class="ip-card-ttl-l">Распределение CAPEX</div></div>
          <CreditDonut
            :entries="donutEntries"
            :center-value="donutCenterValue"
            :center-label="donutCenterLabel"
            :size="140"
          />
        </div>
      </div>

      <!-- Project Lifecycle Timeline -->
      <div class="ip-card" style="--ip-d:800ms;margin-top:14px">
        <div class="ip-card-ttl">
          <div class="ip-card-ttl-l">Жизненный цикл проектов</div>
          <div class="ip-card-ttl-r">{{ TIMELINE_START }} → {{ TIMELINE_END }} · все {{ data.projects.length }} проектов</div>
        </div>

        <div class="ip-gantt">
          <!-- Year ticks header -->
          <div class="ip-gantt-axis">
            <div v-for="y in yearTicks" :key="y" class="ip-gantt-tick" :style="{ left: ((y - TIMELINE_START) / TIMELINE_SPAN * 100) + '%' }">
              <span class="ip-gantt-tick-lbl">{{ y }}</span>
            </div>
          </div>

          <!-- Today line -->
          <div class="ip-gantt-today" :style="{ left: currentYearPct + '%' }">
            <div class="ip-gantt-today-lbl">{{ CURRENT_YEAR }}</div>
          </div>

          <!-- Project rows -->
          <div class="ip-gantt-rows">
            <div v-for="p in timelineProjects" :key="p.num" class="ip-gantt-row ip-gantt-click" :style="{ '--ga-d': (p.idx * 60) + 'ms' }" @click="openProjectDrill(data.projects[p.idx])">
              <div class="ip-gantt-row-label">
                <span class="ip-gantt-row-num">{{ p.num }}</span>
                <span class="ip-gantt-row-name">{{ p.shortName }}</span>
                <span class="ip-gantt-row-kind">{{ p.kind === 'expansion' ? 'расш' : 'модерн' }}</span>
              </div>
              <div class="ip-gantt-row-track">
                <div class="ip-gantt-row-bar"
                  :style="{
                    left: p.startPct + '%',
                    width: p.widthPct + '%',
                    background: p.color,
                    '--bar-d': (p.idx * 60 + 200) + 'ms'
                  }">
                  <span class="ip-gantt-bar-yrs">{{ p.endY - p.startY }} лет</span>
                </div>
              </div>
              <div class="ip-gantt-pill" :style="{ background: p.bgColor, color: p.textColor }">{{ p.label }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- CAPEX execution quarterly — clickable card opens drill-down modal -->
      <div class="ip-card ip-pipe-click" style="--ip-d:880ms;margin-top:14px;cursor:pointer" @click="capexModalOpen = true">
        <div class="ip-card-ttl">
          <div class="ip-card-ttl-l">CAPEX исполнение {{ data.fiscal_year }} · квартальная разбивка</div>
          <div class="ip-card-ttl-r">млн $ · план vs факт</div>
        </div>
        <div class="ip-qrow">
          <div v-for="(q, i) in data.capex.current_year_quarters" :key="q.q" class="ip-qcell" :style="{ '--qd': (i*100)+'ms' }">
            <div class="ip-qbars">
              <div class="ip-qbar-plan" :style="{ height: (q.plan_mln/maxQuarterPlan*100)+'%' }"></div>
              <div class="ip-qbar-fact" :style="{ height: q.actual_mln !== null ? (q.actual_mln/maxQuarterPlan*100)+'%' : '0%' }"></div>
            </div>
            <div class="ip-qfooter">
              <span class="ip-qlbl">{{ q.q }}</span>
              <span class="ip-qexec" :style="{ color: q.actual_mln !== null ? '#1D9E75' : '#E24B4A' }">{{ q.actual_mln !== null ? fmtPct((q.actual_mln/q.plan_mln)*100, 0) : 'прогноз' }}</span>
            </div>
            <div class="ip-qnote">план {{ q.plan_mln.toFixed(1) }} · {{ q.actual_mln !== null ? 'факт ' + q.actual_mln.toFixed(1) : '—' }}</div>
          </div>
        </div>
        <div class="ip-qfoot">
          <span>Утв. план года: <b>${{ fmtMln(data.capex.annual_plan_mln, 1) }}M</b></span>
          <span>Факт YTD: <b>${{ fmtMln(data.capex.annual_actual_ytd_mln, 1) }}M</b></span>
          <span>Прошлый год: <b>${{ fmtMln(data.capex.prev_year_actual_mln, 1) }}M</b> ({{ fmtPct(data.capex.prev_year_exec_rate * 100, 1) }} к плану)</span>
          <span style="margin-left:auto">FTE заказчика ГУ: <b>{{ data.capex.fte_deployed }}/{{ data.capex.fte_approved }}</b></span>
        </div>
      </div>

      <!-- Resource consumption -->
      <div class="ip-row" style="grid-template-columns:repeat(3,1fr);margin-top:14px">
        <div class="ip-card" style="--ip-d:960ms">
          <div class="ip-rsc-head">
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="#EF9F27" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1l-3 7h3l-1 5 5-7H8z"/></svg>
            <span>Электроэнергия</span>
          </div>
          <div class="ip-rsc-val"><span class="ip-rsc-num">{{ fmtMln(totalEnergy, 0) }}</span><span class="ip-rsc-unit">Млн кВт·ч/год</span></div>
          <div class="ip-rsc-sub">по выходу на проектную мощность · 8 проектов</div>
        </div>
        <div class="ip-card" style="--ip-d:1040ms">
          <div class="ip-rsc-head">
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="#378ADD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1c2.5 4 4 6.5 4 8.5a4 4 0 0 1-8 0c0-2 1.5-4.5 4-8.5z"/></svg>
            <span>Вода</span>
          </div>
          <div class="ip-rsc-val"><span class="ip-rsc-num">{{ totalWater.toFixed(2) }}</span><span class="ip-rsc-unit">Млн м³/год</span></div>
          <div class="ip-rsc-sub">оборотное + свежее водопотребление</div>
        </div>
        <div class="ip-card" style="--ip-d:1120ms">
          <div class="ip-rsc-head">
            <svg width="16" height="16" viewBox="0 0 14 14" fill="none" stroke="#9B8EC4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2l3 5 3-5M3 12h8"/></svg>
            <span>Газ</span>
          </div>
          <div class="ip-rsc-val"><span class="ip-rsc-num">{{ totalGas.toFixed(2) }}</span><span class="ip-rsc-unit">Млн м³/год</span></div>
          <div class="ip-rsc-sub">природный газ (технологический)</div>
        </div>
      </div>

    </div>

    <!-- ─── MODALS ─────────────────────────────────────── -->
    <CapexQuarterlyModal v-if="capexModalOpen" :data="data" @close="capexModalOpen = false" />
    <ProjectDrillModal
      v-if="selectedProject"
      :project="selectedProject"
      :portfolio="data"
      @close="closeProjectDrill"
      @updated="onProjectUpdated"
    />
    <KpiDrillModal
      v-if="selectedKpi"
      :kpi-type="selectedKpi"
      :portfolio="data"
      @close="closeKpiDrill"
    />
  </div>
</template>

<style scoped>
/* ─── Sidebar toggle button ────────────────────────── */
.ip-sb-toggle {
  width: 32px; height: 32px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.06);
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.7);
  transition: all .15s; padding: 0;
  flex-shrink: 0;
}
.ip-sb-toggle:hover { background: rgba(255,255,255,.14); color: #fff; }
.ip-sb-toggle:active { transform: scale(.94); }

/* ─── Clickable cards (drill-down hover) ─────────────── */
.ip-kpi-click { cursor: pointer; }
.ip-pipe-click { cursor: pointer; transition: transform .15s, background .15s; }
.ip-pipe-click:hover { background: #F4F3F9; transform: translateX(2px); }
.ip-gantt-click { cursor: pointer; transition: background .15s; border-radius: 4px; }
.ip-gantt-click:hover { background: rgba(127,119,221,.04); }

/* ─── Root + topbar ────────────────────────────────── */
.ip-root { background: #F4F3F9; min-height: calc(100vh - 48px); font-family: -apple-system, system-ui, 'Segoe UI', sans-serif; color: #2C2C2A; }

.ip-topbar {
  position: relative; display: grid;
  grid-template-columns: auto 1fr auto;
  grid-template-rows: 48px;
  align-items: center; gap: 14px;
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  padding: 0 20px; color: #fff;
}
.ip-tb-l { grid-column: 1; grid-row: 1; align-self: center; display: flex; align-items: center; gap: 10px; }
.ip-tb-c { grid-column: 2; grid-row: 1; align-self: center; display: flex; flex-direction: column; align-items: center; gap: 2px; min-width: 0; overflow: hidden; padding: 0 14px; text-align: center; }
.ip-tb-r { grid-column: 3; grid-row: 1; align-self: center; display: flex; align-items: center; gap: 6px; }
.ip-tb-title { font-size: 15px; font-weight: 500; letter-spacing: .01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ip-tb-sub { font-size: 10px; font-weight: 500; color: rgba(255,255,255,.55); letter-spacing: .08em; text-transform: uppercase; white-space: nowrap; }

.ip-glass-select {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 11px; min-width: 180px;
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12);
  border-radius: 8px; color: #fff; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: all .15s;
}
.ip-glass-select:hover { background: rgba(255,255,255,.14); }
.ip-co-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ip-co-name { flex: 1; text-align: left; }

.ip-edit-menu-wrap { position: relative; display: inline-flex; }
.ip-edit-btn {
  width: 32px; height: 32px;
  border: 1px solid rgba(255,255,255,.15);
  background: rgba(255,255,255,.06); border-radius: 8px;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,.7); transition: all .15s; padding: 0;
}
.ip-edit-btn:hover { background: rgba(255,255,255,.14); color: #fff; }
.ip-edit-btn.open { background: rgba(255,255,255,.2); color: #fff; }
.ip-edit-dd {
  display: none; position: absolute;
  top: calc(100% + 6px); right: 0; min-width: 220px;
  background: #1E2A4A; border: 1px solid rgba(255,255,255,.12);
  border-radius: 10px; padding: 5px;
  box-shadow: 0 8px 24px rgba(0,0,0,.35);
  z-index: 1000;
}
.ip-edit-dd.show { display: block; animation: editMenuIn .18s cubic-bezier(0.34, 1.2, 0.64, 1) both; }
@keyframes editMenuIn { from { opacity: 0; transform: translateY(-4px) scale(.97); } to { opacity: 1; transform: translateY(0) scale(1); } }
.ip-edit-dd button {
  display: block; width: 100%; padding: 9px 12px;
  border: none; background: transparent; color: rgba(255,255,255,.82);
  font-size: 12px; font-weight: 500; cursor: pointer;
  border-radius: 6px; text-align: left;
}
.ip-edit-dd button:hover { background: rgba(255,255,255,.08); color: #fff; }
.ip-edit-dd .sep { height: 1px; background: rgba(255,255,255,.1); margin: 4px 8px; }

/* ─── Body layout ──────────────────────────────────── */
.ip-body { padding: 20px; }
.ip-row { display: grid; gap: 14px; }
.ip-kpi-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px; }

.kpi2 {
  background: rgba(255,255,255,.82);
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border-radius: 16px;
  padding: 16px 18px 12px;
  border: 1px solid rgba(255,255,255,.70);
  box-shadow: 0 2px 12px rgba(15,23,60,.07), 0 1px 3px rgba(15,23,60,.04);
  transition: transform .2s cubic-bezier(0.34, 1.2, 0.64, 1), box-shadow .2s, border-color .2s;
  position: relative; overflow: hidden;
  display: flex; flex-direction: column; justify-content: space-between;
}
/* Pack 155c: scoped .kpi2::before/::after removed — identical to
   global rules in main.css. Single source of truth for top-stripe. */
@keyframes kpi2DrawIn { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0% 0 0); } }
@keyframes kpi2Shimmer { 0%, 75% { transform: translateX(-120%); } 85%, 100% { transform: translateX(120%); } }
@keyframes kpi2Breathe { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
.kpi2:hover {
  transform: translateY(-3px) scale(1.01);
  box-shadow: 0 12px 32px rgba(15,23,60,.12), 0 4px 12px rgba(15,23,60,.06);
  border-color: rgba(124,111,247,.25);
}

.kpi2-lbl { font-size: 10px; font-weight: 500; color: #888780; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
.kpi2-val-row { display: flex; align-items: baseline; gap: 5px; }
.kpi2-val { font-size: 22px; font-weight: 400; letter-spacing: -.025em; line-height: 1; color: #2C2C2A; font-variant-numeric: tabular-nums; }
.kpi2-unit { font-size: 12px; color: #888780; font-weight: 500; }
.kpi2-sub { font-size: 10px; color: #888780; margin-top: 5px; font-weight: 400; }

.ip-progress { height: 4px; background: #E5E4EE; border-radius: 4px; margin: 6px 0 3px; overflow: hidden; }
.ip-progress-fill { height: 100%; border-radius: 4px; animation: progFill 1.4s cubic-bezier(0.34, 1.2, 0.64, 1) both; transform-origin: left; }
@keyframes progFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* ─── Cards (sections) ─────────────────────────────── */
.ip-card {
  background: #fff; border-radius: 14px; padding: 16px 18px;
  border: 1px solid rgba(0,0,0,.05);
  animation: ipCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) var(--ip-d, 0ms) both;
}
@keyframes ipCardIn { 0% { opacity: 0; transform: translateY(10px); } 100% { opacity: 1; transform: translateY(0); } }

.ip-card-ttl { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.ip-card-ttl-l { font-size: 15px; font-weight: 500; letter-spacing: -.01em; }
.ip-card-ttl-r { font-size: 10px; color: #888780; text-transform: uppercase; letter-spacing: .06em; }

/* ─── Pipeline ────────────────────────────────────── */
.ip-pipe { display: flex; flex-direction: column; gap: 8px; }
.ip-pipe-row {
  display: grid; grid-template-columns: 1fr auto auto auto;
  gap: 12px; padding: 9px 10px; border-radius: 8px;
  background: #FAFAFC; align-items: center;
  animation: ipCardIn .45s cubic-bezier(0.34, 1.2, 0.64, 1) var(--pp-d, 0ms) both;
}
.ip-pipe-title { font-size: 12px; font-weight: 500; line-height: 1.3; }
.ip-pipe-meta { font-size: 10px; color: #888780; margin-top: 2px; }
.ip-pipe-stat { text-align: right; }
.ip-pipe-stat-lbl { font-size: 10px; color: #888780; }
.ip-pipe-stat-val { font-size: 12px; font-weight: 500; font-variant-numeric: tabular-nums; }
.ip-pill { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; padding: 3px 8px; border-radius: 11px; font-weight: 500; }
.ip-pipe-more { text-align: center; padding: 7px; font-size: 12px; color: #7F77DD; font-weight: 500; cursor: pointer; }

/* ─── Donut ───────────────────────────────────────── */
.ip-donut-wrap { display: flex; justify-content: center; margin-bottom: 12px; }
.ip-legend { display: flex; flex-direction: column; gap: 6px; font-size: 10px; }
.ip-legend-row { display: flex; align-items: center; gap: 7px; }
.ip-legend-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ip-legend-name { flex: 1; }
.ip-legend-pct { color: #888780; font-variant-numeric: tabular-nums; }

/* ─── Gantt timeline ──────────────────────────────── */
.ip-gantt { position: relative; }
.ip-gantt-axis {
  position: relative; height: 18px; margin-left: 280px; margin-right: 70px;
  border-bottom: 1px solid #F0EFF5; margin-bottom: 10px;
}
.ip-gantt-tick { position: absolute; bottom: 0; transform: translateX(-50%); }
.ip-gantt-tick-lbl { font-size: 10px; color: #888780; font-variant-numeric: tabular-nums; }
.ip-gantt-today {
  position: absolute; top: 12px; bottom: 0;
  width: 2px; background: #E24B4A; opacity: .55;
  margin-left: 280px; z-index: 5; pointer-events: none;
}
.ip-gantt-today-lbl {
  position: absolute; top: -10px; left: 50%; transform: translateX(-50%);
  font-size: 10px; color: #E24B4A; font-weight: 500;
  background: #fff; padding: 0 4px;
}

.ip-gantt-rows { display: flex; flex-direction: column; gap: 4px; }
.ip-gantt-row {
  display: grid; grid-template-columns: 280px 1fr 70px;
  gap: 8px; align-items: center; padding: 4px 0;
  animation: ipGanttRowIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) var(--ga-d, 0ms) both;
}
@keyframes ipGanttRowIn { 0% { opacity: 0; transform: translateX(-8px); } 100% { opacity: 1; transform: translateX(0); } }

.ip-gantt-row-label { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ip-gantt-row-num { font-size: 10px; color: #888780; font-weight: 500; min-width: 14px; }
.ip-gantt-row-name { font-size: 12px; font-weight: 500; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ip-gantt-row-kind { font-size: 10px; color: #888780; text-transform: uppercase; letter-spacing: .04em; flex-shrink: 0; }

.ip-gantt-row-track { position: relative; height: 18px; background: #F4F3F9; border-radius: 4px; }
.ip-gantt-row-bar {
  position: absolute; top: 3px; bottom: 3px;
  border-radius: 3px; display: flex; align-items: center; padding: 0 6px;
  animation: ganttBarIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) var(--bar-d, 0ms) both;
  transform-origin: left center;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
}
@keyframes ganttBarIn { 0% { transform: scaleX(0); opacity: 0; } 100% { transform: scaleX(1); opacity: 1; } }
.ip-gantt-bar-yrs { font-size: 10px; color: rgba(255,255,255,.95); font-weight: 500; }

.ip-gantt-pill {
  font-size: 10px; text-transform: uppercase; letter-spacing: .06em;
  padding: 3px 8px; border-radius: 11px; font-weight: 500; text-align: center;
}

/* ─── CAPEX quarterly bars ────────────────────────── */
.ip-qrow { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.ip-qcell { animation: ipCardIn .45s cubic-bezier(0.34, 1.2, 0.64, 1) var(--qd, 0ms) both; }
.ip-qbars { display: flex; align-items: flex-end; height: 80px; gap: 6px; border-bottom: 1px solid #E5E4EE; padding-bottom: 4px; }
.ip-qbar-plan { flex: 1; background: #7F77DD; border-radius: 4px 4px 0 0; min-height: 1px; animation: ipBarH 1s cubic-bezier(0.34, 1.2, 0.64, 1) both; transform-origin: bottom; }
.ip-qbar-fact { flex: 1; background: #E5E4EE; border-radius: 4px 4px 0 0; min-height: 1px; animation: ipBarH 1s cubic-bezier(0.34, 1.2, 0.64, 1) .2s both; transform-origin: bottom; }
@keyframes ipBarH { 0% { transform: scaleY(0); } 100% { transform: scaleY(1); } }
.ip-qfooter { margin-top: 8px; display: flex; justify-content: space-between; align-items: center; }
.ip-qlbl { font-size: 12px; font-weight: 500; }
.ip-qexec { font-size: 10px; font-weight: 500; }
.ip-qnote { font-size: 10px; color: #888780; margin-top: 2px; }
.ip-qfoot { margin-top: 14px; padding-top: 12px; border-top: 1px solid #F0EFF5; display: flex; gap: 14px; font-size: 10px; color: #888780; flex-wrap: wrap; }
.ip-qfoot b { color: #2C2C2A; font-weight: 500; }

/* ─── Resource cards ──────────────────────────────── */
.ip-rsc-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 10px; color: #888780; text-transform: uppercase; letter-spacing: .06em; font-weight: 500; }
.ip-rsc-val { display: flex; align-items: baseline; gap: 6px; }
.ip-rsc-num { font-size: 20px; font-weight: 400; letter-spacing: -.025em; font-variant-numeric: tabular-nums; }
.ip-rsc-unit { font-size: 10px; color: #888780; }
.ip-rsc-sub { font-size: 10px; color: #888780; margin-top: 6px; }
</style>
