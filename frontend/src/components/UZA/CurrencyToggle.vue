<script setup lang="ts">
/**
 * CurrencyToggle.vue
 * ─────────────────────────────────────────────────────────────────
 * Segmented control «сум | USD» в едином стиле UZA design system.
 *
 * Использование:
 *   <CurrencyToggle :year="2025" />
 *
 * Переключает глобальное состояние useCurrencyConverter — все модалки
 * и блоки, подписанные на composable, автоматически перерендерятся.
 *
 * Если передан year — показывается курс под toggle мелким текстом.
 *
 * Pack 7.34
 */
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


interface Props {
  year?: number;
  /** Показать курс под toggle */
  showRate?: boolean;
  /** Компактный режим (без подписи "Валюта:") */
  compact?: boolean;
}
withDefaults(defineProps<Props>(), {
  year: 2025,
  showRate: true,
  compact: false,
});

const conv = useCurrencyConverter();
</script>

<template>
  <div class="ctg-wrap">
    <span v-if="!compact" class="ctg-lbl">{{ t('Валюта:') }}</span>
    <div class="ctg-seg" role="group" :aria-label="t('Переключатель валюты')">
      <button
        type="button"
        class="ctg-btn"
        :class="{ 'ctg-btn--on': conv.currency.value === 'UZS' }"
        :aria-pressed="conv.currency.value === 'UZS'"
        @click="conv.setCurrency('UZS')"
      >
        {{ t('сум') }}
      </button>
      <button
        type="button"
        class="ctg-btn"
        :class="{ 'ctg-btn--on': conv.currency.value === 'USD' }"
        :aria-pressed="conv.currency.value === 'USD'"
        @click="conv.setCurrency('USD')"
      >
        USD
      </button>
      <button
        type="button"
        class="ctg-btn"
        :class="{ 'ctg-btn--on': conv.currency.value === 'EUR' }"
        :aria-pressed="conv.currency.value === 'EUR'"
        @click="conv.setCurrency('EUR')"
      >
        EUR
      </button>
    </div>
    <span
      v-if="showRate && conv.currency.value !== 'UZS'"
      class="ctg-rate"
      :title="t('Среднегодовой курс ЦБ РУ за {value0} год', { value0: year })"
    >
      {{ t('по курсу') }} {{ t(conv.getRateLabel(year)) }}
    </span>
  </div>
</template>

<style scoped>
.ctg-wrap {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-family: inherit;
}
.ctg-lbl {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 500;
}
.ctg-seg {
  display: inline-flex;
  background: rgba(15, 23, 60, 0.05);
  border-radius: 7px;
  padding: 2px;
}
.ctg-btn {
  background: transparent;
  border: none;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  padding: 4px 11px;
  border-radius: 5px;
  cursor: pointer;
  font-family: inherit;
  transition: all 0.14s ease;
  letter-spacing: 0.02em;
}
.ctg-btn:hover:not(.ctg-btn--on) {
  color: var(--t1, #1E2A4A);
}
.ctg-btn--on {
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  box-shadow: 0 1px 3px rgba(15, 23, 60, 0.08);
  cursor: default;
}
.ctg-rate {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  font-feature-settings: "tnum";
}
</style>
