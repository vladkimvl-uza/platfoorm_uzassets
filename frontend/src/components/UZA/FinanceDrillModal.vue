<script setup lang="ts">
/**
 * FinanceDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Premium drill-down модалка для 6 KPI-карточек блока Финансы · НСБУ
 * (ExecDashFinanceBlock).
 *
 * Variant A · Briefing (выбран пользователем) — компактный single-column
 * layout как в Pack 7.29 CompanyDrillModal:
 *   • Header: KPI label + большая сумма + delta-бейдж
 *   • 4-mini-KPI strip (per kind: маржи, ROE, D/E, лидер сектор)
 *   • По секторам — горизонтальный stacked bar + легенда
 *   • Топ-5 компаний по показателю
 *   • Коллапс «Показать все N компаний» (свёрнут по умолчанию)
 *   • Footer: «Открыть финансовый отчёт» → /financials?metric=...
 *
 * Данные приходят пропсами от родителя (ExecDashFinanceBlock) — модалка
 * не знает про composables, что упрощает тестирование и переиспользование.
 *
 * Pack 7.32
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";
import { useRouter } from "vue-router";
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();

export type FinKpiKind =
  | "revenue"
  | "net_profit"
  | "ebitda"
  | "assets"
  | "net_debt"
  | "fcf";

export interface FinExtKpis {
  totalRevenue: number;
  revenueYoYPct: number;
  netProfit: number;
  netMargin: number;
  ebitda: number;
  ebitdaMargin: number;
  totalAssets: number;
  totalDebt: number;
  debtToEquity: number | null;
  freeCashFlow: number;
  roe: number | null;
  cfo: number;
  cfi: number;
  lossMakingCount: number;
  cosWithData: number;
}

export interface FinCompanyRow {
  id: string;
  code: string;
  name: string;
  sector: string; // canonical sector code: mining/oilgas/energy/transport/other
  revenue: number | null;
  profit: number | null;
  assets: number | null;
  debt: number | null;
  cfo: number | null;
  cfi: number | null;
  ebitda: number | null;
  yoy: number | null;
}

export interface FinSectorMetaEntry {
  label: string;
  short: string;
  color: string;
}

interface Props {
  kind: FinKpiKind;
  extKpis: FinExtKpis;
  rows: FinCompanyRow[];
  sectorMeta: Record<string, FinSectorMetaEntry>;
  year: number;
  unitFactor: number;       // 1000 / 1_000_000 / 1_000_000_000
  unitLabel: string;        // "тыс." / "млн" / "млрд"
  currencyLabel: string;    // "UZS" / "USD" / "EUR"
  totalCompanies: number;   // 22 — общее количество для "X / 22"
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();

const router = useRouter();

// ─── KPI metadata ───
interface KpiMeta {
  label: string;
  color: string;
  valueGetter: (k: FinExtKpis) => number;
  /** Какое поле в FinCompanyRow используется как контрибуция этого KPI */
  rowField: (r: FinCompanyRow) => number | null;
  /** Бейдж под заголовком (зеркалит карточку дашборда) */
  badgeGetter: (k: FinExtKpis) => { text: string; tone: "good" | "bad" | "neutral" } | null;
}

const KPI_META: Record<FinKpiKind, KpiMeta> = {
  revenue: {
    label: "Совокупная выручка",
    color: "#7F77DD",
    valueGetter: (k) => k.totalRevenue,
    rowField: (r) => r.revenue,
    badgeGetter: (k) => k.revenueYoYPct != null
      ? { text: fmtPctSigned(k.revenueYoYPct, 0) + " к пред. году", tone: k.revenueYoYPct >= 0 ? "good" : "bad" }
      : null,
  },
  net_profit: {
    label: "Чистая прибыль",
    color: "#1D9E75",
    valueGetter: (k) => k.netProfit,
    rowField: (r) => r.profit,
    badgeGetter: (k) => ({ text: "Маржа " + fmtPct(k.netMargin, 0), tone: k.netMargin >= 0 ? "good" : "bad" }),
  },
  ebitda: {
    label: "EBITDA",
    color: "#EF9F27",
    valueGetter: (k) => k.ebitda,
    rowField: (r) => r.ebitda,
    badgeGetter: (k) => ({ text: "Маржа " + fmtPct(k.ebitdaMargin, 0), tone: "neutral" }),
  },
  assets: {
    label: "Совокупные активы",
    color: "#378ADD",
    valueGetter: (k) => k.totalAssets,
    rowField: (r) => r.assets,
    badgeGetter: (k) => ({ text: k.cosWithData + " компаний с данными", tone: "neutral" }),
  },
  net_debt: {
    label: "Чистый долг",
    color: "#E24B4A",
    valueGetter: (k) => k.totalDebt,
    rowField: (r) => r.debt,
    badgeGetter: (k) => k.debtToEquity != null
      ? { text: "D/E " + k.debtToEquity.toFixed(1) + "x", tone: k.debtToEquity > 2 ? "bad" : "neutral" }
      : null,
  },
  fcf: {
    label: "Free Cash Flow",
    color: "#1D9E75",
    valueGetter: (k) => k.freeCashFlow,
    rowField: (r) => {
      // FCF ≈ CFO + CFI; null only когда оба отсутствуют
      if (r.cfo == null && r.cfi == null) return null;
      return (r.cfo ?? 0) + (r.cfi ?? 0);
    },
    badgeGetter: (k) => k.roe != null
      ? { text: "CFO + CFI · ROE " + fmtPct(k.roe, 0), tone: k.freeCashFlow >= 0 ? "good" : "bad" }
      : { text: "CFO + CFI", tone: k.freeCashFlow >= 0 ? "good" : "bad" },
  },
};

const meta = computed(() => KPI_META[props.kind]);
const bigValue = computed(() => meta.value.valueGetter(props.extKpis));
const badge = computed(() => meta.value.badgeGetter(props.extKpis));

// ─── Format helpers ───
function fmtMoney(n: number | null | undefined): string {
  if (n == null || !isFinite(n)) return "—";
  const scaled = n / props.unitFactor;
  if (Math.abs(scaled) >= 1000) {
    return fmt.fmtNumber(Math.round(scaled));
  }
  return fmt.fmtNumber(scaled, { decimals: Math.abs(scaled) < 10 ? 1 : 0 });
}
function fmtPct(n: number | null | undefined, decimals = 0): string {
  return fmt.fmtPercent(n, { decimals });
}
function fmtPctSigned(n: number | null | undefined, decimals = 0): string {
  return fmt.fmtPercent(n, { decimals, signed: true });
}

// ─── Sector aggregation ───
interface SectorAgg {
  id: string;
  label: string;
  short: string;
  color: string;
  total: number;
  count: number;
  pct: number; // share of absolute total (so works for negatives too)
}
const sectorAgg = computed<SectorAgg[]>(() => {
  const map = new Map<string, SectorAgg>();
  for (const [id, m] of Object.entries(props.sectorMeta)) {
    map.set(id, { id, label: m.label, short: m.short, color: m.color, total: 0, count: 0, pct: 0 });
  }
  for (const row of props.rows) {
    const v = meta.value.rowField(row);
    if (v == null) continue;
    const s = map.get(row.sector);
    if (s) {
      s.total += v;
      s.count++;
    }
  }
  const arr = Array.from(map.values()).filter((s) => s.total !== 0);
  const grandAbs = arr.reduce((a, x) => a + Math.abs(x.total), 0) || 1;
  for (const s of arr) s.pct = Math.round((Math.abs(s.total) / grandAbs) * 100);
  arr.sort((a, b) => Math.abs(b.total) - Math.abs(a.total));
  return arr;
});
const topSector = computed(() => sectorAgg.value[0] ?? null);

// ─── 4-mini KPI strip per kind ───
interface MiniKpi { label: string; value: string; accent: string }
const miniKpis = computed<MiniKpi[]>(() => {
  const k = props.extKpis;
  const top = topSector.value?.short ?? "—";
  switch (props.kind) {
    case "revenue":
      return [
        { label: "EBITDA маржа", value: fmtPct(k.ebitdaMargin, 0), accent: "#1D9E75" },
        { label: "Чист. маржа", value: fmtPct(k.netMargin, 0), accent: "#7F77DD" },
        { label: "Покрытие", value: `${k.cosWithData} / ${props.totalCompanies}`, accent: "#EF9F27" },
        { label: "Лидер сектор", value: top, accent: "#378ADD" },
      ];
    case "net_profit":
      return [
        { label: "Чист. маржа", value: fmtPct(k.netMargin, 0), accent: "#1D9E75" },
        { label: "ROE", value: k.roe != null ? fmtPct(k.roe, 0) : "—", accent: "#7F77DD" },
        { label: "Убыточных", value: k.lossMakingCount.toString(), accent: "#E24B4A" },
        { label: "Лидер сектор", value: top, accent: "#378ADD" },
      ];
    case "ebitda":
      return [
        { label: "EBITDA маржа", value: fmtPct(k.ebitdaMargin, 0), accent: "#EF9F27" },
        { label: "Чист. маржа", value: fmtPct(k.netMargin, 0), accent: "#1D9E75" },
        { label: "Долг/EBITDA", value: k.ebitda > 0 ? (k.totalDebt / k.ebitda).toFixed(1) + "x" : "—", accent: "#E24B4A" },
        { label: "Лидер сектор", value: top, accent: "#378ADD" },
      ];
    case "assets":
      return [
        { label: "Чист. долг", value: fmtMoney(k.totalDebt), accent: "#E24B4A" },
        { label: "D/E", value: k.debtToEquity != null ? k.debtToEquity.toFixed(1) + "x" : "—", accent: "#7F77DD" },
        { label: "ROE", value: k.roe != null ? fmtPct(k.roe, 0) : "—", accent: "#1D9E75" },
        { label: "Лидер сектор", value: top, accent: "#378ADD" },
      ];
    case "net_debt":
      return [
        { label: "D/E", value: k.debtToEquity != null ? k.debtToEquity.toFixed(1) + "x" : "—", accent: "#7F77DD" },
        { label: "Долг/EBITDA", value: k.ebitda > 0 ? (k.totalDebt / k.ebitda).toFixed(1) + "x" : "—", accent: "#E24B4A" },
        { label: "Активы", value: fmtMoney(k.totalAssets), accent: "#378ADD" },
        { label: "Лидер сектор", value: top, accent: "#1D9E75" },
      ];
    case "fcf":
      return [
        { label: "CFO", value: fmtMoney(k.cfo), accent: "#1D9E75" },
        { label: "CFI", value: fmtMoney(k.cfi), accent: "#7F77DD" },
        { label: "ROE", value: k.roe != null ? fmtPct(k.roe, 0) : "—", accent: "#EF9F27" },
        { label: "Лидер сектор", value: top, accent: "#378ADD" },
      ];
    default:
      return [];
  }
});

// ─── Sorted rows (для топ-5 и полного списка) ───
const sortedRows = computed<Array<FinCompanyRow & { _val: number }>>(() => {
  const arr: Array<FinCompanyRow & { _val: number }> = [];
  for (const r of props.rows) {
    const v = meta.value.rowField(r);
    if (v == null) continue;
    arr.push({ ...r, _val: v });
  }
  arr.sort((a, b) => b._val - a._val);
  return arr;
});

const topCompanies = computed(() => sortedRows.value.slice(0, 5));
const grandTotal = computed(() => {
  // Сумма абсолютных значений — для расчёта pct
  return sortedRows.value.reduce((a, r) => a + Math.abs(r._val), 0) || 1;
});
const topMaxAbs = computed(() => {
  return Math.max(...sortedRows.value.slice(0, 5).map((r) => Math.abs(r._val))) || 1;
});

function rowPct(value: number): number {
  return Math.round((Math.abs(value) / grandTotal.value) * 100);
}

// ─── Collapse state (свёрнут по умолчанию — согласно требованию) ───
const expandedAll = ref(false);

// ─── Header count-up ───
const headerDisplay = ref<number>(0);
function startCountUp() {
  const target = bigValue.value;
  if (typeof target !== "number" || !isFinite(target)) {
    headerDisplay.value = target;
    return;
  }
  const reducedMotion = typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reducedMotion) {
    headerDisplay.value = target;
    return;
  }
  const start = performance.now() + 320;
  const dur = 1100;
  function tick(now: number) {
    if (now < start) { requestAnimationFrame(tick); return; }
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    headerDisplay.value = target * eased;
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

// ─── Lifecycle ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

// a11y: фокус-трап диалога + возврат фокуса при закрытии
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function gotoCta() {
  router.push({ name: "financials", query: { metric: props.kind, year: props.year } });
  close();
}
function gotoCompany(code: string) {
  if (code) router.push({ name: "company-workspace", params: { code } });
  close();
}

let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
  startCountUp();
});
onUnmounted(() => {
  document.body.style.overflow = prevOverflow;
  window.removeEventListener("keydown", onKey);
});
</script>

<template>
  <Transition name="uza-modal" appear>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div class="fdm-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div ref="cardEl" tabindex="-1" class="fdm-card" :style="{ '--sc': meta.color }">
          <div class="fdm-stripe" aria-hidden="true" />
          <div class="fdm-shim" aria-hidden="true" />
          <div class="fdm-glow" aria-hidden="true" />

          <button class="fdm-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- ─── HEADER ─── -->
          <div class="fdm-sect fdm-row" style="--si:0; display:flex; justify-content:space-between; align-items:flex-end; gap:18px; flex-wrap:wrap; padding-top:20px;">
            <div>
              <div class="fdm-h-l">{{ meta.label }}</div>
              <div class="fdm-h-v">
                <span class="num">{{ fmtMoney(headerDisplay) }}</span>
                <span class="unit">{{ unitLabel }} {{ currencyLabel }}</span>
              </div>
              <span
                v-if="badge"
                class="fdm-h-d"
                :class="`fdm-h-d--${badge.tone}`"
              >
                <svg v-if="badge.tone === 'good'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 7l3-3 3 3"/></svg>
                <svg v-else-if="badge.tone === 'bad'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 5l3 3 3-3"/></svg>
                {{ badge.text }}
              </span>
            </div>
            <div class="fdm-h-tag-list">
              <div>{{ extKpis.cosWithData }} / {{ totalCompanies }} компаний</div>
              <div>{{ sectorAgg.length }} секторов</div>
              <div class="fdm-h-tag-year">FY {{ year }}</div>
            </div>
          </div>

          <!-- ─── 4 mini-KPI strip ─── -->
          <div class="fdm-sect fdm-row" style="--si:1;">
            <div class="fdm-mini-grid">
              <div
                v-for="(m, i) in miniKpis"
                :key="m.label"
                class="fdm-mini-kpi"
                :style="{ '--kc': m.accent, '--ki': i }"
              >
                <div class="fdm-mk-l">{{ m.label }}</div>
                <div class="fdm-mk-v">{{ m.value }}</div>
              </div>
            </div>
          </div>

          <!-- ─── По секторам ─── -->
          <div class="fdm-sect fdm-row" style="--si:2;">
            <div class="fdm-l-sec">По секторам</div>
            <div v-if="sectorAgg.length" class="fdm-bar">
              <div
                v-for="(s, i) in sectorAgg"
                :key="s.id"
                class="fdm-bar-seg"
                :style="{
                  background: s.color,
                  flex: `0 0 ${s.pct}%`,
                  animationDelay: (0.55 + i * 0.13) + 's',
                }"
                :title="`${s.label} · ${fmtMoney(s.total)} ${unitLabel} ${currencyLabel}`"
              />
            </div>
            <div v-if="sectorAgg.length" class="fdm-leg">
              <span v-for="s in sectorAgg" :key="s.id">
                <i class="fdm-dot" :style="{ background: s.color }"/>
                {{ s.short }} · <strong>{{ fmtMoney(s.total) }}</strong>
                <span class="fdm-leg-pct">{{ s.pct }}%</span>
              </span>
            </div>
            <div v-else class="fdm-empty">Нет данных по секторам</div>
          </div>

          <!-- ─── Top-5 contributors ─── -->
          <div class="fdm-sect fdm-row" style="--si:3;">
            <div class="fdm-l-sec">
              <span>Топ-5 компаний по показателю</span>
              <span v-if="sortedRows.length > 5" class="fdm-l-side">
                остальные {{ sortedRows.length - 5 }} ниже
              </span>
            </div>
            <div v-if="topCompanies.length" class="fdm-toplist">
              <div
                v-for="(c, i) in topCompanies"
                :key="c.id"
                class="fdm-top-row"
                @click="gotoCompany(c.code)"
                :title="'Открыть карточку «' + c.name + '»'"
              >
                <span class="fdm-top-name">
                  <i class="fdm-top-tick" :style="{ background: sectorMeta[c.sector]?.color || '#888' }"/>
                  {{ c.name }}
                </span>
                <span class="fdm-top-bar">
                  <span
                    class="fdm-top-fill"
                    :style="{
                      background: sectorMeta[c.sector]?.color || '#888',
                      width: ((Math.abs(c._val) / topMaxAbs) * 100) + '%',
                      animationDelay: (1.0 + i * 0.07) + 's',
                    }"
                  />
                </span>
                <span class="fdm-top-val">
                  <span class="amt">{{ fmtMoney(c._val) }}</span>
                  <span class="pct">{{ rowPct(c._val) }}%</span>
                </span>
              </div>
            </div>
            <div v-else class="fdm-empty">Нет компаний с данными по этому KPI</div>
          </div>

          <!-- ─── Collapsible full list ─── -->
          <div v-if="sortedRows.length > 5" class="fdm-sect fdm-row" style="--si:4; padding-top:0;">
            <button
              type="button"
              class="fdm-collapse"
              :class="{ 'fdm-collapse--open': expandedAll }"
              @click="expandedAll = !expandedAll"
              :aria-expanded="expandedAll"
            >
              <svg
                viewBox="0 0 14 14"
                fill="none"
                stroke="currentColor"
                stroke-width="1.9"
                stroke-linecap="round"
                stroke-linejoin="round"
                width="11"
                height="11"
                class="fdm-collapse-chev"
              >
                <path d="M3.5 5l3.5 3.5L10.5 5"/>
              </svg>
              {{ expandedAll
                ? `Свернуть · показано ${sortedRows.length}`
                : `Показать все ${sortedRows.length} компаний` }}
            </button>

            <div v-if="expandedAll" class="fdm-fulllist">
              <div
                v-for="(c, i) in sortedRows.slice(5)"
                :key="c.id"
                class="fdm-full-row"
                @click="gotoCompany(c.code)"
              >
                <span class="fdm-full-idx">{{ i + 6 }}</span>
                <span class="fdm-full-name">
                  <i class="fdm-top-tick" :style="{ background: sectorMeta[c.sector]?.color || '#888' }"/>
                  {{ c.name }}
                </span>
                <span class="fdm-full-sec">{{ sectorMeta[c.sector]?.short || '—' }}</span>
                <span class="fdm-full-val">{{ fmtMoney(c._val) }}</span>
                <span class="fdm-full-pct">{{ rowPct(c._val) }}%</span>
              </div>
            </div>
          </div>

          <!-- ─── FOOTER ─── -->
          <div class="fdm-ftr fdm-row" style="--si:5;">
            <button class="fdm-btn fdm-btn-g" @click="close">Закрыть</button>
            <button class="fdm-btn fdm-btn-p" @click="gotoCta">
              Открыть финансовый отчёт
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="12" height="12">
                <path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
  </Transition>
</template>

<style scoped>
.fdm-bd {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 9000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  overflow-y: auto;
}
.fdm-card {
  position: relative;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10);
  width: 100%;
  max-width: 720px;
  overflow: hidden;
  animation: fdmIn .55s var(--ease-standard) .08s both;
}
.fdm-stripe {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: var(--sc);
  transform-origin: left center;
  animation: fdmStripe .75s var(--ease-standard) .2s both;
  z-index: 3;
}
.fdm-shim {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent);
  transform: translateX(-120%);
  animation: fdmShim 6s ease-in-out 1.5s infinite;
  pointer-events: none;
  z-index: 4;
}
.fdm-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%);
  opacity: 0.07;
  pointer-events: none;
  z-index: 1;
}
.fdm-x {
  position: absolute;
  top: 14px; right: 14px;
  width: 28px; height: 28px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--t3, var(--t-muted));
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: var(--bg1, #fff);
  z-index: 6;
  transition: all .14s;
}
.fdm-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); border-color: rgba(0,0,0,.10); }

.fdm-row {
  animation: fdmUp .42s ease both;
  animation-delay: calc(.32s + var(--si, 0) * .06s);
  opacity: 0;
  position: relative;
  z-index: 2;
}

.fdm-sect { padding: 14px 22px; }
.fdm-sect + .fdm-sect { padding-top: 0; }

.fdm-h-l {
  font-size: 10.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .08em;
}
.fdm-h-v {
  font-size: 44px;
  font-weight: 500;
  letter-spacing: -.035em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  margin-top: 4px;
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.fdm-h-v .unit {
  font-size: 13px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  letter-spacing: 0;
}
.fdm-h-d {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 9px;
  border-radius: 999px;
  margin-top: 8px;
}
.fdm-h-d--good { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.fdm-h-d--bad { background: rgba(226, 75, 74, .10); color: var(--sev-critical); }
.fdm-h-d--neutral { background: rgba(127, 119, 221, .08); color: var(--p-deep); }

.fdm-h-tag-list {
  text-align: right;
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
  line-height: 1.7;
}
.fdm-h-tag-list .fdm-h-tag-year {
  color: var(--t1, #1E2A4A);
  margin-top: 2px;
}

/* Mini KPI grid */
.fdm-mini-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 7px;
}
.fdm-mini-kpi {
  position: relative;
  background: var(--bg2, #FAFAFC);
  border-radius: 9px;
  padding: 9px 10px 8px;
  overflow: hidden;
}
.fdm-mini-kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kc);
  transform-origin: left;
  transform: scaleX(0);
  animation: fdmKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards;
}
.fdm-mk-l {
  font-size: 8.5px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .05em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fdm-mk-v {
  font-size: 16px;
  font-weight: 400;
  letter-spacing: -.02em;
  color: var(--t1, #1E2A4A);
  line-height: 1.15;
  margin-top: 3px;
  font-feature-settings: "tnum";
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.fdm-l-sec {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 500;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.fdm-l-side {
  font-size: 9.5px;
  color: #6B6A66;
  text-transform: none;
  letter-spacing: .02em;
  font-weight: 400;
}

/* Sector bar */
.fdm-bar {
  height: 11px;
  background: #F1EFE8;
  border-radius: 5px;
  overflow: hidden;
  display: flex;
}
.fdm-bar-seg {
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: fdmBar 1.1s var(--ease-standard) forwards;
}
.fdm-leg {
  display: flex;
  gap: 14px;
  margin-top: 9px;
  font-size: 11px;
  color: var(--t3, #5F5E5A);
  font-weight: 500;
  flex-wrap: wrap;
}
.fdm-leg strong { color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.fdm-leg-pct { color: var(--t3, var(--t-muted)); margin-left: 3px; font-feature-settings: "tnum"; }
.fdm-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}

/* Top-5 list */
.fdm-toplist { display: flex; flex-direction: column; gap: 6px; }
.fdm-top-row {
  display: grid;
  grid-template-columns: 150px 1fr 110px;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
  cursor: pointer;
  padding: 3px 6px;
  border-radius: 5px;
  transition: background .12s;
}
.fdm-top-row:hover { background: rgba(127, 119, 221, .04); }
.fdm-top-name {
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fdm-top-tick {
  width: 3px;
  height: 12px;
  opacity: .85;
  flex-shrink: 0;
}
.fdm-top-bar {
  height: 6px;
  background: #F1EFE8;
  border-radius: 3px;
  overflow: hidden;
}
.fdm-top-fill {
  display: block;
  height: 100%;
  transform: scaleX(0);
  transform-origin: left;
  animation: fdmBar 1s var(--ease-standard) forwards;
}
.fdm-top-val {
  text-align: right;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  font-feature-settings: "tnum";
  display: flex;
  flex-direction: column;
  gap: 1px;
  line-height: 1.1;
}
.fdm-top-val .amt { font-size: 11.5px; }
.fdm-top-val .pct { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 400; }

/* Collapsible "show all" */
.fdm-collapse {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  padding: 11px 14px;
  border-radius: 8px;
  border: 1px dashed rgba(127, 119, 221, .30);
  background: rgba(127, 119, 221, .04);
  color: var(--p-deep);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all .15s ease;
}
.fdm-collapse:hover {
  background: rgba(127, 119, 221, .07);
  border-style: solid;
}
.fdm-collapse-chev {
  color: #7F77DD;
  transition: transform .2s ease;
}
.fdm-collapse--open .fdm-collapse-chev {
  transform: rotate(180deg);
}

/* Full list (после Развернуть) */
.fdm-fulllist {
  margin-top: 8px;
  border-radius: 8px;
  background: var(--bg2, #FAFAFC);
  padding: 4px;
  max-height: 280px;
  overflow-y: auto;
}
.fdm-full-row {
  display: grid;
  grid-template-columns: 24px 1fr 70px 110px 40px;
  gap: 8px;
  align-items: center;
  font-size: 11px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 5px;
  transition: background .12s;
}
.fdm-full-row:hover { background: var(--bg1, #fff); box-shadow: 0 1px 4px rgba(15, 23, 60, .05); }
.fdm-full-idx {
  color: #6B6A66;
  font-weight: 500;
  font-feature-settings: "tnum";
  font-size: 10px;
  text-align: right;
}
.fdm-full-name {
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fdm-full-sec {
  color: var(--t3, var(--t-muted));
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fdm-full-val {
  text-align: right;
  font-feature-settings: "tnum";
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.fdm-full-pct {
  text-align: right;
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  font-feature-settings: "tnum";
}

/* Empty */
.fdm-empty {
  padding: 16px;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 11.5px;
  font-style: italic;
}

/* Footer */
.fdm-ftr {
  padding: 13px 22px 14px;
  display: flex;
  justify-content: flex-end;
  gap: 9px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  background: var(--bg2, #FAFAFC);
  margin-top: 4px;
}
.fdm-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 9px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all .14s;
  border: 1px solid transparent;
  font-family: inherit;
}
.fdm-btn-g {
  background: var(--bg1, #fff);
  color: var(--t3, #5F5E5A);
  border-color: rgba(0, 0, 0, 0.10);
}
.fdm-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.fdm-btn-p { background: var(--sc); color: #fff; }
.fdm-btn-p:hover { filter: brightness(.93); }

/* Transitions */
.fdm-fade-enter-active, .fdm-fade-leave-active { transition: opacity .28s ease; }
.fdm-fade-enter-from, .fdm-fade-leave-to { opacity: 0; }
.fdm-fade-leave-active .fdm-card { animation: fdmOut .24s ease forwards; }

@keyframes fdmIn {
  0%   { opacity: 0; transform: translateY(22px) scale(.96); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes fdmOut {
  to { opacity: 0; transform: translateY(8px) scale(.98); }
}
@keyframes fdmStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes fdmShim {
  0%   { transform: translateX(-120%); }
  60%  { transform: translateX(220%); }
  100% { transform: translateX(220%); }
}
@keyframes fdmUp {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes fdmBar { to { transform: scaleX(1); } }
@keyframes fdmKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

/* Responsive */
@media (max-width: 600px) {
  .fdm-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .fdm-top-row { grid-template-columns: 110px 1fr 90px; font-size: 11px; }
  .fdm-h-v { font-size: 32px; }
  .fdm-full-row { grid-template-columns: 22px 1fr 70px 36px; }
  .fdm-full-val { display: none; }
}
</style>
