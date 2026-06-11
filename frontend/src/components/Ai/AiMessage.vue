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
      <svg class="ai-logo" width="19" height="19" viewBox="0 0 32 32" fill="none">
        <defs>
          <linearGradient id="aiLogoGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#7F77DD"/>
            <stop offset="100%" stop-color="#1D9E75"/>
          </linearGradient>
        </defs>
        <path class="ai-logo-arrow" d="M 10 4 L 30 16 L 10 28 L 14 16 Z" fill="url(#aiLogoGrad)"/>
        <rect class="ai-logo-dot" x="6" y="5"  width="2" height="2"/>
        <rect class="ai-logo-dot" x="3" y="10" width="2" height="2"/>
        <rect class="ai-logo-dot" x="1" y="15" width="2" height="2"/>
        <rect class="ai-logo-dot" x="3" y="20" width="2" height="2"/>
        <rect class="ai-logo-dot" x="6" y="26" width="2" height="2"/>
      </svg>
    </div>

    <div class="ai-msg-body">
      <header class="ai-msg-head">
        <span class="ai-msg-role">
          {{ role === 'user' ? 'Вы' : 'ИИ-ассистент' }}
        </span>
        <span v-if="error" class="ai-msg-status-err">ошибка</span>
        <span v-else-if="pending && !content" class="ai-msg-status-think">
          <span class="ai-gen-orb"></span>
          <span class="ai-gen-label">генерирует ответ</span>
        </span>
      </header>

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

      <!-- Графики, построенные ИИ на лету -->
      <AiChart v-for="(c, ci) in charts" :key="`chart-${ci}`" :spec="c" />

      <!-- Copy action — для своего запроса и ответа ИИ -->
      <div v-if="content && !error && !pending" class="ai-msg-actions">
        <button
          type="button"
          class="ai-msg-copy"
          :class="{ 'is-done': contentCopied }"
          :title="role === 'user' ? 'Скопировать запрос' : 'Скопировать ответ'"
          @click="copyContent"
        >
          <svg v-if="!contentCopied" width="13" height="13" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          <svg v-else width="13" height="13" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2.5"
               stroke-linecap="round" stroke-linejoin="round">
            <polyline points="20 6 9 17 4 12"/>
          </svg>
          <span>{{ contentCopied ? 'Скопировано' : 'Копировать' }}</span>
        </button>
        <button
          v-if="role === 'assistant' && voice.state.supported"
          type="button"
          class="ai-msg-copy ai-msg-speak"
          :class="{ 'is-speaking': isSpeaking }"
          :title="isSpeaking ? 'Остановить озвучку' : 'Прослушать ответ'"
          @click="speakThis"
        >
          <svg v-if="!isSpeaking" width="13" height="13" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
            <path d="M15.5 8.5a5 5 0 0 1 0 7"/>
            <path d="M19 5a9 9 0 0 1 0 14"/>
          </svg>
          <svg v-else width="13" height="13" viewBox="0 0 24 24"
               fill="none" stroke="currentColor" stroke-width="2.4"
               stroke-linecap="round" stroke-linejoin="round">
            <rect x="6" y="6" width="12" height="12" rx="2"/>
          </svg>
          <span>{{ isSpeaking ? 'Озвучивается' : 'Прослушать' }}</span>
        </button>
      </div>

      <!-- Follow-up чипы — продолжение диалога -->
      <div v-if="followups.length && !pending && !error" class="ai-msg-followups">
        <button
          v-for="(f, fi) in followups"
          :key="fi"
          type="button"
          class="ai-msg-fchip"
          :style="{ animationDelay: `${fi * 60}ms` }"
          @click="emit('ask', f)"
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
          <span>{{ f }}</span>
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import DOMPurify from "dompurify";
import type { ToolCall } from "@/api/aiClient";
import { useAiVoice } from "@/composables/useAiVoice";
import AiChart from "@/components/Ai/AiChart.vue";

const props = defineProps<{
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  error?: boolean;
  toolCalls?: ToolCall[];
}>();
const emit = defineEmits<{ ask: [text: string] }>();

const voice = useAiVoice();
let _msgKeyCounter = (globalThis as any).__aiMsgKey || 0;
(globalThis as any).__aiMsgKey = ++_msgKeyCounter;
const msgKey = `m${_msgKeyCounter}`;

// Парсинг служебной строки follow-ups: «[[followups]] q1 | q2 | q3»
const followups = computed<string[]>(() => {
  if (props.role !== "assistant" || !props.content) return [];
  const m = props.content.match(/\[\[followups\]\]\s*([^\n]*)\s*$/i);
  if (!m) return [];
  return m[1].split("|").map((s) => s.trim()).filter(Boolean).slice(0, 3);
});
// Тело без служебной строки follow-ups
const bodyContent = computed(() =>
  props.content.replace(/\n*\[\[followups\]\][^\n]*\s*$/i, "").trimEnd(),
);

// Графики «на лету»: блоки ```uzachart {json}``` → спецификации Chart.js
const charts = computed<any[]>(() => {
  if (props.role !== "assistant" || props.pending) return [];
  const out: any[] = [];
  const re = /```uzachart\s*([\s\S]*?)```/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(bodyContent.value)) !== null) {
    try {
      const spec = JSON.parse(m[1].trim());
      if (spec && typeof spec === "object") out.push(spec);
    } catch { /* пропускаем кривой JSON */ }
  }
  return out;
});
// Тело для рендера без chart-блоков
const renderBody = computed(() =>
  bodyContent.value.replace(/```uzachart\s*[\s\S]*?```/gi, "").trimEnd(),
);
const isSpeaking = computed(() => voice.state.speakingKey === msgKey);
function speakThis() { voice.speak(msgKey, bodyContent.value); }

// Авто-озвучка завершённого ответа в голосовом режиме
watch(
  () => props.pending,
  (now, was) => {
    if (was && !now && props.role === "assistant" && !props.error
        && voice.state.voiceMode && bodyContent.value) {
      voice.speak(msgKey, bodyContent.value);
    }
  },
);

// Belt-and-suspenders XSS defense: even though renderMarkdown calls
// escapeHtml on user input before reconstructing HTML, DOMPurify enforces
// an explicit allowlist of tags/attrs. Any future regression in
// renderMarkdown (e.g. adding a new inline format that forgets to escape)
// is contained — DOMPurify strips script/iframe/event handlers no matter
// how they got in.
const SAFE_TAGS = ["p","br","strong","em","b","i","u","s","del","code","pre","blockquote","ul","ol","li","a","span","div","h1","h2","h3","h4","table","thead","tbody","tr","th","td"];
const SAFE_ATTRS = ["href","title","class","target","rel"];

function purify(html: string): string {
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: SAFE_TAGS,
    ALLOWED_ATTR: SAFE_ATTRS,
    ALLOW_DATA_ATTR: false,
    FORBID_TAGS: ["script","iframe","object","embed","form","input","button"],
    FORBID_ATTR: ["style","onerror","onload","onclick"],
  });
}

const rendered = computed(() => {
  if (!props.content) return "";
  if (props.role === "user") {
    // User input is pure-text plus newline → <br>. escapeHtml + purify is overkill
    // but free; if escapeHtml ever drops a character class, purify catches it.
    return purify(escapeHtml(props.content).replace(/\n/g, "<br>"));
  }
  return purify(renderMarkdown(renderBody.value));
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

const contentCopied = ref(false);
async function copyContent(): Promise<void> {
  if (!props.content) return;
  try {
    await navigator.clipboard.writeText(props.content);
    contentCopied.value = true;
    setTimeout(() => { contentCopied.value = false; }, 1400);
  } catch {
    /* clipboard unavailable */
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
  const closeList = () => {
    if (listType === "ul") out.push("</ul>");
    if (listType === "ol") out.push("</ol>");
    listType = null;
  };
  // GFM-таблицы: строка-заголовок + строка-разделитель |---|:--:|
  const splitRow = (s: string): string[] => {
    let t = s.trim();
    if (t.startsWith("|")) t = t.slice(1);
    if (t.endsWith("|")) t = t.slice(0, -1);
    return t.split("|").map((c) => c.trim());
  };
  const alignClass = (a: string): string =>
    a === "right" ? ' class="ai-al-r"' : a === "center" ? ' class="ai-al-c"' : "";
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    const sep = lines[i + 1] ?? "";
    if (
      /\|/.test(ln) &&
      ln.trim() !== "" &&
      /^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$/.test(sep) &&
      sep.includes("-")
    ) {
      closeList();
      const headers = splitRow(ln);
      const aligns = splitRow(sep).map((c) => {
        const l = c.startsWith(":"), r = c.endsWith(":");
        return l && r ? "center" : r ? "right" : l ? "left" : "";
      });
      let j = i + 2;
      const rows: string[][] = [];
      while (j < lines.length && /\|/.test(lines[j]) && lines[j].trim() !== "") {
        rows.push(splitRow(lines[j]));
        j++;
      }
      let tbl = '<table class="ai-table"><thead><tr>';
      headers.forEach((h, k) => { tbl += `<th${alignClass(aligns[k])}>${h}</th>`; });
      tbl += "</tr></thead><tbody>";
      for (const r of rows) {
        tbl += "<tr>";
        for (let k = 0; k < headers.length; k++) {
          tbl += `<td${alignClass(aligns[k])}>${r[k] ?? ""}</td>`;
        }
        tbl += "</tr>";
      }
      tbl += "</tbody></table>";
      out.push(`<div class="ai-table-wrap">${tbl}</div>`);
      i = j - 1;
      continue;
    }
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
      if (/^<(h[1-6]|ul|ol|pre|blockquote|table|p|div)/.test(t) || /CODEBLOCK_\d+/.test(t)) return t;
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

/* Фирменный знак платформы как аватар ИИ + уникальная анимация
   «поток данных в стрелку»: точки трейла загораются волной к острию,
   острие мягко подсвечивается в такт. */
.ai-logo { overflow: visible; }
.ai-logo-arrow {
  transform-origin: 16px 16px;
  animation: ai-logo-arrow 2.8s var(--ai-easing, ease-in-out) infinite;
}
.ai-logo-dot {
  fill: #7F77DD;
  transform-origin: center;
  transform-box: fill-box;
  opacity: 0.3;
  animation: ai-logo-flow 2.4s var(--ai-easing, ease-in-out) infinite;
}
/* трейл: дальняя точка (низ дуги) → ближняя к острию (верх) */
.ai-logo-dot:nth-child(5) { animation-delay: 0s;    }
.ai-logo-dot:nth-child(4) { animation-delay: 0.12s; }
.ai-logo-dot:nth-child(3) { animation-delay: 0.24s; }
.ai-logo-dot:nth-child(2) { animation-delay: 0.36s; }
.ai-logo-dot:nth-child(1) { animation-delay: 0.48s; }
@keyframes ai-logo-flow {
  0%, 70%, 100% { opacity: 0.28; transform: scale(0.85); }
  35%           { opacity: 1;    transform: scale(1.5); }
}
@keyframes ai-logo-arrow {
  0%, 100% { filter: drop-shadow(0 0 0 rgba(127,119,221,0)); transform: translateX(0); }
  45%      { filter: drop-shadow(0 0 3px rgba(127,119,221,0.6)); transform: translateX(0.6px); }
}
/* Активная генерация — поток ускоряется и ярче */
.ai-msg-avatar.is-active .ai-logo-dot { animation-duration: 1.1s; }
.ai-msg-avatar.is-active .ai-logo-arrow { animation-duration: 1.3s; }
@media (prefers-reduced-motion: reduce) {
  .ai-logo-dot, .ai-logo-arrow { animation: none !important; }
  .ai-logo-dot { opacity: 0.7; }
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
/* Премиальный индикатор генерации — вращающаяся орбита + shimmer-текст */
.ai-msg-status-think {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.ai-gen-orb {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background:
    conic-gradient(from 0deg,
      rgba(127, 119, 221, 0) 0deg,
      rgba(127, 119, 221, 0.15) 90deg,
      #7F77DD 270deg,
      #534AB7 360deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2px));
          mask: radial-gradient(farthest-side, transparent calc(100% - 2.5px), #000 calc(100% - 2px));
  animation: ai-gen-spin 0.9s linear infinite;
  filter: drop-shadow(0 0 4px rgba(127, 119, 221, 0.45));
}
@keyframes ai-gen-spin { to { transform: rotate(360deg); } }
.ai-gen-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.01em;
  background: linear-gradient(
    100deg,
    rgba(83, 74, 183, 0.45) 20%,
    #7F77DD 40%,
    #534AB7 50%,
    #7F77DD 60%,
    rgba(83, 74, 183, 0.45) 80%);
  background-size: 200% 100%;
  -webkit-background-clip: text;
          background-clip: text;
  -webkit-text-fill-color: transparent;
          color: transparent;
  animation: ai-gen-shimmer 1.6s linear infinite;
}
@keyframes ai-gen-shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
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

/* Премиальные таблицы — как в чат-боте AI engine */
.ai-msg-content :deep(.ai-table-wrap) {
  margin: 12px 0;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 11px;
}
.ai-msg-content :deep(table) {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 12.5px;
  line-height: 1.5;
  border: 1px solid #E5E7EB;
  border-radius: 11px;
  overflow: hidden;
  display: table;
  box-shadow: 0 1px 2px rgba(15, 23, 60, 0.04);
}
.ai-msg-content :deep(thead) {
  background: #FAFAFC;
}
.ai-msg-content :deep(th) {
  text-align: left;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
  padding: 9px 13px;
  border-bottom: 1px solid #E5E7EB;
  white-space: nowrap;
}
.ai-msg-content :deep(td) {
  padding: 8px 13px;
  border-bottom: 1px solid #EEF0F3;
  color: rgba(30, 42, 74, 0.86);
  vertical-align: top;
}
.ai-msg-content :deep(tbody tr:last-child td) { border-bottom: 0; }
.ai-msg-content :deep(tbody tr:nth-child(even)) { background: rgba(250, 250, 252, 0.55); }
.ai-msg-content :deep(tbody tr:hover) { background: rgba(127, 119, 221, 0.06); }
.ai-msg-content :deep(td.ai-al-r),
.ai-msg-content :deep(th.ai-al-r) { text-align: right; font-variant-numeric: tabular-nums; }
.ai-msg-content :deep(td.ai-al-c),
.ai-msg-content :deep(th.ai-al-c) { text-align: center; }
/* Числовые ячейки — моноширинные цифры для ровных колонок */
.ai-msg-content :deep(td) { font-variant-numeric: tabular-nums; }

/* Кнопка копирования сообщения */
.ai-msg-actions {
  display: flex;
  padding: 2px 4px 0;
  opacity: 0;
  transition: opacity 0.14s ease;
}
.ai-msg-user .ai-msg-actions { justify-content: flex-end; }
.ai-msg:hover .ai-msg-actions { opacity: 1; }
.ai-msg-copy {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: transparent;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 500;
  color: var(--uza-muted, #888780);
  cursor: pointer;
  transition: all 0.14s ease;
}
.ai-msg-copy:hover {
  color: var(--uza-navy, #1E2A4A);
  border-color: #D5D8DE;
  background: #FAFAFC;
}
.ai-msg-copy.is-done {
  color: var(--uza-success, #1D9E75);
  border-color: rgba(29, 158, 117, 0.35);
}
.ai-msg-speak.is-speaking {
  color: var(--uza-purple, #7F77DD);
  border-color: rgba(127, 119, 221, 0.4);
  background: rgba(127, 119, 221, 0.07);
}
.ai-msg-speak.is-speaking svg { animation: ai-speak-pulse 1s ease-in-out infinite; }
@keyframes ai-speak-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }
/* На тач-устройствах кнопки видны всегда */
@media (hover: none) {
  .ai-msg-actions { opacity: 1; }
}

/* Follow-up чипы — продолжение диалога */
.ai-msg-followups {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  padding: 8px 4px 2px;
}
.ai-msg-fchip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(127, 119, 221, 0.28);
  background: rgba(127, 119, 221, 0.05);
  color: var(--uza-purple, #534AB7);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.3;
  text-align: left;
  cursor: pointer;
  transition: all 0.16s var(--ai-easing, ease);
  opacity: 0;
  animation: ai-fchip-in 0.4s var(--ai-easing, ease) both;
}
.ai-msg-fchip svg { color: rgba(127, 119, 221, 0.6); flex-shrink: 0; transition: transform 0.16s ease; }
.ai-msg-fchip:hover {
  background: #fff;
  border-color: rgba(127, 119, 221, 0.5);
  color: var(--uza-purple, #534AB7);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.14);
}
.ai-msg-fchip:hover svg { transform: translateX(2px); color: var(--uza-purple); }
@keyframes ai-fchip-in {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
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
