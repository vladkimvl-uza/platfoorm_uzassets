import { api } from "./client";

export interface EmailSettings {
  SMTP_ENABLED: boolean;
  SMTP_HOST: string;
  SMTP_PORT: number;
  SMTP_USER: string;
  SMTP_FROM: string;
  SMTP_USE_TLS: boolean;
  SMTP_USE_SSL: boolean;
  SMTP_VERIFY_CERT: boolean;
  PUBLIC_URL: string;
  SMTP_PASSWORD_SET: boolean;   // пароль наружу не отдаётся — только флаг
}

export type EmailSettingsUpdate = Partial<Omit<EmailSettings, "SMTP_PASSWORD_SET">> & {
  SMTP_PASSWORD?: string;        // пустое = не менять
};

export const emailSettingsApi = {
  async get(): Promise<EmailSettings> {
    const { data } = await api.get<EmailSettings>("/email-settings");
    return data;
  },
  async update(payload: EmailSettingsUpdate): Promise<EmailSettings> {
    const { data } = await api.put<EmailSettings>("/email-settings", payload);
    return data;
  },
  async sendTest(): Promise<{ sent: boolean; to: string }> {
    const { data } = await api.post<{ sent: boolean; to: string }>("/email-settings/test");
    return data;
  },
};
