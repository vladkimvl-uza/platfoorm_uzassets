<script setup lang="ts">
/**
 * ProjectDrillModal — drill-down модалка проекта (Pack 8.1).
 *
 * Полная информация по проекту: 4 investment KPIs + 3 ROI KPIs + lifecycle timeline +
 * resources + auto-insights + contacts. Все KPI карточки используют kpi2 паттерн
 * с верхней цветной полоской (kpi2DrawIn + kpi2Breathe + kpi2Shimmer).
 *
 * Insights генерируются автоматически на основе данных проекта:
 *  - Riskflag (если освоено < 30% плана 2026)
 *  - CAPEX intensity ($/тонна мощности)
 *  - FCF break-even (revenue / investment)
 *  - Energy intensity (кВт·ч/тонна)
 */
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch } from 'vue';
import type { ProjectRow, InvestProjectsCompanyData } from '@/data/ngmk-invest-seed';
import { useFormatters } from '@/composables/useFormatters';
import { saveProject } from '@/api/investProjects';
const fmt = useFormatters();

// Header action buttons
const menuOpen = ref(false);
function toggleMenu() { menuOpen.value = !menuOpen.value; }
function closeMenu() { menuOpen.value = false; }

// ─── Edit mode ────────────────────────────────────────────
const editing = ref(false);
const saving = ref(false);
const saveError = ref<string | null>(null);

const STATUS_OPTIONS = [
  "Планируется",
  "Реализуется",
  "В процессе",
] as const;
// Aligns with ProjectRow.FSStatus = "УТВЕРЖДЕНО" | "В ПРОЦЕССЕ" | "-"
// (what the xlsx parser emits).
const FS_OPTIONS = [
  "-",
  "В ПРОЦЕССЕ",
  "УТВЕРЖДЕНО",
] as const;
const KIND_OPTIONS = [
  { value: "expansion",     label: "Расширение" },
  { value: "modernization", label: "Модернизация" },
] as const;

// Editable buffer — mirrored from props.project when entering edit mode
const buf = reactive<Partial<ProjectRow>>({});

function startEdit() {
  // copy editable fields into buffer. Pack 154 follow-up: extended to ALL
  // ProjectRow fields the dashboard KPI cards and donut/Gantt widgets read,
  // so any value changed here actually moves cards on the dashboard.
  const p = props.project;
  Object.assign(buf, {
    kind: p.kind,
    name: p.name,
    capacity: p.capacity,
    period_start: p.period_start,
    period_end: p.period_end,
    lifetime_years: p.lifetime_years,
    total_investment_mln: p.total_investment_mln,
    funding_source: p.funding_source,
    funding_2026_mln: p.funding_2026_mln,
    disbursed_ytd_mln: p.disbursed_ytd_mln,
    revenue_impact_mln: p.revenue_impact_mln,
    new_jobs: p.new_jobs,
    fs_status: p.fs_status,
    status: p.status,
    responsible: p.responsible,
    // KPI-driving fields previously missing from the editor:
    npv_mln: p.npv_mln,
    irr_pct: p.irr_pct,
    payback_years: p.payback_years,
    infrastructure: p.infrastructure,
    energy_mkwh: p.energy_mkwh,
    water_mm3: p.water_mm3,
    gas_mm3: p.gas_mm3,
    capex_budget_cumul_mln: p.capex_budget_cumul_mln,
    capex_actual_cumul_mln: p.capex_actual_cumul_mln,
  });
  saveError.value = null;
  editing.value = true;
}
function cancelEdit() { editing.value = false; saveError.value = null; }

function onClickEdit() { startEdit(); }

async function saveEdit() {
  saveError.value = null;
  saving.value = true;
  try {
    const updated: ProjectRow = { ...props.project, ...buf } as ProjectRow;
    // Slug: lower-case + ASCII-safe; falls back to "ngmk" when seed-derived.
    const code = (props.portfolio.company || "ngmk").toLowerCase().replace(/[^a-z0-9]+/gi, "-");
    await saveProject(code, props.project.num, updated as any);
    editing.value = false;
    emit('updated', updated);
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить";
  } finally {
    saving.value = false;
  }
}

function downloadSummary() {
  closeMenu();
  // Build minimal markdown summary from current project for download
  const p = props.project;
  const lines = [
    `# ${p.name}`,
    ``,
    `**Проект №:** ${p.num}`,
    `**Тип:** ${p.kind === 'expansion' ? 'Расширение' : 'Модернизация'}`,
    `**Мощность:** ${p.capacity}`,
    `**Период:** ${p.period_start}${p.period_end}`,
    `**Срок жизни (после CAPEX):** ${p.lifetime_years} лет`,
    `**Объём инвестиций:** ${p.total_investment_mln} млн $`,
    `**Финансирование 2026:** ${p.funding_2026_mln ?? '—'} млн $`,
    ``,
    `_Сгенерировано из UzAssets · ${new Date().toLocaleString('ru-RU')}_`,
  ];
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `project_${p.num}_${p.name.replace(/[^\wа-яА-Я0-9]+/g, "_").slice(0, 50)}.md`;
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function copyLink() {
  closeMenu();
  const url = window.location.origin + window.location.pathname + `#project=${props.project.num}`;
  if (navigator.clipboard) {
    void navigator.clipboard.writeText(url).then(() => {
      // Light visual feedback — could be a toast in a future iteration
      alert("Ссылка скопирована в буфер обмена");
    });
  } else {
    prompt("Скопируйте ссылку:", url);
  }
}

function onDocClick(e: MouseEvent) {
  if (!menuOpen.value) return;
  if (!(e.target as HTMLElement).closest(".pd-menu-wrap")) menuOpen.value = false;
}

const props = defineProps<{
  project: ProjectRow;
  portfolio: InvestProjectsCompanyData;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'updated', project: ProjectRow): void;
}>();

// ─── Computed metrics ─────────────────────────────────────
const startYear = computed(() => new Date(props.project.period_start).getFullYear());
const endYear = computed(() => new Date(props.project.period_end).getFullYear());
const capexYears = computed(() => endYear.value - startYear.value);
const lifetimeAfterCapex = computed(() => props.project.lifetime_years);
const totalLifetime = computed(() => capexYears.value + lifetimeAfterCapex.value);

const capexPhasePct = computed(() => {
  const total = totalLifetime.value;
  return total > 0 ? (capexYears.value / total) * 100 : 0;
});

// Portfolio aggregates for comparisons
// 2026-05-26: Number-coerce — backend numeric/decimal приходят строками;
// без явной конверсии `0 + "500"` = "0500" (string-concat).
const portfolioTotalInvestment = computed(() =>
  props.portfolio.projects.reduce((s, p) => s + Number(p.total_investment_mln ?? 0), 0)
);
const portfolioFunding2026 = computed(() =>
  props.portfolio.projects.reduce((s, p) => s + Number(p.funding_2026_mln ?? 0), 0)
);
const portfolioNPV = computed(() =>
  props.portfolio.projects.reduce((s, p) => s + Number(p.npv_mln ?? 0), 0)
);
const portfolioAvgPayback = computed(() => {
  const items = props.portfolio.projects.filter(p => p.payback_years !== null);
  if (items.length === 0) return 0;
  return items.reduce((s, p) => s + Number(p.payback_years ?? 0), 0) / items.length;
});
const portfolioEnergyTotal = computed(() =>
  props.portfolio.projects.reduce((s, p) => s + Number(p.energy_mkwh ?? 0), 0)
);
const portfolioWaterTotal = computed(() =>
  props.portfolio.projects.reduce((s, p) => s + Number(p.water_mm3 ?? 0), 0)
);

// Project share metrics
const investmentSharePct = computed(() =>
  portfolioTotalInvestment.value > 0
    ? (props.project.total_investment_mln / portfolioTotalInvestment.value) * 100
    : 0
);
const fundingSharePct = computed(() =>
  portfolioFunding2026.value > 0
    ? (props.project.funding_2026_mln / portfolioFunding2026.value) * 100
    : 0
);
const disbursementPct = computed(() =>
  props.project.funding_2026_mln > 0
    ? (props.project.disbursed_ytd_mln / props.project.funding_2026_mln) * 100
    : 0
);
const npvSharePct = computed(() =>
  portfolioNPV.value > 0 && props.project.npv_mln !== null
    ? (props.project.npv_mln / portfolioNPV.value) * 100
    : 0
);
const npvRank = computed(() => {
  const sorted = [...props.portfolio.projects]
    .filter(p => p.npv_mln !== null)
    .sort((a, b) => (b.npv_mln as number) - (a.npv_mln as number));
  const idx = sorted.findIndex(p => p.num === props.project.num);
  return idx >= 0 ? idx + 1 : null;
});
const irrRank = computed(() => {
  const sorted = [...props.portfolio.projects]
    .filter(p => p.irr_pct !== null)
    .sort((a, b) => (b.irr_pct as number) - (a.irr_pct as number));
  const idx = sorted.findIndex(p => p.num === props.project.num);
  return idx >= 0 ? idx + 1 : null;
});

// Resource shares
const energySharePct = computed(() =>
  portfolioEnergyTotal.value > 0
    ? (props.project.energy_mkwh / portfolioEnergyTotal.value) * 100
    : 0
);
const waterSharePct = computed(() =>
  portfolioWaterTotal.value > 0
    ? (props.project.water_mm3 / portfolioWaterTotal.value) * 100
    : 0
);

// CAPEX intensity ($/тонна мощности) — parse capacity for number+unit
const capexIntensity = computed(() => {
  const match = props.project.capacity.match(/(\d+(?:[.,]\d+)?)\s*млн\s*т/i);
  if (!match) return null;
  const capacityMlnT = parseFloat(match[1].replace(',', '.'));
  if (capacityMlnT <= 0) return null;
  return props.project.total_investment_mln / capacityMlnT; // $M per Mln tons → $/ton
});

const energyIntensity = computed(() => {
  const match = props.project.capacity.match(/(\d+(?:[.,]\d+)?)\s*млн\s*т/i);
  if (!match || props.project.energy_mkwh === 0) return null;
  const capacityMlnT = parseFloat(match[1].replace(',', '.'));
  if (capacityMlnT <= 0) return null;
  return (props.project.energy_mkwh * 1000) / capacityMlnT; // → kWh/ton (Mln kWh × 1000 / Mln tons)
});

// FCF break-even (revenue / investment)
const fcfBreakEvenYears = computed(() => {
  if (props.project.revenue_impact_mln <= 0) return null;
  return props.project.total_investment_mln / props.project.revenue_impact_mln;
});

// ─── Insights generation ────────────────────────────────────
interface Insight {
  type: 'risk' | 'benchmark' | 'efficiency' | 'info';
  title: string;
  text: string;
}

const insights = computed<Insight[]>(() => {
  const out: Insight[] = [];

  // Riskflag: освоено < 30% from 2026 plan
  if (props.project.funding_2026_mln > 0 && disbursementPct.value < 30 && props.project.disbursed_ytd_mln > 0) {
    out.push({
      type: 'risk',
      title: 'Riskflag',
      text: `Освоено ${fmt.fmtMoneyCompact(props.project.disbursed_ytd_mln * 1e6, "USD", { decimals: 2 })} из ${fmt.fmtMoneyCompact(props.project.funding_2026_mln * 1e6, "USD", { decimals: 1 })} плана 2026 (${fmt.fmtPercent(disbursementPct.value, { decimals: 2 })}) — ранняя фаза, потенциальная задержка вхождения в график CAPEX`,
    });
  }

  // CAPEX intensity benchmark
  if (capexIntensity.value !== null && capexIntensity.value > 0) {
    out.push({
      type: 'benchmark',
      title: 'CAPEX intensity',
      text: `$${capexIntensity.value.toFixed(1)}/тонна годовой мощности — отражает технологическую сложность и глубину разработки месторождения`,
    });
  }

  // FCF break-even
  if (fcfBreakEvenYears.value !== null) {
    const paybackText = props.project.payback_years
      ? ` — но IRR payback ${props.project.payback_years} лет = заметная доля FCF от высокой маржи`
      : '';
    out.push({
      type: 'efficiency',
      title: 'FCF break-even',
      text: `Доход ${fmt.fmtMoneyCompact(props.project.revenue_impact_mln * 1e6, "USD", { decimals: 1 })}/год · возврат через выручку за ${fcfBreakEvenYears.value.toFixed(1)} лет${paybackText}`,
    });
  }

  // Energy intensity
  if (energyIntensity.value !== null) {
    out.push({
      type: 'benchmark',
      title: 'Energy intensity',
      text: `${energyIntensity.value.toFixed(1)} кВт·ч/тонна руды — ${energyIntensity.value > 30 ? 'высокое (открытая добыча, transport)' : 'умеренное'}`,
    });
  }

  // No NPV calc
  if (props.project.npv_mln === null) {
    out.push({
      type: 'info',
      title: 'NPV не рассчитан',
      text: 'Для этого проекта NPV не указан — заполни в редакторе или загрузи через Excel-импорт',
    });
  }

  return out;
});

// Status pill styling
const statusPill = computed(() => {
  const s = props.project.status;
  if (s === 'Реализуется') return { bg: '#E1F5EE', color: '#085041', label: 'реализуется' };
  if (s === 'Планируется') return { bg: '#EAF3DE', color: '#3B6D11', label: 'планируется' };
  return { bg: '#FAEEDA', color: '#854F0B', label: 'в процессе' };
});

const fsPill = computed(() => {
  const s = props.project.fs_status;
  if (s === 'УТВЕРЖДЕНО') return { bg: '#E1F5EE', color: '#085041', label: 'ТЭО утв.' };
  if (s === 'В ПРОЦЕССЕ') return { bg: '#FAEEDA', color: '#854F0B', label: 'ТЭО в проц.' };
  return null;
});

// ─── Format helpers ─────────────────────────────────────────
function fmtM(n: number, dec = 1): string {
  return fmt.fmtNumber(n, { decimals: dec });
}
function fmtInt(n: number): string {
  return fmt.fmtNumber(n);
}
function fmtPct(n: number, dec = 1): string {
  return fmt.fmtPercent(n, { decimals: dec });
}

// ─── Keyboard close ─────────────────────────────────────────
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close');
}
onMounted(() => {
  document.addEventListener('keydown', onKeydown);
  document.addEventListener('click', onDocClick);
});
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown);
  document.removeEventListener('click', onDocClick);
});

function onBackdropClick(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('pd-backdrop')) emit('close');
}

const insightStyles: Record<Insight['type'], { dot: string; color: string }> = {
  risk: { dot: '#A32D2D', color: '#791F1F' },
  benchmark: { dot: '#534AB7', color: '#3C3489' },
  efficiency: { dot: '#0F6E56', color: '#085041' },
  info: { dot: '#888780', color: '#5F5E5A' },
};
</script>

<template>
  <div class="pd-backdrop" @mousedown="onBackdropClick">
    <div class="pd-modal" @mousedown.stop>
      <!-- Top animated bar -->
      <div class="pd-top-bar"></div>
      <div class="pd-top-shimmer"></div>

      <!-- Header -->
      <div class="pd-header">
        <div class="pd-header-l">
          <div class="pd-pills">
            <span class="pd-eyebrow">Проект № {{ project.num }} · {{ project.kind === 'expansion' ? 'РАСШИРЕНИЕ' : 'МОДЕРНИЗАЦИЯ' }}</span>
            <span class="pd-pill" :style="{ background: statusPill.bg, color: statusPill.color }">{{ statusPill.label }}</span>
            <span v-if="fsPill" class="pd-pill" :style="{ background: fsPill.bg, color: fsPill.color }">{{ fsPill.label }}</span>
            <span v-if="investmentSharePct >= 25" class="pd-pill pd-pill-purple">самый крупный</span>
          </div>
          <div class="pd-title">{{ project.name }}</div>
          <div class="pd-meta">{{ project.capacity }} · {{ project.period_start.replace(/-/g, '.').split('.').reverse().join('.') }} – {{ project.period_end.replace(/-/g, '.').split('.').reverse().join('.') }} · {{ totalLifetime }} лет</div>
        </div>
        <div class="pd-header-r">
          <button class="pd-btn-edit" @click="onClickEdit">
            {{ editing ? "Скрыть форму" : "Редактировать" }}
          </button>
          <div class="pd-menu-wrap">
            <button class="pd-btn-icon" aria-label="more" @click.stop="toggleMenu">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="2"/><circle cx="12" cy="5" r="2"/><circle cx="12" cy="19" r="2"/></svg>
            </button>
            <div v-if="menuOpen" class="pd-menu" @click.stop>
              <button class="pd-menu-item" @click="downloadSummary">⬇ Скачать сводку (.md)</button>
              <button class="pd-menu-item" @click="copyLink">🔗 Скопировать ссылку</button>
            </div>
          </div>
          <button class="pd-btn-icon" aria-label="close" @click="emit('close')">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 3l8 8M11 3l-8 8"/></svg>
          </button>
        </div>
      </div>

      <!-- Edit form (inline drawer between header and body) -->
      <Transition name="pd-edit-fade">
        <div v-if="editing" class="pd-edit-form">
          <header class="pd-edit-head">
            <span class="pd-edit-title">Редактировать проект № {{ project.num }}</span>
            <span class="pd-edit-hint">Сохранение пишет данные в backend (invest-projects-storage). Изменения видны сразу.</span>
          </header>

          <div class="pd-edit-grid">
            <label class="pd-edit-fld pd-edit-fld-wide">
              <span>Название</span>
              <input v-model="buf.name" type="text" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld pd-edit-fld-wide">
              <span>Мощность / описание</span>
              <input v-model="buf.capacity" type="text" class="pd-edit-input"/>
            </label>

            <label class="pd-edit-fld">
              <span>Начало</span>
              <input v-model="buf.period_start" type="date" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Окончание</span>
              <input v-model="buf.period_end" type="date" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Срок жизни (лет после CAPEX)</span>
              <input v-model.number="buf.lifetime_years" type="number" min="0" max="100" class="pd-edit-input"/>
            </label>

            <label class="pd-edit-fld">
              <span>Объём инвестиций, млн $</span>
              <input v-model.number="buf.total_investment_mln" type="number" step="0.1" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Финансирование 2026, млн $</span>
              <input v-model.number="buf.funding_2026_mln" type="number" step="0.1" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Освоено YTD, млн $</span>
              <input v-model.number="buf.disbursed_ytd_mln" type="number" step="0.1" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Влияние на выручку, млн $/год</span>
              <input v-model.number="buf.revenue_impact_mln" type="number" step="0.1" class="pd-edit-input"/>
            </label>

            <label class="pd-edit-fld pd-edit-fld-wide">
              <span>Источник финансирования</span>
              <input v-model="buf.funding_source" type="text" class="pd-edit-input"/>
            </label>

            <label class="pd-edit-fld">
              <span>Тип проекта</span>
              <select v-model="buf.kind" class="pd-edit-input">
                <option v-for="k in KIND_OPTIONS" :key="k.value" :value="k.value">{{ k.label }}</option>
              </select>
            </label>
            <label class="pd-edit-fld">
              <span>Инфраструктура</span>
              <select v-model="buf.infrastructure" class="pd-edit-input">
                <option :value="true">да</option>
                <option :value="false">нет</option>
              </select>
            </label>
            <label class="pd-edit-fld">
              <span>Новые рабочие места</span>
              <input v-model.number="buf.new_jobs" type="number" min="0" class="pd-edit-input"/>
            </label>

            <!-- KPI карточки: NPV портфеля / IRR средний / Payback -->
            <label class="pd-edit-fld">
              <span>NPV, млн $</span>
              <input v-model.number="buf.npv_mln" type="number" step="0.1" class="pd-edit-input" placeholder="пусто"/>
            </label>
            <label class="pd-edit-fld">
              <span>IRR, %</span>
              <input v-model.number="buf.irr_pct" type="number" step="0.1" class="pd-edit-input" placeholder="напр. 12.5"/>
            </label>
            <label class="pd-edit-fld">
              <span>Срок окупаемости, лет</span>
              <input v-model.number="buf.payback_years" type="number" step="0.1" min="0" class="pd-edit-input" placeholder="пусто"/>
            </label>

            <!-- Ресурсное потребление: суммы попадают в дашборд-блок «по выходу проектов на мощность» -->
            <label class="pd-edit-fld">
              <span>Электроэнергия, ГВт·ч/год</span>
              <input v-model.number="buf.energy_mkwh" type="number" step="0.1" min="0" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Вода, млн м³/год</span>
              <input v-model.number="buf.water_mm3" type="number" step="0.01" min="0" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>Газ, млн м³/год</span>
              <input v-model.number="buf.gas_mm3" type="number" step="0.01" min="0" class="pd-edit-input"/>
            </label>

            <!-- CAPEX cumul — Pipeline / квартальные виджеты -->
            <label class="pd-edit-fld">
              <span>CAPEX бюджет накопит., млн $</span>
              <input v-model.number="buf.capex_budget_cumul_mln" type="number" step="0.1" min="0" class="pd-edit-input"/>
            </label>
            <label class="pd-edit-fld">
              <span>CAPEX освоено накопит., млн $</span>
              <input v-model.number="buf.capex_actual_cumul_mln" type="number" step="0.1" min="0" class="pd-edit-input"/>
            </label>

            <label class="pd-edit-fld">
              <span>Статус проекта</span>
              <select v-model="buf.status" class="pd-edit-input">
                <option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ s }}</option>
              </select>
            </label>
            <label class="pd-edit-fld">
              <span>Статус ТЭО</span>
              <select v-model="buf.fs_status" class="pd-edit-input">
                <option v-for="s in FS_OPTIONS" :key="s" :value="s">{{ s }}</option>
              </select>
            </label>

            <label class="pd-edit-fld pd-edit-fld-wide">
              <span>Ответственный</span>
              <input v-model="buf.responsible" type="text" class="pd-edit-input"/>
            </label>
          </div>

          <div v-if="saveError" class="pd-edit-err">{{ saveError }}</div>

          <div class="pd-edit-actions">
            <button class="pd-edit-btn-cancel" :disabled="saving" @click="cancelEdit">Отмена</button>
            <button class="pd-edit-btn-save" :disabled="saving" @click="saveEdit">
              {{ saving ? "Сохраняем…" : "Сохранить" }}
            </button>
          </div>
        </div>
      </Transition>

      <!-- Body -->
      <div class="pd-body">

        <!-- Investment KPIs (4 cards) -->
        <div class="pd-section-ttl">Инвестиции и финансирование</div>
        <div class="pd-kpi-row pd-kpi-row-4">

          <div class="pd-k2" style="--ac:#7F77DD;--d:80ms">
            <div class="pd-k2-lbl">Объём инвестиций</div>
            <div class="pd-k2-val"><span class="pd-k2-num">{{ fmtM(project.total_investment_mln, 0) }}</span><span class="pd-k2-unit">млн&nbsp;$</span></div>
            <div class="pd-k2-sub">{{ fmtPct(investmentSharePct, 1) }} от портфеля</div>
          </div>

          <div class="pd-k2" style="--ac:#378ADD;--d:160ms">
            <div class="pd-k2-lbl">Финансирование 2026</div>
            <div class="pd-k2-val"><span class="pd-k2-num">{{ fmtM(project.funding_2026_mln, 1) }}</span><span class="pd-k2-unit">млн&nbsp;$</span></div>
            <div class="pd-k2-sub">{{ fmtPct(fundingSharePct, 1) }} от объёма 2026</div>
          </div>

          <div class="pd-k2" :style="{ '--ac': disbursementPct < 30 ? '#E24B4A' : '#1D9E75', '--d': '240ms' } as any">
            <div class="pd-k2-lbl">Освоено YTD</div>
            <div class="pd-k2-val"><span class="pd-k2-num">{{ project.disbursed_ytd_mln < 1 ? project.disbursed_ytd_mln.toFixed(2) : fmtM(project.disbursed_ytd_mln, 1) }}</span><span class="pd-k2-unit">млн&nbsp;$</span></div>
            <div class="pd-k2-progress"><div class="pd-k2-progress-fill" :style="{ width: Math.min(disbursementPct, 100) + '%', background: disbursementPct < 30 ? '#E24B4A' : '#1D9E75' }"></div></div>
            <div class="pd-k2-sub" :style="{ color: disbursementPct < 30 ? '#A32D2D' : '#5F5E5A' }">{{ fmtPct(disbursementPct, 2) }} от плана 2026{{ disbursementPct < 30 ? ' — riskflag' : '' }}</div>
          </div>

          <div class="pd-k2" style="--ac:#EF9F27;--d:320ms">
            <div class="pd-k2-lbl">Источник</div>
            <div class="pd-k2-src">{{ project.funding_source }}</div>
          </div>

        </div>

        <!-- ROI KPIs (3 cards) -->
        <div class="pd-section-ttl">Финансовая отдача</div>
        <div class="pd-kpi-row pd-kpi-row-3">

          <div class="pd-k2" style="--ac:#1D9E75;--d:400ms">
            <div class="pd-k2-lbl">NPV</div>
            <div class="pd-k2-val">
              <span class="pd-k2-num" :style="{ color: project.npv_mln !== null ? '#0F6E56' : '#888780' }">{{ project.npv_mln !== null ? fmtM(project.npv_mln, 1) : '—' }}</span>
              <span v-if="project.npv_mln !== null" class="pd-k2-unit">млн&nbsp;$</span>
            </div>
            <div class="pd-k2-sub">
              <template v-if="project.npv_mln !== null">{{ fmtPct(npvSharePct, 1) }} NPV портфеля · #{{ npvRank }}</template>
              <template v-else>не рассчитан</template>
            </div>
          </div>

          <div class="pd-k2" :style="{ '--ac': project.irr_pct !== null && project.irr_pct >= 20 ? '#1D9E75' : '#EF9F27', '--d': '480ms' } as any">
            <div class="pd-k2-lbl">IRR</div>
            <div class="pd-k2-val">
              <span class="pd-k2-num" :style="{ color: project.irr_pct !== null && project.irr_pct >= 20 ? '#0F6E56' : project.irr_pct !== null ? '#BA7517' : '#888780' }">{{ project.irr_pct !== null ? project.irr_pct.toFixed(1).replace('.', ',') : '—' }}</span>
              <span v-if="project.irr_pct !== null" class="pd-k2-unit">%</span>
            </div>
            <div class="pd-k2-sub">
              <template v-if="project.irr_pct !== null">#{{ irrRank }} в портфеле</template>
              <template v-else>не рассчитан</template>
            </div>
          </div>

          <div class="pd-k2" :style="{ '--ac': project.payback_years !== null && project.payback_years < portfolioAvgPayback ? '#1D9E75' : '#EF9F27', '--d': '560ms' } as any">
            <div class="pd-k2-lbl">Срок окупаемости</div>
            <div class="pd-k2-val">
              <span class="pd-k2-num">{{ project.payback_years !== null ? project.payback_years.toFixed(1).replace('.', ',') : '—' }}</span>
              <span v-if="project.payback_years !== null" class="pd-k2-unit">лет</span>
            </div>
            <div class="pd-k2-sub">
              <template v-if="project.payback_years !== null">{{ project.payback_years < portfolioAvgPayback ? 'ниже' : 'выше' }} avg ({{ portfolioAvgPayback.toFixed(1).replace('.', ',') }})</template>
              <template v-else>не рассчитан</template>
            </div>
          </div>

        </div>

        <!-- Lifecycle Timeline -->
        <div class="pd-card pd-card-anim" style="--d:640ms">
          <div class="pd-card-head">
            <div class="pd-card-ttl">Жизненный цикл проекта</div>
            <div class="pd-card-meta">{{ totalLifetime }} лет · {{ startYear }} → {{ startYear + totalLifetime }}</div>
          </div>
          <div class="pd-lifecycle">
            <div class="pd-lc-track">
              <div class="pd-lc-fill" :style="{ width: capexPhasePct + '%' }"></div>
            </div>
            <div class="pd-lc-markers">
              <div class="pd-lc-marker" style="left:0">
                <div class="pd-lc-dot" style="background:#7F77DD"></div>
                <div class="pd-lc-marker-lbl">
                  <div class="pd-lc-yr">{{ startYear }}</div>
                  <div class="pd-lc-stage">старт</div>
                </div>
              </div>
              <div class="pd-lc-marker" :style="{ left: capexPhasePct + '%', transform: 'translateX(-50%)' }">
                <div class="pd-lc-dot" style="background:#1D9E75"></div>
                <div class="pd-lc-marker-lbl">
                  <div class="pd-lc-yr" style="color:#0F6E56">{{ endYear }}</div>
                  <div class="pd-lc-stage">пуск</div>
                </div>
              </div>
              <div class="pd-lc-marker" style="left:100%;transform:translateX(-100%)">
                <div class="pd-lc-dot" style="background: var(--bg1, #fff);border:2px solid #888780"></div>
                <div class="pd-lc-marker-lbl pd-lc-marker-end">
                  <div class="pd-lc-yr">{{ startYear + totalLifetime }}</div>
                  <div class="pd-lc-stage">конец</div>
                </div>
              </div>
            </div>
            <div class="pd-lc-phases">
              <div class="pd-lc-phase-lbl" :style="{ left: (capexPhasePct/2) + '%', transform: 'translateX(-50%)' }">CAPEX {{ capexYears }} лет</div>
              <div class="pd-lc-phase-lbl pd-lc-phase-op" :style="{ left: (capexPhasePct + (100 - capexPhasePct)/2) + '%', transform: 'translateX(-50%)' }">эксплуатация {{ lifetimeAfterCapex }} лет</div>
            </div>
          </div>
          <div class="pd-lc-stats">
            <div><span class="pd-lbl-mini">Новые места</span><br><span class="pd-stat-mini">{{ fmtInt(project.new_jobs) }} чел</span></div>
            <div><span class="pd-lbl-mini">Инфраструктура</span><br><span class="pd-stat-mini" :style="{ color: project.infrastructure ? '#0F6E56' : '#A32D2D' }">{{ project.infrastructure ? 'есть' : 'нет' }}</span></div>
            <div><span class="pd-lbl-mini">ТЭО</span><br><span class="pd-stat-mini" :style="{ color: project.fs_status === 'УТВЕРЖДЕНО' ? '#0F6E56' : project.fs_status === 'В ПРОЦЕССЕ' ? '#BA7517' : '#888780' }">{{ project.fs_status === 'УТВЕРЖДЕНО' ? 'УТВ' : project.fs_status === 'В ПРОЦЕССЕ' ? 'В ПРОЦ' : '—' }}</span></div>
            <div><span class="pd-lbl-mini">Освоение</span><br><span class="pd-stat-mini" :style="{ color: disbursementPct < 30 ? '#A32D2D' : '#0F6E56' }">{{ fmtPct(disbursementPct, 2) }}</span></div>
          </div>
        </div>

        <!-- Resources -->
        <div class="pd-card pd-card-anim" style="--d:720ms">
          <div class="pd-card-head">
            <div class="pd-card-ttl">Потребление ресурсов · steady state</div>
            <div class="pd-card-meta">после выхода на проектную мощность</div>
          </div>
          <div class="pd-resources">
            <div class="pd-res">
              <div class="pd-res-head"><svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#EF9F27" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1l-3 7h3l-1 5 5-7H8z"/></svg><span>Энергия</span></div>
              <div class="pd-res-val"><span class="pd-res-num">{{ fmtM(project.energy_mkwh, 1) }}</span><span class="pd-res-unit">Млн кВт·ч</span></div>
              <div class="pd-res-bar"><div class="pd-res-bar-fill" :style="{ width: Math.min(energySharePct, 100) + '%', background: '#EF9F27' }"></div></div>
              <div class="pd-res-sub">{{ fmtPct(energySharePct, 1) }} энергии портфеля{{ energyIntensity !== null ? ` · ${energyIntensity.toFixed(1)} кВт·ч/т` : '' }}</div>
            </div>
            <div class="pd-res">
              <div class="pd-res-head"><svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#378ADD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M7 1c2.5 4 4 6.5 4 8.5a4 4 0 0 1-8 0c0-2 1.5-4.5 4-8.5z"/></svg><span>Вода</span></div>
              <div class="pd-res-val"><span class="pd-res-num">{{ project.water_mm3.toFixed(2).replace('.', ',') }}</span><span class="pd-res-unit">Млн м³</span></div>
              <div class="pd-res-bar"><div class="pd-res-bar-fill" :style="{ width: Math.min(waterSharePct, 100) + '%', background: '#378ADD' }"></div></div>
              <div class="pd-res-sub">{{ fmtPct(waterSharePct, 1) }} воды портфеля</div>
            </div>
            <div class="pd-res">
              <div class="pd-res-head"><svg width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="#9B8EC4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2l3 5 3-5M3 12h8"/></svg><span>Газ</span></div>
              <div class="pd-res-val"><span class="pd-res-num">{{ project.gas_mm3.toFixed(2).replace('.', ',') }}</span><span class="pd-res-unit">Млн м³</span></div>
              <div class="pd-res-bar"><div class="pd-res-bar-fill" :style="{ width: '0%', background: '#9B8EC4' }"></div></div>
              <div class="pd-res-sub">{{ project.gas_mm3 === 0 ? 'не используется' : 'природный газ (технологический)' }}</div>
            </div>
          </div>
        </div>

        <!-- Auto-insights -->
        <div v-if="insights.length > 0" class="pd-insights pd-card-anim" style="--d:800ms">
          <div class="pd-insights-head">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#7F77DD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="6"/><path d="M7 4v3l2 1"/></svg>
            <span>Автоматические инсайты</span>
          </div>
          <div class="pd-insights-list">
            <div v-for="(ins, i) in insights" :key="i" class="pd-insight-row">
              <span class="pd-insight-dot" :style="{ color: insightStyles[ins.type].dot }">●</span>
              <div><span class="pd-insight-title" :style="{ color: insightStyles[ins.type].color }">{{ ins.title }}.</span> {{ ins.text }}</div>
            </div>
          </div>
        </div>

        <!-- Contacts -->
        <div class="pd-contacts pd-card-anim" style="--d:880ms">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#888780" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="5" r="2"/><path d="M2 12c0-2.5 2.2-4 5-4s5 1.5 5 4"/></svg>
          <span class="pd-contacts-lbl">Ответственные</span>
          <div class="pd-contacts-list">{{ project.responsible }}</div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.pd-backdrop {
  position: fixed; inset: 0;
  background: rgba(15,18,40,.45);
  backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);
  z-index: 10000;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 40px 20px; overflow-y: auto;
  animation: pdBgIn .25s ease both;
}
@keyframes pdBgIn { from { opacity: 0; } to { opacity: 1; } }

.pd-modal {
  background: #F4F3F9; border-radius: 16px;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  width: 100%; max-width: 980px; position: relative; overflow: hidden;
  animation: pdModalIn .45s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  font-family: -apple-system, system-ui, 'Segoe UI', sans-serif; color: #2C2C2A;
}
@keyframes pdModalIn { from { opacity: 0; transform: translateY(20px) scale(.96); } to { opacity: 1; transform: translateY(0) scale(1); } }

.pd-top-bar { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: #7F77DD; animation: pdDrawIn .9s cubic-bezier(0.34, 1.2, 0.64, 1) .15s both; z-index: 5; transform-origin: left; }
.pd-top-shimmer { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255,255,255,.6), transparent); animation: pdShimmer 5s ease-in-out 1.4s infinite; transform: translateX(-120%); z-index: 6; pointer-events: none; }
@keyframes pdDrawIn { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0% 0 0); } }
@keyframes pdShimmer { 0%,75% { transform: translateX(-120%); } 85%,100% { transform: translateX(120%); } }
@keyframes pdBreathe { 0%,100% { opacity: 1; } 50% { opacity: .45; } }

.pd-header {
  background: linear-gradient(180deg, #1E2A4A 0%, #1A2440 100%);
  padding: 16px 22px; color: #fff;
  display: flex; align-items: flex-start; justify-content: space-between; gap: 14px;
}
.pd-header-l { flex: 1; min-width: 0; }
.pd-pills { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.pd-eyebrow { font-size: 9px; color: rgba(255,255,255,.5); text-transform: uppercase; letter-spacing: .08em; font-weight: 500; }
.pd-pill { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; padding: 2px 8px; border-radius: 11px; font-weight: 500; }
.pd-pill-purple { background: rgba(127,119,221,.25); color: #CECBF6; border: 1px solid rgba(127,119,221,.35); }
.pd-title { font-size: 15px; font-weight: 500; letter-spacing: -.005em; line-height: 1.3; }
.pd-meta { font-size: 10.5px; color: rgba(255,255,255,.6); margin-top: 4px; line-height: 1.4; }

.pd-header-r { display: flex; gap: 6px; align-items: center; flex-shrink: 0; }
.pd-btn-edit { font-size: 11px; padding: 6px 12px; border: 1px solid rgba(255,255,255,.18); background: rgba(255,255,255,.06); border-radius: 6px; color: rgba(255,255,255,.85); font-weight: 500; cursor: pointer; transition: all .15s; }
.pd-btn-edit:hover { background: rgba(255,255,255,.14); color: #fff; }
.pd-btn-icon { width: 30px; height: 30px; border: 1px solid rgba(255,255,255,.15); background: rgba(255,255,255,.06); border-radius: 6px; display: flex; align-items: center; justify-content: center; color: rgba(255,255,255,.7); cursor: pointer; transition: all .15s; }
.pd-btn-icon:hover { background: rgba(255,255,255,.14); color: #fff; }

.pd-body { padding: 18px 22px; }

.pd-section-ttl { font-size: 10px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin-bottom: 9px; }

.pd-kpi-row { display: grid; gap: 9px; margin-bottom: 14px; }
.pd-kpi-row-4 { grid-template-columns: repeat(4, 1fr); }
.pd-kpi-row-3 { grid-template-columns: repeat(3, 1fr); }

.pd-k2 {
  position: relative; overflow: hidden;
  background: rgba(255,255,255,.92); border: 1px solid rgba(255,255,255,.7); border-radius: 12px;
  padding: 12px 14px 10px; box-shadow: 0 2px 8px rgba(15,23,60,.06);
  transition: transform .2s, box-shadow .2s;
}
.pd-k2:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(15,23,60,.1); }
.pd-k2::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--ac, #7F77DD); border-radius: 12px 12px 0 0;
  animation: pdDrawIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both,
             pdBreathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite;
  transform-origin: left;
}
.pd-k2::after {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  border-radius: 12px 12px 0 0;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
  animation: pdShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) infinite;
  transform: translateX(-120%);
}
.pd-k2-lbl { font-size: 9px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; margin-bottom: 5px; }
.pd-k2-val { display: flex; align-items: baseline; gap: 4px; }
.pd-k2-num { font-size: 20px; font-weight: 400; letter-spacing: -.025em; color: #2C2C2A; font-variant-numeric: tabular-nums; }
.pd-k2-unit { font-size: 10px; color: var(--t3, #888780); font-weight: 500; }
.pd-k2-sub { font-size: 9.5px; color: var(--t3, #888780); margin-top: 4px; }
.pd-k2-src { font-size: 11px; font-weight: 500; line-height: 1.35; margin-top: 2px; }
.pd-k2-progress { height: 3px; background: #E5E4EE; border-radius: 3px; margin-top: 5px; overflow: hidden; }
.pd-k2-progress-fill { height: 100%; border-radius: 3px; animation: pdBarFill 1.4s cubic-bezier(0.34, 1.2, 0.64, 1) both; transform-origin: left; }
@keyframes pdBarFill { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* Generic card */
.pd-card { background: var(--bg1, #fff); border-radius: 12px; padding: 14px 16px; border: 1px solid rgba(0,0,0,.05); margin-bottom: 12px; }
.pd-card-anim { animation: pdFadeIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both; }
@keyframes pdFadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.pd-card-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.pd-card-ttl { font-size: 12px; font-weight: 500; }
.pd-card-meta { font-size: 9.5px; color: var(--t3, #888780); }

/* Lifecycle */
.pd-lifecycle { position: relative; height: 50px; margin-bottom: 8px; }
.pd-lc-track { position: absolute; top: 22px; left: 0; right: 0; height: 4px; background: #F0EFF5; border-radius: 2px; }
.pd-lc-fill { height: 100%; background: #7F77DD; border-radius: 2px; animation: pdBarFill 1.4s cubic-bezier(0.34, 1.2, 0.64, 1) both; transform-origin: left; }
.pd-lc-markers { position: absolute; top: 0; left: 0; right: 0; height: 50px; }
.pd-lc-marker { position: absolute; top: 0; }
.pd-lc-dot { width: 12px; height: 12px; border-radius: 50%; margin-top: 18px; box-shadow: 0 1px 4px rgba(0,0,0,.15); }
.pd-lc-marker-lbl { position: absolute; top: 34px; }
.pd-lc-marker-end .pd-lc-marker-lbl { right: 0; }
.pd-lc-yr { font-size: 9px; font-weight: 500; color: var(--t3, #888780); }
.pd-lc-stage { font-size: 8px; color: var(--t3, #888780); }
.pd-lc-phases { position: absolute; top: 4px; left: 0; right: 0; height: 14px; }
.pd-lc-phase-lbl { position: absolute; font-size: 8.5px; color: var(--t3, #888780); background: var(--bg1, #fff); padding: 1px 5px; border-radius: 3px; border: 1px solid #E5E4EE; white-space: nowrap; }
.pd-lc-phase-op { color: #0F6E56; background: #E1F5EE; border-color: transparent; }
.pd-lc-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 9.5px; padding-top: 10px; border-top: 1px solid #F0EFF5; margin-top: 8px; }
.pd-lbl-mini { color: var(--t3, #888780); }
.pd-stat-mini { font-weight: 500; font-size: 11px; }

/* Resources */
.pd-resources { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.pd-res-head { display: flex; align-items: center; gap: 7px; margin-bottom: 5px; font-size: 10px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; }
.pd-res-val { display: flex; align-items: baseline; gap: 4px; margin-bottom: 3px; }
.pd-res-num { font-size: 17px; font-weight: 400; letter-spacing: -.02em; }
.pd-res-unit { font-size: 9.5px; color: var(--t3, #888780); }
.pd-res-bar { height: 4px; background: #F0EFF5; border-radius: 3px; overflow: hidden; margin-bottom: 3px; }
.pd-res-bar-fill { height: 100%; animation: pdBarFill 1.4s cubic-bezier(0.34, 1.2, 0.64, 1) both; transform-origin: left; }
.pd-res-sub { font-size: 9px; color: var(--t3, #888780); }

/* Insights */
.pd-insights { background: linear-gradient(90deg, rgba(127,119,221,.04) 0%, rgba(29,158,117,.04) 100%); border-radius: 12px; padding: 13px 16px; border: 1px solid rgba(127,119,221,.2); margin-bottom: 12px; }
.pd-insights-head { display: flex; align-items: center; gap: 8px; margin-bottom: 9px; font-size: 11.5px; font-weight: 500; color: #3C3489; }
.pd-insights-list { display: flex; flex-direction: column; gap: 6px; font-size: 10.5px; line-height: 1.55; }
.pd-insight-row { display: flex; gap: 7px; align-items: flex-start; }
.pd-insight-dot { flex-shrink: 0; font-size: 8px; line-height: 1.6; }
.pd-insight-title { font-weight: 500; }

/* Contacts */
.pd-contacts { background: var(--bg1, #fff); border-radius: 12px; padding: 12px 16px; border: 1px solid rgba(0,0,0,.05); display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.pd-contacts-lbl { font-size: 10px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; font-weight: 500; }
.pd-contacts-list { font-size: 10.5px; color: #2C2C2A; flex: 1; }

/* Header action menu (⋯) */
.pd-menu-wrap { position: relative; display: inline-flex; }
.pd-menu {
  position: absolute;
  right: 0;
  top: calc(100% + 6px);
  min-width: 220px;
  background: var(--bg1, #fff);
  border: 0.5px solid #E5E7EB;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, .14);
  padding: 4px;
  z-index: 100;
}
.pd-menu-item {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: transparent;
  border-radius: 5px;
  color: var(--t1, #1E2A4A);
  font-size: 11.5px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background .12s, color .12s;
}
.pd-menu-item:hover { background: rgba(127, 119, 221, .08); color: #534AB7; }

/* ─── Inline edit form ─── */
.pd-edit-form {
  background: var(--bg2, #FAFAFC);
  border-bottom: 0.5px solid #E5E7EB;
  padding: 16px 22px;
}
.pd-edit-head {
  display: flex; flex-direction: column; gap: 3px;
  margin-bottom: 12px;
}
.pd-edit-title {
  font-size: 12px; font-weight: 500;
  color: var(--t1, #1E2A4A); letter-spacing: -.01em;
}
.pd-edit-hint { font-size: 10.5px; color: var(--t3, #888780); }
.pd-edit-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 12px;
}
.pd-edit-fld { display: flex; flex-direction: column; gap: 3px; }
.pd-edit-fld-wide { grid-column: span 3; }
.pd-edit-fld > span {
  font-size: 9.5px; font-weight: 500;
  color: var(--t3, #888780); letter-spacing: .06em; text-transform: uppercase;
}
.pd-edit-input {
  height: 28px; padding: 0 9px;
  border: 0.5px solid #E5E7EB; border-radius: 6px;
  font-size: 11.5px; font-family: inherit;
  background: var(--bg1, #fff); color: var(--t1, #1E2A4A); outline: none;
}
.pd-edit-input:focus { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, .15); }
.pd-edit-input[type="number"] { font-variant-numeric: tabular-nums; }
select.pd-edit-input { padding-right: 24px; }
.pd-edit-err {
  margin-top: 10px;
  padding: 6px 10px;
  background: rgba(226, 75, 74, .06);
  color: #C0322F;
  border-radius: 5px;
  font-size: 11px;
}
.pd-edit-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 12px;
}
.pd-edit-btn-cancel, .pd-edit-btn-save {
  height: 28px; padding: 0 16px;
  border-radius: 6px; font-size: 11.5px;
  font-family: inherit; font-weight: 500;
  cursor: pointer;
}
.pd-edit-btn-cancel {
  background: transparent;
  border: 0.5px solid #E5E7EB;
  color: var(--t3, #888780);
}
.pd-edit-btn-save {
  background: #7F77DD; color: #fff; border: none;
}
.pd-edit-btn-save:hover:not(:disabled) { background: #6B62D6; }
.pd-edit-btn-save:disabled { opacity: .5; cursor: not-allowed; }

.pd-edit-fade-enter-active, .pd-edit-fade-leave-active {
  transition: opacity .2s, max-height .25s ease;
  overflow: hidden;
}
.pd-edit-fade-enter-from, .pd-edit-fade-leave-to {
  opacity: 0; max-height: 0;
}
.pd-edit-fade-enter-to, .pd-edit-fade-leave-from {
  opacity: 1; max-height: 600px;
}
</style>
