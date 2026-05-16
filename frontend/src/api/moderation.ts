import { api } from "./client";

// ─── Types ─────────────────────────────────────────────────────

export type SubmissionStatus = "pending" | "under_review" | "approved" | "rejected" | "withdrawn" | "expired";
export type ApprovalMode = "any" | "dual" | "sequential";
export type ModAction = "edit" | "replace" | "comment" | "upload" | "delete" | "status_change";

export interface Submission {
  id: string;
  created_at: string;
  updated_at: string;
  proposer_user_id: string;
  proposer_is_external: boolean;
  target_module: string;
  target_entity_id: string | null;
  target_entity_label: string | null;
  target_field: string | null;
  target_company_id: string | null;
  target_sector_id: string | null;
  action: ModAction;
  proposed_value: Record<string, unknown> | null;
  original_value: Record<string, unknown> | null;
  diff_summary: string | null;
  attachments: Record<string, unknown>[] | null;
  reason: string | null;
  status: SubmissionStatus;
  rule_id: string | null;
  assigned_moderator_id: string | null;
  coapprover_id: string | null;
  approval_mode: ApprovalMode;
  approvals_given: { user_id: string; at: string }[];
  resolved_at: string | null;
  resolved_by_id: string | null;
  resolution_note: string | null;
  auto_resolved: boolean;
  expires_at: string | null;
}

export interface SubmissionListItem extends Pick<Submission,
  "id" | "created_at" | "proposer_user_id" | "proposer_is_external" |
  "target_module" | "target_entity_label" | "target_field" |
  "action" | "status" | "assigned_moderator_id" | "expires_at" | "diff_summary"> {}

export interface SubmissionListResponse {
  items: SubmissionListItem[];
  total: number;
  counts_by_status: Record<string, number>;
  page: number;
  per_page: number;
}

export interface Comment {
  id: string;
  created_at: string;
  submission_id: string;
  user_id: string | null;
  text: string;
  attachments: Record<string, unknown>[] | null;
  is_internal: boolean;
}

export interface RuleConditionAtom {
  field: string;
  op: "=" | "!=" | ">" | ">=" | "<" | "<=" | "in" | "not_in" | "abs>" | "delta>";
  value: unknown;
  unit?: string | null;
}

export interface Rule {
  id: string;
  created_at: string;
  updated_at: string;
  created_by_id: string | null;
  version: number;
  name: string;
  description: string | null;
  icon: string | null;
  is_active: boolean;
  sort_order: number;

  trigger_user_ids: string[] | null;
  trigger_group_codes: string[] | null;
  trigger_role_codes: string[] | null;
  trigger_is_external: boolean;
  trigger_modules: string[] | null;
  trigger_company_ids: string[] | null;
  trigger_sector_ids: string[] | null;
  trigger_year_from: number | null;
  trigger_year_to: number | null;
  trigger_actions: ModAction[] | null;
  trigger_conditions: RuleConditionAtom[] | null;

  moderator_primary_id: string | null;
  moderator_coapprover_id: string | null;
  moderator_fallback_group_code: string | null;
  approval_mode: ApprovalMode;

  escalate_after_hours: number | null;
  auto_approve_after_hours: number | null;
  expire_after_days: number;

  notify_proposer_assigned: boolean;
  notify_proposer_resolved: boolean;
  notify_coapprovers_cc: boolean;
  notify_owner_on_reject: boolean;
  log_to_audit: boolean;

  last_matched_at: string | null;
  total_matches: number;
  total_approvals: number;
  total_rejections: number;
}

export type RulePayload = Omit<Rule,
  "id" | "created_at" | "updated_at" | "created_by_id" | "version" |
  "last_matched_at" | "total_matches" | "total_approvals" | "total_rejections">;

export interface ModerationOverview {
  pending: number;
  under_review: number;
  resolved_today: number;
  approved_today: number;
  rejected_today: number;
  avg_resolution_hours: number | null;
  my_pending_count: number;
  moderators_count: number;
  external_users_count: number;
  rules_active_count: number;
  rules_total_count: number;
}

export interface ModuleInfo { code: string; label: string; icon: string }
export interface ActionInfo { code: string; label: string }
export interface ModeratorUser {
  id: string; email: string; full_name: string;
  is_owner: boolean; is_active: boolean;
  job_title: string | null; department: string | null;
}
export interface SubmittedUser {
  id: string; email: string; full_name: string;
  is_external: boolean; requires_moderation: boolean;
  bypass_moderation: boolean; external_org_name: string | null;
  is_active: boolean; job_title: string | null;
}


// ─── API ───────────────────────────────────────────────────────

export const moderationApi = {
  // Overview
  async overview(): Promise<ModerationOverview> {
    const r = await api.get<ModerationOverview>("/moderation/overview");
    return r.data;
  },
  async catalog(): Promise<{ modules: ModuleInfo[]; actions: ActionInfo[] }> {
    const r = await api.get<{ modules: ModuleInfo[]; actions: ActionInfo[] }>("/moderation/catalog");
    return r.data;
  },

  // Queue
  async queue(params: {
    status?: SubmissionStatus[];
    assigned_to?: string;
    module?: string;
    proposer_user_id?: string;
    page?: number;
    per_page?: number;
  } = {}): Promise<SubmissionListResponse> {
    const r = await api.get<SubmissionListResponse>("/moderation/queue", { params });
    return r.data;
  },
  async mySubmissions(params: { status?: SubmissionStatus[]; page?: number; per_page?: number } = {}): Promise<SubmissionListResponse> {
    const r = await api.get<SubmissionListResponse>("/moderation/my-submissions", { params });
    return r.data;
  },

  // Submissions CRUD
  async create(payload: Partial<Submission>): Promise<Submission> {
    const r = await api.post<Submission>("/moderation/submissions", payload);
    return r.data;
  },
  async get(id: string): Promise<Submission> {
    const r = await api.get<Submission>(`/moderation/submissions/${id}`);
    return r.data;
  },
  async approve(id: string, note?: string): Promise<Submission> {
    const r = await api.post<Submission>(`/moderation/submissions/${id}/approve`, { note });
    return r.data;
  },
  async reject(id: string, note?: string): Promise<Submission> {
    const r = await api.post<Submission>(`/moderation/submissions/${id}/reject`, { note });
    return r.data;
  },
  async setReview(id: string, note?: string): Promise<Submission> {
    const r = await api.post<Submission>(`/moderation/submissions/${id}/set-review`, { note });
    return r.data;
  },
  async editAndApprove(id: string, proposed_value: Record<string, unknown>, note?: string): Promise<Submission> {
    const r = await api.post<Submission>(`/moderation/submissions/${id}/edit-and-approve`, { proposed_value, note });
    return r.data;
  },
  async withdraw(id: string): Promise<Submission> {
    const r = await api.post<Submission>(`/moderation/submissions/${id}/withdraw`);
    return r.data;
  },

  // Comments
  async listComments(id: string): Promise<Comment[]> {
    const r = await api.get<Comment[]>(`/moderation/submissions/${id}/comments`);
    return r.data;
  },
  async addComment(id: string, text: string, opts: { is_internal?: boolean } = {}): Promise<Comment> {
    const r = await api.post<Comment>(`/moderation/submissions/${id}/comments`, {
      text, is_internal: !!opts.is_internal,
    });
    return r.data;
  },

  // Rules
  async listRules(): Promise<{ items: Rule[]; total: number }> {
    const r = await api.get<{ items: Rule[]; total: number }>("/moderation/rules");
    return r.data;
  },
  async getRule(id: string): Promise<Rule> {
    const r = await api.get<Rule>(`/moderation/rules/${id}`);
    return r.data;
  },
  async createRule(payload: RulePayload): Promise<Rule> {
    const r = await api.post<Rule>("/moderation/rules", payload);
    return r.data;
  },
  async updateRule(id: string, payload: Partial<RulePayload>): Promise<Rule> {
    const r = await api.patch<Rule>(`/moderation/rules/${id}`, payload);
    return r.data;
  },
  async deleteRule(id: string) { await api.delete(`/moderation/rules/${id}`); },
  async toggleRule(id: string): Promise<Rule> {
    const r = await api.post<Rule>(`/moderation/rules/${id}/toggle`);
    return r.data;
  },

  // Users
  async moderators(): Promise<{ items: ModeratorUser[] }> {
    const r = await api.get<{ items: ModeratorUser[] }>("/moderation/moderators");
    return r.data;
  },
  async submittedUsers(): Promise<{ items: SubmittedUser[] }> {
    const r = await api.get<{ items: SubmittedUser[] }>("/moderation/submitted-users");
    return r.data;
  },
  async patchUserFlags(userId: string, flags: Partial<Pick<SubmittedUser, "is_external" | "requires_moderation" | "bypass_moderation" | "external_org_name">>) {
    const r = await api.patch(`/moderation/users/${userId}/flags`, flags);
    return r.data;
  },
};


// ─── Display helpers ───────────────────────────────────────────

export const STATUS_LABELS: Record<SubmissionStatus, { label: string; color: string; bg: string }> = {
  pending:      { label: "Ожидает",       color: "#854F0B", bg: "rgba(239,159,39,.15)" },
  under_review: { label: "На рассмотрении", color: "#185FA5", bg: "rgba(55,138,221,.15)" },
  approved:     { label: "Одобрено",      color: "#0F6E56", bg: "rgba(29,158,117,.15)" },
  rejected:     { label: "Отклонено",     color: "#A32D2D", bg: "rgba(226,75,74,.15)" },
  withdrawn:    { label: "Отозвано",      color: "#5F5E5A", bg: "rgba(136,135,128,.12)" },
  expired:      { label: "Истекло",       color: "#5F5E5A", bg: "rgba(136,135,128,.12)" },
};

export const ACTION_LABELS: Record<ModAction, string> = {
  edit:          "изменить",
  replace:       "заменить",
  comment:       "комментарий",
  upload:        "файл",
  delete:        "удалить",
  status_change: "статус",
};

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diffSec = Math.floor((Date.now() - then) / 1000);
  if (diffSec < 30)        return "только что";
  if (diffSec < 60)        return `${diffSec} с`;
  if (diffSec < 3600)      return `${Math.floor(diffSec / 60)} мин`;
  if (diffSec < 86400)     return `${Math.floor(diffSec / 3600)} ч`;
  if (diffSec < 86400 * 7) return `${Math.floor(diffSec / 86400)} д`;
  return new Date(iso).toLocaleDateString("ru-RU");
}
