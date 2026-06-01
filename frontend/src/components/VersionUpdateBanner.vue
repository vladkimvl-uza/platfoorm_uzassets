<script setup lang="ts">
/**
 * VersionUpdateBanner — ненавязчивый баннер «доступна новая версия».
 * Появляется, когда useVersionCheck обнаружил новый деплой. Перезагрузку
 * инициирует пользователь (чтобы не потерять несохранённые правки редакторов).
 */
import { updateAvailable } from "@/composables/useVersionCheck";

function reload(): void {
  window.location.reload();
}
</script>

<template>
  <Transition name="vub">
    <div v-if="updateAvailable" class="vub" role="status" aria-live="polite">
      <span class="vub-dot" aria-hidden="true"></span>
      <span class="vub-txt">Доступна новая версия платформы</span>
      <button class="vub-btn" type="button" @click="reload">Обновить</button>
    </div>
  </Transition>
</template>

<style scoped>
.vub {
  position: fixed;
  left: 50%;
  bottom: 20px;
  transform: translateX(-50%);
  z-index: 99998;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px 10px 16px;
  background: var(--card-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(99, 102, 180, 0.18));
  border-radius: 12px;
  box-shadow: 0 10px 32px rgba(15, 23, 60, 0.18);
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  max-width: calc(100vw - 32px);
}
.vub-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #7C6FF7;
  flex-shrink: 0;
  animation: vubPulse 1.8s ease-out infinite;
}
@keyframes vubPulse {
  0%   { box-shadow: 0 0 0 0 rgba(124, 111, 247, 0.5); }
  70%  { box-shadow: 0 0 0 7px rgba(124, 111, 247, 0); }
  100% { box-shadow: 0 0 0 0 rgba(124, 111, 247, 0); }
}
.vub-txt { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vub-btn {
  flex-shrink: 0;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 6px 13px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  font-family: inherit;
  transition: transform 0.14s, box-shadow 0.14s;
  box-shadow: 0 2px 10px rgba(108, 92, 231, 0.32);
}
.vub-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(108, 92, 231, 0.45);
}

.vub-enter-active,
.vub-leave-active { transition: all 0.35s var(--ease-standard); }
.vub-enter-from,
.vub-leave-to { opacity: 0; transform: translate(-50%, 14px); }
</style>
