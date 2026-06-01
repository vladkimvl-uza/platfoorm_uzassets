<script setup lang="ts">
/**
 * PaPurchaseDrillModal — drill 2-го уровня по отдельной закупке.
 * v2 rewrite 2026-05-26: built on PaModalShell.
 *
 *   • Stats strip: цена SOE · median рынка · Δ сум/ед · Δ % · объём · потенциал
 *   • Banner: AI recommendation (с эталон-компанией если есть)
 *   • Banner: ⚠ если закупка is_dirty — данные подозрительные, не для аудита
 *   • Table: related closures этой компании в той же категории (max 8)
 */
import { computed } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  paSameCat,
  type ClosureRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import PaModalShell from "./PaModalShell.vue";

const props = defineProps<{
  purchase: ClosureRow;
  data: ProcurementAggregate;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "select-co", companyId: string): void;
}>();

const cat = computed(() => {
  const found = props.data.categories.find(c => paSameCat(c.id, props.purchase.category_id));
  return found || { id: 0, name: "—", short: "ед", icon: null };
});

const related = computed<ClosureRow[]>(() =>
  props.data.purchases
    .filter(r =>
      r.company_id === props.purchase.company_id &&
      paSameCat(r.category_id, props.purchase.category_id),
    )
    .sort((a, b) => (b.contract_date || "").localeCompare(a.contract_date || ""))
    .slice(0, 12),
);

// 2026-05-26: Number-coerce — volume/unit_price приходят строками
// (Postgres numeric → JSON). `0 + "200000"` = string concat → "0200000".
const totalVol = computed(() =>
  related.value.reduce((s, r) => s + Number(r.volume), 0),
);

const devPct = computed(() => Number(props.purchase.deviation_pct ?? 0));
const devAbs = computed(() =>
  (Number(props.purchase.unit_price) - Number(props.purchase.market_avg)) * Number(props.purchase.volume),
);

const bestCo = computed<ClosureRow | null>(() => {
  let best: ClosureRow | null = null;
  let bestPrice = Infinity;
  for (const r of props.data.purchases) {
    if (r.is_dirty) continue;
    if (!paSameCat(r.category_id, props.purchase.category_id)) continue;
    if (r.unit_price < bestPrice) { bestPrice = r.unit_price; best = r; }
  }
  return best;
});

const recommendation = computed<string>(() => {
  const best = bestCo.value;
  if (best && best.company_id !== props.purchase.company_id && best.unit_price < props.purchase.unit_price) {
    const saveTotal = (props.purchase.unit_price - best.unit_price) * totalVol.value;
    return `<b>${best.company_name}</b> закупает по <b>${paFmtMoney(best.unit_price)}</b>` +
      (best.supplier ? ` у поставщика «${best.supplier}»` : "") +
      `. Рассмотреть смену поставщика — потенциальная экономия <b>${paFmtMoneyShort(saveTotal)} сум/год</b> при сохранении объёмов.`;
  }
  if (devPct.value < -5) {
    return `Закупка <b>ниже рынка на ${Math.abs(devPct.value).toFixed(1)}%</b> — хороший результат. Поделиться методикой с другими компаниями портфеля.`;
  }
  return "Цена в пределах рыночной. Продолжать мониторинг.";
});

const isRecGood = computed(() => devPct.value < -5);

function fmtDate(d: string | null): string {
  if (!d) return "—";
  const m = d.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return `${m[3]}.${m[2]}.${m[1]}`;
  return d;
}

const accentColor = computed(() => {
  if (props.purchase.is_dirty) return "#888780";
  if (devPct.value >= 50) return "#E24B4A";
  if (devPct.value >= 10) return "#EF9F27";
  if (devPct.value < -5) return "#1D9E75";
  return "#7F77DD";
});

const headerTitle = computed(() => {
  const company = props.purchase.company_name || props.purchase.company_id;
  return `${company} · ${cat.value.name}`;
});
</script>

<template>
  <PaModalShell
    kind="Закупка"
    :title="headerTitle"
    :accent="accentColor"
    max-width="940px"
    @close="emit('close')"
  >
    <!-- ─── Stats ─── -->
    <template #stats>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Цена SOE</div>
        <div class="pms-stat-val">{{ paFmtMoney(purchase.unit_price) }}<small>/{{ cat.short || 'ед' }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Median рынка</div>
        <div class="pms-stat-val">{{ paFmtMoney(purchase.market_avg) }}<small>/{{ cat.short || 'ед' }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ devAbs >= 0 ? 'Переплата / ед.' : 'Экономия / ед.' }}</div>
        <div class="pms-stat-val" :class="devAbs >= 0 ? 'neg' : 'pos'">
          {{ devAbs >= 0 ? '+' : '−' }}{{ paFmtMoney(Math.abs(purchase.unit_price - purchase.market_avg)) }}
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ 'Δ %' }}</div>
        <div class="pms-stat-val" :class="devPct >= 0 ? 'neg' : 'pos'">
          {{ devPct >= 0 ? '+' : '' }}{{ devPct.toFixed(1) }}<small>%</small>
        </div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">Объём</div>
        <div class="pms-stat-val">{{ purchase.volume.toLocaleString('ru-RU') }}<small>{{ cat.short || 'ед' }}</small></div>
      </div>
      <div class="pms-stat">
        <div class="pms-stat-lbl">{{ devAbs >= 0 ? 'Переплата итого' : 'Экономия итого' }}</div>
        <div class="pms-stat-val" :class="devAbs >= 0 ? 'neg' : 'pos'">
          {{ devAbs >= 0 ? '+' : '−' }}{{ paFmtMoneyShort(Math.abs(devAbs)) }}<small>сум</small>
        </div>
      </div>
    </template>

    <!-- ─── Body ─── -->
    <div class="ppd-body">

      <!-- Dirty warning -->
      <div v-if="purchase.is_dirty" class="ppd-warn uza-side-stripe">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v4M12 17h.01"/>
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        </svg>
        <span><b>Закупка помечена как dirty</b> — extreme deviation, цены могут быть искажены (разные единицы, спецификации). Используй данные с осторожностью.</span>
      </div>

      <!-- AI recommendation -->
      <div class="ppd-rec" :class="{ 'ppd-rec-good': isRecGood }">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span v-html="recommendation"></span>
      </div>

      <!-- Meta line -->
      <div class="ppd-meta">
        <span v-if="purchase.supplier"><span class="ppd-meta-l">Поставщик:</span> {{ purchase.supplier }}</span>
        <span v-if="purchase.contract_date"><span class="ppd-meta-l">Дата:</span> {{ fmtDate(purchase.contract_date) }}</span>
        <span v-if="data.year"><span class="ppd-meta-l">Год:</span> FY {{ data.year }}</span>
        <button
          v-if="bestCo && bestCo.company_id !== purchase.company_id"
          class="ppd-best-btn"
          @click="emit('select-co', bestCo!.company_id); emit('close')"
        >
          Профиль эталона ({{ bestCo!.company_name }}) →
        </button>
      </div>

      <!-- Related purchases -->
      <div v-if="related.length > 1" class="ppd-section">
        <div class="ppd-section-h">
          <span class="ppd-section-t">Закупки этой компании в категории</span>
          <span class="ppd-section-s">{{ related.length }} закупок · {{ totalVol.toLocaleString('ru-RU') }} {{ cat.short || 'ед' }} объёма</span>
        </div>
        <table class="ppd-tbl">
          <thead>
            <tr>
              <th class="left">Дата</th>
              <th class="left">Поставщик</th>
              <th class="right">Объём</th>
              <th class="right">Цена</th>
              <th class="right">{{ 'Δ %' }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in related" :key="r.id" :class="{ 'ppd-row-dirty': r.is_dirty, 'ppd-row-current': r.id === purchase.id }">
              <td class="left">{{ fmtDate(r.contract_date) }}<span v-if="r.id === purchase.id" class="ppd-current-tag">текущая</span></td>
              <td class="left supplier">{{ r.supplier || '—' }}</td>
              <td class="right">{{ r.volume.toLocaleString('ru-RU') }}</td>
              <td class="right">{{ paFmtMoney(r.unit_price) }}</td>
              <td class="right" :class="(r.deviation_pct ?? 0) >= 0 ? 'neg' : 'pos'">
                {{ (r.deviation_pct ?? 0) >= 0 ? '+' : '' }}{{ (r.deviation_pct ?? 0).toFixed(1) }}%
                <span v-if="r.is_dirty" class="ppd-dirty-tag" title="Dirty">⚠</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </PaModalShell>
</template>

<style scoped>
.ppd-body {
  padding: 18px 22px 22px;
  display: flex; flex-direction: column; gap: 16px;
  flex: 1; min-height: 0;
  overflow-y: auto;
}

.ppd-warn {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(239, 159, 39, .10);
  border: 1px solid rgba(239, 159, 39, .35);
  --stripe-color: #EF9F27;
  border-radius: 8px;
  padding: 12px 14px 12px 20px;
  font-size: 12px; color: var(--t1, #1E2A4A);
  line-height: 1.5;
}
.ppd-warn svg { color: #B07415; flex-shrink: 0; margin-top: 1px; }
.ppd-warn :deep(b) { font-weight: 600; color: #B07415; }

.ppd-rec {
  display: flex; align-items: flex-start; gap: 10px;
  background: rgba(127, 119, 221, .06);
  border: 1px solid rgba(127, 119, 221, .15);
  --stripe-color: #7F77DD;
  border-radius: 8px;
  padding: 12px 14px 12px 20px;
  font-size: 12px; color: var(--t1, #1E2A4A);
  line-height: 1.55;
}
.ppd-rec svg { color: #7F77DD; flex-shrink: 0; margin-top: 1px; }
.ppd-rec :deep(b) { font-weight: 600; }
.ppd-rec.ppd-rec-good {
  background: rgba(29, 158, 117, .06);
  border-color: rgba(29, 158, 117, .15);
  --stripe-color: #1D9E75;
}
.ppd-rec.ppd-rec-good svg { color: #1D9E75; }

.ppd-meta {
  display: flex; flex-wrap: wrap; align-items: center; gap: 16px;
  font-size: 11.5px; color: var(--t3, #5F5E5A);
  padding: 6px 0 2px;
}
.ppd-meta-l {
  color: var(--t3, #888780); text-transform: uppercase;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  margin-right: 4px;
}
.ppd-best-btn {
  margin-left: auto;
  background: rgba(29, 158, 117, .08);
  border: 1px solid rgba(29, 158, 117, .25);
  color: #0F6E56;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 11.5px; font-weight: 500;
  cursor: pointer;
  font-family: inherit;
  transition: all .15s;
}
.ppd-best-btn:hover {
  background: #1D9E75;
  color: #fff;
  border-color: #1D9E75;
}

.ppd-section {
  background: var(--bg2, #FAFAFC);
  border: 1px solid rgba(0, 0, 0, .06);
  border-radius: 10px;
  overflow: hidden;
}
.ppd-section-h {
  padding: 11px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 6px;
  background: var(--bg1, #fff);
}
.ppd-section-t {
  font-size: 11px; font-weight: 600; color: var(--t1, #1E2A4A);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ppd-section-s { font-size: 11px; color: var(--t3, #888780); }

.ppd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.ppd-tbl thead th {
  padding: 8px 14px;
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--t3, #888780);
  text-transform: uppercase;
  background: rgba(0, 0, 0, .02);
}
.ppd-tbl thead th.left { text-align: left; }
.ppd-tbl thead th.right { text-align: right; }
.ppd-tbl tbody td {
  padding: 8px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.ppd-tbl tbody td.left { text-align: left; }
.ppd-tbl tbody td.right { text-align: right; }
.ppd-tbl tbody td.supplier {
  color: rgba(15, 23, 60, .65); font-style: italic;
  max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.ppd-tbl tbody td.pos { color: #1D9E75; font-weight: 600; }
.ppd-tbl tbody td.neg { color: #C53030; font-weight: 600; }
.ppd-tbl tbody tr:last-child td { border-bottom: 0; }

.ppd-row-current td { background: rgba(127, 119, 221, .06); font-weight: 600; }
.ppd-row-dirty td { opacity: 0.55; }
.ppd-current-tag {
  display: inline-block;
  font-size: 9px; font-weight: 700;
  background: rgba(127, 119, 221, .18);
  color: #534AB7;
  padding: 1px 6px; border-radius: 3px;
  margin-left: 6px;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.ppd-dirty-tag {
  font-size: 10px; color: #B07415;
  margin-left: 4px;
}
</style>
