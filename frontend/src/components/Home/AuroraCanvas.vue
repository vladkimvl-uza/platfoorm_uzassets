<script setup lang="ts">
/**
 * Calm 2-wave variant: purple-light @ y=0.22, blue @ y=0.50 + 1 horizontal ribbon.
 * Полная семантика: 3 sin-волны per layer, pulse, drift, hue-drift,
 * lighter blend mode.
 */
import { ref, onMounted, onBeforeUnmount } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);
let rafId: number | null = null;
let resizeObserver: ResizeObserver | null = null;

onMounted(() => {
  const cv = canvas.value;
  if (!cv) return;
  const ctx = cv.getContext("2d");
  if (!ctx) return;

  let w = 0, h = 0;
  function resize() {
    if (!cv) return;
    const dpr = window.devicePixelRatio || 1;
    w = cv.clientWidth;
    h = cv.clientHeight;
    cv.width = Math.round(w * dpr);
    cv.height = Math.round(h * dpr);
    ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(cv);

  // ── Hero — calm 2-wave variant (REVISED 2026-04-27) ─────────────
  const layers = [
    { color: "127,119,221", alpha: 0.25, freq1: 0.005, freq2: 0.013, freq3: 0.030, amp1: 0.30, amp2: 0.18, amp3: 0.060, phase: 0.0, yBase: 0.22, speed: 1.8, pulse: 0.42, drift: 0.14, hDrift: 2.5 },
    { color: "55,138,221",  alpha: 0.18, freq1: 0.004, freq2: 0.011, freq3: 0.026, amp1: 0.32, amp2: 0.16, amp3: 0.060, phase: 2.4, yBase: 0.50, speed: 0.6, pulse: 0.48, drift: 0.12, hDrift: 1.4 },
  ];
  const ribbons = [
    { color: "127,119,221", y: 0.18, speed: 0.4, phase: 0, amp: 8, alpha: 0.081, width: 0.30 },
  ];

  let t = 0;
  const tStep = 0.022;

  function draw() {
    ctx!.clearRect(0, 0, w, h);
    ctx!.globalCompositeOperation = "lighter";
    t += tStep;

    // Wave layers
    layers.forEach(L => {
      ctx!.beginPath();
      ctx!.moveTo(0, h);
      const tt = t * L.speed + L.phase;
      const pulse = 1 + L.pulse * Math.sin(t * 0.55 + L.phase * 0.7);
      const a1 = L.amp1 * pulse;
      const a2 = L.amp2 * pulse;
      const a3 = L.amp3 * pulse;
      const yC = L.yBase + L.drift * Math.sin(t * 0.18 + L.phase);
      const xShift = (L.hDrift || 0) * t * (L.phase > 3 ? -1 : 1);
      for (let x = 0; x <= w; x += 3) {
        const xx = x + xShift;
        const y = h * yC
          + Math.sin(xx * L.freq1 + tt) * h * a1
          + Math.sin(xx * L.freq2 + tt * 1.5) * h * a2
          + Math.sin(xx * L.freq3 + tt * 2.3) * h * a3;
        ctx!.lineTo(x, y);
      }
      ctx!.lineTo(w, h);
      ctx!.closePath();
      const grad = ctx!.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, `rgba(${L.color},${L.alpha})`);
      grad.addColorStop(0.6, `rgba(${L.color},${(L.alpha * 0.6).toFixed(3)})`);
      grad.addColorStop(1, `rgba(${L.color},0)`);
      ctx!.fillStyle = grad;
      ctx!.fill();
    });

    // Horizontal ribbons
    ribbons.forEach(R => {
      const yPos = h * R.y + Math.sin(t * R.speed + R.phase) * R.amp;
      const grad = ctx!.createLinearGradient(0, yPos - h * R.width / 2, 0, yPos + h * R.width / 2);
      grad.addColorStop(0, `rgba(${R.color},0)`);
      grad.addColorStop(0.5, `rgba(${R.color},${R.alpha})`);
      grad.addColorStop(1, `rgba(${R.color},0)`);
      ctx!.fillStyle = grad;
      ctx!.fillRect(0, yPos - h * R.width / 2, w, h * R.width);
    });

    ctx!.globalCompositeOperation = "source-over";
    rafId = requestAnimationFrame(draw);
  }

  rafId = requestAnimationFrame(draw);
});

onBeforeUnmount(() => {
  if (rafId !== null) cancelAnimationFrame(rafId);
  if (resizeObserver) resizeObserver.disconnect();
});
</script>

<template>
  <canvas ref="canvas" class="aurora-canvas"></canvas>
</template>

<style scoped>
.aurora-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 1;
}
</style>
