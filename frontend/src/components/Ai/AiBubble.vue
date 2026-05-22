<template>
  <!-- Floating FAB — shown on all routes except /login, /ai-chat, /forgot-password -->
  <Transition name="ai-bubble-fab">
    <button
      v-if="showFab"
      class="ai-bubble-fab"
      :class="{ 'is-active': panelOpen, 'is-thinking': chat.isStreaming.value }"
      type="button"
      :title="ctx?.label ? `ИИ-сводка: ${ctx.label}` : 'ИИ-помощник'"
      :aria-label="ctx?.label ? `ИИ-сводка: ${ctx.label}` : 'ИИ-помощник'"
      @click="togglePanel"
    >
      <span class="ai-bubble-fab-text">AI</span>
      <span v-if="chat.isStreaming.value" class="ai-bubble-fab-pulse" aria-hidden="true" />
    </button>
  </Transition>

  <Teleport to="body">
    <Transition name="ai-bubble-back">
      <div v-if="panelOpen" class="ai-bubble-back" @click="closePanel" />
    </Transition>

    <Transition name="ai-bubble-panel">
      <aside v-if="panelOpen" class="ai-bubble-panel" role="dialog" aria-modal="true">
        <header class="aibp-head">
          <div class="aibp-head-l">
            <div class="aibp-icon"><EptLogo :size="22" /></div>
            <div>
              <h3>{{ ctx?.label || "ИИ-помощник" }}</h3>
              <p v-if="ctx?.describeState">{{ stateLine }}</p>
              <p v-else>контекст страницы</p>
            </div>
          </div>
          <button class="aibp-x" type="button" @click="closePanel" aria-label="Закрыть">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </header>

        <!-- Empty state — quick actions -->
        <section v-if="!chat.messages.value.length" class="aibp-actions">
          <h4>Быстрые действия</h4>
          <button
            class="aibp-action aibp-action-primary"
            type="button"
            :disabled="chat.isStreaming.value || !ctx"
            @click="runSummary"
          >
            <span class="aibp-action-icon">⚡</span>
            <span>Сводка страницы</span>
          </button>
          <button
            v-for="(qa, idx) in ctx?.quickActions || []"
            :key="qa.label + idx"
            class="aibp-action"
            type="button"
            :disabled="chat.isStreaming.value"
            @click="run(qa.prompt)"
          >
            <span v-if="qa.icon" class="aibp-action-icon">{{ qa.icon }}</span>
            <span v-else class="aibp-action-icon">▶</span>
            <span>{{ qa.label }}</span>
          </button>
          <p v-if="!ctx" class="aibp-no-ctx">
            На этой странице нет AI-контекста. Открой полный чат для свободных запросов.
          </p>
        </section>

        <!-- Stream output -->
        <section v-else class="aibp-msgs" ref="msgsBoxRef">
          <AiMessage
            v-for="(m, i) in chat.messages.value"
            :key="i"
            :role="m.role"
            :content="m.content"
            :pending="m.pending ?? false"
            :error="m.error ?? false"
            :tool-calls="m.toolCalls"
          />
          <!-- Error banner (separately из message tag because content может быть пуст) -->
          <div v-if="chat.error.value" class="aibp-err" role="alert">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>{{ chat.error.value }}</span>
          </div>
        </section>

        <footer class="aibp-foot">
          <AiInput
            :disabled="chat.isStreaming.value"
            placeholder="Свой вопрос про эту страницу…"
            @submit="run($event)"
          />
          <div class="aibp-foot-row">
            <button
              v-if="chat.isStreaming.value"
              class="aibp-stop"
              type="button"
              @click="chat.abort"
            >
              ■ Остановить
            </button>
            <button
              v-if="chat.messages.value.length > 0 && !chat.isStreaming.value"
              class="aibp-restart"
              type="button"
              @click="chat.reset"
            >
              ↺ Новый запрос
            </button>
            <RouterLink to="/ai-chat" class="aibp-full" @click="closePanel">
              → Полный чат
            </RouterLink>
          </div>
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from "vue";
import { useRoute } from "vue-router";
import EptLogo from "@/components/EptLogo.vue";
import AiMessage from "@/components/Ai/AiMessage.vue";
import AiInput from "@/components/Ai/AiInput.vue";
import { useAiChat } from "@/composables/useAiChat";
import { getCurrentPageContext, buildSummaryPrompt } from "@/composables/useAiPageContext";

const route = useRoute();
const ctx = getCurrentPageContext();
const chat = useAiChat();
const panelOpen = ref(false);
const msgsBoxRef = ref<HTMLElement | null>(null);

const HIDDEN_ROUTES = new Set(["/login", "/forgot-password", "/ai-chat", "/twa"]);
const showFab = computed(() => {
  const p = route.path || "";
  if (HIDDEN_ROUTES.has(p)) return false;
  if (p.startsWith("/twa/")) return false;
  return true;
});

const stateLine = computed(() => {
  try { return ctx.value?.describeState?.() || ""; } catch { return ""; }
});

function togglePanel() {
  panelOpen.value = !panelOpen.value;
}

function closePanel() {
  panelOpen.value = false;
}

async function runSummary() {
  if (!ctx.value) return;
  const prompt = buildSummaryPrompt(ctx.value);
  await run(prompt);
}

async function run(prompt: string) {
  if (chat.isStreaming.value || !prompt.trim()) return;
  await chat.send(prompt);
  scrollBottom();
}

function scrollBottom() {
  nextTick(() => {
    if (msgsBoxRef.value) msgsBoxRef.value.scrollTop = msgsBoxRef.value.scrollHeight;
  });
}

watch(() => chat.messages.value.length, scrollBottom);
watch(
  () => chat.messages.value[chat.messages.value.length - 1]?.content,
  scrollBottom,
);

// Reset conversation when navigating between pages (новая страница = новый контекст)
watch(() => route.path, () => {
  if (chat.messages.value.length > 0) chat.reset();
  closePanel();
});
</script>

<style scoped>
/* ─── FAB (right edge, vertically centered — паттерн Intercom/Drift,
       никогда не конфликтует со ScrollToTopButton bottom-right) ─── */
.ai-bubble-fab {
  position: fixed;
  right: 18px;
  top: 50%;
  /* base translate centers vertically; hover/active modify via composition */
  transform: translateY(-50%);
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 0;
  cursor: pointer;
  background: linear-gradient(135deg, var(--uza-purple, #7F77DD) 0%, var(--uza-purple-2, #534AB7) 100%);
  color: #fff;
  display: grid;
  place-items: center;
  box-shadow:
    0 10px 30px rgba(127, 119, 221, 0.42),
    0 4px 10px rgba(15, 23, 60, 0.18);
  z-index: 950;
  transition: transform 0.22s cubic-bezier(0.34, 1.2, 0.64, 1), box-shadow 0.2s, right 0.18s;
  animation: aiBubbleBreathe 4s ease-in-out infinite;
}
.ai-bubble-fab:hover {
  transform: translate(-3px, -50%) scale(1.06);
  box-shadow:
    0 14px 36px rgba(127, 119, 221, 0.55),
    0 6px 14px rgba(15, 23, 60, 0.22);
}
.ai-bubble-fab:active { transform: translateY(-50%) scale(0.94); }
.ai-bubble-fab.is-active {
  background: linear-gradient(135deg, var(--uza-purple-2, #534AB7) 0%, var(--uza-purple-3, #3F3796) 100%);
  transform: translateY(-50%) scale(0.92);
}
.ai-bubble-fab.is-thinking { animation: aiBubbleBreatheFast 1.6s ease-in-out infinite; }
@keyframes aiBubbleBreathe {
  0%, 100% { box-shadow: 0 10px 30px rgba(127, 119, 221, 0.42), 0 4px 10px rgba(15, 23, 60, 0.18); }
  50%      { box-shadow: 0 14px 40px rgba(127, 119, 221, 0.62), 0 6px 14px rgba(15, 23, 60, 0.22); }
}
@keyframes aiBubbleBreatheFast {
  0%, 100% { box-shadow: 0 10px 30px rgba(127, 119, 221, 0.55), 0 0 0 0 rgba(127, 119, 221, 0.6); }
  50%      { box-shadow: 0 14px 40px rgba(127, 119, 221, 0.75), 0 0 0 14px rgba(127, 119, 221, 0); }
}
.ai-bubble-fab-text {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #fff;
  line-height: 1;
  user-select: none;
}
.ai-bubble-fab-pulse {
  position: absolute;
  inset: -6px;
  border-radius: 50%;
  border: 2px solid rgba(127, 119, 221, 0.55);
  animation: aiFabPulse 1.6s ease-out infinite;
  pointer-events: none;
}
@keyframes aiFabPulse {
  0%   { transform: scale(0.85); opacity: 1; }
  100% { transform: scale(1.4);  opacity: 0; }
}

/* FAB enter/leave — preserve vertical-center transform */
.ai-bubble-fab-enter-active, .ai-bubble-fab-leave-active {
  transition: transform .35s cubic-bezier(0.34, 1.2, 0.64, 1), opacity .25s;
}
.ai-bubble-fab-enter-from, .ai-bubble-fab-leave-to {
  transform: translateY(-50%) scale(0);
  opacity: 0;
}

/* ─── Backdrop + panel ─── */
.ai-bubble-back {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, 0.35);
  -webkit-backdrop-filter: blur(6px);
          backdrop-filter: blur(6px);
  z-index: 998;
}
.ai-bubble-back-enter-active, .ai-bubble-back-leave-active {
  transition: opacity .22s;
}
.ai-bubble-back-enter-from, .ai-bubble-back-leave-to { opacity: 0; }

.ai-bubble-panel {
  position: fixed;
  top: 14px;
  right: 14px;
  bottom: 14px;
  width: min(420px, calc(100vw - 28px));
  background: rgba(255, 255, 255, 0.92);
  -webkit-backdrop-filter: blur(18px);
          backdrop-filter: blur(18px);
  border: 1px solid rgba(127, 119, 221, 0.18);
  border-radius: 16px;
  box-shadow:
    0 24px 64px rgba(15, 23, 60, 0.20),
    0 8px 24px rgba(15, 23, 60, 0.10);
  z-index: 999;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.ai-bubble-panel-enter-active, .ai-bubble-panel-leave-active {
  transition: transform .4s cubic-bezier(0.34, 1.2, 0.64, 1), opacity .25s;
}
.ai-bubble-panel-enter-from, .ai-bubble-panel-leave-to {
  transform: translateX(16px) scale(0.98); opacity: 0;
}

/* Header */
.aibp-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid rgba(127, 119, 221, 0.12);
}
.aibp-head-l { display: flex; align-items: center; gap: 10px; min-width: 0; }
.aibp-icon {
  width: 36px; height: 36px;
  border-radius: 10px;
  display: grid; place-items: center;
  background: linear-gradient(135deg, var(--uza-purple, #7F77DD) 0%, var(--uza-purple-2, #534AB7) 100%);
  color: #fff;
  flex-shrink: 0;
}
.aibp-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--uza-navy, #1E2A4A);
}
.aibp-head p {
  margin: 2px 0 0;
  font-size: 11px;
  color: rgba(30, 42, 74, 0.55);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.aibp-x {
  border: 0; background: transparent; cursor: pointer;
  color: rgba(30, 42, 74, 0.6);
  width: 28px; height: 28px; border-radius: 8px;
  display: grid; place-items: center;
  transition: all 0.15s;
  flex-shrink: 0;
}
.aibp-x:hover { background: rgba(127, 119, 221, 0.08); color: var(--uza-purple, #7F77DD); }

/* Empty state — actions */
.aibp-actions { padding: 16px 18px; }
.aibp-actions h4 {
  margin: 0 0 10px;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(30, 42, 74, 0.5);
}
.aibp-action {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 12px;
  margin-bottom: 6px;
  border: 1px solid rgba(127, 119, 221, 0.20);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.7);
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy, #1E2A4A);
  cursor: pointer;
  text-align: left;
  transition: all .15s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.aibp-action:hover:not(:disabled) {
  background: #fff;
  border-color: var(--uza-purple, #7F77DD);
  transform: translateX(2px);
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.12);
}
.aibp-action:disabled { opacity: .5; cursor: not-allowed; }
.aibp-action-icon { font-size: 14px; flex-shrink: 0; opacity: .7; }
.aibp-action-primary,
.aibp-action-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #7F77DD 0%, #534AB7 100%);
  color: #fff;
  border-color: transparent;
}
.aibp-action-primary { box-shadow: 0 4px 12px rgba(127, 119, 221, 0.32); }
.aibp-action-primary:hover:not(:disabled) { box-shadow: 0 6px 18px rgba(127, 119, 221, 0.45); }
.aibp-action-primary .aibp-action-icon,
.aibp-action-primary span { color: #fff; opacity: 1; }
.aibp-no-ctx {
  margin: 14px 4px 0;
  font-size: 11px;
  color: rgba(30, 42, 74, 0.5);
  line-height: 1.5;
}

/* Messages */
.aibp-msgs {
  flex: 1;
  overflow-y: auto;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Pack 7.9f hotfix: force AiMessage user-bubble visibility in teleported panel.
   CSS-переменные --uza-purple не всегда доходят через Teleport+Transition
   scope chain — переопределяем явными hex чтобы белый текст
   user-сообщения не сливался с белым фоном панели. */
.aibp-msgs :deep(.ai-msg-bubble-user) {
  background: linear-gradient(135deg, #7F77DD 0%, #534AB7 100%) !important;
  color: #fff !important;
  border: 1px solid rgba(127, 119, 221, 0.4);
}
.aibp-msgs :deep(.ai-msg-bubble-user *) { color: #fff !important; }
.aibp-msgs :deep(.ai-msg-bubble-ai) {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(127, 119, 221, 0.15);
  color: #1E2A4A;
}

/* Error banner */
.aibp-err {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(254, 242, 242, 0.95);
  border: 1px solid rgba(252, 165, 165, 0.65);
  color: #991B1B;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-line;
}
.aibp-err svg { flex-shrink: 0; margin-top: 2px; }

/* Footer */
.aibp-foot {
  padding: 12px 18px 16px;
  border-top: 1px solid rgba(127, 119, 221, 0.12);
  background: rgba(255, 255, 255, 0.7);
}
.aibp-foot-row {
  display: flex; align-items: center; gap: 8px;
  margin-top: 8px;
  font-size: 11px;
}
.aibp-stop, .aibp-restart {
  border: 1px solid rgba(127, 119, 221, 0.25);
  background: rgba(255, 255, 255, 0.85);
  color: var(--uza-purple, #7F77DD);
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all .12s;
}
.aibp-stop:hover, .aibp-restart:hover {
  background: rgba(127, 119, 221, 0.08);
  border-color: var(--uza-purple, #7F77DD);
}
.aibp-full {
  margin-left: auto;
  font-size: 11px;
  font-weight: 500;
  color: var(--uza-purple, #7F77DD);
  text-decoration: none;
  letter-spacing: -0.005em;
  transition: opacity .15s;
}
.aibp-full:hover { opacity: .7; }

@media (max-width: 640px) {
  .ai-bubble-fab { right: 12px; width: 46px; height: 46px; }
  .ai-bubble-panel { top: 8px; right: 8px; bottom: 8px; left: 8px; width: auto; }
}
</style>
