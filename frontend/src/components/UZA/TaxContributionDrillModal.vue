<script setup lang="ts">
/**
 * TaxContributionDrillModal.vue
 * ─────────────────────────────────────────────────────────────────
 * Premium drill-down модалка для блока «Налоговый вклад портфеля»
 * (ExecDashTaxContributionBlock). Открывается кликом на любую из 4
 * KPI-карточек:
 *
 *   Налог на прибыль          → kind='income_tax'   (#378ADD)
 *   НДС (12% от выручки)      → kind='vat'          (#1D9E75)
 *   Итого вклад               → kind='total'        (#7F77DD)
 *   Процент бюджета РУ        → kind='budget_share' (#EF9F27)
 *
 * Variant A briefing для всех 4 (по выбору Vladimir Kim):
 *   • Header: KPI label + большое число + delta-бейдж + переключатель валюты
 *   • 4 mini-KPI strip (per kind: другие три KPI + лидирующий сектор)
 *   • Сектор breakdown — горизонтальный stacked bar + легенда
 *   • Топ-5 плательщиков (с барами, кликабельны для перехода к компании)
 *   • Коллапс «Показать все компании с налоговыми данными»
 *   • Footer: «Открыть финансовые данные» → /financials
 *
 * Особенности:
 *   • Все денежные значения форматируются с тремя знаками после запятой
 *     (47.412 миллиард сум) — чтобы избежать путаницы с триллионами
 *   • Глобальный переключатель UZS / USD через useCurrencyConverter
 *   • Полные подписи (без сокращений) — «Лидирующий сектор», «Горно-
 *     металлургический комплекс» вместо «Лидер сектор», «Горно-мет.»
 *
 * Pack 7.34
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useFocusTrap } from "@/composables/useFocusTrap";
import { useRouter } from "vue-router";
import type { ExecTaxKpi, ExecTaxTopPayer } from "@/api/executiveDashboard";
import { useCurrencyConverter } from "@/composables/useCurrencyConverter";
import CurrencyToggle from "@/components/UZA/CurrencyToggle.vue";

export type TaxKind = "income_tax" | "vat" | "total" | "budget_share";

interface Props {
  kind: TaxKind;
  kpi: ExecTaxKpi;
  topPayers: ExecTaxTopPayer[];
  year: number;
  prevYear: number;
  cosCount: number;
  standardLabel: string; // "НСБУ" / "МСФО"
  sectorColor: Record<string, string>;
  sectorLabel: Record<string, string>; // полное название сектора
}
const props = defineProps<Props>();
const emit = defineEmits<{ close: [] }>();
const router = useRouter();
const conv = useCurrencyConverter();

// ─── KPI metadata per kind ───
interface KindMeta {
  label: string;
  color: string;
  /** Хедер-значение (в млрд сум для UZS режима) */
  bigValueMlrd: (k: ExecTaxKpi) => number | null;
  /** Является ли значение процентом — для kind='budget_share' */
  isPct: boolean;
  /** Бейдж под заголовком */
  badge: (k: ExecTaxKpi) => { text: string; tone: "good" | "bad" | "neutral" } | null;
}

const KIND_META: Record<TaxKind, KindMeta> = {
  income_tax: {
    label: "Налог на прибыль — вклад в бюджет",
    color: "#378ADD",
    bigValueMlrd: (k) => k.income_tax,
    isPct: false,
    badge: (k) => k.yoy_income_tax_pct != null
      ? {
          text: fmtSignedPct(k.yoy_income_tax_pct) + " к предыдущему году",
          tone: k.yoy_income_tax_pct >= 0 ? "good" : "bad",
        }
      : null,
  },
  vat: {
    label: "Налог на добавленную стоимость — вклад в бюджет",
    color: "#1D9E75",
    bigValueMlrd: (k) => k.vat,
    isPct: false,
    badge: (k) => k.yoy_vat_pct != null
      ? {
          text: fmtSignedPct(k.yoy_vat_pct) + " к предыдущему году · ставка 12% от выручки",
          tone: k.yoy_vat_pct >= 0 ? "good" : "bad",
        }
      : { text: "ставка 12% от выручки", tone: "neutral" },
  },
  total: {
    label: "Итоговый налоговый вклад портфеля",
    color: "#7F77DD",
    bigValueMlrd: (k) => k.total,
    isPct: false,
    badge: (k) => k.yoy_total_pct != null
      ? {
          text: fmtSignedPct(k.yoy_total_pct) + " к предыдущему году · налог на прибыль плюс НДС",
          tone: k.yoy_total_pct >= 0 ? "good" : "bad",
        }
      : { text: "налог на прибыль плюс налог на добавленную стоимость", tone: "neutral" },
  },
  budget_share: {
    label: "Доля портфеля в доходной части бюджета Республики Узбекистан",
    color: "#EF9F27",
    bigValueMlrd: (k) => k.budget_share_pct,
    isPct: true,
    badge: (k) => k.budget != null
      ? {
          text: "из " + conv.format(k.budget, props.year).full,
          tone: (k.budget_share_pct ?? 0) >= 25 ? "good" : "neutral",
        }
      : null,
  },
};

const meta = computed(() => KIND_META[props.kind]);

// ─── Forматтеры ───
function fmtSignedPct(v: number | null | undefined, decimals = 1): string {
  if (v == null || !isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return sign + v.toFixed(decimals) + "%";
}
function fmt3(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const parts = (Math.round(v * 1000) / 1000).toFixed(3).split(".");
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, "\u00A0");
  return parts.join(".").replace(/\u00A0/g, " ");
}

// ─── Hero values (в активной валюте) ───
const heroFormatted = computed(() => {
  const m = meta.value;
  const raw = m.bigValueMlrd(props.kpi);
  if (raw == null) return { value: "—", unit: "" };
  if (m.isPct) {
    return { value: fmt3(raw), unit: "% от 350.000 триллион сум" };
  }
  const f = conv.format(raw, props.year);
  return { value: f.value, unit: f.unit };
});

const badgeText = computed(() => meta.value.badge(props.kpi));

// ─── Sector aggregation (по amount из top_payers) ───
interface SectorAgg {
  id: string;
  label: string;
  color: string;
  totalMlrd: number; // сырое в млрд сум
  count: number;
  pct: number;
}
const sectorAgg = computed<SectorAgg[]>(() => {
  const map = new Map<string, SectorAgg>();
  for (const p of props.topPayers) {
    const id = p.sector || "other";
    if (!map.has(id)) {
      map.set(id, {
        id,
        label: props.sectorLabel[id] || id,
        color: props.sectorColor[id] || "#888780",
        totalMlrd: 0,
        count: 0,
        pct: 0,
      });
    }
    const s = map.get(id)!;
    s.totalMlrd += Number(p.amount ?? 0);
    s.count++;
  }
  const arr = Array.from(map.values()).filter((s) => s.totalMlrd !== 0);
  const grand = arr.reduce((a, x) => a + Math.abs(x.totalMlrd), 0) || 1;
  for (const s of arr) s.pct = Math.round((Math.abs(s.totalMlrd) / grand) * 100);
  arr.sort((a, b) => Math.abs(b.totalMlrd) - Math.abs(a.totalMlrd));
  return arr;
});
const topSector = computed(() => sectorAgg.value[0] ?? null);

// ─── 4 mini-KPI strip per kind ───
interface MiniKpi {
  label: string;
  value: string;
  unit: string;
  accent: string;
}
const miniKpis = computed<MiniKpi[]>(() => {
  const k = props.kpi;
  const top = topSector.value?.label ?? "—";
  const fmtAmount = (mlrd: number | null) => {
    if (mlrd == null) return { value: "—", unit: "" };
    const f = conv.format(mlrd, props.year);
    return { value: f.value, unit: f.unit };
  };

  switch (props.kind) {
    case "income_tax": {
      return [
        { label: "Налог на добавленную стоимость", ...fmtAmount(k.vat), accent: "#1D9E75" },
        { label: "Итоговый налоговый вклад", ...fmtAmount(k.total), accent: "#7F77DD" },
        {
          label: "Доля в бюджете Республики",
          value: k.budget_share_pct != null ? fmt3(k.budget_share_pct) : "—",
          unit: "%",
          accent: "#EF9F27",
        },
        { label: "Лидирующий сектор", value: top, unit: "", accent: "#378ADD" },
      ];
    }
    case "vat": {
      return [
        { label: "Налог на прибыль", ...fmtAmount(k.income_tax), accent: "#378ADD" },
        { label: "Итоговый налоговый вклад", ...fmtAmount(k.total), accent: "#7F77DD" },
        {
          label: "Динамика год к году",
          value: k.yoy_vat_pct != null ? fmtSignedPct(k.yoy_vat_pct) : "—",
          unit: "",
          accent: "#1D9E75",
        },
        { label: "Лидирующий сектор", value: top, unit: "", accent: "#EF9F27" },
      ];
    }
    case "total": {
      return [
        { label: "Налог на прибыль", ...fmtAmount(k.income_tax), accent: "#378ADD" },
        { label: "Налог на добавленную стоимость", ...fmtAmount(k.vat), accent: "#1D9E75" },
        {
          label: "Доля в бюджете Республики",
          value: k.budget_share_pct != null ? fmt3(k.budget_share_pct) : "—",
          unit: "%",
          accent: "#EF9F27",
        },
        { label: "Лидирующий сектор", value: top, unit: "", accent: "#378ADD" },
      ];
    }
    case "budget_share": {
      const top1 = props.topPayers[0];
      const top1Share = top1
        ? Math.round((top1.amount / Math.max(1, k.total)) * 100)
        : 0;
      const top3 = props.topPayers.slice(0, 3);
      const top3Sum = top3.reduce((a, p) => a + Number(p.amount ?? 0), 0);
      const top3Share = Math.round((top3Sum / Math.max(1, k.total)) * 100);
      return [
        { label: "Итоговый налоговый вклад", ...fmtAmount(k.total), accent: "#7F77DD" },
        { label: "Налог на прибыль", ...fmtAmount(k.income_tax), accent: "#378ADD" },
        {
          label: "Концентрация — крупнейший плательщик",
          value: top1Share + "%",
          unit: "",
          accent: "#E24B4A",
        },
        {
          label: "Концентрация — три крупнейших",
          value: top3Share + "%",
          unit: "",
          accent: "#EF9F27",
        },
      ];
    }
  }
  return [];
});

// ─── Top-5 payers ───
const topMaxAbs = computed(() => {
  return Math.max(1, ...props.topPayers.slice(0, 5).map((p) => Math.abs(p.amount)));
});
function payerPct(p: ExecTaxTopPayer): number {
  if (props.kpi.total <= 0) return 0;
  return Math.round((p.amount / props.kpi.total) * 100);
}

// ─── Header count-up ───
const headerDisplay = ref<number>(0);
const headerTarget = computed(() => {
  const raw = meta.value.bigValueMlrd(props.kpi);
  if (raw == null) return 0;
  if (meta.value.isPct) return raw;
  // Для денежных KPI count-up по числу в активной валюте
  return conv.convert(raw, props.year);
});
function startCountUp() {
  const target = headerTarget.value;
  if (!isFinite(target)) { headerDisplay.value = target; return; }
  const reduced = typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (reduced) { headerDisplay.value = target; return; }
  headerDisplay.value = 0;
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
const headerDisplayStr = computed(() => {
  if (meta.value.isPct) return fmt3(headerDisplay.value);
  // Для денежного KPI: display нужно отформатировать с теми же 3 знаками
  // но без юнита (он отображается отдельно через heroFormatted.unit)
  if (conv.currency.value === "UZS") {
    // raw в млрд сум — если >=1000, показываем в трлн (heroFormatted делает это)
    const raw = meta.value.bigValueMlrd(props.kpi) ?? 0;
    if (Math.abs(raw) >= 1000) return fmt3(headerDisplay.value / 1000);
    return fmt3(headerDisplay.value);
  }
  // USD: convert вернул в млн USD, если >=1000 → отображаем в млрд USD
  const usdMln = headerDisplay.value;
  if (Math.abs(usdMln) >= 1000) return fmt3(usdMln / 1000);
  return fmt3(usdMln);
});

// ─── Close + nav ───
function close() { emit("close"); }
function onBackdrop(e: MouseEvent) { if (e.target === e.currentTarget) close(); }
function onKey(e: KeyboardEvent) { if (e.key === "Escape") { e.preventDefault(); close(); } }

// a11y: фокус-трап диалога + возврат фокуса при закрытии
const cardEl = ref<HTMLElement | null>(null);
useFocusTrap(cardEl);

function gotoFinancials() {
  router.push({ name: "financials", query: { year: props.year } });
  close();
}
function gotoCompany(companyId: string) {
  if (!companyId) return;
  router.push({ name: "company-detail", params: { id: companyId } });
  close();
}

let prevOverflow = "";
onMounted(() => {
  prevOverflow = document.body.style.overflow;
  document.body.style.overflow = "hidden";
  window.addEventListener("keydown", onKey);
  startCountUp();
});

// Pack 7.37: re-animate hero number when currency switches (sum → USD/EUR).
// Without this the number stays at the previous currency's value and only the
// unit label changes — looking like the conversion is broken.
watch(() => conv.currency.value, () => {
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
      <div class="txd-bd" @click="onBackdrop" role="dialog" aria-modal="true">
        <div ref="cardEl" tabindex="-1" class="txd-card" :style="{ '--sc': meta.color }">
          <div class="txd-stripe" aria-hidden="true" />
          <div class="txd-shim" aria-hidden="true" />
          <div class="txd-glow" aria-hidden="true" />

          <button class="txd-x" @click="close" aria-label="Закрыть модальное окно">
            <svg viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="13" height="13">
              <path d="M3.5 3.5l7 7M10.5 3.5l-7 7"/>
            </svg>
          </button>

          <!-- Header -->
          <div class="txd-sect txd-row" style="--si:0; padding-top:20px;">
            <div class="txd-h-top">
              <div class="txd-h-l">{{ meta.label }}</div>
              <!-- Pack 7.37: toggle moved below to avoid collision with X close button -->
            </div>
            <div class="txd-h-row-flex">
              <div class="txd-h-v">
                <span class="num">{{ headerDisplayStr }}</span>
                <span class="unit">{{ heroFormatted.unit }} · {{ year }} год</span>
              </div>
              <CurrencyToggle
                v-if="!meta.isPct"
                :year="year"
                :compact="true"
                :show-rate="true"
                class="txd-h-toggle"
              />
            </div>
            <span
              v-if="badgeText"
              class="txd-h-d"
              :class="`txd-h-d--${badgeText.tone}`"
            >
              <svg v-if="badgeText.tone === 'good'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 7l3-3 3 3"/></svg>
              <svg v-else-if="badgeText.tone === 'bad'" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" width="10" height="10"><path d="M3 5l3 3 3-3"/></svg>
              {{ badgeText.text }}
            </span>
            <div class="txd-h-tag-list">
              <span>{{ cosCount }} компаний с налоговыми данными</span>
              <span class="txd-h-sep">·</span>
              <span>{{ sectorAgg.length }} секторов</span>
              <span class="txd-h-sep">·</span>
              <span>{{ standardLabel }}</span>
            </div>
          </div>

          <!-- 4 mini-KPI strip -->
          <div class="txd-sect txd-row" style="--si:1;">
            <div class="txd-mini-grid">
              <div
                v-for="(m, i) in miniKpis"
                :key="m.label"
                class="txd-mini"
                :style="{ '--kc': m.accent, '--ki': i }"
              >
                <div class="txd-mk-l">{{ m.label }}</div>
                <div class="txd-mk-v">
                  {{ m.value }}<span v-if="m.unit" class="txd-mk-u">{{ m.unit }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- Sector breakdown -->
          <div class="txd-sect txd-row" style="--si:2;">
            <div class="txd-l-sec">Распределение по секторам</div>
            <div v-if="sectorAgg.length" class="txd-bar">
              <div
                v-for="(s, i) in sectorAgg"
                :key="s.id"
                class="txd-bar-seg"
                :style="{
                  background: s.color,
                  flex: `0 0 ${s.pct}%`,
                  animationDelay: (0.55 + i * 0.13) + 's',
                }"
                :title="`${s.label} · ${conv.format(s.totalMlrd, year).full}`"
              />
            </div>
            <div v-if="sectorAgg.length" class="txd-leg">
              <span v-for="s in sectorAgg" :key="s.id">
                <i class="txd-dot" :style="{ background: s.color }"/>
                {{ s.label }} · <strong>{{ conv.format(s.totalMlrd, year).value }}</strong>
                <span class="txd-leg-unit">{{ conv.format(s.totalMlrd, year).unit }}</span>
                <span class="txd-leg-pct">{{ s.pct }} процентов</span>
              </span>
            </div>
            <div v-else class="txd-empty">Нет данных по секторам</div>
          </div>

          <!-- Top-5 payers -->
          <div class="txd-sect txd-row" style="--si:3;">
            <div class="txd-l-sec">
              <span>Пять крупнейших плательщиков · {{ year }} год</span>
              <span v-if="cosCount > 5" class="txd-l-side">
                ещё {{ cosCount - 5 }} компаний скрыто
              </span>
            </div>
            <div v-if="topPayers.length" class="txd-toplist">
              <div
                v-for="(p, i) in topPayers.slice(0, 5)"
                :key="p.company_id"
                class="txd-top-row"
                @click="gotoCompany(p.company_id)"
                :title="'Открыть карточку компании «' + p.name + '»'"
              >
                <span class="txd-top-rank">{{ i + 1 }}</span>
                <span class="txd-top-name">
                  <i class="txd-top-tick" :style="{ background: sectorColor[p.sector] || '#888780' }"/>
                  {{ p.name }}
                </span>
                <span class="txd-top-bar">
                  <span
                    class="txd-top-fill"
                    :style="{
                      background: sectorColor[p.sector] || '#888780',
                      width: ((Math.abs(p.amount) / topMaxAbs) * 100) + '%',
                      animationDelay: (1.0 + i * 0.07) + 's',
                    }"
                  />
                </span>
                <span class="txd-top-val">
                  <span class="amt">{{ conv.format(p.amount, year).value }}</span>
                  <span class="unit">{{ conv.format(p.amount, year).unit }}</span>
                  <span class="pct">{{ payerPct(p) }} процентов</span>
                </span>
              </div>
            </div>
            <div v-else class="txd-empty">Нет данных по плательщикам</div>
          </div>

          <!-- Footer -->
          <div class="txd-ftr txd-row" style="--si:4;">
            <button class="txd-btn txd-btn-g" @click="close">Закрыть</button>
            <button class="txd-btn txd-btn-p" @click="gotoFinancials">
              Открыть финансовые данные
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
.txd-bd { position: fixed; inset: 0; background: rgba(15, 18, 40, 0.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); z-index: 9000; display: flex; align-items: center; justify-content: center; padding: 24px 16px; overflow-y: auto; }
.txd-card { position: relative; background: var(--bg1, #fff); border: 1px solid var(--card-border, transparent); border-radius: 14px; box-shadow: 0 24px 64px rgba(15, 23, 60, 0.22), 0 8px 24px rgba(15, 23, 60, 0.10); width: 100%; max-width: 740px; overflow: hidden; animation: txdIn .55s var(--ease-standard) .08s both; }
.txd-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--sc); transform-origin: left center; animation: txdStripe .75s var(--ease-standard) .2s both; z-index: 3; }
.txd-shim { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent); transform: translateX(-120%); animation: txdShim 6s ease-in-out 1.5s infinite; pointer-events: none; z-index: 4; }
.txd-glow { position: absolute; inset: 0; background: radial-gradient(circle at 92% -6%, var(--sc), transparent 42%); opacity: 0.07; pointer-events: none; z-index: 1; }
.txd-x { position: absolute; top: 14px; right: 14px; width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; cursor: pointer; color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, 0.06); background: var(--bg1, #fff); z-index: 6; transition: all .14s; }
.txd-x:hover { background: var(--bg2, #FAFAFC); color: var(--t1, #1E2A4A); }

.txd-row { animation: txdUp .42s ease both; animation-delay: calc(.32s + var(--si, 0) * .06s); opacity: 0; position: relative; z-index: 2; }
.txd-sect { padding: 14px 22px; }
.txd-sect + .txd-sect { padding-top: 0; }

.txd-h-top { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; }

/* Pack 7.37: hero number row + toggle on the right (below the header row,
   well clear of the X close button at top-right of card) */
.txd-h-row-flex {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.txd-h-toggle { flex-shrink: 0; }
@media (max-width: 640px) {
  .txd-h-row-flex { align-items: flex-start; flex-direction: column; gap: 10px; }
}
.txd-h-l { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.txd-h-v { font-size: 44px; font-weight: 500; letter-spacing: -.035em; line-height: 1; color: var(--t1, #1E2A4A); font-feature-settings: "tnum"; margin-top: 6px; display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.txd-h-v .unit { font-size: 13px; color: var(--t3, var(--t-muted)); font-weight: 500; letter-spacing: 0; }
.txd-h-d { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; padding: 3px 9px; border-radius: 999px; margin-top: 8px; }
.txd-h-d--good { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.txd-h-d--bad { background: rgba(226, 75, 74, .10); color: var(--sev-critical); }
.txd-h-d--neutral { background: rgba(127, 119, 221, .08); color: var(--p-deep); }
.txd-h-tag-list { margin-top: 10px; font-size: 11px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.txd-h-sep { margin: 0 6px; color: rgba(15, 23, 60, 0.18); }

.txd-mini-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 7px; }
.txd-mini { position: relative; background: var(--bg2, #FAFAFC); border-radius: 9px; padding: 9px 10px 8px; overflow: hidden; }
.txd-mini::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--kc); transform-origin: left; transform: scaleX(0); animation: txdKpiTop .65s var(--ease-standard) calc(.78s + var(--ki) * .09s) forwards; }
.txd-mk-l { font-size: 8.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .05em; line-height: 1.25; min-height: 22px; }
.txd-mk-v { font-size: 15px; font-weight: 400; letter-spacing: -.02em; color: var(--t1, #1E2A4A); line-height: 1.15; margin-top: 4px; font-feature-settings: "tnum"; }
.txd-mk-u { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; margin-left: 4px; letter-spacing: 0; }

.txd-l-sec { font-size: 10px; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.txd-l-side { font-size: 9.5px; color: #6B6A66; text-transform: none; letter-spacing: .02em; font-weight: 400; }

.txd-bar { height: 11px; background: #F1EFE8; border-radius: 5px; overflow: hidden; display: flex; }
.txd-bar-seg { height: 100%; transform: scaleX(0); transform-origin: left; animation: txdBar 1.1s var(--ease-standard) forwards; }
.txd-leg { display: flex; gap: 14px; margin-top: 9px; font-size: 11px; color: var(--t3, #5F5E5A); font-weight: 500; flex-wrap: wrap; }
.txd-leg strong { color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; }
.txd-leg-unit { color: var(--t3, var(--t-muted)); margin-left: 3px; }
.txd-leg-pct { color: var(--t3, var(--t-muted)); margin-left: 6px; font-feature-settings: "tnum"; }
.txd-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }

.txd-toplist { display: flex; flex-direction: column; gap: 6px; }
.txd-top-row { display: grid; grid-template-columns: 26px 200px 1fr 130px; gap: 10px; align-items: center; font-size: 11.5px; cursor: pointer; padding: 4px 6px; border-radius: 5px; transition: background .12s; }
.txd-top-row:hover { background: rgba(127, 119, 221, .04); }
.txd-top-rank { color: #6B6A66; font-weight: 500; font-feature-settings: "tnum"; font-size: 11px; text-align: center; background: rgba(0, 0, 0, 0.03); border-radius: 50%; width: 22px; height: 22px; line-height: 22px; }
.txd-top-name { color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 7px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.txd-top-tick { width: 3px; height: 12px; opacity: .85; flex-shrink: 0; }
.txd-top-bar { height: 6px; background: #F1EFE8; border-radius: 3px; overflow: hidden; }
.txd-top-fill { display: block; height: 100%; transform: scaleX(0); transform-origin: left; animation: txdBar 1s var(--ease-standard) forwards; }
.txd-top-val { text-align: right; color: var(--t1, #1E2A4A); font-weight: 500; font-feature-settings: "tnum"; display: flex; flex-direction: column; gap: 1px; line-height: 1.1; }
.txd-top-val .amt { font-size: 11.5px; }
.txd-top-val .unit { font-size: 9.5px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.txd-top-val .pct { font-size: 9.5px; color: var(--p-deep); font-weight: 500; }

.txd-empty { padding: 16px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11.5px; font-style: italic; }

.txd-ftr { padding: 13px 22px 14px; display: flex; justify-content: flex-end; gap: 9px; border-top: 1px solid rgba(0, 0, 0, 0.05); background: var(--bg2, #FAFAFC); margin-top: 4px; }
.txd-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 500; padding: 9px 14px; border-radius: 8px; cursor: pointer; transition: all .14s; border: 1px solid transparent; font-family: inherit; }
.txd-btn-g { background: var(--bg1, #fff); color: var(--t3, #5F5E5A); border-color: rgba(0, 0, 0, 0.10); }
.txd-btn-g:hover { background: #F5F4F9; color: var(--t1, #1E2A4A); }
.txd-btn-p { background: var(--sc); color: #fff; }
.txd-btn-p:hover { filter: brightness(.93); }

.txd-fade-enter-active, .txd-fade-leave-active { transition: opacity .28s ease; }
.txd-fade-enter-from, .txd-fade-leave-to { opacity: 0; }
.txd-fade-leave-active .txd-card { animation: txdOut .24s ease forwards; }

@keyframes txdIn { 0% { opacity: 0; transform: translateY(22px) scale(.96); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
@keyframes txdOut { to { opacity: 0; transform: translateY(8px) scale(.98); } }
@keyframes txdStripe { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes txdShim { 0% { transform: translateX(-120%); } 60% { transform: translateX(220%); } 100% { transform: translateX(220%); } }
@keyframes txdUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes txdBar { to { transform: scaleX(1); } }
@keyframes txdKpiTop { from { transform: scaleX(0); } to { transform: scaleX(1); } }

@media (max-width: 600px) {
  .txd-mini-grid { grid-template-columns: repeat(2, 1fr); }
  .txd-top-row { grid-template-columns: 22px 120px 1fr 90px; font-size: 11px; }
  .txd-h-v { font-size: 32px; }
}
</style>
