<script setup lang="ts">
/**
 * Upcoming holiday widget — показывается если в ближайшие 3 дня (сегодня…+3)
 * есть праздник в УЗ. Берёт ближайший подходящий из @/api/holidays.
 */
import { computed } from "vue";
import { getHoliday, HOLIDAY_KIND_COLORS, HOLIDAY_KIND_LABELS, type UzHoliday } from "@/api/holidays";

interface UpcomingHit { holiday: UzHoliday; date: Date; daysOffset: number; }

// Look across [today … today+3] and return the FIRST hit (closest day)
const upcoming = computed<UpcomingHit | null>(() => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let offset = 0; offset <= 3; offset++) {
    const d = new Date(today);
    d.setDate(today.getDate() + offset);
    const h = getHoliday(d);
    if (h) return { holiday: h, date: d, daysOffset: offset };
  }
  return null;
});

function whenLabel(offset: number, d: Date): string {
  if (offset === 0) return "Сегодня";
  if (offset === 1) return "Завтра";
  if (offset === 2) return "Послезавтра";
  // 3 days → "Через 3 дня · day month"
  const fmt = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" });
  return `Через ${offset} дн. · ${fmt.format(d)}`;
}

const whenText = computed(() => {
  if (!upcoming.value) return "";
  return whenLabel(upcoming.value.daysOffset, upcoming.value.date);
});

const fullDate = computed(() => {
  if (!upcoming.value) return "";
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "long" }).format(upcoming.value.date);
});
</script>

<template>
  <div v-if="upcoming" class="th-root" :style="{ '--h-color': HOLIDAY_KIND_COLORS[upcoming.holiday.kind] }">
    <div class="th-icon">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="5" width="18" height="16" rx="2"/>
        <path d="M3 9h18"/>
        <path d="M8 3v4M16 3v4"/>
      </svg>
    </div>
    <div class="th-body">
      <div class="th-tag" :title="fullDate">{{ whenText }}</div>
      <div class="th-title">{{ upcoming.holiday.title_ru }}</div>
      <div class="th-meta">
        <span class="th-kind">{{ HOLIDAY_KIND_LABELS[upcoming.holiday.kind] }}</span>
        <span v-if="upcoming.holiday.is_dayoff" class="th-dayoff">нерабочий день</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Smooth conic-gradient angle interpolation для бегущей искры */
@property --spark-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}

.th-root {
  position: relative;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #fff;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  min-width: 360px;
  min-height: 72px;
  box-sizing: border-box;
  isolation: isolate;
  /* Distinctive entry — 3D flip-in + glow pulse */
  transform-style: preserve-3d;
  perspective: 800px;
  animation:
    thReveal 0.75s cubic-bezier(0.22, 1, 0.36, 1) 0.36s both,
    thGlow 2.6s ease-in-out 1.1s 2;
}

/* ═══ Тонкая UZ-флаг рамка вокруг виджета (2px) ═══
   Такой же linear-gradient(90deg) как у FlagSeparator, но обёрнут
   вокруг периметра через mask-trick — поддерживает border-radius.
   Top/Bottom: cyan|red|white|red|green слева направо
   Left edge:  solid cyan; Right edge: solid green */
.th-root::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 2px;
  background: linear-gradient(
    90deg,
    #0099B5 0%,    #0099B5 33%,
    #CE1126 33%,   #CE1126 33.5%,
    #FFFFFF 33.5%, #FFFFFF 66.5%,
    #CE1126 66.5%, #CE1126 67%,
    #1EB53A 67%,   #1EB53A 100%
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
          mask-composite: exclude;
  pointer-events: none;
  z-index: 1;
}

/* ═══ Animated sheen — белый блик пробегает по флаг-рамке циклически ═══ */
.th-root::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 2px;
  background: conic-gradient(
    from var(--spark-angle, 0deg),
    transparent 0deg,
    transparent 320deg,
    rgba(255, 255, 255, 0.0) 330deg,
    rgba(255, 255, 255, 0.85) 352deg,
    rgba(255, 255, 255, 0.0) 360deg
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
          mask-composite: exclude;
  animation: thFlagSheen 6s linear infinite;
  pointer-events: none;
  z-index: 2;
  mix-blend-mode: overlay;
}

@keyframes thFlagSheen {
  to { --spark-angle: 360deg; }
}

/* Содержимое над рамкой */
.th-root > * { position: relative; z-index: 3; }
@keyframes thReveal {
  0%   { opacity: 0; transform: perspective(800px) rotateX(-22deg) translateY(8px) scale(0.92); filter: blur(6px); }
  55%  { opacity: 1; transform: perspective(800px) rotateX(4deg)   translateY(-2px) scale(1.03); filter: blur(0); }
  100% { opacity: 1; transform: perspective(800px) rotateX(0deg)   translateY(0)    scale(1);    filter: blur(0); }
}
/* Soft glow pulse — 2 repeats после появления, потом затихает */
@keyframes thGlow {
  0%, 100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0); }
  50%      { box-shadow: 0 0 0 4px rgba(var(--h-glow-rgb, 255, 255, 255), 0.12), 0 4px 18px rgba(0, 0, 0, 0.20); }
}
.th-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.10);
  color: var(--h-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  filter: brightness(1.4);
}
.th-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.th-tag {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.45);
}
.th-title {
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}
.th-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
  font-size: 10.5px;
}
.th-kind {
  color: rgba(255, 255, 255, 0.65);
}
.th-dayoff {
  color: var(--h-color);
  font-weight: 600;
  filter: brightness(1.4);
}
</style>
