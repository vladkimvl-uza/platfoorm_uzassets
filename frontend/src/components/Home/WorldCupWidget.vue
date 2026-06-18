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

      <!-- Все матчи группы — ежедневное расписание и результаты -->
      <div class="wc-col">
        <div class="wc-col-h">Расписание · все матчи группы K</div>
        <div v-for="g in matchesByDay" :key="g.day" class="wc-day">
          <div class="wc-day-h">{{ g.day }}</div>
          <div v-for="(m, i) in g.items" :key="g.day + '-' + i" class="wc-match" :class="{ 'wc-match-uz': m.uz }">
            <div class="wc-m-line" :class="{ 'wc-m-uz': m.h === 'Узбекистан' }">
              <img class="wc-fl" :src="flagUrl(m.hcc)" :alt="m.h" width="18" height="13" />
              <span class="wc-m-team">{{ m.h }}</span>
              <span class="wc-m-score">{{ splitScore(m.score).h }}</span>
            </div>
            <div class="wc-m-line" :class="{ 'wc-m-uz': m.a === 'Узбекистан' }">
              <img class="wc-fl" :src="flagUrl(m.acc)" :alt="m.a" width="18" height="13" />
              <span class="wc-m-team">{{ m.a }}</span>
              <span class="wc-m-score">{{ splitScore(m.score).a }}</span>
            </div>
            <div v-if="m.time" class="wc-m-time">{{ m.time }}</div>
          </div>
        </div>
        <div class="wc-note">Время начала — по Ташкенту (UTC+5)</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from "vue";
import { api } from "@/api/client";
// Группа K ЧМ-2026. Данные — live из /worldcup/groupk (football-data.org по
// ключу на бэке), с фолбэком на статику. Флаги — flagcdn.
const emit = defineEmits<{ hide: [] }>();
function flagUrl(cc: string): string { return `https://flagcdn.com/w40/${cc}.png`; }
// Счёт "H : A" → отдельные стороны (для вертикальной раскладки матча).
function splitScore(s: string): { h: string; a: string } {
  const parts = (s || "").split(":");
  return { h: (parts[0] || "—").trim(), a: (parts[1] || "—").trim() };
}

const standings = ref([
  { code: "POR", cc: "pt", name: "Португалия", p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COL", cc: "co", name: "Колумбия",   p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "UZB", cc: "uz", name: "Узбекистан", p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COD", cc: "cd", name: "ДР Конго",   p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
]);
type WcMatch = { matchday?: number; day: string; time: string; h: string; hcc: string; a: string; acc: string; score: string; uz: boolean };
const uzMatches = ref([
  { date: "18 июня · 07:00", h: "Узбекистан", hcc: "uz", a: "Колумбия",   acc: "co", score: "— : —" },
  { date: "23 июня · 22:00", h: "Португалия", hcc: "pt", a: "Узбекистан", acc: "uz", score: "— : —" },
  { date: "28 июня · 04:30", h: "ДР Конго",   hcc: "cd", a: "Узбекистан", acc: "uz", score: "— : —" },
]);
// Все 6 матчей группы (3 тура × 2). Время «соседних» матчей придёт из live.
const matches = ref<WcMatch[]>([
  { matchday: 1, day: "18 июня", time: "07:00", h: "Узбекистан", hcc: "uz", a: "Колумбия",   acc: "co", score: "— : —", uz: true },
  { matchday: 1, day: "18 июня", time: "",      h: "Португалия", hcc: "pt", a: "ДР Конго",   acc: "cd", score: "— : —", uz: false },
  { matchday: 2, day: "23 июня", time: "22:00", h: "Португалия", hcc: "pt", a: "Узбекистан", acc: "uz", score: "— : —", uz: true },
  { matchday: 2, day: "23 июня", time: "",      h: "Колумбия",   hcc: "co", a: "ДР Конго",   acc: "cd", score: "— : —", uz: false },
  { matchday: 3, day: "28 июня", time: "04:30", h: "ДР Конго",   hcc: "cd", a: "Узбекистан", acc: "uz", score: "— : —", uz: true },
  { matchday: 3, day: "28 июня", time: "",      h: "Колумбия",   hcc: "co", a: "Португалия", acc: "pt", score: "— : —", uz: false },
]);
const isLive = ref(false);

// Группировка матчей по дню — для ежедневного расписания.
const matchesByDay = computed(() => {
  const out: { day: string; items: WcMatch[] }[] = [];
  const idx: Record<string, number> = {};
  for (const m of matches.value) {
    const key = m.day || "—";
    if (!(key in idx)) { idx[key] = out.length; out.push({ day: key, items: [] }); }
    out[idx[key]].items.push(m);
  }
  return out;
});

// Победа Узбекистана в любом сыгранном матче → салют.
const uzWon = computed(() => matches.value.some((m) => {
  if (!m.uz) return false;
  const mm = m.score.match(/(\d+)\s*:\s*(\d+)/);
  if (!mm) return false;
  const hs = Number(mm[1]), as = Number(mm[2]);
  return (m.h === "Узбекистан" && hs > as) || (m.a === "Узбекистан" && as > hs);
}));
const sparks = Array.from({ length: 32 }, (_, i) => ({
  i, angle: (i * 137.5) % 360,
  dist: 54 + (i % 5) * 16,
  delay: (i % 8) * 0.06,
  color: ["#1EB53A", "#0099FF", "#ffffff", "#FCD116"][i % 4],
}));

let _timer: number | null = null;
async function loadLive() {
  try {
    const { data } = await api.get("/worldcup/groupk");
    if (Array.isArray(data?.standings) && data.standings.length) standings.value = data.standings;
    if (Array.isArray(data?.uz_matches) && data.uz_matches.length) uzMatches.value = data.uz_matches;
    if (Array.isArray(data?.matches) && data.matches.length) matches.value = data.matches;
    isLive.value = !!data?.live;
  } catch { /* оставляем фолбэк */ }
}
onMounted(() => {
  loadLive();
  _timer = window.setInterval(loadLive, 5 * 60 * 1000); // обновление раз в 5 мин
});
onBeforeUnmount(() => { if (_timer) clearInterval(_timer); });
</script>

<style scoped>
.wc {
  position: relative; overflow: hidden;
  width: 500px; max-width: 100%; flex-shrink: 0;
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
  animation: wc-ball-roll 2.2s cubic-bezier(.3,.7,.5,1) .12s both;
}
.wc-spin {
  display: inline-block; filter: drop-shadow(0 2px 4px rgba(0,0,0,.3));
  animation: wc-ball-spin 2.2s linear .12s both;
}
@keyframes wc-ball-spin { from { transform: rotate(0); } to { transform: rotate(1440deg); } }
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
.wc-col { min-width: 0; }  /* чтобы колонки делились честно, без min-content давления */
@media (max-width: 520px) { .wc-body { grid-template-columns: 1fr; } }

.wc-col-h {
  display: flex; align-items: center; gap: 6px;
  font-size: 9.5px; text-transform: uppercase; letter-spacing: .06em;
  color: rgba(255,255,255,.5); margin-bottom: 8px;
}

/* Таблица */
.wc-thead, .wc-trow {
  display: grid;
  grid-template-columns: 1fr 15px 15px 15px 15px 28px 16px;
  align-items: center; gap: 2px;
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

/* Дневное расписание / матчи */
.wc-day { margin-bottom: 8px; }
.wc-day-h {
  font-size: 9.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  color: rgba(255,255,255,.62); padding: 0 2px 4px;
}
.wc-match {
  position: relative;
  padding: 6px 9px; margin-bottom: 5px;
  border-radius: 9px;
  background: rgba(255,255,255,.04);
  border-left: 2.5px solid rgba(255,255,255,.12);
}
/* Матч сборной Узбекистана — зелёный акцент */
.wc-match-uz {
  background: rgba(30,181,58,.10);
  border-left-color: rgba(30,181,58,.55);
}
.wc-m-date { font-size: 9.5px; color: rgba(255,255,255,.48); text-transform: uppercase; letter-spacing: .03em; margin-bottom: 5px; }
.wc-m-line { display: flex; align-items: center; gap: 8px; font-size: 11.5px; padding: 2px 0; }
.wc-m-team { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wc-m-score { flex-shrink: 0; min-width: 16px; text-align: right; font-size: 12.5px; font-weight: 600; color: rgba(255,255,255,.82); font-variant-numeric: tabular-nums; white-space: nowrap; }
.wc-m-uz .wc-m-team { color: #6EE7A0; font-weight: 600; }
.wc-m-time { position: absolute; top: 6px; right: 9px; font-size: 9px; color: rgba(255,255,255,.4); font-variant-numeric: tabular-nums; }
</style>
