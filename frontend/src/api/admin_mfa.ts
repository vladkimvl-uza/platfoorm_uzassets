import { api } from "./client";

export interface UserMfaRow {
  id: string;
  email: string;
  full_name: string | null;
  username: string | null;
  is_active: boolean;
  is_owner: boolean;
  mfa_enabled: boolean;
  mfa_method: "none" | "telegram" | "totp" | "both";
  telegram_linked: boolean;
  telegram_username: string | null;
  telegram_linked_at: string | null;
  recovery_codes_remaining: number;
  last_login_at: string | null;
  last_login_ip: string | null;
}

export interface MfaOverviewSummary {
  total: number;
  mfa_enabled_count: number;
  telegram_linked_count: number;
  no_2fa_count: number;
}

export interface MfaOverviewResponse {
  users: UserMfaRow[];
  summary: MfaOverviewSummary;
}

export const adminMfaApi = {
  /** List all active users with their MFA / Telegram status. Requires admin.users. */
  async overview(): Promise<MfaOverviewResponse> {
    const { data } = await api.get<MfaOverviewResponse>("/admin/users/mfa-overview");
    return data;
  },

  /** Wipe a target user's MFA + Telegram link. Owner-only. Audit-logged. */
  async forceDisable(userId: string): Promise<void> {
    await api.post(`/admin/users/${userId}/mfa-force-disable`);
  },
};
