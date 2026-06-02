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
  | 'overview'
  | 'kanban' | 'list' | 'notes'
  | 'ifrs' | 'nsbu' | 'hlf' | 'bp' | 'credit'
  | 'invest' | 'kpi' | 'procurement'
  | 'governance' | 'consultants' | 'esg';

export type GroupId = 'overview' | 'tasks' | 'finance' | 'performance' | 'governance';

export type AlertLevel = 'critical' | 'warning' | null;

export interface TabConfig {
  id: TabId;
  label: string;
  groupId: GroupId;
}

export interface TabIndicators {
  badge?: number;
  alert?: AlertLevel;
  alertTooltip?: string;
}

// All 14 tabs, left-to-right, in 5 groups.
export const COMPANY_TABS: TabConfig[] = [
  { id: 'overview',    label: 'Обзор',          groupId: 'overview' },

  { id: 'kanban',      label: 'Канбан',         groupId: 'tasks' },
  { id: 'list',        label: 'Список',         groupId: 'tasks' },
  { id: 'notes',       label: 'Заметки',        groupId: 'tasks' },

  { id: 'ifrs',        label: 'МСФО',           groupId: 'finance' },
  { id: 'nsbu',        label: 'НСБУ',           groupId: 'finance' },
  { id: 'hlf',         label: 'Фин. отчётность', groupId: 'finance' },
  { id: 'bp',          label: 'Бизнес-план',    groupId: 'finance' },
  // 2026-05-26: 'credit' и 'invest' скрыты по запросу — раскомментировать для возврата
  // { id: 'credit',      label: 'Кредит',         groupId: 'finance' },
  // { id: 'invest',      label: 'Инвест-проекты', groupId: 'performance' },

  { id: 'kpi',         label: 'KPI',            groupId: 'performance' },
  { id: 'procurement', label: 'Закупки',        groupId: 'performance' },

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
  kanban:      {},
  list:        {},
  notes:       {},
  ifrs:        {},
  nsbu:        {},
  hlf:         {},
  bp:          {},
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
