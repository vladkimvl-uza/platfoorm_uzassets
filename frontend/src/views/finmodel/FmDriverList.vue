<template>
  <section class="fm-card fm-driv-card" :style="{ '--d': '640ms', '--accent': accent }">
    <div class="fm-card-ttl">
      <span>{{ title }}</span>
      <span class="fm-card-meta">{{ items.length }} позиций</span>
    </div>

    <div class="fm-driv-wrap">
      <table class="fm-driv-tbl">
        <thead>
          <tr>
            <th class="fm-driv-name">Драйвер</th>
            <th class="fm-driv-unit">Ед.</th>
            <th
              v-for="y in years"
              :key="y"
              :class="{ forecast: !isFactYear(y) }"
            >{{ y }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(d, idx) in items" :key="d.id">
            <td class="fm-driv-name">
              <span class="fm-dot" :style="{ background: accent, animationDelay: (idx * 40) + 'ms' }" />
              {{ d.name }}
            </td>
            <td class="fm-driv-unit">{{ d.unit }}</td>
            <td
              v-for="y in years"
              :key="y"
              :class="{ forecast: !isFactYear(y) }"
            >{{ fmtNum(d.values[y]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { FmDriver, FmCost, FmCapex } from "./fmUapSeed";

const props = defineProps<{
  title: string;
  accent: string;
  items: Array<FmDriver | FmCost | FmCapex>;
  years: number[];
  factYears: number[];
}>();

function isFactYear(y: number): boolean {
  return props.factYears.includes(y);
}

function fmtNum(v: number | undefined): string {
  if (!Number.isFinite(v as number) || v === 0) return "—";
  const n = v as number;
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (Math.abs(n) >= 1_000) return (n / 1_000).toFixed(0) + "k";
  return Math.round(n).toLocaleString("ru-RU");
}
</script>

<style scoped>
.fm-card {
  background: #fff;
  border-radius: 12px;
  border: 1px solid rgba(15, 23, 60, 0.05);
  padding: 16px 18px;
  position: relative;
  overflow: hidden;
  animation: fmCardIn 0.55s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
}
.fm-card::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--accent, #7F77DD);
  transform-origin: left center;
  animation: fmStripeIn 0.8s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
}
@keyframes fmCardIn {
  0%   { opacity: 0; transform: translateY(10px) scale(0.98); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes fmStripeIn {
  from { transform: scaleX(0); opacity: 0; }
  to   { transform: scaleX(1); opacity: 1; }
}

.fm-card-ttl {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
  font-size: 11px;
  font-weight: 500;
  color: rgba(15, 23, 60, 0.65);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.fm-card-meta { text-transform: none; letter-spacing: normal; font-size: 11px; color: rgba(15, 23, 60, 0.45); }

.fm-driv-wrap { overflow-x: auto; }
.fm-driv-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}
.fm-driv-tbl thead th {
  padding: 6px 8px;
  text-align: right;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, 0.55);
  border-bottom: 1px solid rgba(15, 23, 60, 0.06);
  white-space: nowrap;
}
.fm-driv-tbl thead th.fm-driv-name,
.fm-driv-tbl thead th.fm-driv-unit { text-align: left; }
.fm-driv-tbl thead th.forecast { background: #FFFBF4; color: #7A4A00; }
.fm-driv-tbl tbody td {
  padding: 5px 8px;
  text-align: right;
  color: #1E2A4A;
  border-bottom: 1px solid rgba(15, 23, 60, 0.03);
}
.fm-driv-tbl tbody td.fm-driv-name {
  text-align: left;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 180px;
}
.fm-driv-tbl tbody td.fm-driv-unit {
  text-align: left;
  color: rgba(15, 23, 60, 0.5);
  font-size: 10px;
}
.fm-driv-tbl tbody td.forecast { background: #FFFBF4; color: #7A4A00; }

.fm-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  animation: fmDotPulse 1.4s ease-in-out infinite;
}
@keyframes fmDotPulse {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50%      { opacity: 1;   transform: scale(1.25); }
}
</style>
