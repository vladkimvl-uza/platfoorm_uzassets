<script setup lang="ts">
/**
 * PaSpendBreakdown — совокупный объём закупок компании + разбивка
 * товары/услуги/работы (3-сегментный бар + легенда). Лот-дедуп, ВСЕ типы.
 */
import { computed } from "vue";
import { paFmtMoneyShort } from "@/api/procurement_analysis";

const props = defineProps<{
  total: number;
  goods: number;
  services: number;
  works: number;
  lots?: number;
}>();

const tot = computed(() => Number(props.total) || 0);
const g = computed(() => Number(props.goods) || 0);
const s = computed(() => Number(props.services) || 0);
const w = computed(() => Number(props.works) || 0);
function pct(v: number): number {
  return tot.value > 0 ? (v / tot.value) * 100 : 0;
}
</script>

<template>
  <div class="psb">
    <div class="psb-head">
      <div class="psb-total">
        {{ paFmtMoneyShort(tot) }}<span class="psb-cur"> сум</span>
      </div>
      <div class="psb-lbl">
        Общий объём закупок<template v-if="lots"> · {{ lots }} лот.</template>
      </div>
    </div>
    <div class="psb-bar">
      <span class="psb-seg goods" :style="{ width: pct(g) + '%' }" :title="`Товары: ${paFmtMoneyShort(g)}`" />
      <span class="psb-seg serv" :style="{ width: pct(s) + '%' }" :title="`Услуги: ${paFmtMoneyShort(s)}`" />
      <span class="psb-seg work" :style="{ width: pct(w) + '%' }" :title="`Работы: ${paFmtMoneyShort(w)}`" />
    </div>
    <div class="psb-leg">
      <span class="psb-li"><i class="goods" />Товары <b>{{ paFmtMoneyShort(g) }}</b> · {{ pct(g).toFixed(0) }}%</span>
      <span class="psb-li"><i class="serv" />Услуги <b>{{ paFmtMoneyShort(s) }}</b> · {{ pct(s).toFixed(0) }}%</span>
      <span class="psb-li"><i class="work" />Работы <b>{{ paFmtMoneyShort(w) }}</b> · {{ pct(w).toFixed(0) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.psb {
  background: var(--bg2, #FAFAFD);
  border-radius: 10px;
  padding: 12px 14px;
}
.psb-head { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.psb-total {
  font-size: 22px; font-weight: 400;
  color: var(--t1, #1e2a4a);
  font-variant-numeric: tabular-nums; letter-spacing: -.01em;
}
.psb-cur { font-size: 12px; color: rgba(15, 23, 60, .45); }
.psb-lbl {
  font-size: 10px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; color: rgba(15, 23, 60, .5);
}
.psb-bar {
  display: flex; height: 8px; margin-top: 10px;
  border-radius: 4px; overflow: hidden;
  background: rgba(15, 23, 60, .05);
}
.psb-seg { height: 100%; transition: width .7s cubic-bezier(.22,1,.36,1); }
.psb-seg.goods { background: linear-gradient(90deg, #9D97E6, #7F77DD); }
.psb-seg.serv  { background: linear-gradient(90deg, #93D3B0, #5DC093); }
.psb-seg.work  { background: linear-gradient(90deg, #EFC58A, #E89B4A); }
.psb-leg {
  display: flex; flex-wrap: wrap; gap: 12px; margin-top: 9px;
  font-size: 10.5px; color: rgba(15, 23, 60, .6);
}
.psb-li { display: inline-flex; align-items: center; gap: 5px; }
.psb-li b { font-weight: 600; color: var(--t1, #1e2a4a); }
.psb-li i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.psb-li i.goods { background: #7F77DD; }
.psb-li i.serv  { background: #5DC093; }
.psb-li i.work  { background: #E89B4A; }
</style>
