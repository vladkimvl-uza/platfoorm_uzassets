<script setup lang="ts">
/**
 * MeshGradient — премиум Stripe-style mesh-blob фон для hero-баннера.
 *
 * Pure CSS, 5 blob + sheen sweep + global hue-drift на root.
 * Палитра под navy banner (#0C1230 → #1E2A4A):
 *   purple #8B7FFF, indigo #6366F1, teal #14B8A6, blue #60A5FA, magenta #C084FC
 *
 * GPU-cheap: только transform / filter / opacity (composite layer).
 * Respects prefers-reduced-motion.
 */
</script>

<template>
  <div class="mesh-bg" aria-hidden="true">
    <div class="mesh-blob mesh-blob-1"></div>
    <div class="mesh-blob mesh-blob-2"></div>
    <div class="mesh-blob mesh-blob-3"></div>
    <div class="mesh-blob mesh-blob-4"></div>
    <div class="mesh-blob mesh-blob-5"></div>
    <!-- Sheen sweep — soft highlight sliding diagonally every 12s -->
    <div class="mesh-sheen"></div>
    <!-- Top vignette so eye flows to greeting+cards -->
    <div class="mesh-vignette"></div>
  </div>
</template>

<style scoped>
.mesh-bg {
  position: absolute;
  inset: 0;
  overflow: hidden;
  z-index: 1;
  pointer-events: none;
  /* Faster global hue drift */
  animation: meshHueDrift 5.6s linear infinite;
}

.mesh-blob {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  mix-blend-mode: screen;
  will-change: transform, opacity;
  transform-origin: 50% 50%;
}

/* ── Blob 1: purple, top-left, biggest ─────────────────────── */
.mesh-blob-1 {
  width: 55vw;
  height: 95%;
  top: -25%;
  left: -18%;
  background: radial-gradient(circle at 50% 50%, #8B7FFF 0%, rgba(139, 127, 255, 0.45) 35%, transparent 65%);
  animation:
    meshFloat1 3.2s cubic-bezier(0.45, 0, 0.55, 1) infinite,
    meshPulse1 1.4s ease-in-out infinite;
}

/* ── Blob 2: indigo, top-right ─────────────────────────────── */
.mesh-blob-2 {
  width: 50vw;
  height: 85%;
  top: -15%;
  right: -12%;
  background: radial-gradient(circle at 50% 50%, #6366F1 0%, rgba(99, 102, 241, 0.50) 35%, transparent 65%);
  animation:
    meshFloat2 3.6s cubic-bezier(0.45, 0, 0.55, 1) infinite,
    meshPulse2 1.6s ease-in-out infinite;
  animation-delay: -1.2s, -0.6s;
}

/* ── Blob 3: teal accent, center-bottom ────────────────────── */
.mesh-blob-3 {
  width: 50vw;
  height: 70%;
  bottom: -30%;
  left: 18%;
  background: radial-gradient(circle at 50% 50%, #14B8A6 0%, rgba(20, 184, 166, 0.40) 40%, transparent 65%);
  animation:
    meshFloat3 4s cubic-bezier(0.45, 0, 0.55, 1) infinite,
    meshPulse3 1.2s ease-in-out infinite;
  animation-delay: -2s, -0.2s;
}

/* ── Blob 4: light blue, mid-right ─────────────────────────── */
.mesh-blob-4 {
  width: 38vw;
  height: 65%;
  top: 22%;
  right: 12%;
  background: radial-gradient(circle at 50% 50%, #60A5FA 0%, rgba(96, 165, 250, 0.45) 40%, transparent 65%);
  animation:
    meshFloat4 2.8s cubic-bezier(0.45, 0, 0.55, 1) infinite,
    meshPulse4 1.1s ease-in-out infinite;
  animation-delay: -0.4s, -0.6s;
}

/* ── Blob 5 (NEW): magenta highlight, smaller, fastest ───── */
.mesh-blob-5 {
  width: 30vw;
  height: 55%;
  top: 10%;
  left: 35%;
  background: radial-gradient(circle at 50% 50%, #C084FC 0%, rgba(192, 132, 252, 0.35) 40%, transparent 65%);
  animation:
    meshFloat5 2.4s cubic-bezier(0.45, 0, 0.55, 1) infinite,
    meshPulse5 1s ease-in-out infinite;
  animation-delay: -0.8s, -0.4s;
}

/* Sheen — diagonal highlight sweep every 12s */
.mesh-sheen {
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: linear-gradient(
    115deg,
    transparent 38%,
    rgba(255, 255, 255, 0.06) 48%,
    rgba(255, 255, 255, 0.12) 50%,
    rgba(255, 255, 255, 0.06) 52%,
    transparent 62%
  );
  transform: translateX(-100%);
  animation: meshSheen 2.8s ease-in-out infinite;
  mix-blend-mode: screen;
  pointer-events: none;
}

/* Soft top→bottom vignette */
.mesh-vignette {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 100% at 50% 0%, transparent 0%, rgba(12, 18, 48, 0.30) 80%),
    linear-gradient(180deg, transparent 60%, rgba(12, 18, 48, 0.25) 100%);
  pointer-events: none;
}

/* ───── Animations: bigger movement range, faster cycles ───── */
@keyframes meshFloat1 {
  0%, 100% { transform: translate(0%, 0%) scale(1) rotate(0deg); }
  25%      { transform: translate(28%, 14%) scale(1.20) rotate(8deg); }
  50%      { transform: translate(12%, 32%) scale(0.92) rotate(-5deg); }
  75%      { transform: translate(-15%, 18%) scale(1.10) rotate(4deg); }
}
@keyframes meshFloat2 {
  0%, 100% { transform: translate(0%, 0%) scale(1) rotate(0deg); }
  33%      { transform: translate(-22%, 28%) scale(0.88) rotate(-7deg); }
  66%      { transform: translate(14%, 14%) scale(1.18) rotate(6deg); }
}
@keyframes meshFloat3 {
  0%, 100% { transform: translate(0%, 0%) scale(1) rotate(0deg); }
  40%      { transform: translate(22%, -18%) scale(1.22) rotate(10deg); }
  70%      { transform: translate(-26%, -12%) scale(0.85) rotate(-8deg); }
}
@keyframes meshFloat4 {
  0%, 100% { transform: translate(0%, 0%) scale(1) rotate(0deg); }
  30%      { transform: translate(-30%, 22%) scale(1.25) rotate(-12deg); }
  60%      { transform: translate(20%, -12%) scale(0.82) rotate(8deg); }
}
@keyframes meshFloat5 {
  0%, 100% { transform: translate(0%, 0%) scale(1); }
  25%      { transform: translate(18%, -22%) scale(1.30); }
  50%      { transform: translate(-24%, -8%) scale(0.78); }
  75%      { transform: translate(8%, 24%) scale(1.15); }
}

/* Opacity pulses — each at different tempo for organic feel */
@keyframes meshPulse1 { 0%, 100% { opacity: 0.45; } 50% { opacity: 0.68; } }
@keyframes meshPulse2 { 0%, 100% { opacity: 0.42; } 50% { opacity: 0.62; } }
@keyframes meshPulse3 { 0%, 100% { opacity: 0.30; } 50% { opacity: 0.50; } }
@keyframes meshPulse4 { 0%, 100% { opacity: 0.36; } 50% { opacity: 0.55; } }
@keyframes meshPulse5 { 0%, 100% { opacity: 0.22; } 50% { opacity: 0.42; } }

@keyframes meshSheen {
  0%        { transform: translateX(-100%) translateY(-10%); opacity: 0; }
  10%       { opacity: 1; }
  60%, 100% { transform: translateX(80%)   translateY(10%);  opacity: 0; }
}

@keyframes meshHueDrift {
  0%, 100% { filter: hue-rotate(0deg); }
  50%      { filter: hue-rotate(8deg); }
}

@media (prefers-reduced-motion: reduce) {
  .mesh-bg, .mesh-blob, .mesh-sheen {
    animation: none !important;
  }
}
</style>
