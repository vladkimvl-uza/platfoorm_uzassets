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
import SoeHealthBoard, { type SoeHealthPayload, type SoeCompany } from "@/components/Financials/SoeHealthBoard.vue";
import SoeHealthParamsModal from "@/components/Financials/SoeHealthParamsModal.vue";
import SoeHealthDrillModal from "@/components/Financials/SoeHealthDrillModal.vue";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t: tr } = useI18n();
const t = tr;


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
    error.value = err?.response?.data?.detail || err?.message || tr('Не удалось загрузить');
  } finally {
    if (my === seq) loading.value = false;
  }
}
onMounted(() => { ensureFinancialsCss(); load(); });
watch([year, standard], load);

const paramsOpen = ref(false);
const pf = computed(() => data.value?.portfolio || null);

// Дрилл компании из графиков (скаттер) + кросс-фильтр по сектору
const drillCompany = ref<SoeCompany | null>(null);
function openCompany(code: string) {
  drillCompany.value = (data.value?.companies || []).find((c) => c.code === code) || null;
}
const focusSector = ref<string | null>(null);
function toggleSector(code: string | null) {
  focusSector.value = focusSector.value === code ? null : code;
}

// ─── Портфельный уровень: Pareto по компаниям ──────────────────────
const PARETO_METRICS = [
  { value: "totalLiabilities", label: i18nKey("Обязательства") },
  { value: "ebitda", label: "EBITDA" },
  { value: "debt", label: i18nKey("Долг") },
] as const;
const paretoMetric = ref<string>("totalLiabilities");

interface ParetoBar { code: string; name: string; v: number; color: string; cum: number; sector: string }
const paretoBars = computed<ParetoBar[]>(() => {
  const cos = (data.value?.companies || [])
    .map((c) => ({
      code: c.code, name: c.name,
      v: Number((c as { metrics_out?: Record<string, number | null> }).metrics_out?.[paretoMetric.value] ?? 0),
      color: c.sector_color || "#7F77DD",
      sector: c.sector_code || "",
    }))
    .filter((b) => b.v > 0)
    .sort((a, b) => b.v - a.v);
  const total = cos.reduce((s, b) => s + b.v, 0) || 1;
  let acc = 0;
  return cos.map((b) => { acc += b.v; return { ...b, cum: acc / total * 100 }; });
});
const paretoMax = computed(() => Math.max(1, ...paretoBars.value.map((b) => b.v)));
// доля топ-3 компаний в портфеле (смысл «концентрации» без кумул-линии)
const top3Pct = computed(() => {
  const b = paretoBars.value; if (!b.length) return 0;
  return b[Math.min(2, b.length - 1)].cum;
});

// Вертикальная геометрия Pareto (ранжированные столбцы с подписями)
const PW = 960, PH = 260, PL = 10, PR = 12, PT = 26, PB = 42;
function pX(i: number): number {
  const n = paretoBars.value.length || 1; const w = (PW - PL - PR) / n;
  return PL + i * w + w * 0.26;
}
function pW(): number {
  const n = paretoBars.value.length || 1; return ((PW - PL - PR) / n) * 0.48;
}
function pH(v: number): number { return (v / paretoMax.value) * (PH - PT - PB); }
function pY(v: number): number { return PH - PB - pH(v); }
// подпись значения над столбцом — всё в трлн, единый масштаб
function barLabel(vBln: number): string {
  const t = vBln / 1000;
  return t >= 10 ? t.toFixed(0) : t.toFixed(1);
}

function fmtBln(v: number): string {
  if (Math.abs(v) >= 1000) return tr('{value0} трлн', { value0: (v / 1000).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 1 }) });
  return tr('{value0} млрд', { value0: v.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 0 }) });
}

// ─── Размер vs риск (scatter): x = обязательства (√-шкала), y = балл 1..5 ──
interface RiskDot { code: string; name: string; liab: number; overall: number; color: string; sector: string }
const riskDots = computed<RiskDot[]>(() =>
  (data.value?.companies || [])
    .map((c) => ({
      code: c.code, name: c.name,
      liab: Number(c.metrics_out?.totalLiabilities ?? 0),
      overall: Number(c.overall ?? NaN),
      color: c.zone?.color || "#94A3B8",
      sector: c.sector_code || "",
    }))
    .filter((d) => d.liab > 0 && isFinite(d.overall)),
);
function dotDimmed(d: RiskDot): boolean {
  return focusSector.value != null && d.sector !== focusSector.value;
}
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
  { value: "totalLiabilities", label: i18nKey("Обязательства") },
  { value: "totalAssets", label: i18nKey("Активы") },
  { value: "revenue", label: i18nKey("Выручка") },
  { value: "equity", label: i18nKey("Капитал") },
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
  { key: "totalAssets", label: i18nKey("Активы"), accent: "#7F77DD" },
  { key: "totalLiabilities", label: i18nKey("Обязательства"), accent: "#EF9F27" },
  { key: "revenue", label: i18nKey("Выручка"), accent: "#1D9E75" },
  { key: "debt", label: i18nKey("Финансовый долг"), accent: "#E24B4A" },
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
  return tr('{value0} трлн', { value0: (bln / 1000).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 0 }) });
}

// ─── Комбо «Активы и ROA» / «Капитал и ROE» по секторам (верт. бары) ──
interface ComboRow { code: string; name: string; color: string; bar: number; ret: number | null }
interface ComboVM { rows: ComboRow[]; barMax: number }
function buildCombo(barKey: "totalAssets" | "equity", lineKey: "roa" | "roe"): ComboVM {
  const rows = (pf.value?.by_sector || [])
    .map((s) => ({ code: s.code, name: s.name, color: s.color,
                   bar: Number(s[barKey] ?? 0), ret: s[lineKey] }))
    .filter((s) => s.bar > 0)
    .sort((a, b) => b.bar - a.bar);
  return { rows, barMax: Math.max(1, ...rows.map((r) => r.bar)) };
}
const comboAssets = computed(() => buildCombo("totalAssets", "roa"));
const comboEquity = computed(() => buildCombo("equity", "roe"));
// Вертикальная геометрия комбо (тонкие бары + рентабельность подписью над баром)
const CW = 520, CH = 230, CL = 10, CR = 12, CT = 26, CB = 44;
function cX(i: number, n: number): number { const w = (CW - CL - CR) / n; return CL + i * w + w * 0.30; }
function cW(n: number): number { return ((CW - CL - CR) / n) * 0.40; }
function cH(v: number, max: number): number { return (v / max) * (CH - CT - CB); }
function cY(v: number, max: number): number { return CH - CB - cH(v, max); }
function cutName(s: string): string { return s.length > 11 ? s.slice(0, 10) + "…" : s; }
function fmtPct(v: number | null): string {
  return v == null ? "—" : (v * 100).toFixed(1) + "%";
}
function retColor(v: number | null): string {
  if (v == null) return "#9AA0AE";
  return v >= 0 ? "#1D9E75" : "#E24B4A";
}

// ─── Пайчарты структуры портфеля (канон-донат CreditDonut) ─────────
const SECTOR_PALETTE = ["#7F77DD", "#1D9E75", "#EF9F27", "#378ADD", "#E24B4A",
                        "#8B7FFF", "#5DC093", "#E8590C", "#9AA0AE"];
const profitDonut = computed<DonutEntry[]>(() => {
  const p = profitSplit.value;
  if (!p) return [];
  const out: DonutEntry[] = [
    { label: i18nKey("Прибыльные"), color: "#1D9E75", value: p.profitable, sub: String(p.profitable) },
    { label: i18nKey("Убыточные"), color: "#E24B4A", value: p.loss, sub: String(p.loss) },
  ];
  if (p.unknown) out.push({ label: i18nKey("Нет данных"), color: "#C4C8D4", value: p.unknown, sub: String(p.unknown) });
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
const sectorDonutCodes = computed(() =>
  (pf.value?.by_sector || []).filter((s) => s.count > 0).map((s) => s.code));
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
  { key: "roa", label: i18nKey("ROA портфеля"), fmt: "pct", accent: "#1D9E75" },
  { key: "roe", label: i18nKey("ROE портфеля"), fmt: "pct", accent: "#378ADD" },
  { key: "debtToEquity", label: i18nKey("Долг / Капитал"), fmt: "x", accent: "#EF9F27" },
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
      delta = (d >= 0 ? "+" : "") + (t.fmt === "pct" ? tr("{value} п.п.", { value: (d * 100).toFixed(1) }) : d.toFixed(2));
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
      <button class="sh-burger" @click="onBurger()" :title="tr('Меню / свернуть сайдбар')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>

      <div class="sh-head">
        <div class="sh-eyebrow">{{ tr('ФИНАНСЫ · ЗДОРОВЬЕ ПОРТФЕЛЯ') }}</div>
        <div class="sh-title-row">
          <span class="sh-title">SOE Health Check Tool</span>
          <span class="sh-sub">
            {{ tr('RAG-оценка устойчивости ·') }} <strong>{{ standard }}</strong> · FY {{ year }}
            <span v-if="data?.params_overridden" class="sh-ovr-badge" :title="tr('Пороги изменены относительно методики')">{{ tr('пороги настроены') }}</span>
          </span>
        </div>
      </div>

      <div class="sh-cluster">
        <div class="sh-tabs uza-seg on-dark" :title="tr('Стандарт отчётности')">
          <button class="uza-seg-btn" :class="{ on: standard === 'NSBU' }" @click="standard = 'NSBU'">{{ tr('НСБУ') }}</button>
          <button class="uza-seg-btn" :class="{ on: standard === 'IFRS' }" @click="standard = 'IFRS'">{{ tr('МСФО') }}</button>
        </div>
        <div class="sh-div" aria-hidden="true"></div>
        <UzaYearStepper tone="dark" :model-value="year" :years="YEARS" prefix="FY "
                        @update:model-value="year = ($event as number) ?? year" />
        <div class="sh-div" aria-hidden="true"></div>
        <button v-if="finPerm.canEdit.value" class="sh-params-btn" type="button" @click="paramsOpen = true"
                :title="tr('Редактор порогов риска')">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/></svg>
          {{ tr('Пороги') }}
        </button>
      </div>
    </header>

    <!-- Состояния -->
    <div v-if="loading && !data" class="sh-state">
      <div class="sh-skel" v-for="i in 3" :key="i" :style="{ '--d': (i * 90) + 'ms' }" />
    </div>
    <div v-else-if="error && !data" class="sh-state sh-err">
      {{ error }}
      <button class="sh-retry" type="button" @click="load">{{ tr('Повторить') }}</button>
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
            <div class="sh-card-t">{{ tr('Фискальная материальность · % ВВП') }}</div>
            <div class="sh-card-s">
              {{ tr('портфель к номинальному ВВП · ВВП FY') }}{{ data.year }} = {{ fmtTrln(gdpBln) }} {{ tr('сум') }}
              <span class="sh-gdp-src">{{ tr('IMF WEO · ред.') }}</span>
            </div>
          </div></div>
          <div class="sh-fiscal-grid kpi-rail">
            <div v-for="(f, i) in fiscalCards" :key="f.label" class="sh-fiscal-i"
                 :style="{ '--accent': f.accent, '--d': (i * 80) + 'ms' }">
              <div class="sh-fiscal-l">{{ tr(f.label) }}</div>
              <div class="sh-fiscal-v">
                <span v-if="f.pct != null"><Odometer :value="f.pct.toFixed(1)" /><span class="sh-fiscal-u">{{ tr('% ВВП') }}</span></span>
                <span v-else>—</span>
              </div>
              <div class="sh-fiscal-abs">{{ fmtTrln(f.abs) }} {{ tr('сум') }}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- ═══ Структура портфеля: пайчарты (канон-донат) ═══ -->
      <section class="sh-section sh-4col">
        <div class="sh-card" style="--d:60ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ tr('Прибыльные компании') }}</div>
            <div class="sh-card-s">{{ tr('по знаку чистой прибыли · FY') }} {{ data.year }}</div>
          </div></div>
          <CreditDonut v-if="profitDonut.length" :entries="profitDonut"
            :center-value="String(profitTotal)" :center-label="t('компаний')"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">{{ tr('нет данных') }}</div>
        </div>
        <div class="sh-card" style="--d:140ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ tr('Компании по секторам') }}</div>
            <div class="sh-card-s">{{ tr('распределение портфеля') }}</div>
          </div></div>
          <CreditDonut v-if="sectorDonut.length" :entries="sectorDonut"
            :center-value="String(sectorTotal)" :center-label="t('компаний')"
            :hover-fmt="donutHover" :size="140" clickable
            @slice-click="(_e, idx) => toggleSector(sectorDonutCodes[idx] || null)" />
          <div v-else class="sh-none">{{ tr('нет данных') }}</div>
        </div>
        <div class="sh-card" style="--d:220ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ tr('Орг-правовая форма') }}</div>
            <div class="sh-card-s">{{ tr('по типу юрлица') }}</div>
          </div></div>
          <CreditDonut v-if="legalDonut.length" :entries="legalDonut"
            :center-value="String(legalTotal)" :center-label="t('компаний')"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">{{ tr('нет данных') }}</div>
        </div>
        <div class="sh-card" style="--d:300ms">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ tr('Орган управления') }}</div>
            <div class="sh-card-s">{{ tr('собственник / надзорный орган') }}</div>
          </div></div>
          <CreditDonut v-if="ownershipDonut.length" :entries="ownershipDonut"
            :center-value="String(ownershipTotal)" :center-label="t('компаний')"
            :hover-fmt="donutHover" :size="140" />
          <div v-else class="sh-none">{{ tr('нет данных') }}</div>
        </div>
      </section>

      <!-- ═══ Портфельный уровень: Pareto ═══ -->
      <section class="sh-section sh-grid">
        <div class="sh-card sh-pareto" style="--d:80ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">{{ tr('Концентрация портфеля') }}</div>
              <div class="sh-card-s">
                {{ tr('размер по компаниям (трлн сум) · топ-3 =') }} <strong>{{ top3Pct.toFixed(0) }}%</strong> {{ tr('портфеля · клик — детали') }}
              </div>
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
              <line v-for="f in [0.5, 1]" :key="f" :x1="PL" :x2="PW - PR"
                    :y1="PT + (1 - f) * (PH - PT - PB)" :y2="PT + (1 - f) * (PH - PT - PB)" class="sh-grid-line" />
              <g v-for="(b, i) in paretoBars" :key="b.code" class="sh-vbar-g"
                 :class="{ dim: focusSector && b.sector !== focusSector }" @click="openCompany(b.code)">
                <rect :x="pX(i)" :y="pY(b.v)" :width="pW()" :height="pH(b.v)" rx="3"
                      fill="#8B7FFF" fill-opacity="0.85" class="sh-vbar" :style="{ '--d': (i * 35) + 'ms' }">
                  <title>{{ b.name }} · {{ fmtBln(b.v) }} · Σ {{ b.cum.toFixed(0) }}{{ tr('% · клик — детали') }}</title>
                </rect>
                <text :x="pX(i) + pW() / 2" :y="pY(b.v) - 5" text-anchor="middle" class="sh-vbar-val"
                      :style="{ '--d': (i * 35 + 250) + 'ms' }">{{ tr(barLabel(b.v)) }}</text>
                <text :x="pX(i) + pW() / 2" :y="PH - PB + 13" text-anchor="middle" class="sh-vbar-lbl">{{ b.code.toUpperCase() }}</text>
              </g>
            </svg>
          </div>
          <div v-else class="sh-none">{{ tr('Нет данных за') }} {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Размер vs риск + разрезы по секторам ═══ -->
      <section class="sh-section sh-2col">
        <!-- Scatter: обязательства × балл риска -->
        <div class="sh-card" style="--d:80ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">{{ tr('Размер обязательств и риск') }}</div>
              <div class="sh-card-s">{{ tr('ось X — обязательства (√-шкала) · ось Y — балл 1→5 · клик по точке — детали компании') }}</div>
            </div>
            <button v-if="focusSector" type="button" class="sh-focus-chip" @click="toggleSector(null)">
              {{ tr('фокус ·') }} {{ (sectorBars.find(s => s.code === focusSector) || {}).name }} ✕
            </button>
          </div>
          <div v-if="riskDots.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${SXW} ${SXH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <!-- зоны балла (горизонтальные полосы) -->
              <line v-for="s in [1,2,3,4,5]" :key="'g'+s"
                    :x1="SXL" :x2="SXW - SXR" :y1="scY(s)" :y2="scY(s)" class="sh-grid-line" />
              <text v-for="s in [1,2,3,4,5]" :key="'gl'+s"
                    :x="SXL - 8" :y="scY(s) + 3" text-anchor="end" class="sh-axis-lbl">{{ s }}</text>
              <!-- точки компаний (кликабельны) -->
              <g v-for="(d, i) in riskDots" :key="d.code" class="sh-dot-g"
                 :class="{ dim: dotDimmed(d) }" @click="openCompany(d.code)">
                <circle :cx="scX(d.liab)" :cy="scY(d.overall)" r="7"
                        :fill="d.color" fill-opacity="0.82" stroke="#fff" stroke-width="1.5"
                        class="sh-dot" :style="{ '--d': (i * 30) + 'ms' }">
                  <title>{{ d.name }} {{ tr('· балл') }} {{ d.overall.toFixed(1) }} {{ tr('· обяз.') }} {{ fmtBln(d.liab) }} {{ tr('· клик — детали') }}</title>
                </circle>
                <text :x="scX(d.liab)" :y="scY(d.overall) - 10" text-anchor="middle"
                      class="sh-dot-lbl">{{ d.code.toUpperCase() }}</text>
              </g>
            </svg>
          </div>
          <div v-else class="sh-none">{{ tr('Нет данных за') }} {{ data.year }} ({{ data.standard }})</div>
        </div>

        <!-- Разрезы по секторам -->
        <div class="sh-card" style="--d:160ms">
          <div class="sh-card-hd">
            <div>
              <div class="sh-card-t">{{ tr('Разрез по секторам') }}</div>
              <div class="sh-card-s" v-if="profitSplit">
                {{ tr('прибыльные') }} {{ profitSplit.profitable }} {{ tr('· убыточные') }} {{ profitSplit.loss }}
                <span v-if="profitSplit.unknown">{{ tr('· н/д') }} {{ profitSplit.unknown }}</span>
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
            <button v-for="(s, i) in sectorBars" :key="s.code" type="button" class="sh-lolli"
                 :class="{ active: focusSector === s.code, dim: focusSector && focusSector !== s.code }"
                 :style="{ '--d': (i * 55) + 'ms', '--c': s.color }"
                 :title="tr('Фокус на секторе: {value0}', { value0: s.name })" @click="toggleSector(s.code)">
              <span class="sh-lolli-name">{{ s.name }}</span>
              <span class="sh-lolli-track">
                <span class="sh-lolli-line" :style="{ width: s.pct + '%' }" />
                <span class="sh-lolli-dot" :style="{ left: s.pct + '%' }" />
              </span>
              <span class="sh-lolli-val">{{ fmtBln(s.v) }}</span>
            </button>
          </div>
          <div v-else class="sh-none">{{ tr('Нет данных за') }} {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Активы/Капитал и рентабельность по секторам (комбо) ═══ -->
      <section class="sh-section sh-2eq">
        <div v-for="cfg in [
               { key: 'a', vm: comboAssets, t: i18nKey('Активы и ROA'), s: i18nKey('бар — активы (млрд) · справа — рентабельность активов'), ret: 'ROA' },
               { key: 'e', vm: comboEquity, t: i18nKey('Капитал и ROE'), s: i18nKey('бар — капитал (млрд) · справа — рентабельность капитала'), ret: 'ROE' },
             ]" :key="cfg.key" class="sh-card" :style="{ '--d': (cfg.key === 'a' ? 80 : 160) + 'ms' }">
          <div class="sh-card-hd"><div>
            <div class="sh-card-t">{{ tr(cfg.t) }}</div>
            <div class="sh-card-s">{{ tr(cfg.s) }}</div>
          </div></div>
          <div v-if="cfg.vm.rows.length" class="sh-pareto-svgwrap">
            <svg :viewBox="`0 0 ${CW} ${CH}`" class="sh-pareto-svg" preserveAspectRatio="xMidYMid meet">
              <line v-for="f in [0.5, 1]" :key="f" :x1="CL" :x2="CW - CR"
                    :y1="CT + (1 - f) * (CH - CT - CB)" :y2="CT + (1 - f) * (CH - CT - CB)" class="sh-grid-line" />
              <g v-for="(row, i) in cfg.vm.rows" :key="row.code" class="sh-vbar-g"
                 :class="{ dim: focusSector && row.code !== focusSector }">
                <rect :x="cX(i, cfg.vm.rows.length)" :y="cY(row.bar, cfg.vm.barMax)"
                      :width="cW(cfg.vm.rows.length)" :height="cH(row.bar, cfg.vm.barMax)" rx="3"
                      :fill="row.color" fill-opacity="0.82" class="sh-vbar" :style="{ '--d': (i * 60) + 'ms' }">
                  <title>{{ row.name }} · {{ fmtBln(row.bar) }} · {{ cfg.ret }} {{ fmtPct(row.ret) }}</title>
                </rect>
                <text :x="cX(i, cfg.vm.rows.length) + cW(cfg.vm.rows.length) / 2"
                      :y="cY(row.bar, cfg.vm.barMax) - 6" text-anchor="middle" class="sh-vret"
                      :fill="retColor(row.ret)" :style="{ '--d': (i * 60 + 350) + 'ms' }">{{ fmtPct(row.ret) }}</text>
                <text :x="cX(i, cfg.vm.rows.length) + cW(cfg.vm.rows.length) / 2" :y="CH - CB + 13"
                      text-anchor="middle" class="sh-vbar-lbl">{{ cutName(row.name) }}</text>
              </g>
            </svg>
          </div>
          <div v-else class="sh-none">{{ tr('Нет данных за') }} {{ data.year }} ({{ data.standard }})</div>
        </div>
      </section>

      <!-- ═══ Тренды агрегатов ═══ -->
      <section class="sh-section">
        <div class="sh-trends">
          <div v-for="(t, i) in trendCards" :key="t.key" class="sh-card sh-trend"
               :style="{ '--accent': t.accent, '--d': (i * 70) + 'ms' }">
            <div class="sh-trend-l">{{ tr(t.label) }}</div>
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
            <div v-else class="sh-none sm">{{ tr('мало данных') }}</div>
            <div class="sh-trend-yrs">{{ seriesYears[0] }}–{{ seriesYears[seriesYears.length - 1] }}</div>
          </div>
        </div>
      </section>
    </template>

    <SoeHealthDrillModal
      :open="!!drillCompany"
      :company="drillCompany"
      :zones="data?.zones || []"
      :year="data?.year ?? 0"
      :standard="data?.standard ?? ''"
      @close="drillCompany = null"
    />

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
/* Стеклянные fkb-card как в финансах: блюр + верхняя полоса (draw+breathe) + шиммер */
.sh-fiscal-i {
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(16px) saturate(1.5); -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255, 255, 255, 0.70); border-radius: 14px; padding: 14px 16px 12px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, 0.07), 0 1px 3px rgba(15, 23, 60, 0.04);
  position: relative; overflow: hidden; display: flex; flex-direction: column;
  justify-content: space-between; min-height: 96px;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d, 0ms) both;
}
.sh-fiscal-i::before {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both,
             finKpi2Breathe 2.8s ease-in-out calc(var(--d, 0ms) + 1s) infinite;
  transform-origin: left center;
}
.sh-fiscal-i::after {
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .55), transparent);
  animation: finShimmer 6s ease-in-out calc(var(--d, 0ms) + 1.2s) 1;
  transform: translateX(-120%); pointer-events: none;
}
.sh-fiscal-l { font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin-bottom: 6px; }
.sh-fiscal-v { font-size: 26px; font-weight: 400; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 2px; margin: 2px 0 4px; }
.sh-fiscal-u { font-size: 11px; color: var(--t3, #94A3B8); font-weight: 500; margin-left: 3px; letter-spacing: 0; }
.sh-fiscal-abs { font-size: 11px; color: var(--t2, #4B5468); font-variant-numeric: tabular-nums; margin-top: 4px; }

/* ── Структура: паи ── */
.sh-4col { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
@media (max-width: 1400px) { .sh-4col { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 700px) { .sh-4col { grid-template-columns: 1fr; } }

/* ── Размер×риск + секторы ── */
.sh-2col { display: grid; grid-template-columns: 1.4fr 1fr; gap: 12px; }
@media (max-width: 1100px) { .sh-2col { grid-template-columns: 1fr; } }
.sh-2eq { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 1100px) { .sh-2eq { grid-template-columns: 1fr; } }
/* Scatter: кликабельные точки + затемнение вне фокуса */
.sh-dot-g { cursor: pointer; transition: opacity .18s ease; }
.sh-dot-g.dim { opacity: .18; }
.sh-dot { transform-origin: center; transform-box: fill-box;
  animation: shDotPop .45s var(--ease-standard, ease) var(--d, 0ms) both; transition: fill-opacity .15s, r .15s; }
.sh-dot-g:hover .sh-dot { fill-opacity: 1; }
@keyframes shDotPop { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
.sh-dot-lbl { font-size: 8px; font-weight: 600; fill: var(--t3, #94A3B8); letter-spacing: .02em;
  pointer-events: none; opacity: 0; animation: shDotIn .3s ease .4s forwards; }
.sh-focus-chip { font-size: 10.5px; font-weight: 600; font-family: inherit; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.1); border: 1px solid rgba(124,111,247,.28); border-radius: 999px;
  padding: 4px 11px; cursor: pointer; transition: all .14s; }
.sh-focus-chip:hover { background: rgba(124,111,247,.18); }

/* Разрез по секторам — минималистичный лоллипоп (тонкая линия + точка) */
.sh-secwrap { display: flex; flex-direction: column; gap: 2px; padding-top: 6px; }
.sh-lolli { display: grid; grid-template-columns: 128px 1fr max-content; align-items: center; gap: 12px;
  width: 100%; text-align: left; background: none; border: 0; font-family: inherit; cursor: pointer;
  padding: 7px 8px; border-radius: 9px; transition: background .14s, opacity .18s;
  animation: shSecRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes shSecRowIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.sh-lolli:hover { background: rgba(127,119,221,.05); }
.sh-lolli.active { background: rgba(127,119,221,.09); }
.sh-lolli.dim { opacity: .4; }
.sh-lolli-name { font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sh-lolli-track { position: relative; height: 12px; display: flex; align-items: center; }
.sh-lolli-track::before { content: ''; position: absolute; left: 0; right: 0; height: 1.5px;
  background: rgba(30,42,74,.07); border-radius: 1px; }
.sh-lolli-line { position: absolute; left: 0; height: 2px; border-radius: 1px; background: var(--c, #7F77DD);
  opacity: .55; transform-origin: left center; animation: shSecGrow .7s var(--ease-standard, ease) var(--d, 0ms) both; }
.sh-lolli-dot { position: absolute; width: 9px; height: 9px; border-radius: 50%; background: var(--c, #7F77DD);
  transform: translateX(-50%); box-shadow: 0 0 0 2.5px #fff; opacity: 0;
  animation: shDotIn .3s ease calc(var(--d, 0ms) + .35s) forwards; }
@keyframes shSecGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.sh-lolli-val { font-size: 11.5px; font-weight: 600; color: var(--t2, #4B5468);
  font-variant-numeric: tabular-nums; white-space: nowrap; }

/* Вертикальные бары (Концентрация + комбо) — тонкие, скруглённый верх, приглушённые */
.sh-vbar-g { cursor: pointer; transition: opacity .18s ease; }
.sh-vbar-g.dim { opacity: .22; }
.sh-vbar { transform-origin: center bottom; transform-box: fill-box;
  animation: shBarGrow .6s var(--ease-standard, ease) var(--d, 0ms) both; transition: filter .15s; }
.sh-vbar-g:hover .sh-vbar { filter: brightness(1.08) saturate(1.1); }
.sh-vbar-lbl { font-size: 8.5px; font-weight: 600; fill: var(--t3, #94A3B8); letter-spacing: .02em; }
.sh-vbar-val { font-size: 9px; font-weight: 700; fill: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums;
  opacity: 0; animation: shDotIn .3s ease var(--d, 0ms) forwards; }
.sh-vret { font-size: 9.5px; font-weight: 700; font-variant-numeric: tabular-nums;
  opacity: 0; animation: shDotIn .3s ease var(--d, 0ms) forwards; }
.sh-vcum-line { stroke: var(--p-deep, #534AB7); stroke-width: 1.5; opacity: .55;
  stroke-dasharray: 1400; stroke-dashoffset: 1400; animation: shLineDraw 1.2s ease .35s forwards; }
.sh-vcum-dot { fill: #fff; stroke: var(--p-deep, #534AB7); stroke-width: 1.5;
  opacity: 0; animation: shDotIn .3s ease var(--d, 0ms) forwards; }

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
