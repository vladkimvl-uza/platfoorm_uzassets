<script setup lang="ts">
/**
 * BusinessPlanDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Premium drill-down модалка для блока «Бизнес-план портфеля»
 * (ExecDashBPTrackerBlock). Открывается кликом на hero число / чарт
 * или на сегменты distribution-bar в footer.
 *
 * Kinds:
 *   • overall   — общий обзор (все компании, активная метрика)
 *   • leaders   — фокус на опережающих (cls="ok")
 *   • tracking  — на трекинге (cls="warn")
 *   • behind    — отстают (cls="bad")
 *
 * Variant A · Briefing:
 *   • Header: метрика + большое % + bаge с план/факт суммами
 *   • 4 mini-KPI: опережают / на трекинге / отстают / сред. исп.
 *   • Distribution segmented bar — 3 сегмента (ok/warn/bad)
 *   • Лидеры/Аутсайдеры split (top-3 и bottom-3)
 *   • Коллапс «Показать все N компаний»
 *   • Footer: «Открыть бизнес-план» → /business-plan
 *
 * Pack 7.33
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";
import { useRouter } from "vue-router";
import type { ExecBPBlock, ExecBPCompanyRow } from "@/api/executiveDashboard";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import CurrencyToggle from "@/components/UZA/CurrencyToggle.vue";

export type BpKind = "overall" | "leaders" | "tracking" | "behind";

interface Props {
  kind: BpKind;
  block: ExecBPBlock;
  /** Канонический sector code → display label/short */
  sectorLabel: Record<string, string>;
  sectorColor: Record<string, string>;
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const conv = useCurrencyConverter();

// ─── KPI metadata per kind ───
interface KindMeta {
  label: string;
  color: string;
  /** Фильтр для строк */
  rowFilter: (r: ExecBPCompanyRow) => boolean;
  /** Какие строки идут в "топ-3 / bottom-3" */
  showLeadersLaggards: boolean;
  /** Эмфаза в hero */
  heroFocus: "overall" | "leaders" | "tracking" | "behind";
}

const KIND_META: Record<BpKind, KindMeta> = {
  overall: {
    label: "Выполнение плана",
    color: "#1D9E75",
    rowFilter: () => true,
    showLeadersLaggards: true,
    heroFocus: "overall",
  },
  leaders: {
    label: "Опережают план",
    color: "#1D9E75",
    rowFilter: (r) => r.cls === "ok",
    showLeadersLaggards: false,
    heroFocus: "leaders",
  },
  tracking: {
    label: "На трекинге",
    color: "#EF9F27",
    rowFilter: (r) => r.cls === "warn",
    showLeadersLaggards: false,
    heroFocus: "tracking",
  },
  behind: {
    label: "Отстают от плана",
    color: "#E24B4A",
    rowFilter: (r) => r.cls === "bad",
    showLeadersLaggards: false,
    heroFocus: "behind",
  },
};

const meta = computed(() => KIND_META[props.kind]);

// ─── Number formatters (Pack 7.34: 3 decimals + USD conversion) ───
function fmtNum(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const f = conv.format(v, props.block.year);
  return f.value + " " + f.unit;
}
function fmtPctDisplay(pct: number | null | undefined): string {
  if (pct == null) return "—";
  return Math.round(pct).toString();
}

// ─── Filtered rows ───
const filteredRows = computed<ExecBPCompanyRow[]>(() => {
  return (props.block.rows || []).filter(meta.value.rowFilter);
});

// ─── Hero values per kind ───
interface Hero {
  bigVal: string;
  bigUnit: string;
  bigColor: string;
  badge: { text: string; tone: "good" | "bad" | "neutral" } | null;
}
const hero = computed<Hero>(() => {
  const b = props.block;
  switch (props.kind) {
    case "overall":
      return {
        bigVal: fmtPctDisplay(b.overall_pct),
        bigUnit: "% выполнения",
        bigColor: pctColor(b.overall_pct),
        badge: {
          text: `план ${fmtNum(b.sum_plan_ll)} · факт ${fmtNum(b.sum_fact_ll)}`,
          tone: (b.overall_pct ?? 0) >= 100 ? "good"
              : (b.overall_pct ?? 0) >= 80 ? "neutral" : "bad",
        },
      };
    case "leaders":
      return {
        bigVal: b.on_target.toString(),
        bigUnit: "компаний опережают",
        bigColor: "#0F6E56",
        badge: {
          text: `≥ ${b.metric === "revenue" ? "100" : "95"}% от плана`,
          tone: "good",
        },
      };
    case "tracking":
      return {
        bigVal: b.attention.toString(),
        bigUnit: "компаний на трекинге",
        bigColor: "#854F0B",
        badge: { text: "80–99% от плана", tone: "neutral" },
      };
    case "behind":
      return {
        bigVal: b.behind.toString(),
        bigUnit: "компаний отстают",
        bigColor: "#A32D2D",
        badge: { text: "< 80% от плана", tone: "bad" },
      };
  }
  return { bigVal: "—", bigUnit: "", bigColor: "#1E2A4A", badge: null };
});

function pctColor(pct: number | null | undefined): string {
  if (pct == null) return "#1E2A4A";
  if (pct >= 100) return "#0F6E56";
  if (pct >= 80) return "#854F0B";
  return "#A32D2D";
}

// ─── Mini-KPI strip ───
interface MiniKpi { label: string; value: string; accent: string; emphasis?: boolean }
// Падежи: «1 процент», «2 процента», «5 процентов» (было всегда «процентов»).
function pctWord(n: number): string {
  const m = Math.abs(n) % 100;
  if (m >= 11 && m <= 14) return "процентов";
  const r = Math.abs(n) % 10;
  if (r === 1) return "процент";
  if (r >= 2 && r <= 4) return "процента";
  return "процентов";
}
const miniKpis = computed<MiniKpi[]>(() => {
  const b = props.block;
  const avgN = b.overall_pct != null ? Math.round(b.overall_pct) : null;
  const avg = avgN != null ? `${avgN} ${pctWord(avgN)}` : "—";
  return [
    { label: "Опережают план", value: b.on_target.toString(), accent: "#1D9E75", emphasis: props.kind === "leaders" },
    { label: "На трекинге", value: b.attention.toString(), accent: "#EF9F27", emphasis: props.kind === "tracking" },
    { label: "Отстают от плана", value: b.behind.toString(), accent: "#E24B4A", emphasis: props.kind === "behind" },
    { label: "Среднее выполнение", value: avg, accent: "#378ADD", emphasis: props.kind === "overall" },
  ];
});

// ─── Distribution bar widths ───
const distrib = computed(() => {
  const b = props.block;
  const tot = (b.on_target + b.attention + b.behind) || 1;
  return {
    pctOk: Math.round((b.on_target / tot) * 100),
    pctWarn: Math.round((b.attention / tot) * 100),
    pctBad: Math.round((b.behind / tot) * 100),
  };
});

// ─── Leaders / Laggards (3 + 3) ───
interface RankedRow extends ExecBPCompanyRow { _rank: number }
const sortedRows = computed<RankedRow[]>(() => {
  const arr = (props.block.rows || [])
    .filter((r) => r.pct != null)
    .map((r, i) => ({ ...r, _rank: i }));
  arr.sort((a, b) => (b.pct ?? -Infinity) - (a.pct ?? -Infinity));
  return arr;
});
const leaders = computed(() => sortedRows.value.slice(0, 3));
const laggards = computed(() => {
  const arr = [...sortedRows.value].reverse();
  return arr.slice(0, 3);
});

// ─── Single-kind list (когда kind !== overall) ───
const kindList = computed<ExecBPCompanyRow[]>(() => {
  if (props.kind === "overall") return [];
  return filteredRows.value
    .filter((r) => r.pct != null)
    .sort((a, b) => {
      // leaders → desc, behind/tracking → asc (хуже сверху)
      if (props.kind === "leaders") return (b.pct ?? 0) - (a.pct ?? 0);
      return (a.pct ?? 0) - (b.pct ?? 0);
    });
});
const kindListTop3 = computed(() => kindList.value.slice(0, 3));

// ─── Collapse state ───
const expandedAll = ref(false);

// ─── Count-up ───
const headerDisplay = ref<number>(0);
function startCountUp() {
  const targetStr = hero.value.bigVal;
  const targetNum = parseFloat(targetStr);
  if (isNaN(targetNum)) {
    headerDisplay.value = NaN;
    return;
  }
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduced) { headerDisplay.value = targetNum; return; }
  const start = performance.now() + 320;
  const dur = 1100;
  function tick(now: number) {
    if (now < start) { requestAnimationFrame(tick); return; }
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    headerDisplay.value = targetNum * eased;
    if (t < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
const headerDisplayStr = computed(() => {
  if (isNaN(headerDisplay.value)) return hero.value.bigVal;
  // Если в hero.bigVal был "12" (int) — округляем, если "67.5" (float) — оставляем
  return Math.round(headerDisplay.value).toString();
});

// ─── Close + nav ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

// a11y: фокус-трап диалога + возврат фокуса при закрытии
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function gotoBusinessPlan() {
  router.push({ name: "business-plan" });
  close();
}
function rowPctColor(r: ExecBPCompanyRow): string {
  if (r.cls === "ok") return "#0F6E56";
  if (r.cls === "warn") return "#854F0B";
  if (r.cls === "bad") return "#A32D2D";
  return "#1E2A4A";
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
  <Teleport to="body">
    <Transition name="bpd-fade">
      <div class="bpd-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div ref="cardEl" tabindex="-1" class="bpd-card" :style="{ '--sc': meta.color }">
          <div class="bpd-stripe" aria-hidden="true" />
          <div class="bpd-shim" aria-hidden="true" />
          <div class="bpd-glow" aria-hidden="true" />

          <button class="bpd-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- Header -->
          <div class="bpd-sect bpd-row" style="--si:0; display:flex; justify-content:space-between; align-items:flex-end; gap:18px; flex-wrap:wrap; padding-top:20px;">
            <div>
              <div class="bpd-h-l">{{ meta.label }} · {{ block.metric_label || 'выручка' }}</div>
              <div class="bpd-h-v">
                <span class="num" :style="{ color: hero.bigColor }">{{ headerDisplayStr }}</span>
                <span class="unit">{{ hero.bigUnit }}</span>
              </div>
              <span
                v-if="hero.badge"
                class="bpd-h-d"
                :class="`bpd-h-d--${hero.badge.tone}`"
              >
                <svg v-if="hero.badge.tone === 'good'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 7l3-3 3 3"/></svg>
                <svg v-else-if="hero.badge.tone === 'bad'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 5l3 3 3-3"/></svg>
                {{ hero.badge.text }}
              </span>
            </div>
            <div class="bpd-h-tag-list">
              <CurrencyToggle :year="block.year" :compact="true" :show-rate="true" />
              <div style="margin-top:6px;">{{ block.with_pct_count || block.total_count }} компаний с план/факт</div>
              <div>{{ block.standard || "НСБУ" }} · {{ block.year }} финансовый год</div>
              <div class="bpd-h-tag-y" v-if="block.prev_year">сравнение с {{ block.prev_year }} годом</div>
            </div>
          </div>

          <!-- 4 mini-KPI strip -->
          <div class="bpd-sect bpd-row" style="--si:1;">
            <div class="bpd-mini-grid">
              <div
                v-for="(m, i) in miniKpis"
                :key="m.label"
                class="bpd-mini"
                :class="{ 'bpd-mini--em': m.emphasis }"
                :style="{ '--kc': m.accent, '--ki': i }"
              >
                <div class="bpd-mk-l">{{ m.label }}</div>
                <div class="bpd-mk-v">{{ m.value }}</div>
              </div>
            </div>
          </div>

          <!-- Distribution segmented bar -->
          <div class="bpd-sect bpd-row" style="--si:2;">
            <div class="bpd-l-sec">Распределение компаний</div>
            <div class="bpd-distrib">
              <div
                class="bpd-distrib-seg"
                :class="{ 'bpd-distrib-seg--dim': kind !== 'overall' && kind !== 'leaders' }"
                :style="{
                  background: '#1D9E75',
                  flex: `0 0 ${distrib.pctOk}%`,
                  animationDelay: '0.6s',
                }"
              >
                <span v-if="distrib.pctOk >= 12">{{ block.on_target }} · {{ distrib.pctOk }}%</span>
              </div>
              <div
                class="bpd-distrib-seg"
                :class="{ 'bpd-distrib-seg--dim': kind !== 'overall' && kind !== 'tracking' }"
                :style="{
                  background: '#EF9F27',
                  flex: `0 0 ${distrib.pctWarn}%`,
                  animationDelay: '0.74s',
                }"
              >
                <span v-if="distrib.pctWarn >= 12">{{ block.attention }} · {{ distrib.pctWarn }}%</span>
              </div>
              <div
                class="bpd-distrib-seg"
                :class="{ 'bpd-distrib-seg--dim': kind !== 'overall' && kind !== 'behind' }"
                :style="{
                  background: '#E24B4A',
                  flex: `0 0 ${distrib.pctBad}%`,
                  animationDelay: '0.88s',
                }"
              >
                <span v-if="distrib.pctBad >= 12">{{ block.behind }} · {{ distrib.pctBad }}%</span>
              </div>
            </div>
            <div class="bpd-leg">
              <span><i class="bpd-dot" style="background:#1D9E75"/>Опережают</span>
              <span><i class="bpd-dot" style="background:#EF9F27"/>На трекинге</span>
              <span><i class="bpd-dot" style="background:#E24B4A"/>Отстают</span>
            </div>
          </div>

          <!-- Body: overall → Leaders+Laggards split; else → kind list -->
          <template v-if="kind === 'overall' && meta.showLeadersLaggards">
            <div class="bpd-sect bpd-row" style="--si:3; display:grid; grid-template-columns:1fr 1fr; gap:18px; border-top:1px solid rgba(0,0,0,.05); padding-top:14px;">
              <div>
                <div class="bpd-l-sec" style="color:#0F6E56;">↑ Топ-3 опережают</div>
                <div class="bpd-ll-list">
                  <div
                    v-for="c in leaders"
                    :key="c.company_id"
                    class="bpd-ll-row"
                  >
                    <span class="name">{{ c.name }}</span>
                    <span class="val" :style="{ color: rowPctColor(c) }">{{ c.display_label || fmtPctDisplay(c.pct) + '%' }}</span>
                  </div>
                </div>
              </div>
              <div>
                <div class="bpd-l-sec" style="color:#A32D2D;">↓ Топ-3 отстают</div>
                <div class="bpd-ll-list">
                  <div
                    v-for="c in laggards"
                    :key="c.company_id"
                    class="bpd-ll-row"
                  >
                    <span class="name">{{ c.name }}</span>
                    <span class="val" :style="{ color: rowPctColor(c) }">{{ c.display_label || fmtPctDisplay(c.pct) + '%' }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <!-- Single-kind list: top-3 + collapse -->
            <div class="bpd-sect bpd-row" style="--si:3;">
              <div class="bpd-l-sec">
                <span>{{ meta.heroFocus === 'leaders' ? 'Лучшие из опережающих' : meta.heroFocus === 'tracking' ? 'Близко к плану' : 'Наибольший разрыв' }}</span>
                <span v-if="kindList.length > 3" class="bpd-l-side">остальные {{ kindList.length - 3 }} ниже</span>
              </div>
              <div v-if="kindListTop3.length" class="bpd-toplist">
                <div
                  v-for="(c, i) in kindListTop3"
                  :key="c.company_id"
                  class="bpd-top-row"
                  :title="c.display_label_full || ''"
                >
                  <span class="bpd-top-name">
                    <i class="bpd-top-tick" :style="{ background: sectorColor[c.sector] || '#888' }"/>
                    {{ c.name }}
                  </span>
                  <span class="bpd-top-vals">
                    <span class="amt">факт {{ fmtNum(c.fact_value) }}</span>
                    <span class="plan">из {{ fmtNum(c.plan_value) }}</span>
                  </span>
                  <span class="bpd-top-pct" :style="{ color: rowPctColor(c) }">
                    {{ c.display_label || fmtPctDisplay(c.pct) + '%' }}
                  </span>
                </div>
              </div>
              <div v-else class="bpd-empty">Нет компаний в этой категории</div>
            </div>
          </template>

          <!-- Collapsible full list -->
          <div v-if="(kind === 'overall' && sortedRows.length > 0) || (kind !== 'overall' && kindList.length > 3)" class="bpd-sect bpd-row" style="--si:4; padding-top:0;">
            <button
              type="button"
              class="bpd-collapse"
              :class="{ 'bpd-collapse--open': expandedAll }"
              @click="expandedAll = !expandedAll"
              :aria-expanded="expandedAll"
            >
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="11" height="11" class="bpd-collapse-chev">
                <path d="M3.5 5l3.5 3.5L10.5 5"/>
              </svg>
              {{ expandedAll
                ? `Свернуть · показано ${kind === 'overall' ? sortedRows.length : kindList.length}`
                : `Показать все ${kind === 'overall' ? sortedRows.length : kindList.length} компаний` }}
            </button>

            <div v-if="expandedAll" class="bpd-fulllist">
              <div
                v-for="(c, i) in (kind === 'overall' ? sortedRows : kindList)"
                :key="c.company_id"
                class="bpd-full-row"
              >
                <span class="bpd-full-idx">{{ i + 1 }}</span>
                <span class="bpd-full-name">
                  <i class="bpd-top-tick" :style="{ background: sectorColor[c.sector] || '#888' }"/>
                  {{ c.name }}
                </span>
                <span class="bpd-full-fact">{{ fmtNum(c.fact_value) }}</span>
                <span class="bpd-full-plan">{{ fmtNum(c.plan_value) }}</span>
                <span class="bpd-full-pct" :style="{ color: rowPctColor(c) }">{{ c.display_label || fmtPctDisplay(c.pct) + '%' }}</span>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="bpd-ftr bpd-row" style="--si:5;">
            <button class="bpd-btn bpd-btn-g" @click="close">Закрыть</button>
            <button class="bpd-btn bpd-btn-p" @click="gotoBusinessPlan">
              Открыть Бизнес-план
              <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="12" height="12">
                <path d="M3 7h8M7.5 3.5L11 7l-3.5 3.5"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.bpd-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.bpd-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 720px; overflow: hidden; animation: bpdIn .55s var(--ease-standard) .08s both; }
.bpd-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: bpdStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.bpd-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: bpdShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.bpd-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.bpd-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.bpd-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.bpd-row { animation: bpdUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.bpd-sect { padding: 14px 22px; }
.bpd-sect + .bpd-sect { padding-top: 0; }

.bpd-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.bpd-h-v { font-size: 44px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 4px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.bpd-h-v .unit { font-size: 13px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.bpd-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; }
.bpd-h-d--good { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.bpd-h-d--bad { background: rgba(226, 75, 74, .10); color: var(--sev-critical); }
.bpd-h-d--neutral { background: rgba(239, 159, 39, .10); color: #854F0B; }
.bpd-h-tag-list { text-align: right; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; line-height: 1.7; }
.bpd-h-tag-y { color: var(--t1, #1E2A4A); margin-top: 2px; }

.bpd-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.bpd-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; transition: transform 0.2s ease; }
.bpd-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: bpdKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards; }
.bpd-mini--em { background: linear-gradient(180deg, rgba(127, 119, 221, 0.06), #FAFAFC); transform: scale(1.02); box-shadow: 0 4px 14px rgba(127, 119, 221, 0.12); }
.bpd-mini--em::before { height: 3px; }
.bpd-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bpd-mk-v { font-size: 17px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 3px; font-feature-settings: "tnum"; white-space: nowrap; }

.bpd-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.bpd-l-side { font-size: 9.5px; color: #6B6A66; text-transform: none; letter-spacing: .02em; font-weight: 400; }

/* Distribution bar */
.bpd-distrib { height: 30px; background: #F1EFE8; border-radius: 6px; overflow: hidden; display: flex; }
.bpd-distrib-seg { height: 100%; transform: scaleX(0); transform-origin: left; animation: bpdBar 1.1s var(--ease-standard) forwards; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; font-weight: 500; transition: opacity 0.2s ease, filter 0.2s ease; }
.bpd-distrib-seg--dim { opacity: 0.4; filter: saturate(0.6); }
.bpd-leg { display: flex; gap: 14px; margin-top: 9px; font-size: 11px; color: var(--t3, #5F5E5A); font-weight: 500; }
.bpd-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }

/* Leaders/Laggards */
.bpd-ll-list { display: flex; flex-direction: column; gap: 0; }
.bpd-ll-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px dashed rgba(0, 0, 0, 0.06); font-size: 11.5px; }
.bpd-ll-row:last-child { border-bottom: none; }
.bpd-ll-row .name { color: var(--t1, #1E2A4A); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
.bpd-ll-row .val { font-weight: 500; font-feature-settings: "tnum"; }

/* Top-3 list */
.bpd-toplist { display: flex; flex-direction: column; gap: 6px; }
.bpd-top-row { display: grid; grid-template-columns: 1fr 150px 70px; gap: 10px; align-items: center; font-size: 11.5px; padding: 4px 6px; border-radius: 5px; }
.bpd-top-name { color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bpd-top-tick { width: 3px; height: 12px; opacity: .85; flex-shrink: 0; }
.bpd-top-vals { display: flex; flex-direction: column; gap: 1px; line-height: 1.15; text-align: right; }
.bpd-top-vals .amt { font-size: 11px; color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.bpd-top-vals .plan { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-feature-settings: "tnum"; }
.bpd-top-pct { text-align: right; font-weight: 500; font-feature-settings: "tnum"; }

/* Collapsible */
.bpd-collapse { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 11px 14px; border-radius: 8px; border: 1px dashed rgba(127, 119, 221, .30); background: rgba(127, 119, 221, .04); color: var(--p-deep); font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s ease; }
.bpd-collapse:hover { background: rgba(127, 119, 221, .07); border-style: solid; }
.bpd-collapse-chev { color: #7F77DD; transition: transform .2s ease; }
.bpd-collapse--open .bpd-collapse-chev { transform: rotate(180deg); }

.bpd-fulllist { margin-top: 8px; border-radius: 8px; background: var(--bg2, #FAFAFC); padding: 4px; max-height: 320px; overflow-y: auto; }
.bpd-full-row { display: grid; grid-template-columns: 22px 1fr 90px 90px 60px; gap: 8px; align-items: center; font-size: 11px; padding: 6px 8px; border-radius: 5px; transition: background .12s; }
.bpd-full-row:hover { background: var(--bg1, #fff); box-shadow: 0 1px 4px rgba(15, 23, 60, .05); }
.bpd-full-idx { color: #6B6A66; font-weight: 500; font-feature-settings: "tnum"; font-size: 10px; text-align: right; }
.bpd-full-name { color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bpd-full-fact, .bpd-full-plan { text-align: right; font-feature-settings: "tnum"; font-size: 10.5px; }
.bpd-full-fact { color: var(--t1, #1E2A4A); font-weight: 500; }
.bpd-full-plan { color: var(--t3, var(--t-muted)); }
.bpd-full-pct { text-align: right; font-feature-settings: "tnum"; font-weight: 500; }

.bpd-empty { padding: 16px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11.5px; font-style: italic; }

.bpd-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.bpd-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.bpd-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.bpd-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.bpd-btn-p { background: var(--sc); color: #fff; }
.bpd-btn-p:hover { filter: brightness(.93); }

.bpd-fade-enter-active, .bpd-fade-leave-active { transition: opacity .28s ease; }
.bpd-fade-enter-from, .bpd-fade-leave-to { opacity: 0; }
.bpd-fade-leave-active .bpd-card { animation: bpdOut .24s ease forwards; }

@keyframes bpdIn { 0% { opacity: 0; transform: translateY(22px) scale(.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes bpdOut { to { opacity: 0; transform: translateY(8px) scale(.98); } }
@keyframes bpdStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes bpdShim { 0% { transform: translateX(-120%); } 60% { transform: translateX(220%); } 100% { transform: translateX(220%); } }
@keyframes bpdUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes bpdBar { to { transform: scaleX(1); } }
@keyframes bpdKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 600px) {
  .bpd-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .bpd-top-row { grid-template-columns: 1fr 110px 56px; font-size: 11px; }
  .bpd-h-v { font-size: 32px; }
  .bpd-full-row { grid-template-columns: 22px 1fr 60px 60px; }
  .bpd-full-pct { display: none; }
}
</style>
