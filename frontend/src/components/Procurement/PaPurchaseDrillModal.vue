<script setup lang="ts">
/**
 * PaPurchaseDrillModal — drill 2-го уровня по отдельной закупке.
 *
 * Содержит:
 *   • KPI cards: цена компании / средняя рынка / переплата / объём за период
 *   • Related purchases этой компании в той же категории (max 8)
 *   • Эталон-компания (наименьшая средняя цена в категории) + рекомендация
 *
 * История чарта (line 22682 paRenderHistChart) — TODO в Phase 2, для MVP
 * показываем без графика; structure остаётся.
 */
import { computed } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  paSameCat,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";

const props = defineProps<{
  purchase: ClosureRow;
  data: ProcurementAggregate;
}>();

defineEmits<{
  (e: "close"): void;
  (e: "select-co", companyId: string): void;
}>();

const cat = computed(() => {
  const found = props.data.categories.find(c => paSameCat(c.id, props.purchase.category_id));
  return found || { id: 0, name: "", short: "", icon: null };
});

const related = computed<ClosureRow[]>(() => {
  return props.data.purchases
    .filter(r =>
      r.company_id === props.purchase.company_id &&
      paSameCat(r.category_id, props.purchase.category_id),
    )
    .sort((a, b) => (b.contract_date || "").localeCompare(a.contract_date || ""))
    .slice(0, 8);
});

const totalVol = computed(() =>
  related.value.reduce((s, r) => s + r.volume, 0),
);

const devPct = computed(() => props.purchase.deviation_pct ?? 0);
const devAbs = computed(() =>
  (props.purchase.unit_price - props.purchase.market_avg) * props.purchase.volume,
);
const dirClass = computed(() => devPct.value >= 0 ? "up" : "dn");

const bestCo = computed<ClosureRow | null>(() => {
  let best: ClosureRow | null = null;
  let bestPrice = Infinity;
  for (const r of props.data.purchases) {
    if (!paSameCat(r.category_id, props.purchase.category_id)) continue;
    if (r.unit_price < bestPrice) { bestPrice = r.unit_price; best = r; }
  }
  return best;
});

const recommendation = computed<string>(() => {
  const best = bestCo.value;
  if (best && best.company_id !== props.purchase.company_id && best.unit_price < props.purchase.unit_price) {
    const saveTotal = (props.purchase.unit_price - best.unit_price) * totalVol.value;
    return `${best.company_name} закупает по ${paFmtMoney(best.unit_price)}` +
      (best.supplier ? ` у поставщика ${best.supplier}` : "") +
      `. Рассмотреть смену поставщика. Потенциальная экономия — ${paFmtMoneyShort(saveTotal)} сум/год при сохранении объёмов.`;
  }
  if (devPct.value < -5) {
    return `Закупка ниже рынка на ${Math.abs(devPct.value).toFixed(1)}%. Хороший результат — поделиться методикой с другими компаниями.`;
  }
  return "Цена в пределах рыночной. Продолжать мониторинг.";
});

function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return d;
}
</script>

<template>
  <Transition name="pa-modal" appear>
    <div class="pa-modal-bg" @click.self="$emit('close')">
      <div class="pa-modal-card">
        <div class="pa-mh">
          <div class="pa-mh-l">
            <div class="pa-mh-cat">
              <span class="pa-mh-pill">№{{ purchase.category_id }}</span> {{ cat.name }}
            </div>
            <div class="pa-mh-t">{{ purchase.company_name || purchase.company_id }} · {{ cat.name || 'закупка' }}</div>
            <div class="pa-mh-s">
              <span class="pa-mh-badge" :class="dirClass">
                {{ devPct >= 0 ? '+' : '' }}{{ devPct.toFixed(1) }}% к рынку
              </span>
              <span>
                средняя {{ paFmtMoney(purchase.market_avg) }} · ваша
                {{ paFmtMoney(purchase.unit_price) }} / {{ cat.short || 'ед' }}
              </span>
            </div>
          </div>
          <button class="pa-mh-x" @click="$emit('close')">✕</button>
        </div>

        <!-- KPI row -->
        <div class="pa-mk-row">
          <div class="pa-mk">
            <div class="pa-mk-l">Цена компании</div>
            <div class="pa-mk-v">{{ paFmtMoney(purchase.unit_price) }}<small>/{{ cat.short || 'ед' }}</small></div>
          </div>
          <div class="pa-mk">
            <div class="pa-mk-l">Средняя рынка</div>
            <div class="pa-mk-v">{{ paFmtMoney(purchase.market_avg) }}<small>/{{ cat.short || 'ед' }}</small></div>
          </div>
          <div class="pa-mk">
            <div class="pa-mk-l">{{ devAbs >= 0 ? 'Переплата' : 'Экономия' }}</div>
            <div class="pa-mk-v" :class="dirClass">
              {{ devAbs >= 0 ? '+' : '' }}{{ paFmtMoney(Math.abs(purchase.unit_price - purchase.market_avg)) }}<small>/{{ cat.short || 'ед' }}</small>
            </div>
          </div>
          <div class="pa-mk">
            <div class="pa-mk-l">Объём за период</div>
            <div class="pa-mk-v">{{ totalVol.toLocaleString('ru-RU') }}<small>{{ cat.short || 'ед' }}</small></div>
          </div>
        </div>

        <!-- Body -->
        <div class="pa-mb">
          <!-- Recommendation -->
          <div class="pa-rec" :class="{ 'pa-rec-good': devPct < -5 }">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span v-html="recommendation"></span>
          </div>

          <!-- Related purchases -->
          <div v-if="related.length > 1" class="pa-mb-card">
            <div class="pa-mb-h">
              <span class="pa-mb-t">Состав закупок · {{ related.length }} {{ related.length === 1 ? 'закупка' : 'закупок' }}</span>
              <span class="pa-mb-s">общий объём {{ totalVol.toLocaleString('ru-RU') }} {{ cat.short || 'ед' }}</span>
            </div>
            <table class="pa-list-tbl">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Поставщик</th>
                  <th class="rt">Объём, {{ cat.short || 'ед' }}</th>
                  <th class="rt">Цена/{{ cat.short || 'ед' }}</th>
                  <th class="rt">vs рынок</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in related" :key="r.id">
                  <td>{{ fmtDate(r.contract_date) }}</td>
                  <td>{{ r.supplier || '—' }}</td>
                  <td class="rt">{{ r.volume.toLocaleString('ru-RU') }}</td>
                  <td class="rt">{{ r.unit_price.toLocaleString('ru-RU') }}</td>
                  <td class="rt" :class="(r.deviation_pct ?? 0) >= 0 ? 'up' : 'dn'">
                    {{ (r.deviation_pct ?? 0) >= 0 ? '+' : '' }}{{ (r.deviation_pct ?? 0).toFixed(1) }}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="pa-mf">
          <div class="pa-mf-meta">
            Год {{ data.year || '—' }}
            <template v-if="purchase.supplier"> · поставщик {{ purchase.supplier }}</template>
          </div>
          <div class="pa-mf-actions">
            <button v-if="bestCo && bestCo.company_id !== purchase.company_id"
              class="pa-mf-btn"
              @click="$emit('select-co', bestCo!.company_id)">
              Профиль эталона
            </button>
            <button class="pa-mf-btn primary" @click="$emit('close')">Закрыть</button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.pa-modal-bg {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.pa-modal-card {
  background: #fff;
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(0, 0, 0, .22);
  width: 760px; max-width: 100%;
  max-height: 88vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}

.pa-mh {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
}
.pa-mh-l { min-width: 0; flex: 1; }
.pa-mh-cat {
  font-size: 11px; color: #888780;
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 4px;
}
.pa-mh-pill {
  display: inline-block;
  background: rgba(127, 119, 221, .12); color: #534AB7;
  font-size: 10px; font-weight: 700;
  padding: 2px 7px;
  border-radius: 4px;
}
.pa-mh-t { font-size: 15px; font-weight: 600; color: #1E2A4A; }
.pa-mh-s {
  font-size: 12px; color: #5F5E5A; margin-top: 4px;
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.pa-mh-badge {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 4px;
  font-size: 11px; font-weight: 700;
  font-feature-settings: "tnum";
}
.pa-mh-badge.up { background: rgba(226, 75, 74, .12); color: #A32D2D; }
.pa-mh-badge.dn { background: rgba(29, 158, 117, .12); color: #0F6E56; }
.pa-mh-x {
  border: 0; background: #F4F3F9;
  width: 30px; height: 30px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: #888780;
  flex-shrink: 0;
}
.pa-mh-x:hover { background: rgba(226, 75, 74, .12); color: #A32D2D; }

/* KPI cards row */
.pa-mk-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding: 14px 22px;
  background: linear-gradient(180deg, #FAFAFC, #fff);
  border-bottom: 1px solid rgba(0, 0, 0, .04);
}
@media (max-width: 600px) { .pa-mk-row { grid-template-columns: repeat(2, 1fr); } }
.pa-mk {
  padding: 8px 0;
  border-right: 0.5px solid rgba(0, 0, 0, .06);
}
.pa-mk:last-child { border-right: 0; }
.pa-mk-l {
  font-size: 9.5px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .07em;
  margin-bottom: 4px;
}
.pa-mk-v {
  font-size: 18px; font-weight: 600; color: #1E2A4A;
  font-feature-settings: "tnum";
  line-height: 1.1;
}
.pa-mk-v small { font-size: 10px; color: #888780; font-weight: 500; margin-left: 2px; }
.pa-mk-v.up { color: #A32D2D; }
.pa-mk-v.dn { color: #0F6E56; }

.pa-mb {
  flex: 1; overflow-y: auto;
  padding: 14px 22px;
}

.pa-rec {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(127, 119, 221, .06);
  border: 1px solid rgba(127, 119, 221, .15);
  border-left: 3px solid #7F77DD;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px; line-height: 1.55;
  color: #1E2A4A;
  margin-bottom: 14px;
}
.pa-rec svg { color: #7F77DD; flex-shrink: 0; margin-top: 1px; }
.pa-rec.pa-rec-good {
  background: rgba(29, 158, 117, .06);
  border-color: rgba(29, 158, 117, .15);
  border-left-color: #1D9E75;
}
.pa-rec.pa-rec-good svg { color: #1D9E75; }

.pa-mb-card {
  background: #FAFAFC;
  border: 1px solid rgba(0, 0, 0, .04);
  border-radius: 8px;
  overflow: hidden;
}
.pa-mb-h {
  padding: 10px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
}
.pa-mb-t { font-size: 12px; font-weight: 600; color: #1E2A4A; }
.pa-mb-s { font-size: 11px; color: #888780; }

.pa-list-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pa-list-tbl thead th {
  padding: 8px 14px; text-align: left;
  font-size: 10px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .04em;
  background: rgba(0, 0, 0, .02);
}
.pa-list-tbl thead th.rt { text-align: right; }
.pa-list-tbl tbody td {
  padding: 7px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  color: #1E2A4A;
  font-feature-settings: "tnum";
}
.pa-list-tbl tbody td.rt { text-align: right; }
.pa-list-tbl tbody td.up { color: #A32D2D; font-weight: 600; }
.pa-list-tbl tbody td.dn { color: #0F6E56; font-weight: 600; }
.pa-list-tbl tbody tr:last-child td { border-bottom: 0; }

.pa-mf {
  padding: 12px 22px;
  border-top: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  background: #FAFAFC;
}
.pa-mf-meta { font-size: 11px; color: #888780; }
.pa-mf-actions { display: flex; gap: 8px; }
.pa-mf-btn {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid rgba(15, 23, 60, .12);
  background: #fff;
  color: #1E2A4A;
  cursor: pointer;
  font-family: inherit;
  transition: all .12s;
}
.pa-mf-btn:hover { background: #F4F3F9; }
.pa-mf-btn.primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pa-mf-btn.primary:hover { background: #6F66D0; }

.pa-modal-enter-active, .pa-modal-leave-active { transition: opacity .2s; }
.pa-modal-enter-active .pa-modal-card,
.pa-modal-leave-active .pa-modal-card { transition: transform .2s, opacity .2s; }
.pa-modal-enter-from .pa-modal-card,
.pa-modal-leave-to .pa-modal-card { transform: scale(.96); opacity: 0; }
.pa-modal-enter-from, .pa-modal-leave-to { opacity: 0; }
</style>
