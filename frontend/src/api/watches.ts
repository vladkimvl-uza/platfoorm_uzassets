import { api } from "./client";

export type WatchEntityType = "project" | "task";

export interface WatchedItem {
  entity_type: WatchEntityType;
  entity_id: string;
  num: string | null;
  title: string;
  status: string;
  due_date: string | null;
  company_id: string | null;
  company_name: string | null;
  current_health: string | null;
  followed_at: string | null;
}

export const watchesApi = {
  async follow(entityType: WatchEntityType, entityId: string): Promise<void> {
    await api.post("/watches", { entity_type: entityType, entity_id: entityId });
  },
  async unfollow(entityType: WatchEntityType, entityId: string): Promise<void> {
    await api.delete("/watches", { params: { entity_type: entityType, entity_id: entityId } });
  },
  async status(entityType: WatchEntityType, entityId: string): Promise<{ watching: boolean; count: number }> {
    const { data } = await api.get("/watches/status", { params: { entity_type: entityType, entity_id: entityId } });
    return data;
  },
  async mine(): Promise<WatchedItem[]> {
    const { data } = await api.get<WatchedItem[]>("/watches/me");
    return data;
  },
};
