<template>
  <Transition name="uza-modal" appear>
  <div class="kpd-backdrop" @click.self="$emit('close')">
    <div class="kpd-modal">
      <div class="kpd-header">
        <div>
          <div class="kpd-eyebrow">{{ headerEyebrow }}</div>
          <h2 class="kpd-title">{{ headerTitle }}</h2>
        </div>
        <button class="kpd-close" @click="$emit('close')">×</button>
      </div>

      <div class="kpd-body">
        <!-- Status drill: list indicators in a status bucket -->
        <div v-if="mode === 'status' && summary && statusKey">
          <div class="kpd-summary">
            <div class="kpd-stat">
              <span class="kpd-stat-l">Индикаторов</span>
              <span class="kpd-stat-v">{{ statusItems.length }}</span>
            </div>
            <div class="kpd-stat">
              <span class="kpd-stat-l">Компаний</span>
              <span class="kpd-stat-v">{{ uniqueCompanies(statusItems).length }}</span>
            </div>
            <div class="kpd-stat">
              <span class="kpd-stat-l">Средний %</span>
              <span class="kpd-stat-v" :style="{ color: kpiStatusColor(avgStatusPct) }">
                {{ avgStatusPct.toFixed(1) }}%
              </span>
            </div>
          </div>

          <table class="kpd-tbl">
            <thead>
              <tr>
                <th class="lbl">Индикатор</th>
                <th class="lbl">Компания</th>
                <th>Вес</th>
                <th>План</th>
                <th>Факт</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(ind, i) in statusItems"
                :key="ind.ind_id"
                :style="{ animationDelay: `${i * 30}ms` }"
              >
                <td class="lbl">{{ ind.name }}</td>
                <td class="lbl">{{ ind.co_name }} · {{ ind.mgr }}</td>
                <td class="num">{{ ind.weight }}</td>
                <td class="num">{{ fmtNum(ind.plan) }}</td>
                <td class="num">{{ fmtNum(ind.fact) }}</td>
                <td class="pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                  {{ ind.pct != null ? ind.pct.toFixed(1) + "%" : "—" }}
                </td>
              </tr>
              <tr v-if="!statusItems.length">
                <td colspan="6" class="kpd-empty">В этой группе нет индикаторов</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Sector drill -->
        <div v-else-if="mode === 'sector' && summary">
          <table class="kpd-tbl">
            <thead>
              <tr>
                <th class="lbl">Компания</th>
                <th>Индикаторов</th>
                <th>На цели</th>
                <th>В риске</th>
                <th>Критично</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(c, i) in sectorCompanies"
                :key="c.company_id"
                :style="{ animationDelay: `${i * 40}ms` }"
              >
                <td class="lbl">{{ c.co_name }}</td>
                <td class="num">{{ c.count }}</td>
                <td class="num cnt-good">{{ c.hit }}</td>
                <td class="num cnt-warn">{{ c.risk }}</td>
                <td class="num cnt-bad">{{ c.crit }}</td>
                <td class="pct" :style="{ color: kpiStatusColor(c.pct) }">{{ c.pct.toFixed(1) }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  kpiStatusColor,
  kpiStatusLabel,
  num,
  type KpiIndPayload,
  type KpiStatus,
  type KpiSummary,
} from "@/api/bpKpi";

const props = defineProps<{
  mode: "status" | "sector";
  statusKey?: KpiStatus;
  sectorCode?: string;
  sectorLabel?: string;
  summary: KpiSummary;
}>();

defineEmits<{ (e: "close"): void }>();

const statusItems = computed<KpiIndPayload[]>(() => {
  if (props.mode !== "status" || !props.statusKey) return [];
  const items = props.summary.distribution[props.statusKey] || [];
  return [...items].sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));
});

function uniqueCompanies(items: KpiIndPayload[]): string[] {
  return Array.from(new Set(items.map((i) => i.co_id)));
}

const avgStatusPct = computed(() => {
  if (!statusItems.value.length) return 0;
  const sum = statusItems.value.reduce((s, i) => s + (i.pct ?? 0), 0);
  return sum / statusItems.value.length;
});

const sectorCompanies = computed(() => {
  if (props.mode !== "sector" || !props.sectorCode) return [];
  return props.summary.by_company.filter((c) => c.sector_code === props.sectorCode);
});

const headerEyebrow = computed(() => {
  if (props.mode === "status") return "Группа индикаторов";
  if (props.mode === "sector") return "Компании сектора";
  return "";
});

const headerTitle = computed(() => {
  if (props.mode === "status" && props.statusKey) return kpiStatusLabel(props.statusKey);
  if (props.mode === "sector") return props.sectorLabel ?? props.sectorCode ?? "—";
  return "—";
});

function fmtNum(v: number | string | null | undefined): string {
  if (v == null) return "—";
  const n = num(v);
  if (Math.abs(n) >= 1000) return Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ");
  if (Math.abs(n) >= 10) return n.toFixed(1);
  return n.toFixed(2);
}
</script>

<style scoped>
.kpd-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.kpd-modal {
  background: #fff;
  border-radius: 14px;
  width: min(900px, 95vw);
  max-height: 88vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
}

.kpd-header {
  padding: 18px 22px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.kpd-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.kpd-title { font-size: 16px; font-weight: 600; margin: 4px 0 0; color: #1e2a4a; }
.kpd-close {
  background: transparent;
  border: none;
  font-size: 24px;
  color: rgba(15, 23, 60, .45);
  cursor: pointer;
  padding: 0 8px;
}

.kpd-body { padding: 16px 22px 22px; overflow-y: auto; flex: 1; }

.kpd-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: #FAFAFD;
  border-radius: 8px;
}
.kpd-stat { flex: 1; }
.kpd-stat-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  display: block;
}
.kpd-stat-v {
  font-size: 18px;
  font-weight: 400;
  letter-spacing: -.02em;
  color: #1e2a4a;
  display: block;
  margin-top: 4px;
  font-variant-numeric: tabular-nums;
}

.kpd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.kpd-tbl th {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .04em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .5);
  text-align: right;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .08);
}
.kpd-tbl th.lbl { text-align: left; }
.kpd-tbl td {
  padding: 7px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  text-align: right;
  color: #1e2a4a;
  animation: rowIn .35s ease backwards;
}
@keyframes rowIn { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }
.kpd-tbl td.lbl { text-align: left; }
.kpd-tbl td.pct { font-weight: 600; }

.cnt-good { color: #1D9E75; font-weight: 600; }
.cnt-warn { color: #EF9F27; font-weight: 600; }
.cnt-bad { color: #E24B4A; font-weight: 600; }

.kpd-empty {
  text-align: center;
  color: rgba(15, 23, 60, .5);
  font-style: italic;
  padding: 16px;
}
</style>
