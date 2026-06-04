import { api } from "./client";

export interface ApiSource {
  key: string;
  label: string;
  columns: string[];
  filters: string[];
  permission: string;
}

export interface CustomEndpoint {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  source: string;
  config: { columns?: string[]; year?: number | null; standard?: string | null; limit?: number };
  required_permission: string;
  is_active: boolean;
  url: string;
}

export interface PreviewResult {
  count: number;
  sample: Record<string, unknown>[];
  columns: string[];
}

export const customApi = {
  async sources(): Promise<ApiSource[]> {
    return (await api.get("/custom-api/sources")).data.items;
  },
  async preview(source: string, config: CustomEndpoint["config"]): Promise<PreviewResult> {
    return (await api.post("/custom-api/preview", { source, config })).data;
  },
  async list(): Promise<CustomEndpoint[]> {
    return (await api.get("/custom-api/endpoints")).data.items;
  },
  async create(body: {
    slug: string; title: string; description?: string | null; source: string;
    config: CustomEndpoint["config"]; is_active?: boolean;
  }): Promise<CustomEndpoint> {
    return (await api.post("/custom-api/endpoints", body)).data;
  },
  async update(id: string, body: Partial<{ title: string; description: string | null; config: CustomEndpoint["config"]; is_active: boolean }>): Promise<CustomEndpoint> {
    return (await api.patch(`/custom-api/endpoints/${id}`, body)).data;
  },
  async remove(id: string): Promise<void> {
    await api.delete(`/custom-api/endpoints/${id}`);
  },
};
