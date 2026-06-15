<script setup lang="ts">
/**
 * Лёгкая обёртка над chart.js (canvas). Принимает готовый ChartConfiguration,
 * пересоздаёт график при смене spec, чистит при unmount. Анимации — встроенные.
 */
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { Chart, type ChartConfiguration } from "@/utils/chartjsRegister";

const props = defineProps<{ config: ChartConfiguration; height?: number }>();
const cv = ref<HTMLCanvasElement | null>(null);
let chart: Chart | null = null;

function render() {
  if (!cv.value) return;
  if (chart) { chart.destroy(); chart = null; }
  chart = new Chart(cv.value, props.config);
}

onMounted(render);
watch(() => props.config, render, { deep: true });
onBeforeUnmount(() => { if (chart) { chart.destroy(); chart = null; } });
</script>

<template>
  <div class="auc-wrap" :style="{ height: (height || 180) + 'px' }">
    <canvas ref="cv"></canvas>
  </div>
</template>

<style scoped>
.auc-wrap { position: relative; width: 100%; }
.auc-wrap canvas { width: 100% !important; height: 100% !important; }
</style>
