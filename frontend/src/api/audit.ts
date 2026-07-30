import { api } from "./client";
import { getCurrentIntlLocale, t } from "@/locale/i18n";


// ─── Types matching backend Pydantic schemas ─────────────────

export interface AuditEventRead {
  id: string;
  created_at: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;
  module: string | null;
  entity_type: string | null;
  entity_id: string | null;
  entity_label: string | null;
  http_method: string | null;
  http_path: string | null;
  http_status: number | null;
  duration_ms: number | null;
  ip_address: string | null;
  is_critical: boolean;
  has_diff: boolean;
  has_payload: boolean;
}

export interface AuditEventDetail extends AuditEventRead {
  user_agent: string | null;
  diff: Record<string, unknown> | null;
  payload: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
  notes: string | null;
  prev_hash: string | null;
  entry_hash: string | null;
}

export interface AuditEventList {
  items: AuditEventRead[];
  total: number;
  page: number;
  per_page: number;
}

export interface AuditStat {
  key: string;
  label: string;
  value: number;
  delta_pct: number | null;
  sub: string | null;
  accent: string | null;
}

export interface AuditStatsResponse {
  period_hours: number;
  events_total: number;
  unique_users: number;
  online_users: number;
  changes: number;
  views: number;
  errors: number;
  critical: number;
  stats: AuditStat[];
}

export interface AuditTopUser {
  actor_id: string | null;
  email: string;
  initials: string;
  count: number;
  accent: string;
}

export interface AuditTopModule {
  module: string;
  label: string;
  count: number;
}

export interface AuditSecurityFlag {
  id: string;
  severity: "critical" | "warning" | "info";
  kind: string;
  title: string;
  detail: string;
  created_at: string;
  related_user_email: string | null;
  related_ip: string | null;
  is_resolved: boolean;
}

export interface AuditTimelineBucket {
  ts: string;
  view: number;
  update: number;
  create: number;
  delete: number;
  error: number;
  login: number;
}

export interface AuditTimelineResponse {
  bucket: "hour" | "day";
  buckets: AuditTimelineBucket[];
}

export interface AuditOverviewResponse {
  stats: AuditStatsResponse;
  top_users: AuditTopUser[];
  top_modules: AuditTopModule[];
  security_flags: AuditSecurityFlag[];
  timeline: AuditTimelineResponse;
  recent_events: AuditEventRead[];
}

export interface AuditUserRow {
  actor_id: string;
  email: string;
  name: string;
  role: string | null;
  company: string | null;
  sector: string | null;
  department: string | null;
  job_title: string | null;
  is_owner?: boolean;
  avatar_url?: string | null;
  initials: string;
  accent: string;
  total: number;
  last_at: string | null;
  changes: number;
  deletions: number;
  views: number;
  logins: number;
  errors: number;
}

export interface AuditActivitySession {
  start: string; end: string; duration_sec: number; events: number;
}
export interface AuditActivityModule {
  module: string; label: string; count: number; seconds: number;
}
export interface AuditActivityRecent {
  desc: string; action: string; module: string | null; label: string | null;
  where?: string | null;   // конкретный раздел («Финансы · НСБУ»)
  entity?: string | null;  // ЦЕЛЬ: компания/запись (+год/период), напр. «НГМК · 2022»
  detail?: string | null;  // таблица + поля (для изменений)
  notes?: string | null;   // примечание события (напр. «сессии отозваны»)
  ip?: string | null;      // IP-адрес действия
  path?: string | null;    // точный URL запроса
  method?: string | null;  // HTTP-метод
  status?: number | null;  // HTTP-статус
  dur_ms?: number | null;  // длительность запроса, мс
  at: string; last_at: string; count: number; type: string;
}
export interface AuditCompanyRow {
  company: string; sector: string | null;
  total: number; people: number; changes: number;
  last_at: string | null; accent: string;
}
export interface AuditUserActivity {
  total_events: number;
  in_system_seconds: number;
  sessions_count: number;
  sessions: AuditActivitySession[];
  by_module: AuditActivityModule[];
  by_type: Record<string, number>;
  recent: AuditActivityRecent[];
}

// ─── API client ─────────────────────────────────────────────

export const auditApi = {
  async overview(hours = 24): Promise<AuditOverviewResponse> {
    const r = await api.get<AuditOverviewResponse>("/admin/audit/overview", {
      params: { hours },
    });
    return r.data;
  },

  async listEvents(params: {
    actor_email?: string;
    module?: string;
    action?: string;
    action_category?: string;
    hours?: number;
    search?: string;
    only_critical?: boolean;
    page?: number;
    per_page?: number;
  } = {}): Promise<AuditEventList> {
    const r = await api.get<AuditEventList>("/admin/audit/events", { params });
    return r.data;
  },

  async eventDetail(id: string): Promise<AuditEventDetail> {
    const r = await api.get<AuditEventDetail>(`/admin/audit/events/${id}`);
    return r.data;
  },

  async stats(hours = 24): Promise<AuditStatsResponse> {
    const r = await api.get<AuditStatsResponse>("/admin/audit/stats", {
      params: { hours },
    });
    return r.data;
  },

  /** Агрегат активности по пользователям (главный экран «по пользователям»). */
  async byUser(params: { since?: string; until?: string; search?: string } = {}): Promise<AuditUserRow[]> {
    const r = await api.get<AuditUserRow[]>("/admin/audit/by-user", { params });
    return r.data;
  },

  /** Персональная аналитика активности пользователя (сессии, время по разделам). */
  async userActivity(actorId: string, params: { since?: string; until?: string } = {}): Promise<AuditUserActivity> {
    const r = await api.get<AuditUserActivity>(`/admin/audit/user/${actorId}/activity`, { params });
    return r.data;
  },

  /** Активность по компаниям (какая компания активнее). */
  async byCompany(params: { since?: string; until?: string } = {}): Promise<AuditCompanyRow[]> {
    const r = await api.get<AuditCompanyRow[]>("/admin/audit/by-company", { params });
    return r.data;
  },

  async timeline(hours = 24, bucket: "hour" | "day" = "hour"): Promise<AuditTimelineResponse> {
    const r = await api.get<AuditTimelineResponse>("/admin/audit/timeline", {
      params: { hours, bucket },
    });
    return r.data;
  },

  exportCsvUrl(hours = 24): string {
    return `/admin/audit/export.csv?hours=${hours}`;
  },
};

// ─── Display helpers ────────────────────────────────────────

export const ACTION_META: Record<string, { color: string; bg: string; label: string; icon: string }> = {
  VIEW:         { color: "#185FA5", bg: "rgba(55,138,221,.12)",  label: "VIEW",    icon: "eye" },
  CREATE:       { color: "#534AB7", bg: "rgba(127,119,221,.12)", label: "CREATE",  icon: "plus" },
  UPDATE:       { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "UPDATE",  icon: "edit" },
  DELETE:       { color: "#993556", bg: "rgba(212,83,126,.12)",  label: "DELETE",  icon: "trash" },
  EXPORT:       { color: "#A36500", bg: "rgba(239,159,39,.12)",  label: "EXPORT",  icon: "download" },
  IMPORT:       { color: "#A36500", bg: "rgba(239,159,39,.12)",  label: "IMPORT",  icon: "upload" },
  LOGIN:        { color: "#0F6E56", bg: "rgba(29,158,117,.12)",  label: "LOGIN",   icon: "login" },
  LOGOUT:       { color: "#5F5E5A", bg: "rgba(0,0,0,.06)",       label: "LOGOUT",  icon: "logout" },
  FAILED:       { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "FAILED",  icon: "alert" },
  FAILED_LOGIN: { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "FAILED",  icon: "alert" },
  ERROR:        { color: "#A32D2D", bg: "rgba(226,75,74,.12)",   label: "ERROR",   icon: "alert" },
};

export function actionMeta(action: string) {
  return ACTION_META[action] || { color: "#5F5E5A", bg: "rgba(0,0,0,.06)", label: action, icon: "circle" };
}

export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  const diff = Date.now() - d.getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return t('{value0}с назад', { value0: sec });
  if (sec < 3600) return t('{value0}мин назад', { value0: Math.floor(sec / 60) });
  if (sec < 86400) return t('{value0}ч назад', { value0: Math.floor(sec / 3600) });
  return d.toLocaleDateString(getCurrentIntlLocale());
}

export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(getCurrentIntlLocale(), { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function formatDateShort(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return t('сегодня');
  const yest = new Date(today);
  yest.setDate(yest.getDate() - 1);
  if (d.toDateString() === yest.toDateString()) return t('вчера');
  return d.toLocaleDateString(getCurrentIntlLocale(), { day: "2-digit", month: "short" });
}
