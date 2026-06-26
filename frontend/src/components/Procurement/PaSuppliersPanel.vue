<script setup lang="ts">
/**
 * PaSuppliersPanel — премиум-панель ПОСТАВЩИКОВ для страницы анализа закупок.
 *
 * Четыре смысловые секции в одном контейнере-сетке:
 *   1. Сводка сверху (supplier_count / disclosed_supplier_pct / доля сквозных).
 *   2. Сегмент-переключатель «Топ по сумме · Сквозные · Дорогие» + список строк.
 *      Каждая строка: название, ИНН, бар спенда (spend_share_pct), сумма,
 *      лоты, клиенты-компании, ставка экономии, премия (для «Дорогих»).
 *      Клик → emit('drill-supplier').
 *   3. Таблица концентрации (HHI / top1 / top3) по компаниям.
 *      Клик → emit('select-company').
 *
 * Дизайн: пастельная палитра, top-accent, пурпурные бары спенда,
 * stagger fade-up, растущие бары, hover-лифт.
 */
import { ref, computed } from "vue";
import {
  paFmtMoneyShort,
  type ProcurementAggregate,
  type SupplierAgg,
  type SupplierConcentration,
} from "@/api/procurement_analysis";

const props = defineProps<{ data: ProcurementAggregate }>();

const emit = defineEmits<{
  (e: "drill-supplier", s: SupplierAgg): void;
  (e: "select-company", companyId: string): void;
}>();

// ── Сегмент-переключатель ──
type Seg = "top" | "cross" | "expensive";
const seg = ref<Seg>("top");

const segs: { key: Seg; label: string; hint: string }[] = [
  { key: "top", label: "Топ по сумме", hint: "Крупнейшие поставщики по объёму спенда" },
  { key: "cross", label: "Сквозные", hint: "Работают с двумя и более компаниями (≥2)" },
  { key: "expensive", label: "Дорогие", hint: "С премией к медиане рынка" },
];

const segCount = (k: Seg): number => {
  if (k === "top") return props.data.suppliers_top?.length || 0;
  if (k === "cross") return props.data.suppliers_cross?.length || 0;
  return props.data.suppliers_expensive?.length || 0;
};

const activeList = computed<SupplierAgg[]>(() => {
  if (seg.value === "top") return props.data.suppliers_top || [];
  if (seg.value === "cross") return props.data.suppliers_cross || [];
  return props.data.suppliers_expensive || [];
});

// Максимум для нормировки ширины бара внутри текущего списка (визуальный
// контраст: лидер занимает всю дорожку, остальные — пропорционально доле).
const maxShare = computed<number>(() => {
  let m = 0;
  for (const s of activeList.value) {
    const v = Number(s.spend_share_pct) || 0;
    if (v > m) m = v;
  }
  return m > 0 ? m : 1;
});

function barWidth(s: SupplierAgg): string {
  const share = Number(s.spend_share_pct) || 0;
  const pct = Math.max(4, Math.min(100, (share / maxShare.value) * 100));
  return pct.toFixed(1) + "%";
}

// ── Сводка ──
const kpiSupplierCount = computed<number>(() => Number(props.data.kpis?.supplier_count) || 0);
const kpiDisclosedPct = computed<number>(() => Number(props.data.kpis?.disclosed_supplier_pct) || 0);
// Доля совокупного спенда, идущая сквозным поставщикам (работают с ≥2 SOE) —
// кандидаты на централизованные рамочные контракты.
const crossSharePct = computed<number>(() => {
  return (props.data.suppliers_cross || []).reduce(
    (s, x) => s + (Number(x.spend_share_pct) || 0), 0,
  );
});

// ── Концентрация: сортировка по top1_pct desc ──
const concentration = computed<SupplierConcentration[]>(() => {
  return [...(props.data.supplier_concentration || [])].sort(
    (a, b) => (Number(b.top1_pct) || 0) - (Number(a.top1_pct) || 0),
  );
});

// ── Форматтеры ──
const fmtN = (v: number | null | undefined): string =>
  v == null || isNaN(Number(v)) ? "—" : Number(v).toLocaleString("ru-RU");

const fmtPct1 = (v: number | null | undefined): string =>
  v == null || isNaN(Number(v)) ? "—" : Number(v).toFixed(1) + "%";

function hhiBand(hhi: number): { cls: string; label: string } {
  if (hhi > 2500) return { cls: "hhi-high", label: "высокая" };
  if (hhi >= 1500) return { cls: "hhi-mid", label: "умеренная" };
  return { cls: "hhi-low", label: "низкая" };
}

// Чипы кодов компаний — до 12 видимых, остаток «+N».
const CHIP_LIMIT = 12;
function visibleCodes(s: SupplierAgg): string[] {
  return (s.company_codes || []).slice(0, CHIP_LIMIT);
}
function hiddenCount(s: SupplierAgg): number {
  return Math.max(0, (s.company_codes?.length || 0) - CHIP_LIMIT);
}

function premiumClass(p: number): string {
  if (p >= 20) return "prem-high";
  if (p >= 8) return "prem-mid";
  return "prem-low";
}
</script>

<template>
  <div class="psp">
    <!-- ═══ Секция 1 · Сводка сверху ═══ -->
    <header class="psp-summary card" :style="{ '--i': 0 }">
      <div class="psp-eyebrow">Поставщики · обзор</div>
      <div class="psp-summary-grid">
        <div class="psp-sum-cell">
          <div class="psp-sum-val">{{ fmtN(kpiSupplierCount) }}</div>
          <div class="psp-sum-lbl">всего поставщиков</div>
        </div>
        <div class="psp-sum-cell">
          <div class="psp-sum-val">{{ fmtPct1(kpiDisclosedPct) }}</div>
          <div class="psp-sum-lbl">раскрытого спенда</div>
        </div>
        <div class="psp-sum-cell">
          <div class="psp-sum-val">{{ fmtPct1(crossSharePct) }}</div>
          <div class="psp-sum-lbl">спенда у сквозных</div>
        </div>
      </div>
    </header>

    <!-- ═══ Секция 2 · Списки поставщиков ═══ -->
    <section class="psp-suppliers card" :style="{ '--i': 1 }">
      <div class="psp-head-row">
        <div class="psp-eyebrow">Поставщики</div>
        <div class="psp-seg" role="tablist">
          <button
            v-for="s in segs"
            :key="s.key"
            type="button"
            class="psp-seg-btn"
            :class="{ active: seg === s.key }"
            role="tab"
            :aria-selected="seg === s.key"
            :title="s.hint"
            @click="seg = s.key"
          >
            {{ s.label }}
            <span class="psp-seg-cnt">{{ segCount(s.key) }}</span>
          </button>
        </div>
      </div>

      <div v-if="!activeList.length" class="psp-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 9h18M8 4v16" />
        </svg>
        <span>Нет данных по поставщикам в этом сегменте</span>
      </div>

      <ul v-else class="psp-list">
        <li
          v-for="(s, i) in activeList"
          :key="(s.supplier_inn || s.supplier_name) + ':' + i"
          class="psp-row"
          :style="{ '--i': i }"
          :title="'Открыть детализацию: ' + s.supplier_name"
          @click="emit('drill-supplier', s)"
        >
          <!-- Левая колонка: имя + ИНН + бар спенда -->
          <div class="psp-main">
            <div class="psp-name-line">
              <span class="psp-name" :title="s.supplier_name">{{ s.supplier_name }}</span>
              <span v-if="s.is_cross" class="psp-cross-badge" title="Сквозной поставщик (≥2 компаний)">
                сквозной
              </span>
            </div>
            <div class="psp-inn" v-if="s.supplier_inn">ИНН {{ s.supplier_inn }}</div>
            <div class="psp-inn psp-inn-muted" v-else>ИНН не раскрыт</div>

            <div class="psp-bar-track">
              <div class="psp-bar-fill" :style="{ width: barWidth(s) }" />
              <span class="psp-bar-share">{{ fmtPct1(s.spend_share_pct) }}</span>
            </div>

            <!-- Чипы компаний — только для «Сквозных» -->
            <div v-if="seg === 'cross' && s.company_codes && s.company_codes.length" class="psp-chips">
              <span v-for="c in visibleCodes(s)" :key="c" class="psp-chip">{{ c }}</span>
              <span v-if="hiddenCount(s)" class="psp-chip psp-chip-more">+{{ hiddenCount(s) }}</span>
            </div>
          </div>

          <!-- Правая колонка: метрики -->
          <div class="psp-metrics">
            <div class="psp-spend">{{ paFmtMoneyShort(s.spend) }}</div>
            <div class="psp-sub">
              <span class="psp-sub-it">{{ fmtN(s.lot_count) }} лот.</span>
              <span class="psp-dot">·</span>
              <span class="psp-sub-it">
                <span class="psp-co-badge" :class="{ hot: s.is_cross }">{{ fmtN(s.company_count) }}</span>
                комп.
              </span>
            </div>
            <div class="psp-sub psp-sub-2">
              <span class="psp-saved" :class="{ pos: (Number(s.saved_rate_pct) || 0) > 0 }">
                экономия {{ fmtPct1(s.saved_rate_pct) }}
              </span>
            </div>
            <!-- Премия — только для «Дорогих» -->
            <div v-if="seg === 'expensive'" class="psp-prem-line">
              <span class="psp-prem-badge" :class="premiumClass(Number(s.premium_pct) || 0)">
                +{{ fmtPct1(s.premium_pct) }} к рынку
              </span>
              <span class="psp-excess">+{{ paFmtMoneyShort(s.excess_uzs) }}</span>
            </div>
          </div>
        </li>
      </ul>
    </section>

    <!-- ═══ Секция 3 · Концентрация ═══ -->
    <section class="psp-conc card" :style="{ '--i': 2 }">
      <div class="psp-eyebrow">Концентрация поставщиков по компаниям</div>

      <div v-if="!concentration.length" class="psp-empty">
        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
          <path d="M3 3v18h18" />
          <path d="M7 14l4-4 4 3 4-6" />
        </svg>
        <span>Нет данных о концентрации</span>
      </div>

      <table v-else class="psp-table">
        <thead>
          <tr>
            <th class="ta-l">Компания</th>
            <th class="ta-r">Поставщ.</th>
            <th class="ta-l">Крупнейший поставщик</th>
            <th class="ta-r">Топ-3</th>
            <th class="ta-r">HHI</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(c, i) in concentration"
            :key="c.company_id"
            class="psp-trow"
            :style="{ '--i': i }"
            :title="'Открыть профиль: ' + c.company_name"
            @click="emit('select-company', c.company_id)"
          >
            <td class="ta-l">
              <span class="psp-co">
                <span class="psp-dotc" :style="{ background: c.company_color || '#7F77DD' }" />
                <span class="psp-co-nm" :title="c.company_name">{{ c.company_name }}</span>
              </span>
            </td>
            <td class="ta-r psp-num">{{ fmtN(c.supplier_count) }}</td>
            <td class="ta-l">
              <div class="psp-top1">
                <span class="psp-top1-nm" :title="c.top1_name || '—'">{{ c.top1_name || "—" }}</span>
                <div class="psp-top1-bar">
                  <div
                    class="psp-top1-fill"
                    :style="{ width: Math.max(2, Math.min(100, Number(c.top1_pct) || 0)) + '%' }"
                  />
                </div>
              </div>
            </td>
            <td class="ta-r psp-num">{{ fmtPct1(c.top3_pct) }}</td>
            <td class="ta-r">
              <span class="psp-hhi" :class="hhiBand(Number(c.hhi) || 0).cls">
                {{ fmtN(Math.round(Number(c.hhi) || 0)) }}
                <small>{{ hhiBand(Number(c.hhi) || 0).label }}</small>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
/* ═══ Премиум-анимация появления ═══ */
@keyframes paIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}

.psp {
  display: grid;
  gap: 16px;
}

/* ── Базовая карточка с top-accent ── */
.card {
  position: relative;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  padding: 16px;
  overflow: hidden;
  opacity: 0;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 60ms);
}
.card::before {
  content: "";
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
  border-top-left-radius: 14px;
  border-top-right-radius: 14px;
}

/* ── Eyebrow ── */
.psp-eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .5);
}

/* ═══ Секция 1 · Сводка ═══ */
.psp-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 12px;
}
.psp-sum-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  border-radius: 10px;
  background: rgba(127, 119, 221, .045);
  border: 1px solid rgba(127, 119, 221, .08);
}
.psp-sum-val {
  font-size: 26px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.02em;
  color: #1E2A4A;
  line-height: 1.05;
}
.psp-sum-lbl {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: rgba(15, 23, 60, .5);
}

/* ═══ Секция 2 · Списки ═══ */
.psp-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.psp-seg {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  background: rgba(15, 23, 60, .04);
}
.psp-seg-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: none;
  background: transparent;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  color: rgba(15, 23, 60, .55);
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background .18s, color .18s, box-shadow .18s;
}
.psp-seg-btn:hover { color: #1E2A4A; }
.psp-seg-btn.active {
  background: #fff;
  color: #5B53C2;
  box-shadow: 0 2px 6px rgba(15, 23, 60, .08);
}
.psp-seg-cnt {
  font-size: 10.5px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 18px;
  text-align: center;
  padding: 1px 6px;
  border-radius: 9px;
  background: rgba(127, 119, 221, .14);
  color: #5B53C2;
}
.psp-seg-btn.active .psp-seg-cnt { background: rgba(127, 119, 221, .2); }

/* ── Список ── */
.psp-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.psp-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
  padding: 12px 14px;
  border-radius: 10px;
  background: #FAFAFC;
  border: 1px solid rgba(0, 0, 0, .03);
  cursor: pointer;
  opacity: 0;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
  transition: background .18s, transform .18s, box-shadow .18s;
}
.psp-row:hover {
  background: rgba(127, 119, 221, .05);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(15, 23, 60, .07);
}

.psp-main { min-width: 0; }
.psp-name-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.psp-name {
  font-size: 13.5px;
  font-weight: 600;
  color: #1E2A4A;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.psp-cross-badge {
  flex-shrink: 0;
  font-size: 9.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .04em;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(127, 119, 221, .14);
  color: #5B53C2;
}
.psp-inn {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .5);
  margin-top: 2px;
  font-variant-numeric: tabular-nums;
}
.psp-inn-muted { font-style: italic; color: rgba(15, 23, 60, .38); }

/* ── Бар спенда ── */
.psp-bar-track {
  position: relative;
  height: 16px;
  margin-top: 8px;
  border-radius: 3px;
  background: rgba(127, 119, 221, .08);
  overflow: hidden;
  display: flex;
  align-items: center;
}
.psp-bar-fill {
  position: absolute;
  inset: 0 auto 0 0;
  width: 0;
  border-radius: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
  animation: pspGrow .8s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms + 120ms);
  transition: width .8s cubic-bezier(.22, 1, .36, 1);
}
@keyframes pspGrow { from { width: 0 !important; } }
.psp-bar-share {
  position: relative;
  z-index: 1;
  margin-left: 8px;
  font-size: 10.5px;
  font-weight: 700;
  color: #1E2A4A;
  font-variant-numeric: tabular-nums;
}

/* ── Чипы компаний ── */
.psp-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.psp-chip {
  font-size: 10px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(15, 23, 60, .05);
  color: rgba(15, 23, 60, .62);
  white-space: nowrap;
}
.psp-chip-more {
  background: rgba(127, 119, 221, .12);
  color: #5B53C2;
}

/* ── Метрики справа ── */
.psp-metrics {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  text-align: right;
  flex-shrink: 0;
}
.psp-spend {
  font-size: 15px;
  font-weight: 400;
  color: #1E2A4A;
  font-variant-numeric: tabular-nums;
  letter-spacing: -.01em;
}
.psp-sub {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: rgba(15, 23, 60, .55);
  font-variant-numeric: tabular-nums;
}
.psp-sub-it { display: inline-flex; align-items: center; gap: 4px; }
.psp-dot { color: rgba(15, 23, 60, .28); }
.psp-co-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 700;
  background: rgba(15, 23, 60, .06);
  color: rgba(15, 23, 60, .6);
}
.psp-co-badge.hot {
  background: rgba(127, 119, 221, .16);
  color: #5B53C2;
}
.psp-sub-2 { margin-top: 1px; }
.psp-saved {
  font-size: 11px;
  font-weight: 600;
  color: rgba(15, 23, 60, .5);
}
.psp-saved.pos { color: #0F6E56; }

.psp-prem-line {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
}
.psp-prem-badge {
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 7px;
}
.psp-prem-badge.prem-low {
  background: rgba(239, 179, 115, .18);
  color: #854F0B;
}
.psp-prem-badge.prem-mid {
  background: rgba(239, 179, 115, .26);
  color: #854F0B;
}
.psp-prem-badge.prem-high {
  background: rgba(226, 128, 127, .22);
  color: #933632;
}
.psp-excess {
  font-size: 12px;
  font-weight: 600;
  color: #C76A68;
  font-variant-numeric: tabular-nums;
}

/* ═══ Секция 3 · Концентрация ═══ */
.psp-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 12px;
}
.psp-table thead th {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: rgba(15, 23, 60, .45);
  padding: 6px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
}
.ta-l { text-align: left; }
.ta-r { text-align: right; }

.psp-trow {
  cursor: pointer;
  opacity: 0;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
  transition: background .18s;
}
.psp-trow:hover { background: rgba(127, 119, 221, .05); }
.psp-trow td {
  padding: 9px 10px;
  border-bottom: 1px solid rgba(0, 0, 0, .04);
  font-size: 12.5px;
  color: #1E2A4A;
  vertical-align: middle;
}
.psp-num { font-variant-numeric: tabular-nums; }

.psp-co {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  max-width: 220px;
}
.psp-dotc {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  box-shadow: 0 0 0 2px rgba(0, 0, 0, .04);
}
.psp-co-nm {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.psp-top1 {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  max-width: 260px;
}
.psp-top1-nm {
  font-size: 12px;
  color: rgba(15, 23, 60, .72);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.psp-top1-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(127, 119, 221, .1);
  overflow: hidden;
}
.psp-top1-fill {
  height: 100%;
  width: 0;
  border-radius: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
  animation: pspGrow .8s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms + 120ms);
  transition: width .8s cubic-bezier(.22, 1, .36, 1);
}

.psp-hhi {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 1px;
  font-size: 12.5px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 3px 9px;
  border-radius: 8px;
}
.psp-hhi small {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .03em;
  opacity: .85;
}
.psp-hhi.hhi-high { background: rgba(226, 128, 127, .18); color: #933632; }
.psp-hhi.hhi-mid  { background: rgba(239, 179, 115, .2);  color: #854F0B; }
.psp-hhi.hhi-low  { background: rgba(93, 192, 147, .18);  color: #0F6E56; }

/* ═══ Пустое состояние ═══ */
.psp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 34px 18px;
  color: rgba(15, 23, 60, .4);
  font-size: 12.5px;
}
.psp-empty svg { color: rgba(15, 23, 60, .22); }

/* ═══ Адаптив ═══ */
@media (max-width: 720px) {
  .psp-summary-grid { grid-template-columns: 1fr; }
  .psp-row {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }
  .psp-metrics { align-items: flex-start; text-align: left; }
  .psp-table thead { display: none; }
  .psp-trow,
  .psp-trow td {
    display: block;
    width: 100%;
    border: none;
  }
  .psp-trow {
    padding: 10px 8px;
    border-bottom: 1px solid rgba(0, 0, 0, .06);
    margin-bottom: 2px;
  }
  .psp-top1, .psp-co { max-width: none; }
}

@media (prefers-reduced-motion: reduce) {
  .card, .psp-row, .psp-trow,
  .psp-bar-fill, .psp-top1-fill {
    animation: none !important;
    opacity: 1 !important;
  }
}
</style>
