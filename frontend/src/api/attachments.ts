/**
 * Attachments API — wraps backend /attachments/* endpoints.
 *
 * Three parent kinds:
 *   - task     → /attachments/task/{id}
 *   - project  → /attachments/project/{id}
 *   - company  → /attachments/company/{id}
 *
 * Task/project attachments carry an `is_result_doc` flag distinguishing
 * "результат" (proof of completion) from regular files. Company attachments
 * are a flat shared folder ("общая папка") — no category UI for now.
 */
import { api } from "./client";
import { t } from "@/locale/i18n";


export type AttachmentKind = "task" | "project" | "company";

export interface Attachment {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  is_result_doc: boolean;
  uploader_id: string | null;
  uploader_name?: string | null;
  created_at: string;
  /** Number of users this file is hidden from. Only populated for admins. */
  denied_user_count?: number;
}

export interface DeniedUser {
  user_id: string;
  user_email: string | null;
  user_full_name: string | null;
  denied_at: string;
  denied_by_email: string | null;
  reason: string | null;
}

export interface SignedUrlResponse {
  url: string;
  expires_in: number;
  filename: string;
  mime_type: string | null;
}

export const attachmentsApi = {
  async list(kind: AttachmentKind, parentId: string): Promise<Attachment[]> {
    const r = await api.get(`/attachments/${kind}/${parentId}`);
    return Array.isArray(r.data) ? r.data : [];
  },

  /** Upload a file. For task/project pass `isResultDoc` to mark it as a result.
   *  For company pass `title` (required) and optional `category` / `year`. */
  async upload(
    kind: AttachmentKind,
    parentId: string,
    file: File,
    opts: { isResultDoc?: boolean; title?: string; category?: string; year?: number } = {},
  ): Promise<Attachment> {
    const fd = new FormData();
    fd.append("file", file);
    if (kind === "task" || kind === "project") {
      fd.append("is_result_doc", opts.isResultDoc ? "true" : "false");
    } else {
      // company — title is required by backend Form(...)
      fd.append("title", opts.title || file.name);
      if (opts.category) fd.append("category", opts.category);
      if (opts.year != null) fd.append("year", String(opts.year));
    }
    const r = await api.post(`/attachments/${kind}/${parentId}`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return r.data as Attachment;
  },

  async signedUrl(kind: AttachmentKind, attId: string): Promise<SignedUrlResponse> {
    const r = await api.get(`/attachments/${kind}/${attId}/url`);
    return r.data as SignedUrlResponse;
  },

  async remove(kind: AttachmentKind, attId: string): Promise<void> {
    await api.delete(`/attachments/${kind}/${attId}`);
  },

  // ─── Admin per-user hide ─────────────────────────────────────────
  async listDeniedUsers(kind: AttachmentKind, attId: string): Promise<DeniedUser[]> {
    const r = await api.get(`/attachments/${kind}/${attId}/denied-users`);
    return Array.isArray(r.data) ? r.data : [];
  },
  async deny(kind: AttachmentKind, attId: string, userId: string, reason?: string): Promise<void> {
    await api.post(`/attachments/${kind}/${attId}/deny`, { user_id: userId, reason });
  },
  async allow(kind: AttachmentKind, attId: string, userId: string): Promise<void> {
    await api.delete(`/attachments/${kind}/${attId}/deny/${userId}`);
  },
};

// ─── Format helpers ────────────────────────────────────────────────────

export function formatBytes(n: number | null | undefined): string {
  if (n == null || isNaN(n) || n <= 0) return "—";
  if (n < 1024) return t('{value0} Б', { value0: n });
  if (n < 1024 * 1024) return t('{value0} КБ', { value0: (n / 1024).toFixed(1) });
  if (n < 1024 * 1024 * 1024) return t('{value0} МБ', { value0: (n / (1024 * 1024)).toFixed(1) });
  return t('{value0} ГБ', { value0: (n / (1024 * 1024 * 1024)).toFixed(2) });
}

/** Pick an icon-class hint from mime type (used by UI to colour-code icons). */
export function fileKind(mime: string | null | undefined): "pdf" | "doc" | "xls" | "ppt" | "img" | "zip" | "txt" | "other" {
  const m = (mime || "").toLowerCase();
  if (m.includes("pdf")) return "pdf";
  if (m.includes("word") || m.includes("msword") || m.includes("officedocument.wordprocessing")) return "doc";
  if (m.includes("excel") || m.includes("spreadsheet")) return "xls";
  if (m.includes("powerpoint") || m.includes("presentation")) return "ppt";
  if (m.startsWith("image/")) return "img";
  if (m.includes("zip")) return "zip";
  if (m.startsWith("text/")) return "txt";
  return "other";
}
