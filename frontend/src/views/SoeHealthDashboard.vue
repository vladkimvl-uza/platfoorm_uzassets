<script setup lang="ts">
/**
 * SoeHealthDashboard — полноценный дашборд «SOE Health Check» (сайдбар Финансы).
 *
 * Структура зеркалит дашборды исходного инструмента (Portfolio Level /
 * Single Company Level): KPI-полоса → светофорная матрица → портфельный
 * уровень (Pareto по компаниям + тренды агрегатов) → дриллы по компании.
 *
 * Премиум: kpi-rail, staggered-появление, Odometer, SVG-бар-чарт с
 * анимацией роста и кумулятивной линией, спарклайны с draw-анимацией,
 * редактор порогов (dirty-guard) и дрилл-модалка компании.
 */
import { computed, inject, onMounted, ref, watch } from "vue";
import { api } from "@/api/client";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { usePermissions } from "@/composables/usePermissions";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import Odometer from "@/components/Odometer.vue";
import SoeHealthBoard, { type SoeHealthPayload } from "@/components/Financials/SoeHealthBoard.vue";
import SoeHealthParamsModal from "@/components/Financials/SoeHealthParamsModal.vue";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";

const finPerm = usePermissions("financials");

// Бургер как в FinTopFilters (инжект из AppShell): ≤1023 — drawer, иначе рейка.
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const CURRENT_FY = 2025;
const YEARS = Array.from({ length: 8 }, (_, i) => 2019 + i); // 2019..2026
const year = useSavedFilter<number>("soeHealth.year", CURRENT_FY);
const standard = useSavedFilter<"NSBU" | "IFRS">("soeHealth.standard", "NSBU");

const data = ref<SoeHealthPayload | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
let seq = 0;

async function load() {
  const my = ++seq;
  loading.value = true;
  error.value = null;
  try {
    const r = await api.get<SoeHealthPayload>("/financials/soe-health", {
      params: { year: year.value, standard: standard.value },
    });
    if (my !== seq) return;
    data.value = r.data;
  } catch (e: unknown) {
    if (my !== seq) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally {
    if (my === seq) loading.value = false;
  }
}
onMounted(() => { ensureFinancialsCss(); load(); });
watch([year, standard], load);

const paramsOpen = ref(false);
const pf = computed(() => data.value?.portfolio || null);

// ─── Портфельный уровень: Pareto по компаниям ──────────────────────
const PARETO_METRICS = [
  { value: "totalLiabilities", label: "Обязательства" },
  { value: "ebitda", label: "EBITDA" },
  { value: "debt", label: "Долг" },
] as const;
const paretoMetric = ref<string>("totalLiabilities");

interface ParetoBar { code: string; name: string; v: number; color: string; cum: number }
const paretoBars = computed<ParetoBar[]>(() => {
  const cos = (data.value?.companies || [])
    .map((c) => ({
      code: c.code, name: c.name,
      v: Number((c as { metrics_out?: Record<string, number | null> }).metrics_out?.[paretoMetric.value] ?? 0),
      color: c.sector_color || "#7F77DD",
    }))
    .filter((b) => b.v > 0)
    .sort((a, b) => b.v - a.v);
  const total = cos.reduce((s, b) => s + b.v, 0) || 1;
  let acc = 0;
  return cos.map((b) => { acc += b.v; return { ...b, cum: acc / total * 100 }; });
});
const paretoMax = computed(() => Math.max(1, ...paretoBars.value.map((b) => b.v)));

// SVG-геометрия Pareto
const PW = 960, PH = 300, PADL = 8, PADR = 40, PADT = 16, PADB = 44;
function barX(i: number): number {
  const n = paretoBars.value.length || 1;
  const w = (PW - PADL - PADR) / n;
  return PADL + i * w + w * 0.14;
}
function barW(): number {
  const n = paretoBars.value.length || 1;
  return ((PW - PADL - PADR) / n) * 0.72;
}
function barH(v: number): number { return (v / paretoMax.value) * (PH - PADT - PADB); }
function barY(v: number): number { return PH - PADB - barH(v); }
function cumPoints(): string {
  return paretoBars.value
    .map((b, i) => `${(barX(i) + barW() / 2).toFixed(1)},${(PADT + (1 - b.cum / 100) * (PH - PADT - PADB)).toFixed(1)}`)
    .join(" ");
}
function fmtBln(v: number): string {
  if (Math.abs(v) >= 1000) return (v / 1000).toLocaleString("ru", { maximumFractionDigits: 1 }) + " трлн";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 }) + " млрд";
}

// ─── Размер vs риск (scatter): x = обязательства (√-шкала), y = балл 1..5 ──
interface RiskDot { code: string; name: string; liab: number; overall: number; color: string }
const riskDots = computed<RiskDot[]>(() =>
  (data.value?.companies || [])
    .map((c) => ({
      code: c.code, name: c.name,
      liab: Number(c.metrics_out?.totalLiabilities ?? 0),
      overall: Number(c.overall ?? NaN),
      color: c.zone?.color || "#94A3B8",
    }))
    .filter((d) => d.liab > 0 && isFinite(d.overall)),
);
const SXW = 960, SXH = 300, SXL = 46, SXR = 16, SXT = 16, SXB = 40;
const liabMaxSqrt = computed(() => Math.sqrt(Math.max(1, ...riskDots.value.map((d) => d.liab))));
function scX(liab: number): number {
  return SXL + (Math.sqrt(liab) / liabMaxSqrt.value) * (SXW - SXL - SXR);
}
function scY(overall: number): number {
  // 1 (устойчиво) сверху → 5 (критично) снизу
  return SXT + ((overall - 1) / 4) * (SXH - SXT - SXB);
}

// ─── Разрезы по секторам ───────────────────────────────────────────
const SECTOR_METRICS = [
  { value: "totalLiabilities", label: "Обязательства" },
  { value: "totalAssets", label: "Активы" },
  { value: "revenue", label: "Выручка" },
  { value: "equity", label: "Капитал" },
] as const;
const sectorMetric = ref<string>("totalLiabilities");
interface SectorBar { code: string; name: string; color: string; v: number; pct: number }
const sectorBars = computed<SectorBar[]>(() => {
  const rows = (pf.value?.by_sector || [])
    .map((s) => ({ code: s.code, name: s.name, color: s.color,
                   v: Number((s as unknown as Record<string, number>)[sectorMetric.value] ?? 0) }))
    .filter((s) => s.v > 0)
    .sort((a, b) => b.v - a.v);
  const max = Math.max(1, ...rows.map((r) => r.v));
  return rows.map((r) => ({ ...r, pct: Math.max(2, (r.v / max) * 100) }));
});

const profitSplit = computed(() => pf.value?.profit_split || null);

// ─── Фискальная материальность (% ВВП) ─────────────────────────────
const FISCAL_ROWS = [
  { key: "totalAssets", label: "Активы", accent: "#7F77DD" },
  { key: "totalLiabilities", label: "Обязательства", accent: "#EF9F27" },
  { key: "revenue", label: "Выручка", accent: "#1D9E75" },
  { key: "debt", label: "Финансовый долг", accent: "#E24B4A" },
] as const;
const fiscalCards = computed(() => {
  const pct = pf.value?.pct_gdp; const tot = pf.value?.totals;
  if (!pct || !tot) return [];
  return FISCAL_ROWS.map((r) => ({
    label: r.label, accent: r.accent,
    pct: pct[r.key] ?? null, abs: tot[r.key] ?? null,
  }));
});
const gdpBln = computed(() => pf.value?.gdp_bln || null);
function fmtTrln(bln: number | null): string {
  if (bln == null) return "—";
  return (bln / 1000).toLocaleString("ru", { maximumFractionDigits: 0 }) + " трлн";
}

// ─── Комбо «Активы и ROA» / «Капитал и ROE» по секторам ────────────
const CW = 520, CH = 240, CL = 8, CR = 42, CT = 16, CB = 54;
interface ComboBar { name: string; color: string; bar: number; line: number | null;
  x: number; w: number; h: number; y: number; ly: number | null; lx: number }
interface ComboVM { bars: ComboBar[]; linePts: string; lmin: number; lmax: number; barMax: number }
function buildCombo(barKey: "totalAssets" | "equity", lineKey: "roa" | "roe"): ComboVM {
  const rows = (pf.value?.by_sector || [])
    .map((s) => ({ name: s.name, color: s.color, bar: Number(s[barKey] ?? 0), line: s[lineKey] }))
    .filter((s) => s.bar > 0)
    .sort((a, b) => b.bar - a.bar);
  const n = rows.length || 1;
  const barMax = Math.max(1, ...rows.map((r) => r.bar));
  const lvals = rows.map((r) => r.line).filter((v) => v != null) as number[];
  const lmax = lvals.length ? Math.max(...lvals) : 1;
  const lmin = Math.min(0, ...lvals, 0);
  const span = (lmax - lmin) || 1;
  const cw = (CW - CL - CR) / n, bw = cw * 0.64;
  const bars: ComboBar[] = rows.map((r, i) => {
    const x = CL + i * cw + cw * 0.18;
    const h = (r.bar / barMax) * (CH - CT - CB);
    const lx = x + bw / 2;
    const ly = r.line == null ? null : CT + (1 - (r.line - lmin) / span) * (CH - CT - CB);
    return { ...r, x, w: bw, h, y: CH - CB - h, lx, ly };
  });
  const linePts = bars.filter((b) => b.ly != null)
    .map((b) => `${b.lx.toFixed(1)},${(b.ly as number).toFixed(1)}`).join(" ");
  return { bars, linePts, lmin, lmax, barMax };
}
const comboAssets = computed(() => buildCombo("totalAssets", "roa"));
const comboEquity = computed(() => buildCombo("equity", "roe"));
function fmtPct(v: number | null): string {
  return v == null ? "—" : (v * 100).toFixed(1) + "%";
}

// ─── Пайчарты структуры портфеля (канон-донат CreditDonut) ─────────
const SECTOR_PALETTE = ["#7F77DD", "#1D9E75", "#EF9F27", "#378ADD", "#E24B4A",
                        "#8B7FFF", "#5DC093", "#E8590C", "#9AA0AE"];
const profitDonut = computed<DonutEntry[]>(() => {
  const p = profitSplit.value;
  if (!p) return [];
  const out: DonutEntry[] = [
    { label: "Прибыльные", color: "#1D9E75", value: p.profitable, sub: String(p.profitable) },
    { label: "Убыточные", color: "#E24B4A", value: p.loss, sub: String(p.loss) },
  ];
  if (p.unknown) out.push({ label: "Нет данных", color: "#C4C8D4", value: p.unknown, sub: String(p.unknown) });
  return out.filter((e) => e.value > 0);
});
const profitTotal = computed(() => {
  const p = profitSplit.value; return p ? p.profitable + p.loss + p.unknown : 0;
});
const sectorDonut = computed<DonutEntry[]>(() =>
  (pf.value?.by_sector || [])
    .filter((s) => s.count > 0)
    .map((s) => ({ label: s.name, color: s.color, value: s.count, sub: String(s.count) })),
);
const sectorTotal = computed(() =>
  (pf.value?.by_sector || []).reduce((a, s) => a + s.count, 0));
const legalDonut = computed<DonutEntry[]>(() =>
  (pf.value?.legal_form_split || [])
    .map((l, i) => ({ label: l.label, color: SECTOR_PALETTE[i % SECTOR_PALETTE.length],
                      value: l.count, sub: String(l.count) })),
);
const legalTotal = computed(() =>
  (pf.value?.legal_form_split || []).reduce((a, l) => a + l.count, 0));
const ownershipDonut = computed<DonutEntry[]>(() =>
  (pf.value?.ownership_split || [])
    .map((l, i) => ({ label: l.label, color: SECTOR_PALETTE[i % SECTOR_PALETTE.length],
                      value: l.count, sub: String(l.count) })),
);
const ownershipTotal = computed(() =>
  (pf.value?.ownership_split || []).reduce((a, l) => a + l.count, 0));
function donutHover(e: DonutEntry, total: number): [string, string] {
  return [String(e.value), total ? Math.round((e.value / total) * 100) + "%" : ""];
}

// ─── Тренды агрегатов (спарклайны) ─────────────────────────────────
const TRENDS = [
  { key: "roa", label: "ROA портфеля", fmt: "pct", accent: "#1D9E75" },
  { key: "roe", label: "ROE портфеля", fmt: "pct", accent: "#378ADD" },
  { key: "debtToEquity", label: "Долг / Капитал", fmt: "x", accent: "#EF9F27" },
  { key: "currentRatio", label: "Current Ratio", fmt: "x", accent: "#7F77DD" },
] as const;

interface TrendCard {
  key: string; label: string; accent: string;
  last: string; delta: string | null; deltaGood: boolean | null;
  points: string; area: string; lastXY: [number, number] | null;
}
const SW = 220, SH = 56;
const trendCards = computed<TrendCard[]>(() => {
  const s = data.value?.series;
  return TRENDS.map((t) => {
    const raw = (s?.ratios?.[t.key] || []) as (number | null)[];
    const vals = raw.map((v, i) => ({ v, i })).filter((p) => p.v != null) as { v: number; i: number }[];
    const fmtV = (v: number) => t.fmt === "pct" ? (v * 100).toFixed(1) + "%" : v.toFixed(2);
    let points = "", area = "", lastXY: [number, number] | null = null;
    if (vals.length >= 2) {
      const min = Math.min(...vals.map((p) => p.v));
      const max = Math.max(...vals.map((p) => p.v));
      const span = max - min || 1;
      const n = raw.length - 1 || 1;
      const xy = vals.map((p) => [
        6 + (p.i / n) * (SW - 12),
        6 + (1 - (p.v - min) / span) * (SH - 12),
      ] as [number, number]);
      points = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
      area = `${xy[0][0].toFixed(1)},${SH - 2} ` + points + ` ${xy[xy.length - 1][0].toFixed(1)},${SH - 2}`;
      lastXY = xy[xy.length - 1];
    }
    const last = vals.length ? fmtV(vals[vals.length - 1].v) : "—";
    let delta: string | null = null, deltaGood: boolean | null = null;
    if (vals.length >= 2) {
      const d = vals[vals.length - 1].v - vals[vals.length - 2].v;
      const goodUp = t.key !== "debtToEquity";  // рост долга/капитала — плохо
      deltaGood = goodUp ? d >= 0 : d <= 0;
      delta = (d >= 0 ? "+" : "") + (t.fmt === "pct" ? (d * 100).toFixed(1) + " п.п." : d.toFixed(2));
    }
    return { key: t.key, label: t.label, accent: t.accent, last, delta, deltaGood, points, area, lastXY };
  });
});
const seriesYears = computed(() => data.value?.series?.years || []);
</script>

<template>
  <div class="sh-page">
    <!-- ═══ Топбар — тёмная плашка в стиле financials (FinTopFilters) ═══ -->
    <header class="sh-bar">
      <button class="sh-burger" @click="onBurger()" title="Меню / свернуть сайдбар">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <div class="sh-head">
        <div class="sh-eyebrow">ФИНАНСЫ · ЗДОРОВЬЕ ПОРТФЕЛЯ</div>
        <div class="sh-title-row">
          <span class="sh-title">SOE Health Check Tool</span>
          <span class="sh-sub">
            RAG-оценка устойчивости · <strong>{{ standard }}</strong> · FY {{ year }}
            <span v-if="data?.params_overridden" class="sh-ovr-badge" title="Пороги изменены относительно методики">пороги настроены</span>
          </span>
        </div>
      </div>

      <div class="sh-cluster">
        <div class="sh-tabs uza-seg on-dark" title="Стандарт отчётности">
          <button class="uza-seg-btn" :class="{ on: standard === 'NSBU' }" @click="standard = 'NSBU'">НСБУ</button>
          <button class="uza-seg-btn" :class="{ on: standard === 'IFRS' }" @click="standard = 'IFRS'">МСФО</button>
        </div>
        <div class="sh-div" aria-hidden="true"></div>
        <UzaYearStepper tone="dark" :model-value="year" :years="YEARS" prefix="FY "
                        @update:model-value="year = ($event as number) ?? year" />
        <div class="sh-div" aria-hidden="true"></div>
        <button v-if="finPerm.canEdit.value" class="sh-params-btn" type="button" @click="paramsOpen = true"
                title="Редактор порогов риска">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          Пороги
        </button>
      </div>
    </header>

    <!-- Состояния -->
    <div v-if="loading && !data" class="sh-state">
      <div class="sh-skel" v-for="i in 3" :key="i" :style="{ '--d': (i * 90) + 'ms' }" />
    </div>
    <div v-else-if="error && !data" class="sh-state sh-err">
      {{ error }}
      <button class="sh-retry" type="button" @click="load">Повторить</button>
    </div>

    <template v-else-if="data">
      <!-- ═══ KPI + матрица ═══ -->
      <section class="sh-section">
        <SoeHealthBoard :data="data" />
      </section>

      <!-- ═══ Фискальная материальность (% ВВП) ═══ -->
      <section v-if="fiscalCards.length" class="sh-section">
        <div class="sh-card sh-fiscal" style="--d:40ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">Фискальная материальность · % ВВП</div>
            <div class="sh-card-s">
              портфель к номинальному ВВП · ВВП FY{{ data.year }} = {{ fmtTrln(gdpBln) }} сум
              <span class="sh-gdp-src">IMF WEO · ред.</span>
            </div>
          </div></div>
          <div class="sh-fiscal-grid">
            <div v-for="(f, i) in fiscalCards" :key="f.label" class="sh-fiscal-i"
                 :style="{ '--accent': f.accent, '--d': (i * 70) + 'ms' }">
              <div class="sh-fiscal-l">{{ f.label }}</div>
              <div class="sh-fiscal-v">
                <span v-if="f.pct != null">{{ f.pct.toFixed(1) }}<span class="sh-fiscal-u">% ВВП</span></span>
                <span v-else>—</span>
              </div>
              <div class="sh-fiscal-abs">{{ fmtTrln(f.abs) }} сум</div>
            </div>
          </div>
        </div>
      </section>

      <!-- ═══ Структура портфеля: пайчарты (канон-донат) ═══ -->
      <section class="sh-section sh-4col">
        <div class="sh-card" style="--d:60ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">Прибыльные компании</div>
            <div class="sh-card-s">по знаку чистой прибыли · FY {{ data.year }}</div>
          </div></div>
          <CreditDonut v-if="profitDonut.length" :entries="profitDonut"
            :center-value="String(profitTotal)" center-label="компаний"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">нет данных</div>
        </div>
        <div class="sh-card" style="--d:140ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">Компании по секторам</div>
            <div class="sh-card-s">распределение портфеля</div>
          </div></div>
          <CreditDonut v-if="sectorDonut.length" :entries="sectorDonut"
            :center-value="String(sectorTotal)" center-label="компаний"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">нет данных</div>
        </div>
        <div class="sh-card" style="--d:220ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">Орг-правовая форма</div>
            <div class="sh-card-s">по типу юрлица</div>
          </div></div>
          <CreditDonut v-if="legalDonut.length" :entries="legalDonut"
            :center-value="String(legalTotal)" center-label="компаний"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">нет данных</div>
        </div>
        <div class="sh-card" style="--d:300ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">Орган управления</div>
            <div class="sh-card-s">собственник / надзорный орган</div>
          </div></div>
          <CreditDonut v-if="ownershipDonut.length" :entries="ownershipDonut"
            :center-value="String(ownershipTotal)" center-label="компаний"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">нет данных</div>
        </div>
      </section>

      <!-- ═══ Портфельный уровень: Pareto ═══ -->
      <section class="sh-section sh-grid">
        <div class="sh-card sh-pareto" style="--d:80ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">Концентрация портфеля</div>
              <div class="sh-card-s">компании по убыванию · линия — накопленная доля</div>
            </div>
            <UzaSegment
              :model-value="paretoMetric"
              :options="PARETO_METRICS as never"
              size="sm"
              @update:model-value="paretoMetric = $event as string"
            />
          </div>
          <div v-if="paretoBars.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${PW} ${PH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <!-- сетка -->
              <line v-for="f in [0.25, 0.5, 0.75]" :key="f"
                    :x1="PADL" :x2="PW - PADR"
                    :y1="PADT + (1 - f) * (PH - PADT - PADB)" :y2="PADT + (1 - f) * (PH - PADT - PADB)"
                    class="sh-grid-line" />
              <!-- бары -->
              <!-- единый бренд-пурпур (канон: без секторной радуги) -->
              <defs>
                <linearGradient id="shBarGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="#8B7FFF" />
                  <stop offset="100%" stop-color="#6C5CE7" />
                </linearGradient>
              </defs>
              <g v-for="(b, i) in paretoBars" :key="b.code">
                <rect :x="barX(i)" :y="barY(b.v)" :width="barW()" :height="barH(b.v)"
                      fill="url(#shBarGrad)" rx="4" class="sh-bar" :style="{ '--d': (i * 40) + 'ms' }">
                  <title>{{ b.name }} · {{ fmtBln(b.v) }} · накоплено {{ b.cum.toFixed(0) }}%</title>
                </rect>
                <text :x="barX(i) + barW() / 2" :y="PH - PADB + 14" class="sh-bar-lbl"
                      text-anchor="middle">{{ b.code.toUpperCase() }}</text>
              </g>
              <!-- кумулятивная линия -->
              <polyline :points="cumPoints()" class="sh-cum-line" fill="none" />
              <circle v-for="(b, i) in paretoBars" :key="'c' + b.code"
                      :cx="barX(i) + barW() / 2"
                      :cy="PADT + (1 - b.cum / 100) * (PH - PADT - PADB)"
                      r="3" class="sh-cum-dot" :style="{ '--d': (i * 40 + 300) + 'ms' }">
                <title>{{ b.name }} · накоплено {{ b.cum.toFixed(0) }}%</title>
              </circle>
              <!-- правая ось % -->
              <text v-for="f in [0, 50, 100]" :key="'p' + f"
                    :x="PW - PADR + 6" :y="PADT + (1 - f / 100) * (PH - PADT - PADB) + 3"
                    class="sh-axis-lbl">{{ f }}%</text>
            </svg>
          </div>
          <div v-else class="sh-none">Нет данных за {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Размер vs риск + разрезы по секторам ═══ -->
      <section class="sh-section sh-2col">
        <!-- Scatter: обязательства × балл риска -->
        <div class="sh-card" style="--d:80ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">Размер обязательств и риск</div>
              <div class="sh-card-s">ось X — обязательства (√-шкала) · ось Y — балл 1→5 · правый-низ = крупные и рисковые</div>
            </div>
          </div>
          <div v-if="riskDots.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${SXW} ${SXH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <!-- зоны балла (горизонтальные полосы) -->
              <line v-for="s in [1,2,3,4,5]" :key="'g'+s"
                    :x1="SXL" :x2="SXW - SXR" :y1="scY(s)" :y2="scY(s)" class="sh-grid-line" />
              <text v-for="s in [1,2,3,4,5]" :key="'gl'+s"
                    :x="SXL - 8" :y="scY(s) + 3" text-anchor="end" class="sh-axis-lbl">{{ s }}</text>
              <!-- точки компаний -->
              <g v-for="(d, i) in riskDots" :key="d.code">
                <circle :cx="scX(d.liab)" :cy="scY(d.overall)" r="7"
                        :fill="d.color" fill-opacity="0.82" stroke="#fff" stroke-width="1.5"
                        class="sh-dot" :style="{ '--d': (i * 30) + 'ms' }">
                  <title>{{ d.name }} · балл {{ d.overall.toFixed(1) }} · обяз. {{ fmtBln(d.liab) }}</title>
                </circle>
                <text :x="scX(d.liab)" :y="scY(d.overall) - 10" text-anchor="middle"
                      class="sh-dot-lbl">{{ d.code.toUpperCase() }}</text>
              </g>
            </svg>
          </div>
          <div v-else class="sh-none">Нет данных за {{ data.year }} ({{ data.standard }})</div>
        </div>

        <!-- Разрезы по секторам -->
        <div class="sh-card" style="--d:160ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">Разрез по секторам</div>
              <div class="sh-card-s" v-if="profitSplit">
                прибыльные {{ profitSplit.profitable }} · убыточные {{ profitSplit.loss }}
                <span v-if="profitSplit.unknown">· н/д {{ profitSplit.unknown }}</span>
              </div>
            </div>
            <UzaSegment
              :model-value="sectorMetric"
              :options="SECTOR_METRICS as never"
              size="sm"
              @update:model-value="sectorMetric = $event as string"
            />
          </div>
          <div v-if="sectorBars.length" class="sh-secwrap">
            <div v-for="(s, i) in sectorBars" :key="s.code" class="sh-sec-row"
                 :style="{ '--d': (i * 60) + 'ms' }">
              <span class="sh-sec-name" :title="s.name">{{ s.name }}</span>
              <div class="sh-sec-track">
                <div class="sh-sec-fill" :style="{ width: s.pct + '%', background: s.color }" />
              </div>
              <span class="sh-sec-val">{{ fmtBln(s.v) }}</span>
            </div>
          </div>
          <div v-else class="sh-none">Нет данных за {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Активы/Капитал и рентабельность по секторам (комбо) ═══ -->
      <section class="sh-section sh-2col">
        <div v-for="cfg in [
               { key: 'a', vm: comboAssets, t: 'Активы и ROA', s: 'столбцы — активы (млрд) · линия — рентабельность активов', accent: '#1D9E75' },
               { key: 'e', vm: comboEquity, t: 'Капитал и ROE', s: 'столбцы — капитал (млрд) · линия — рентабельность капитала', accent: '#378ADD' },
             ]" :key="cfg.key" class="sh-card" :style="{ '--d': (cfg.key === 'a' ? 80 : 160) + 'ms' }">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ cfg.t }}</div>
            <div class="sh-card-s">{{ cfg.s }}</div>
          </div></div>
          <div v-if="cfg.vm.bars.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${CW} ${CH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <line v-for="f in [0.25,0.5,0.75]" :key="f" :x1="CL" :x2="CW-CR"
                    :y1="CT+(1-f)*(CH-CT-CB)" :y2="CT+(1-f)*(CH-CT-CB)" class="sh-grid-line" />
              <g v-for="(b, i) in cfg.vm.bars" :key="b.name">
                <rect :x="b.x" :y="b.y" :width="b.w" :height="b.h" :fill="b.color" rx="4"
                      class="sh-bar" :style="{ '--d': (i*50)+'ms' }">
                  <title>{{ b.name }} · {{ fmtBln(b.bar) }} · {{ fmtPct(b.line) }}</title>
                </rect>
                <text :x="b.lx" :y="CH-CB+13" text-anchor="middle" class="sh-bar-lbl">
                  {{ b.name.length > 10 ? b.name.slice(0,9)+'…' : b.name }}
                </text>
              </g>
              <polyline v-if="cfg.vm.linePts" :points="cfg.vm.linePts" fill="none"
                        :stroke="cfg.accent" stroke-width="2.5" stroke-linecap="round"
                        stroke-linejoin="round" class="sh-combo-line" />
              <circle v-for="(b, i) in cfg.vm.bars.filter(x => x.ly != null)" :key="'d'+i"
                      :cx="b.lx" :cy="b.ly!" r="3.5" :fill="cfg.accent" class="sh-cum-dot"
                      :style="{ '--d': (i*50+300)+'ms' }" />
              <text v-for="f in [0,0.5,1]" :key="'ax'+f" :x="CW-CR+6"
                    :y="CT+(1-f)*(CH-CT-CB)+3" class="sh-axis-lbl">
                {{ ((cfg.vm.lmin + f*(cfg.vm.lmax-cfg.vm.lmin))*100).toFixed(0) }}%
              </text>
            </svg>
          </div>
          <div v-else class="sh-none">Нет данных за {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Тренды агрегатов ═══ -->
      <section class="sh-section">
        <div class="sh-trends">
          <div v-for="(t, i) in trendCards" :key="t.key" class="sh-card sh-trend"
               :style="{ '--accent': t.accent, '--d': (i * 70) + 'ms' }">
            <div class="sh-trend-l">{{ t.label }}</div>
            <div class="sh-trend-v">
              <Odometer :value="t.last" />
              <span v-if="t.delta" class="sh-trend-d"
                    :style="{ color: t.deltaGood ? '#1D9E75' : '#E24B4A' }">{{ t.delta }}</span>
            </div>
            <svg v-if="t.points" :viewBox="`0 0 ${SW} ${SH}`" class="sh-spark">
              <polygon :points="t.area" :fill="t.accent" opacity="0.10" />
              <polyline :points="t.points" fill="none" :stroke="t.accent" stroke-width="2"
                        stroke-linecap="round" stroke-linejoin="round" class="sh-spark-line" />
              <circle v-if="t.lastXY" :cx="t.lastXY[0]" :cy="t.lastXY[1]" r="3.4"
                      :fill="t.accent" class="sh-spark-dot" />
            </svg>
            <div v-else class="sh-none sm">мало данных</div>
            <div class="sh-trend-yrs">{{ seriesYears[0] }}–{{ seriesYears[seriesYears.length - 1] }}</div>
          </div>
        </div>
      </section>
    </template>

    <SoeHealthParamsModal
      :open="paramsOpen"
      :ratios="data?.ratios_meta || []"
      @close="paramsOpen = false"
      @saved="paramsOpen = false; load()"
    />
  </div>
</template>

<style scoped>
/* Компоновка как в financials (.fd-page): бар примыкает full-bleed,
   секции — с собственными боковыми отступами */
.sh-page { padding: 0 0 32px; max-width: none; margin: 0; display: flex; flex-direction: column; gap: 12px; }
.sh-section, .sh-state { margin: 0 14px; }

/* ── Топбар — 1:1 стиль financials (.ft-bar: градиент #1E2A4A → #182039) ── */
.sh-bar {
  display: flex; align-items: center; gap: 14px; row-gap: 10px; flex-wrap: wrap;
  padding: 10px 16px; min-height: 52px;
  background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%);
  color: #fff;
  /* цельно с сайдбаром: слева без радиуса (нет светлой выемки), без анимаций */
  border-radius: 0 12px 12px 0;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.15);
  animation: none !important;
  transition: none;
}
.sh-burger {
  width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0;
  border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.85); cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  transition: background .15s ease, border-color .15s ease, transform .16s ease;
}
.sh-burger:hover { background: rgba(255,255,255,.14); border-color: rgba(255,255,255,.22); color: #fff; }
.sh-burger:active { transform: scale(.94); }
/* 1:1 значения из FinTopFilters (.ft-head/.ft-div/.ft-cluster) */
.sh-head { flex: 1 1 280px; min-width: 0; display: flex; flex-direction: column; gap: 1px; overflow: hidden; }
.sh-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: rgba(255,255,255,.55); }
.sh-title-row { display: flex; align-items: baseline; gap: 10px; min-width: 0; flex-wrap: wrap; row-gap: 2px; }
.sh-title { font-size: 19px; font-weight: 500; letter-spacing: -.01em; color: #fff; line-height: 1.15; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 0 1 auto; min-width: 0; }
.sh-sub { font-size: 12px; color: rgba(255,255,255,.65); line-height: 1.45; flex: 1 1 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sh-sub strong { color: #fff; font-weight: 500; }
.sh-ovr-badge { margin-left: 7px; font-size: 9px; font-weight: 700; color: #FFD9A0; background: rgba(239,159,39,.22); border-radius: 5px; padding: 1px 6px; letter-spacing: .03em; }
.sh-cluster { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; row-gap: 6px; flex: 0 1 auto; min-width: 0; margin-left: auto; }
@media (max-width: 1440px) { .sh-cluster { flex: 1 1 100%; margin-left: 0; justify-content: flex-start; row-gap: 8px; } }
.sh-div { width: 1px; height: 20px; background: rgba(255,255,255,.12); margin: 0 2px; flex-shrink: 0; }
.sh-params-btn {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; font-family: inherit; color: rgba(255,255,255,.88);
  background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.16); border-radius: 9px;
  padding: 7px 13px; cursor: pointer; transition: all .15s ease;
}
.sh-params-btn:hover { background: rgba(255,255,255,.15); border-color: rgba(255,255,255,.28); transform: translateY(-1px); }

/* ── Состояния ── */
.sh-state { display: flex; flex-direction: column; gap: 10px; padding: 8px 0; }
.sh-skel { height: 96px; border-radius: 14px; background: linear-gradient(90deg, #F1F0F7 25%, #FAF9FE 50%, #F1F0F7 75%); background-size: 200% 100%; animation: shShimmer 1.4s ease-in-out var(--d, 0ms) infinite; }
@keyframes shShimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.sh-err { align-items: center; color: #E24B4A; font-size: 12.5px; flex-direction: row; gap: 12px; }
.sh-retry { font-size: 12px; font-weight: 600; font-family: inherit; border: 1px solid var(--border-hard, #E5E7EB); background: #fff; border-radius: 9px; padding: 6px 14px; cursor: pointer; }

.sh-section { animation: shSecIn .5s var(--ease-standard, ease) both; }
@keyframes shSecIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

/* ── Карточки ── */
.sh-card {
  background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 2px 12px rgba(15,23,60,.07), 0 1px 3px rgba(15,23,60,.04);
  animation: finKpiCardIn .55s var(--ease-standard, ease) var(--d, 0ms) both;
  position: relative; overflow: hidden;
}
.sh-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both; transform-origin: left center; }
.sh-card-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.sh-card-t { font-size: 13px; font-weight: 650; color: var(--t1, #1E2A4A); }
.sh-card-s { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 2px; }
.sh-none { padding: 26px; text-align: center; color: var(--t3, #94A3B8); font-size: 12px; }
.sh-none.sm { padding: 10px; font-size: 10.5px; }

/* ── Pareto ── */
.sh-grid { display: grid; }
.sh-pareto-svgwrap { overflow-x: auto; }
.sh-pareto-svg { width: 100%; min-width: 640px; height: auto; display: block; }
.sh-grid-line { stroke: rgba(30,42,74,.07); stroke-width: 1; }
.sh-bar { transform-origin: center bottom; transform-box: fill-box; animation: shBarGrow .6s var(--ease-standard, ease) var(--d, 0ms) both; cursor: default; transition: filter .15s; }
.sh-bar:hover { filter: brightness(1.1) saturate(1.2); }
@keyframes shBarGrow { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.sh-bar-lbl { font-size: 9px; font-weight: 600; fill: var(--t3, #94A3B8); letter-spacing: .02em; }
.sh-cum-line { stroke: var(--p-deep, #534AB7); stroke-width: 2; stroke-dasharray: 1400; stroke-dashoffset: 1400; animation: shLineDraw 1.2s ease .35s forwards; }
.sh-combo-line { stroke-dasharray: 1200; stroke-dashoffset: 1200; animation: shLineDraw 1.1s ease .4s forwards; }
@keyframes shLineDraw { to { stroke-dashoffset: 0; } }
.sh-cum-dot { fill: #fff; stroke: var(--p-deep, #534AB7); stroke-width: 2; opacity: 0; animation: shDotIn .3s ease var(--d, 0ms) forwards; }
@keyframes shDotIn { to { opacity: 1; } }
.sh-axis-lbl { font-size: 9px; fill: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }

/* ── Фискальная материальность ── */
.sh-gdp-src { margin-left: 6px; font-size: 8.5px; font-weight: 700; color: var(--t3, #94A3B8);
  background: rgba(127,119,221,.1); border-radius: 4px; padding: 1px 5px; letter-spacing: .03em; }
.sh-fiscal-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 6px; }
@media (max-width: 900px) { .sh-fiscal-grid { grid-template-columns: repeat(2, 1fr); } }
.sh-fiscal-i { padding: 12px 14px; border-radius: 12px; background: var(--bg2, #FAFAFD);
  position: relative; overflow: hidden; animation: finKpiCardIn .5s var(--ease-standard) var(--d, 0ms) both; }
.sh-fiscal-i::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both;
  transform-origin: left center; }
.sh-fiscal-l { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.sh-fiscal-v { font-size: 26px; font-weight: 400; letter-spacing: -.03em; color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums; margin: 4px 0 2px; }
.sh-fiscal-u { font-size: 11px; color: var(--t3, #94A3B8); font-weight: 500; margin-left: 3px; }
.sh-fiscal-abs { font-size: 11px; color: var(--t2, #4B5468); font-variant-numeric: tabular-nums; }

/* ── Структура: паи ── */
.sh-4col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
@media (max-width: 1400px) { .sh-4col { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 700px) { .sh-4col { grid-template-columns: 1fr; } }

/* ── Размер×риск + секторы ── */
.sh-2col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
@media (max-width: 1100px) { .sh-2col { grid-template-columns: 1fr; } }
.sh-dot { transform-origin: center; transform-box: fill-box; cursor: default;
  animation: shDotPop .45s var(--ease-standard, ease) var(--d, 0ms) both; transition: fill-opacity .15s; }
.sh-dot:hover { fill-opacity: 1; }
@keyframes shDotPop { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.sh-dot-lbl { font-size: 8px; font-weight: 600; fill: var(--t3, #94A3B8); letter-spacing: .02em;
  pointer-events: none; opacity: 0; animation: shDotIn .3s ease .4s forwards; }
.sh-secwrap { display: flex; flex-direction: column; gap: 9px; padding-top: 4px; }
.sh-sec-row { display: grid; grid-template-columns: 120px 1fr max-content; align-items: center; gap: 10px;
  animation: shSecRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes shSecRowIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.sh-sec-name { font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sh-sec-track { height: 9px; background: rgba(127,119,221,.08); border-radius: 5px; overflow: hidden; }
.sh-sec-fill { height: 100%; border-radius: 5px; transition: width .6s var(--ease-standard, ease);
  animation: shSecGrow .7s var(--ease-standard, ease) var(--d, 0ms) both; transform-origin: left center; }
@keyframes shSecGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.sh-sec-val { font-size: 11px; font-weight: 600; color: var(--t2, #4B5468);
  font-variant-numeric: tabular-nums; white-space: nowrap; }

/* ── Тренды ── */
.sh-trends { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
@media (max-width: 1100px) { .sh-trends { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 560px) { .sh-trends { grid-template-columns: 1fr; } }
.sh-trend { display: flex; flex-direction: column; gap: 6px; }
.sh-trend-l { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.sh-trend-v { font-size: 24px; font-weight: 400; letter-spacing: -.03em; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 8px; }
.sh-trend-d { font-size: 11px; font-weight: 700; }
.sh-spark { width: 100%; height: 56px; }
.sh-spark-line { stroke-dasharray: 480; stroke-dashoffset: 480; animation: shLineDraw 1s ease .25s forwards; }
.sh-spark-dot { opacity: 0; animation: shDotIn .3s ease 1.1s forwards; }
.sh-trend-yrs { font-size: 9.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }

@media (max-width: 720px) { .sh-section, .sh-state { margin: 0 8px; } .sh-title { font-size: 15px; } }
</style>
