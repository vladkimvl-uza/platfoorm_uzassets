<script setup lang="ts">
// ============================================================================
// Scoreboard — sortable per-company table with sparkline trend + click-to-card.
//
// Layout depends on viewTab:
//   PL   → # | Компания | Тренд | Выручка | Вал.маржа | EBITDA | EB маржа | Чист.приб. | Чист.маржа | Δ Rev
//   SOFP → # | Компания | Активы | Капитал | Долг | D/E | Чист.долг | Кэш | ROE
//   CF   → # | Компания | CFO | CFI | CFF | FCF | Дивиденды | CF/EBITDA
//   BS (NSBU) → same as SOFP
//
// 1:1 port of legacy showFinanceView scoreboardTable (lines 43215-43330).
// ============================================================================

import { computed, ref } from "vue";
import type { PortfolioSummaryResponse } from "@/api/financials";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import { fmtCompact, sectorColor, buildCompanyIndex } from "./financialsHelpers";
import { useI18n } from "@/composables/useI18n";
import { resolveCompanyDisplayName } from "@/utils/displayNames";

const { t } = useI18n();

const props = defineProps<{
  summary: PortfolioSummaryResponse | null;
  companies: CompanyListItem[];
  sectors: SectorBrief[];
  viewTab: string;
  standard: "IFRS" | "NSBU";
  year: number;
  unit: "bln" | "mln";
  sectorFilter?: string;
  search?: string;
}>();

const emit = defineEmits<{
  (e: "row-click", company_code: string): void;
}>();

const sortCol = ref<number>(-1);
const sortDir = ref<"asc" | "desc">("desc");

function toggleSort(ci: number, sortable: boolean) {
  if (!sortable) return;
  if (sortCol.value === ci) {
    sortDir.value = sortDir.value === "desc" ? "asc" : "desc";
  } else {
    sortCol.value = ci;
    sortDir.value = "desc";
  }
}

const companyIdx = computed(() => buildCompanyIndex(props.companies));
const sectorByCode = computed(() => {
  const m: Record<string, SectorBrief> = {};
  for (const s of props.sectors) m[String(s.code).toLowerCase()] = s;
  return m;
});

function ratio(a: number | null, b: number | null): number | null {
  if (a == null || b == null || b === 0) return null;
  return Math.round((a / b) * 10) / 10;
}
function pct(a: number | null, b: number | null): number | null {
  if (a == null || b == null || b === 0) return null;
  return Math.round((a / b) * 100);
}

function sparkSvg(values: Array<number | null>, color: string): string {
  if (!Array.isArray(values) || values.length < 2) return "";
  const fv = values.filter(v => v != null) as number[];
  if (!fv.length) return "";
  const w = 52, h = 16, p = 1;
  const mn = Math.min(...fv), mx = Math.max(...fv), rng = mx - mn || 1;
  const pts = values.map((v, i) => {
    const val = v == null ? mn : v;
    const x = Math.round(p + (i / (values.length - 1)) * (w - 2 * p));
    const y = Math.round(p + (1 - (val - mn) / rng) * (h - 2 * p));
    return `${x},${y}`;
  }).join(" ");
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="stroke-dasharray:200;animation:sparkDraw .8s ease-out both"/></svg>`;
}

type Align = "left" | "right" | "center";
interface Cell { html: string; align: Align; }

function coCell(name: string, color: string): Cell {
  const safe = name.replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return {
    html: `<span style="display:inline-block;width:3px;height:14px;border-radius:2px;background:${color};margin-right:6px;vertical-align:middle"></span><span style="font-weight:600">${safe}</span>`,
    align: "left",
  };
}
function sparkCell(values: Array<number | null>, color: string): Cell {
  return { html: sparkSvg(values, color), align: "center" };
}
function numCell(v: number | null, unit: "bln" | "mln", inverseColor = false): Cell {
  if (v == null) return { html: `<span style="color:var(--t3, #64748B)">—</span>`, align: "right" };
  const c = inverseColor
    ? (v >= 0 ? "#E24B4A" : "#1D9E75")
    : (v < 0 ? "#E24B4A" : "var(--t1, #1E2A4A)");
  return { html: `<span style="color:${c};font-feature-settings:'tnum'">${fmtCompact(v, unit)}</span>`, align: "right" };
}
function pctCell(v: number | null, goodThreshold: number | null): Cell {
  if (v == null) return { html: `<span style="color:var(--t3, #64748B)">—</span>`, align: "right" };
  const c = goodThreshold != null
    ? (v >= goodThreshold ? "#1D9E75" : v >= 0 ? "var(--t2, #4B5468)" : "#E24B4A")
    : (v >= 0 ? "var(--t1, #1E2A4A)" : "#E24B4A");
  return { html: `<span style="font-weight:600;color:${c};font-feature-settings:'tnum'">${v}%</span>`, align: "right" };
}
function ratioCell(v: number | null, dangerThreshold: number | null): Cell {
  if (v == null) return { html: `<span style="color:var(--t3, #64748B)">—</span>`, align: "right" };
  const c = dangerThreshold != null
    ? (v > dangerThreshold ? "#E24B4A" : v > dangerThreshold / 2 ? "#EF9F27" : "#1D9E75")
    : "var(--t1, #1E2A4A)";
  return { html: `<span style="font-weight:600;color:${c};font-feature-settings:'tnum'">${v}x</span>`, align: "right" };
}
function yoyCell(v: number | null): Cell {
  if (v == null) return { html: `<span style="color:var(--t3, #64748B)">—</span>`, align: "right" };
  const bg = v >= 0 ? "rgba(29,158,117,.12)" : "rgba(226,75,74,.12)";
  const c = v >= 0 ? "#1D9E75" : "#E24B4A";
  const sign = v > 0 ? "+" : "";
  return { html: `<span style="font-weight:600;padding:2px 7px;border-radius:4px;background:${bg};color:${c}">${sign}${v}%</span>`, align: "right" };
}

interface Row {
  rank: number;
  company_code: string;
  name: string;
  sector_color: string;
  sortVals: Array<number | null>;
  cells: Cell[];
}

const rows = computed<Row[]>(() => {
  if (!props.summary) return [];
  const items = props.summary.items;
  const q = (props.search || "").trim().toLowerCase();
  const filtered = items.filter(it => {
    if (props.sectorFilter) {
      const co = companyIdx.value.get(it.company_code.toLowerCase());
      if (String(co?.sector_code || "").toLowerCase() !== props.sectorFilter) return false;
    }
    if (q) {
      const hay = `${it.company_name || ""} ${it.company_name_short || ""} ${it.company_code || ""} ${resolveCompanyDisplayName(it.company_name_short || it.company_name, it.company_code)}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const yearValues = (item: typeof items[0], metric: string): Array<number | null> => {
    return props.summary!.years.map(y => {
      const v = item.by_year[y]?.[metric];
      return typeof v === "number" ? v : null;
    });
  };

  const out: Row[] = [];
  for (const item of filtered) {
    const localizedName = resolveCompanyDisplayName(item.company_name_short || item.company_name, item.company_code);
    const co = companyIdx.value.get(item.company_code.toLowerCase());
    const sec = sectorByCode.value[String(co?.sector_code || "").toLowerCase()];
    const sColor = sectorColor(sec);
    const muted = sColor + "BF";

    const cur = item.by_year[props.year] || {};
    const prev = item.by_year[props.year - 1] || {};

    // В модуле 0 = «нет данных» (fmtCompact рисует 0 как «—»). Поэтому в
    // расчётах динамики тоже трактуем 0 как отсутствие данных, иначе выручка
    // 0 против прошлого года даёт ложные −100%, хотя в ячейке стоит «—».
    const nz = (v: number | null | undefined): number | null =>
      (v == null || v === 0 ? null : v);
    const revCur = nz(cur.revenue);
    const revPrev = nz(prev.revenue);
    const yoy = (revCur != null && revPrev != null)
      ? Math.round(((revCur - revPrev) / Math.abs(revPrev)) * 100)
      : null;

    let cells: Cell[] = [];
    let sortVals: Array<number | null> = [];

    if (props.viewTab === "SOFP" || props.viewTab === "BS") {
      const ta = cur.totalAssets ?? null;
      const eq = cur.equity ?? null;
      const dt = cur.debt ?? null;
      const ca = cur.cash ?? null;
      const ni = cur.profit ?? null;
      const de = ratio(dt, eq);
      const nd = (dt != null && ca != null) ? dt - ca : null;
      const roe = pct(ni, eq);
      sortVals = [0, 0, ta, eq, dt, de, nd, ca, roe];
      cells = [
        coCell(localizedName, sColor),
        numCell(ta, props.unit),
        numCell(eq, props.unit),
        numCell(dt, props.unit),
        ratioCell(de, 3),
        numCell(nd, props.unit),
        numCell(ca, props.unit),
        pctCell(roe, 10),
      ];
    } else if (props.viewTab === "CF") {
      const cfo = cur.cfo ?? null;
      const cfi = cur.cfi ?? null;
      const cff = cur.cff ?? null;
      const div = cur.dividendsPaid ?? null;
      const eb  = cur.ebitda ?? null;
      const fcf = (cfo != null && cfi != null) ? cfo + cfi : null;
      const conv = (eb != null && eb > 0 && cfo != null) ? pct(cfo, eb) : null;
      sortVals = [0, 0, cfo, cfi, cff, fcf, div, conv];
      cells = [
        coCell(localizedName, sColor),
        numCell(cfo, props.unit),
        numCell(cfi, props.unit, true),
        numCell(cff, props.unit),
        numCell(fcf, props.unit),
        numCell(div, props.unit, true),
        pctCell(conv, 50),
      ];
    } else {
      // PL
      const rev = cur.revenue ?? null;
      const gp  = cur.grossProfit ?? null;
      const eb  = cur.ebitda ?? null;
      const ni  = cur.profit ?? null;
      const gm  = pct(gp, rev);
      const em  = pct(eb, rev);
      const nm  = pct(ni, rev);
      sortVals = [0, 0, 0, rev, gm, eb, em, ni, nm, yoy];
      const sparkVals = yearValues(item, "revenue");
      cells = [
        coCell(localizedName, sColor),
        sparkCell(sparkVals, muted),
        numCell(rev, props.unit),
        pctCell(gm, 20),
        numCell(eb, props.unit),
        pctCell(em, 15),
        numCell(ni, props.unit),
        pctCell(nm, 5),
        yoyCell(yoy),
      ];
    }

    out.push({
      rank: 0,
      company_code: item.company_code,
      name: localizedName,
      sector_color: sColor,
      sortVals,
      cells,
    });
  }
  return out;
});

const sortedRows = computed<Row[]>(() => {
  const data = [...rows.value];
  if (sortCol.value < 0) {
    const defaultCol = (props.viewTab === "SOFP" || props.viewTab === "BS") ? 2
                     : (props.viewTab === "CF") ? 2 : 3;
    data.sort((a, b) => {
      const av = a.sortVals[defaultCol], bv = b.sortVals[defaultCol];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return (bv as number) - (av as number);
    });
  } else {
    data.sort((a, b) => {
      const av = a.sortVals[sortCol.value], bv = b.sortVals[sortCol.value];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      return sortDir.value === "desc"
        ? (bv as number) - (av as number)
        : (av as number) - (bv as number);
    });
  }
  data.forEach((r, i) => { r.rank = i + 1; });
  return data;
});

interface Col { label: string; sortable: boolean; align: Align; width?: string; }

const cols = computed<Col[]>(() => {
  if (props.viewTab === "SOFP" || props.viewTab === "BS") {
    return [
      { label: "#",             sortable: false, align: "center", width: "32px" },
      { label: t("Компания"),   sortable: false, align: "left" },
      { label: t("Активы"),     sortable: true,  align: "right" },
      { label: t("Капитал"),    sortable: true,  align: "right" },
      { label: t("Долг"),       sortable: true,  align: "right" },
      { label: "D/E",           sortable: true,  align: "right" },
      { label: t("Чист.долг"),  sortable: true,  align: "right" },
      { label: t("Кэш"),        sortable: true,  align: "right" },
      { label: "ROE",           sortable: true,  align: "right" },
    ];
  }
  if (props.viewTab === "CF") {
    return [
      { label: "#",             sortable: false, align: "center", width: "32px" },
      { label: t("Компания"),   sortable: false, align: "left" },
      { label: "CFO",           sortable: true,  align: "right" },
      { label: "CFI",           sortable: true,  align: "right" },
      { label: "CFF",           sortable: true,  align: "right" },
      { label: "FCF",           sortable: true,  align: "right" },
      { label: t("Дивиденды"),  sortable: true,  align: "right" },
      { label: "CF/EBITDA",     sortable: true,  align: "right" },
    ];
  }
  return [
    { label: "#",               sortable: false, align: "center", width: "32px" },
    { label: t("Компания"),     sortable: false, align: "left" },
    { label: t("Тренд"),        sortable: false, align: "center", width: "60px" },
    { label: t("Выручка"),      sortable: true,  align: "right" },
    { label: t("Вал.маржа"),    sortable: true,  align: "right" },
    { label: "EBITDA",          sortable: true,  align: "right" },
    { label: t("EB маржа"),     sortable: true,  align: "right" },
    { label: t("Чист.приб."),   sortable: true,  align: "right" },
    { label: t("Чист.маржа"),   sortable: true,  align: "right" },
    { label: "Δ Rev",           sortable: true,  align: "right" },
  ];
});

function rowClick(co: string) {
  emit("row-click", co);
}
</script>

<template>
  <div class="fsb-card">
    <div class="fsb-head">
      <div class="fsb-eyebrow">{{ t("Скорборд") }}</div>
      <div class="fsb-title">{{ standard }} · {{ viewTab }} · FY {{ year }}</div>
    </div>

    <div class="fsb-scroll">
      <table class="fsb-tbl">
        <thead>
          <tr>
            <th v-for="(c, ci) in cols"
                :key="ci"
                :class="['fsb-th', `align-${c.align}`, {
                  's': sortCol === ci,
                  'sortable': c.sortable,
                }]"
                :style="c.width ? { width: c.width } : {}"
                @click="toggleSort(ci, c.sortable)">
              {{ t(c.label) }}
              <span v-if="c.sortable"
                    class="fsb-sort-arrow"
                    :class="{
                      'on': sortCol === ci,
                      'asc': sortCol === ci && sortDir === 'asc',
                    }">▲</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in sortedRows"
              :key="r.company_code"
              class="fsb-row"
              :style="{ animationDelay: Math.min(i * 25, 400) + 'ms' }"
              @click="rowClick(r.company_code)">
            <td class="fsb-rank">{{ r.rank }}</td>
            <td v-for="(cell, ci) in r.cells"
                :key="ci"
                :class="['fsb-cell', `align-${cell.align}`, { 'fsb-cell-s': ci === sortCol - 1 }]"
                v-html="cell.html" />
          </tr>
          <tr v-if="!sortedRows.length">
            <td :colspan="cols.length" class="fsb-empty">
              {{ t("Нет данных по этой выборке") }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.fsb-card {
  background: var(--card-bg, rgba(255, 255, 255, .82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(255, 255, 255, .70));
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, .07), 0 1px 3px rgba(15, 23, 60, .04);
  overflow: hidden;
  animation: finFadeSlideIn .4s ease 220ms both;
  display: flex;
  flex-direction: column;
}

.fsb-head {
  display: flex; align-items: baseline; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border, var(--border-input));
}
.fsb-eyebrow {
  font-size: 11px; font-weight: 600; color: #7F77DD;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.fsb-title {
  font-size: 11px; font-weight: 500; color: var(--t3, var(--t3));
  font-variant-numeric: tabular-nums;
}

.fsb-scroll {
  overflow-x: auto;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: #C8C7C0 transparent;
  max-height: 720px;
}
.fsb-scroll::-webkit-scrollbar { height: 10px; width: 10px; }
.fsb-scroll::-webkit-scrollbar-thumb { background: #C8C7C0; border-radius: 5px; }
.fsb-scroll::-webkit-scrollbar-thumb:hover { background: var(--t-muted); }
.fsb-scroll::-webkit-scrollbar-track { background: var(--bg2, #FAFAFC); }

.fsb-tbl {
  /* width:100% — таблица заполняет контейнер (нет пустоты справа на ≤14"):
     слабину забирает авто-колонка «Компания», числовые остаются плотными.
     При контенте шире контейнера table-layout:auto держит min-content →
     горизонтальный скролл .fsb-scroll сохраняется. */
  width: 100%;
  border-collapse: collapse;
  font-size: 10.5px;
}

.fsb-tbl thead tr {
  background: var(--bg3, #F1F5F9);
  position: sticky; top: 0; z-index: 1;
}

.fsb-th {
  padding: 6px 5px;
  font-size: 9px;
  font-weight: 600;
  color: var(--t3, var(--t3));
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
  border-bottom: 1px solid var(--border, var(--border-input));
  user-select: none;
}
.align-left   { text-align: left; }
.align-right  { text-align: right; }
.align-center { text-align: center; }

.fsb-th.sortable { cursor: pointer; transition: color .15s, background .15s; }
.fsb-th.sortable:hover { color: var(--t1, #1E2A4A); }
.fsb-th.s { color: var(--t1, #1E2A4A); background: rgba(127, 119, 221, .08); }

.fsb-sort-arrow {
  font-size: 9px;
  margin-left: 3px;
  display: inline-block;
  transition: opacity .2s, color .2s, transform .2s;
  transform: rotate(180deg);
  opacity: 0;
}
.fsb-th.sortable:hover .fsb-sort-arrow { opacity: .45; }
.fsb-sort-arrow.on { opacity: 1; color: #7F77DD; }
.fsb-sort-arrow.asc { transform: rotate(0); }

/* Подсветка отсортированного столбца */
.fsb-cell-s { background: rgba(127, 119, 221, .05); }

.fsb-row {
  cursor: pointer;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  transition: background .15s;
  animation: finFadeSlideIn .3s ease both;
}
.fsb-row:hover { background: var(--bg3, #F1F5F9); }

.fsb-cell {
  padding: 5px 6px;
  font-size: 11px;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
}

.fsb-rank {
  padding: 5px 6px;
  font-size: 11px;
  text-align: center;
  color: var(--t3, var(--t3));
  min-width: 28px;
  border-right: 1px solid var(--border, var(--border-input));
}

.fsb-empty {
  padding: 24px;
  text-align: center;
  color: var(--t3, var(--t3));
  font-style: italic;
}

@keyframes sparkDraw {
  to { stroke-dashoffset: 0; }
}
</style>
