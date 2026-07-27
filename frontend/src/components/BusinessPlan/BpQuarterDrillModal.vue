 <script setup lang="ts">
/**
 * BpQuarterDrillModal — разбор квартала. КАНОН: кварталы БП хранятся нарастающим
 * итогом (НСБУ: q2=полугодие, q4=год) — план/факт/ожидание здесь YTD-значения,
 * % и шкала = исполнение С НАЧАЛА ГОДА; «за квартал» — отдельные строки-дельты.
 */
import { computed } from "vue";
import ModalShell from "@/components/ModalShell.vue";

const props = defineProps<{
  q: string;
  plan: number | null;          // YTD (нарастающим итогом)
  fact: number | null;          // YTD
  expect?: number | null;       // YTD
  planDelta?: number | null;    // «за квартал»
  factDelta?: number | null;
  cum?: number | null;
  label?: string;
  unit?: string;
  fmt: (n: number) => string;
}>();

const emit = defineEmits<{ close: [] }>();

// % исполнения С НАЧАЛА ГОДА (YTD факт / YTD план) — им же красится бейдж и шкала.
const pct = computed(() =>
  (props.plan != null && props.plan !== 0 && props.fact != null)
    ? Math.round((props.fact / props.plan) * 100) : null,
);
// % исполнения ЗА квартал (дельта факта / дельта плана).
const pctQ = computed(() =>
  (props.planDelta != null && props.planDelta !== 0 && props.factDelta != null)
    ? Math.round((props.factDelta / props.planDelta) * 100) : null,
);
const delta = computed(() => (props.fact != null && props.plan != null) ? props.fact - props.plan : null);
function signed(v: number): string {
  return (v < 0 ? "−" : "") + props.fmt(Math.abs(v));
}
function pctColor(p: number | null): string {
  if (p == null) return "#94A3B8";
  if (p >= 100) return "#1D9E75";
  if (p >= 80) return "#A36500";
  return "#C5352F";
}
const fillPct = computed(() => Math.max(0, Math.min(140, pct.value ?? 0)));
const tone = computed(() => {
  const p = pct.value;
  if (p == null) return { c: "#94A3B8", bg: "rgba(148,163,184,.14)", t: "нет факта" };
  if (p >= 110) return { c: "#1D9E75", bg: "rgba(29,158,117,.12)", t: "план перевыполнен" };
  if (p >= 100) return { c: "#1D9E75", bg: "rgba(29,158,117,.12)", t: "план выполнен" };
  if (p >= 80) return { c: "#A36500", bg: "rgba(239,159,39,.14)", t: "требует внимания" };
  return { c: "#C5352F", bg: "rgba(226,75,74,.12)", t: "недобор" };
});
</script>

<template>
  <ModalShell :open="true" size="sm" @close="emit('close')">
    <template #header>
      <div class="bqd-hd">
        <span class="bqd-q">{{ q.toUpperCase() }}</span>
        <div>
          <div class="bqd-t">Разбор квартала<span v-if="label"> · {{ label }}</span></div>
          <div class="bqd-sub" :style="{ color: tone.c }">{{ tone.t }}</div>
        </div>
        <span v-if="pct != null" class="bqd-badge" :style="{ color: tone.c, background: tone.bg }">{{ pct }}%</span>
      </div>
    </template>

    <!-- Шкала: исполнение С НАЧАЛА ГОДА (бейдж в шапке — тот же %) -->
    <div class="bqd-gauge">
      <div class="bqd-gauge-track">
        <div class="bqd-gauge-fill" :style="{ width: (fillPct / 140 * 100) + '%', background: tone.c }"></div>
        <div class="bqd-gauge-100" :style="{ left: (100 / 140 * 100) + '%' }" title="План = 100%"></div>
      </div>
      <div class="bqd-gauge-cap"><span>0</span><span>исполнение с начала года · план = 100%</span><span>140%</span></div>
    </div>

    <!-- Секция 1: только этот квартал (дельты) -->
    <div class="bqd-sec">За квартал {{ q.toUpperCase() }}</div>
    <div class="bqd-rows">
      <div class="bqd-row"><span>План</span><b>{{ planDelta != null ? signed(planDelta) : '—' }} <i>{{ unit }}</i></b></div>
      <div class="bqd-row"><span>Факт</span><b>{{ factDelta != null ? signed(factDelta) : '—' }} <i>{{ unit }}</i></b></div>
      <div v-if="factDelta == null && fact != null" class="bqd-row-note">за квартал не вычислимо: нет данных предыдущего квартала</div>
      <div v-if="pctQ != null" class="bqd-row"><span>Исполнение за квартал</span><b :style="{ color: pctColor(pctQ) }">{{ pctQ }}%</b></div>
    </div>

    <!-- Секция 2: с начала года (как хранится в отчётности НСБУ) -->
    <div class="bqd-sec">С начала года · нарастающим итогом</div>
    <div class="bqd-rows">
      <div class="bqd-row"><span>План</span><b>{{ plan != null ? fmt(plan) : '—' }} <i>{{ unit }}</i></b></div>
      <div class="bqd-row"><span>Факт</span><b>{{ fact != null ? fmt(fact) : '—' }} <i>{{ unit }}</i></b></div>
      <div v-if="expect != null && expect !== fact" class="bqd-row"><span>Ожидание</span><b>{{ fmt(expect) }} <i>{{ unit }}</i></b></div>
      <div v-if="delta != null" class="bqd-row"><span>Дельта факт−план</span><b :style="{ color: delta >= 0 ? '#0F6E56' : '#C5352F' }">{{ delta >= 0 ? '+' : '' }}{{ fmt(delta) }} <i>{{ unit }}</i></b></div>
      <div v-if="pct != null" class="bqd-row"><span>Исполнение с начала года</span><b :style="{ color: tone.c }">{{ pct }}%</b></div>
    </div>
  </ModalShell>
</template>

<style scoped>
.bqd-hd { display: flex; align-items: center; gap: 12px; width: 100%; }
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

.bqd-rows { display: flex; flex-direction: column; gap: 1px; margin-bottom: 6px; }
.bqd-sec {
  font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em;
  color: var(--t3, #94A3B8); margin: 12px 0 3px; padding-bottom: 4px;
  border-bottom: 1px solid var(--line, #F1F0F7);
}
.bqd-row-note { font-size: 10.5px; color: var(--t3, #A6A3B8); padding: 4px 0; }
.bqd-row { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; padding: 9px 0; border-bottom: 1px solid var(--line, #F1F0F7); }
.bqd-row:last-child { border-bottom: none; }
.bqd-row > span { font-size: 12px; color: var(--t2, #6B6880); }
.bqd-row > b { font-size: 14px; font-weight: 600; color: var(--t1, #1A1730); font-variant-numeric: tabular-nums; }
.bqd-row > b i { font-size: 10px; font-weight: 500; color: var(--t3, #A6A3B8); font-style: normal; }
</style>
