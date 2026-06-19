<script setup lang="ts">
/**
 * Odometer — премиум-число с роллингом разрядов: при смене значения каждая
 * цифра «прокручивается» по вертикали к новой (как механический счётчик).
 * Принимает уже отформатированную строку/число (включая %, запятые, пробелы) —
 * катятся только цифры [0-9], остальные символы статичны. Наследует font-size/
 * вес/цвет от родителя. Уважает prefers-reduced-motion.
 *
 * <Odometer :value="overallText" />   // напр. "97,1 %"
 */
import { computed } from "vue";

const props = defineProps<{ value: number | string }>();

const chars = computed(() => {
  const s = String(props.value ?? "");
  return s.split("").map((c, i) => {
    const digit = c >= "0" && c <= "9";
    return { key: `${i}-${c}`, c, digit, v: digit ? Number(c) : 0 };
  });
});
</script>

<template>
  <span class="odo" :aria-label="String(value)">
    <span
      v-for="ch in chars"
      :key="ch.key"
      class="odo-cell"
      :class="{ 'odo-digit': ch.digit }"
    >
      <span
        v-if="ch.digit"
        class="odo-roll"
        :style="{ transform: `translateY(${ch.v * -10}%)` }"
      >
        <b>0</b><b>1</b><b>2</b><b>3</b><b>4</b><b>5</b><b>6</b><b>7</b><b>8</b><b>9</b>
      </span>
      <template v-else>{{ ch.c }}</template>
    </span>
  </span>
</template>

<style scoped>
.odo {
  display: inline-flex;
  align-items: baseline;
  font-variant-numeric: tabular-nums;
  white-space: pre;
}
.odo-cell { display: inline-block; }
.odo-digit {
  display: inline-block;
  height: 1em;
  line-height: 1;
  overflow: hidden;
  vertical-align: baseline;
}
.odo-roll {
  display: flex;
  flex-direction: column;
  transition: transform 0.85s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform;
}
.odo-roll > b {
  display: block;
  height: 1em;
  line-height: 1;
  font-weight: inherit;
}
@media (prefers-reduced-motion: reduce) {
  .odo-roll { transition: none; }
}
</style>
