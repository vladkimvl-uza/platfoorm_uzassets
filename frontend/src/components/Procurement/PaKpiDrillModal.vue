<script setup lang="ts">
/**
 * PaKpiDrillModal — drill для 4-х KPI карточек.
 * v2 rewrite 2026-05-26: built on PaModalShell, фильтрует is_dirty.
 *
 * 4 типа (mapped to PaKpiBand events):
 *   netpos    → топ компаний по net economy (savings - overpay)
 *   overpay   → top переплат (отдельные purchases, по abs(diff))
 *   red       → красные purchases (deviation_pct >= 10)
 *   above     → компании с avg deviation > 0
 *
 * 2026-05-26: КРИТИЧНО — раньше rows не фильтровали is_dirty, top-100
 * красных = 100% мусора (deviations 1,000,000%). Теперь dirty исключены
 * и шапка показывает «X dirty excluded».
 */
import { computed } from "vue";
import {
  paFmtMoney,
  paFmtMoneyShort,
  type ClosureRow,
  type CompanyRatingRow,
  type ProcurementAggregate,
} from "@/api/procurement_analysis";
import PaModalShell from "./PaModalShell.vue";

// 2026-05-26: legacy KpiBand sends 'netpos|overpay|red|above', не
// 'leaders|closures' — расширил алиасы для совместимости.
export type KpiDrillType = "netpos" | "leaders" | "overpay" | "red" | "closures" | "above";

const props = defineProps<{
  type: KpiDrillType;
  data: ProcurementAggregate;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "select-co", companyId: string): void;
  (e: "drill-purchase", purchase: ClosureRow): void;
}>();

// ─── Clean-only purchases (filter is_dirty=true) ────────────────
const cleanPurchases = computed(() => props.data.purchases.filter(p => !p.is_dirty));
const dirtyCount = computed(() => props.data.purchases.length - cleanPurchases.value.length);

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
  for (const p of cleanPurchases.value) {
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

// ─── Type → metadata ────────────────────────────────────────────
type TypeMeta = {
  kind: string;
  title: string;
  accent: string;
  empty: string;
  rowKind: "company" | "purchase";
};

const meta = computed<TypeMeta>(() => {
  switch (props.type) {
    case "netpos":
    case "leaders":
      return {
        kind: "Чистая позиция",
        title: "Лидеры портфеля по чистой экономии",
        accent: "#1D9E75",
        empty: "Нет компаний с экономией",
        rowKind: "company",
      };
    case "overpay":
      return {
        kind: "Переплаты",
        title: "Топ закупок · потенциал экономии",
        accent: "#E24B4A",
        empty: "Все закупки на уровне рынка или ниже",
        rowKind: "purchase",
      };
    case "red":
    case "closures":
      return {
        kind: "Красные закупки",
        title: "Закупки с отклонением ≥ +10 %",
        accent: "#E24B4A",
        empty: "Нет закупок ≥ +10% — отличный результат",
        rowKind: "purchase",
      };
    default:
      return {
        kind: "Выше рынка",
        title: "Компании с положительным средним отклонением",
        accent: "#EF9F27",
        empty: "Все SOE в среднем закупают по рынку или ниже",
        rowKind: "company",
      };
  }
});

// ─── Row data per type ──────────────────────────────────────────
interface LeaderRow { kind: "company"; rank: number; co: CompanyRatingRow; econ: CompanyEcon; }
interface PurchaseRow { kind: "purchase"; p: ClosureRow; }
type Row = LeaderRow | PurchaseRow;

const rows = computed<Row[]>(() => {
  if (props.type === "leaders" || props.type === "netpos") {
    const list = [...companyEconBy.value.values()]
      .filter(e => props.type === "netpos" || e.netEconomy > 0)
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
    const overs = cleanPurchases.value
      .map(p => ({ p, devAbs: (p.unit_price - p.market_avg) * p.volume }))
      .filter(x => x.devAbs > 0)
      .sort((a, b) => b.devAbs - a.devAbs)
      .slice(0, 50);
    return overs.map(x => ({ kind: "purchase" as const, p: x.p }));
  }
  // red / closures — фильтр is_dirty уже внутри cleanPurchases
  const red = cleanPurchases.value
    .filter(p => (p.deviation_pct ?? 0) >= 10)
    .sort((a, b) => (b.deviation_pct ?? 0) - (a.deviation_pct ?? 0))
    .slice(0, 100);
  return red.map(p => ({ kind: "purchase" as const, p }));
});

// ─── Aggregate stats per type for hero strip ────────────────────
const aggregateStats = computed(() => {
  if (meta.value.rowKind === "company") {
    const cos = rows.value as LeaderRow[];
    const totalNet = cos.reduce((s, r) => s + r.econ.netEconomy, 0);
    const totalSav = cos.reduce((s, r) => s + r.econ.sumSavings, 0);
    const totalOver = cos.reduce((s, r) => s + r.econ.sumOverpay, 0);
    return {
      count: cos.length,
      totalNet, totalSav, totalOver,
      topName: cos[0]?.co.company_name || "—",
      topValue: cos[0] ? (props.type === "above" ? cos[0].co.company_deviation : cos[0].econ.netEconomy) : 0,
    };
  }
  const prs = (rows.value as PurchaseRow[]).map(r => r.p);
  const totalOver = prs.reduce((s, p) => s + (p.unit_price - p.market_avg) * p.volume, 0);
  const totalVol = prs.reduce((s, p) => s + p.market_avg * p.volume, 0);
  const uniqueCos = new Set(prs.map(p => p.company_id)).size;
  const biggest = prs[0];
  return {
    count: prs.length,
    totalNet: 0, totalSav: 0, totalOver,
    topName: biggest ? (biggest.company_name || "—") : "—",
    topValue: biggest ? (biggest.unit_price - biggest.market_avg) * biggest.volume : 0,
    uniqueCos,
    totalVol,
  };
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
  <PaModalShell
    :kind="meta.kind"
    :title="meta.title"
    :accent="meta.accent"
    max-width="980px"
    @close="emit('close')"
  >
    <!-- ─── Stats strip ─── -->
    <template #stats>
      <template v-if="meta.rowKind === 'company'">
        <div class="pms-stat">
          <div class="pms-stat-lbl">Компаний в списке</div>
          <div class="pms-stat-val">{{ aggregateStats.count }}</div>
        </div>
        <div class="pms-stat" v-if="type === 'netpos' || type === 'leaders'">
          <div class="pms-stat-lbl">Чистая позиция</div>
          <div class="pms-stat-val" :class="aggregateStats.totalNet >= 0 ? 'pos' : 'neg'">
            {{ aggregateStats.totalNet >= 0 ? '−' : '+' }}{{ paFmtMoneyShort(Math.abs(aggregateStats.totalNet)) }}<small>сум</small>
          </div>
        </div>
        <div class="pms-stat" v-if="type !== 'above'">
          <div class="pms-stat-lbl">Сумма экономии</div>
          <div class="pms-stat-val pos">−{{ paFmtMoneyShort(aggregateStats.totalSav) }}<small>сум</small></div>
        </div>
        <div class="pms-stat" v-if="type !== 'above'">
          <div class="pms-stat-lbl">Сумма переплат</div>
          <div class="pms-stat-val neg">+{{ paFmtMoneyShort(aggregateStats.totalOver) }}<small>сум</small></div>
        </div>
        <div class="pms-stat" v-if="type === 'above'">
          <div class="pms-stat-lbl">Среднее отклонение</div>
          <div class="pms-stat-val warn">+{{ (aggregateStats.topValue as number).toFixed(1) }}<small>%</small></div>
        </div>
      </template>
      <template v-else>
        <div class="pms-stat">
          <div class="pms-stat-lbl">Закупок в списке</div>
          <div class="pms-stat-val">{{ aggregateStats.count }}</div>
        </div>
        <div class="pms-stat">
          <div class="pms-stat-lbl">Сумма переплат</div>
          <div class="pms-stat-val neg">+{{ paFmtMoneyShort(aggregateStats.totalOver) }}<small>сум</small></div>
        </div>
        <div class="pms-stat">
          <div class="pms-stat-lbl">SOE затронуто</div>
          <div class="pms-stat-val">{{ (aggregateStats as any).uniqueCos || 0 }}</div>
        </div>
        <div class="pms-stat">
          <div class="pms-stat-lbl">Самая крупная</div>
          <div class="pms-stat-val neg">+{{ paFmtMoneyShort(aggregateStats.topValue) }}<small>сум</small></div>
        </div>
        <div class="pms-stat" v-if="dirtyCount > 0">
          <div class="pms-stat-lbl">Исключено dirty</div>
          <div class="pms-stat-val warn">{{ dirtyCount }}</div>
        </div>
      </template>
    </template>

    <!-- ─── Body ─── -->
    <div class="pkd-table-wrap">
      <table class="pkd-tbl" v-if="rows.length">
        <!-- LEADERS / NETPOS / ABOVE → company rows -->
        <template v-if="meta.rowKind === 'company'">
          <thead>
            <tr>
              <th class="rk">#</th>
              <th class="left">Компания</th>
              <th class="left">Сектор</th>
              <th v-if="type !== 'above'" class="right">Закупок</th>
              <th v-if="type !== 'above'" class="right">Экономия</th>
              <th v-if="type !== 'above'" class="right">Переплата</th>
              <th v-if="type !== 'above'" class="right">Нетто</th>
              <th v-if="type === 'above'" class="right">Откл. %</th>
              <th v-if="type === 'above'" class="right">Категорий выше</th>
              <th v-if="type === 'above'" class="right">Сумма потерь</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in (rows as LeaderRow[])" :key="r.co.company_id"
                class="pkd-row-clickable"
                @click="onRowClick(r)" :title="`Открыть профиль ${r.co.company_name}`">
              <td class="rk">{{ r.rank }}</td>
              <td class="left">
                <span class="pkd-co-strip" :style="{ background: r.co.company_color || '#888' }"></span>
                {{ r.co.company_name }}
              </td>
              <td class="left muted">{{ sectorLabel(r.co.company_sector) }}</td>
              <template v-if="type !== 'above'">
                <td class="right">{{ r.econ.purchasesCount }}</td>
                <td class="right pos">−{{ paFmtMoneyShort(r.econ.sumSavings) }}</td>
                <td class="right neg">+{{ paFmtMoneyShort(r.econ.sumOverpay) }}</td>
                <td class="right" :class="r.econ.netEconomy >= 0 ? 'pos' : 'neg'">
                  {{ r.econ.netEconomy >= 0 ? '−' : '+' }}{{ paFmtMoneyShort(Math.abs(r.econ.netEconomy)) }}
                </td>
              </template>
              <template v-else>
                <td class="right warn">+{{ r.co.company_deviation.toFixed(1) }}%</td>
                <td class="right">{{ r.co.above_count }} из {{ r.co.cat_count }}</td>
                <td class="right neg">+{{ paFmtMoneyShort(Math.max(0, r.co.sum_dev)) }}</td>
              </template>
            </tr>
          </tbody>
        </template>

        <!-- OVERPAY / RED → purchase rows -->
        <template v-else>
          <thead>
            <tr>
              <th class="left">Компания</th>
              <th class="left">Категория</th>
              <th class="left">Поставщик</th>
              <th class="right">Цена SOE</th>
              <th class="right">Median рынка</th>
              <th class="right">Объём</th>
              <th class="right">{{ 'Δ %' }}</th>
              <th class="right">Переплата</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in (rows as PurchaseRow[])" :key="r.p.id + '-' + i"
                class="pkd-row-clickable"
                @click="onRowClick(r)" title="Подробнее о закупке">
              <td class="left">
                <span class="pkd-co-strip" :style="{ background: r.p.company_color || '#888' }"></span>
                {{ r.p.company_name || r.p.company_id }}
              </td>
              <td class="left muted">{{ r.p.category_name }}</td>
              <td class="left supplier">{{ r.p.supplier || '—' }}</td>
              <td class="right">{{ paFmtMoney(r.p.unit_price) }}</td>
              <td class="right muted">{{ paFmtMoney(r.p.market_avg) }}</td>
              <td class="right">{{ r.p.volume.toLocaleString('ru-RU') }}</td>
              <td class="right neg">+{{ (r.p.deviation_pct ?? 0).toFixed(1) }}%</td>
              <td class="right neg">+{{ paFmtMoneyShort((r.p.unit_price - r.p.market_avg) * r.p.volume) }}</td>
            </tr>
          </tbody>
        </template>
      </table>
      <div v-else class="pms-empty">{{ meta.empty }}</div>
    </div>
  </PaModalShell>
</template>

<style scoped>
.pkd-table-wrap {
  flex: 1; min-height: 0;
  display: flex; flex-direction: column;
}
.pkd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.pkd-tbl thead th {
  font-size: 9.5px; font-weight: 600; letter-spacing: 0.07em;
  text-transform: uppercase; color: var(--t3, var(--t-muted));
  padding: 10px 14px;
  background: var(--bg2, #FAFAFC);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
  position: sticky; top: 0; z-index: 1;
  white-space: nowrap;
}
.pkd-tbl thead th.left { text-align: left; }
.pkd-tbl thead th.right { text-align: right; }
.pkd-tbl thead th.rk { text-align: center; width: 36px; }

.pkd-tbl tbody td {
  padding: 9px 14px;
  border-bottom: 0.5px solid rgba(15, 23, 60, .05);
  color: var(--t1, #1E2A4A);
  font-weight: 500;
}
.pkd-tbl tbody td.left { text-align: left; }
.pkd-tbl tbody td.right { text-align: right; }
.pkd-tbl tbody td.rk { text-align: center; color: var(--t3, var(--t-muted)); font-weight: 600; }
.pkd-tbl tbody td.muted { color: rgba(15, 23, 60, .55); font-weight: 400; }
.pkd-tbl tbody td.supplier { color: rgba(15, 23, 60, .65); font-style: italic; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pkd-tbl tbody td.pos { color: var(--green); font-weight: 600; }
.pkd-tbl tbody td.neg { color: #C53030; font-weight: 600; }
.pkd-tbl tbody td.warn { color: #B07415; font-weight: 600; }

.pkd-co-strip {
  display: inline-block;
  width: 3px; height: 14px;
  border-radius: 2px;
  margin-right: 8px;
  vertical-align: middle;
}

.pkd-row-clickable { cursor: pointer; transition: background .12s; }
.pkd-row-clickable:hover td { background: rgba(127, 119, 221, .05); }
</style>
