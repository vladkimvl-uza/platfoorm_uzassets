<template>
  <div class="ai-page" :class="{ 'ai-page-sb-hidden': sidebarHidden }">
    <!-- Aurora ambient background -->
    <div class="ai-aurora-bg" aria-hidden="true"></div>

    <!-- Sidebar -->
    <AiSidebar
      v-if="!sidebarHidden"
      :items="conversations"
      :active-id="chat.conversationId.value"
      :loading="convLoading"
      @new-chat="newChat"
      @select="selectConversation"
      @delete="onDeleteConv"
      @renamed="onRenamed"
      @open-settings="settingsOpen = true"
    />

    <!-- Main chat -->
    <section class="ai-main">
      <header class="ai-page-head">
        <div class="ai-page-title">
          <div class="ai-page-icon ai-page-icon-logo" :class="{ 'is-active': chat.isStreaming.value }">
            <EptLogo :size="32" />
          </div>
          <div>
            <h1>ИИ-ассистент</h1>
            <p v-if="health">
              <span v-if="!aiActive" class="ai-page-warn">
                <span class="ai-page-status-dot off"></span>
                выключен владельцем
              </span>
              <span v-else-if="health.enabled && !chat.isStreaming.value">
                <span class="ai-page-status-dot"></span>
                онлайн
              </span>
              <span v-else-if="health.enabled && chat.isStreaming.value" class="ai-page-thinking">
                <span class="ai-typing-dots">
                  <span class="ai-typing-dot"></span>
                  <span class="ai-typing-dot"></span>
                  <span class="ai-typing-dot"></span>
                </span>
                <span class="ai-thinking-text">думаю…</span>
              </span>
              <span v-else class="ai-page-warn">
                AI недоступен
              </span>
            </p>
          </div>
        </div>

        <div class="ai-page-actions">
          <button
            class="ai-page-btn ai-page-btn-icon"
            type="button"
            @click="toggleSidebar"
            :title="sidebarHidden ? 'Показать историю чатов' : 'Скрыть историю чатов'"
            :aria-label="sidebarHidden ? 'Показать историю чатов' : 'Скрыть историю чатов'"
          >
            <svg v-if="sidebarHidden" width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
            <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="9" y1="3" x2="9" y2="21"/>
              <line x1="13" y1="9" x2="17" y2="9"/>
              <line x1="13" y1="13" x2="17" y2="13"/>
              <line x1="13" y1="17" x2="17" y2="17"/>
            </svg>
          </button>
          <button
            class="ai-page-btn"
            type="button"
            :disabled="chat.isStreaming.value"
            @click="settingsOpen = true"
            title="Настройки"
            aria-label="Настройки"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.01a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.01a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>

          <button
            class="ai-page-btn ai-page-btn-prim"
            type="button"
            :disabled="chat.isStreaming.value"
            @click="newChat"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 12a9 9 0 1 0 9-9 9.74 9.74 0 0 0-7 3l-2 2"/>
              <path d="M3 4v5h5"/>
            </svg>
            Новый разговор
          </button>
        </div>
      </header>

      <main class="ai-page-body" ref="bodyRef">
        <div v-if="!chat.messages.value.length" class="ai-page-empty">
          <div class="ai-page-empty-card">
            <div class="ai-page-empty-icon ai-page-empty-icon-logo">
              <EptLogo :size="88" />
            </div>
            <h2>Чем могу помочь?</h2>
            <p>
              Аналитика портфеля — компании, финансы, рейтинги, задачи, ESG, корп. управление.
              Все ответы строятся на данных вашей платформы.
            </p>
            <!-- Quick-prompt buttons hidden per user request 2026-05-23.
                 Чтобы вернуть — снять `v-if="false"`. -->
            <div v-if="false" class="ai-page-suggestions">
              <button
                v-for="(s, idx) in suggestions"
                :key="s"
                class="ai-page-sug"
                :style="{ animationDelay: `${idx * 50}ms` }"
                type="button"
                :disabled="!health?.enabled"
                @click="onSuggest(s)"
              >
                <span>{{ s }}</span>
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none"
                     stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round">
                  <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <div v-else class="ai-page-msgs">
          <AiMessage
            v-for="(m, i) in chat.messages.value"
            :key="i"
            :role="m.role"
            :content="m.content"
            :pending="m.pending ?? false"
            :error="m.error ?? false"
            :tool-calls="m.toolCalls"
          />
          <div
            v-if="chat.canContinue.value"
            class="ai-page-continue"
          >
            <span class="ai-page-continue-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2"
                   stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
            </span>
            <span>Ответ обрезан по лимиту токенов</span>
            <button
              type="button"
              class="ai-page-btn ai-page-btn-prim"
              @click="onContinue"
            >
              Продолжить
            </button>
          </div>
        </div>
      </main>

      <footer class="ai-page-foot">
        <AiInput
          :disabled="!health?.enabled || !aiActive || chat.isStreaming.value"
          :placeholder="health?.enabled
            ? (chat.isStreaming.value ? 'Подождите ответа…' : 'Спросите о портфеле, проектах, рейтингах…')
            : 'AI недоступен — обратитесь к администратору'"
          @submit="onSubmit"
        />
        <div v-if="chat.isStreaming.value" class="ai-page-controls">
          <button class="ai-page-stop" type="button" @click="onStop" title="Остановить генерацию">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="1.5"/>
            </svg>
            Остановить
          </button>
        </div>
        <div v-if="chat.error.value" class="ai-page-err">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{{ chat.error.value }}</span>
        </div>
        <div v-if="chat.error.value && lastUserMsg" class="ai-page-controls">
          <button class="ai-page-retry" type="button" @click="onRetry" title="Повторить запрос">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M3 12a9 9 0 1 0 9-9 9.74 9.74 0 0 0-7 3l-2 2"/>
              <path d="M3 4v5h5"/>
            </svg>
            Повторить
          </button>
        </div>
        <p class="ai-page-disclaimer">
          ответы строятся на актуальном снимке БД портфеля
        </p>
      </footer>
    </section>

    <!-- Settings drawer -->
    <AiSettings
      v-model="settingsOpen"
      @saved="onSettingsSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch, computed } from "vue";
import {
  getHealth,
  listConversations,
  deleteConversation,
  type AiHealth,
  type ConversationListItem,
} from "@/api/aiClient";
import { useAiChat } from "@/composables/useAiChat";
import { useAiConfig } from "@/composables/useAiConfig";
import { useAiActivation } from "@/composables/useAiActivation";
import AiMessage from "@/components/Ai/AiMessage.vue";
import AiInput from "@/components/Ai/AiInput.vue";
import AiSidebar from "@/components/Ai/AiSidebar.vue";
import AiSettings from "@/components/Ai/AiSettings.vue";
import EptLogo from "@/components/EptLogo.vue";
import "@/styles/ai-aurora.css";

const chat = useAiChat();
const cfg = useAiConfig();

const health = ref<AiHealth | null>(null);
const aiAct = useAiActivation();
const aiActive = computed(() => aiAct.state.active);
const conversations = ref<ConversationListItem[]>([]);

// Pack 7.44 — Sidebar visibility toggle (persisted)
const SB_HIDDEN_KEY = "ai-chat-sidebar-hidden";
const sidebarHidden = ref<boolean>(
  typeof localStorage !== "undefined" && localStorage.getItem(SB_HIDDEN_KEY) === "1"
);
function toggleSidebar() {
  sidebarHidden.value = !sidebarHidden.value;
  try { localStorage.setItem(SB_HIDDEN_KEY, sidebarHidden.value ? "1" : "0"); } catch {}
}
const convLoading = ref(false);
const settingsOpen = ref(false);
const bodyRef = ref<HTMLElement | null>(null);

const suggestions = [
  "Сводка по портфелю за 2026",
  "Просроченные задачи на сегодня",
  "Сравни 2025 vs 2026 по выполнению задач",
  "Топ-5 отстающих компаний",
  "Кредитный портфель — крупнейшие займы в USD",
  "Какие Big4 работают по нашим проектам?",
];

async function loadHealth() {
  try { health.value = await getHealth(); } catch { health.value = null; }
}

async function loadConversations() {
  convLoading.value = true;
  try { conversations.value = await listConversations(); }
  catch { conversations.value = []; }
  finally { convLoading.value = false; }
}

function newChat() { chat.reset(); }

async function selectConversation(id: string) {
  await chat.loadConversation(id);
  scrollBottom();
}

async function onDeleteConv(id: string) {
  if (!confirm("Удалить разговор? Это действие необратимо.")) return;
  try {
    await deleteConversation(id);
    conversations.value = conversations.value.filter((c) => c.id !== id);
    if (chat.conversationId.value === id) chat.reset();
  } catch (e: unknown) {
    alert(e instanceof Error ? e.message : "Не удалось удалить");
  }
}

function onRenamed(id: string, title: string) {
  const c = conversations.value.find((x) => x.id === id);
  if (c) c.title = title;
}

const lastUserMsg = computed(() => {
  const msgs = chat.messages.value;
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "user") return msgs[i].content;
  }
  return "";
});

async function onSubmit(text: string) {
  await cfg.load();
  await chat.send(text);
  scrollBottom();
  loadConversations();
}

async function onSuggest(text: string) { await onSubmit(text); }

async function onContinue() {
  await chat.continueResponse();
  scrollBottom();
}

function onStop() {
  chat.abort();
}

async function onRetry() {
  const text = chat.popLastTurn();
  if (!text) return;
  await onSubmit(text);
}

function onSettingsSaved() { /* picked up on next message */ }

function scrollBottom() {
  nextTick(() => {
    if (bodyRef.value) bodyRef.value.scrollTop = bodyRef.value.scrollHeight;
  });
}

watch(() => chat.messages.value.length, scrollBottom);
watch(
  () => chat.messages.value[chat.messages.value.length - 1]?.content,
  scrollBottom,
);

onMounted(() => { loadHealth(); loadConversations(); aiAct.load(true); });
</script>

<style scoped>
.ai-page {
  position: relative;
  display: flex;
  height: 100vh;
  height: 100dvh;
  background:
    linear-gradient(180deg, #fafbff 0%, #f5f6fb 100%);
  overflow: hidden;
}

.ai-main {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* Header */
.ai-page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 24px;
  background: var(--ai-glass-bg-strong);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border-bottom: 1px solid var(--ai-glass-border);
  position: relative;
  z-index: 2;
}

.ai-page-title { display: flex; align-items: center; gap: 12px; }
.ai-page-icon {
  width: 38px; height: 38px;
  display: grid; place-items: center;
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: white;
  border-radius: var(--ai-radius-md);
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.32);
}
.ai-page-title h1 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
}
.ai-page-title p {
  margin: 3px 0 0;
  font-size: 11px;
  color: rgba(30, 42, 74, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ai-page-status-dot {
  display: inline-block;
  width: 6px; height: 6px;
  background: var(--uza-teal);
  border-radius: 50%;
  box-shadow: 0 0 0 2px rgba(29, 158, 117, 0.18);
  animation: ai-status-pulse 2.4s ease-in-out infinite;
}
.ai-page-status-dot.off {
  background: #C7C9D1;
  box-shadow: none;
  animation: none;
}
@keyframes ai-status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
.ai-page-warn { color: var(--uza-red); }

.ai-page-actions { display: flex; gap: 8px; }
.ai-page-btn {
  padding: 8px 14px;
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  background: var(--ai-glass-bg-strong);
  color: rgba(30, 42, 74, 0.7);
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.15s var(--ai-easing-soft);
}
.ai-page-btn:hover:not(:disabled) {
  background: white;
  color: var(--uza-navy);
  border-color: rgba(127, 119, 221, 0.3);
}
.ai-page-btn-prim {
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: white;
  border-color: transparent;
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.28);
}
.ai-page-btn-prim:hover:not(:disabled) {
  background: linear-gradient(135deg, var(--uza-purple-2) 0%, var(--uza-purple-3) 100%);
  color: white;
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(127, 119, 221, 0.38);
}
.ai-page-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Body */
.ai-page-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
}

/* Empty state */
.ai-page-empty {
  flex: 1;
  display: grid;
  place-items: center;
}
.ai-page-empty-card {
  max-width: 580px;
  text-align: center;
  padding: 24px;
}
.ai-page-empty-icon {
  display: inline-grid;
  place-items: center;
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: white;
  border-radius: 16px;
  margin-bottom: 18px;
  box-shadow: 0 8px 28px rgba(127, 119, 221, 0.35);
}
.ai-page-empty-card h2 {
  font-size: 24px;
  font-weight: 400;
  color: var(--uza-navy);
  letter-spacing: -0.025em;
  margin: 0 0 8px;
}
.ai-page-empty-card p {
  color: rgba(30, 42, 74, 0.6);
  font-size: 13.5px;
  line-height: 1.6;
  margin: 0;
}
.ai-page-suggestions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: 24px;
}
@media (max-width: 600px) { .ai-page-suggestions { grid-template-columns: 1fr; } }

.ai-page-sug {
  padding: 12px 14px;
  background: var(--ai-glass-bg-strong);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  font-size: 12.5px;
  color: var(--uza-navy);
  cursor: pointer;
  text-align: left;
  transition: all 0.18s var(--ai-easing-soft);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  opacity: 0;
  animation: ai-sug-in 0.5s var(--ai-easing) both;
}
@keyframes ai-sug-in {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
.ai-page-sug svg { color: rgba(30, 42, 74, 0.4); transition: all 0.15s; flex-shrink: 0; }
.ai-page-sug:hover:not(:disabled) {
  background: white;
  border-color: rgba(127, 119, 221, 0.32);
  color: var(--uza-purple);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(127, 119, 221, 0.12);
}
.ai-page-sug:hover:not(:disabled) svg {
  color: var(--uza-purple);
  transform: translateX(2px);
}
.ai-page-sug:disabled { opacity: 0.5; cursor: not-allowed; }

/* Messages container */
.ai-page-msgs {
  display: flex;
  flex-direction: column;
  max-width: 920px;
  width: 100%;
  margin: 0 auto;
}

/* Continue banner */
.ai-page-continue {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin: 8px 0 12px;
  background: rgba(254, 251, 235, 0.85);
  -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
  border: 1px solid rgba(253, 230, 138, 0.7);
  border-radius: var(--ai-radius-md);
  font-size: 12px;
  color: #92400E;
}
.ai-page-continue-icon {
  display: grid; place-items: center;
  color: var(--uza-amber);
}
.ai-page-continue span:nth-child(2) { flex: 1; }

/* Footer */
.ai-page-foot {
  padding: 14px 24px 18px;
  background: var(--ai-glass-bg);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border-top: 1px solid var(--ai-glass-border);
  position: relative;
  z-index: 2;
}

.ai-page-err {
  margin: 8px 0 0;
  padding: 9px 12px;
  background: rgba(254, 242, 242, 0.95);
  border: 1px solid rgba(252, 165, 165, 0.6);
  color: #991B1B;
  border-radius: var(--ai-radius-md);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: pre-line;
}
.ai-page-err svg { flex-shrink: 0; }

.ai-page-disclaimer {
  margin: 8px 0 0;
  font-size: 10px;
  color: rgba(30, 42, 74, 0.4);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  text-align: center;
}

/* ─────── Pack 7.44 — AI logo styling (variant 1: breathing + typing) ─────── */
.ai-page-icon-logo {
  background: transparent !important;
  box-shadow: none !important;
  width: 42px !important;
  height: 42px !important;
  padding: 0;
  display: flex; align-items: center; justify-content: center;
  border-radius: 10px;
  animation: ai-logo-breathe 3.2s ease-in-out infinite;
}
@keyframes ai-logo-breathe {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 2px 8px rgba(127, 119, 221, 0.20)); }
  50%      { transform: scale(1.06); filter: drop-shadow(0 4px 14px rgba(127, 119, 221, 0.40)); }
}
.ai-page-icon-logo.is-active {
  animation: ai-logo-breathe-fast 1.8s ease-in-out infinite;
}
@keyframes ai-logo-breathe-fast {
  0%, 100% { transform: scale(1); filter: drop-shadow(0 2px 10px rgba(127, 119, 221, 0.35)); }
  50%      { transform: scale(1.08); filter: drop-shadow(0 6px 18px rgba(127, 119, 221, 0.60)); }
}

.ai-page-empty-icon-logo {
  background: transparent !important;
  box-shadow: none !important;
  width: 110px !important;
  height: 110px !important;
  padding: 0;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto;
  animation: ai-logo-breathe 4s ease-in-out infinite;
}

/* Typing indicator — 3 пульсирующих точки + текст "думаю..." */
.ai-page-thinking {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-transform: none;
  letter-spacing: 0;
}
.ai-typing-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.ai-typing-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--uza-purple, #7F77DD);
  animation: ai-typing-pulse 1.4s ease-in-out infinite;
}
.ai-typing-dot:nth-child(2) { animation-delay: 0.18s; }
.ai-typing-dot:nth-child(3) { animation-delay: 0.36s; }
@keyframes ai-typing-pulse {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
  30%           { opacity: 1;   transform: scale(1.1); }
}
.ai-thinking-text {
  font-size: 11px;
  color: var(--uza-purple, #7F77DD);
  font-weight: 500;
  letter-spacing: 0;
  text-transform: none;
}

/* ─────────── Pack 7.44 — Sidebar toggle ─────────── */
.ai-page-btn-icon {
  padding: 8px 9px;
  display: flex; align-items: center; justify-content: center;
}
.ai-page-btn-icon svg {
  transition: transform .25s var(--ease-standard);
}
.ai-page-btn-icon:hover:not(:disabled) svg {
  transform: scale(1.15);
  color: var(--uza-purple, #7F77DD);
}
.ai-page.ai-page-sb-hidden .ai-main {
  /* main takes full width when sidebar hidden */
  width: 100%;
}

/* ─────────── Stop / Retry / error controls ─────────── */
.ai-page-controls {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin: 8px 0 0;
}
.ai-page-stop, .ai-page-retry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all .15s var(--ai-easing-soft);
  border: 1px solid;
}
.ai-page-stop {
  background: rgba(255, 255, 255, .95);
  color: var(--uza-red, var(--sev-high));
  border-color: rgba(226, 75, 74, .35);
}
.ai-page-stop:hover {
  background: rgba(254, 242, 242, 1);
  border-color: var(--uza-red, var(--sev-high));
  transform: translateY(-1px);
}
.ai-page-retry {
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 3px 12px rgba(127, 119, 221, .25);
}
.ai-page-retry:hover {
  transform: translateY(-1px);
  box-shadow: 0 5px 16px rgba(127, 119, 221, .38);
}
</style>
