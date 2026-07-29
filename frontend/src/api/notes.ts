/**
 * Smart Journal API client.
 * Backend: /backend/app/api/routes/notes.py
 */
import { api } from "./client";
import { i18nKey } from "@/locale/keys";

export type NoteKind = "event" | "decision" | "task" | "risk" | "observation";

export const NOTE_KINDS: NoteKind[] = ["event", "decision", "task", "risk", "observation"];

export const NOTE_KIND_LABELS: Record<NoteKind, string> = {
  event: i18nKey("Событие"),
  decision: i18nKey("Решение"),
  task: i18nKey("Задача"),
  risk: i18nKey("Риск"),
  observation: i18nKey("Наблюдение"),
};

export const NOTE_KIND_COLORS: Record<NoteKind, string> = {
  event: "#1D9E75",
  decision: "#7F77DD",
  task: "#EF9F27",
  risk: "#E24B4A",
  observation: "#378ADD",
};

export const NOTE_KIND_ICONS: Record<NoteKind, string> = {
  event: '<circle cx="8" cy="8" r="3.5" fill="currentColor"/>',
  decision: '<path d="M8 1.5 L14.5 8 L8 14.5 L1.5 8 Z" fill="none" stroke="currentColor" stroke-width="2"/>',
  task: '<path d="M2 8 L12 8 M9 5 L12 8 L9 11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  risk: '<path d="M8 1.5 L15 14 L1 14 Z M8 6 L8 10 M8 12 L8 12.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>',
  observation: '<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="2"/>',
};

export type LinkEntityType = "project" | "task" | "kpi_indicator" | "kpi_manager" | "esg_issue" | "esg_metric" | "board_member" | "loan" | "consultant" | "bp_metric" | "financial_line" | "procurement_contract" | "rating";

export const LINK_ENTITY_LABELS: Record<LinkEntityType, string> = {
  project: i18nKey("Проект"),
  task: i18nKey("Задача"),
  kpi_indicator: i18nKey("KPI индикатор"),
  kpi_manager: i18nKey("KPI руководитель"),
  esg_issue: i18nKey("ESG issue"),
  esg_metric: i18nKey("ESG метрика"),
  board_member: i18nKey("Член совета"),
  loan: i18nKey("Кредит"),
  consultant: i18nKey("Консультант"),
  bp_metric: i18nKey("Бизнес-план"),
  financial_line: i18nKey("Фин. строка"),
  procurement_contract: i18nKey("Закупка"),
  rating: i18nKey("Рейтинг"),
};

export interface NoteLink {
  id?: string;
  note_id?: string;
  entity_type: LinkEntityType;
  entity_id?: string | null;
  entity_key?: string | null;
  entity_label?: string | null;
  created_at?: string;
}

// Пункт чек-листа (read из API)
export interface ChecklistItem {
  id: string;
  note_id: string;
  text: string;
  is_done: boolean;
  position: number;
  assignee_id?: string | null;
  assignee_name?: string | null;
  due_date?: string | null;
  done_at?: string | null;
  created_at: string;
}

// Желаемое состояние пункта в payload create/update заметки. id есть у
// существующих пунктов (для diff), отсутствует у новых.
export interface ChecklistItemIn {
  id?: string | null;
  text: string;
  is_done?: boolean;
  position?: number;
  assignee_id?: string | null;
  assignee_name?: string | null;
  due_date?: string | null;
}

export interface ChecklistItemPatch {
  text?: string;
  is_done?: boolean;
  position?: number;
  assignee_id?: string | null;
  assignee_name?: string | null;
  due_date?: string | null;
}

export interface Note {
  id: string;
  user_id?: string | null;
  author_id?: string | null;
  company_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  kind: NoteKind;
  title?: string | null;
  body: string;
  tags: string[];
  color?: string | null;
  is_pinned: boolean;
  event_date?: string | null;
  due_date?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  is_resolved: boolean;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
  links: NoteLink[];
  checklist: ChecklistItem[];
}

export interface NoteCreate {
  company_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  kind?: NoteKind;
  title?: string | null;
  body: string;
  tags?: string[];
  color?: string | null;
  is_pinned?: boolean;
  event_date?: string | null;
  due_date?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  links?: NoteLink[];
  checklist?: ChecklistItemIn[];
}

export interface NoteUpdate {
  company_id?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  kind?: NoteKind;
  title?: string | null;
  body?: string;
  tags?: string[];
  color?: string | null;
  is_pinned?: boolean;
  event_date?: string | null;
  due_date?: string | null;
  assignee_id?: string | null;
  assignee_name?: string | null;
  is_resolved?: boolean;
  links?: NoteLink[];
  checklist?: ChecklistItemIn[];
}

export interface TagCount {
  tag: string;
  count: number;
}

export interface NoteListResponse {
  items: Note[];
  total: number;
  tag_counts: TagCount[];
}

export interface ListNotesParams {
  company_id?: string;
  kind?: NoteKind[];
  tag?: string[];
  q?: string;
  only_unresolved?: boolean;
  include_resolved?: boolean;
  pinned_first?: boolean;
  limit?: number;
  offset?: number;
}

const BASE = "/notes";

function _toUrlSearchParams(p: ListNotesParams): URLSearchParams {
  const usp = new URLSearchParams();
  if (p.company_id) usp.set("company_id", p.company_id);
  if (p.kind && p.kind.length) p.kind.forEach((k) => usp.append("kind", k));
  if (p.tag && p.tag.length) p.tag.forEach((t) => usp.append("tag", t));
  if (p.q) usp.set("q", p.q);
  if (p.only_unresolved) usp.set("only_unresolved", "true");
  if (p.include_resolved === false) usp.set("include_resolved", "false");
  if (p.pinned_first === false) usp.set("pinned_first", "false");
  if (p.limit !== undefined) usp.set("limit", String(p.limit));
  if (p.offset !== undefined) usp.set("offset", String(p.offset));
  return usp;
}

export const notesApi = {
  async list(params: ListNotesParams = {}): Promise<NoteListResponse> {
    const usp = _toUrlSearchParams(params);
    const qs = usp.toString();
    const url = qs ? `${BASE}?${qs}` : BASE;
    const r = await api.get<NoteListResponse>(url);
    return r.data;
  },
  async create(payload: NoteCreate): Promise<Note> {
    const r = await api.post<Note>(BASE, payload);
    return r.data;
  },
  async update(id: string, payload: NoteUpdate): Promise<Note> {
    const r = await api.patch<Note>(`${BASE}/${id}`, payload);
    return r.data;
  },
  async delete(id: string): Promise<void> {
    await api.delete(`${BASE}/${id}`);
  },
  /** Точечно обновить пункт чек-листа (галочка с карточки / inline-правка). */
  async patchChecklistItem(itemId: string, payload: ChecklistItemPatch): Promise<Note> {
    const r = await api.patch<Note>(`${BASE}/checklist/${itemId}`, payload);
    return r.data;
  },
  async tags(company_id?: string): Promise<TagCount[]> {
    const url = company_id ? `${BASE}/tags?company_id=${company_id}` : `${BASE}/tags`;
    const r = await api.get<TagCount[]>(url);
    return r.data;
  },
  async byEntity(entity_type: LinkEntityType, entity_id?: string, entity_key?: string): Promise<Note[]> {
    const usp = new URLSearchParams({ entity_type });
    if (entity_id) usp.set("entity_id", entity_id);
    if (entity_key) usp.set("entity_key", entity_key);
    const r = await api.get<Note[]>(`${BASE}/by-entity?${usp.toString()}`);
    return r.data;
  },
};
