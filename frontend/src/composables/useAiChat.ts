// frontend/src/composables/useAiChat.ts
//
// tracks tool calls per assistant message.
// UiMessage now has a toolCalls[] array, populated from tool_use_start/end events.

import { ref, computed } from "vue";
import {
  streamChat,
  getConversation,
  type ChatMessage,
  type ChatStreamEvent,
  type ToolCall,
} from "@/api/aiClient";

export interface UiMessage {
  id?: string;
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
  stopReason?: string | null;
  maxTokensReached?: boolean;
  toolCalls?: ToolCall[];
}

export function useAiChat() {
  const messages = ref<UiMessage[]>([]);
  const conversationId = ref<string | null>(null);
  const isStreaming = ref(false);
  const error = ref<string | null>(null);
  let abortCtrl: AbortController | null = null;

  function reset() {
    messages.value = [];
    conversationId.value = null;
    error.value = null;
    if (abortCtrl) {
      abortCtrl.abort();
      abortCtrl = null;
    }
    isStreaming.value = false;
  }

  function abort() {
    if (abortCtrl) {
      abortCtrl.abort();
      abortCtrl = null;
    }
    isStreaming.value = false;
  }

  async function loadConversation(id: string) {
    reset();
    try {
      const conv = await getConversation(id);
      conversationId.value = conv.id;
      messages.value = conv.messages
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          stopReason: m.stop_reason,
          maxTokensReached: m.stop_reason === "max_tokens",
        }));
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  function _updateLast(patch: Partial<UiMessage>) {
    const i = messages.value.length - 1;
    if (i < 0) return;
    messages.value[i] = { ...messages.value[i], ...patch };
  }

  function _appendToLast(text: string) {
    const i = messages.value.length - 1;
    if (i < 0) return;
    messages.value[i] = {
      ...messages.value[i],
      content: messages.value[i].content + text,
    };
  }

  function _addToolCall(call: ToolCall) {
    const i = messages.value.length - 1;
    if (i < 0) return;
    const existing = messages.value[i].toolCalls || [];
    messages.value[i] = {
      ...messages.value[i],
      toolCalls: [...existing, call],
    };
  }

  function _updateToolCall(id: string, patch: Partial<ToolCall>) {
    const i = messages.value.length - 1;
    if (i < 0) return;
    const calls = messages.value[i].toolCalls || [];
    const newCalls = calls.map((c) => (c.id === id ? { ...c, ...patch } : c));
    messages.value[i] = { ...messages.value[i], toolCalls: newCalls };
  }

  async function send(
    text: string,
    options?: {
      role?: string;
      style?: string;
      model?: string;
      temperature?: number;
      maxTokens?: number;
      web?: boolean;
    },
  ) {
    if (!text.trim() || isStreaming.value) return;

    const trimmed = text.trim();
    error.value = null;

    messages.value = [...messages.value, { role: "user", content: trimmed }];
    messages.value = [
      ...messages.value,
      { role: "assistant", content: "", pending: true, toolCalls: [] },
    ];

    isStreaming.value = true;
    abortCtrl = new AbortController();

    try {
      const apiMessages: ChatMessage[] = messages.value
        .filter((m) => !m.pending && !m.error)
        .map((m) => ({ role: m.role, content: m.content }));

      const stream = streamChat({
        conversationId: conversationId.value,
        messages: apiMessages,
        signal: abortCtrl.signal,
        role: options?.role,
        style: options?.style,
        model: options?.model,
        temperature: options?.temperature,
        maxTokens: options?.maxTokens,
        web: options?.web,
      });

      for await (const ev of stream as AsyncGenerator<ChatStreamEvent>) {
        if (ev.type === "meta") {
          conversationId.value = ev.conversationId;
        } else if (ev.type === "text") {
          _appendToLast(ev.text);
        } else if (ev.type === "stop") {
          _updateLast({
            stopReason: ev.reason,
            maxTokensReached: ev.reason === "max_tokens",
          });
        } else if (ev.type === "tool_use_start") {
          _addToolCall({ id: ev.id, name: ev.name, args: ev.args });
        } else if (ev.type === "tool_use_end") {
          _updateToolCall(ev.id, {
            ok: ev.ok,
            summary: ev.summary,
            resultJson: ev.resultJson,
          });
        } else if (ev.type === "error") {
          _updateLast({
            content: messages.value[messages.value.length - 1].content || "",
            pending: false,
            error: true,
          });
          error.value = ev.message;
        } else if (ev.type === "done") {
          _updateLast({ pending: false });
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg !== "AbortError" && !(e instanceof Error && e.name === "AbortError")) {
        error.value = msg;
        _updateLast({ pending: false, error: true });
      }
    } finally {
      _updateLast({ pending: false });
      isStreaming.value = false;
      abortCtrl = null;
    }
  }

  async function continueResponse(options?: {
    role?: string;
    style?: string;
    model?: string;
    temperature?: number;
    maxTokens?: number;
  }) {
    if (isStreaming.value) return;
    const last = messages.value[messages.value.length - 1];
    if (!last || last.role !== "assistant" || !last.maxTokensReached) return;
    await send("Продолжай с того места где остановился.", options);
  }

  /** Drop trailing assistant + user turn (for retry flow). Returns the user text. */
  function popLastTurn(): string {
    error.value = null;
    let trim = messages.value.length;
    if (trim > 0 && messages.value[trim - 1].role === "assistant") trim--;
    let userText = "";
    if (trim > 0 && messages.value[trim - 1].role === "user") {
      userText = messages.value[trim - 1].content;
      trim--;
    }
    messages.value = messages.value.slice(0, trim);
    return userText;
  }

  return {
    messages: computed(() => messages.value),
    conversationId: computed(() => conversationId.value),
    isStreaming: computed(() => isStreaming.value),
    error: computed(() => error.value),
    canContinue: computed(() => {
      const last = messages.value[messages.value.length - 1];
      return Boolean(last && last.role === "assistant" && last.maxTokensReached && !isStreaming.value);
    }),
    send,
    abort,
    reset,
    loadConversation,
    continueResponse,
    popLastTurn,
  };
}
