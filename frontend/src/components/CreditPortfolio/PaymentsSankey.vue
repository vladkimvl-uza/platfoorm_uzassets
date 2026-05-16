<script setup lang="ts">
/**
 * PaymentsSankey — Pure SVG sankey-диаграмма «Банк → Год».
 *
 * Источник: useCreditData.sankeyFlows — backend group'ит топ-8 банков.
 *
 * Layout:
 *   • viewBox 0 0 1200 480
 *   • Левая колонка — банки, правая — годы
 *   • Линки — cubic Bézier filled paths
 *   • Цвет банка → lender_type из aggregate.by_bank_full
 *   • Hover на link → opacity + tooltip
 *   • Click на год → filterByYear; click на банк → filterByBank
 */
import { computed, ref } from "vue";
import { useCreditData } from "@/composables/useCreditData";
import {
  CP_LENDER_LABELS,
  fmtMoneyShort,
  toNum,
  type LenderType,
} from "@/api/credit";

const credit = useCreditData();

const VB_W = 1200;
const VB_H = 480;
const NODE_W = 14;
const TOP = 18;
const BOTTOM = 18;
const GAP = 6;
const LEFT_LBL_X = 220;
const RIGHT_LBL_X = VB_W - 200;

const bankTypeMap = computed<Record<string, LenderType | undefined>>(() => {
  const m: Record<string, LenderType | undefined> = {};
  const banks = credit.aggregate.value?.by_bank_full || [];
  for (const b of banks) m[b.bank_short_name] = b.lender_type || undefined;
  return m;
});

function colorForBank(bankShort: string): string {
  const t = bankTypeMap.value[bankShort];
  return t && CP_LENDER_LABELS[t] ? CP_LENDER_LABELS[t].color : "#7F77DD";
}

interface SankeyNode {
  label: string;
  total: number;
  y: number;
  h: number;
  color: string;
  _offset: number;
}

interface SankeyLink {
  bank: string;
  year: string;
  debt: number;
  s1y: number;
  s2y: number;
  t1y: number;
  t2y: number;
  color: string;
}

const layout = computed(() => {
  const flows = credit.sankeyFlows.value;
  if (!flows.length) return { banks: [] as SankeyNode[], years: [] as SankeyNode[], links: [] as SankeyLink[] };

  const banksAgg: Record<string, number> = {};
  const yearsAgg: Record<string, number> = {};
  for (const f of flows) {
    const v = toNum(f.debt_usd);
    banksAgg[f.bank_short_name] = (banksAgg[f.bank_short_name] || 0) + v;
    yearsAgg[f.year_label] = (yearsAgg[f.year_label] || 0) + v;
  }

  const totalAll = Object.values(banksAgg).reduce((s, v) => s + v, 0) || 1;

  const banksList = Object.keys(banksAgg).sort((a, b) => banksAgg[b] - banksAgg[a]);
  const yearsList = Object.keys(yearsAgg).sort((a, b) => {
    const ag = a.startsWith(">"), bg = b.startsWith(">");
    if (ag && !bg) return 1;
    if (!ag && bg) return -1;
    return parseInt(a, 10) - parseInt(b, 10);
  });

  const innerHBanks = VB_H - TOP - BOTTOM - Math.max(0, banksList.length - 1) * GAP;
  const innerHYears = VB_H - TOP - BOTTOM - Math.max(0, yearsList.length - 1) * GAP;

  const banks: SankeyNode[] = [];
  let yPos = TOP;
  for (const bk of banksList) {
    const h = (banksAgg[bk] / totalAll) * innerHBanks;
    banks.push({
      label: bk, total: banksAgg[bk], y: yPos, h,
      color: colorForBank(bk), _offset: 0,
    });
    yPos += h + GAP;
  }

  const years: SankeyNode[] = [];
  yPos = TOP;
  for (const yr of yearsList) {
    const h = (yearsAgg[yr] / totalAll) * innerHYears;
    years.push({
      label: yr, total: yearsAgg[yr], y: yPos, h,
      color: "#7F77DD", _offset: 0,
    });
    yPos += h + GAP;
  }

  const sortedFlows = flows.slice().sort((a, b) => toNum(b.debt_usd) - toNum(a.debt_usd));

  const links: SankeyLink[] = [];
  for (const f of sortedFlows) {
    const v = toNum(f.debt_usd);
    if (v <= 0) continue;
    const bn = banks.find((b) => b.label === f.bank_short_name);
    const yn = years.find((y) => y.label === f.year_label);
    if (!bn || !yn) continue;
    const lhSrc = (v / bn.total) * bn.h;
    const lhTgt = (v / yn.total) * yn.h;
    const s1y = bn.y + bn._offset;
    const s2y = s1y + lhSrc;
    const t1y = yn.y + yn._offset;
    const t2y = t1y + lhTgt;
    bn._offset += lhSrc;
    yn._offset += lhTgt;
    links.push({
      bank: f.bank_short_name, year: f.year_label, debt: v,
      s1y, s2y, t1y, t2y, color: bn.color,
    });
  }
  return { banks, years, links };
});

const sourceX = LEFT_LBL_X + NODE_W;
const targetX = RIGHT_LBL_X;

function linkPath(L: SankeyLink): string {
  const sx = sourceX, tx = targetX;
  const midX = sx + (tx - sx) * 0.5;
  return `M ${sx} ${L.s1y} C ${midX} ${L.s1y}, ${midX} ${L.t1y}, ${tx} ${L.t1y} L ${tx} ${L.t2y} C ${midX} ${L.t2y}, ${midX} ${L.s2y}, ${sx} ${L.s2y} Z`;
}

const hoveredLink = ref<number | null>(null);

function onYearClick(yLabel: string) {
  if (yLabel.startsWith(">")) return;
  const y = parseInt(yLabel, 10);
  if (!isNaN(y)) credit.filterByYear(y);
}
function onBankClick(b: string) { credit.filterByBank(b); }

const tooltipText = computed(() => {
  if (hoveredLink.value === null) return null;
  const L = layout.value.links[hoveredLink.value];
  if (!L) return null;
  return `${L.bank} → ${L.year} · ${fmtMoneyShort(L.debt)}`;
});
</script>

<template>
  <div class="cp-sk-host">
    <div v-if="!layout.links.length" class="cp-sk-empty">
      Нет данных для построения диаграммы потоков
    </div>

    <svg
      v-else
      class="cp-sk-svg"
      :viewBox="`0 0 ${VB_W} ${VB_H}`"
      preserveAspectRatio="xMidYMid meet"
      xmlns="http://www.w3.org/2000/svg"
    >
      <g class="cp-sk-links">
        <path
          v-for="(L, i) in layout.links"
          :key="i"
          :d="linkPath(L)"
          :fill="L.color"
          :opacity="hoveredLink === null ? 0.32 : (hoveredLink === i ? 0.78 : 0.10)"
          @mouseenter="hoveredLink = i"
          @mouseleave="hoveredLink = null"
        />
      </g>

      <g class="cp-sk-banks">
        <g
          v-for="bn in layout.banks"
          :key="'b-' + bn.label"
          class="cp-sk-bank"
          @click="onBankClick(bn.label)"
        >
          <rect :x="LEFT_LBL_X" :y="bn.y" :width="NODE_W" :height="bn.h" :fill="bn.color" rx="2"/>
          <text :x="LEFT_LBL_X - 6" :y="bn.y + bn.h / 2 + 4" class="cp-sk-bank-lbl" text-anchor="end">
            {{ bn.label }}
          </text>
          <text :x="LEFT_LBL_X - 6" :y="bn.y + bn.h / 2 + 18" class="cp-sk-bank-amt" text-anchor="end">
            {{ fmtMoneyShort(bn.total) }}
          </text>
        </g>
      </g>

      <g class="cp-sk-years">
        <g
          v-for="yn in layout.years"
          :key="'y-' + yn.label"
          :class="['cp-sk-year', { 'cp-sk-year-gt': yn.label.startsWith('>') }]"
          @click="onYearClick(yn.label)"
        >
          <rect :x="RIGHT_LBL_X - NODE_W" :y="yn.y" :width="NODE_W" :height="yn.h" :fill="yn.color" rx="2"/>
          <text :x="RIGHT_LBL_X + 6" :y="yn.y + yn.h / 2 + 4" class="cp-sk-year-lbl" text-anchor="start">
            {{ yn.label }}
          </text>
          <text :x="RIGHT_LBL_X + 6" :y="yn.y + yn.h / 2 + 18" class="cp-sk-year-amt" text-anchor="start">
            {{ fmtMoneyShort(yn.total) }}
          </text>
        </g>
      </g>
    </svg>

    <transition name="cp-sk-tip">
      <div v-if="tooltipText" class="cp-sk-tooltip">{{ tooltipText }}</div>
    </transition>
  </div>
</template>

<style scoped>
.cp-sk-host {
  position: relative;
  width: 100%;
  height: 480px;
  padding: 8px 4px;
}
.cp-sk-svg { width: 100%; height: 100%; overflow: visible; }
.cp-sk-links path { cursor: pointer; transition: opacity 0.18s ease; }
.cp-sk-bank, .cp-sk-year { cursor: pointer; }
.cp-sk-year-gt { cursor: default; }
.cp-sk-bank rect, .cp-sk-year rect { transition: filter 0.16s; }
.cp-sk-bank:hover rect, .cp-sk-year:not(.cp-sk-year-gt):hover rect {
  filter: brightness(1.15);
}
.cp-sk-bank-lbl, .cp-sk-year-lbl {
  font-size: 11.5px;
  font-weight: 500;
  fill: #1e2a4a;
  font-family: inherit;
  letter-spacing: -0.005em;
}
.cp-sk-bank-amt, .cp-sk-year-amt {
  font-size: 9.5px;
  font-weight: 400;
  fill: #888780;
  font-family: inherit;
  font-feature-settings: "tnum";
}
.cp-sk-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--t3, #888780);
  font-style: italic;
}
.cp-sk-tooltip {
  position: absolute;
  bottom: 14px;
  left: 50%;
  transform: translateX(-50%);
  background: #0F172A;
  color: #fff;
  font-size: 11.5px;
  font-weight: 500;
  padding: 8px 14px;
  border-radius: 8px;
  pointer-events: none;
  letter-spacing: -0.005em;
  font-feature-settings: "tnum";
  white-space: nowrap;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
}
.cp-sk-tip-enter-active, .cp-sk-tip-leave-active {
  transition: opacity 0.14s ease, transform 0.18s ease;
}
.cp-sk-tip-enter-from, .cp-sk-tip-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}
</style>
