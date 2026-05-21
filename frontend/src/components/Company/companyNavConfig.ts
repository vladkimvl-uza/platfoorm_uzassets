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
  | 'ifrs' | 'nsbu' | 'bp' | 'credit'
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
  { id: 'bp',          label: 'Бизнес-план',    groupId: 'finance' },
  { id: 'credit',      label: 'Кредит',         groupId: 'finance' },

  { id: 'invest',      label: 'Инвест-проекты', groupId: 'performance' },
  { id: 'kpi',         label: 'KPI',            groupId: 'performance' },
  { id: 'procurement', label: 'Закупки',        groupId: 'performance' },

  { id: 'governance',  label: 'Корп. упр.',     groupId: 'governance' },
  { id: 'consultants', label: 'Консультанты',   groupId: 'governance' },
  { id: 'esg',         label: 'ESG',            groupId: 'governance' },
];

// Mock indicators — replace with real API later (caller can override via prop).
export const MOCK_INDICATORS: Record<TabId, TabIndicators> = {
  overview:    {},
  kanban:      { badge: 24 },
  list:        { badge: 87 },
  notes:       {},
  ifrs:        {},
  nsbu:        { alert: 'critical', alertTooltip: 'Баланс не сошёлся' },
  bp:          {},
  credit:      { badge: 14, alert: 'warning', alertTooltip: '2 просрочки' },
  invest:      { badge: 7 },
  kpi:         {},
  procurement: { badge: 234 },
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
