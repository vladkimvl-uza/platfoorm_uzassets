<script setup lang="ts">
/**
 * EconomicEffectDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Premium drill-down модалка для блока «Экономический эффект портфеля»
 * (ExecDashEconomicEffectBlock). Открывается кликом на любую из 4
 * KPI-карточек (Реализовано / План / Остаток / % реализации) или на
 * заголовок блока (kind='overview').
 *
 * Variant A · Briefing — single-column compact layout:
 *   • Header: KPI label + большое число + delta-бейдж (% от плана / etc)
 *   • 4 mini-KPI strip per kind (3 оставшихся числа + лидер сектор)
 *   • Sector breakdown — horizontal stacked bar + легенда
 *   • Top-3 проекта по релевантному значению
 *   • Коллапс «Показать все N проектов» (свёрнут по умолчанию)
 *   • Footer: «Открыть проекты с эффектом» → /projects?has_effect=true
 *
 * Pack 7.33
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import type { ExecEEKpi, ExecEEProject } from "@/api/executiveDashboard";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import CurrencyToggle from "@/components/UZA/CurrencyToggle.vue";

export type EeKind =
  | "overview"
  | "realized"
  | "planned"
  | "pipeline"
  | "conversion";

interface Props {
  kind: EeKind;
  kpi: ExecEEKpi;
  projects: ExecEEProject[];
  year: number;
  sectorColor: Record<string, string>;
  sectorLabel: Record<string, string>; // canonical code → label (для bar легенды)
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const conv = useCurrencyConverter();

// ─── KPI metadata ───
interface KpiMeta {
  label: string;
  color: string;
  /** Главное число (в млрд сум или %) */
  bigGetter: (k: ExecEEKpi) => { value: number; isPct: boolean };
  /** Бейдж под заголовком */
  badge: (k: ExecEEKpi) => { text: string; tone: "good" | "bad" | "neutral" } | null;
  /** Какое поле проекта используется для топ-листа и sector breakdown */
  projField: (p: ExecEEProject) => number;
  /** Заголовок секции "Top-N по ..." */
  topTitle: string;
  /** Является ли проект-поле процентом (для conversion kind) */
  projIsPct: boolean;
}

const KPI_META: Record<EeKind, KpiMeta> = {
  overview: {
    label: "Экономический эффект портфеля",
    color: "#1D9E75",
    bigGetter: (k) => ({ value: k.realized_sum, isPct: false }),
    badge: (k) => ({
      text: k.conversion_pct + "% от плана · " + k.total_count + " проектов",
      tone: k.conversion_pct >= 75 ? "good" : k.conversion_pct >= 40 ? "neutral" : "bad",
    }),
    projField: (p) => p.realized_value,
    topTitle: "Три крупнейших проекта по реализованному эффекту",
    projIsPct: false,
  },
  realized: {
    label: "Реализованный эффект",
    color: "#1D9E75",
    bigGetter: (k) => ({ value: k.realized_sum, isPct: false }),
    badge: (k) => ({
      text: k.conversion_pct + "% от плана · " + k.done_count + " завершённых",
      tone: k.conversion_pct >= 75 ? "good" : k.conversion_pct >= 40 ? "neutral" : "bad",
    }),
    projField: (p) => p.realized_value,
    topTitle: "Три крупнейших проекта по реализованному эффекту",
    projIsPct: false,
  },
  planned: {
    label: "Плановый эффект (потенциал)",
    color: "#EF9F27",
    bigGetter: (k) => ({ value: k.planned_sum, isPct: false }),
    badge: (k) => ({
      text: k.total_count + " проектов с целевым эффектом",
      tone: "neutral",
    }),
    projField: (p) => p.planned_value,
    topTitle: "Три крупнейших проекта по плановому эффекту",
    projIsPct: false,
  },
  pipeline: {
    label: "Остаток до плана",
    color: "#7F77DD",
    bigGetter: (k) => ({ value: k.pipeline_sum, isPct: false }),
    badge: (k) => ({
      text: "∑ (план − факт) по портфелю",
      tone: k.pipeline_sum > k.realized_sum ? "bad" : "neutral",
    }),
    projField: (p) => Math.max(0, p.planned_value - p.realized_value),
    topTitle: "Три проекта с наибольшим разрывом план/факт",
    projIsPct: false,
  },
  conversion: {
    label: "Процент реализации",
    color: "#378ADD",
    bigGetter: (k) => ({ value: k.conversion_pct, isPct: true }),
    badge: (k) => ({
      text: "факт ÷ план · " + k.done_count + " завершено из " + k.total_count,
      tone: k.conversion_pct >= 75 ? "good" : k.conversion_pct >= 40 ? "neutral" : "bad",
    }),
    projField: (p) => p.pct_realized,
    topTitle: "Три проекта с наибольшим процентом реализации",
    projIsPct: true,
  },
};

const meta = computed(() => KPI_META[props.kind]);
const bigSpec = computed(() => {
  const raw = meta.value.bigGetter(props.kpi);
  if (raw.isPct) {
    return { value: raw.value, unit: "процент", isPct: true };
  }
  // Динамическая единица из converter (млрд сум / трлн сум / млн USD / млрд USD)
  const f = conv.format(raw.value, props.year);
  return { value: raw.value, unit: f.unit, isPct: false };
});
const badge = computed(() => meta.value.badge(props.kpi));

// ─── Format (Pack 7.34: 3 decimals + USD conversion via composable) ───
// Все денежные значения в EE block приходят в млрд сум (см. _pack5_blocks.py).
function fmtMoney(v: number | null | undefined): { value: string; unit: string } {
  if (v == null || !isFinite(v)) return { value: "—", unit: "" };
  const f = conv.format(v, props.year);
  return { value: f.value, unit: f.unit };
}
// Только числовое значение (для inline-вёрстки)
function fmtMlrd(v: number | null | undefined): string {
  return fmtMoney(v).value;
}
function fmtBig(spec: { value: number; isPct: boolean }): string {
  if (spec.isPct) return Math.round(spec.value).toString();
  return fmtMlrd(spec.value);
}

// ─── Sector aggregation ───
interface SectorAgg {
  id: string;
  label: string;
  color: string;
  total: number;
  count: number;
  pct: number;
}
const sectorAgg = computed<SectorAgg[]>(() => {
  const map = new Map<string, SectorAgg>();
  for (const p of props.projects) {
    const id = p.sector || "other";
    if (!map.has(id)) {
      map.set(id, {
        id,
        label: props.sectorLabel[id] || id,
        color: props.sectorColor[id] || "#888780",
        total: 0,
        count: 0,
        pct: 0,
      });
    }
    const v = meta.value.projField(p);
    const s = map.get(id)!;
    s.total += v;
    s.count++;
  }
  const arr = Array.from(map.values()).filter((s) => s.total !== 0);
  const grand = arr.reduce((a, x) => a + Math.abs(x.total), 0) || 1;
  for (const s of arr) s.pct = Math.round((Math.abs(s.total) / grand) * 100);
  arr.sort((a, b) => Math.abs(b.total) - Math.abs(a.total));
  return arr;
});
const topSector = computed(() => sectorAgg.value[0] ?? null);

// ─── Mini-KPI strip per kind ───
interface MiniKpi { label: string; value: string; accent: string }
const miniKpis = computed<MiniKpi[]>(() => {
  const k = props.kpi;
  const top = topSector.value?.label ?? "—";
  const fmtMon = (v: number) => {
    const f = conv.format(v, props.year);
    return f.value + " " + f.unit;
  };
  switch (props.kind) {
    case "overview":
    case "realized":
      return [
        { label: "Плановый эффект", value: fmtMon(k.planned_sum), accent: "#EF9F27" },
        { label: "Остаток до плана", value: fmtMon(k.pipeline_sum), accent: "#7F77DD" },
        {
          label: "Средний вклад на проект",
          value: k.done_count > 0 ? fmtMon(k.realized_sum / k.done_count) : "—",
          accent: "#1D9E75",
        },
        { label: "Лидирующий сектор", value: top, accent: "#378ADD" },
      ];
    case "planned":
      return [
        { label: "Реализованный эффект", value: fmtMon(k.realized_sum), accent: "#1D9E75" },
        { label: "Процент реализации", value: k.conversion_pct + " процентов", accent: "#378ADD" },
        {
          label: "Средний план на проект",
          value: k.total_count > 0 ? fmtMon(k.planned_sum / k.total_count) : "—",
          accent: "#EF9F27",
        },
        { label: "Лидирующий сектор", value: top, accent: "#7F77DD" },
      ];
    case "pipeline":
      return [
        { label: "Плановый эффект", value: fmtMon(k.planned_sum), accent: "#EF9F27" },
        { label: "Реализованный эффект", value: fmtMon(k.realized_sum), accent: "#1D9E75" },
        { label: "Процент реализации", value: k.conversion_pct + " процентов", accent: "#378ADD" },
        { label: "Лидирующий сектор", value: top, accent: "#7F77DD" },
      ];
    case "conversion":
      return [
        { label: "Реализованный эффект", value: fmtMon(k.realized_sum), accent: "#1D9E75" },
        { label: "Плановый эффект", value: fmtMon(k.planned_sum), accent: "#EF9F27" },
        { label: "Завершено проектов", value: k.done_count + " из " + k.total_count, accent: "#7F77DD" },
        { label: "Лидирующий сектор", value: top, accent: "#378ADD" },
      ];
  }
});

// ─── Top projects ───
const sortedProjects = computed(() => {
  const arr = [...props.projects];
  arr.sort((a, b) => meta.value.projField(b) - meta.value.projField(a));
  return arr;
});
const topProjects = computed(() => sortedProjects.value.slice(0, 3));
const topMaxAbs = computed(() => {
  return Math.max(
    1,
    ...topProjects.value.map((p) => Math.abs(meta.value.projField(p))),
  );
});

// ─── Collapse state ───
const expandedAll = ref(false);

// ─── Header count-up ───
const headerDisplay = ref<number>(0);
function startCountUp() {
  const target = bigSpec.value.value;
  if (typeof target !== "number" || !isFinite(target)) {
    headerDisplay.value = target;
    return;
  }
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduced) { headerDisplay.value = target; return; }
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

// ─── Close + nav ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }
function gotoProjects() {
  router.push({ name: "projects", query: { has_effect: "1", year: props.year } });
  close();
}
function gotoProject(id: string) {
  // project-detail page удалён — открываем проект in-place в списке «Проекты»
  if (id) router.push({ name: "projects", query: { open: id } });
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
    <Transition name="eed-fade">
      <div class="eed-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div class="eed-card" :style="{ '--sc': meta.color }">
          <div class="eed-stripe" aria-hidden="true" />
          <div class="eed-shim" aria-hidden="true" />
          <div class="eed-glow" aria-hidden="true" />

          <button class="eed-x" @click="close" aria-label="Закрыть">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- Header -->
          <div class="eed-sect eed-row" style="--si:0; display:flex; justify-content:space-between; align-items:flex-end; gap:18px; flex-wrap:wrap; padding-top:20px;">
            <div>
              <div class="eed-h-l">{{ meta.label }}</div>
              <div class="eed-h-v">
                <span class="num">{{ fmtBig({ value: headerDisplay, isPct: bigSpec.isPct }) }}</span>
                <span class="unit">{{ bigSpec.unit }}</span>
              </div>
              <span
                v-if="badge"
                class="eed-h-d"
                :class="`eed-h-d--${badge.tone}`"
              >
                <svg v-if="badge.tone === 'good'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 7l3-3 3 3"/></svg>
                <svg v-else-if="badge.tone === 'bad'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 5l3 3 3-3"/></svg>
                {{ badge.text }}
              </span>
            </div>
            <div class="eed-h-tag-list">
              <CurrencyToggle v-if="!bigSpec.isPct" :year="year" :compact="true" :show-rate="true" />
              <div style="margin-top:6px;">{{ kpi.total_count }} проектов с эффектом</div>
              <div>{{ kpi.done_count }} завершено<span v-if="kpi.active_count > 0"> · {{ kpi.active_count }} активны</span></div>
              <div class="eed-h-tag-year">{{ year }} финансовый год</div>
            </div>
          </div>

          <!-- 4 mini-KPI strip -->
          <div class="eed-sect eed-row" style="--si:1;">
            <div class="eed-mini-grid">
              <div
                v-for="(m, i) in miniKpis"
                :key="m.label"
                class="eed-mini"
                :style="{ '--kc': m.accent, '--ki': i }"
              >
                <div class="eed-mk-l">{{ m.label }}</div>
                <div class="eed-mk-v">{{ m.value }}</div>
              </div>
            </div>
          </div>

          <!-- Sector breakdown -->
          <div class="eed-sect eed-row" style="--si:2;">
            <div class="eed-l-sec">Распределение по секторам</div>
            <div v-if="sectorAgg.length" class="eed-bar">
              <div
                v-for="(s, i) in sectorAgg"
                :key="s.id"
                class="eed-bar-seg"
                :style="{
                  background: s.color,
                  flex: `0 0 ${s.pct}%`,
                  animationDelay: (0.55 + i * 0.13) + 's',
                }"
                :title="`${s.label} · ${fmtMoney(s.total).value} ${fmtMoney(s.total).unit}`"
              />
            </div>
            <div v-if="sectorAgg.length" class="eed-leg">
              <span v-for="s in sectorAgg" :key="s.id">
                <i class="eed-dot" :style="{ background: s.color }"/>
                {{ s.label }} · <strong>{{ fmtMoney(s.total).value }}</strong>
                <span class="eed-leg-unit">{{ fmtMoney(s.total).unit }}</span>
                <span class="eed-leg-pct">{{ s.pct }} процентов</span>
              </span>
            </div>
            <div v-else class="eed-empty">Нет данных по секторам</div>
          </div>

          <!-- Top-3 projects -->
          <div class="eed-sect eed-row" style="--si:3;">
            <div class="eed-l-sec">
              <span>{{ meta.topTitle }}</span>
              <span v-if="sortedProjects.length > 3" class="eed-l-side">
                остальные {{ sortedProjects.length - 3 }} ниже
              </span>
            </div>
            <div v-if="topProjects.length" class="eed-toplist">
              <div
                v-for="(p, i) in topProjects"
                :key="p.project_id"
                class="eed-top-row"
                @click="gotoProject(p.project_id)"
                :title="'Открыть проект «' + p.title + '»'"
              >
                <span class="eed-top-name">
                  <i class="eed-top-tick" :style="{ background: sectorColor[p.sector] || '#888' }"/>
                  <span class="eed-top-name-text">{{ p.title }}<span class="eed-top-co"> · {{ p.company_name }}</span></span>
                </span>
                <span class="eed-top-bar">
                  <span
                    class="eed-top-fill"
                    :style="{
                      background: sectorColor[p.sector] || '#888',
                      width: ((Math.abs(meta.projField(p)) / topMaxAbs) * 100) + '%',
                      animationDelay: (1.0 + i * 0.07) + 's',
                    }"
                  />
                </span>
                <span class="eed-top-val">
                  <span class="amt">
                    {{ meta.projIsPct ? fmtMlrd(meta.projField(p)) + ' процентов' : fmtMoney(meta.projField(p)).value }}
                    <span v-if="!meta.projIsPct" class="eed-amt-unit">{{ fmtMoney(meta.projField(p)).unit }}</span>
                  </span>
                  <span class="pct" v-if="!meta.projIsPct">реализовано {{ p.pct_realized }} процентов</span>
                </span>
              </div>
            </div>
            <div v-else class="eed-empty">Нет проектов с данными</div>
          </div>

          <!-- Collapsible full list -->
          <div v-if="sortedProjects.length > 3" class="eed-sect eed-row" style="--si:4; padding-top:0;">
            <button
              type="button"
              class="eed-collapse"
              :class="{ 'eed-collapse--open': expandedAll }"
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
                class="eed-collapse-chev"
              >
                <path d="M3.5 5l3.5 3.5L10.5 5"/>
              </svg>
              {{ expandedAll
                ? `Свернуть · показано ${sortedProjects.length}`
                : `Показать все ${sortedProjects.length} проектов с эффектом` }}
            </button>

            <div v-if="expandedAll" class="eed-fulllist">
              <div
                v-for="(p, i) in sortedProjects.slice(3)"
                :key="p.project_id"
                class="eed-full-row"
                @click="gotoProject(p.project_id)"
              >
                <span class="eed-full-idx">{{ i + 4 }}</span>
                <span class="eed-full-name">
                  <i class="eed-top-tick" :style="{ background: sectorColor[p.sector] || '#888' }"/>
                  <span class="eed-full-name-text">{{ p.title }}</span>
                </span>
                <span class="eed-full-co">{{ p.company_name }}</span>
                <span class="eed-full-val">
                  {{ meta.projIsPct ? fmtMlrd(meta.projField(p)) : fmtMoney(meta.projField(p)).value }}<span v-if="meta.projIsPct">%</span><span v-else class="eed-full-unit"> {{ fmtMoney(meta.projField(p)).unit }}</span>
                </span>
                <span class="eed-full-pct">{{ p.pct_realized }} процентов</span>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="eed-ftr eed-row" style="--si:5;">
            <button class="eed-btn eed-btn-g" @click="close">Закрыть</button>
            <button class="eed-btn eed-btn-p" @click="gotoProjects">
              Открыть проекты с эффектом
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
.eed-bd {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px 16px;
  overflow-y: auto;
}
.eed-card {
  position: relative;
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10);
  width: 100%;
  max-width: 720px;
  overflow: hidden;
  animation: eedIn .55s var(--ease-standard) .08s both;
}
.eed-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: eedStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.eed-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: eedShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.eed-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.eed-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.eed-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.eed-row { animation: eedUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.eed-sect { padding: 14px 22px; }
.eed-sect + .eed-sect { padding-top: 0; }

.eed-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.eed-h-v { font-size: 44px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 4px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.eed-h-v .unit { font-size: 13px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.eed-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; }
.eed-h-d--good { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.eed-h-d--bad { background: rgba(226, 75, 74, .10); color: var(--sev-critical); }
.eed-h-d--neutral { background: rgba(127, 119, 221, .08); color: var(--p-deep); }
.eed-h-tag-list { text-align: right; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; line-height: 1.7; }
.eed-h-tag-year { color: var(--t1, #1E2A4A); margin-top: 2px; }

.eed-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.eed-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; }
.eed-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: eedKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards; }
.eed-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eed-mk-v { font-size: 15px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 3px; font-feature-settings: "tnum"; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.eed-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.eed-l-side { font-size: 9.5px; color: #B4B2A9; text-transform: none; letter-spacing: .02em; font-weight: 400; }

.eed-bar { height: 11px; background: #F1EFE8; border-radius: 5px; overflow: hidden; display: flex; }
.eed-bar-seg { height: 100%; transform: scaleX(0); transform-origin: left; animation: eedBar 1.1s var(--ease-standard) forwards; }
.eed-leg { display: flex; gap: 14px; margin-top: 9px; font-size: 11px; color: var(--t3, #5F5E5A); font-weight: 500; flex-wrap: wrap; }
.eed-leg strong { color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.eed-leg-pct { color: var(--t3, var(--t-muted)); margin-left: 3px; font-feature-settings: "tnum"; }
.eed-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }

.eed-toplist { display: flex; flex-direction: column; gap: 6px; }
.eed-top-row { display: grid; grid-template-columns: 200px 1fr 95px; gap: 10px; align-items: center; font-size: 11.5px; cursor: pointer; padding: 4px 6px; border-radius: 5px; transition: background .12s; }
.eed-top-row:hover { background: rgba(127, 119, 221, .04); }
.eed-top-name { color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 7px; overflow: hidden; }
.eed-top-name-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eed-top-co { color: var(--t3, var(--t-muted)); font-weight: 400; }
.eed-top-tick { width: 3px; height: 12px; opacity: .85; flex-shrink: 0; }
.eed-top-bar { height: 6px; background: #F1EFE8; border-radius: 3px; overflow: hidden; }
.eed-top-fill { display: block; height: 100%; transform: scaleX(0); transform-origin: left; animation: eedBar 1s var(--ease-standard) forwards; }
.eed-top-val { text-align: right; color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; display: flex; flex-direction: column; gap: 1px; line-height: 1.1; }
.eed-top-val .amt { font-size: 11.5px; }
.eed-top-val .pct { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 400; }
.eed-amt-unit { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-left: 3px; }
.eed-full-unit { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.eed-leg-unit { color: var(--t3, var(--t-muted)); margin-left: 3px; font-weight: 500; }

.eed-collapse { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; padding: 11px 14px; border-radius: 8px; border: 1px dashed rgba(127, 119, 221, .30); background: rgba(127, 119, 221, .04); color: var(--p-deep); font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s ease; }
.eed-collapse:hover { background: rgba(127, 119, 221, .07); border-style: solid; }
.eed-collapse-chev { color: #7F77DD; transition: transform .2s ease; }
.eed-collapse--open .eed-collapse-chev { transform: rotate(180deg); }

.eed-fulllist { margin-top: 8px; border-radius: 8px; background: var(--bg2, #FAFAFC); padding: 4px; max-height: 280px; overflow-y: auto; }
.eed-full-row { display: grid; grid-template-columns: 24px 1fr 130px 80px 40px; gap: 8px; align-items: center; font-size: 11px; padding: 6px 8px; cursor: pointer; border-radius: 5px; transition: background .12s; }
.eed-full-row:hover { background: var(--bg1, #fff); box-shadow: 0 1px 4px rgba(15, 23, 60, .05); }
.eed-full-idx { color: #B4B2A9; font-weight: 500; font-feature-settings: "tnum"; font-size: 10px; text-align: right; }
.eed-full-name { color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 7px; overflow: hidden; }
.eed-full-name-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.eed-full-co { color: var(--t3, var(--t-muted)); font-size: 10px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eed-full-val { text-align: right; font-feature-settings: "tnum"; color: var(--t1, #1E2A4A); font-weight: 500; }
.eed-full-pct { text-align: right; font-size: 10px; color: var(--t3, var(--t-muted)); font-feature-settings: "tnum"; }

.eed-empty { padding: 16px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11.5px; font-style: italic; }

.eed-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.eed-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.eed-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.eed-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.eed-btn-p { background: var(--sc); color: #fff; }
.eed-btn-p:hover { filter: brightness(.93); }

.eed-fade-enter-active, .eed-fade-leave-active { transition: opacity .28s ease; }
.eed-fade-enter-from, .eed-fade-leave-to { opacity: 0; }
.eed-fade-leave-active .eed-card { animation: eedOut .24s ease forwards; }

@keyframes eedIn { 0% { opacity: 0; transform: translateY(22px) scale(.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes eedOut { to { opacity: 0; transform: translateY(8px) scale(.98); } }
@keyframes eedStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes eedShim { 0% { transform: translateX(-120%); } 60% { transform: translateX(220%); } 100% { transform: translateX(220%); } }
@keyframes eedUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes eedBar { to { transform: scaleX(1); } }
@keyframes eedKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 600px) {
  .eed-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .eed-top-row { grid-template-columns: 130px 1fr 75px; font-size: 11px; }
  .eed-h-v { font-size: 32px; }
  .eed-full-row { grid-template-columns: 22px 1fr 60px 36px; }
  .eed-full-co { display: none; }
}
</style>
