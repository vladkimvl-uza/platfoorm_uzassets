<script setup lang="ts">
/**
 * Odometer — премиум-число с роллингом разрядов: каждая цифра «прокручивается»
 * по вертикали к новой (как механический счётчик). Катится:
 *   • при появлении (от 0 к значению — reveal на загрузке),
 *   • при смене значения (напр. морф центра доната по hover).
 * Принимает уже отформатированную строку/число (%, запятые, пробелы) — катятся
 * только цифры [0-9], остальные символы статичны. Наследует font/цвет родителя.
 * Уважает prefers-reduced-motion.
 */
import { computed, ref, onMounted } from "vue";

const props = defineProps<{ value: number | string }>();

// Гейт: до первого кадра все ролики стоят на 0 → затем прокатываются к значению
// (CSS-transition даёт roll-in). Без этого статичное число не анимировалось бы.
const ready = ref(false);
onMounted(() => {
  requestAnimationFrame(() => requestAnimationFrame(() => { ready.value = true; }));
});

const chars = computed(() => {
  const s = String(props.value ?? "");
  return s.split("").map((c) => {
    const digit = c >= "0" && c <= "9";
    return { c, digit, v: digit ? Number(c) : 0 };
  });
});
</script>

<template>
  <span class="odo" :aria-label="String(value)">
    <!-- :key по ПОЗИЦИИ (i), а не по символу — иначе при смене цифры Vue
         пересоздаёт элемент и transform не транзишенится. -->
    <span
      v-for="(ch, i) in chars"
      :key="i"
      class="odo-cell"
      :class="{ 'odo-digit': ch.digit }"
    >
      <span
        v-if="ch.digit"
        class="odo-roll"
        :style="{ transform: `translateY(${(ready ? ch.v : 0) * -10}%)` }"
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
  transition: transform 0.9s cubic-bezier(0.22, 1, 0.36, 1);
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
