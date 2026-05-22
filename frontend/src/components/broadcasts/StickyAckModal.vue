<script setup lang="ts">
/**
 * StickyAckModal — глобальная модалка для sticky уведомлений.
 *
 * Mount once in AppShell. Polls GET /broadcasts/sticky every 30s.
 * If any item exists with acknowledged_at=null and is_sticky=true, blocks
 * UI until user submits ack (text/select/yesno/click/file) or postpones 1h.
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { broadcastsApi, PRIORITY_PILL, type StickyNotification, type AckPayload } from "@/api/admin_broadcasts";

const queue = ref<StickyNotification[]>([]);
const submitting = ref(false);
const error = ref<string | null>(null);
const postponedIds = ref<Set<string>>(new Set());

// Per-current-item form state
const textResponse = ref("");
const selectResponse = ref<string | null>(null);
const yesnoResponse = ref<"yes" | "no" | null>(null);

const current = computed<StickyNotification | null>(() => {
  for (const n of queue.value) {
    if (!postponedIds.value.has(n.id)) return n;
  }
  return null;
});

let pollTimer: number | null = null;
let countdownTimer: number | null = null;
const countdownText = ref<string>("");

function tickCountdown() {
  if (!current.value?.ack_deadline) {
    countdownText.value = "";
    return;
  }
  const ms = new Date(current.value.ack_deadline).getTime() - Date.now();
  if (ms <= 0) {
    countdownText.value = "ДЕДЛАЙН ПРОПУЩЕН";
    return;
  }
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 24) countdownText.value = `${Math.floor(h / 24)} д ${h % 24} ч`;
  else if (h > 0) countdownText.value = `${h} ч ${String(m).padStart(2, "0")} мин`;
  else countdownText.value = `${m} мин ${String(s).padStart(2, "0")} с`;
}

async function fetchSticky() {
  try {
    const items = await broadcastsApi.mySticky();
    queue.value = items;
  } catch (e: any) {
    // 401/403 — user logged out, suppress
    if (e?.response?.status === 401 || e?.response?.status === 403) return;
  }
}

function resetForm() {
  textResponse.value = "";
  selectResponse.value = null;
  yesnoResponse.value = null;
  error.value = null;
}

async function submitAck(value?: "yes" | "no") {
  if (!current.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const payload: AckPayload = {};
    const mode = current.value.ack_mode;
    if (mode === "text") {
      if (!textResponse.value.trim()) {
        error.value = "Введите текстовый ответ";
        submitting.value = false;
        return;
      }
      payload.response_text = textResponse.value.trim();
    } else if (mode === "select") {
      if (!selectResponse.value) {
        error.value = "Выберите вариант";
        submitting.value = false;
        return;
      }
      payload.response_value = selectResponse.value;
    } else if (mode === "yesno") {
      const v = value ?? yesnoResponse.value;
      if (!v) {
        error.value = "Выберите Да или Нет";
        submitting.value = false;
        return;
      }
      payload.response_value = v;
    } else if (mode === "file") {
      error.value = "Загрузка файлов ещё не подключена";
      submitting.value = false;
      return;
    }
    // mode === "click" or "none" → empty payload

    await broadcastsApi.ack(current.value.id, payload);
    // Remove from queue
    queue.value = queue.value.filter((n) => n.id !== current.value!.id);
    resetForm();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось подтвердить";
  } finally {
    submitting.value = false;
  }
}

function postpone1h() {
  if (!current.value) return;
  postponedIds.value.add(current.value.id);
  resetForm();
  // Re-show after 1 hour
  setTimeout(() => {
    if (current.value) postponedIds.value.delete(current.value.id);
  }, 60 * 60 * 1000);
}

onMounted(() => {
  fetchSticky();
  pollTimer = window.setInterval(fetchSticky, 30000);
  countdownTimer = window.setInterval(tickCountdown, 1000);
});
onUnmounted(() => {
  if (pollTimer) window.clearInterval(pollTimer);
  if (countdownTimer) window.clearInterval(countdownTimer);
});

const remaining = computed(() => queue.value.filter((n) => !postponedIds.value.has(n.id)).length);
</script>

<template>
  <Transition name="uza-fade">
    <div v-if="current" class="sam-backdrop">
      <div class="sam-card">

        <div class="sam-card-head">
          <div class="sam-pills">
            <span class="sam-pri-pill"
                  :style="{ color: PRIORITY_PILL[current.priority].color, background: PRIORITY_PILL[current.priority].bg }">
              {{ current.priority }}
            </span>
            <span class="sam-sticky-pill">
              <i class="ti ti-pin" aria-hidden="true"></i> sticky
            </span>
            <span v-if="remaining > 1" class="sam-queue-pill">
              + ещё {{ remaining - 1 }} в очереди
            </span>
          </div>
          <div class="sam-lock-lbl">
            <i class="ti ti-lock" aria-hidden="true"></i> Окно нельзя закрыть до ответа
          </div>
        </div>

        <div class="sam-body">
          <div class="sam-title">{{ current.title }}</div>
          <div v-if="current.body" class="sam-text">{{ current.body }}</div>

          <a v-if="current.link_url" :href="current.link_url" target="_blank" rel="noopener noreferrer" class="sam-link">
            <i class="ti ti-external-link" aria-hidden="true"></i> Открыть ссылку
          </a>

          <div v-if="countdownText" class="sam-deadline">
            <i class="ti ti-alarm" aria-hidden="true"></i>
            Ответ ожидается через: <b>{{ countdownText }}</b>
          </div>

          <!-- Ack form per mode -->
          <div v-if="current.requires_ack" class="sam-form">
            <div v-if="current.ack_question" class="sam-question">{{ current.ack_question }}</div>

            <div v-if="current.ack_mode === 'text'">
              <textarea v-model="textResponse"
                        rows="3"
                        placeholder="Ваш ответ..."
                        class="sam-textarea"></textarea>
            </div>

            <div v-else-if="current.ack_mode === 'select'" class="sam-options">
              <label v-for="opt in (current.ack_options || [])" :key="opt"
                     class="sam-option"
                     :class="{ selected: selectResponse === opt }">
                <input type="radio" :value="opt" v-model="selectResponse"/>
                <span>{{ opt }}</span>
              </label>
            </div>

            <div v-else-if="current.ack_mode === 'yesno'" class="sam-yesno">
              <button class="sam-yn-btn sam-yn-yes" :class="{ selected: yesnoResponse === 'yes' }"
                      @click="yesnoResponse = 'yes'">
                <i class="ti ti-check" aria-hidden="true"></i> Да
              </button>
              <button class="sam-yn-btn sam-yn-no" :class="{ selected: yesnoResponse === 'no' }"
                      @click="yesnoResponse = 'no'">
                <i class="ti ti-x" aria-hidden="true"></i> Нет
              </button>
            </div>

            <div v-else-if="current.ack_mode === 'file'" class="sam-hint">
              Загрузка файлов ещё не подключена.
            </div>
          </div>
        </div>

        <div v-if="error" class="sam-err">{{ error }}</div>

        <div class="sam-footer">
          <button class="sam-btn sam-btn-ghost"
                  @click="postpone1h"
                  :disabled="submitting">
            <i class="ti ti-clock" aria-hidden="true"></i> Отложить на 1 ч
          </button>
          <div style="flex: 1"></div>
          <button class="sam-btn sam-btn-primary"
                  @click="submitAck()"
                  :disabled="submitting">
            <i class="ti ti-check" aria-hidden="true"></i>
            {{ submitting ? "Отправка..." : "Подтвердить" }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.sam-backdrop {
  position: fixed; inset: 0;
  z-index: 9999;
  background: rgba(15,18,40,.45);
  backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}

.sam-card {
  background: var(--color-background-primary, #fff);
  width: 100%;
  max-width: 520px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: samIn .45s cubic-bezier(0.34, 1.2, 0.64, 1);
}
@keyframes samIn {
  from { transform: scale(.94) translateY(20px); opacity: 0; }
  to   { transform: scale(1) translateY(0);     opacity: 1; }
}

.sam-card-head {
  padding: 11px 18px;
  background: linear-gradient(90deg, rgba(127,119,221,.08), rgba(212,83,126,.06));
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
}
.sam-pills { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }
.sam-pri-pill {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: lowercase;
}
.sam-sticky-pill {
  background: rgba(212,83,126,.15);
  color: #993556;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  display: inline-flex; align-items: center; gap: 3px;
}
.sam-queue-pill {
  background: rgba(0,0,0,.05);
  color: var(--color-text-secondary, #5F5E5A);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 9.5px;
}
.sam-lock-lbl {
  font-size: 9.5px;
  color: #A32D2D;
  display: inline-flex; align-items: center; gap: 3px;
  text-transform: uppercase;
  letter-spacing: .05em;
  font-weight: 500;
}

.sam-body { padding: 20px 22px 14px; }
.sam-title {
  font-size: 17px;
  color: var(--color-text-primary, #2C2A28);
  font-weight: 500;
  letter-spacing: -.01em;
  margin-bottom: 10px;
}
.sam-text {
  font-size: 13px;
  color: var(--color-text-secondary, #5F5E5A);
  line-height: 1.55;
  white-space: pre-wrap;
}
.sam-link {
  display: inline-flex; align-items: center; gap: 5px;
  margin-top: 10px;
  color: #534AB7;
  font-size: 12px;
  text-decoration: none;
}
.sam-link:hover { text-decoration: underline; }

.sam-deadline {
  margin-top: 14px;
  padding: 9px 12px;
  background: rgba(239,159,39,.1);
  border-radius: 6px;
  font-size: 12px;
  color: #854F0B;
  display: flex; align-items: center; gap: 6px;
  font-feature-settings: "tnum";
  position: relative; overflow: hidden;
}
.sam-deadline::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #EF9F27;
  animation: uzaStripeDrawIn .6s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}

.sam-form { margin-top: 14px; }
.sam-question {
  font-size: 12px;
  color: var(--color-text-primary, #2C2A28);
  font-weight: 500;
  margin-bottom: 7px;
}
.sam-textarea {
  width: 100%;
  padding: 8px 11px;
  border: 0.5px solid var(--color-border-tertiary, rgba(0,0,0,.1));
  border-radius: 7px;
  font-family: inherit;
  font-size: 12.5px;
  resize: vertical;
  outline: none;
  background: var(--color-background-primary, #fff);
}
.sam-textarea:focus { border-color: #7F77DD; }

.sam-options { display: flex; flex-direction: column; gap: 5px; }
.sam-option {
  padding: 9px 12px;
  border: 0.5px solid var(--color-border-tertiary, rgba(0,0,0,.1));
  border-radius: 7px;
  font-size: 12.5px;
  cursor: pointer;
  display: flex; align-items: center; gap: 8px;
  transition: all .15s;
}
.sam-option:hover { background: rgba(127,119,221,.04); }
.sam-option.selected {
  background: rgba(127,119,221,.08);
  border-color: #7F77DD;
}
.sam-option input[type="radio"] { accent-color: #7F77DD; }

.sam-yesno { display: flex; gap: 8px; }
.sam-yn-btn {
  flex: 1;
  padding: 10px 14px;
  border: 0.5px solid var(--color-border-tertiary, rgba(0,0,0,.1));
  border-radius: 8px;
  background: var(--color-background-primary, #fff);
  font-family: inherit;
  font-size: 13px;
  cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center; gap: 5px;
}
.sam-yn-yes.selected { background: rgba(29,158,117,.1); border-color: #1D9E75; color: #0F6E56; font-weight: 500; }
.sam-yn-no.selected  { background: rgba(226,75,74,.1);  border-color: #E24B4A; color: #A32D2D; font-weight: 500; }

.sam-hint { font-size: 11.5px; color: var(--color-text-tertiary, #888780); padding: 6px 0; }

.sam-err {
  margin: 0 22px 8px;
  padding: 7px 11px;
  background: rgba(226,75,74,.08);
  border-radius: 6px;
  font-size: 11.5px;
  color: #A32D2D;
}

.sam-footer {
  padding: 12px 18px;
  background: #FAFAFC;
  border-top: 0.5px solid rgba(0,0,0,.05);
  display: flex; align-items: center; gap: 6px;
}
.sam-btn {
  border: 0;
  padding: 8px 16px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  display: inline-flex; align-items: center; gap: 5px;
}
.sam-btn:disabled { opacity: .5; cursor: not-allowed; }
.sam-btn-ghost {
  background: transparent;
  border: 0.5px solid var(--color-border-tertiary, rgba(0,0,0,.1));
  color: var(--color-text-secondary, #5F5E5A);
}
.sam-btn-ghost:hover:not(:disabled) { background: rgba(0,0,0,.03); }
.sam-btn-primary {
  background: #1D9E75;
  color: #fff;
}
.sam-btn-primary:hover:not(:disabled) { background: #167E5D; }

.sam-fade-enter-active, .sam-fade-leave-active { transition: opacity .25s; }
.sam-fade-enter-from, .sam-fade-leave-to { opacity: 0; }
</style>
