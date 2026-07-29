<script setup lang="ts">
// #5 — число разной жирностью: целая 600, дробная + единица 400 приглушённые.
// Drop-in замена {{ value }} в KPI: <NumMixed :value="x" />.
// Строгий парсер: всё, что не «число/деньги/процент/ratio», рендерится как есть.
import { computed } from "vue";

const props = defineProps<{ value: number | string | null | undefined }>();

const parts = computed(() => {
  const raw = String(props.value ?? "").trim();
  const m = raw.match(/^([$₽€⃀]?)([\d\s,]*\d)(\.\d+)?\s*(%|x|×|M|B|K|млн|млрд|тыс|шт)?$/i); // i18n-exempt -- numeric parser suffixes
  if (!m) return null;
  return { pre: m[1] || "", int: m[2], dec: m[3] || "", unit: m[4] || "" };
});
</script>

<template>
  <span class="uza-num"><template v-if="parts"><span v-if="parts.pre" class="uza-num-u">{{ parts.pre }}</span><span class="uza-num-i">{{ parts.int }}</span><span v-if="parts.dec" class="uza-num-d">{{ parts.dec }}</span><span v-if="parts.unit" class="uza-num-u">{{ parts.unit }}</span></template><template v-else>{{ value }}</template></span>
</template>

<style scoped>
.uza-num { font-variant-numeric: tabular-nums; }
.uza-num-i { font-weight: 600; }
.uza-num-d { font-weight: 400; opacity: .6; }
.uza-num-u { font-weight: 400; font-size: .62em; opacity: .6; margin-left: 1px; }
</style>
