/**
 * Directions API — admin CRUD for transformation directions
 * (Стратегическое управление, Финансы, ESG, etc.) + custom user-added ones.
 */
import { api } from "./client";

export interface DirectionBrief {
  id: string;
  code: string;
  label: string;          // name_ru on the server, label here for FE consistency
  name_uz?: string | null;
  name_en?: string | null;
  description?: string | null;
  color: string;
  sort_order: number;
  is_custom: boolean;
  is_canonical: boolean;
}

export interface DirectionCreatePayload {
  name_ru: string;
  code?: string;
  name_uz?: string | null;
  name_en?: string | null;
  description?: string | null;
  sort_order?: number;
  color?: string | null;
}

export interface DirectionPatchPayload {
  name_ru?: string;
  name_uz?: string | null;
  name_en?: string | null;
  description?: string | null;
  sort_order?: number;
  color?: string | null;
}

export const directionsApi = {
  async list(): Promise<DirectionBrief[]> {
    const { data } = await api.get<{ directions: DirectionBrief[] }>("/directions");
    return data.directions;
  },

  async create(payload: DirectionCreatePayload): Promise<DirectionBrief> {
    const { data } = await api.post<DirectionBrief>("/directions", payload);
    return data;
  },

  async update(id: string, payload: DirectionPatchPayload): Promise<DirectionBrief> {
    const { data } = await api.patch<DirectionBrief>(`/directions/${id}`, payload);
    return data;
  },

  async usage(id: string): Promise<{ tasks: number; projects: number; code: string; label: string }> {
    const { data } = await api.get(`/directions/${id}/usage`);
    return data;
  },

  async remove(id: string, opts?: { reassignTo?: string }): Promise<void> {
    const params = opts?.reassignTo ? { reassign_to: opts.reassignTo } : {};
    await api.delete(`/directions/${id}`, { params });
  },
};
