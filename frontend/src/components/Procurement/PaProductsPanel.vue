<script setup lang="ts">
/**
 * PaProductsPanel — ТОВАРЫ И УСЛУГИ.
 *
 * Ценовой бенчмарк по productCode (`data.products_by_code`) + потенциальная
 * экономия, с разделением PRODUCT / SERVICE. Сегмент-переключатель «Товары ⟷
 * Услуги» фильтрует позиции по `product_type`; над таблицей — сводка спенда
 * (goods_spend / services_spend) и число позиций каждого типа.
 *
 * Логика бенчмарка:
 *  - 1 строка = 1 productCode (ProductAgg из products_by_code);
 *  - по умолчанию показываем только сравнимые позиции (unique_buyers >= 2),
 *    но есть тумблер «показать все»;
 *  - сортировка по potential_saving убыв.;
 *  - мини-бар «цена-позиция»: маркер медианы (avg_price) на шкале min..max;
 *  - quality_band → бейдж разброса (clean / wide / dirty «несопоставимо»);
 *  - Top-5 «болевых» позиций сверху как премиум-карточки.
 *
 * Услуги (shartli birlik / условная единица) часто несопоставимы — для них
 * показываем явное предупреждение об ориентировочности сравнения.
 */
import { computed, ref } from "vue";
import {
  paFmtMoneyShort,
  paFmtMoney,
  type ProcurementAggregate,
  type ProductAgg,
} from "@/api/procurement_analysis";

const props = defineProps<{ data: ProcurementAggregate }>();

const emit = defineEmits<{
  (e: "drill-product", code: string): void;
}>();

type SegType = "PRODUCT" | "SERVICE";

const seg = ref<SegType>("PRODUCT");
const showAll = ref(false);

/** Все позиции реестра в виде массива. */
const allProducts = computed<ProductAgg[]>(() =>
  Object.values(props.data.products_by_code || {}),
);

/** Число позиций по типу — для сводки и подписи сегмента. */
const counts = computed(() => {
  let goods = 0;
  let services = 0;
  for (const p of allProducts.value) {
    if (p.product_type === "SERVICE") services++;
    else goods++;
  }
  return { goods, services };
});

const goodsSpend = computed<number>(() => Number(props.data.kpis?.goods_spend ?? 0));
const servicesSpend = computed<number>(() => Number(props.data.kpis?.services_spend ?? 0));
const totalSegSpend = computed<number>(() => goodsSpend.value + servicesSpend.value);

function spendShare(v: number): number {
  const t = totalSegSpend.value;
  return t > 0 ? (v / t) * 100 : 0;
}

const isServices = computed<boolean>(() => seg.value === "SERVICE");

/** Отфильтрованные + отсортированные строки для активного сегмента. */
const rows = computed<ProductAgg[]>(() => {
  const wantService = isServices.value;
  return allProducts.value
    .filter((p) => (p.product_type === "SERVICE") === wantService)
    .filter((p) => (showAll.value ? true : Number(p.unique_buyers) >= 2))
    .sort((a, b) => Number(b.potential_saving) - Number(a.potential_saving));
});

/** Сколько позиций отфильтровано требованием unique_buyers>=2 (для подсказки). */
const hiddenCount = computed<number>(() => {
  const wantService = isServices.value;
  const total = allProducts.value.filter(
    (p) => (p.product_type === "SERVICE") === wantService,
  ).length;
  return total - rows.value.length;
});

/** Top-5 «болевых» позиций активного сегмента (по potential_saving). */
const topPain = computed<ProductAgg[]>(() => rows.value.slice(0, 5));

/** Суммарный потенциал экономии по активному сегменту (видимые строки). */
const totalPotential = computed<number>(() =>
  rows.value.reduce((s, p) => s + Number(p.potential_saving), 0),
);

function bandLabel(band: ProductAgg["quality_band"]): string {
  if (band === "clean") return "сопоставимо";
  if (band === "wide") return "широкий разброс";
  return "несопоставимо";
}

/** Положение медианы (avg_price) на шкале min..max, % 0..100. */
function medianPos(p: ProductAgg): number {
  const min = Number(p.min_price);
  const max = Number(p.max_price);
  const med = Number(p.avg_price);
  if (!(max > min)) return 50;
  const pos = ((med - min) / (max - min)) * 100;
  return Math.max(2, Math.min(98, pos));
}

function setSeg(s: SegType): void {
  seg.value = s;
}
</script>

<template>
  <div class="pa-prod-host">
    <!-- ── Сводка спенда + сегмент-переключатель ───────────────── -->
    <div class="pa-prod-head">
      <div class="pa-prod-eyebrow">Товары и услуги · ценовой бенчмарк</div>

      <div class="pa-prod-summary">
        <button
          class="pa-seg-card"
          :class="{ active: !isServices }"
          type="button"
          @click="setSeg('PRODUCT')"
        >
          <span class="pa-seg-dot dot-goods"></span>
          <span class="pa-seg-body">
            <span class="pa-seg-name">Товары</span>
            <span class="pa-seg-val">{{ paFmtMoneyShort(goodsSpend) }}</span>
            <span class="pa-seg-meta">{{ counts.goods }} позиций · {{ spendShare(goodsSpend).toFixed(1) }}%</span>
          </span>
        </button>

        <button
          class="pa-seg-card"
          :class="{ active: isServices }"
          type="button"
          @click="setSeg('SERVICE')"
        >
          <span class="pa-seg-dot dot-services"></span>
          <span class="pa-seg-body">
            <span class="pa-seg-name">Услуги</span>
            <span class="pa-seg-val">{{ paFmtMoneyShort(servicesSpend) }}</span>
            <span class="pa-seg-meta">{{ counts.services }} позиций · {{ spendShare(servicesSpend).toFixed(1) }}%</span>
          </span>
        </button>
      </div>
    </div>

    <!-- ── Предупреждение для услуг ───────────────────────────── -->
    <transition name="pa-fade">
      <div v-if="isServices" class="pa-warn">
        Цена за условную единицу (shartli birlik) — состав услуг неоднороден,
        сравнение цен ориентировочное.
      </div>
    </transition>

    <!-- ── Top-5 «болевых» позиций ────────────────────────────── -->
    <transition name="pa-swap" mode="out-in">
      <div :key="seg" class="pa-prod-body">
        <div v-if="topPain.length" class="pa-pain-grid">
          <div
            v-for="(p, i) in topPain"
            :key="'pain-' + p.code"
            class="pa-pain-card"
            :class="'band-' + p.quality_band"
            :style="{ '--i': i }"
            role="button"
            tabindex="0"
            :title="'Открыть детализацию · ' + p.name"
            @click="emit('drill-product', p.code)"
            @keydown.enter="emit('drill-product', p.code)"
          >
            <div class="pa-pain-rank">{{ i + 1 }}</div>
            <div class="pa-pain-nm" :title="p.name">{{ p.name }}</div>
            <div class="pa-pain-code">{{ p.code }}</div>
            <div class="pa-pain-save">+{{ paFmtMoneyShort(p.potential_saving) }}</div>
            <div class="pa-pain-lbl">потенц. экономия</div>
            <div class="pa-pain-foot">
              <span class="pa-chip" :class="'band-' + p.quality_band">{{ p.spread_pct.toFixed(1) }}%</span>
              <span class="pa-pain-buyers">{{ p.unique_buyers }} покуп.</span>
            </div>
          </div>
        </div>

        <!-- ── Таблица бенчмарка ───────────────────────────────── -->
        <div class="pa-table-card">
          <div class="pa-table-bar">
            <div class="pa-table-title">
              {{ isServices ? 'Бенчмарк услуг' : 'Бенчмарк товаров' }}
              <span class="pa-table-count">{{ rows.length }}</span>
            </div>
            <div class="pa-table-right">
              <div class="pa-table-total">
                Σ потенциал
                <span class="pa-table-total-v">{{ paFmtMoneyShort(totalPotential) }}</span>
              </div>
              <label class="pa-toggle">
                <input v-model="showAll" type="checkbox" />
                <span class="pa-toggle-track"><span class="pa-toggle-knob"></span></span>
                <span class="pa-toggle-text">показать все</span>
              </label>
            </div>
          </div>

          <div v-if="!showAll && hiddenCount > 0" class="pa-hint">
            Скрыто {{ hiddenCount }} позиций с одним покупателем (нет базы для сравнения цен).
          </div>

          <div v-if="!rows.length" class="pa-empty">
            <div class="pa-empty-title">Нет данных</div>
            <div class="pa-empty-sub">
              По выбранному типу нет позиций{{ !showAll ? ' с двумя и более покупателями' : '' }}.
            </div>
          </div>

          <div v-else class="pa-table-wrap">
            <table class="pa-table">
              <thead>
                <tr>
                  <th class="al">Товар</th>
                  <th class="ac">Ед.</th>
                  <th class="ac">Покуп.</th>
                  <th class="ar">Мин. цена</th>
                  <th class="ac sc">Цена-позиция</th>
                  <th class="ar">Медиана</th>
                  <th class="ar">Макс. цена</th>
                  <th class="ac">Разброс</th>
                  <th class="ar main">Потенц. экономия</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(p, i) in rows"
                  :key="p.code"
                  class="pa-row"
                  :style="{ '--i': i }"
                  :title="'Открыть детализацию · ' + p.name"
                  @click="emit('drill-product', p.code)"
                >
                  <td class="al">
                    <div class="pa-cell-nm" :title="p.name">{{ p.name }}</div>
                    <div class="pa-cell-code">{{ p.code }}</div>
                  </td>
                  <td class="ac pa-unit">{{ p.unit || '—' }}</td>
                  <td class="ac pa-buyers">{{ p.unique_buyers }}</td>
                  <td class="ar pa-num pa-min">{{ paFmtMoney(p.min_price) }}</td>
                  <td class="ac sc">
                    <div class="pa-scale" :title="'Медиана между мин. и макс.'">
                      <span class="pa-scale-track"></span>
                      <span class="pa-scale-marker" :style="{ left: medianPos(p) + '%' }"></span>
                    </div>
                  </td>
                  <td class="ar pa-num pa-med">{{ paFmtMoney(p.avg_price) }}</td>
                  <td class="ar pa-num pa-max">{{ paFmtMoney(p.max_price) }}</td>
                  <td class="ac">
                    <span
                      class="pa-chip"
                      :class="'band-' + p.quality_band"
                      :title="bandLabel(p.quality_band)"
                    >
                      {{ p.spread_pct.toFixed(1) }}%
                    </span>
                  </td>
                  <td class="ar pa-save">+{{ paFmtMoneyShort(p.potential_saving) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
@keyframes paIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: none; }
}
@keyframes paScaleGrow {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
}

.pa-prod-host {
  display: flex;
  flex-direction: column;
  gap: 14px;
  color: #1E2A4A;
}

/* ── Head / summary ────────────────────────────────────────── */
.pa-prod-eyebrow {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .5);
  margin-bottom: 10px;
}

.pa-prod-summary {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.pa-seg-card {
  display: flex;
  align-items: center;
  gap: 12px;
  text-align: left;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  padding: 14px 16px;
  cursor: pointer;
  position: relative;
  overflow: hidden;
  transition: transform .18s cubic-bezier(.22, 1, .36, 1), box-shadow .18s, border-color .18s;
}
.pa-seg-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
  opacity: 0;
  transition: opacity .18s;
}
.pa-seg-card:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(15, 23, 60, .1); }
.pa-seg-card.active {
  border-color: rgba(127, 119, 221, .45);
  box-shadow: 0 8px 22px rgba(127, 119, 221, .14);
}
.pa-seg-card.active::before { opacity: 1; }

.pa-seg-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.dot-goods { background: linear-gradient(135deg, #9D97E6, #7F77DD); }
.dot-services { background: linear-gradient(135deg, #EFB373, #E2807F); }

.pa-seg-body { display: flex; flex-direction: column; min-width: 0; }
.pa-seg-name {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: rgba(15, 23, 60, .5);
}
.pa-seg-val {
  font-size: 22px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: #1E2A4A;
  line-height: 1.1;
  margin-top: 2px;
}
.pa-seg-meta {
  font-size: 11px;
  color: rgba(15, 23, 60, .5);
  font-variant-numeric: tabular-nums;
  margin-top: 3px;
}

/* ── Warning for services ──────────────────────────────────── */
.pa-warn {
  font-size: 12px;
  line-height: 1.45;
  color: #854F0B;
  background: rgba(239, 179, 115, .14);
  border: 1px solid rgba(239, 179, 115, .35);
  border-radius: 10px;
  padding: 10px 14px;
}

/* ── Pain cards ────────────────────────────────────────────── */
.pa-prod-body { display: flex; flex-direction: column; gap: 14px; }

.pa-pain-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 12px;
}

.pa-pain-card {
  position: relative;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  padding: 16px;
  cursor: pointer;
  overflow: hidden;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
  transition: transform .18s cubic-bezier(.22, 1, .36, 1), box-shadow .18s;
}
.pa-pain-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
}
.pa-pain-card.band-wide::before { background: linear-gradient(90deg, #EFB373, #E2807F); }
.pa-pain-card.band-dirty::before { background: linear-gradient(90deg, #E2807F, #C76A68); }
.pa-pain-card:hover { transform: translateY(-3px); box-shadow: 0 10px 26px rgba(15, 23, 60, .12); }

.pa-pain-rank {
  position: absolute;
  top: 12px; right: 14px;
  font-size: 13px;
  font-weight: 600;
  color: rgba(127, 119, 221, .35);
  font-variant-numeric: tabular-nums;
}
.pa-pain-nm {
  font-size: 13px;
  font-weight: 600;
  color: #1E2A4A;
  line-height: 1.3;
  padding-right: 22px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.pa-pain-code {
  font-size: 10.5px;
  color: rgba(15, 23, 60, .42);
  font-variant-numeric: tabular-nums;
  margin-top: 3px;
}
.pa-pain-save {
  font-size: 21px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  color: #0F6E56;
  line-height: 1.1;
  margin-top: 12px;
}
.pa-pain-lbl {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: rgba(15, 23, 60, .45);
  margin-top: 2px;
}
.pa-pain-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
}
.pa-pain-buyers {
  font-size: 11px;
  color: rgba(15, 23, 60, .5);
  font-variant-numeric: tabular-nums;
}

/* ── Quality chip ──────────────────────────────────────────── */
.pa-chip {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  padding: 2px 8px;
  border-radius: 999px;
  white-space: nowrap;
}
.pa-chip.band-clean { background: rgba(93, 192, 147, .16); color: #0F6E56; }
.pa-chip.band-wide  { background: rgba(239, 179, 115, .18); color: #854F0B; }
.pa-chip.band-dirty { background: rgba(226, 128, 127, .18); color: #933632; }

/* ── Table card ────────────────────────────────────────────── */
.pa-table-card {
  background: #fff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, .05);
  box-shadow: 0 4px 14px rgba(15, 23, 60, .06);
  padding: 16px;
  position: relative;
  overflow: hidden;
}
.pa-table-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #9D97E6, #7F77DD);
}

.pa-table-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.pa-table-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .07em;
  color: rgba(15, 23, 60, .5);
  display: flex;
  align-items: center;
  gap: 8px;
}
.pa-table-count {
  font-size: 11px;
  font-weight: 600;
  color: #7F77DD;
  background: rgba(127, 119, 221, .12);
  border-radius: 999px;
  padding: 1px 8px;
  font-variant-numeric: tabular-nums;
}
.pa-table-right { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.pa-table-total {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: rgba(15, 23, 60, .5);
  display: flex;
  align-items: center;
  gap: 6px;
}
.pa-table-total-v {
  font-size: 14px;
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  color: #0F6E56;
  font-variant-numeric: tabular-nums;
}

/* ── Toggle «показать все» ─────────────────────────────────── */
.pa-toggle {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  user-select: none;
}
.pa-toggle input { position: absolute; opacity: 0; pointer-events: none; }
.pa-toggle-track {
  width: 32px; height: 18px;
  border-radius: 999px;
  background: rgba(15, 23, 60, .14);
  position: relative;
  transition: background .18s;
  flex: 0 0 auto;
}
.pa-toggle-knob {
  position: absolute;
  top: 2px; left: 2px;
  width: 14px; height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 60, .25);
  transition: transform .18s cubic-bezier(.22, 1, .36, 1);
}
.pa-toggle input:checked + .pa-toggle-track { background: #7F77DD; }
.pa-toggle input:checked + .pa-toggle-track .pa-toggle-knob { transform: translateX(14px); }
.pa-toggle-text {
  font-size: 12px;
  color: rgba(15, 23, 60, .6);
}

.pa-hint {
  font-size: 11.5px;
  color: rgba(15, 23, 60, .5);
  margin-bottom: 8px;
}

/* ── Empty ─────────────────────────────────────────────────── */
.pa-empty {
  text-align: center;
  padding: 38px 16px;
}
.pa-empty-title {
  font-size: 14px;
  font-weight: 600;
  color: rgba(15, 23, 60, .6);
}
.pa-empty-sub {
  font-size: 12px;
  color: rgba(15, 23, 60, .45);
  margin-top: 4px;
}

/* ── Table ─────────────────────────────────────────────────── */
.pa-table-wrap { overflow-x: auto; margin: 0 -4px; }
.pa-table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}
.pa-table thead th {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: rgba(15, 23, 60, .45);
  padding: 6px 10px;
  border-bottom: 1px solid rgba(15, 23, 60, .07);
  white-space: nowrap;
  position: sticky;
  top: 0;
  background: #fff;
}
.pa-table th.al, .pa-table td.al { text-align: left; }
.pa-table th.ac, .pa-table td.ac { text-align: center; }
.pa-table th.ar, .pa-table td.ar { text-align: right; }
.pa-table th.sc, .pa-table td.sc { width: 130px; }
.pa-table th.main { color: #0F6E56; }

.pa-row {
  cursor: pointer;
  animation: paIn .45s cubic-bezier(.22, 1, .36, 1) both;
  animation-delay: calc(var(--i, 0) * 35ms);
  transition: background .18s;
}
.pa-row td {
  padding: 9px 10px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  font-size: 12.5px;
  color: #1E2A4A;
}
.pa-row:hover { background: rgba(127, 119, 221, .05); }
.pa-row:hover .pa-cell-nm { color: #7F77DD; }

.pa-cell-nm {
  font-size: 12.5px;
  font-weight: 600;
  color: #1E2A4A;
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  transition: color .18s;
}
.pa-cell-code {
  font-size: 10px;
  color: rgba(15, 23, 60, .42);
  margin-top: 2px;
}
.pa-unit { font-size: 11.5px; color: rgba(15, 23, 60, .6); white-space: nowrap; }
.pa-buyers { font-weight: 600; }
.pa-num { color: rgba(15, 23, 60, .72); white-space: nowrap; }
.pa-med { color: #1E2A4A; font-weight: 600; }
.pa-min { color: #0F6E56; }
.pa-max { color: #933632; }

.pa-save {
  font-size: 14px;
  font-weight: 400;
  color: #0F6E56;
  white-space: nowrap;
}

/* ── Mini scale «цена-позиция» ─────────────────────────────── */
.pa-scale {
  position: relative;
  height: 18px;
  display: flex;
  align-items: center;
}
.pa-scale-track {
  position: absolute;
  left: 0; right: 0;
  height: 4px;
  border-radius: 3px;
  background: linear-gradient(90deg,
    rgba(93, 192, 147, .55) 0%,
    rgba(239, 179, 115, .55) 55%,
    rgba(226, 128, 127, .6) 100%);
  transform: scaleX(0);
  transform-origin: left center;
  animation: paScaleGrow .8s cubic-bezier(.22, 1, .36, 1) forwards;
  animation-delay: calc(var(--i, 0) * 35ms);
}
.pa-scale-marker {
  position: absolute;
  top: 50%;
  width: 9px; height: 9px;
  border-radius: 50%;
  background: #7F77DD;
  border: 2px solid #fff;
  box-shadow: 0 1px 3px rgba(15, 23, 60, .3);
  transform: translate(-50%, -50%);
  z-index: 1;
}

/* ── Transitions ───────────────────────────────────────────── */
.pa-fade-enter-active, .pa-fade-leave-active { transition: opacity .25s, transform .25s; }
.pa-fade-enter-from, .pa-fade-leave-to { opacity: 0; transform: translateY(-4px); }

.pa-swap-enter-active { transition: opacity .3s cubic-bezier(.22, 1, .36, 1), transform .3s cubic-bezier(.22, 1, .36, 1); }
.pa-swap-leave-active { transition: opacity .18s, transform .18s; }
.pa-swap-enter-from { opacity: 0; transform: translateY(8px); }
.pa-swap-leave-to { opacity: 0; transform: translateY(-6px); }

@media (max-width: 720px) {
  .pa-prod-summary { grid-template-columns: 1fr; }
}
</style>
