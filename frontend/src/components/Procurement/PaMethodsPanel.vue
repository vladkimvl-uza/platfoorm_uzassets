<script setup lang="ts">
/**
 * PaMethodsPanel — премиум-панель «Способы закупки + Электронные площадки + Без торга».
 *
 * Главный инсайт: прямые каталоги (e-shop / e-store, неконкурентные методы)
 * дают ~0% экономии, тогда как конкурентные методы — ощутимую ставку saved_rate_pct.
 * Панель визуально подсвечивает «спенд без торга» и зоны нулевой экономии.
 *
 * Источник данных:
 *   data.methods   — MethodAgg[]  (способы закупки)
 *   data.platforms — PlatformAgg[](электронные площадки)
 *   data.kpis      — ProcurementKpis (no_tender_pct / no_tender_spend)
 */
import { computed, onMounted, ref } from "vue";
import {
  paFmtMoneyShort,
  type ProcurementAggregate,
  type MethodAgg,
  type PlatformAgg,
} from "@/api/procurement_analysis";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

const props = defineProps<{ data: ProcurementAggregate }>();

// ── Анимация роста баров: ширина 0 → реальная при маунте ──
const mounted = ref(false);
onMounted(() => {
  // двойной rAF — гарантируем, что начальное width:0 успело отрендериться
  requestAnimationFrame(() => requestAnimationFrame(() => { mounted.value = true; }));
});

// Тип бейджа метода/площадки:
//   'catalog' — неконкурентный метод (каталог e-shop, прямая закупка) — торга нет;
//   'no-effect' — конкурентный метод, но экономия ≈0 (имитация торга);
//   'saving' — конкурентный метод с достигнутой экономией.
type Badge = "catalog" | "no-effect" | "saving";
function badgeKind(saved: number, competitive: boolean): Badge {
  if (!competitive) return "catalog";
  return Math.abs(saved) < 0.1 ? "no-effect" : "saving";
}
function isZeroRow(saved: number, competitive: boolean): boolean {
  return badgeKind(saved, competitive) !== "saving";
}

// ── Способы закупки: сортировка по спенду desc ──
const methods = computed<MethodAgg[]>(() =>
  [...(props.data?.methods || [])].sort(
    (a, b) => (Number(b.spend) || 0) - (Number(a.spend) || 0),
  ),
);

// ── Электронные площадки: сортировка по спенду desc ──
const platforms = computed<PlatformAgg[]>(() =>
  [...(props.data?.platforms || [])].sort(
    (a, b) => (Number(b.spend) || 0) - (Number(a.spend) || 0),
  ),
);

const kpis = computed(() => props.data?.kpis);

// Доля «без торга» — для callout-кольца.
const noTenderPct = computed(() => {
  const v = Number(kpis.value?.no_tender_pct);
  return isFinite(v) ? Math.max(0, Math.min(100, v)) : 0;
});
const noTenderSpend = computed(() => Number(kpis.value?.no_tender_spend) || 0);

// Второй сигнал: конкурентные процедуры с нулевой экономией (имитация торга).
const compNoSavingPct = computed(() => {
  const v = Number(kpis.value?.competitive_no_saving_pct);
  return isFinite(v) ? Math.max(0, Math.min(100, v)) : 0;
});
const compNoSavingSpend = computed(() => Number(kpis.value?.competitive_no_saving_spend) || 0);

// Ширина бара (clamp 0..100). Пока !mounted → 0 (для анимации роста).
function barW(sharePct: number | null | undefined): string {
  if (!mounted.value) return "0%";
  const v = Number(sharePct);
  if (!isFinite(v) || v <= 0) return "0%";
  return Math.min(100, v).toFixed(2) + "%";
}

function fmtPct(v: number | null | undefined): string {
  const n = Number(v);
  if (!isFinite(n)) return "—";
  return n.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function fmtInt(v: number | null | undefined): string {
  const n = Number(v);
  if (!isFinite(n)) return "0";
  return Math.round(n).toLocaleString("ru-RU");
}
</script>

<template>
  <div class="pa-mp">
    <!-- ───────────── CALLOUT «БЕЗ ТОРГА» ───────────── -->
    <section class="pa-mp-callout" :style="{ '--i': 0 }">
      <div class="pa-mp-callout-ring" aria-hidden="true">
        <svg viewBox="0 0 64 64" class="pa-mp-ring-svg">
          <circle class="pa-mp-ring-bg" cx="32" cy="32" r="27" />
          <circle
            class="pa-mp-ring-fg"
            cx="32"
            cy="32"
            r="27"
            :style="{
              strokeDasharray: 2 * Math.PI * 27,
              strokeDashoffset: mounted
                ? 2 * Math.PI * 27 * (1 - noTenderPct / 100)
                : 2 * Math.PI * 27,
            }"
          />
        </svg>
        <div class="pa-mp-ring-num">{{ fmtPct(noTenderPct) }}<span>%</span></div>
      </div>

      <div class="pa-mp-callout-body">
        <div class="pa-mp-eyebrow pa-mp-eyebrow--amber">{{ t("Без конкурентной процедуры") }}</div>
        <div class="pa-mp-callout-amt">{{ paFmtMoneyShort(noTenderSpend) }}<span class="pa-mp-cur"> {{ t("сум") }}</span></div>
        <div class="pa-mp-callout-sub">
          {{ t("{pct}% спенда — прямые каталоги/неконкурентные методы (e-shop), где торга нет по определению.", { pct: fmtPct(noTenderPct) }) }}
        </div>
        <div class="pa-mp-callout-flag">
          <span class="pa-mp-flag-dot" />
          {{ t("ещё") }} <b>{{ fmtPct(compNoSavingPct) }}%</b> ({{ paFmtMoneyShort(compNoSavingSpend) }} {{ t("сум") }}) —
          {{ t("конкурентные процедуры с нулевой экономией (возможная имитация торга)") }}
        </div>
      </div>
    </section>

    <!-- ───────────── СЕТКА ИЗ ДВУХ КАРТОЧЕК ───────────── -->
    <div class="pa-mp-grid">
      <!-- ── Карточка 1: Способы закупки ── -->
      <section class="pa-mp-card pa-mp-card--methods" :style="{ '--i': 1 }">
        <header class="pa-mp-card-head">
          <div class="pa-mp-eyebrow">{{ t("Способы закупки") }}</div>
          <div class="pa-mp-card-hint">{{ t("экономия по типу процедуры") }}</div>
        </header>

        <div v-if="!methods.length" class="pa-mp-empty">
          <div class="pa-mp-empty-title">{{ t("Нет данных о способах закупки") }}</div>
          <div class="pa-mp-empty-sub">{{ t("За выбранный период записи отсутствуют") }}</div>
        </div>

        <ul v-else class="pa-mp-rows">
          <li
            v-for="(m, i) in methods"
            :key="m.method"
            class="pa-mp-row pa-mp-row--method"
            :class="{ 'is-zero': isZeroRow(m.saved_rate_pct, m.is_competitive) }"
            :style="{ '--i': i + 2 }"
          >
            <div class="pa-mp-row-top">
              <span class="pa-mp-label" :title="t(m.label)">{{ t(m.label) }}</span>

              <!-- Бейдж ставки экономии — главный инсайт -->
              <span
                v-if="badgeKind(m.saved_rate_pct, m.is_competitive) === 'catalog'"
                class="pa-mp-badge pa-mp-badge--red"
                :title="t('Неконкурентный метод (каталог/прямая закупка) — торга нет по определению')"
              >{{ t("каталог · без торга") }}</span>
              <span
                v-else-if="badgeKind(m.saved_rate_pct, m.is_competitive) === 'no-effect'"
                class="pa-mp-badge pa-mp-badge--amber"
                :title="t('Конкурентная процедура, но экономия ≈0 — возможна имитация торга')"
              >{{ t("торг без эффекта") }}</span>
              <span
                v-else
                class="pa-mp-badge pa-mp-badge--green"
                :title="t('Конкурентный метод — достигнута экономия')"
              >−{{ fmtPct(m.saved_rate_pct) }}% {{ t("экономия") }}</span>
            </div>

            <div class="pa-mp-bar-track">
              <div
                class="pa-mp-bar"
                :style="{ width: barW(m.spend_share_pct) }"
              />
              <span class="pa-mp-bar-amt">{{ paFmtMoneyShort(m.spend) }}</span>
            </div>

            <div class="pa-mp-row-meta">
              <span class="pa-mp-share">{{ t("{p}% спенда", { p: fmtPct(m.spend_share_pct) }) }}</span>
              <span class="pa-mp-dot">·</span>
              <span class="pa-mp-lots">{{ fmtInt(m.lot_count) }} {{ t("лот.") }}</span>
            </div>
          </li>
        </ul>
      </section>

      <!-- ── Карточка 2: Электронные площадки ── -->
      <section class="pa-mp-card pa-mp-card--platforms" :style="{ '--i': 1 }">
        <header class="pa-mp-card-head">
          <div class="pa-mp-eyebrow">{{ t("Электронные площадки") }}</div>
          <div class="pa-mp-card-hint">{{ t("экономия по торговой площадке") }}</div>
        </header>

        <div v-if="!platforms.length" class="pa-mp-empty">
          <div class="pa-mp-empty-title">{{ t("Нет данных о площадках") }}</div>
          <div class="pa-mp-empty-sub">{{ t("За выбранный период записи отсутствуют") }}</div>
        </div>

        <ul v-else class="pa-mp-rows">
          <li
            v-for="(p, i) in platforms"
            :key="p.platform"
            class="pa-mp-row pa-mp-row--platform"
            :class="{ 'is-zero': isZeroRow(p.saved_rate_pct, true) }"
            :style="{ '--i': i + 2 }"
          >
            <div class="pa-mp-row-top">
              <span class="pa-mp-label" :title="p.platform">{{ p.platform || "—" }}</span>
              <span
                v-if="isZeroRow(p.saved_rate_pct, true)"
                class="pa-mp-badge pa-mp-badge--red"
                :title="t('Площадка прямого каталога — экономия отсутствует')"
              >0% {{ t("экономия") }}</span>
              <span
                v-else
                class="pa-mp-badge pa-mp-badge--green"
                :title="t('Достигнута экономия на торгах')"
              >−{{ fmtPct(p.saved_rate_pct) }}%</span>
            </div>

            <div class="pa-mp-bar-track">
              <div
                class="pa-mp-bar"
                :style="{ width: barW(p.spend_share_pct) }"
              />
              <span class="pa-mp-bar-amt">{{ paFmtMoneyShort(p.spend) }}</span>
            </div>

            <div class="pa-mp-row-meta">
              <span class="pa-mp-share">{{ t("{p}% спенда", { p: fmtPct(p.spend_share_pct) }) }}</span>
              <span class="pa-mp-dot">·</span>
              <span class="pa-mp-lots">{{ fmtInt(p.lot_count) }} {{ t("лот.") }}</span>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
/* ───────────── премиум-анимации ───────────── */
@keyframes paIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}

.pa-mp {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* eyebrow */
.pa-mp-eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .5);
}
.pa-mp-eyebrow--amber { color: #854F0B; }

/* ───────────── CALLOUT «БЕЗ ТОРГА» ───────────── */
.pa-mp-callout {
  position: relative;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 16px 20px;
  border-radius: 14px;
  border: 1px solid rgba(239, 179, 115, .35);
  background:
    radial-gradient(120% 140% at 0% 0%, rgba(239, 179, 115, .14), rgba(239, 179, 115, 0) 60%),
    linear-gradient(180deg, #FFFDFA, #FFFFFF);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  overflow: hidden;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
}
.pa-mp-callout::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  background: linear-gradient(90deg, #EFB373, #E2807F);
  border-top-left-radius: 14px;
  border-top-right-radius: 14px;
}

/* кольцо-прогресс */
.pa-mp-callout-ring {
  position: relative;
  width: 84px;
  height: 84px;
  flex: 0 0 84px;
}
.pa-mp-ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.pa-mp-ring-bg {
  fill: none;
  stroke: rgba(239, 179, 115, .22);
  stroke-width: 6;
}
.pa-mp-ring-fg {
  fill: none;
  stroke: #E2807F;
  stroke-width: 6;
  stroke-linecap: round;
  transition: stroke-dashoffset .9s cubic-bezier(.22, 1, .36, 1);
}
.pa-mp-ring-num {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: #933632;
}
.pa-mp-ring-num span {
  font-size: 12px;
  margin-left: 1px;
  opacity: .7;
}

.pa-mp-callout-body { min-width: 0; }
.pa-mp-callout-amt {
  margin-top: 4px;
  font-size: 26px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: #1E2A4A;
  line-height: 1.1;
}
.pa-mp-cur {
  font-size: 14px;
  color: rgba(15, 23, 60, .45);
}
.pa-mp-callout-sub {
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.45;
  color: rgba(15, 23, 60, .62);
  max-width: 560px;
}

/* ───────────── СЕТКА КАРТОЧЕК ───────────── */
.pa-mp-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
@media (max-width: 900px) {
  .pa-mp-grid { grid-template-columns: 1fr; }
}

.pa-mp-card {
  position: relative;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  padding: 16px;
  overflow: hidden;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
}
.pa-mp-card::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 3px;
  border-top-left-radius: 14px;
  border-top-right-radius: 14px;
}
.pa-mp-card--methods::before   { background: linear-gradient(90deg, #9D97E6, #7F77DD); }
.pa-mp-card--platforms::before { background: linear-gradient(90deg, #93D3B0, #5DC093); }

.pa-mp-card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.pa-mp-card-hint {
  font-size: 11px;
  color: rgba(15, 23, 60, .38);
}

/* ───────────── СТРОКИ ───────────── */
.pa-mp-rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.pa-mp-row {
  position: relative;
  padding: 10px 11px;
  border-radius: 10px;
  background: #FAFAFC;
  border: 1px solid transparent;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
  transition: background .18s, transform .18s, box-shadow .18s, border-color .18s;
}
.pa-mp-row--method { cursor: pointer; }
.pa-mp-row:hover {
  background: rgba(127, 119, 221, .05);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 60, .07);
}
.pa-mp-row--method:focus-visible {
  outline: none;
  border-color: rgba(127, 119, 221, .5);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, .16);
}
/* строки с нулевой экономией — мягкий красный оттенок */
.pa-mp-row.is-zero { background: rgba(226, 128, 127, .07); }
.pa-mp-row.is-zero:hover { background: rgba(226, 128, 127, .12); }

.pa-mp-row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
}
.pa-mp-label {
  font-size: 13px;
  font-weight: 600;
  color: #1E2A4A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* бейджи экономии */
.pa-mp-badge {
  flex: 0 0 auto;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: .01em;
  padding: 3px 8px;
  border-radius: 999px;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.pa-mp-badge--green {
  background: rgba(93, 192, 147, .18);
  color: #0F6E56;
  box-shadow: inset 0 0 0 1px rgba(93, 192, 147, .35);
}
.pa-mp-badge--red {
  background: rgba(226, 128, 127, .18);
  color: #933632;
  box-shadow: inset 0 0 0 1px rgba(226, 128, 127, .4);
}
.pa-mp-badge--amber {
  background: rgba(239, 179, 115, .2);
  color: #854F0B;
  box-shadow: inset 0 0 0 1px rgba(239, 179, 115, .45);
}

/* второй сигнал в callout — конкурентные процедуры без экономии */
.pa-mp-callout-flag {
  margin-top: 8px;
  display: flex;
  align-items: baseline;
  gap: 7px;
  font-size: 11.5px;
  line-height: 1.4;
  color: rgba(15, 23, 60, .6);
  max-width: 560px;
}
.pa-mp-callout-flag b { color: #854F0B; font-weight: 600; }
.pa-mp-flag-dot {
  flex: 0 0 auto;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #EFB373;
  transform: translateY(1px);
}

/* бар спенда */
.pa-mp-bar-track {
  position: relative;
  height: 18px;
  border-radius: 3px;
  background: rgba(15, 23, 60, .05);
  overflow: hidden;
  display: flex;
  align-items: center;
}
.pa-mp-bar {
  position: absolute;
  inset: 0 auto 0 0;
  height: 100%;
  width: 0;
  border-radius: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
  transition: width .8s cubic-bezier(.22, 1, .36, 1);
}
/* площадки — мятный бар */
.pa-mp-card--platforms .pa-mp-bar {
  background: linear-gradient(90deg, #93D3B0, #5DC093);
}
/* строки с нулевой экономией — приглушённо-красный бар */
.pa-mp-row.is-zero .pa-mp-bar {
  background: linear-gradient(90deg, #ECB4B3, #E2807F);
}
.pa-mp-bar-amt {
  position: relative;
  z-index: 1;
  padding: 0 8px;
  font-size: 11.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: #1E2A4A;
}

.pa-mp-row-meta {
  margin-top: 7px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: rgba(15, 23, 60, .5);
  font-variant-numeric: tabular-nums;
}
.pa-mp-dot { color: rgba(15, 23, 60, .25); }
.pa-mp-share { font-weight: 600; color: rgba(15, 23, 60, .62); }

/* ───────────── ПУСТОЕ СОСТОЯНИЕ ───────────── */
.pa-mp-empty {
  padding: 32px 16px;
  text-align: center;
}
.pa-mp-empty-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(15, 23, 60, .55);
}
.pa-mp-empty-sub {
  margin-top: 4px;
  font-size: 11.5px;
  color: rgba(15, 23, 60, .38);
}

@media (prefers-reduced-motion: reduce) {
  .pa-mp-callout,
  .pa-mp-card,
  .pa-mp-row { animation: none; }
  .pa-mp-bar,
  .pa-mp-ring-fg { transition: none; }
}
</style>
