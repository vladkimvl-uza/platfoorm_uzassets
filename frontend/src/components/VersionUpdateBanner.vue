<script setup lang="ts">
/**
 * VersionUpdateBanner — заметный баннер «доступна новая версия».
 * Появляется сверху по центру, когда useVersionCheck обнаружил новый деплой.
 * Перезагрузку инициирует пользователь (чтобы не потерять несохранённые правки
 * редакторов KPI/финмодели). «Позже» скрывает баннер, но он мягко возвращается
 * через несколько минут — чтобы рассинхрон версий не жил бесконечно.
 */
import { ref, watch, onBeforeUnmount } from "vue";
import { updateAvailable } from "@/composables/useVersionCheck";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const dismissed = ref(false);
const show = ref(false);
let renagTimer: number | undefined;

watch(updateAvailable, (v) => { if (v) show.value = true; }, { immediate: true });

function reload(): void {
  window.location.reload();
}

function later(): void {
  show.value = false;
  dismissed.value = true;
  if (renagTimer) window.clearTimeout(renagTimer);
  // Мягко напомнить снова через 4 минуты, если так и не обновились.
  renagTimer = window.setTimeout(() => {
    if (updateAvailable.value) { dismissed.value = false; show.value = true; }
  }, 4 * 60_000);
}

onBeforeUnmount(() => { if (renagTimer) window.clearTimeout(renagTimer); });
</script>

<template>
  <Transition name="vub">
    <div v-if="show && updateAvailable" class="vub" role="status" aria-live="polite">
      <span class="vub-ic" aria-hidden="true">
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12a9 9 0 1 1-2.64-6.36" />
          <path d="M21 3v6h-6" />
        </svg>
      </span>
      <div class="vub-body">
        <div class="vub-ttl">{{ t('Доступно обновление платформы') }}</div>
        <div class="vub-sub">{{ t('Перезагрузите, чтобы получить последние улучшения') }}</div>
      </div>
      <button class="vub-btn" type="button" @click="reload">{{ t('Обновить') }}</button>
      <button class="vub-x" type="button" :aria-label="t('Позже')" :title="t('Позже')" @click="later">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.vub {
  position: fixed;
  left: 50%;
  top: 16px;
  transform: translateX(-50%);
  z-index: 99999;
  display: flex;
  align-items: center;
  gap: 13px;
  padding: 11px 12px 11px 15px;
  background: linear-gradient(120deg, #1E2A4A 0%, #2E2A66 55%, #4B3F9E 100%);
  border: 1px solid rgba(124, 111, 247, 0.45);
  border-radius: 14px;
  box-shadow: 0 16px 44px rgba(24, 18, 70, 0.40), 0 4px 14px rgba(15, 23, 60, 0.22);
  color: #fff;
  max-width: calc(100vw - 24px);
}
.vub-ic {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; flex-shrink: 0;
  border-radius: 9px;
  background: rgba(124, 111, 247, 0.22);
  color: #C8C2FF;
  animation: vubSpin 9s linear infinite;
}
@keyframes vubSpin { to { transform: rotate(360deg); } }
.vub-body { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.vub-ttl { font-size: 13px; font-weight: 600; letter-spacing: -.01em; white-space: nowrap; }
.vub-sub { font-size: 11px; font-weight: 400; color: rgba(255, 255, 255, 0.62); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.vub-btn {
  flex-shrink: 0;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  color: #fff; border: none; border-radius: 9px;
  padding: 8px 16px; font-size: 12.5px; font-weight: 600;
  cursor: pointer; font-family: inherit;
  transition: transform 0.14s var(--ease-standard, ease), box-shadow 0.14s;
  box-shadow: 0 3px 12px rgba(108, 92, 231, 0.5);
}
.vub-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108, 92, 231, 0.6); }
.vub-btn:active { transform: translateY(0); }
.vub-x {
  flex-shrink: 0; width: 26px; height: 26px;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; border-radius: 7px;
  color: rgba(255, 255, 255, 0.55); cursor: pointer; padding: 0;
  transition: background .12s, color .12s;
}
.vub-x:hover { background: rgba(255, 255, 255, 0.12); color: #fff; }

.vub-enter-active, .vub-leave-active { transition: opacity .35s var(--ease-standard, ease), transform .35s var(--ease-standard, ease); }
.vub-enter-from, .vub-leave-to { opacity: 0; transform: translate(-50%, -16px); }

@media (max-width: 560px) {
  .vub { gap: 9px; padding: 9px 9px 9px 12px; top: 10px; }
  .vub-sub { display: none; }
  .vub-ttl { font-size: 12px; white-space: normal; }
  .vub-ic { width: 28px; height: 28px; }
  .vub-btn { padding: 7px 13px; font-size: 12px; }
}
</style>
