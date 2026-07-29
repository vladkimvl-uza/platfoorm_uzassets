<script setup lang="ts">
/**
 * UzaYearStepper — единый степпер года «‹ 2026 ›» (стрелки prev/next).
 * Парный к UzaSegment/UzaSelect: один визуальный язык в топбарах/карточках.
 * Шагает по ДОСТУПНЫМ годам (years), стрелки гаснут на краях диапазона.
 */
import { computed } from "vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
const { t } = useI18n();


const props = withDefaults(
  defineProps<{
    modelValue: number | null;
    years: number[];          // доступные годы (любой порядок)
    label?: string;
    prefix?: string;          // напр. "FY " → «FY 2024»
    tone?: "light" | "dark";
    allowAll?: boolean;       // левая позиция «Все годы» (modelValue = null)
    allLabel?: string;
  }>(),
  { tone: "light", allowAll: false, allLabel: i18nKey("Все годы") },
);

const emit = defineEmits<{ "update:modelValue": [number | null] }>();

const sorted = computed(() => [...(props.years || [])].sort((a, b) => a - b));
// последовательность шагов: при allowAll первым идёт «Все годы» (null)
const seq = computed<(number | null)[]>(() => (props.allowAll ? [null, ...sorted.value] : [...sorted.value]));
const idx = computed(() => seq.value.findIndex((v) => v === props.modelValue));
// Год ВНЕ списка доступных (idx = -1) — рабочая ситуация: значение приходит из
// localStorage и переживает изменение состава данных (год закрыли, компанию
// переключили). Раньше обе стрелки в этом случае гасли, а step(), умеющий
// вернуть выбор в допустимый диапазон, не мог сработать — кнопки заблокированы.
// Степпер запирался навсегда и «переключатель годов не работал» ровно у тех
// пользователей, у кого сохранён выпавший год. Поэтому вне диапазона стрелки
// активны, а первый же клик возвращает к ближайшему доступному году.
const outOfRange = computed(() => idx.value < 0 && seq.value.length > 0);
const canPrev = computed(() => outOfRange.value || idx.value > 0);
const canNext = computed(() => outOfRange.value || (idx.value >= 0 && idx.value < seq.value.length - 1));
const display = computed(() =>
  props.modelValue == null ? t(props.allLabel) : `${props.prefix || ""}${props.modelValue}`);

/** Ближайший доступный год к текущему значению (для выхода из «вне диапазона»). */
function nearest(): number | null | undefined {
  const cur = props.modelValue;
  if (cur == null) return seq.value[seq.value.length - 1];
  let best: number | null | undefined;
  let bestDist = Infinity;
  for (const v of seq.value) {
    if (v == null) continue;
    const d = Math.abs(v - cur);
    if (d < bestDist) { bestDist = d; best = v; }
  }
  return best !== undefined ? best : seq.value[seq.value.length - 1];
}

function step(d: number) {
  const i = idx.value;
  if (i < 0) {
    // Вне диапазона — возвращаемся к ближайшему доступному году, а не к
    // последнему: при сохранённом 2024 и списке [2025, 2026] пользователь
    // ожидает 2025, а не прыжок в конец.
    const near = nearest();
    if (near !== undefined) emit("update:modelValue", near);
    return;
  }
  const ni = i + d;
  if (ni >= 0 && ni < seq.value.length) emit("update:modelValue", seq.value[ni]);
}
</script>

<template>
  <div class="uza-seg-grp">
    <span v-if="label" class="uza-ys-l" :class="'is-' + tone">{{ t(label) }}</span>
    <div class="uza-ys" :class="'is-' + tone">
      <button type="button" class="uza-ys-arr" :disabled="!canPrev" @click="step(-1)" :aria-label="t('Предыдущий год')">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
      </button>
      <span class="uza-ys-val">{{ display }}</span>
      <button type="button" class="uza-ys-arr" :disabled="!canNext" @click="step(1)" :aria-label="t('Следующий год')">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    </div>
  </div>
</template>

<style scoped>
.uza-seg-grp { display: inline-flex; align-items: center; gap: 7px; }
.uza-ys-l {
  font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; white-space: nowrap;
}
.uza-ys-l.is-light { color: var(--t3, #94A3B8); }
.uza-ys-l.is-dark  { color: rgba(255, 255, 255, .42); }

/* Габариты/фон 1:1 с UzaSegment (radius 8, padding 2, тёмный фон .10) */
.uza-ys {
  display: inline-flex; align-items: center; gap: 1px;
  border-radius: 8px; padding: 2px;
}
.uza-ys-val {
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
  padding: 0 5px; min-width: 36px; text-align: center;
}
.uza-ys-arr {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border: none; border-radius: 6px;
  background: transparent; cursor: pointer; font-family: inherit;
  transition: background .16s, color .16s, opacity .16s;
}
.uza-ys-arr:disabled { opacity: .3; cursor: default; }

/* ── Светлый ── */
.uza-ys.is-light { background: var(--bg2, #F1F0F7); border: 1px solid var(--line, rgba(30,42,74,.06)); }
.uza-ys.is-light .uza-ys-val { color: var(--t1, #1A1730); }
.uza-ys.is-light .uza-ys-arr { color: var(--t2, #6B6880); }
.uza-ys.is-light .uza-ys-arr:not(:disabled):hover { background: #E9E7F2; color: var(--p-deep, #534AB7); }

/* ── Тёмный (навы-топбары) ── */
.uza-ys.is-dark { background: rgba(255, 255, 255, .10); border: 1px solid rgba(255, 255, 255, .08); }
.uza-ys.is-dark .uza-ys-val { color: #fff; }
.uza-ys.is-dark .uza-ys-arr { color: rgba(255, 255, 255, .62); }
.uza-ys.is-dark .uza-ys-arr:not(:disabled):hover { background: rgba(255, 255, 255, .18); color: #fff; }
</style>
