// DB Admin Console — API wrapper.
// All endpoints под is_owner || is_admin gate в backend.
import { api } from "./client";

export interface ColumnInfo {
  name: string;
  data_type: string;
  is_nullable: boolean;
  column_default: string | null;
  character_maximum_length: number | null;
  is_pk: boolean;
  is_fk: boolean;
  fk_references: string | null;
}

export interface IndexInfo {
  name: string;
  definition: string;
  is_unique: boolean;
  is_primary: boolean;
}

export interface TableInfo {
  schema: string;
  name: string;
  row_count: number | null;
  size_bytes: number | null;
  columns: ColumnInfo[];
  indexes: IndexInfo[];
}

export interface SchemaOverview {
  tables: TableInfo[];
  db_size_bytes: number | null;
  db_version: string | null;
}

export interface QueryResponse {
  columns: string[];
  rows: any[][];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  command: string;
}

export interface TableRowsResponse {
  columns: string[];
  rows: Record<string, any>[];
  total: number;
  limit: number;
  offset: number;
}

export const dbAdminApi = {
  async schema(): Promise<SchemaOverview> {
    const { data } = await api.get<SchemaOverview>("/admin/db/schema");
    return data;
  },

  async query(sql: string, dry_run = false): Promise<QueryResponse> {
    const { data } = await api.post<QueryResponse>("/admin/db/query", { sql, dry_run });
    return data;
  },

  async browseTable(
    name: string,
    opts: { limit?: number; offset?: number; order_by?: string; order_dir?: "ASC" | "DESC" } = {},
  ): Promise<TableRowsResponse> {
    const { data } = await api.get<TableRowsResponse>(`/admin/db/table/${name}/rows`, {
      params: {
        limit: opts.limit ?? 50,
        offset: opts.offset ?? 0,
        order_by: opts.order_by,
        order_dir: opts.order_dir ?? "ASC",
      },
    });
    return data;
  },

  async updateRow(table: string, pk_column: string, pk_value: any, values: Record<string, any>) {
    const { data } = await api.patch(`/admin/db/table/${table}/row`, {
      pk_column,
      pk_value,
      values,
    });
    return data as { updated: Record<string, any> | null };
  },

  async deleteRow(table: string, pk_column: string, pk_value: any) {
    const { data } = await api.delete(`/admin/db/table/${table}/row`, {
      params: { pk_column, pk_value },
    });
    return data as { deleted: number };
  },
};

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return new Intl.NumberFormat("ru-RU").format(n);
}
