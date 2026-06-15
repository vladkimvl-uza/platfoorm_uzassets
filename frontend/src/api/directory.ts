import { api } from "./client";

/** Лёгкая карточка пользователя для поповера (hover/click). */
export interface UserCard {
  id: string;
  full_name: string | null;
  email: string;
  role: string | null;
  is_owner: boolean;
  company: string | null;
  sector: string | null;
  sector_color: string | null;
  department: string | null;
  job_title: string | null;
  phone?: string | null;
  initials: string;
  accent: string;
  is_active: boolean;
  is_external?: boolean;
  avatar_url?: string | null;
  last_active: string | null;
  linkedin_url?: string | null;
  website_url?: string | null;
  telegram_username?: string | null;
}

export const directoryApi = {
  async userCard(userId: string): Promise<UserCard> {
    const r = await api.get<UserCard>(`/users/card`, { params: { id: userId } });
    return r.data;
  },
};
