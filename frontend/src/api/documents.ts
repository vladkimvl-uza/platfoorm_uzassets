/**
 * Библиотека документов компании.
 *
 * Один файл хранится один раз и показывается везде, куда привязан: в
 * библиотеке компании И в карточке задачи/проекта/отчёта (document_links).
 * Поэтому загрузка из карточки идёт ЧЕРЕЗ этот же клиент — с entity_type /
 * entity_id, а не в отдельное хранилище вложений.
 */
import { api } from "@/api/client";
import { t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";


export type DocKind = "pdf" | "doc" | "sheet" | "slide" | "image" | "archive" | "other";

export interface DocLink {
  id: string;
  entity_type: string;
  entity_id: string;
  label: string | null;
}

export interface DocItem {
  id: string;
  name: string;
  folder_id: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  description: string | null;
  source_module: string;
  kind: DocKind;
  ext: string;
  uploader_id: string | null;
  uploader_name: string | null;
  is_deleted: boolean;
  created_at: string | null;
  updated_at: string | null;
  links: DocLink[];
}

export interface DocFolder {
  id: string;
  parent_id: string | null;
  name: string;
  /** #RRGGBB из палитры FOLDER_COLORS; null = цвет по умолчанию */
  color: string | null;
  system_key: string | null;
  is_system: boolean;
  file_count?: number;
}

/**
 * Палитра папок — 10 пастельных корпоративных тонов.
 *
 * Правила набора: низкая насыщенность и высокая светлота (пастель), близкий
 * между собой контраст, чтобы ряд папок читался как единая система, а не
 * «радуга»; первый тон — брендовый пурпур платформы. Красный/зелёный
 * «светофорных» оттенков в наборе НЕТ: в интерфейсе они означают статус, и
 * папка такого цвета читалась бы как тревога.
 */
export const FOLDER_COLORS: { hex: string; name: string }[] = [
  { hex: "#C7C3F0", name: i18nKey("Лаванда") },
  { hex: "#B9C7EE", name: i18nKey("Барвинок") },
  { hex: "#AFD3E8", name: i18nKey("Незабудка") },
  { hex: "#B3DCD2", name: i18nKey("Мята") },
  { hex: "#C2D6BC", name: i18nKey("Шалфей") },
  { hex: "#E4D9B4", name: i18nKey("Пшеница") },
  { hex: "#E6CDB2", name: i18nKey("Песок") },
  { hex: "#E4BFB4", name: i18nKey("Терракота") },
  { hex: "#E8C4CE", name: i18nKey("Пудра") },
  { hex: "#CBCDD6", name: i18nKey("Графит") },
];

/**
 * Цвет папки по умолчанию — классический «виндовый» жёлтый (решение владельца):
 * папка без выбранного цвета должна выглядеть привычно, как в проводнике.
 * Оттенок приглушён до корпоративного, чтобы не спорить с пастельной палитрой.
 */
export const FOLDER_COLOR_DEFAULT = "#F2C25C";

/** Цвет папки для отображения (с дефолтом). */
export function folderColor(f: { color?: string | null } | null | undefined): string {
  return (f?.color || FOLDER_COLOR_DEFAULT);
}

export interface DocTree {
  company_code: string;
  folders: DocFolder[];
  total_files: number;
  trash_count: number;
}

export interface DocListParams {
  folder_id?: string | null;
  entity_type?: string;
  entity_id?: string;
  q?: string;
  kind?: string;
  trash?: boolean;
  limit?: number;
  offset?: number;
}

export const documentsApi = {
  async tree(code: string): Promise<DocTree> {
    const { data } = await api.get<DocTree>(`/documents/${code}/tree`);
    return data;
  },
  async stats(code: string): Promise<{ files: number; size_bytes: number; last_upload_at: string | null }> {
    const { data } = await api.get(`/documents/${code}/stats`);
    return data;
  },
  async kinds(code: string): Promise<{ counts: Record<string, number>; total: number }> {
    const { data } = await api.get(`/documents/${code}/kinds`);
    return data;
  },
  async list(code: string, params: DocListParams = {}): Promise<{ items: DocItem[]; total: number }> {
    const { data } = await api.get(`/documents/${code}/items`, { params });
    return data;
  },
  async upload(
    code: string,
    file: File,
    opts: {
      folderId?: string | null;
      entityType?: string;
      entityId?: string;
      entityLabel?: string;
      description?: string;
      onProgress?: (pct: number) => void;
    } = {},
  ): Promise<DocItem> {
    const fd = new FormData();
    fd.append("file", file);
    if (opts.folderId) fd.append("folder_id", opts.folderId);
    if (opts.entityType) fd.append("entity_type", opts.entityType);
    if (opts.entityId) fd.append("entity_id", opts.entityId);
    if (opts.entityLabel) fd.append("entity_label", opts.entityLabel);
    if (opts.description) fd.append("description", opts.description);
    const { data } = await api.post(`/documents/${code}/upload`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (e: any) => {
        if (opts.onProgress && e.total) opts.onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return data;
  },
  async patch(code: string, id: string, body: Partial<Pick<DocItem, "name" | "folder_id" | "description">>): Promise<DocItem> {
    const { data } = await api.patch(`/documents/${code}/items/${id}`, body);
    return data;
  },
  async remove(code: string, id: string, hard = false): Promise<void> {
    await api.delete(`/documents/${code}/items/${id}`, { params: { hard } });
  },
  async restore(code: string, id: string): Promise<void> {
    await api.post(`/documents/${code}/items/${id}/restore`);
  },
  async url(code: string, id: string): Promise<{ url: string; filename: string; mime_type: string | null }> {
    const { data } = await api.get(`/documents/${code}/items/${id}/url`);
    return data;
  },
  async createFolder(code: string, name: string, parentId?: string | null, color?: string | null): Promise<DocFolder> {
    const { data } = await api.post(`/documents/${code}/folders`, {
      name, parent_id: parentId ?? null, color: color ?? null,
    });
    return data;
  },
  async patchFolder(code: string, id: string, body: { name?: string; color?: string | null }): Promise<DocFolder> {
    const { data } = await api.patch(`/documents/${code}/folders/${id}`, body);
    return data;
  },
  async renameFolder(code: string, id: string, name: string): Promise<DocFolder> {
    const { data } = await api.patch(`/documents/${code}/folders/${id}`, { name });
    return data;
  },
  async deleteFolder(code: string, id: string): Promise<void> {
    await api.delete(`/documents/${code}/folders/${id}`);
  },
  async link(code: string, id: string, entityType: string, entityId: string, label?: string): Promise<void> {
    await api.post(`/documents/${code}/items/${id}/links`, {
      entity_type: entityType, entity_id: entityId, label: label || null,
    });
  },
  async unlink(code: string, id: string, linkId: string): Promise<void> {
    await api.delete(`/documents/${code}/items/${id}/links/${linkId}`);
  },
};

/** Человеческий размер файла. */
export function fmtBytes(n: number | null | undefined): string {
  const b = Number(n || 0);
  if (!b) return "—";
  if (b < 1024) return t('{value0} Б', { value0: b });
  if (b < 1024 * 1024) return t('{value0} КБ', { value0: (b / 1024).toFixed(0) });
  if (b < 1024 * 1024 * 1024) return t('{value0} МБ', { value0: (b / 1024 / 1024).toFixed(1) });
  return t('{value0} ГБ', { value0: (b / 1024 / 1024 / 1024).toFixed(2) });
}

/** Подпись и цвет типа документа — единый язык иконок библиотеки. */
export const KIND_META: Record<string, { label: string; color: string; short: string }> = {
  pdf:     { label: "PDF",         color: "#E24B4A", short: "PDF" },
  doc:     { label: i18nKey("Документы"),   color: "#378ADD", short: "DOC" },
  sheet:   { label: i18nKey("Таблицы"),     color: "#1D9E75", short: "XLS" },
  slide:   { label: i18nKey("Презентации"), color: "#EF9F27", short: "PPT" },
  image:   { label: i18nKey("Изображения"), color: "#7C6FF7", short: "IMG" },
  archive: { label: i18nKey("Архивы"),      color: "#8A8F98", short: "ZIP" },
  other:   { label: i18nKey("Прочее"),      color: "#94A3B8", short: "FILE" },
};
