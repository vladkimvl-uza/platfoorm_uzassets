// TLS admin — API wrapper. Under is_owner||is_admin gate.
import { api } from "./client";
import { t } from "@/locale/i18n";

export interface CertInfo {
  present: boolean;
  subject?: string;
  issuer?: string;
  not_before?: string;
  not_after?: string;
  days_left?: number;
  expired?: boolean;
  san?: string[];
  size_bytes?: number;
  mtime?: string;
  parse_error?: string;
}

export interface TlsConfig {
  source: "manual" | "letsencrypt" | null;
  renewed_at: string | null;
  schedule_enabled: boolean;
  schedule_interval_days: number;
  last_le_attempt: string | null;
  last_le_result: { code?: number; stdout_tail?: string; stderr_tail?: string; error?: string } | null;
  domain: string | null;
  email: string | null;
}

export interface CertStatus {
  active_label: "production" | "dev-fallback" | null;
  cert_path: string | null;
  key_path: string | null;
  info: CertInfo;
  config: TlsConfig;
}

export interface InstallResult {
  ok: boolean;
  info: CertInfo;
  reload_required?: boolean;
  reload_hint?: string;
  stdout_tail?: string;
}

export const tlsApi = {
  async status(): Promise<CertStatus> {
    const { data } = await api.get<CertStatus>("/admin/tls/status");
    return data;
  },

  async upload(cert_pem: string, key_pem: string, label = "manual"): Promise<InstallResult> {
    const { data } = await api.post<InstallResult>("/admin/tls/upload", { cert_pem, key_pem, label });
    return data;
  },

  async letsEncrypt(domain: string, email: string, staging = false): Promise<InstallResult> {
    const { data } = await api.post<InstallResult>("/admin/tls/letsencrypt", { domain, email, staging });
    return data;
  },

  async updateSchedule(enabled: boolean, interval_days = 90) {
    const { data } = await api.patch<{ ok: boolean; config: TlsConfig }>("/admin/tls/schedule", {
      schedule_enabled: enabled,
      schedule_interval_days: interval_days,
    });
    return data;
  },
};

export function formatDaysLeft(d: number | undefined): { text: string; tone: "ok" | "warn" | "crit" } {
  if (d === undefined) return { text: "—", tone: "crit" };
  if (d <= 7) return { text: t("{days} дн.", { days: d }), tone: "crit" };
  if (d <= 30) return { text: t("{days} дн.", { days: d }), tone: "warn" };
  return { text: t("{days} дн.", { days: d }), tone: "ok" };
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" });
  } catch { return "—"; }
}
