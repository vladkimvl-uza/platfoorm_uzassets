<template>
  <section class="wc">
    <div class="wc-aura" aria-hidden="true"></div>

    <header class="wc-head">
      <div class="wc-title">
        <span class="wc-cup">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/>
            <path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>
          </svg>
        </span>
        Чемпионат мира 2026
        <span class="wc-sub">Группа K · сборная Узбекистана — впервые на ЧМ</span>
      </div>
    </header>

    <div class="wc-grid">
      <!-- Таблица группы -->
      <div class="wc-table-card">
        <div class="wc-card-h">Турнирная таблица · Группа K</div>
        <div class="wc-thead">
          <span class="wc-th-pos">#</span>
          <span class="wc-th-team">Команда</span>
          <span class="wc-th-n" title="Игры">И</span>
          <span class="wc-th-n" title="Выигрыши">В</span>
          <span class="wc-th-n" title="Ничьи">Н</span>
          <span class="wc-th-n" title="Поражения">П</span>
          <span class="wc-th-gd" title="Голы">Голы</span>
          <span class="wc-th-pts" title="Очки">О</span>
        </div>
        <div
          v-for="(t, i) in standings"
          :key="t.code"
          class="wc-row"
          :class="{ 'wc-uz': t.code === 'UZB' }"
        >
          <span class="wc-pos">{{ i + 1 }}</span>
          <span class="wc-team">
            <span class="wc-code" :style="{ background: t.color + '22', color: t.color }">{{ t.code }}</span>
            {{ t.name }}
          </span>
          <span class="wc-n">{{ t.p }}</span>
          <span class="wc-n">{{ t.w }}</span>
          <span class="wc-n">{{ t.d }}</span>
          <span class="wc-n">{{ t.l }}</span>
          <span class="wc-gd">{{ t.gf }}:{{ t.ga }}</span>
          <span class="wc-pts">{{ t.pts }}</span>
        </div>
        <div class="wc-foot">Старт группового этапа — 17 июня 2026. Топ-2 + лучшие третьи выходят в плей-офф.</div>
      </div>

      <!-- Матчи сборной Узбекистана -->
      <div class="wc-uz-card">
        <div class="wc-card-h">
          <span class="wc-code wc-code-uz">UZB</span> Матчи сборной Узбекистана
        </div>
        <div
          v-for="m in uzMatches"
          :key="m.date"
          class="wc-match"
          :class="m.status"
        >
          <div class="wc-match-date">{{ m.dateLabel }}</div>
          <div class="wc-match-body">
            <span class="wc-side" :class="{ 'wc-side-uz': m.homeCode === 'UZB' }">
              <span class="wc-code-sm" :style="{ background: m.homeColor + '22', color: m.homeColor }">{{ m.homeCode }}</span>
              {{ m.home }}
            </span>
            <span class="wc-score">{{ m.score }}</span>
            <span class="wc-side wc-side-r" :class="{ 'wc-side-uz': m.awayCode === 'UZB' }">
              {{ m.away }}
              <span class="wc-code-sm" :style="{ background: m.awayColor + '22', color: m.awayColor }">{{ m.awayCode }}</span>
            </span>
          </div>
          <div class="wc-match-tag" :class="m.status">{{ m.statusLabel }}</div>
        </div>
        <div class="wc-foot wc-foot-note">
          Первое в истории участие · квалифицировались 5 июня 2025
        </div>
      </div>
    </div>

    <!-- Полное расписание Группы K -->
    <div class="wc-sched">
      <div class="wc-card-h">Расписание Группы K · все матчи</div>
      <div class="wc-sched-grid">
        <div v-for="md in schedule" :key="md.md" class="wc-md">
          <div class="wc-md-h">{{ md.md }}</div>
          <div
            v-for="m in md.matches"
            :key="m.h + m.a"
            class="wc-sm"
            :class="{ 'wc-sm-uz': m.uz }"
          >
            <span class="wc-sm-pair">
              <span class="wc-code-sm" :style="{ background: col(m.hc) + '22', color: col(m.hc) }">{{ m.hc }}</span>
              <span class="wc-sm-x">—</span>
              <span class="wc-code-sm" :style="{ background: col(m.ac) + '22', color: col(m.ac) }">{{ m.ac }}</span>
            </span>
            <span class="wc-sm-names">{{ m.h }} — {{ m.a }}</span>
            <span class="wc-sm-city">{{ m.city }}</span>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
// Источник: FIFA / Sky Sports / ESPN (Группа K ЧМ-2026). Результаты обновляются
// по ходу турнира — структура готова под живые счёта.
const C = { POR: "#C8102E", COL: "#FCD116", UZB: "#1EB53A", COD: "#007FFF" };

const standings = [
  { code: "POR", name: "Португалия", color: C.POR, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COL", name: "Колумбия",   color: C.COL, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "UZB", name: "Узбекистан", color: C.UZB, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
  { code: "COD", name: "ДР Конго",   color: C.COD, p: 0, w: 0, d: 0, l: 0, gf: 0, ga: 0, pts: 0 },
];

function col(code: string): string {
  return (C as Record<string, string>)[code] || "#888780";
}

const schedule = [
  { md: "1-й тур · 17 июня", matches: [
    { h: "Узбекистан", hc: "UZB", a: "Колумбия", ac: "COL", city: "Мехико · Ацтека", uz: true },
    { h: "Португалия", hc: "POR", a: "ДР Конго", ac: "COD", city: "Хьюстон", uz: false },
  ]},
  { md: "2-й тур · 23 июня", matches: [
    { h: "Португалия", hc: "POR", a: "Узбекистан", ac: "UZB", city: "Хьюстон", uz: true },
    { h: "Колумбия", hc: "COL", a: "ДР Конго", ac: "COD", city: "Гвадалахара", uz: false },
  ]},
  { md: "3-й тур · 27 июня", matches: [
    { h: "ДР Конго", hc: "COD", a: "Узбекистан", ac: "UZB", city: "Атланта", uz: true },
    { h: "Колумбия", hc: "COL", a: "Португалия", ac: "POR", city: "Майами", uz: false },
  ]},
];

const uzMatches = [
  {
    date: "2026-06-17", dateLabel: "17 июня · 1-й тур",
    home: "Узбекистан", homeCode: "UZB", homeColor: C.UZB,
    away: "Колумбия", awayCode: "COL", awayColor: C.COL,
    score: "— : —", status: "upcoming", statusLabel: "скоро",
  },
  {
    date: "2026-06-23", dateLabel: "23 июня · 2-й тур",
    home: "Португалия", homeCode: "POR", homeColor: C.POR,
    away: "Узбекистан", awayCode: "UZB", awayColor: C.UZB,
    score: "— : —", status: "upcoming", statusLabel: "скоро",
  },
  {
    date: "2026-06-27", dateLabel: "27 июня · 3-й тур",
    home: "ДР Конго", homeCode: "COD", homeColor: C.COD,
    away: "Узбекистан", awayCode: "UZB", awayColor: C.UZB,
    score: "— : —", status: "upcoming", statusLabel: "скоро",
  },
];
</script>

<style scoped>
.wc {
  position: relative;
  overflow: hidden;
  border-radius: 16px;
  padding: 18px 20px 16px;
  background: linear-gradient(135deg, #0E2A1A 0%, #12352b 50%, #1E2A4A 100%);
  color: #fff;
  box-shadow: 0 14px 40px rgba(15, 36, 26, 0.28);
}
.wc-aura {
  position: absolute; top: -30%; right: -8%;
  width: 360px; height: 360px;
  background: radial-gradient(circle, rgba(30, 181, 58, 0.4), transparent 62%);
  filter: blur(26px); pointer-events: none;
  animation: wc-aura 9s ease-in-out infinite;
}
@keyframes wc-aura { 0%,100%{opacity:.7;transform:scale(1);} 50%{opacity:1;transform:scale(1.14);} }

.wc-head { position: relative; z-index: 1; margin-bottom: 14px; }
.wc-title { display: flex; align-items: center; gap: 9px; font-size: 16px; font-weight: 500; letter-spacing: -.01em; flex-wrap: wrap; }
.wc-cup { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; background: rgba(252, 209, 22, .16); color: #FCD116; }
.wc-sub { font-size: 11.5px; color: rgba(255,255,255,.6); font-weight: 400; letter-spacing: 0; margin-left: 4px; }

.wc-grid {
  position: relative; z-index: 1;
  display: grid; grid-template-columns: 1.25fr 1fr; gap: 14px;
}
@media (max-width: 880px) { .wc-grid { grid-template-columns: 1fr; } }

.wc-table-card, .wc-uz-card {
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 13px;
  padding: 12px 13px;
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
}
.wc-card-h {
  display: flex; align-items: center; gap: 8px;
  font-size: 11px; text-transform: uppercase; letter-spacing: .06em;
  color: rgba(255,255,255,.62); margin-bottom: 10px;
}

/* Таблица */
.wc-thead, .wc-row {
  display: grid;
  grid-template-columns: 20px 1fr 22px 22px 22px 22px 46px 26px;
  align-items: center; gap: 4px;
}
.wc-thead { font-size: 9.5px; color: rgba(255,255,255,.45); padding: 0 6px 7px; border-bottom: 1px solid rgba(255,255,255,.08); }
.wc-th-n, .wc-th-gd, .wc-th-pts { text-align: center; }
.wc-th-team { padding-left: 2px; }
.wc-row {
  font-size: 12.5px; padding: 8px 6px; border-radius: 8px;
  transition: background .15s; font-variant-numeric: tabular-nums;
}
.wc-row:hover { background: rgba(255,255,255,.05); }
.wc-uz {
  background: linear-gradient(90deg, rgba(30,181,58,.20), rgba(30,181,58,.06));
  border: 1px solid rgba(30,181,58,.4);
}
.wc-pos { color: rgba(255,255,255,.5); text-align: center; font-size: 11px; }
.wc-team { display: flex; align-items: center; gap: 8px; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.wc-code, .wc-code-sm { font-size: 9px; font-weight: 700; letter-spacing: .03em; padding: 2px 5px; border-radius: 5px; flex-shrink: 0; }
.wc-code-uz { background: rgba(30,181,58,.26); color: #6EE7A0; }
.wc-n, .wc-pts { text-align: center; }
.wc-pts { font-weight: 600; }
.wc-uz .wc-pts { color: #6EE7A0; }
.wc-gd { text-align: center; color: rgba(255,255,255,.7); font-size: 11.5px; }
.wc-foot { margin-top: 10px; font-size: 10px; color: rgba(255,255,255,.42); line-height: 1.4; }

/* Матчи UZ */
.wc-match {
  display: flex; flex-direction: column; gap: 5px;
  padding: 10px 11px; margin-bottom: 7px;
  border-radius: 10px;
  background: rgba(255,255,255,.04);
  border-left: 3px solid rgba(30,181,58,.5);
}
.wc-match-date { font-size: 10px; color: rgba(255,255,255,.5); text-transform: uppercase; letter-spacing: .04em; }
.wc-match-body { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.wc-side { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
.wc-side-r { justify-content: flex-end; text-align: right; }
.wc-side-uz { font-weight: 600; color: #6EE7A0; }
.wc-score { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; color: rgba(255,255,255,.85); padding: 0 4px; white-space: nowrap; }
.wc-match-tag {
  align-self: flex-start; font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em;
  padding: 2px 8px; border-radius: 999px;
}
.wc-match-tag.upcoming { background: rgba(252,209,22,.16); color: #FCD116; }
.wc-match-tag.live { background: rgba(226,75,74,.2); color: #FCA5A5; }
.wc-match-tag.done { background: rgba(30,181,58,.18); color: #6EE7A0; }
.wc-foot-note { color: rgba(110,231,160,.6); }

/* Расписание группы */
.wc-sched {
  position: relative; z-index: 1;
  margin-top: 14px;
  background: rgba(255,255,255,.05);
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 13px;
  padding: 12px 13px;
}
.wc-sched-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 880px) { .wc-sched-grid { grid-template-columns: 1fr; } }
.wc-md-h {
  font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em;
  color: #FCD116; margin-bottom: 8px;
}
.wc-sm {
  display: flex; flex-direction: column; gap: 3px;
  padding: 8px 10px; margin-bottom: 6px;
  border-radius: 9px; background: rgba(255,255,255,.04);
}
.wc-sm-uz { background: rgba(30,181,58,.12); border: 1px solid rgba(30,181,58,.3); }
.wc-sm-pair { display: flex; align-items: center; gap: 6px; }
.wc-sm-x { color: rgba(255,255,255,.4); font-size: 10px; }
.wc-sm-names { font-size: 12px; color: rgba(255,255,255,.88); }
.wc-sm-uz .wc-sm-names { color: #6EE7A0; font-weight: 600; }
.wc-sm-city { font-size: 9.5px; color: rgba(255,255,255,.42); }

@media (prefers-reduced-motion: reduce) { .wc-aura { animation: none; } }
</style>
