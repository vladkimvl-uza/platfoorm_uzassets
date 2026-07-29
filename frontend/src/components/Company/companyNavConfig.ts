/**
 * Company Navigation — static config for CompanyHeader + CompanyTabBar.
 *
 * IMPORTANT: TabId values match the existing CompanyWorkspace URL keys
 * (`?tab=ifrs`, `?tab=bp`, `?tab=governance`) so the new nav components
 * are a drop-in replacement that preserves URL routing and the existing
 * `v-else-if="activeTab === '...'"` chain in CompanyWorkspace.vue.
 *
 * Labels and group structure follow company-nav-redesign-handoff.md spec.
 */

export type TabId =
  | 'overview' | 'people'
  | 'work' | 'kanban' | 'list' | 'notes' | 'pmo' | 'reporting'
  | 'ifrs' | 'nsbu' | 'hlf' | 'bp' | 'unitcost' | 'credit'
  | 'invest' | 'kpi' | 'procurement'
  | 'governance' | 'consultants' | 'esg';

export type GroupId = 'overview' | 'tasks' | 'finance' | 'performance' | 'governance';

export type AlertLevel = 'critical' | 'warning' | null;

export interface TabConfig {
  id: TabId;
  label: string;
  groupId: GroupId;
  /** Если задано — вкладка видна только при праве `<gated>.view`
   *  (через usePermissions). Напр. 'pmo' → нужен `pmo.view`. */
  gated?: string;
}

export interface TabIndicators {
  badge?: number;
  alert?: AlertLevel;
  alertTooltip?: string;
}

// All 14 tabs, left-to-right, in 5 groups.
export const COMPANY_TABS: TabConfig[] = [
  { id: 'overview',    label: 'Обзор',          groupId: 'overview' },
  { id: 'people',      label: 'Сотрудники',     groupId: 'overview' },

  // Канбан + Список объединены в «Работа» (переключатель вида внутри таба).
  { id: 'work',        label: 'Работа',         groupId: 'tasks' },
  // PMO — только для роли с правом pmo.view (расписание/Гантт; позже RAID/здоровье).
  { id: 'pmo',         label: 'PMO',            groupId: 'tasks', gated: 'pmo' },
  { id: 'notes',       label: 'Календарь',      groupId: 'tasks' },
  { id: 'reporting',   label: 'Отчёт',          groupId: 'tasks' },

  { id: 'ifrs',        label: 'МСФО',           groupId: 'finance' },
  { id: 'nsbu',        label: 'НСБУ',           groupId: 'finance' },
  { id: 'hlf',         label: 'Фин. отчётность', groupId: 'finance' },
  { id: 'bp',          label: 'Бизнес-план',    groupId: 'finance' },
  // Себестоимость — тот же бэкенд, что и полноэкранный /unit-cost, поэтому и
  // право то же (unit_cost.view). Без гейта вкладка осталась бы окном в модуль
  // в обход его собственного права.
  { id: 'unitcost',    label: 'Себестоимость',  groupId: 'finance', gated: 'unit_cost' },

  { id: 'kpi',         label: 'KPI',            groupId: 'performance' },
  // Закупки во вкладке читают procurementAnalysisApi — то же право, что у
  // полноэкранного /procurement/analysis, а не форензик-право procurement.view.
  { id: 'procurement', label: 'Закупки',        groupId: 'performance', gated: 'procurement_analysis' },

  { id: 'governance',  label: 'Корп. упр.',     groupId: 'governance' },
  { id: 'consultants', label: 'Консультанты',   groupId: 'governance' },
  { id: 'esg',         label: 'ESG',            groupId: 'governance' },
];

// Default indicators — все пустые. Caller must pass real ones via `:indicators` prop.
// 2026-05-26: были hardcoded mock-цифры (24/87/14/7/234, dots etc.) которые
// не отражали реальное состояние и не реагировали на смену года → user видел
// постоянные «фейковые» числа. Очищены — теперь чипы показываются ТОЛЬКО когда
// CompanyWorkspace передаёт real-time данные.
export const MOCK_INDICATORS: Record<TabId, TabIndicators> = {
  overview:    {},
  people:      {},
  work:        {},
  kanban:      {},
  list:        {},
  pmo:         {},
  notes:       {},
  reporting:   {},
  ifrs:        {},
  nsbu:        {},
  hlf:         {},
  bp:          {},
  unitcost:    {},
  credit:      {},
  invest:      {},
  kpi:         {},
  procurement: {},
  governance:  {},
  consultants: {},
  esg:         {},
};

// Sector mapping for header badge.
export type SectorId = 'mining' | 'oil' | 'energy' | 'transport' | 'telecom' | 'other';

export interface SectorMeta {
  bg: string;
  text: string;
}

export const SECTOR_META: Record<SectorId, SectorMeta> = {
  mining:    { bg: '#E1F5EE', text: '#0F6E56' },
  oil:       { bg: '#E1ECFA', text: '#1E4584' },
  energy:    { bg: '#FAF0DC', text: '#9C6E2D' },
  transport: { bg: '#EFE9FA', text: '#534AB7' },
  telecom:   { bg: '#FAE9E9', text: '#C73E3E' },
  other:     { bg: '#F1EFE8', text: '#888780' },
};
