import { api } from "./client";

export type StatusHealth = "on_track" | "at_risk" | "delayed" | "blocked";

export interface StatusUpdate {
  id: string;
  entity_type: "project" | "task";
  entity_id: string;
  body: string;
  health: StatusHealth | null;
  author_id: string | null;
  author_name: string | null;
  created_at: string;
  updated_at: string;
}

export const statusUpdatesApi = {
  async list(entityType: "project" | "task", entityId: string): Promise<StatusUpdate[]> {
    const { data } = await api.get<StatusUpdate[]>("/status-updates", {
      params: { entity_type: entityType, entity_id: entityId },
    });
    return data;
  },
  async create(entityType: "project" | "task", entityId: string, body: string, health: StatusHealth | null): Promise<StatusUpdate> {
    const { data } = await api.post<StatusUpdate>("/status-updates", {
      entity_type: entityType, entity_id: entityId, body, health,
    });
    return data;
  },
  async update(id: string, patch: { body?: string; health?: StatusHealth | null }): Promise<StatusUpdate> {
    const { data } = await api.patch<StatusUpdate>(`/status-updates/${id}`, patch);
    return data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/status-updates/${id}`);
  },
};

// ─── Health meta (цвета/подписи по дизайн-системе) ───
export const HEALTH_META: Record<StatusHealth, { label: string; color: string }> = {
  on_track: { label: "В графике", color: "#1D9E75" },
  at_risk:  { label: "Под риском", color: "#EF9F27" },
  delayed:  { label: "Задержка", color: "#E24B4A" },
  blocked:  { label: "Блокер", color: "#7A1F1F" },
};
export const HEALTH_ORDER: StatusHealth[] = ["on_track", "at_risk", "delayed", "blocked"];
