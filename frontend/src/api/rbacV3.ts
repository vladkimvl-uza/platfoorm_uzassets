import { api } from './client';

export interface RbacV3UserBrief {
  id: string;
  email: string;
  full_name: string;
  department: string | null;
  is_active: boolean;
  is_owner: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  last_seen_at: string | null;
  locked_until: string | null;
  created_at: string;
  role_codes: string[];
  role_names: string[];
  organization_id: string | null;
  allowed_companies: string[] | null;
}

export interface RbacV3UserGroupMembership {
  group_id: string;
  group_code: string;
  group_name: string;
  company_id: string | null;
  role_code: string;
  role_name: string;
}

export interface RbacV3UserDetail extends RbacV3UserBrief {
  effective_permissions: string[];
  role_by_email_rule: any | null;
  // Pack 147: per-(user, group) memberships with their role inside the group.
  group_memberships: RbacV3UserGroupMembership[];
  // Pack 148-followup: moderation flags surfaced for the user-detail drawer.
  is_external: boolean;
  bypass_moderation: boolean;
  external_org_name: string | null;
  // Область доступа к данным: «По секторам» / прямые компании.
  allowed_sectors: string[] | null;
  allowed_companies: string[] | null;
}

export interface RbacV3UserListResponse {
  items: RbacV3UserBrief[];
  total: number;
}

export const rbacV3Api = {
  async listUsers(opts?: { search?: string; is_active?: boolean; limit?: number; offset?: number }): Promise<RbacV3UserListResponse> {
    const { data } = await api.get<RbacV3UserListResponse>('/rbac/v3/users', { params: opts });
    return data;
  },
  async getUser(id: string): Promise<RbacV3UserDetail> {
    const { data } = await api.get<RbacV3UserDetail>(`/rbac/v3/users/${id}`);
    return data;
  },
  async deactivate(id: string) {
    await api.delete(`/rbac/v3/users/${id}`);
  },
  // Разблокировать аккаунт: снять деактивацию + lockout по попыткам входа.
  async reactivate(id: string): Promise<RbacV3UserDetail> {
    const { data } = await api.post<RbacV3UserDetail>(`/rbac/v3/users/${id}/reactivate`);
    return data;
  },
  async deletePermanent(id: string) {
    await api.delete(`/rbac/v3/users/${id}/permanent`);
  },
  // Назначить/снять статус OWNER. Доступно только текущему OWNER (бэк гейтит).
  async setOwner(id: string, isOwner: boolean): Promise<RbacV3UserDetail> {
    const { data } = await api.post<RbacV3UserDetail>(`/rbac/v3/users/${id}/owner`, { is_owner: isOwner });
    return data;
  },
  async update(id: string, payload: { full_name?: string; department?: string; is_active?: boolean; role_codes?: string[]; allowed_companies?: string[] | null }) {
    const { data } = await api.patch<RbacV3UserDetail>(`/rbac/v3/users/${id}`, payload);
    return data;
  },
  // Pack 148-followup: per-user group membership upsert + delete so the
  // user-detail drawer can add/change/remove a single membership without
  // having to PUT the whole group member list.
  async upsertMembership(userId: string, groupId: string, roleCode: string): Promise<RbacV3UserDetail> {
    const { data } = await api.put<RbacV3UserDetail>(
      `/rbac/v3/users/${userId}/memberships/${groupId}`,
      { role_code: roleCode },
    );
    return data;
  },
  async removeMembership(userId: string, groupId: string): Promise<void> {
    await api.delete(`/rbac/v3/users/${userId}/memberships/${groupId}`);
  },
  // Прямое per-user редактирование доступа к модулям (OWNER/ADMIN).
  // permission_codes — плоский список (из levelsToPermissions сетки).
  async setPermissions(userId: string, permission_codes: string[]): Promise<RbacV3UserDetail> {
    const { data } = await api.put<RbacV3UserDetail>(
      `/rbac/v3/users/${userId}/permissions`,
      { permission_codes },
    );
    return data;
  },
  // Admin-set a new password for any user. Revokes all live sessions on
  // success so the prior tokens can't keep going. `must_change_password`
  // forces the user to change it again on their next login.
  async resetPassword(userId: string, newPassword: string, mustChange = true): Promise<void> {
    await api.post(`/rbac/v3/users/${userId}/reset-password`, {
      new_password: newPassword,
      must_change_password: mustChange,
    });
  },
  // Toggle must_change_password=true WITHOUT changing the actual password.
  // User can still log in with current credentials but is bounced into the
  // change-password page on first protected request.
  async forcePasswordChange(userId: string): Promise<void> {
    await api.post(`/rbac/v3/users/${userId}/force-password-change`);
  },
};

// ─── Admin MFA management (Pack 13.1.2 backend) ───────────────────

export interface AdminMfaRow {
  id: string;
  email: string;
  full_name: string | null;
  username: string | null;
  is_active: boolean;
  is_owner: boolean;
  mfa_enabled: boolean;
  mfa_method: string;
  telegram_linked: boolean;
  telegram_username: string | null;
  telegram_linked_at: string | null;
  recovery_codes_remaining: number;
  last_login_at: string | null;
  last_login_ip: string | null;
}

export interface AdminMfaOverview {
  users: AdminMfaRow[];
  summary: {
    total: number;
    mfa_enabled_count: number;
    telegram_linked_count: number;
    no_2fa_count: number;
  };
}

export const adminMfaApi = {
  async overview(): Promise<AdminMfaOverview> {
    const { data } = await api.get<AdminMfaOverview>('/admin/users/mfa-overview');
    return data;
  },
  /** Owner-only — wipes target user's 2FA (TOTP + Telegram + recovery codes). */
  async forceDisable(userId: string): Promise<void> {
    await api.post(`/admin/users/${userId}/mfa-force-disable`);
  },
};

/**
 * Convert effective_permissions array into the format AccessCard expects:
 * { moduleCode -> AccessLevel } + { moduleCode -> source string }.
 *
 * Heuristic for level:
 *   - has *.manage or *.admin -> 'admin'
 *   - has *.edit or *.create or *.update or *.delete -> 'write'
 *   - has *.view -> 'read'
 *   - else -> 'none'
 *
 * Owner / admin role gets 'admin' on all 16 modules unconditionally.
 * (Mirror backend `app/core/security.is_super_admin` — никаких других ролей
 *  в bypass, иначе UI показывает кнопки, а бэк возвращает 403.)
 */
import { MODULE_REGISTRY } from '@/composables/usePermissions';
import type { AccessLevel } from '@/composables/usePermissions';

export function deriveAccessMap(user: RbacV3UserDetail | null): {
  levels: Record<string, AccessLevel>;
  sources: Record<string, string>;
} {
  const levels: Record<string, AccessLevel> = {};
  const sources: Record<string, string> = {};
  if (!user) return { levels, sources };

  // Owner / admin bypass — admin everywhere. Mirrors backend is_super_admin.
  if (user.is_owner || user.role_codes.includes('admin')) {
    const reason = user.is_owner ? 'владелец платформы' : 'via role: admin';
    for (const m of MODULE_REGISTRY) {
      levels[m.code] = 'admin';
      sources[m.code] = reason;
    }
    return { levels, sources };
  }

  const perms = user.effective_permissions || [];
  for (const m of MODULE_REGISTRY) {
    const prefix = m.code + '.';
    const codes = perms.filter(p => p.startsWith(prefix));
    if (codes.length === 0) { levels[m.code] = 'none'; sources[m.code] = 'нет в роли'; continue; }

    let level: AccessLevel = 'none';
    if (codes.some(c => c.endsWith('.manage') || c.endsWith('.admin'))) level = 'admin';
    else if (codes.some(c => /\.(edit|create|update|delete|write|approve)$/.test(c))) level = 'write';
    else if (codes.some(c => c.endsWith('.view') || c.endsWith('.read'))) level = 'read';

    levels[m.code] = level;
    // Best-effort source — first non-empty role
    sources[m.code] = user.role_codes.length > 0
      ? `via role: ${user.role_codes[0]}`
      : 'via permissions';
  }
  return { levels, sources };
}
// ─── Roles ───────────────────────────────────────────────────────

export interface RbacV3RolePerm {
  id: string;
  code: string;
  description?: string | null;
  category?: string | null;
}
export interface RbacV3Role {
  id: string;
  code: string;
  name_ru: string;
  name_en: string | null;
  description_ru: string | null;
  is_system: boolean;
  sort_order: number;
  permission_count: number;
}
export interface RbacV3RoleDetail extends RbacV3Role {
  permissions: RbacV3RolePerm[];
}

export const rolesApi = {
  async list(): Promise<RbacV3Role[]> {
    const { data } = await api.get<RbacV3Role[]>('/rbac/v3/roles');
    return data;
  },
  async get(code: string): Promise<RbacV3RoleDetail> {
    const { data } = await api.get<RbacV3RoleDetail>(`/rbac/v3/roles/${code}`);
    return data;
  },
  async updatePermissions(code: string, permission_codes: string[]): Promise<RbacV3RoleDetail> {
    const { data } = await api.patch<RbacV3RoleDetail>(`/rbac/v3/roles/${code}/permissions`, { permission_codes });
    return data;
  },
};

// ─── Groups ──────────────────────────────────────────────────────

export interface RbacV3Group {
  id: string;
  code: string;
  name: string;
  description: string | null;
  // Pack 147: 1:1 group↔company binding; null = free-form group.
  company_id: string | null;
  organization_id: string | null;
  department: string | null;
  member_count: number;
  permission_count: number;
  role_codes: string[];
}
export interface RbacV3GroupMember {
  id: string;
  email: string;
  full_name: string;
  // Pack 147: role of this user inside this group.
  role_code: string | null;
  role_name: string | null;
}
export interface RbacV3GroupPerm {
  code: string;
  description?: string | null;
}
export interface RbacV3GroupDetail extends RbacV3Group {
  members: RbacV3GroupMember[];
  permissions: RbacV3GroupPerm[];
  roles: string[];
}

export const groupsApi = {
  async list(): Promise<RbacV3Group[]> {
    const { data } = await api.get<RbacV3Group[]>('/rbac/v3/groups');
    return data;
  },
  async get(id: string): Promise<RbacV3GroupDetail> {
    const { data } = await api.get<RbacV3GroupDetail>(`/rbac/v3/groups/${id}`);
    return data;
  },
  async create(payload: { code: string; name: string; description?: string; department?: string }): Promise<RbacV3Group> {
    const { data } = await api.post<RbacV3Group>('/rbac/v3/groups', payload);
    return data;
  },
  async update(id: string, payload: { name?: string; description?: string; department?: string }): Promise<RbacV3Group> {
    const { data } = await api.patch<RbacV3Group>(`/rbac/v3/groups/${id}`, payload);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/rbac/v3/groups/${id}`);
  },
  /**
   * Pack 147: members carry their per-(user, group) role.
   * Backend backward-compat: passing { user_ids } still works (each user
   * gets `viewer` role). Prefer { members: [{user_id, role_code}, ...] }.
   */
  async setMembers(
    id: string,
    members: Array<{ user_id: string; role_code: string }>,
  ): Promise<RbacV3GroupDetail> {
    const { data } = await api.put<RbacV3GroupDetail>(`/rbac/v3/groups/${id}/members`, { members });
    return data;
  },
  /** Legacy helper — only when caller doesn't care about per-group role. */
  async setMembersLegacy(id: string, user_ids: string[]): Promise<RbacV3GroupDetail> {
    const { data } = await api.put<RbacV3GroupDetail>(`/rbac/v3/groups/${id}/members`, { user_ids });
    return data;
  },
  async setPermissions(id: string, permission_codes: string[]): Promise<RbacV3GroupDetail> {
    const { data } = await api.put<RbacV3GroupDetail>(`/rbac/v3/groups/${id}/permissions`, { permission_codes });
    return data;
  },
};

// ─── Helper: permissions <-> level on module conversion ──────────

import { MODULE_REGISTRY as _MODS } from '@/composables/usePermissions';

/**
 * Convert flat permission_codes back into per-module level map.
 * Inverse of deriveAccessMap on permissions only.
 */
export function permissionsToLevels(codes: string[]): Record<string, AccessLevel> {
  const out: Record<string, AccessLevel> = {};
  for (const m of _MODS) {
    const prefix = m.code + '.';
    const owned = codes.filter(c => c.startsWith(prefix));
    if (owned.length === 0) { out[m.code] = 'none'; continue; }
    if (owned.some(c => c.endsWith('.manage') || c.endsWith('.admin'))) out[m.code] = 'admin';
    else if (owned.some(c => /\.(edit|create|update|delete|write|approve)$/.test(c))) out[m.code] = 'write';
    else if (owned.some(c => c.endsWith('.view') || c.endsWith('.read'))) out[m.code] = 'read';
    else out[m.code] = 'none';
  }
  return out;
}

/**
 * Convert per-module level map back into flat permission_codes.
 * Used when saving role.permissions or group.permissions.
 * Strategy: produce canonical codes per level
 *   read  -> {module}.view
 *   write -> {module}.view + {module}.edit + {module}.export
 *   admin -> {module}.view + {module}.edit + {module}.export + {module}.manage
 */
export function levelsToPermissions(levels: Record<string, AccessLevel>): string[] {
  const codes: string[] = [];
  for (const [code, level] of Object.entries(levels)) {
    if (level === 'none') continue;
    codes.push(`${code}.view`);
    if (level === 'write' || level === 'admin') {
      codes.push(`${code}.edit`, `${code}.export`);
    }
    if (level === 'admin') {
      codes.push(`${code}.manage`);
    }
  }
  return codes;
}
// ─── User creation (invite / clone) ──────────────────────────────

export interface RbacV3CreateUserPayload {
  email: string;
  full_name: string;
  department?: string;
  password: string;
  must_change_password?: boolean;
  role_codes: string[];
  allowed_companies?: string[];
  allowed_sectors?: string[];   // Область доступа «По секторам»
}

export async function createUser(payload: RbacV3CreateUserPayload): Promise<RbacV3UserDetail> {
  const { data } = await api.post<RbacV3UserDetail>('/rbac/v3/users', payload);
  return data;
}

/**
 * Generate a random 16-char password with mixed case / digits / symbols.
 * Cryptographically secure where available (window.crypto).
 */
export function generatePassword(): string {
  const sets = [
    'ABCDEFGHJKLMNPQRSTUVWXYZ',  // uppercase (no I, O — visual confusion)
    'abcdefghjkmnpqrstuvwxyz',   // lowercase (no i, l, o)
    '23456789',                   // digits (no 0, 1)
    '!@#$%^&*?',                  // symbols
  ];
  const out: string[] = [];
  // 4 chars from each set — guarantees variety
  for (const set of sets) {
    for (let i = 0; i < 4; i++) {
      const r = (window.crypto?.getRandomValues
        ? window.crypto.getRandomValues(new Uint32Array(1))[0]
        : Math.floor(Math.random() * 0xffffffff));
      out.push(set[r % set.length]);
    }
  }
  // Shuffle
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out.join('');
}
// ─── Email rules (auto-assign on signup) ─────────────────────────

export interface RbacV3EmailRule {
  id: string;
  email: string;
  role_codes: string[];
  department: string | null;
  allowed_sectors: string[] | null;
  allowed_companies: string[] | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface RbacV3EmailRuleCreate {
  email: string;
  role_codes: string[];
  department?: string;
  allowed_sectors?: string[];
  allowed_companies?: string[];
  notes?: string;
}

export interface RbacV3EmailRuleUpdate {
  role_codes?: string[];
  department?: string | null;
  allowed_sectors?: string[] | null;
  allowed_companies?: string[] | null;
  notes?: string | null;
}

export const emailRulesApi = {
  async list(): Promise<RbacV3EmailRule[]> {
    const { data } = await api.get<RbacV3EmailRule[]>('/rbac/v3/role-by-email');
    return data;
  },
  async create(payload: RbacV3EmailRuleCreate): Promise<RbacV3EmailRule> {
    const { data } = await api.post<RbacV3EmailRule>('/rbac/v3/role-by-email', payload);
    return data;
  },
  async update(id: string, payload: RbacV3EmailRuleUpdate): Promise<RbacV3EmailRule> {
    const { data } = await api.patch<RbacV3EmailRule>(`/rbac/v3/role-by-email/${id}`, payload);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/rbac/v3/role-by-email/${id}`);
  },
};
// ─── Audit ───────────────────────────────────────────────────────

export interface RbacV3AuditEvent {
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

export interface RbacV3AuditEventDetail extends RbacV3AuditEvent {
  diff: any | null;
  payload: any | null;
}

export interface RbacV3AuditList {
  items: RbacV3AuditEvent[];
  total: number;
  page: number;
  per_page: number;
}

export interface AuditFilters {
  hours?: number;
  module?: string;
  action?: string;
  search?: string;
  only_critical?: boolean;
  page?: number;
  per_page?: number;
}

export const auditApi = {
  async list(filters: AuditFilters): Promise<RbacV3AuditList> {
    const params: any = {
      page: filters.page || 1,
      per_page: filters.per_page || 50,
    };
    if (filters.hours) params.hours = filters.hours;
    if (filters.module) params.module = filters.module;
    if (filters.action) params.action = filters.action;
    if (filters.search) params.search = filters.search;
    if (filters.only_critical) params.only_critical = true;
    const { data } = await api.get<RbacV3AuditList>('/admin/audit/events', { params });
    return data;
  },
  async get(id: string): Promise<RbacV3AuditEventDetail> {
    const { data } = await api.get<RbacV3AuditEventDetail>(`/admin/audit/events/${id}`);
    return data;
  },
  exportCsvUrl(filters: AuditFilters): string {
    const params = new URLSearchParams();
    if (filters.hours) params.set('hours', String(filters.hours));
    if (filters.module) params.set('module', filters.module);
    if (filters.action) params.set('action', filters.action);
    if (filters.search) params.set('search', filters.search);
    if (filters.only_critical) params.set('only_critical', 'true');
    return '/api/admin/audit/export.csv?' + params.toString();
  },
};
// ─── Roles CRUD additions (Pack 143c backend) ──────────────────

export interface RbacV3RoleCreatePayload {
  code: string;
  name_ru: string;
  name_en?: string;
  description_ru?: string;
  sort_order?: number;
  permission_codes?: string[];
}

export interface RbacV3RoleUpdatePayload {
  name_ru?: string;
  name_en?: string;
  description_ru?: string;
  sort_order?: number;
}

export const rolesApiExt = {
  async create(payload: RbacV3RoleCreatePayload): Promise<RbacV3RoleDetail> {
    const { data } = await api.post<RbacV3RoleDetail>('/rbac/v3/roles', payload);
    return data;
  },
  async update(code: string, payload: RbacV3RoleUpdatePayload): Promise<RbacV3RoleDetail> {
    const { data } = await api.patch<RbacV3RoleDetail>(`/rbac/v3/roles/${code}`, payload);
    return data;
  },
  async remove(code: string): Promise<void> {
    await api.delete(`/rbac/v3/roles/${code}`);
  },
};

// ─── Impersonate / preview-token ───────────────────────────────

export interface RbacV3PreviewTokenResponse {
  access_token: string;
  expires_in: number;
  target_user_id: string;
  target_email: string;
}

export async function createPreviewToken(userId: string): Promise<RbacV3PreviewTokenResponse> {
  const { data } = await api.post<RbacV3PreviewTokenResponse>(
    `/rbac/v3/users/${userId}/preview-token`,
  );
  return data;
}