<template>
  <div class="cmd">
    <div class="cmd-aura" aria-hidden="true"></div>

    <!-- Header -->
    <header class="cmd-top">
      <div class="cmd-brand">
        <EptLogo :size="40" />
        <div>
          <div class="cmd-brand-t">UzAssets · Командный центр</div>
          <div class="cmd-brand-s">Портфель 22 предприятий · {{ year }}</div>
        </div>
      </div>
      <div class="cmd-clock">
        <div class="cmd-time">{{ clock }}</div>
        <div class="cmd-date">{{ dateStr }}</div>
      </div>
      <button class="cmd-exit" @click="exit" title="Выйти (Esc)">✕</button>
    </header>

    <!-- Panels -->
    <main class="cmd-stage">
      <transition name="cmd-panel" mode="out-in">
        <!-- 1. Обзор портфеля -->
        <section v-if="panel === 0" key="p0" class="cmd-panel">
          <div class="cmd-panel-h">Обзор портфеля</div>
          <div class="cmd-kpis">
            <div class="cmd-kpi">
              <div class="cmd-kpi-v">{{ tProjects }}</div>
              <div class="cmd-kpi-l">проектов</div>
            </div>
            <div class="cmd-kpi">
              <div class="cmd-kpi-v">{{ tTasks }}</div>
              <div class="cmd-kpi-l">задач</div>
            </div>
            <div class="cmd-kpi cmd-kpi-accent">
              <div class="cmd-kpi-v">{{ tDone }}<span class="cmd-kpi-pct">%</span></div>
              <div class="cmd-kpi-l">выполнение</div>
            </div>
            <div class="cmd-kpi" :class="{ 'cmd-kpi-danger': overdue > 0 }">
              <div class="cmd-kpi-v">{{ tOverdue }}</div>
              <div class="cmd-kpi-l">просрочено</div>
            </div>
          </div>
          <div class="cmd-bars">
            <div v-for="s in statuses" :key="s.id" class="cmd-bar-row">
              <span class="cmd-bar-dot" :style="{ background: s.color }"></span>
              <span class="cmd-bar-l">{{ s.label }}</span>
              <div class="cmd-bar-track"><span :style="{ width: barPct(s) + '%', background: s.color }"></span></div>
              <span class="cmd-bar-v">{{ s.tasks_count }}</span>
            </div>
          </div>
        </section>

        <!-- 2. Требует внимания -->
        <section v-else-if="panel === 1" key="p1" class="cmd-panel">
          <div class="cmd-panel-h">Требует внимания</div>
          <div v-if="insights.length" class="cmd-attn">
            <div v-for="it in insights" :key="it.id" class="cmd-attn-row" :class="`sev-${it.severity}`">
              <span class="cmd-attn-c">{{ it.count }}</span>
              <span class="cmd-attn-t">
                <span class="cmd-attn-title">{{ it.title }}</span>
                <span class="cmd-attn-d">{{ it.detail }}</span>
              </span>
            </div>
          </div>
          <div v-else class="cmd-clear">✓ Всё под контролем — критичных сигналов нет</div>
        </section>

        <!-- 3. Лидеры и отстающие -->
        <section v-else-if="panel === 2" key="p2" class="cmd-panel">
          <div class="cmd-panel-h">Выполнение по компаниям</div>
          <div class="cmd-cols">
            <div class="cmd-col">
              <div class="cmd-col-h cmd-col-up">▲ Лидеры</div>
              <div v-for="c in leaders" :key="c.code" class="cmd-co">
                <span class="cmd-co-n">{{ c.name }}</span>
                <span class="cmd-co-v" style="color:#6EE7B7">{{ c.progress_pct }}%</span>
              </div>
            </div>
            <div class="cmd-col">
              <div class="cmd-col-h cmd-col-dn">▼ Отстающие</div>
              <div v-for="c in laggards" :key="c.code" class="cmd-co">
                <span class="cmd-co-n">{{ c.name }}</span>
                <span class="cmd-co-v" style="color:#FCA5A5">{{ c.progress_pct }}%</span>
              </div>
            </div>
          </div>
        </section>

        <!-- 4. Рейтинги -->
        <section v-else key="p3" class="cmd-panel">
          <div class="cmd-panel-h">Покрытие рейтингами</div>
          <div class="cmd-rings">
            <div v-for="r in rings" :key="r.agency" class="cmd-ring">
              <div class="cmd-ring-v" :style="{ color: r.color }">{{ r.pct }}<span>%</span></div>
              <div class="cmd-ring-l">{{ r.label }}</div>
              <div class="cmd-ring-sub">{{ r.covered }}/{{ r.total }}</div>
            </div>
          </div>
        </section>
      </transition>
    </main>

    <!-- Footer dots -->
    <footer class="cmd-dots">
      <button v-for="i in 4" :key="i" class="cmd-dot" :class="{ on: panel === i - 1 }" @click="setPanel(i - 1)"></button>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { usePortfolioYearStore } from "@/stores/portfolioYear";
import { useNumberTween } from "@/composables/useNumberTween";
import EptLogo from "@/components/EptLogo.vue";

const router = useRouter();
const yearStore = usePortfolioYearStore();
const year = computed(() => yearStore.year || 2026);

const data = ref<any>(null);
const insights = ref<any[]>([]);
const panel = ref(0);

const projects = computed(() => data.value?.kpis?.projects || 0);
const tasks = computed(() => data.value?.kpis?.tasks || 0);
const doneTasks = computed(() => data.value?.kpis?.done_tasks || 0);
const overdue = computed(() => data.value?.kpis?.overdue_tasks || 0);
const donePct = computed(() => tasks.value ? Math.round(doneTasks.value / tasks.value * 100) : 0);
const statuses = computed(() => (data.value?.statuses || []).filter((s: any) => s.id !== "overdue").slice(0, 5));

const _tProjects = useNumberTween(projects, { duration: 1000 });
const _tTasks = useNumberTween(tasks, { duration: 1000 });
const _tDone = useNumberTween(donePct, { duration: 1000 });
const _tOverdue = useNumberTween(overdue, { duration: 1000 });
const tProjects = computed(() => Math.round(_tProjects.value));
const tTasks = computed(() => Math.round(_tTasks.value));
const tDone = computed(() => Math.round(_tDone.value));
const tOverdue = computed(() => Math.round(_tOverdue.value));

const allCompanies = computed(() => {
  const out: any[] = [];
  for (const g of (data.value?.companies_by_sector || [])) for (const c of g.companies) out.push(c);
  return out;
});
const leaders = computed(() => [...allCompanies.value].sort((a, b) => b.progress_pct - a.progress_pct).slice(0, 6));
const laggards = computed(() => [...allCompanies.value].sort((a, b) => a.progress_pct - b.progress_pct).slice(0, 6));
const rings = computed(() => data.value?.ratings?.rings || []);

function barPct(s: any): number {
  const max = Math.max(...statuses.value.map((x: any) => x.tasks_count), 1);
  return Math.round((s.tasks_count / max) * 100);
}

const clock = ref("");
const dateStr = ref("");
let clockTimer: any = null;
let rotateTimer: any = null;
let refreshTimer: any = null;

function tick() {
  const d = new Date();
  clock.value = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  dateStr.value = d.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" });
}
function setPanel(i: number) {
  panel.value = i;
  restartRotate();
}
function restartRotate() {
  if (rotateTimer) clearInterval(rotateTimer);
  rotateTimer = setInterval(() => { panel.value = (panel.value + 1) % 4; }, 12000);
}
function exit() { router.back(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") exit(); }

async function load() {
  try {
    const params: any = {};
    if (year.value) params.year = year.value;
    const [d, ins] = await Promise.all([
      api.get("/dashboard/shareholder", { params }),
      api.get("/insights/attention").catch(() => ({ data: { items: [] } })),
    ]);
    data.value = d.data;
    insights.value = ins.data?.items || [];
  } catch { /* keep previous */ }
}

onMounted(() => {
  tick();
  clockTimer = setInterval(tick, 1000);
  restartRotate();
  load();
  refreshTimer = setInterval(load, 60000);
  window.addEventListener("keydown", onKey);
});
onBeforeUnmount(() => {
  clearInterval(clockTimer); clearInterval(rotateTimer); clearInterval(refreshTimer);
  window.removeEventListener("keydown", onKey);
});
</script>

<style scoped>
.cmd {
  position: fixed; inset: 0; z-index: 50;
  display: flex; flex-direction: column;
  background: radial-gradient(120% 100% at 50% 0%, #2A2065 0%, #1E2A4A 45%, #131A30 100%);
  color: #fff; overflow: hidden;
  font-feature-settings: "tnum";
}
.cmd-aura {
  position: absolute; top: -20%; left: 50%; transform: translateX(-50%);
  width: 900px; height: 600px;
  background: radial-gradient(circle, rgba(127,119,221,.4), transparent 60%);
  filter: blur(40px); pointer-events: none;
  animation: cmd-aura 12s ease-in-out infinite;
}
@keyframes cmd-aura { 0%,100%{opacity:.7;transform:translateX(-50%) scale(1);} 50%{opacity:1;transform:translateX(-50%) scale(1.15);} }

.cmd-top {
  position: relative; z-index: 1;
  display: flex; align-items: center; justify-content: space-between;
  padding: 22px 34px;
  border-bottom: 1px solid rgba(255,255,255,.08);
}
.cmd-brand { display: flex; align-items: center; gap: 14px; }
.cmd-brand-t { font-size: 17px; font-weight: 500; letter-spacing: -.01em; }
.cmd-brand-s { font-size: 12px; color: rgba(255,255,255,.55); margin-top: 2px; }
.cmd-clock { text-align: center; }
.cmd-time { font-size: 30px; font-weight: 300; letter-spacing: .02em; font-variant-numeric: tabular-nums; }
.cmd-date { font-size: 12px; color: rgba(255,255,255,.55); text-transform: capitalize; }
.cmd-exit {
  width: 38px; height: 38px; border-radius: 10px; border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.06); color: rgba(255,255,255,.7); font-size: 16px; cursor: pointer;
  transition: all .15s;
}
.cmd-exit:hover { background: rgba(255,255,255,.14); color: #fff; }

.cmd-stage { position: relative; z-index: 1; flex: 1; display: flex; padding: 30px 44px; }
.cmd-panel { flex: 1; display: flex; flex-direction: column; }
.cmd-panel-h {
  font-size: 13px; text-transform: uppercase; letter-spacing: .12em;
  color: rgba(255,255,255,.5); margin-bottom: 22px;
}

/* KPIs */
.cmd-kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; margin-bottom: 30px; }
.cmd-kpi {
  padding: 26px 24px; border-radius: 18px;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.09);
  -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
}
.cmd-kpi-accent { background: linear-gradient(135deg, rgba(127,119,221,.28), rgba(83,74,183,.14)); border-color: rgba(127,119,221,.4); }
.cmd-kpi-danger { background: linear-gradient(135deg, rgba(226,75,74,.25), rgba(226,75,74,.08)); border-color: rgba(226,75,74,.4); }
.cmd-kpi-v { font-size: 58px; font-weight: 300; letter-spacing: -.03em; line-height: 1; font-variant-numeric: tabular-nums; }
.cmd-kpi-pct { font-size: 28px; color: rgba(255,255,255,.55); margin-left: 4px; }
.cmd-kpi-l { margin-top: 10px; font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: rgba(255,255,255,.55); }

.cmd-bars { display: flex; flex-direction: column; gap: 12px; }
.cmd-bar-row { display: flex; align-items: center; gap: 12px; }
.cmd-bar-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.cmd-bar-l { width: 160px; font-size: 14px; color: rgba(255,255,255,.8); }
.cmd-bar-track { flex: 1; height: 8px; border-radius: 5px; background: rgba(255,255,255,.08); overflow: hidden; }
.cmd-bar-track span { display: block; height: 100%; border-radius: 5px; transition: width 1s cubic-bezier(.34,1.2,.64,1); }
.cmd-bar-v { width: 60px; text-align: right; font-size: 16px; font-variant-numeric: tabular-nums; }

/* Attention */
.cmd-attn { display: flex; flex-direction: column; gap: 14px; }
.cmd-attn-row { display: flex; align-items: center; gap: 22px; padding: 20px 26px; border-radius: 16px; background: rgba(255,255,255,.05); border-left: 4px solid; }
.cmd-attn-row.sev-critical { border-color: #E24B4A; }
.cmd-attn-row.sev-warning { border-color: #EF9F27; }
.cmd-attn-row.sev-info { border-color: #378ADD; }
.cmd-attn-c { font-size: 46px; font-weight: 300; min-width: 80px; font-variant-numeric: tabular-nums; }
.cmd-attn-row.sev-critical .cmd-attn-c { color: #FCA5A5; }
.cmd-attn-row.sev-warning .cmd-attn-c { color: #FCD34D; }
.cmd-attn-row.sev-info .cmd-attn-c { color: #93C5FD; }
.cmd-attn-t { display: flex; flex-direction: column; gap: 4px; }
.cmd-attn-title { font-size: 19px; font-weight: 500; }
.cmd-attn-d { font-size: 13px; color: rgba(255,255,255,.55); }
.cmd-clear { font-size: 24px; color: #6EE7B7; padding: 40px; text-align: center; }

/* Cols */
.cmd-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; }
.cmd-col-h { font-size: 14px; font-weight: 500; margin-bottom: 14px; letter-spacing: .04em; }
.cmd-col-up { color: #6EE7B7; }
.cmd-col-dn { color: #FCA5A5; }
.cmd-co { display: flex; align-items: center; justify-content: space-between; padding: 12px 6px; border-bottom: 1px solid rgba(255,255,255,.06); font-size: 17px; }
.cmd-co-n { color: rgba(255,255,255,.85); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cmd-co-v { font-weight: 500; font-variant-numeric: tabular-nums; margin-left: 14px; }

/* Rings */
.cmd-rings { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 22px; }
.cmd-ring { padding: 28px; border-radius: 18px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.09); text-align: center; }
.cmd-ring-v { font-size: 44px; font-weight: 300; font-variant-numeric: tabular-nums; }
.cmd-ring-v span { font-size: 22px; opacity: .6; }
.cmd-ring-l { margin-top: 8px; font-size: 14px; }
.cmd-ring-sub { font-size: 12px; color: rgba(255,255,255,.5); margin-top: 4px; }

.cmd-dots { position: relative; z-index: 1; display: flex; justify-content: center; gap: 10px; padding: 20px; }
.cmd-dot { width: 9px; height: 9px; border-radius: 50%; border: 0; background: rgba(255,255,255,.22); cursor: pointer; transition: all .2s; }
.cmd-dot.on { background: #7F77DD; width: 26px; border-radius: 5px; }

.cmd-panel-enter-active, .cmd-panel-leave-active { transition: opacity .5s ease, transform .5s var(--ease-standard, ease); }
.cmd-panel-enter-from { opacity: 0; transform: translateY(16px); }
.cmd-panel-leave-to { opacity: 0; transform: translateY(-16px); }
</style>
