<template>
  <ModalShell :open="true" size="lg" @close="$emit('close')">
    <template #header>
      <div>
        <div class="kpd-eyebrow">{{ headerEyebrow }}</div>
        <h2 class="kpd-title">{{ headerTitle }}</h2>
      </div>
    </template>

    <div class="kpd-body">
        <!-- Status drill: list indicators in a status bucket -->
        <div v-if="mode === 'status' && summary && statusKey">
          <div class="kpd-summary">
            <div class="kpd-stat">
              <span class="kpd-stat-l">{{ t("Индикаторов") }}</span>
              <span class="kpd-stat-v">{{ statusItems.length }}</span>
            </div>
            <div class="kpd-stat">
              <span class="kpd-stat-l">{{ t("Компаний") }}</span>
              <span class="kpd-stat-v">{{ uniqueCompanies(statusItems).length }}</span>
            </div>
            <div class="kpd-stat">
              <span class="kpd-stat-l">{{ t("Средний %") }}</span>
              <span class="kpd-stat-v" :style="{ color: kpiStatusColor(avgStatusPct) }">
                {{ avgStatusPct.toFixed(1) }}%
              </span>
            </div>
          </div>

          <table class="kpd-tbl">
            <thead>
              <tr>
                <th class="lbl srt" :class="{ active: sort.key === 'name' }" @click="sortBy('name')">{{ t("Индикатор") }}{{ arrow('name') }}</th>
                <th class="lbl srt" :class="{ active: sort.key === 'co' }" @click="sortBy('co')">{{ t("Компания") }}{{ arrow('co') }}</th>
                <th class="srt" :class="{ active: sort.key === 'weight' }" @click="sortBy('weight')">{{ t("Вес") }}{{ arrow('weight') }}</th>
                <th class="srt" :class="{ active: sort.key === 'plan' }" @click="sortBy('plan')">{{ t("План") }}{{ arrow('plan') }}</th>
                <th class="srt" :class="{ active: sort.key === 'fact' }" @click="sortBy('fact')">{{ t("Факт") }}{{ arrow('fact') }}</th>
                <th class="srt" :class="{ active: sort.key === 'pct' }" @click="sortBy('pct')">%{{ arrow('pct') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(ind, i) in sortedStatusItems"
                :key="ind.ind_id"
                :style="{ animationDelay: `${i * 30}ms` }"
              >
                <td class="lbl">{{ ind.name }}</td>
                <td class="lbl">{{ ind.co_name }} · {{ ind.mgr }}</td>
                <td class="num">{{ ind.weight }}</td>
                <td class="num">{{ fmtNum(ind.plan) }}</td>
                <td class="num">
                  {{ fmtNum(ind.fact) }}
                  <span v-if="ind.source && !['annual', 'quarter'].includes(ind.source)" class="kpd-src" :title="t(srcTitle(ind.source))">{{ t(srcShort(ind.source)) }}</span>
                </td>
                <td class="pct" :style="{ color: kpiStatusColor(ind.pct ?? 0) }">
                  {{ ind.pct != null ? ind.pct.toFixed(1) + "%" : "—" }}
                  <span v-if="ind.is_anomaly" class="kpd-anom" :title="t('Аномальное значение (вероятная ошибка данных) — показано в пределах [0;150%]')">⚠</span>
                </td>
              </tr>
              <tr v-if="!statusItems.length">
                <td colspan="6" class="kpd-empty">{{ t("В этой группе нет индикаторов") }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Sector drill -->
        <div v-else-if="mode === 'sector' && summary">
          <table class="kpd-tbl">
            <thead>
              <tr>
                <th class="lbl srt" :class="{ active: sort.key === 'co' }" @click="sortBy('co')">{{ t("Компания") }}{{ arrow('co') }}</th>
                <th class="srt" :class="{ active: sort.key === 'count' }" @click="sortBy('count')">{{ t("Индикаторов") }}{{ arrow('count') }}</th>
                <th class="srt" :class="{ active: sort.key === 'hit' }" @click="sortBy('hit')">{{ t("На цели") }}{{ arrow('hit') }}</th>
                <th class="srt" :class="{ active: sort.key === 'risk' }" @click="sortBy('risk')">{{ t("В риске") }}{{ arrow('risk') }}</th>
                <th class="srt" :class="{ active: sort.key === 'crit' }" @click="sortBy('crit')">{{ t("Критично") }}{{ arrow('crit') }}</th>
                <th class="srt" :class="{ active: sort.key === 'pct' }" @click="sortBy('pct')">%{{ arrow('pct') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(c, i) in sortedSectorCompanies"
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
              <tr v-if="!sortedSectorCompanies.length">
                <td colspan="6" class="kpd-empty">{{ t("В этом секторе нет компаний с KPI") }}</td>
              </tr>
            </tbody>
          </table>
        </div>
    </div>
  </ModalShell>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";
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

const { t } = useI18n();

const statusItems = computed<KpiIndPayload[]>(() => {
  if (props.mode !== "status" || !props.statusKey) return [];
  const items = props.summary.distribution[props.statusKey] || [];
  return [...items].sort((a, b) => (b.pct ?? 0) - (a.pct ?? 0));
});

function uniqueCompanies(items: KpiIndPayload[]): string[] {
  return Array.from(new Set(items.map((i) => i.co_id)));
}

// P2-2: взвешенное среднее (по weight), как и вся методика модуля, а не простое
// среднее по индикаторам. pct приходит уже clamp[0;150] с бэка.
const avgStatusPct = computed(() => {
  if (!statusItems.value.length) return 0;
  let sw = 0, swp = 0;
  for (const i of statusItems.value) {
    const w = num(i.weight) || 0;
    if (w <= 0) continue;
    sw += w;
    swp += (i.pct ?? 0) * w;
  }
  if (sw > 0) return swp / sw;
  return statusItems.value.reduce((s, i) => s + (i.pct ?? 0), 0) / statusItems.value.length;
});

const sectorCompanies = computed(() => {
  if (props.mode !== "sector" || !props.sectorCode) return [];
  return props.summary.by_company.filter((c) => c.sector_code === props.sectorCode);
});

// P1-3: происхождение план/факт (когда не годовой/квартальный «как есть»).
function srcShort(s?: string | null): string {
  return ({
    ytd: "Σ кв.", ytd_q4: "нараст.", nsbu: "НСБУ", bp_plan: "БП", bp: "БП",
    quarter_cum: "нараст.",
  } as Record<string, string>)[s || ""] || "";
}
function srcTitle(s?: string | null): string {
  return ({
    // Конвенция кварталов задана в самой строке KPI (quarters_mode):
    // 'per_quarter' → год = Σ Q1..Q4, 'cumulative' → год = последний квартал.
    ytd: "Годовой факт не закрыт: сумма Q1..Q4 (кварталы строки — суммы за квартал)",
    ytd_q4: "Годовой факт не закрыт: последний закрытый квартал (кварталы строки ведутся нарастающим итогом)",
    quarter_cum: "Значение с начала года на конец квартала (кварталы строки ведутся нарастающим итогом)",
    nsbu: "Факт из НСБУ-отчётности (связь с Бизнес-планом)",
    bp_plan: "План из Бизнес-плана (связанный KPI)",
    bp: "Из Бизнес-плана (связанный KPI)",
  } as Record<string, string>)[s || ""] || "";
}

// ─── Column sorting (обе таблицы) ─────────────────────────────────
const sort = ref<{ key: string; dir: "asc" | "desc" }>({ key: "pct", dir: "desc" });
const TEXT_KEYS = new Set(["name", "co"]);
function sortBy(key: string) {
  if (sort.value.key === key) {
    sort.value = { key, dir: sort.value.dir === "asc" ? "desc" : "asc" };
  } else {
    sort.value = { key, dir: TEXT_KEYS.has(key) ? "asc" : "desc" };
  }
}
function arrow(key: string): string {
  if (sort.value.key !== key) return "";
  return sort.value.dir === "asc" ? " ↑" : " ↓";
}
function cmp(a: number | string, b: number | string, dir: "asc" | "desc"): number {
  const mul = dir === "asc" ? 1 : -1;
  if (typeof a === "string" || typeof b === "string") {
    return mul * String(a).localeCompare(String(b), "ru");
  }
  return mul * (a - b);
}

const sortedStatusItems = computed<KpiIndPayload[]>(() => {
  const { key, dir } = sort.value;
  const val = (it: KpiIndPayload): number | string => {
    switch (key) {
      case "name": return (it.name ?? "").toLowerCase();
      case "co": return `${it.co_name ?? ""} ${it.mgr ?? ""}`.toLowerCase();
      case "weight": return num(it.weight);
      case "plan": return num(it.plan);
      case "fact": return num(it.fact);
      default: return it.pct ?? -Infinity;
    }
  };
  return [...statusItems.value].sort((a, b) => cmp(val(a), val(b), dir));
});

const sortedSectorCompanies = computed(() => {
  const { key, dir } = sort.value;
  const val = (c: typeof sectorCompanies.value[number]): number | string => {
    switch (key) {
      case "co": return (c.co_name ?? "").toLowerCase();
      case "count": return c.count;
      case "hit": return c.hit;
      case "risk": return c.risk;
      case "crit": return c.crit;
      default: return c.pct;
    }
  };
  return [...sectorCompanies.value].sort((a, b) => cmp(val(a), val(b), dir));
});

const headerEyebrow = computed(() => {
  if (props.mode === "status") return t("Группа индикаторов");
  if (props.mode === "sector") return t("Компании сектора");
  return "";
});

const headerTitle = computed(() => {
  if (props.mode === "status" && props.statusKey) return t(kpiStatusLabel(props.statusKey));
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
.kpd-eyebrow {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
}
.kpd-title { font-size: 16px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1e2a4a); }

.kpd-body { padding: 16px 4px 4px; overflow-y: auto; }

.kpd-summary {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  padding: 12px 14px;
  background: var(--bg2, #FAFAFD);
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
  color: var(--t1, #1e2a4a);
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
.kpd-tbl th.srt { cursor: pointer; user-select: none; white-space: nowrap; transition: color .15s; }
.kpd-tbl th.srt:hover { color: rgba(15, 23, 60, .8); }
.kpd-tbl th.srt.active { color: #6C5CE7; }
.kpd-tbl thead th { position: sticky; top: 0; background: var(--bg1, #fff); z-index: 1; }
.kpd-tbl td {
  padding: 7px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  text-align: right;
  color: var(--t1, #1e2a4a);
  animation: rowIn .35s ease backwards;
}
@keyframes rowIn { from { opacity: 0; transform: translateX(-3px); } to { opacity: 1; transform: translateX(0); } }
.kpd-tbl td.lbl { text-align: left; }
.kpd-tbl td.pct { font-weight: 600; }
.kpd-src {
  font-size: 8.5px; font-weight: 600; letter-spacing: .02em;
  color: var(--p-deep, #534AB7); background: rgba(127, 119, 221, .12);
  padding: 0 4px; border-radius: 999px; margin-left: 4px; cursor: help;
}
.kpd-anom { color: #C97F1A; font-size: 11px; cursor: help; margin-left: 3px; }

.cnt-good { color: var(--green); font-weight: 600; }
.cnt-warn { color: var(--amber); font-weight: 600; }
.cnt-bad { color: var(--sev-high); font-weight: 600; }

.kpd-empty {
  text-align: center;
  color: rgba(15, 23, 60, .5);
  font-style: italic;
  padding: 16px;
}
</style>
