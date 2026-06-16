<script setup lang="ts">
/**
 * BpQuarterDrillModal — разбор квартала: план / факт / ожидание / выполнение /
 * дельта / вклад в нарастающий итог. Премиум-модалка с анимацией.
 */
import { computed } from "vue";

const props = defineProps<{
  q: string;
  plan: number | null;
  fact: number | null;
  expect?: number | null;
  cum?: number | null;
  label?: string;
  unit?: string;
  fmt: (n: number) => string;
}>();

const emit = defineEmits<{ close: [] }>();

const pct = computed(() =>
  (props.plan != null && props.plan !== 0 && props.fact != null)
    ? Math.round((props.fact / props.plan) * 100) : null,
);
const delta = computed(() => (props.fact != null && props.plan != null) ? props.fact - props.plan : null);
const fillPct = computed(() => Math.max(0, Math.min(140, pct.value ?? 0)));
const tone = computed(() => {
  const p = pct.value;
  if (p == null) return { c: "#94A3B8", bg: "rgba(148,163,184,.14)", t: "нет факта" };
  if (p >= 100) return { c: "#1D9E75", bg: "rgba(29,158,117,.12)", t: "план выполнен" };
  if (p >= 80) return { c: "#A36500", bg: "rgba(239,159,39,.14)", t: "требует внимания" };
  return { c: "#C5352F", bg: "rgba(226,75,74,.12)", t: "недобор" };
});
</script>

<template>
  <Teleport to="body">
    <div class="bqd-overlay" @click.self="emit('close')">
      <div class="bqd" role="dialog" aria-modal="true">
        <button class="bqd-x" @click="emit('close')">×</button>
        <div class="bqd-hd">
          <span class="bqd-q">{{ q.toUpperCase() }}</span>
          <div>
            <div class="bqd-t">Разбор квартала<span v-if="label"> · {{ label }}</span></div>
            <div class="bqd-sub" :style="{ color: tone.c }">{{ tone.t }}</div>
          </div>
          <span v-if="pct != null" class="bqd-badge" :style="{ color: tone.c, background: tone.bg }">{{ pct }}%</span>
        </div>

        <!-- Шкала выполнения -->
        <div class="bqd-gauge">
          <div class="bqd-gauge-track">
            <div class="bqd-gauge-fill" :style="{ width: (fillPct / 140 * 100) + '%', background: tone.c }"></div>
            <div class="bqd-gauge-100" :style="{ left: (100 / 140 * 100) + '%' }" title="План = 100%"></div>
          </div>
          <div class="bqd-gauge-cap"><span>0</span><span>план</span><span>140%</span></div>
        </div>

        <div class="bqd-rows">
          <div class="bqd-row"><span>План</span><b>{{ plan != null ? fmt(plan) : '—' }} <i>{{ unit }}</i></b></div>
          <div class="bqd-row"><span>Факт</span><b>{{ fact != null ? fmt(fact) : '—' }} <i>{{ unit }}</i></b></div>
          <div v-if="expect != null" class="bqd-row"><span>Ожидание</span><b>{{ fmt(expect) }} <i>{{ unit }}</i></b></div>
          <div v-if="delta != null" class="bqd-row"><span>Дельта факт−план</span><b :style="{ color: delta >= 0 ? '#0F6E56' : '#C5352F' }">{{ delta >= 0 ? '+' : '' }}{{ fmt(delta) }} <i>{{ unit }}</i></b></div>
          <div v-if="cum != null" class="bqd-row"><span>Нараст. итог (YTD)</span><b>{{ fmt(cum) }} <i>{{ unit }}</i></b></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.bqd-overlay {
  position: fixed; inset: 0; z-index: 9400;
  background: rgba(20,16,40,.46); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.bqd {
  position: relative; width: 380px; max-width: 100%;
  background: var(--bg1, #fff); border-radius: 18px; padding: 20px 22px;
  box-shadow: 0 30px 70px -15px rgba(30,20,70,.5);
  font-family: Geist, system-ui, sans-serif;
  animation: bqdPop .3s cubic-bezier(.34,1.4,.5,1);
}
@keyframes bqdPop { from { opacity: 0; transform: translateY(12px) scale(.96); } to { opacity: 1; transform: none; } }
.bqd-x { position: absolute; top: 12px; right: 12px; width: 26px; height: 26px; border: none; border-radius: 8px; background: var(--bg2, #F1F0F7); color: var(--t3, #8B889C); font-size: 15px; cursor: pointer; }
.bqd-x:hover { background: #E7E5F1; }

.bqd-hd { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.bqd-q {
  width: 42px; height: 42px; border-radius: 12px; flex-shrink: 0;
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 15px; font-weight: 700;
}
.bqd-t { font-size: 13px; font-weight: 600; color: var(--t1, #1A1730); }
.bqd-sub { font-size: 11px; font-weight: 600; margin-top: 1px; }
.bqd-badge { margin-left: auto; font-size: 16px; font-weight: 700; padding: 4px 11px; border-radius: 999px; font-variant-numeric: tabular-nums; }

.bqd-gauge { margin-bottom: 16px; }
.bqd-gauge-track { position: relative; height: 9px; background: var(--bg2, #EEEDF4); border-radius: 6px; overflow: visible; }
.bqd-gauge-fill { height: 100%; border-radius: 6px; transition: width .6s var(--ease-standard); }
.bqd-gauge-100 { position: absolute; top: -3px; bottom: -3px; width: 2px; background: var(--t3, #94A3B8); border-radius: 2px; }
.bqd-gauge-cap { display: flex; justify-content: space-between; font-size: 9px; color: var(--t3, #A6A3B8); margin-top: 5px; }

.bqd-rows { display: flex; flex-direction: column; gap: 1px; }
.bqd-row { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; padding: 9px 0; border-bottom: 1px solid var(--line, #F1F0F7); }
.bqd-row:last-child { border-bottom: none; }
.bqd-row > span { font-size: 12px; color: var(--t2, #6B6880); }
.bqd-row > b { font-size: 14px; font-weight: 600; color: var(--t1, #1A1730); font-variant-numeric: tabular-nums; }
.bqd-row > b i { font-size: 10px; font-weight: 500; color: var(--t3, #A6A3B8); font-style: normal; }
</style>
