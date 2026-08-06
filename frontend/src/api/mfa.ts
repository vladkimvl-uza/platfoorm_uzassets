import { api } from "./client";
import type { TokenPair } from "./auth";

// ─── Types ────────────────────────────────────────────────────────────────

export interface MfaStatus {
  enabled: boolean;
  method: "none" | "telegram" | "totp" | "both";
  telegram_linked: boolean;
  telegram_username: string | null;
  telegram_linked_at: string | null;
  recovery_codes_remaining: number;
  recovery_codes_total: number;
}

export interface MfaLinkOut {
  bot_username: string;
  deep_link: string;
  token: string;
  expires_at: string;
}

export interface MfaEnableOut {
  enabled: boolean;
  method: "telegram" | "totp" | "both";
  recovery_codes: string[];
}

export interface MfaOnboardingSendCodeOut {
  challenge_id: string;
  ttl_minutes: number;
}

export interface MfaRecoveryCodesOut {
  codes: string[];
}

export interface TelegramPref {
  enabled: boolean;
  type_assignments: boolean;
  type_mentions: boolean;
  type_deadlines: boolean;
  type_moderation: boolean;
  type_broadcasts: boolean;
  type_system: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;  // "22:00:00"
  quiet_hours_end: string;    // "07:00:00"
  timezone: string;
}

export interface MfaOnboardingStatus {
  needed: boolean;
  reason: "mfa_enabled" | "skipped" | "show";
  skipped_until?: string | null;
}

export interface MfaOnboardingSkipOut {
  ok: boolean;
  skipped_until: string;
}

export interface LoginMfaResponse {
  mfa_required: boolean;
  // when mfa_required=false → TokenPair fields populated
  access_token?: string | null;
  refresh_token?: string | null;
  token_type?: string | null;
  expires_in?: number | null;
  // when mfa_required=true → challenge fields populated
  challenge_id?: string | null;
  method?: "telegram" | "totp" | "both" | null;
  masked_destination?: string | null;
  ttl_minutes?: number | null;
}

// ─── /mfa/* endpoints ─────────────────────────────────────────────────────

export const mfaApi = {
  /** Current user's MFA configuration. */
  async status(): Promise<MfaStatus> {
    const { data } = await api.get<MfaStatus>("/mfa/status");
    return data;
  },

  /** Start Telegram link flow → returns deep_link to bot. */

  /** Wipe Telegram link. May disable MFA if mode was telegram-only. */

  /** Turn on 2FA — returns 10 recovery codes (shown ONCE). */
  async enable(method: "telegram" | "totp" | "both" = "telegram"): Promise<MfaEnableOut> {
    const { data } = await api.post<MfaEnableOut>("/mfa/enable", { method });
    return data;
  },

  /** Turn off 2FA — must confirm with a recovery code. */
  async disable(confirmCode: string): Promise<void> {
    await api.post("/mfa/disable", { confirm_code: confirmCode });
  },

  /** Generate fresh 10 recovery codes (old hashes are wiped). */
  async regenerateRecoveryCodes(): Promise<MfaRecoveryCodesOut> {
    const { data } = await api.post<MfaRecoveryCodesOut>("/mfa/recovery-codes/regenerate");
    return data;
  },

  /** Get notification routing preferences. */

  /** Update notification routing preferences (partial). */
  async updatePrefs(patch: Partial<TelegramPref>): Promise<TelegramPref> {
    const { data } = await api.patch<TelegramPref>("/mfa/notification-prefs", patch);
    return data;
  },

  /** Send a test message to the user's Telegram. */

  // ─── onboarding wizard ────────────────────────────────────

  /** Check whether the first-login MFA wizard should run. */

  /** User clicked "Remind me in 7 days". */

  /** User finished the wizard (recovery codes saved). */

  // ─── Login flow endpoints (under /auth namespace but MFA-related) ───────

  /** Initial login — returns either TokenPair or MFA challenge. */
  async loginMfa(login: string, password: string): Promise<LoginMfaResponse> {
    const { data } = await api.post<LoginMfaResponse>("/auth/login-mfa", { login, password });
    return data;
  },

  /** Complete MFA login: Telegram code OR recovery code. */
  async verifyMfa(payload: {
    challenge_id?: string;
    code?: string;
    login?: string;
    recovery_code?: string;
  }): Promise<TokenPair> {
    const { data } = await api.post<TokenPair>("/auth/verify-mfa", payload);
    return data;
  },

  // ─── .2: onboarding code delivery ─────────────────────────

  /** Send a 6-digit code to user's Telegram (during onboarding). */

  /** Verify the 6-digit code AND enable MFA in one shot. */
  async onboardingVerifyAndEnable(challenge_id: string, code: string): Promise<MfaEnableOut> {
    const { data } = await api.post<MfaEnableOut>("/mfa/onboarding/verify-and-enable", {
      challenge_id, code,
    });
    return data;
  },
};
