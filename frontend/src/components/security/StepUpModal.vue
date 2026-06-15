<script setup lang="ts">
/**
 * StepUpModal — повторная аутентификация для чувствительных операций.
 * Монтируется один раз в AppShell; управляется через useStepUp (промис-API).
 */
import { ref, watch, nextTick } from "vue";
import { useStepUp } from "@/composables/useStepUp";

const { state, submit, cancel } = useStepUp();
const password = ref("");
const input = ref<HTMLInputElement | null>(null);

watch(() => state.open, async (open) => {
  if (open) {
    password.value = "";
    await nextTick();
    input.value?.focus();
  }
});

function onSubmit() {
  submit(password.value);
}
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") cancel();
}
</script>

<template>
  <Teleport to="body">
    <Transition name="su-fade">
      <div v-if="state.open" class="su-overlay" @keydown="onKey">
        <div class="su-card" role="dialog" aria-modal="true">
          <div class="su-ic">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <h3 class="su-title">Подтвердите личность</h3>
          <p class="su-sub">Это действие защищено. Введите пароль ещё раз, чтобы продолжить.</p>

          <form @submit.prevent="onSubmit">
            <input
              ref="input"
              v-model="password"
              type="password"
              class="su-in"
              :class="{ 'su-in-err': state.error }"
              placeholder="Текущий пароль"
              autocomplete="current-password"
              :disabled="state.busy"
            />
            <p v-if="state.error" class="su-err">{{ state.error }}</p>
            <div class="su-actions">
              <button type="button" class="su-btn su-ghost" :disabled="state.busy" @click="cancel">Отмена</button>
              <button type="submit" class="su-btn su-primary" :disabled="state.busy || !password">
                {{ state.busy ? 'Проверка…' : 'Подтвердить' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.su-overlay {
  position: fixed; inset: 0; z-index: 9500;
  background: rgba(20, 16, 40, .42); backdrop-filter: blur(3px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.su-card {
  width: 360px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 16px;
  box-shadow: 0 24px 60px -12px rgba(30, 20, 70, .4);
  padding: 26px 24px 22px; text-align: center;
  font-family: Geist, system-ui, sans-serif;
}
.su-ic {
  width: 48px; height: 48px; margin: 0 auto 14px;
  border-radius: 13px; display: flex; align-items: center; justify-content: center;
  background: rgba(124,111,247,.12); color: var(--p-deep, #534AB7);
}
.su-ic svg { width: 24px; height: 24px; }
.su-title { font-size: 17px; font-weight: 600; color: var(--t1, #1A1730); margin: 0 0 6px; }
.su-sub { font-size: 12.5px; color: var(--t2, #6B6880); margin: 0 0 18px; line-height: 1.5; }
.su-in {
  width: 100%; box-sizing: border-box; padding: 11px 13px;
  border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 10px;
  font-size: 14px; outline: none; font-family: inherit;
  transition: border-color .14s, box-shadow .14s;
}
.su-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.16); }
.su-in-err { border-color: #E24B4A; }
.su-err { color: #C5352F; font-size: 12px; margin: 8px 0 0; text-align: left; }
.su-actions { display: flex; gap: 10px; margin-top: 18px; }
.su-btn {
  flex: 1; padding: 10px; border-radius: 10px; border: none;
  font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit;
  transition: all .14s;
}
.su-ghost { background: var(--bg2, #F1F0F7); color: var(--t2, #5F5E5A); }
.su-ghost:hover { background: #E7E5F1; }
.su-primary { background: var(--p-deep, #534AB7); color: #fff; }
.su-primary:hover:not(:disabled) { background: #43399E; }
.su-btn:disabled { opacity: .6; cursor: default; }

.su-fade-enter-active, .su-fade-leave-active { transition: opacity .18s ease; }
.su-fade-enter-from, .su-fade-leave-to { opacity: 0; }
.su-fade-enter-active .su-card { animation: suPop .22s var(--ease-standard); }
@keyframes suPop { from { transform: translateY(8px) scale(.97); opacity: 0; } to { transform: none; opacity: 1; } }
</style>
