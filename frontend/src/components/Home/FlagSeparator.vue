<script setup lang="ts">
/**
 * FlagSeparator — 1:1 с флаг-полосой из ExecDashTopbar.vue (lines 288-326):
 *   - 5px высота
 *   - linear-gradient(90deg) с 3 цветными секциями (cyan / white / green)
 *     и двумя тонкими красными разделителями 0.5%
 *   - sheen sweep: 28% ширина, 8s loop, mix-blend-mode: screen
 *
 * Entry: scaleX 0→1 from left (синхронно с виджетом праздника, delay 0.36s).
 */
</script>

<template>
  <div class="flag-sep" aria-hidden="true"></div>
</template>

<style scoped>
/* 1:1 с .edt-flag из ExecDashTopbar */
.flag-sep {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 5px;
  background: linear-gradient(
    90deg,
    #0099B5 0%,    #0099B5 33%,
    #CE1126 33%,   #CE1126 33.5%,
    #FFFFFF 33.5%, #FFFFFF 66.5%,
    #CE1126 66.5%, #CE1126 67%,
    #1EB53A 67%,   #1EB53A 100%
  );
  pointer-events: none;
  z-index: 5;
  overflow: hidden;
  /* Entry sync с TomorrowHolidayWidget (thIn 550ms, delay 360ms) */
  transform: scaleX(0);
  transform-origin: left center;
  animation: flagPour 700ms var(--ease-standard) 0.36s forwards;
}

/* Sheen — 1:1 с edt-flag::before (28% width, 8s loop) */
.flag-sep::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 28%;
  background: linear-gradient(
    115deg,
    transparent 38%,
    rgba(255, 255, 255, 0.10) 45%,
    rgba(255, 255, 255, 0.65) 50%,
    rgba(255, 255, 255, 0.10) 55%,
    transparent 62%
  );
  animation: edtFlagSheen 8s ease-in-out 1;
  pointer-events: none;
  mix-blend-mode: screen;
}
@keyframes edtFlagSheen {
  0%        { transform: translateX(-150%); }
  60%, 100% { transform: translateX(450%);  }
}

@keyframes flagPour {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}

@media (prefers-reduced-motion: reduce) {
  .flag-sep { animation: none; transform: scaleX(1); }
  .flag-sep::before { animation: none; display: none; }
}
</style>
