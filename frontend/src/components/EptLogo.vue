<!--
  EptLogo — анимированный логотип Единой платформы трансформации

  Палитра: #7F77DD → #1D9E75 (пурпур-бирюза), пиксели #AFA9EC
  Анимация A1 «Сборка»: пиксели слетаются → проявляется стрелка (~2.05s)
  Уважает prefers-reduced-motion

  Использование:
    <EptLogo :size="64" />
    <EptLogo ref="logoRef" :size="220" /> + logoRef.value?.replay()
-->

<script setup lang="ts">
import { ref, computed } from 'vue'
import { i18nKey } from "@/locale/keys";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();



interface Props {
  size?: number
  ariaLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  size: 64,
  ariaLabel: i18nKey('UzAssets — Единая платформа трансформации'),
})

const renderKey = ref(0)

// Уникальные id для defs — на случай нескольких инстансов на странице
const uid = Math.random().toString(36).slice(2, 10)
const gradId = `ept-grad-${uid}`
const clipId = `ept-clip-${uid}`

const height = computed(() => Math.round((props.size * 220) / 240))

/**
 * Перезапустить анимацию сборки.
 * Вызывать на роут-смене, после re-login, при значимых событиях.
 * Работает через смену :key — Vue пересоздаёт SVG, CSS-анимации стартуют заново.
 */
function replay(): void {
  renderKey.value++
}

defineExpose({ replay })
</script>

<template>
  <div
    class="ept-logo"
    :style="{ width: `${size}px`, height: `${height}px` }"
  >
    <svg
      :key="renderKey"
      :width="size"
      :height="height"
      viewBox="0 0 240 220"
      :aria-label="t(ariaLabel)"
      role="img"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <linearGradient :id="gradId" x1="0" y1="0.5" x2="1" y2="0.5">
          <stop offset="0%" stop-color="#7F77DD" />
          <stop offset="100%" stop-color="#1D9E75" />
        </linearGradient>
        <clipPath :id="clipId">
          <path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" />
        </clipPath>
      </defs>

      <g class="ept-arrow">
        <path
          d="M 80 30 L 210 110 L 80 190 L 115 110 Z"
          :fill="`url(#${gradId})`"
        />
        <g :clip-path="`url(#${clipId})`">
          <rect x="80" y="50"  width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="68"  width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="86"  width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="104" width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="122" width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="140" width="130" height="2" fill="#1E2A4A" opacity="0.5" />
          <rect x="80" y="158" width="130" height="2" fill="#1E2A4A" opacity="0.5" />
        </g>
      </g>

      <g fill="#AFA9EC">
        <rect class="ept-pixel" x="68" y="35"  width="7" height="7" />
        <rect class="ept-pixel" x="56" y="50"  width="6" height="6" />
        <rect class="ept-pixel" x="42" y="62"  width="6" height="6" />
        <rect class="ept-pixel" x="64" y="72"  width="5" height="5" />
        <rect class="ept-pixel" x="28" y="82"  width="6" height="6" />
        <rect class="ept-pixel" x="50" y="94"  width="6" height="6" />
        <rect class="ept-pixel" x="18" y="106" width="5" height="5" />
        <rect class="ept-pixel" x="36" y="116" width="6" height="6" />
        <rect class="ept-pixel" x="60" y="126" width="5" height="5" />
        <rect class="ept-pixel" x="44" y="138" width="6" height="6" />
        <rect class="ept-pixel" x="64" y="150" width="5" height="5" />
        <rect class="ept-pixel" x="48" y="162" width="6" height="6" />
        <rect class="ept-pixel" x="66" y="178" width="6" height="6" />
        <rect class="ept-pixel" x="34" y="156" width="4" height="4" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.ept-logo {
  display: inline-block;
  line-height: 0;
}

.ept-logo svg {
  display: block;
}

.ept-pixel {
  transform-box: fill-box;
  transform-origin: center;
  animation: ept-assemble 1.4s cubic-bezier(0.25, 0.85, 0.3, 1) both;
}

@keyframes ept-assemble {
  0%   { transform: translate(-28px, -10px) scale(0);   opacity: 0; }
  50%  { transform: translate(-10px, -4px)  scale(0.7); opacity: 0.5; }
  100% { transform: translate(0, 0)         scale(1);   opacity: 1; }
}

.ept-pixel:nth-child(1)  { animation-delay: 0.00s; }
.ept-pixel:nth-child(2)  { animation-delay: 0.05s; }
.ept-pixel:nth-child(3)  { animation-delay: 0.10s; }
.ept-pixel:nth-child(4)  { animation-delay: 0.15s; }
.ept-pixel:nth-child(5)  { animation-delay: 0.20s; }
.ept-pixel:nth-child(6)  { animation-delay: 0.25s; }
.ept-pixel:nth-child(7)  { animation-delay: 0.30s; }
.ept-pixel:nth-child(8)  { animation-delay: 0.35s; }
.ept-pixel:nth-child(9)  { animation-delay: 0.40s; }
.ept-pixel:nth-child(10) { animation-delay: 0.45s; }
.ept-pixel:nth-child(11) { animation-delay: 0.50s; }
.ept-pixel:nth-child(12) { animation-delay: 0.55s; }
.ept-pixel:nth-child(13) { animation-delay: 0.60s; }
.ept-pixel:nth-child(14) { animation-delay: 0.65s; }

.ept-arrow {
  transform-box: fill-box;
  transform-origin: center;
  animation: ept-arrow-in 1.4s cubic-bezier(0.25, 0.85, 0.3, 1) 0.6s both;
}

@keyframes ept-arrow-in {
  0%   { opacity: 0; transform: translateX(-12px); }
  100% { opacity: 1; transform: translateX(0); }
}

@media (prefers-reduced-motion: reduce) {
  .ept-pixel,
  .ept-arrow {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>