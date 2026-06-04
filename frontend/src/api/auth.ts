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
  department: string | null;
  job_title: string | null;
  phone?: string | null;
  avatar_url?: string | null;
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

  /** Самостоятельное редактирование своего профиля (ФИО/должность/телефон/отдел). */
  async updateMe(payload: { full_name?: string; job_title?: string; phone?: string; department?: string; avatar_url?: string }): Promise<User> {
    const { data } = await api.patch<User>("/auth/me", payload);
    return data;
  },

  /** Отметить приветственное окно первого входа как показанное. */
  async dismissWelcome(): Promise<void> {
    await api.post("/auth/me/welcome-seen");
  },
};
