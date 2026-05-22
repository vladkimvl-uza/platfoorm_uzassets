// frontend/src/api/aiClient.ts
//
// Pack 7.5: adds tool_use events for function calling.
//
// New ChatStreamEvent variants:
//   - tool_use_start { id, name, args }
//   - tool_use_end   { id, name, ok, summary }

const API_BASE = "/api";
const TOKEN_KEY = "uza_access_token";

// ─────────── Types ───────────

export type Role = "user" | "assistant";

export interface ChatMessage {
  role: Role;
  content: string;
}

export interface ToolCall {
  id: string;
  name: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  summary?: string;
  resultJson?: string;  // Pack 7.8: raw result for inspection
}

export type ChatStreamEvent =
  | { type: "meta"; conversationId: string }
  | { type: "text"; text: string }
  | { type: "stop"; reason: string }
  | { type: "tool_use_start"; id: string; name: string; args: Record<string, unknown> }
  | { type: "tool_use_end"; id: string; name: string; ok: boolean; summary: string; resultJson?: string }
  | { type: "error"; message: string; code?: string }
  | { type: "done" };

export interface ConversationListItem {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ConversationDetail extends ConversationListItem {
  messages: PersistedMessage[];
}

export interface PersistedMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
  tokens_in: number | null;
  tokens_out: number | null;
  stop_reason: string | null;
}

export interface AiHealth {
  enabled: boolean;
  model: string;
  has_api_key: boolean;
}

export interface AiConfig {
  role: string;
  style: string;
  model: string;
  temperature: number;
  max_tokens: number;
  custom_instructions: string | null;
}

// ─────────── Helpers ───────────

function getAuthHeader(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY) || "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function prettifyError(raw: unknown): string {
  if (!raw) return "Неизвестная ошибка";
  if (typeof raw === "string") return raw;
  if (typeof raw !== "object") return String(raw);

  const obj = raw as Record<string, unknown>;
  const errObj = obj.error;
  if (typeof errObj === "object" && errObj !== null) {
    const e = errObj as Record<string, unknown>;
    if (typeof e.message === "string") {
      const msg = e.message;
      if (msg.startsWith("{")) {
        try {
          const inner = JSON.parse(msg);
          const innerErr = inner?.error;
          if (innerErr?.message) {
            const t = innerErr.type;
            if (t === "rate_limit_error") {
              return `Лимит токенов превышен. Подождите ~1 минуту и попробуйте снова.\n\n(${innerErr.message})`;
            }
            if (t === "invalid_request_error") {
              return `Неверный запрос: ${innerErr.message}`;
            }
            if (t === "overloaded_error") {
              return "Сервис AI временно перегружен. Попробуйте через несколько секунд.";
            }
            return innerErr.message;
          }
        } catch { /* ignore */ }
      }
      return msg;
    }
  }
  if (typeof obj.message === "string") return obj.message;
  if (typeof obj.detail === "string") return obj.detail;
  return JSON.stringify(raw);
}

// ─────────── Streaming chat ───────────

export async function* streamChat(input: {
  conversationId?: string | null;
  messages: ChatMessage[];
  signal?: AbortSignal;
  role?: string | null;
  style?: string | null;
  model?: string | null;
  temperature?: number | null;
  maxTokens?: number | null;
}): AsyncGenerator<ChatStreamEvent> {
  const body = {
    conversation_id: input.conversationId ?? null,
    messages: input.messages,
    role: input.role ?? null,
    style: input.style ?? null,
    model: input.model ?? null,
    temperature: input.temperature ?? null,
    max_tokens: input.maxTokens ?? null,
  };

  const resp = await fetch(`${API_BASE}/ai/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
      ...getAuthHeader(),
    },
    body: JSON.stringify(body),
    signal: input.signal,
  });

  if (!resp.ok || !resp.body) {
    let errMsg = `HTTP ${resp.status}`;
    try {
      const errJson = await resp.json();
      errMsg = prettifyError(errJson) || errMsg;
    } catch {
      try { errMsg = (await resp.text()) || errMsg; } catch { /* ignore */ }
    }
    yield { type: "error", message: errMsg, code: `HTTP ${resp.status}` };
    return;
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let nlIdx: number;
    while ((nlIdx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, nlIdx);
      buffer = buffer.slice(nlIdx + 2);

      let evtName = "message";
      let dataStr = "";
      const lines = frame.split("\n");
      for (const ln of lines) {
        if (ln.startsWith("event:")) evtName = ln.slice(6).trim();
        else if (ln.startsWith("data:")) dataStr += ln.slice(5).trim();
      }

      if (evtName === "done") {
        yield { type: "done" };
        continue;
      }
      if (evtName === "error") {
        let parsed: unknown = dataStr;
        try { parsed = JSON.parse(dataStr); } catch { /* ignore */ }
        yield { type: "error", message: prettifyError(parsed) };
        continue;
      }

      // Pack 7.5: handle custom tool_use events
      if (evtName === "tool_use_start") {
        try {
          const obj = JSON.parse(dataStr);
          yield {
            type: "tool_use_start",
            id: obj.id || "",
            name: obj.name || "",
            args: obj.args || {},
          };
        } catch { /* ignore */ }
        continue;
      }
      if (evtName === "tool_use_end") {
        try {
          const obj = JSON.parse(dataStr);
          yield {
            type: "tool_use_end",
            id: obj.id || "",
            name: obj.name || "",
            ok: !!obj.ok,
            summary: obj.summary || "",
            resultJson: obj.result_json || undefined,
          };
        } catch { /* ignore */ }
        continue;
      }

      if (!dataStr || dataStr === "[DONE]") continue;

      try {
        const obj = JSON.parse(dataStr);
        if (obj.type === "meta" && obj.conversation_id) {
          yield { type: "meta", conversationId: obj.conversation_id };
        } else if (obj.type === "content_block_delta") {
          const t = obj.delta?.text;
          if (t) yield { type: "text", text: t };
        } else if (obj.type === "message_delta") {
          if (obj.delta?.stop_reason) {
            yield { type: "stop", reason: obj.delta.stop_reason };
          }
        } else if (obj.type === "error") {
          yield { type: "error", message: prettifyError(obj) };
        }
      } catch { /* not json */ }
    }
  }
}

// ─────────── Conversations ───────────

export async function listConversations(): Promise<ConversationListItem[]> {
  const resp = await fetch(`${API_BASE}/ai/conversations`, {
    headers: { ...getAuthHeader() },
  });
  if (!resp.ok) throw new Error(`Failed to list conversations: ${resp.status}`);
  return resp.json();
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const resp = await fetch(`${API_BASE}/ai/conversations/${id}`, {
    headers: { ...getAuthHeader() },
  });
  if (!resp.ok) throw new Error(`Failed to fetch conversation: ${resp.status}`);
  return resp.json();
}

export async function createConversation(title?: string): Promise<ConversationListItem> {
  const resp = await fetch(`${API_BASE}/ai/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify({ title: title ?? null }),
  });
  if (!resp.ok) throw new Error(`Failed to create conversation: ${resp.status}`);
  return resp.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const resp = await fetch(`${API_BASE}/ai/conversations/${id}`, {
    method: "DELETE",
    headers: { ...getAuthHeader() },
  });
  if (!resp.ok) throw new Error(`Failed to delete conversation: ${resp.status}`);
}

export async function renameConversation(id: string, title: string): Promise<ConversationListItem> {
  const resp = await fetch(`${API_BASE}/ai/conversations/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) throw new Error(`Failed to rename: ${resp.status}`);
  return resp.json();
}

// ─────────── Health ───────────

export async function getHealth(): Promise<AiHealth> {
  const resp = await fetch(`${API_BASE}/ai/health`, { headers: { ...getAuthHeader() } });
  if (!resp.ok) throw new Error(`Health check failed: ${resp.status}`);
  return resp.json();
}

// ─────────── Config ───────────

export async function getConfig(): Promise<AiConfig> {
  const resp = await fetch(`${API_BASE}/ai/config`, { headers: { ...getAuthHeader() } });
  if (!resp.ok) throw new Error(`Failed to load config: ${resp.status}`);
  return resp.json();
}

export async function saveConfig(cfg: Partial<AiConfig>): Promise<AiConfig> {
  const resp = await fetch(`${API_BASE}/ai/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...getAuthHeader() },
    body: JSON.stringify(cfg),
  });
  if (!resp.ok) {
    let msg = `HTTP ${resp.status}`;
    try { msg = (await resp.json())?.detail || msg; } catch { /* ignore */ }
    throw new Error(msg);
  }
  return resp.json();
}
