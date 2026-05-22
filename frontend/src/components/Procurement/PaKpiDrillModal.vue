<script setup lang="ts">
/**
 *
 * 4 типа (mapped to PaKpiBand events):
 *   leaders   → топ компаний по net economy (savings - overpay), best→worst
 *   overpay   → top переплат по абсолютной сумме (отдельные purchases)
 *   closures  → красные purchases (deviation_pct >= 10)
 *   above     → компании с avg deviation > 0
 *
 * Клик по строке → emit('select-co' | 'drill-purchase'), модалка закрывается.
 */
import { computed } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  type ClosureRow,
  type CompanyRatingRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";

export type KpiDrillType = "leaders" | "overpay" | "closures" | "above";

const props = defineProps<{
  type: KpiDrillType;
  data: ProcurementAggregate;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "select-co", companyId: string): void;
  (e: "drill-purchase", purchase: ClosureRow): void;
}>();

interface CompanyEcon {
  co: CompanyRatingRow;
  sumOverpay: number;
  sumSavings: number;
  netEconomy: number;
  purchasesCount: number;
}

const companyEconBy = computed<Map<string, CompanyEcon>>(() => {
  const result = new Map<string, CompanyEcon>();
  for (const co of props.data.rating) {
    result.set(co.company_id, {
      co, sumOverpay: 0, sumSavings: 0, netEconomy: 0, purchasesCount: 0,
    });
  }
  for (const p of props.data.purchases) {
    const e = result.get(p.company_id);
    if (!e) continue;
    e.purchasesCount++;
    const diff = (p.unit_price - p.market_avg) * p.volume;
    if (diff > 0) e.sumOverpay += diff;
    else if (diff < 0) e.sumSavings += -diff;
  }
  for (const e of result.values()) e.netEconomy = e.sumSavings - e.sumOverpay;
  return result;
});

const meta = computed(() => {
  const y = props.data.year ?? "—";
  switch (props.type) {
    case "leaders":
      return {
        title: "Лидеры портфеля · экономия от рынка",
        subtitle: `Год ${y} · сортировка по чистой экономии (savings − overpay) · клик — профиль компании`,
        headers: ["#", "Компания", "Сектор", "Закупок", "Экономия", "Переплата", "Нетто"],
        empty: "Нет компаний с экономией",
      };
    case "overpay":
      return {
        title: "Топ переплат · потенциал экономии",
        subtitle: `Год ${y} · отдельные закупки отсортированы по абсолютной переплате · клик — детализация`,
        headers: ["Компания", "Категория", "Цена компании", "Средняя рынка", "Объём", "Переплата"],
        empty: "Все закупки в этом году ниже или на уровне рынка",
      };
    case "closures":
      return {
        title: "Красные закупки · отклонение ≥ +10%",
        subtitle: `Год ${y} · сортировка по deviation desc · клик — детализация`,
        headers: ["Компания", "Категория", "Цена компании", "Отклонение", "Объём", "Переплата"],
        empty: "Нет закупок с отклонением ≥ +10% — отличный результат",
      };
    case "above":
      return {
        title: "Компании выше средней цены рынка",
        subtitle: `Год ${y} · в среднем переплачивают · клик — профиль компании`,
        headers: ["#", "Компания", "Сектор", "Отклонение", "Категорий выше", "Сумма потерь"],
        empty: "Все компании в среднем закупают по цене рынка или ниже",
      };
  }
});

// ─── Row data per type ────────────────────────────────────────
interface LeaderRow { kind: "company"; rank: number; co: CompanyRatingRow; econ: CompanyEcon }
interface PurchaseRow { kind: "purchase"; p: ClosureRow }
interface CompanyDevRow { kind: "company"; rank: number; co: CompanyRatingRow; econ: CompanyEcon }
type Row = LeaderRow | PurchaseRow | CompanyDevRow;

const rows = computed<Row[]>(() => {
  if (props.type === "leaders") {
    const list = [...companyEconBy.value.values()]
      .filter(e => e.netEconomy > 0)
      .sort((a, b) => b.netEconomy - a.netEconomy);
    return list.map((econ, i) => ({ kind: "company" as const, rank: i + 1, co: econ.co, econ }));
  }
  if (props.type === "above") {
    const list = [...companyEconBy.value.values()]
      .filter(e => e.co.company_deviation > 0)
      .sort((a, b) => b.co.company_deviation - a.co.company_deviation);
    return list.map((econ, i) => ({ kind: "company" as const, rank: i + 1, co: econ.co, econ }));
  }
  if (props.type === "overpay") {
    const overs = props.data.purchases
      .map(p => ({ p, devAbs: (p.unit_price - p.market_avg) * p.volume }))
      .filter(x => x.devAbs > 0)
      .sort((a, b) => b.devAbs - a.devAbs)
      .slice(0, 50);
    return overs.map(x => ({ kind: "purchase" as const, p: x.p }));
  }
  // closures
  const red = props.data.purchases
    .filter(p => (p.deviation_pct ?? 0) >= 10)
    .sort((a, b) => (b.deviation_pct ?? 0) - (a.deviation_pct ?? 0))
    .slice(0, 100);
  return red.map(p => ({ kind: "purchase" as const, p }));
});

function sectorLabel(code: string | null): string {
  const map: Record<string, string> = {
    mining: "Горнодобыча", oilgas: "Нефтегаз", oil_gas: "Нефтегаз",
    energy: "Энергетика", transport: "Транспорт", other: "Прочие",
  };
  return code ? (map[code] || code) : "—";
}

function onRowClick(r: Row) {
  if (r.kind === "company") {
    emit("select-co", r.co.company_id);
    emit("close");
  } else {
    emit("drill-purchase", r.p);
  }
}
</script>

<template>
  <Transition name="uza-fade" appear>
    <div class="pa-modal-bg" @click.self="emit('close')">
      <div class="pa-modal-card">
        <div class="pa-mh">
          <div class="pa-mh-l">
            <div class="pa-mh-t">{{ meta.title }}</div>
            <div class="pa-mh-s">{{ meta.subtitle }}</div>
          </div>
          <button class="pa-mh-x" @click="emit('close')">✕</button>
        </div>

        <div class="pa-mb">
          <table class="pa-list-tbl">
            <thead>
              <tr><th v-for="h in meta.headers" :key="h">{{ h }}</th></tr>
            </thead>
            <tbody>
              <template v-if="rows.length">
                <!-- LEADERS / ABOVE → company rows -->
                <template v-if="type === 'leaders'">
                  <tr v-for="r in (rows as LeaderRow[])" :key="r.co.company_id" @click="onRowClick(r)">
                    <td class="num rk">{{ r.rank }}</td>
                    <td class="lt">
                      <span class="pa-sec-strip" :style="{ background: r.co.company_color || '#888' }"></span>
                      <span class="pa-co-nm">{{ r.co.company_name }}</span>
                    </td>
                    <td class="muted">{{ sectorLabel(r.co.company_sector) }}</td>
                    <td class="num">{{ r.econ.purchasesCount }}</td>
                    <td class="num savings">−{{ paFmtMoneyShort(r.econ.sumSavings) }}</td>
                    <td class="num overpay">+{{ paFmtMoneyShort(r.econ.sumOverpay) }}</td>
                    <td class="num" :class="r.econ.netEconomy >= 0 ? 'net-pos' : 'net-neg'">
                      {{ r.econ.netEconomy >= 0 ? '−' : '+' }}{{ paFmtMoneyShort(Math.abs(r.econ.netEconomy)) }}
                    </td>
                  </tr>
                </template>

                <template v-else-if="type === 'above'">
                  <tr v-for="r in (rows as CompanyDevRow[])" :key="r.co.company_id" @click="onRowClick(r)">
                    <td class="num rk">{{ r.rank }}</td>
                    <td class="lt">
                      <span class="pa-sec-strip" :style="{ background: r.co.company_color || '#888' }"></span>
                      <span class="pa-co-nm">{{ r.co.company_name }}</span>
                    </td>
                    <td class="muted">{{ sectorLabel(r.co.company_sector) }}</td>
                    <td class="num overpay">+{{ r.co.company_deviation.toFixed(1) }}%</td>
                    <td class="num">{{ r.co.above_count }} из {{ r.co.cat_count }}</td>
                    <td class="num overpay">+{{ paFmtMoneyShort(Math.max(0, r.co.sum_dev)) }}</td>
                  </tr>
                </template>

                <!-- OVERPAY / CLOSURES → purchase rows -->
                <template v-else>
                  <tr v-for="(r, i) in (rows as PurchaseRow[])" :key="r.p.id + '-' + i" @click="onRowClick(r)">
                    <td class="lt">
                      <span class="pa-sec-strip" :style="{ background: r.p.company_color || '#888' }"></span>
                      <span class="pa-co-nm">{{ r.p.company_name || r.p.company_id }}</span>
                    </td>
                    <td class="muted">{{ r.p.category_name }}</td>
                    <td class="num">{{ paFmtMoney(r.p.unit_price) }}</td>
                    <td v-if="type === 'overpay'" class="num muted">{{ paFmtMoney(r.p.market_avg) }}</td>
                    <td v-else class="num overpay">+{{ (r.p.deviation_pct ?? 0).toFixed(1) }}%</td>
                    <td class="num">{{ r.p.volume.toLocaleString('ru-RU') }}</td>
                    <td class="num overpay">+{{ paFmtMoneyShort((r.p.unit_price - r.p.market_avg) * r.p.volume) }}</td>
                  </tr>
                </template>
              </template>

              <tr v-else>
                <td :colspan="meta.headers.length" class="empty">{{ meta.empty }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="pa-mf">
          <div class="pa-mf-meta">{{ rows.length }} {{ rows.length === 1 ? 'запись' : 'записей' }} · клик по строке — детализация</div>
          <div class="pa-mf-actions">
            <button class="pa-mf-btn primary" @click="emit('close')">Закрыть</button>
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
  width: 840px; max-width: 100%;
  max-height: 88vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.pa-mh {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
}
.pa-mh-l { min-width: 0; }
.pa-mh-t { font-size: 15px; font-weight: 600; color: #1E2A4A; }
.pa-mh-s { font-size: 11.5px; color: #888780; margin-top: 3px; }
.pa-mh-x {
  border: 0; background: #F4F3F9;
  width: 30px; height: 30px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: #888780;
  transition: background .12s, color .12s;
  flex-shrink: 0;
}
.pa-mh-x:hover { background: rgba(226, 75, 74, .12); color: #A32D2D; }

.pa-mb {
  flex: 1; overflow-y: auto;
  padding: 8px 0;
}

.pa-list-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pa-list-tbl thead th {
  position: sticky; top: 0;
  background: #FAFAFA;
  padding: 9px 14px; text-align: left;
  font-size: 10px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .04em;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  white-space: nowrap;
}
.pa-list-tbl tbody tr {
  cursor: pointer;
  transition: background .1s;
  animation: paRowIn .2s ease both;
}
.pa-list-tbl tbody tr:hover { background: rgba(127, 119, 221, .05); }
.pa-list-tbl tbody td {
  padding: 10px 14px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .04);
  color: #1E2A4A;
  font-feature-settings: "tnum";
}
.pa-list-tbl tbody td.empty {
  text-align: center; padding: 32px;
  color: #888780; font-style: italic;
}

td.num { text-align: right; }
td.lt {
  display: flex; align-items: center; gap: 8px;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
td.rk { color: #888780; font-weight: 600; text-align: center; width: 32px; }
td.muted { color: #888780; font-size: 11px; }
td.savings { color: #1D9E75; font-weight: 600; }
td.overpay { color: #E24B4A; font-weight: 600; }
td.net-pos { color: #0F6E56; font-weight: 700; }
td.net-neg { color: #A32D2D; font-weight: 700; }

.pa-sec-strip {
  display: inline-block; width: 3px; height: 14px;
  border-radius: 2px; flex-shrink: 0;
}
.pa-co-nm {
  font-weight: 500;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

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
.pa-mf-btn.primary {
  background: #7F77DD; color: #fff;
  border-color: #7F77DD;
}
.pa-mf-btn.primary:hover { background: #6F66D0; }

@keyframes paRowIn {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}

.pa-modal-enter-active, .pa-modal-leave-active { transition: opacity .2s; }
.pa-modal-enter-active .pa-modal-card,
.pa-modal-leave-active .pa-modal-card { transition: transform .2s, opacity .2s; }
.pa-modal-enter-from .pa-modal-card,
.pa-modal-leave-to .pa-modal-card { transform: scale(.96); opacity: 0; }
.pa-modal-enter-from, .pa-modal-leave-to { opacity: 0; }
</style>
