/**
 * Moderation API for the TWA bundle (Phase C, Session 4).
 *
 * Thin wrappers over the existing /moderation/* endpoints that the desktop
 * frontend already uses. Schema mirrors backend SubmissionRead.
 */
import { api } from "./client";

export type ModSubmissionStatus =
  | "pending"
  | "in_review"
  | "approved"
  | "rejected"
  | "withdrawn"
  | "applied"
  | "apply_failed";

export interface ModSubmission {
  id: string;
  target_module: string;       // "kpi" | "procurement" | "bp" | "financials" | ...
  target_action: string;       // "update" | "create" | ...
  target_entity_id?: string | null;
  target_entity_label?: string | null;
  status: ModSubmissionStatus;
  proposer_user_id: string;
  proposer_email?: string | null;
  proposer_name?: string | null;
  assigned_moderator_id?: string | null;
  coapprover_id?: string | null;
  current_value?: unknown;
  proposed_value?: unknown;
  field_path?: string | null;
  reason?: string | null;
  note?: string | null;
  created_at: string;
  reviewed_at?: string | null;
  apply_status?: string | null;
  apply_error?: string | null;
  meta?: Record<string, unknown> | null;
}

export interface ModSubmissionList {
  items: ModSubmission[];
  total: number;
  counts_by_status: Record<string, number>;
  page: number;
  per_page: number;
}

export const moderationApi = {
  /** GET /moderation/queue — supports status filter and assigned_to=me */
  queue(params: { status?: string[]; assignedToMe?: boolean; module?: string; page?: number; per_page?: number } = {}) {
    const qs: Record<string, string | string[] | number | undefined> = {};
    if (params.status?.length)  qs.status = params.status;
    if (params.assignedToMe)    qs.assigned_to = "me";
    if (params.module)          qs.module = params.module;
    if (params.page)            qs.page = params.page;
    if (params.per_page)        qs.per_page = params.per_page;
    return api.get<ModSubmissionList>("/moderation/queue", { params: qs }).then(r => r.data);
  },

  /** GET /moderation/my-submissions — what I submitted */
  mine(params: { status?: string[]; page?: number; per_page?: number } = {}) {
    const qs: Record<string, string | string[] | number | undefined> = {};
    if (params.status?.length) qs.status = params.status;
    if (params.page)           qs.page = params.page;
    if (params.per_page)       qs.per_page = params.per_page;
    return api.get<ModSubmissionList>("/moderation/my-submissions", { params: qs }).then(r => r.data);
  },

  /** GET /moderation/submissions/{id} */
  get(id: string) {
    return api.get<ModSubmission>(`/moderation/submissions/${id}`).then(r => r.data);
  },

  approve(id: string, note?: string) {
    return api.post<ModSubmission>(
      `/moderation/submissions/${id}/approve`,
      { note: note ?? null },
    ).then(r => r.data);
  },

  reject(id: string, note?: string) {
    return api.post<ModSubmission>(
      `/moderation/submissions/${id}/reject`,
      { note: note ?? null },
    ).then(r => r.data);
  },
};

// ── Display helpers ─────────────────────────────────────────────────────

export function moduleLabel(module: string): string {
  return ({
    kpi:         "KPI",
    bp:          "Бизнес-план",
    procurement: "Закупки",
    financials:  "Финансы",
    governance:  "Корп. упр.",
    esg:         "ESG",
    forensic:    "Forensic",
    credit:      "Кредит",
    invest:      "Инвестпроекты",
    ratings:     "Рейтинги",
    tasks:       "Задачи",
  } as Record<string, string>)[module.toLowerCase()] || module;
}

export function statusLabel(s: ModSubmissionStatus): string {
  return ({
    pending:      "Ожидает",
    in_review:    "В рассмотрении",
    approved:     "Утверждено",
    rejected:     "Отклонено",
    withdrawn:    "Отозвано",
    applied:      "Применено",
    apply_failed: "Ошибка применения",
  } as Record<string, string>)[s] || s;
}

export function statusTone(s: ModSubmissionStatus): "info" | "success" | "warning" | "danger" {
  if (s === "approved" || s === "applied") return "success";
  if (s === "rejected" || s === "apply_failed" || s === "withdrawn") return "danger";
  if (s === "in_review") return "warning";
  return "info";
}
