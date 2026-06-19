<script setup lang="ts">
/**
 * ConfirmHost — глобальный рендер confirm/prompt-диалогов (см. useConfirm).
 * Монтируется один раз в App.vue рядом с ToastContainer.
 */
import { ref, watch, nextTick } from "vue";
import { useConfirmHost } from "@/composables/useConfirm";

const { current, resolveDialog } = useConfirmHost();

const inputVal = ref("");
const inputEl = ref<HTMLInputElement | null>(null);
const okBtn = ref<HTMLButtonElement | null>(null);
let _lastFocused: HTMLElement | null = null;

watch(current, async (req) => {
  if (req) {
    _lastFocused = (document.activeElement as HTMLElement) || null;
    if (req.kind === "prompt") inputVal.value = req.opts.defaultValue || "";
    await nextTick();
    if (req.kind === "prompt") { inputEl.value?.focus(); inputEl.value?.select(); }
    else okBtn.value?.focus();
  } else if (_lastFocused) {
    _lastFocused.focus?.();
    _lastFocused = null;
  }
});

function onConfirm() {
  const req = current.value;
  if (!req) return;
  resolveDialog(req.kind === "prompt" ? inputVal.value : true);
}
function onCancel() {
  const req = current.value;
  if (!req) return;
  resolveDialog(req.kind === "prompt" ? null : false);
}
function onKeydown(e: KeyboardEvent) {
  if (!current.value) return;
  if (e.key === "Escape") { e.preventDefault(); onCancel(); }
  else if (e.key === "Enter" && current.value.kind === "confirm") { e.preventDefault(); onConfirm(); }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uc-fade">
      <div
        v-if="current"
        class="uc-backdrop"
        role="dialog"
        aria-modal="true"
        :aria-label="current.opts.title || current.opts.message"
        tabindex="-1"
        @click.self="onCancel"
        @keydown="onKeydown"
      >
        <Transition name="uc-pop" appear>
          <div class="uc-card">
            <h3 v-if="current.opts.title" class="uc-title">{{ current.opts.title }}</h3>
            <p class="uc-msg">{{ current.opts.message }}</p>

            <input
              v-if="current.kind === 'prompt'"
              ref="inputEl"
              v-model="inputVal"
              class="uc-input"
              :placeholder="current.opts.placeholder || ''"
              @keydown.enter.prevent="onConfirm"
            />

            <div class="uc-actions">
              <button class="uc-btn uc-btn-ghost" type="button" @click="onCancel">
                {{ current.opts.cancelText || "Отмена" }}
              </button>
              <button
                ref="okBtn"
                class="uc-btn"
                :class="(current.kind === 'confirm' && current.opts.danger) ? 'uc-btn-danger' : 'uc-btn-primary'"
                type="button"
                @click="onConfirm"
              >
                {{ current.opts.confirmText || (current.kind === "prompt" ? "OK" : "Подтвердить") }}
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.uc-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-critical, 100000);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(12, 18, 48, 0.46);
  -webkit-backdrop-filter: blur(5px);
  backdrop-filter: blur(5px);
}
.uc-card {
  width: 100%;
  max-width: 420px;
  background: var(--card-bg, #fff);
  border-radius: 16px;
  padding: 22px 22px 18px;
  border: 1px solid var(--card-border, rgba(16, 24, 64, 0.06));
  box-shadow: 0 2px 6px rgba(16, 24, 64, 0.06), 0 18px 44px rgba(16, 24, 64, 0.20);
}
.uc-title {
  margin: 0 0 8px;
  font-size: 16px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
}
.uc-msg {
  margin: 0 0 16px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--t2, #334155);
  white-space: pre-line;
}
.uc-input {
  width: 100%;
  box-sizing: border-box;
  margin: 0 0 16px;
  border: 1.5px solid var(--border-input, #E2E8F0);
  border-radius: 9px;
  background: var(--bg2, #F8FAFC);
  padding: 9px 11px;
  font-size: 13px;
  font-family: inherit;
  color: var(--t1, #1E2A4A);
  outline: none;
  transition: border-color 0.14s, box-shadow 0.14s;
}
.uc-input:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124, 111, 247, 0.14); }
.uc-actions { display: flex; justify-content: flex-end; gap: 8px; }
.uc-btn {
  border: none;
  border-radius: 9px;
  padding: 9px 16px;
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.14s, box-shadow 0.14s, background 0.14s, filter 0.14s;
}
.uc-btn:active { transform: translateY(1px); }
.uc-btn-ghost {
  background: transparent;
  border: 1px solid var(--border-input, #E2E8F0);
  color: var(--t2, #334155);
}
.uc-btn-ghost:hover { background: var(--bg3, #F1F5F9); }
.uc-btn-primary {
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  color: #fff;
  box-shadow: 0 2px 10px rgba(108, 92, 231, 0.30);
}
.uc-btn-primary:hover { filter: brightness(1.04); box-shadow: 0 4px 14px rgba(108, 92, 231, 0.42); }
.uc-btn-danger {
  background: linear-gradient(135deg, #F2706E 0%, #E24B4A 100%);
  color: #fff;
  box-shadow: 0 2px 10px rgba(226, 75, 74, 0.30);
}
.uc-btn-danger:hover { filter: brightness(1.04); box-shadow: 0 4px 14px rgba(226, 75, 74, 0.42); }

.uc-fade-enter-active, .uc-fade-leave-active { transition: opacity 0.2s ease; }
.uc-fade-enter-from, .uc-fade-leave-to { opacity: 0; }
.uc-pop-enter-active { transition: transform 0.32s cubic-bezier(0.34, 1.3, 0.5, 1), opacity 0.22s ease; }
.uc-pop-enter-from { transform: translateY(12px) scale(0.96); opacity: 0; }
</style>
