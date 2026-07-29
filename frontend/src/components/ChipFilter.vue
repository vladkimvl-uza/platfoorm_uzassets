<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
const props = defineProps<{
  label: string;
  count?: number;
  active?: boolean;
  // Цвет «активного» состояния
  accent?: string;       // напр '#7F77DD' (default)
  accentBg?: string;     // напр 'rgba(127,119,221,.10)' (default)
  // Цвет иконки/индикатора (например для status chips — это цвет dot)
  dotColor?: string;
  // Анимация появления
  animateIn?: boolean;
  // Disabled: показывать но не реагировать на клики
  disabled?: boolean;
}>();

const emit = defineEmits<{
  (e: "click"): void;
}>();

const accent = props.accent || "#7F77DD";
const accentBg = props.accentBg || "rgba(127, 119, 221, 0.10)";
</script>

<template>
  <button
    type="button"
    :class="['chip-filter', { active, disabled, 'chip-anim-in': animateIn }]"
    :disabled="disabled"
    :style="active
      ? { background: accent, color: 'white', borderColor: accent }
      : { background: accentBg, color: accent, borderColor: 'transparent' }"
    @click="!disabled && emit('click')">
    <span v-if="dotColor" class="chip-dot" :style="{ background: dotColor }"></span>
    <slot name="icon"></slot>
    <span class="chip-label">{{ t(label) }}</span>
    <span v-if="count != null" class="chip-count" :style="{ opacity: 0.85 }">
      {{ count }}
    </span>
  </button>
</template>

<style scoped>
.chip-filter {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 11px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 11px;
  font-variant-numeric: tabular-nums;
  font-family: inherit;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background .15s, color .15s, border-color .15s, transform .12s;
  line-height: 1;
  white-space: nowrap;
}
.chip-filter:hover:not(.disabled) {
  filter: brightness(1.04);
  transform: translateY(-1px);
}
.chip-filter.disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.chip-label {
  white-space: nowrap;
}

.chip-count {
  margin-left: 2px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

/* Animation copied 1:1 from legacy fChipIn (line 2372) */
@keyframes chipIn {
  0%   { opacity: 0; transform: scale(.5) translateY(6px); }
  55%  { opacity: 1; transform: scale(1.06) translateY(-1px); }
  100% { opacity: 1; transform: scale(1) translateY(0); }
}
.chip-anim-in {
  animation: chipIn .28s cubic-bezier(.34, 1.56, .64, 1) both;
}
</style>
