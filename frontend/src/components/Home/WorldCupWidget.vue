<template>
  <div class="wc">
    <!-- Футбольный мяч + шлейф флага Узбекистана — прокат при раскрытии -->
    <span class="wc-ball" aria-hidden="true">
      <i class="wc-trail"></i>
      <span class="wc-spin">
        <svg viewBox="0 0 24 24" width="22" height="22">
          <circle cx="12" cy="12" r="11" fill="#fff" stroke="#1E2A4A" stroke-width="1"/>
          <polygon points="12,7 15,9.2 13.8,12.8 10.2,12.8 9,9.2" fill="#1E2A4A"/>
          <path d="M12 1.2v4M3.2 8l3.6 1.3M20.8 8l-3.6 1.3M6 21l1.2-4M18 21l-1.2-4"
                stroke="#1E2A4A" stroke-width="1" fill="none"/>
        </svg>
      </span>
    </span>

    <!-- Салют при победе Узбекистана -->
    <div v-if="uzWon" class="wc-salute" aria-hidden="true">
      <span
        v-for="s in sparks" :key="s.i" class="wc-spark"
        :style="{
          '--ang': s.angle + 'deg', '--dist': s.dist + 'px',
          '--delay': s.delay + 's', '--c': s.color,
        }"
      ></span>
    </div>

    <div class="wc-head">
      <img class="wc-fl wc-fl-lg" :src="flagUrl('uz')" alt="UZ" width="22" height="16" />
      <div class="wc-h-txt">
        <div class="wc-h-title">Чемпионат мира 2026</div>
        <div class="wc-h-sub">Группа K · впервые в истории</div>
      </div>
      <button class="wc-hide" type="button" title="Скрыть модуль" aria-label="Скрыть" @click="emit('hide')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M18 6L6 18M6 6l12 12"/>
        </svg>
      </button>
    </div>

    <div class="wc-body">
      <!-- Таблица группы -->
      <div class="wc-col">
        <div class="wc-col-h">Таблица · Группа K</div>
        <div class="wc-thead">
          <span class="wc-c-team">Команда</span>
          <span>И</span><span>В</span><span>Н</span><span>П</span>
          <span class="wc-c-gd">Голы</span><span class="wc-c-pts">О</span>
        </div>
        <div
          v-for="t in standings"
          :key="t.code"
          class="wc-trow"
          :class="{ 'wc-uz': t.code === 'UZB' }"
        >
          <span class="wc-c-team"><img class="wc-fl" :src="flagUrl(t.cc)" :alt="t.code" width="18" height="13" />{{ t.name }}</span>
          <span>{{ t.p }}</span><span>{{ t.w }}</span><span>{{ t.d }}</span><span>{{ t.l }}</span>
          <span class="wc-c-gd">{{ t.gf }}:{{ t.ga }}</span><span class="wc-c-pts">{{ t.pts }}</span>
        </div>
      </div>

      <!-- Матчи сборной Узбекистана -->
      <div class="wc-col">
        <div class="wc-col-h"><img class="wc-fl" :src="flagUrl('uz')" alt="UZ" width="16" height="12" /> Матчи Узбекистана</div>
        <div v-for="m in uzMatches" :key="m.date" class="wc-match">
          <div class="wc-m-date">{{ m.date }}</div>
          <div class="wc-m-row">
            <img class="wc-fl" :src="flagUrl(m.hcc)" :alt="m.h" width="18" height="13" />
            <span class="wc-m-team" :class="{ 'wc-m-uz': m.h === 'Узбекистан' }">{{ m.h }}</span>
            <span class="wc-m-score">{{ m.score }}</span>
            <span class="wc-m-team wc-m-r" :class="{ 'wc-m-uz': m.a === 'Узбекистан' }">{{ m.a }}</span>
            <img class="wc-fl" :src="flagUrl(m.acc)" :alt="m.a" width="18" height="13" />
          </div>
        </div>
        <div class="wc-note">Время начала — по Ташкенту (UTC+5)</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
// Группа K ЧМ-2026 (FIFA / Sky Sports). Счёта статичные — обновляются вручную/
// через API. Флаги — flagcdn (alt-код показывается, если CDN недоступен).
const emit = defineEmits<{ hide: [] }>();
function flagUrl(cc: string): string { return `https://flagcdn.com/w40/${cc}.png`; }

// Победа Узбекистана в любом сыгранном матче → салют.
const uzWon = computed(() => uzMatches.some((m) => {
  const mm = m.score.match(/(\d+)\s*:\s*(\d+)/);
  if (!mm) return false;
  const [hs, as] = [Number(mm[1]), Number(mm[2])];
  return (m.h === "Узбекистан" && hs > as) || (m.a === "Узбекистан" && as > hs);
}));
// Искры салюта (цвета флага Узбекистана + золото)
const sparks = Array.from({ length: 32 }, (_, i) => ({
  i, angle: (i * 137.5) % 360,
  dist: 54 + (i % 5) * 16,
  delay: (i % 8) * 0.06,
  color: ["#1EB53A", "#0099FF", "#ffffff", "#FCD116"][i % 4],
}));

const standings = [
  { code: "POR", cc: "pt", name: "Португалия", p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COL", cc: "co", name: "Колумбия",   p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "UZB", cc: "uz", name: "Узбекистан", p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COD", cc: "cd", name: "ДР Конго",   p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
];

const uzMatches = [
  { date: "18 июня · 07:00", h: "Узбекистан", hcc: "uz", a: "Колумбия",   acc: "co", score: "— : —" },
  { date: "23 июня · 22:00", h: "Португалия", hcc: "pt", a: "Узбекистан", acc: "uz", score: "— : —" },
  { date: "28 июня · 04:30", h: "ДР Конго",   hcc: "cd", a: "Узбекистан", acc: "uz", score: "— : —" },
];
</script>

<style scoped>
.wc {
  position: relative; overflow: hidden;
  background: rgba(22, 34, 58, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  padding: 14px 16px;
  color: rgba(255, 255, 255, 0.92);
  display: flex; flex-direction: column;
}

/* Футбольный мяч — прокат при раскрытии (позиция, без вращения) */
.wc-ball {
  position: absolute; top: 9px; left: -30px; z-index: 3; pointer-events: none;
  animation: wc-ball-roll 1.15s var(--ease-standard, cubic-bezier(.34,1.05,.6,1)) .12s both;
}
.wc-spin {
  display: inline-block; filter: drop-shadow(0 2px 4px rgba(0,0,0,.3));
  animation: wc-ball-spin 1.15s linear .12s both;
}
@keyframes wc-ball-spin { from { transform: rotate(0); } to { transform: rotate(1080deg); } }
/* Шлейф — развевающийся флаг Узбекистана, следует за мячом, НЕ вращается */
.wc-trail {
  position: absolute; right: 11px; top: 50%; transform: translateY(-50%);
  width: 64px; height: 13px; border-radius: 0 7px 7px 0;
  background: linear-gradient(180deg, #0099FF 0 33.3%, #fff 33.3% 66.6%, #1EB53A 66.6% 100%);
  -webkit-mask: linear-gradient(90deg, transparent 2%, #000 88%);
          mask: linear-gradient(90deg, transparent 2%, #000 88%);
  opacity: .82; z-index: -1; transform-origin: right center;
  animation: wc-trail-wave .42s ease-in-out infinite;
}
@keyframes wc-trail-wave {
  0%, 100% { transform: translateY(-50%) skewX(0) scaleY(1); }
  35%      { transform: translateY(-54%) skewX(7deg) scaleY(.9); }
  70%      { transform: translateY(-46%) skewX(-5deg) scaleY(1.06); }
}
@keyframes wc-ball-roll {
  0%   { transform: translateX(0); opacity: 0; }
  12%  { opacity: 1; }
  88%  { opacity: 1; }
  100% { transform: translateX(560px); opacity: 0; }
}

/* Салют при победе Узбекистана */
.wc-salute { position: absolute; inset: 0; z-index: 4; pointer-events: none; }
.wc-spark {
  position: absolute; top: 36%; left: 50%;
  width: 5px; height: 5px; border-radius: 50%;
  background: var(--c); box-shadow: 0 0 7px var(--c);
  animation: wc-spark 1.5s ease-out var(--delay) infinite;
}
@keyframes wc-spark {
  0%   { opacity: 0; transform: rotate(var(--ang)) translateY(0) scale(.4); }
  14%  { opacity: 1; }
  100% { opacity: 0; transform: rotate(var(--ang)) translateY(calc(var(--dist) * -1)) scale(1); }
}

/* Премиум-волна флага Узбекистана в шапке */
.wc-fl-lg { animation: wc-flag-wave 2.8s ease-in-out infinite; transform-origin: left center; }
@keyframes wc-flag-wave {
  0%, 100% { transform: skewX(0) scaleX(1); }
  35%      { transform: skewX(-7deg) scaleX(.97); }
  70%      { transform: skewX(4deg) scaleX(1); }
}

@media (prefers-reduced-motion: reduce) {
  .wc-ball, .wc-spark, .wc-fl-lg { animation: none !important; }
  .wc-ball { display: none; }
}
.wc-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.wc-h-txt { flex: 1; min-width: 0; }
.wc-h-title { font-size: 13px; font-weight: 500; letter-spacing: -.01em; }
.wc-h-sub { font-size: 10.5px; color: rgba(255,255,255,.5); margin-top: 1px; }
.wc-hide {
  flex-shrink: 0; width: 24px; height: 24px; border-radius: 7px;
  border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.05);
  color: rgba(255,255,255,.55); display: grid; place-items: center; cursor: pointer;
  transition: all .14s;
}
.wc-hide:hover { background: rgba(255,255,255,.14); color: #fff; }
.wc-fl {
  border-radius: 2px; object-fit: cover; flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(0,0,0,.18);
  vertical-align: middle;
}
.wc-fl-lg { border-radius: 3px; }
.wc-note { margin-top: 9px; font-size: 9px; color: rgba(255,255,255,.38); }

.wc-body { display: grid; grid-template-columns: 1.3fr 1fr; gap: 16px; }
@media (max-width: 520px) { .wc-body { grid-template-columns: 1fr; } }

.wc-col-h {
  display: flex; align-items: center; gap: 6px;
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .06em;
  color: rgba(255,255,255,.5); margin-bottom: 8px;
}

/* Таблица */
.wc-thead, .wc-trow {
  display: grid;
  grid-template-columns: 1fr 16px 16px 16px 16px 30px 18px;
  align-items: center; gap: 3px;
  font-variant-numeric: tabular-nums;
}
.wc-thead { font-size: 9px; color: rgba(255,255,255,.4); padding: 0 5px 6px; }
.wc-thead > span:not(.wc-c-team):not(.wc-c-gd):not(.wc-c-pts),
.wc-trow > span:not(.wc-c-team):not(.wc-c-gd):not(.wc-c-pts) { text-align: center; }
.wc-c-gd { text-align: center; }
.wc-c-pts { text-align: center; font-weight: 600; }
.wc-trow { font-size: 11.5px; padding: 6px 5px; border-radius: 7px; }
.wc-trow:not(.wc-uz) + .wc-trow:not(.wc-uz),
.wc-trow { border-top: 1px solid rgba(255,255,255,.05); }
.wc-c-team { display: flex; align-items: center; gap: 7px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wc-fl { font-size: 14px; line-height: 1; flex-shrink: 0; }
.wc-uz {
  background: rgba(30, 181, 58, .14);
  border: 1px solid rgba(30, 181, 58, .34);
}
.wc-uz .wc-c-team, .wc-uz .wc-c-pts { color: #6EE7A0; font-weight: 600; }

/* Матчи UZ */
.wc-match {
  padding: 7px 9px; margin-bottom: 6px;
  border-radius: 9px;
  background: rgba(255,255,255,.04);
  border-left: 2.5px solid rgba(30,181,58,.45);
}
.wc-m-date { font-size: 9.5px; color: rgba(255,255,255,.48); text-transform: uppercase; letter-spacing: .03em; margin-bottom: 3px; }
.wc-m-row { display: flex; align-items: center; gap: 6px; font-size: 11.5px; }
.wc-m-team { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wc-m-r { text-align: right; }
.wc-m-uz { color: #6EE7A0; font-weight: 600; }
.wc-m-score { font-size: 12px; font-weight: 600; color: rgba(255,255,255,.8); font-variant-numeric: tabular-nums; white-space: nowrap; }
</style>
