<template>
  <article
    class="ai-msg ai-msg-appear"
    :class="[
      role === 'user' ? 'ai-msg-user' : 'ai-msg-assistant',
      { 'ai-msg-error': error },
    ]"
  >
    <!-- AI avatar -->
    <div
      v-if="role === 'assistant'"
      class="ai-msg-avatar ai-avatar-glow"
      :class="{ 'is-active': pending }"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
      </svg>
    </div>

    <div class="ai-msg-body">
      <header class="ai-msg-head">
        <span class="ai-msg-role">
          {{ role === 'user' ? 'Вы' : 'ИИ-ассистент' }}
        </span>
        <span v-if="error" class="ai-msg-status-err">ошибка</span>
        <span v-else-if="pending && !content && (!toolCalls || !toolCalls.length)" class="ai-msg-status-think">
          <span class="ai-msg-dots"><i></i><i></i><i></i></span>
        </span>
      </header>

      <!-- Tool call badges (assistant only) -->
      <div v-if="role === 'assistant' && toolCalls && toolCalls.length" class="ai-msg-tools">
        <div
          v-for="call in toolCalls"
          :key="call.id"
          class="ai-msg-tool"
          :class="{
            'ai-msg-tool-pending': call.ok === undefined,
            'ai-msg-tool-ok': call.ok === true,
            'ai-msg-tool-err': call.ok === false,
          }"
        >
          <button
            class="ai-msg-tool-row"
            type="button"
            :disabled="!call.resultJson"
            @click="toggleExpand(call.id)"
          >
            <svg
              v-if="call.ok === undefined"
              class="ai-msg-tool-spinner"
              width="12" height="12" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round"
            >
              <circle cx="12" cy="12" r="9" stroke-dasharray="14 14" stroke-dashoffset="0"/>
            </svg>
            <svg
              v-else-if="call.ok"
              width="12" height="12" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            <svg
              v-else
              width="12" height="12" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
            <span class="ai-msg-tool-text">
              <span class="ai-msg-tool-name">{{ formatToolName(call.name) }}</span>
              <span class="ai-msg-tool-args" v-if="formatArgs(call.args)">
                {{ formatArgs(call.args) }}
              </span>
              <span v-if="call.summary" class="ai-msg-tool-summary">— {{ call.summary }}</span>
            </span>
            <svg
              v-if="call.resultJson"
              class="ai-msg-tool-chevron"
              :class="{ 'is-open': isExpanded(call.id) }"
              width="11" height="11" viewBox="0 0 24 24"
              fill="none" stroke="currentColor" stroke-width="2.5"
              stroke-linecap="round" stroke-linejoin="round"
            >
              <polyline points="6 9 12 15 18 9"/>
            </svg>
          </button>
          <div v-if="isExpanded(call.id) && call.resultJson" class="ai-msg-tool-json">
            <div class="ai-msg-tool-json-header">
              <span>tool result · {{ call.name }}</span>
              <button type="button" class="ai-msg-tool-copy" @click.stop="copyJson(call.resultJson)">
                {{ copiedId === call.id ? 'скопировано' : 'копировать' }}
              </button>
            </div>
            <pre class="ai-msg-tool-json-body"><code>{{ prettyJson(call.resultJson) }}</code></pre>
          </div>
        </div>
      </div>

      <!-- Bubble (only if there's content) -->
      <div
        v-if="content || (!toolCalls || !toolCalls.length)"
        class="ai-msg-bubble"
        :class="{
          'ai-msg-bubble-user': role === 'user',
          'ai-msg-bubble-ai': role === 'assistant',
          'ai-msg-bubble-error': error,
        }"
      >
        <span class="ai-msg-content" v-html="rendered"></span>
        <span v-if="pending && content" class="ai-cursor"></span>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import type { ToolCall } from "@/api/aiClient";

const props = defineProps<{
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
  toolCalls?: ToolCall[];
}>();

const rendered = computed(() => {
  if (!props.content) return "";
  if (props.role === "user") {
    return escapeHtml(props.content).replace(/\n/g, "<br>");
  }
  return renderMarkdown(props.content);
});

const TOOL_NAMES_RU: Record<string, string> = {
  get_company_full: "Профиль компании",
  list_overdue_tasks: "Просроченные задачи",
  compare_companies: "Сравнение компаний",
  search_tasks: "Поиск задач",
  // Pack 7.6
  get_financials: "Финансовая отчётность",
  get_governance: "Корпоративное управление",
  get_credit_portfolio: "Кредитный портфель",
  get_kpi_summary: "Сводка по портфелю",
  search_audit_log: "Журнал действий",
  get_ratings_history: "История рейтингов",
  // Pack 7.7
  get_task_details: "Детали задачи",
  get_project_details: "Детали проекта",
  search_comments: "Поиск в комментариях",
  list_consultants: "Список консультантов",
  list_carried_over: "Перенесённые задачи",
};

function formatToolName(name: string): string {
  return TOOL_NAMES_RU[name] || name;
}

// Pack 7.8: expandable tool result viewer
const expanded = ref<Set<string>>(new Set());
const copiedId = ref<string | null>(null);

function isExpanded(id: string): boolean {
  return expanded.value.has(id);
}

function toggleExpand(id: string): void {
  const next = new Set(expanded.value);
  if (next.has(id)) {
    next.delete(id);
  } else {
    next.add(id);
  }
  expanded.value = next;
}

function prettyJson(raw?: string): string {
  if (!raw) return "";
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

async function copyJson(raw?: string): Promise<void> {
  if (!raw) return;
  try {
    await navigator.clipboard.writeText(prettyJson(raw));
    // Find which call this came from to flash "copied"
    for (const c of (props.toolCalls || [])) {
      if (c.resultJson === raw) {
        copiedId.value = c.id;
        setTimeout(() => { copiedId.value = null; }, 1400);
        return;
      }
    }
  } catch {
    /* clipboard unavailable */
  }
}

function formatArgs(args?: Record<string, unknown>): string {
  if (!args) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(args)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      parts.push(v.join(", "));
    } else if (typeof v === "string") {
      parts.push(v);
    } else if (typeof v === "number" || typeof v === "boolean") {
      parts.push(String(v));
    }
  }
  if (!parts.length) return "";
  const joined = parts.join(" · ");
  return joined.length > 60 ? joined.slice(0, 57) + "…" : joined;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderMarkdown(src: string): string {
  const codeBlocks: string[] = [];
  let text = src.replace(/```(\w+)?\n([\s\S]*?)```/g, (_m, _lang, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(`<pre><code>${escapeHtml(code.trimEnd())}</code></pre>`);
    return `\u0000CODEBLOCK_${idx}\u0000`;
  });

  const inlineCode: string[] = [];
  text = text.replace(/`([^`\n]+)`/g, (_m, code) => {
    const idx = inlineCode.length;
    inlineCode.push(`<code>${escapeHtml(code)}</code>`);
    return `\u0000INLINECODE_${idx}\u0000`;
  });

  text = escapeHtml(text);
  text = text.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
  text = text.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  text = text.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  text = text.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");
  text = text.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/(?<![*\w])\*([^*\n]+)\*(?!\w)/g, "<em>$1</em>");
  text = text.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  text = text.replace(/^&gt;\s+(.+)$/gm, "<blockquote>$1</blockquote>");
  text = text.replace(/<\/blockquote>\n<blockquote>/g, "<br>");

  const lines = text.split("\n");
  const out: string[] = [];
  let listType: "ul" | "ol" | null = null;
  for (const ln of lines) {
    const ulMatch = /^\s*[-*]\s+(.+)$/.exec(ln);
    const olMatch = /^\s*(\d+)\.\s+(.+)$/.exec(ln);
    if (ulMatch) {
      if (listType !== "ul") {
        if (listType === "ol") out.push("</ol>");
        out.push("<ul>");
        listType = "ul";
      }
      out.push(`<li>${ulMatch[1]}</li>`);
    } else if (olMatch) {
      if (listType !== "ol") {
        if (listType === "ul") out.push("</ul>");
        out.push("<ol>");
        listType = "ol";
      }
      out.push(`<li>${olMatch[2]}</li>`);
    } else {
      if (listType === "ul") { out.push("</ul>"); listType = null; }
      if (listType === "ol") { out.push("</ol>"); listType = null; }
      out.push(ln);
    }
  }
  if (listType === "ul") out.push("</ul>");
  if (listType === "ol") out.push("</ol>");
  text = out.join("\n");

  const blocks = text.split(/\n{2,}/);
  text = blocks
    .map((block) => {
      const t = block.trim();
      if (!t) return "";
      if (/^<(h[1-6]|ul|ol|pre|blockquote|p|div)/.test(t) || /CODEBLOCK_\d+/.test(t)) return t;
      return `<p>${t.replace(/\n/g, "<br>")}</p>`;
    })
    .filter(Boolean)
    .join("\n");

  text = text.replace(/\u0000CODEBLOCK_(\d+)\u0000/g, (_m, i) => codeBlocks[+i] || "");
  text = text.replace(/\u0000INLINECODE_(\d+)\u0000/g, (_m, i) => inlineCode[+i] || "");
  return text;
}
</script>

<style scoped>
.ai-msg {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.ai-msg-user { flex-direction: row-reverse; }

.ai-msg-avatar {
  flex-shrink: 0;
  width: 32px; height: 32px;
  border-radius: 10px;
  background: var(--uza-navy);
  color: white;
  display: grid;
  place-items: center;
  box-shadow: var(--ai-shadow-soft);
  margin-top: 22px;
}

.ai-msg-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 78%;
  min-width: 0;
}
.ai-msg-user .ai-msg-body { align-items: flex-end; }

.ai-msg-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 4px;
}
.ai-msg-role {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(30, 42, 74, 0.5);
}

.ai-msg-status-err {
  font-size: 10px;
  font-weight: 500;
  color: var(--uza-red);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.ai-msg-status-think .ai-msg-dots {
  display: inline-flex;
  gap: 3px;
  align-items: center;
}
.ai-msg-status-think .ai-msg-dots i {
  width: 4px; height: 4px;
  background: var(--uza-purple);
  border-radius: 50%;
  animation: ai-think-pulse 1.2s ease-in-out infinite;
}
.ai-msg-status-think .ai-msg-dots i:nth-child(2) { animation-delay: .15s; }
.ai-msg-status-think .ai-msg-dots i:nth-child(3) { animation-delay: .30s; }
@keyframes ai-think-pulse {
  0%, 80%, 100% { opacity: .25; transform: scale(.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* Tool call badges */
.ai-msg-tools {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 4px;
}
.ai-msg-tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 10px;
  font-size: 11.5px;
  line-height: 1.4;
  background: rgba(255, 255, 255, 0.7);
  -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
  border: 1px solid var(--ai-glass-border);
  color: var(--uza-navy);
  animation: ai-tool-in 0.3s var(--ai-easing) both;
}
@keyframes ai-tool-in {
  from { opacity: 0; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}
.ai-msg-tool-pending {
  border-color: rgba(127, 119, 221, 0.32);
  color: var(--uza-purple);
  background: rgba(127, 119, 221, 0.06);
}
.ai-msg-tool-ok {
  border-color: rgba(29, 158, 117, 0.28);
  color: var(--uza-teal);
  background: rgba(29, 158, 117, 0.06);
}
.ai-msg-tool-err {
  border-color: rgba(226, 75, 74, 0.32);
  color: var(--uza-red);
  background: rgba(226, 75, 74, 0.06);
}

.ai-msg-tool-spinner {
  animation: ai-tool-spin 0.9s linear infinite;
  flex-shrink: 0;
}
@keyframes ai-tool-spin { to { transform: rotate(360deg); } }

.ai-msg-tool-text {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  flex-wrap: wrap;
}
.ai-msg-tool-name {
  font-weight: 500;
  letter-spacing: -0.01em;
}
.ai-msg-tool-args {
  font-size: 10.5px;
  color: rgba(30, 42, 74, 0.55);
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
.ai-msg-tool-summary {
  font-size: 10.5px;
  opacity: 0.75;
}

/* Bubble */
.ai-msg-bubble {
  padding: 10px 14px;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--uza-navy);
  word-break: break-word;
  overflow-wrap: anywhere;
  position: relative;
}

.ai-msg-bubble-user {
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: #fff;
  border-radius: var(--ai-radius-lg) var(--ai-radius-lg) 4px var(--ai-radius-lg);
  box-shadow:
    0 4px 14px rgba(127, 119, 221, 0.28),
    inset 0 1px 0 rgba(255, 255, 255, 0.12);
}

.ai-msg-bubble-ai {
  background: var(--ai-glass-bg-strong);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-lg) var(--ai-radius-lg) var(--ai-radius-lg) 4px;
  box-shadow: var(--ai-shadow-soft);
}

.ai-msg-bubble-error {
  background: rgba(254, 242, 242, 0.95);
  border-color: rgba(252, 165, 165, 0.7);
  color: #991B1B;
}

/* Markdown */
.ai-msg-content :deep(h1),
.ai-msg-content :deep(h2),
.ai-msg-content :deep(h3),
.ai-msg-content :deep(h4) {
  font-weight: 500;
  margin: 12px 0 6px;
  letter-spacing: -0.01em;
  line-height: 1.35;
}
.ai-msg-content :deep(h1) { font-size: 16px; }
.ai-msg-content :deep(h2) { font-size: 14.5px; }
.ai-msg-content :deep(h3) { font-size: 13.5px; }
.ai-msg-content :deep(h4) { font-size: 13px; }
.ai-msg-content :deep(h1:first-child),
.ai-msg-content :deep(h2:first-child),
.ai-msg-content :deep(h3:first-child),
.ai-msg-content :deep(h4:first-child) { margin-top: 0; }

.ai-msg-content :deep(p) { margin: 6px 0; }
.ai-msg-content :deep(p:first-child) { margin-top: 0; }
.ai-msg-content :deep(p:last-child) { margin-bottom: 0; }

.ai-msg-content :deep(strong) { font-weight: 500; }
.ai-msg-content :deep(em) { font-style: italic; }

.ai-msg-content :deep(ul),
.ai-msg-content :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}
.ai-msg-content :deep(li) { margin: 3px 0; line-height: 1.55; }

.ai-msg-content :deep(code) {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 12px;
  background: rgba(127, 119, 221, 0.08);
  padding: 1px 5px;
  border-radius: 4px;
  color: var(--uza-purple-3);
}

.ai-msg-content :deep(pre) {
  background: rgba(30, 42, 74, 0.04);
  border: 1px solid rgba(30, 42, 74, 0.08);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0;
  overflow-x: auto;
  font-size: 12px;
  line-height: 1.5;
}
.ai-msg-content :deep(pre code) {
  background: transparent;
  padding: 0;
  color: var(--uza-navy);
}

.ai-msg-content :deep(a) {
  color: var(--uza-purple);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
}
.ai-msg-content :deep(a:hover) { color: var(--uza-purple-3); }

.ai-msg-content :deep(blockquote) {
  border-left: 2px solid var(--uza-purple);
  padding-left: 10px;
  margin: 8px 0;
  color: rgba(30, 42, 74, 0.7);
}

.ai-msg-bubble-user .ai-msg-content :deep(code) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}
.ai-msg-bubble-user .ai-msg-content :deep(strong) { color: #fff; }
.ai-msg-bubble-user .ai-msg-content :deep(a) {
  color: #fff;
  text-decoration-color: rgba(255, 255, 255, 0.6);
}

/* Pack 7.8: expandable tool result */
.ai-msg-tool-row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  background: transparent;
  border: 0;
  padding: 0;
  margin: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
  text-align: left;
}
.ai-msg-tool-row:disabled {
  cursor: default;
}
.ai-msg-tool-chevron {
  margin-left: auto;
  flex-shrink: 0;
  opacity: 0.6;
  transition: transform .2s var(--ai-easing), opacity .2s;
}
.ai-msg-tool-chevron.is-open {
  transform: rotate(180deg);
  opacity: 0.95;
}
.ai-msg-tool-json {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px dashed rgba(30, 42, 74, 0.18);
  animation: ai-tool-json-in .25s var(--ai-easing) both;
}
@keyframes ai-tool-json-in {
  from { opacity: 0; transform: translateY(-2px); }
  to   { opacity: 1; transform: translateY(0); }
}
.ai-msg-tool-json-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: rgba(30, 42, 74, 0.5);
  margin-bottom: 4px;
}
.ai-msg-tool-copy {
  background: transparent;
  border: 1px solid rgba(30, 42, 74, 0.18);
  border-radius: 6px;
  padding: 2px 8px;
  font-size: 9.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: rgba(30, 42, 74, 0.65);
  cursor: pointer;
  transition: background .15s, border-color .15s;
}
.ai-msg-tool-copy:hover {
  background: rgba(127, 119, 221, 0.08);
  border-color: rgba(127, 119, 221, 0.4);
  color: var(--uza-purple-3);
}
.ai-msg-tool-json-body {
  margin: 0;
  padding: 8px 10px;
  background: rgba(30, 42, 74, 0.06);
  border-radius: 6px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 10.5px;
  line-height: 1.45;
  color: var(--uza-navy);
  max-height: 320px;
  overflow: auto;
  white-space: pre;
  word-wrap: normal;
}

</style>
