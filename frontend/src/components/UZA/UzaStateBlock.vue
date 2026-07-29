<script setup lang="ts">
/**
 * UzaStateBlock — единый блок состояний: пусто / загрузка / ошибка.
 *
 * Заменяет россыпь кустарных `.*-empty` / `.*-loading` / `.*-error` по дашбордам
 * (Apple-аудит, п.7 — консолидация состояний). Палитра и размеры берутся из
 * дизайн-токенов, поэтому блок выглядит «родным» в любом модуле.
 *
 * state: 'empty' | 'loading' | 'error'
 * variant (если не задан — дефолт под состояние):
 *   empty   → 'block'  (центр: иконка-слот + title + desc + CTA) | 'inline' (строка, курсив)
 *   loading → 'spinner'(спиннер + текст) | 'text' (только текст) | 'skeleton' (слот для UzaSkeleton)
 *   error   → 'banner' (плашка с ×) | 'block' (центр: иконка + текст + «Повторить»)
 *
 * Слоты: #icon — иконка для empty/error block; default — кастомное сообщение
 * (перебивает text/desc). События: action (CTA empty), retry, dismiss.
 */
import { computed, useSlots } from "vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
const { t } = useI18n();


const props = withDefaults(
  defineProps<{
    state: "empty" | "loading" | "error";
    variant?: "block" | "inline" | "banner" | "spinner" | "text" | "skeleton";
    text?: string;          // основное сообщение (empty inline / loading / error)
    title?: string;         // заголовок для empty block
    desc?: string;          // описание для empty block
    loadingText?: string;
    actionLabel?: string;   // CTA для empty block
    retry?: boolean;        // показать кнопку «Повторить» у error block
    retryLabel?: string;    // подпись кнопки повтора
    dismissible?: boolean;  // показать × у error banner
    minHeight?: string;
  }>(),
  {
    loadingText: i18nKey("Загрузка…"),
    retryLabel: i18nKey("Повторить"),
  },
);

const emit = defineEmits<{
  (e: "action"): void;
  (e: "retry"): void;
  (e: "dismiss"): void;
}>();

const slots = useSlots();

// Дефолтный вариант под каждое состояние.
const v = computed(() => {
  if (props.variant) return props.variant;
  return props.state === "loading"
    ? "spinner"
    : props.state === "error"
      ? "banner"
      : "block";
});

const role = computed(() =>
  props.state === "error" ? "alert" : props.state === "loading" ? "status" : undefined,
);
</script>

<template>
  <div
    class="usb"
    :class="[`usb-${state}`, `usb-v-${v}`]"
    :style="minHeight ? { minHeight } : undefined"
    :role="role"
    :aria-busy="state === 'loading' ? 'true' : undefined"
  >
    <!-- ── LOADING ─────────────────────────────────────────── -->
    <template v-if="state === 'loading'">
      <slot v-if="v === 'skeleton'" />
      <template v-else>
        <span v-if="v === 'spinner'" class="usb-spinner" aria-hidden="true" />
        <span class="usb-load-txt">{{ t(text || loadingText) }}</span>
      </template>
    </template>

    <!-- ── ERROR ───────────────────────────────────────────── -->
    <template v-else-if="state === 'error'">
      <template v-if="v === 'block'">
        <span class="usb-ico usb-ico-err" aria-hidden="true">
          <slot name="icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="9" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </slot>
        </span>
        <div v-if="title" class="usb-title">{{ t(title) }}</div>
        <div class="usb-msg"><slot>{{ t(text || '') }}</slot></div>
        <button v-if="retry" class="usb-btn usb-retry" type="button" @click="emit('retry')">{{ t(retryLabel) }}</button>
        <div v-if="slots.actions" class="usb-actions"><slot name="actions" /></div>
      </template>
      <template v-else>
        <span class="usb-msg"><slot>{{ t(text || '') }}</slot></span>
        <button v-if="dismissible" class="usb-x" type="button" :aria-label="t('Закрыть')" @click="emit('dismiss')">×</button>
      </template>
    </template>

    <!-- ── EMPTY ───────────────────────────────────────────── -->
    <template v-else>
      <slot v-if="v === 'inline'">{{ t(text || '') }}</slot>
      <template v-else>
        <span v-if="slots.icon" class="usb-ico" aria-hidden="true"><slot name="icon" /></span>
        <div v-if="title" class="usb-title">{{ t(title) }}</div>
        <div class="usb-desc"><slot>{{ t(desc || text || '') }}</slot></div>
        <button v-if="actionLabel" class="usb-btn usb-cta" type="button" @click="emit('action')">{{ t(actionLabel) }}</button>
        <div v-if="slots.actions" class="usb-actions"><slot name="actions" /></div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.usb {
  width: 100%;
  box-sizing: border-box;
}

/* ── Empty: inline (строка в списке/таблице) ───────────────── */
.usb-empty.usb-v-inline {
  padding: 20px;
  text-align: center;
  font-size: 11px;
  font-style: italic;
  color: var(--t3, #94a3b8);
}

/* ── Empty: block (центрированный) ─────────────────────────── */
.usb-empty.usb-v-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 20px 40px;
  text-align: center;
}
.usb-empty .usb-ico {
  display: inline-flex;
  color: rgba(124, 111, 247, 0.5);
}
.usb-title {
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--t1, #1e2a4a);
}
.usb-desc {
  font-size: 12.5px;
  line-height: 1.55;
  max-width: 380px;
  color: var(--t3, #94a3b8);
}

/* ── Loading ───────────────────────────────────────────────── */
.usb-loading.usb-v-text,
.usb-loading.usb-v-spinner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 40px 20px;
}
.usb-load-txt {
  font-size: 12.5px;
  color: var(--t3, #64748b);
}
.usb-spinner {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  border: 2px solid rgba(124, 111, 247, 0.2);
  border-top-color: var(--p, #7c6ff7);
  border-radius: 50%;
  animation: usbSpin 0.7s linear infinite;
}

/* ── Error: banner (плашка) ────────────────────────────────── */
.usb-error.usb-v-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 11px 14px;
  border-radius: 8px;
  background: rgba(226, 75, 74, 0.08);
  border: 1px solid rgba(226, 75, 74, 0.18);
  color: #a32d2d;
  font-size: 12px;
}
.usb-error.usb-v-banner .usb-msg { min-width: 0; }
.usb-x {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
  color: inherit;
  opacity: 0.7;
  padding: 0 2px;
  transition: opacity 0.12s;
}
.usb-x:hover { opacity: 1; }

/* ── Error: block (центрированный + повтор) ────────────────── */
.usb-error.usb-v-block {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 40px 20px;
  text-align: center;
}
.usb-error .usb-ico-err { color: var(--sev-high, #e24b4a); display: inline-flex; }
.usb-error.usb-v-block .usb-msg {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--sev-high, #e24b4a);
  max-width: 420px;
}

/* ── Buttons (CTA / retry) ─────────────────────────────────── */
.usb-btn {
  font: 500 12px var(--font, inherit);
  padding: 7px 14px;
  border-radius: 9px;
  cursor: pointer;
  border: 1px solid var(--p, #7c6ff7);
  background: var(--p, #7c6ff7);
  color: #fff;
  transition: filter 0.14s, transform 0.14s;
}
.usb-btn:hover { filter: brightness(1.06); }
.usb-btn:active { transform: scale(0.97); }
.usb-retry {
  background: transparent;
  color: var(--p-deep, #534ab7);
  border-color: var(--border2, rgba(99, 102, 180, 0.18));
}
.usb-retry:hover { background: rgba(124, 111, 247, 0.08); filter: none; }

/* Слот для кастомных CTA-кнопок (несколько действий в пусто/ошибка-блоке) */
.usb-actions { display: flex; gap: 8px; margin-top: 2px; flex-wrap: wrap; justify-content: center; }

@keyframes usbSpin { to { transform: rotate(360deg); } }
</style>
