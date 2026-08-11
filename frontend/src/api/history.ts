/**
 * Пер-сущностный журнал изменений (кто/что/когда по конкретной записи).
 * Бэкенд: GET /history/{entity_type}/{entity_id} — открыт всем
 * аутентифицированным (ключ = неугадываемый UUID, отдаются только имена полей).
 * Полный админ-журнал с фильтрами — отдельно в /admin/audit (audit.ts).
 */
import { api } from "@/api/client";

export interface ChangeEvent {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_role: string | null;
  action: string;            // CREATE | UPDATE | DELETE | ...
  module: string | null;
  entity_label: string | null;
  fields: string[] | null;   // имена изменённых полей (без значений)
  http_method: string | null;
  http_status: number | null;
  at: string | null;         // ISO-время
}

export const historyApi = {
  async entity(entityType: string, entityId: string, limit = 50): Promise<ChangeEvent[]> {
    const { data } = await api.get<ChangeEvent[]>(
      `/history/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
      { params: { limit } },
    );
    return data;
  },
};
