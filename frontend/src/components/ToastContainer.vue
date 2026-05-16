<script setup lang="ts">
/**
 * ToastContainer.vue -- глобальный рендер активных toasts.
 * Подключается ОДИН раз в App.vue.
 *
 * Дизайн: UzAssets glassmorphism, palette #1D9E75 / #E24B4A / #378ADD,
 * анимация 380ms cubic-bezier(0.34, 1.2, 0.64, 1).
 */

import { useToast } from "@/composables/useToast";

const { toasts, remove } = useToast();

function iconPath(kind: string): string {
  if (kind === "ok") {
    return "M5 12 L10 17 L19 8";
  }
  if (kind === "err") {
    return "M6 6 L18 18 M18 6 L6 18";
  }
  return "M12 8 L12 13 M12 16 L12 16.5";
}
</script>

<template>
  <Teleport to="body">
    <div class="uza-toast-container">
      <TransitionGroup name="uza-toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="uza-toast"
          :class="`uza-toast-${t.kind}`"
          @click="remove(t.id)"
          role="alert"
        >
          <span class="uza-toast-icon">
            <svg
              v-if="t.kind === 'ok'"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.4"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M5 12 L10 17 L19 8" />
            </svg>
            <svg
              v-else-if="t.kind === 'err'"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.4"
              stroke-linecap="round"
            >
              <circle cx="12" cy="12" r="10" stroke-width="2" />
              <path d="M12 8 L12 13 M12 16 L12 16.5" />
            </svg>
            <svg
              v-else
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M12 8 L12 13 M12 16 L12 16.5" stroke-width="2.4" />
            </svg>
          </span>
          <span class="uza-toast-msg">{{ t.message }}</span>
          <button
            class="uza-toast-close"
            @click.stop="remove(t.id)"
            aria-label="Закрыть"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
            >
              <path d="M6 6 L18 18 M18 6 L6 18" />
            </svg>
          </button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.uza-toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column-reverse;
  gap: 10px;
  z-index: 9999;
  max-width: 460px;
  pointer-events: none;
}

.uza-toast {
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px 12px 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: -0.005em;
  color: white;
  cursor: pointer;
  user-select: none;
  box-shadow:
    0 12px 32px rgba(15, 23, 60, 0.22),
    0 4px 12px rgba(15, 23, 60, 0.12);
  -webkit-backdrop-filter: blur(20px);
  backdrop-filter: blur(20px);
  border: 0.5px solid rgba(255, 255, 255, 0.18);
  min-width: 240px;
  max-width: 460px;
}

.uza-toast-ok {
  background: linear-gradient(135deg, #1d9e75 0%, #15825e 100%);
}
.uza-toast-err {
  background: linear-gradient(135deg, #e24b4a 0%, #c93331 100%);
}
.uza-toast-info {
  background: linear-gradient(135deg, #378add 0%, #2a6ec0 100%);
}

.uza-toast-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.18);
}

.uza-toast-msg {
  flex: 1;
  line-height: 1.4;
  word-break: break-word;
}

.uza-toast-close {
  flex-shrink: 0;
  background: transparent;
  border: none;
  padding: 4px;
  margin: -4px -2px -4px 0;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.7);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s ease;
}
.uza-toast-close:hover {
  background: rgba(255, 255, 255, 0.18);
  color: white;
}

/* Animations -- UzAssets cubic-bezier overshoot */
.uza-toast-enter-active {
  transition:
    opacity 0.38s cubic-bezier(0.34, 1.2, 0.64, 1),
    transform 0.38s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.uza-toast-leave-active {
  transition:
    opacity 0.28s ease,
    transform 0.28s ease;
}
.uza-toast-enter-from {
  opacity: 0;
  transform: translateX(60px) scale(0.95);
}
.uza-toast-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}

@media (prefers-reduced-motion: reduce) {
  .uza-toast-enter-active,
  .uza-toast-leave-active {
    transition: opacity 0.18s ease;
  }
  .uza-toast-enter-from,
  .uza-toast-leave-to {
    transform: none;
  }
}

@media (max-width: 540px) {
  .uza-toast-container {
    bottom: 16px;
    right: 12px;
    left: 12px;
    max-width: calc(100vw - 24px);
  }
  .uza-toast {
    min-width: 0;
  }
}
</style>
