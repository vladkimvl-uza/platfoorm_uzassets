import { api } from "./client";

export interface User {
  id: string;
  email: string;
  username: string | null;
  full_name: string | null;
  is_owner: boolean;
  is_active: boolean;
  must_change_password: boolean;
  password_changed_at: string | null;
  organization_id: string | null;
  company?: string | null;
  sector?: string | null;
  org_profile_set?: boolean;
  department: string | null;
  job_title: string | null;
  phone?: string | null;
  avatar_url?: string | null;
  linkedin_url?: string | null;
  website_url?: string | null;
  telegram_username?: string | null;
  last_login_at: string | null;
  welcome_seen?: boolean;
  roles: string[];
  permissions: string[];
  groups?: Array<{ code?: string; name?: string; permissions?: Array<string | { code: string }> }>;
  module_visibility?: Record<string, boolean>;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export const authApi = {
  async login(login: string, password: string): Promise<TokenPair> {
    const { data } = await api.post<TokenPair>("/auth/login", { login, password });
    return data;
  },

  async refresh(refresh_token: string): Promise<TokenPair> {
    const { data } = await api.post<TokenPair>("/auth/refresh", { refresh_token });
    return data;
  },

  async logout(refresh_token: string | null): Promise<void> {
    await api.post("/auth/logout", { refresh_token });
  },

  async me(): Promise<User> {
    const { data } = await api.get<User>("/auth/me");
    return data;
  },

  async changePassword(current_password: string, new_password: string): Promise<void> {
    await api.post("/auth/change-password", { current_password, new_password });
  },

  /** Самостоятельное редактирование своего профиля (ФИО/должность/телефон/отдел/компания при первой настройке). */
  async updateMe(payload: { full_name?: string; job_title?: string; phone?: string; department?: string; avatar_url?: string; organization_id?: string; linkedin_url?: string; website_url?: string }): Promise<User> {
    const { data } = await api.patch<User>("/auth/me", payload);
    return data;
  },

  /** Отметить приветственное окно первого входа как показанное. */
  async dismissWelcome(): Promise<void> {
    await api.post("/auth/me/welcome-seen");
  },

  /** Активные сессии текущего пользователя. */
  async listSessions(): Promise<SessionInfo[]> {
    const { data } = await api.get<SessionInfo[]>("/auth/sessions");
    return data;
  },

  /** Завершить конкретную свою сессию. */
  async revokeSession(id: string): Promise<void> {
    await api.delete(`/auth/sessions/${id}`);
  },

  /** Завершить все сессии, кроме текущей. */
  async revokeOtherSessions(): Promise<number> {
    const { data } = await api.post<{ revoked: number }>("/auth/sessions/revoke-others");
    return data.revoked;
  },

  /** Step-up re-auth: повторный ввод пароля разблокирует чувствительные операции. */
  async reauth(password: string): Promise<void> {
    await api.post("/auth/reauth", { password });
  },
};

export interface SessionInfo {
  id: string;
  ip_address: string | null;
  user_agent: string | null;
  started_at: string;
  last_at: string;
  count: number;
  current: boolean;
}
