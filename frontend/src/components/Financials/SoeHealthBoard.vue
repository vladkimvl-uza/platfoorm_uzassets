<script setup lang="ts">
/**
 * SoeHealthBoard — «SOE Health Check»: светофорная матрица финансовой
 * устойчивости портфеля (11 коэффициентов × компании, бенды риска 1..5,
 * Overall Rating). Данные — канон financial_lines (НСБУ/МСФО), эндпоинт
 * GET /financials/soe-health.
 *
 * Премиум-паттерны платформы: kpi-rail полоса с Odometer, top-accent карточки,
 * staggered-появление строк, светофорные пилюли (пастель), дрилл-модалка.
 */
import { computed, onMounted, ref } from "vue";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import Odometer from "@/components/Odometer.vue";
import SoeHealthDrillModal from "@/components/Financials/SoeHealthDrillModal.vue";

export interface SoeRatio {
  key: string; label: string; group: string; formula: string;
  direction: "gte" | "lte"; thresholds: number[]; fmt: "pct" | "x" | "days";
  value: number | null; band: number | null; note: string | null;
}
export interface SoeCompany {
  code: string; name: string; company_id: string;
  sector_code: string | null; sector_name: string | null; sector_color: string | null;
  ratios: SoeRatio[]; overall: number | null;
  zone: { key: string; label: string; color: string } | null;
  prev_overall: number | null; delta: number | null; available: number;
}
export interface SoeRatioMeta {
  key: string; label: string; group: string; formula: string;
  thresholds: number[]; default_thresholds?: number[]; overridden?: boolean;
  direction: "gte" | "lte"; fmt: "pct" | "x" | "days";
}
export interface SoeZone { key: string; label: string; color: string; max: number }
export interface SoeHealthPayload {
  year: number; standard: string;
  ratios_meta: SoeRatioMeta[];
  params_overridden?: boolean;
  zones: SoeZone[];
  companies: SoeCompany[];
  series?: {
    years: number[];
    totals: Record<string, (number | null)[]>;
    ratios: Record<string, (number | null)[]>;
  };
  portfolio: {
    avg: number | null; zone: { key: string; label: string; color: string } | null;
    zone_counts: Record<string, number>; scored_count: number; total_companies: number;
    worst: { code: string; name: string; overall: number }[];
    best: { code: string; name: string; overall: number }[];
  };
  methodology: string;
}

// Презентационный компонент: данные загружает страница-дашборд.
const props = defineProps<{ data: SoeHealthPayload | null; search?: string }>();

onMounted(() => { ensureFinancialsCss(); });

const data = computed(() => props.data);
const companies = computed(() => {
  const list = data.value?.companies || [];
  const q = (props.search || "").trim().toLowerCase();
  return q ? list.filter((c) => (c.name || c.code).toLowerCase().includes(q)) : list;
});
const zones = computed(() => data.value?.zones || []);
const ratiosMeta = computed(() => data.value?.ratios_meta || []);
const pf = computed(() => data.value?.portfolio || null);

function zoneByBand(band: number | null): { color: string; label: string } {
  if (band == null) return { color: "#94A3B8", label: "н/д" };
  const z = zones.value[Math.min(band, 5) - 1];
  return z ? { color: z.color, label: z.label } : { color: "#94A3B8", label: "н/д" };
}
function fmtVal(r: SoeRatio): string {
  if (r.value == null) return r.note ? "!" : "—";
  if (r.fmt === "pct") return (r.value * 100).toFixed(1) + "%";
  if (r.fmt === "days") return String(Math.round(r.value));
  return r.value.toFixed(2);
}
function fmtThr(meta: { thresholds: number[]; fmt: string; direction: string }): string {
  const f = (t: number) => meta.fmt === "pct" ? (t * 100) + "%" : String(t);
  return (meta.direction === "gte" ? "лучше ≥ " : "лучше ≤ ") + meta.thresholds.map(f).join(" / ");
}
function cellTitle(r: SoeRatio): string {
  const z = zoneByBand(r.band);
  const parts = [r.label + ": " + (r.value == null ? (r.note || "нет данных") : fmtVal(r))];
  if (r.band != null) parts.push("зона: " + z.label);
  parts.push(r.formula);
  parts.push(fmtThr(r));
  return parts.join("\n");
}
// дельта к прошлому году: снижение балла = улучшение (зелёная ↓)
function deltaMeta(c: SoeCompany): { txt: string; color: string; up: boolean } | null {
  if (c.delta == null || c.delta === 0) return null;
  const better = c.delta < 0;
  return {
    txt: (c.delta > 0 ? "+" : "") + c.delta.toFixed(2),
    color: better ? "#1D9E75" : "#E24B4A",
    up: c.delta > 0,
  };
}

const drillCompany = ref<SoeCompany | null>(null);
</script>

<template>
  <div class="shb">
    <template v-if="data && pf">
      <!-- KPI-полоса (единая лента kpi-rail, как эталон Финансов) -->
      <div class="shb-band kpi-rail">
        <div class="shb-kpi" :style="{ '--accent': pf.zone?.color || '#7F77DD', '--d': '0ms' }">
          <div class="shb-lbl">Средний балл портфеля</div>
          <div class="shb-val">
            <Odometer :value="pf.avg != null ? pf.avg.toFixed(2) : '—'" />
            <span class="shb-u">из 5</span>
          </div>
          <div class="shb-sub">
            <span v-if="pf.zone" class="shb-zone-chip" :style="{ color: pf.zone.color, background: pf.zone.color + '1C' }">{{ pf.zone.label }}</span>
            <span v-else>—</span>
          </div>
        </div>

        <div class="shb-kpi" style="--accent:#7F77DD; --d:70ms">
          <div class="shb-lbl">Зоны риска</div>
          <div class="shb-zones">
            <span v-for="z in zones" :key="z.key" class="shb-zcount" :title="z.label"
                  :style="{ color: z.color, background: z.color + '16' }">
              <i :style="{ background: z.color }" />{{ pf.zone_counts[z.key] ?? 0 }}
            </span>
          </div>
          <div class="shb-sub">оценено {{ pf.scored_count }} из {{ pf.total_companies }}</div>
        </div>

        <div class="shb-kpi" style="--accent:#E24B4A; --d:140ms">
          <div class="shb-lbl">Требуют внимания</div>
          <div class="shb-names">
            <div v-for="w in pf.worst" :key="w.code" class="shb-name-row">
              <span class="shb-name">{{ w.name }}</span>
              <b :style="{ color: zoneByBand(Math.min(5, Math.round(w.overall)))?.color }">{{ w.overall.toFixed(1) }}</b>
            </div>
            <span v-if="!pf.worst.length" class="shb-dash">—</span>
          </div>
        </div>

        <div class="shb-kpi" style="--accent:#1D9E75; --d:210ms">
          <div class="shb-lbl">Наиболее устойчивые</div>
          <div class="shb-names">
            <div v-for="b in pf.best" :key="b.code" class="shb-name-row">
              <span class="shb-name">{{ b.name }}</span>
              <b style="color:#1D9E75">{{ b.overall.toFixed(1) }}</b>
            </div>
            <span v-if="!pf.best.length" class="shb-dash">—</span>
          </div>
        </div>
      </div>

      <!-- Легенда зон + методика -->
      <div class="shb-legend">
        <span v-for="z in zones" :key="z.key" class="shb-leg-chip" :style="{ color: z.color, background: z.color + '14' }">
          <i :style="{ background: z.color }" />{{ z.label }}
        </span>
        <span class="shb-leg-note">{{ data.methodology }} · {{ data.standard }} · FY {{ data.year }}</span>
      </div>

      <!-- Светофорная матрица -->
      <div class="shb-wrap">
        <table class="shb-tbl">
          <thead>
            <tr>
              <th class="shb-h-co">Компания</th>
              <th v-for="m in ratiosMeta" :key="m.key" class="shb-h" :title="m.formula + '\n' + fmtThr(m as never)">{{ m.label }}</th>
              <th class="shb-h shb-h-ov">Оценка</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, ci) in companies" :key="c.code" class="shb-row"
                :style="{ '--d': Math.min(ci * 26, 500) + 'ms' }"
                @click="drillCompany = c" :title="'Открыть детали: ' + (c.name || c.code)">
              <td class="shb-co">
                <span class="shb-co-dot" :style="{ background: c.sector_color || '#94A3B8' }" />
                <span class="shb-co-name">{{ c.name || c.code }}</span>
                <span v-if="deltaMeta(c)" class="shb-delta" :style="{ color: deltaMeta(c)!.color }"
                      :title="'Изменение балла к ' + (data.year - 1) + ' (ниже = лучше)'">
                  {{ deltaMeta(c)!.up ? '▲' : '▼' }}{{ deltaMeta(c)!.txt }}
                </span>
              </td>
              <td v-for="r in c.ratios" :key="r.key" class="shb-c">
                <span class="shb-pill" :title="cellTitle(r)"
                      :style="r.band != null
                        ? { color: zoneByBand(r.band).color, background: zoneByBand(r.band).color + '1C' }
                        : { color: '#B6BBC8', background: 'transparent' }">
                  {{ fmtVal(r) }}
                </span>
              </td>
              <td class="shb-c shb-ov">
                <span v-if="c.overall != null" class="shb-ov-chip"
                      :style="{ color: '#fff', background: c.zone?.color || '#94A3B8' }">
                  {{ c.overall.toFixed(1) }}
                </span>
                <span v-else class="shb-dash">н/д</span>
              </td>
            </tr>
            <tr v-if="!companies.length"><td :colspan="ratiosMeta.length + 2" class="shb-empty">Нет данных за {{ data.year }} ({{ data.standard }})</td></tr>
          </tbody>
        </table>
      </div>
    </template>

    <SoeHealthDrillModal
      :open="!!drillCompany"
      :company="drillCompany"
      :zones="zones"
      :year="data?.year ?? 0"
      :standard="data?.standard ?? ''"
      @close="drillCompany = null"
    />
  </div>
</template>

<style scoped>
.shb { display: flex; flex-direction: column; gap: 12px; }
.shb-state { padding: 40px; text-align: center; color: var(--t3, #94A3B8); font-size: 12.5px; }
.shb-err { color: #E24B4A; }

/* ── KPI-полоса ── */
.shb-band { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: 10px; }
@media (max-width: 900px) { .shb-band { grid-auto-flow: row; grid-template-columns: repeat(2, minmax(0, 1fr)); } }
.shb-kpi {
  position: relative; overflow: hidden; min-width: 0;
  background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px;
  padding: 14px clamp(10px, .9vw, 16px) 12px;
  display: flex; flex-direction: column; justify-content: space-between; min-height: 96px;
  animation: finKpiCardIn .55s var(--ease-standard, ease) var(--d, 0ms) both;
}
.shb-kpi::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD); border-radius: 14px 14px 0 0;
  animation: finKpi2DrawIn .8s var(--ease-standard) var(--d, 0ms) both; transform-origin: left center; }
.shb-lbl { font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94A3B8); margin-bottom: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shb-val { font-size: clamp(20px, 1.7vw, 28px); font-weight: 400; letter-spacing: -.04em; line-height: 1; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 5px; }
.shb-u { font-size: 11px; color: var(--t3, #94A3B8); }
.shb-sub { font-size: 11px; margin-top: 6px; color: var(--t3, #94A3B8); }
.shb-zone-chip { font-size: 10px; font-weight: 700; border-radius: 6px; padding: 2px 8px; letter-spacing: .02em; }
.shb-zones { display: flex; gap: 5px; flex-wrap: wrap; align-items: center; }
.shb-zcount { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 700; border-radius: 7px; padding: 3px 8px; font-variant-numeric: tabular-nums; }
.shb-zcount i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.shb-names { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.shb-name-row { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; font-size: 11.5px; }
.shb-name { color: var(--t2, #4B5468); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.shb-dash { color: #C4C8D4; }

/* ── Легенда ── */
.shb-legend { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; padding: 0 2px; }
.shb-leg-chip { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; font-weight: 600; border-radius: 7px; padding: 3px 9px; }
.shb-leg-chip i { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.shb-leg-note { margin-left: auto; font-size: 10.5px; color: var(--t3, #94A3B8); font-style: italic; }

/* ── Матрица ── */
.shb-wrap { overflow-x: auto; border: 1px solid rgba(0,0,0,.06); border-radius: 14px; background: var(--bg1, #fff); }
.shb-tbl { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 12px; }
.shb-tbl thead th {
  position: sticky; top: 0; z-index: 2; background: #F6F5FB; color: var(--p-deep, #534AB7);
  font-weight: 700; font-size: 9.5px; text-transform: uppercase; letter-spacing: .04em;
  padding: 8px 8px; text-align: center; border-bottom: 1px solid #E7E5F2; white-space: nowrap;
}
.shb-h-co { text-align: left !important; position: sticky; left: 0; z-index: 3 !important; min-width: 190px; }
.shb-h-ov { background: #EFEEF9 !important; }
.shb-row { cursor: pointer; transition: background .12s; animation: shbRowIn .4s var(--ease-standard, ease) var(--d, 0ms) both; }
@keyframes shbRowIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
.shb-row:hover td { background: rgba(127,119,221,.05); }
.shb-tbl td { border-bottom: 1px solid #F1F0F7; padding: 6px 6px; text-align: center; vertical-align: middle; }
.shb-co { position: sticky; left: 0; background: var(--bg1, #fff); text-align: left !important; padding: 6px 10px !important; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 230px; }
.shb-row:hover .shb-co { background: #FBFAFF; }
.shb-co-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; vertical-align: middle; }
.shb-co-name { font-size: 11.5px; font-weight: 500; color: var(--t1, #1E2A4A); }
.shb-delta { font-size: 9px; font-weight: 700; margin-left: 6px; font-variant-numeric: tabular-nums; }
.shb-pill {
  display: inline-block; min-width: 44px; padding: 3px 7px; border-radius: 7px;
  font-size: 10.5px; font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap;
  transition: transform .12s;
}
.shb-row:hover .shb-pill { transform: scale(1.05); }
.shb-ov-chip { display: inline-block; min-width: 40px; padding: 4px 9px; border-radius: 8px; font-size: 11.5px; font-weight: 700; font-variant-numeric: tabular-nums; box-shadow: 0 2px 8px rgba(15,23,60,.14); }
.shb-empty { padding: 28px; text-align: center; color: var(--t3, #94A3B8); }

@media (min-width: 2200px) {
  .shb-tbl { font-size: 14px; }
  .shb-tbl thead th { font-size: 11.5px; }
  .shb-co-name { font-size: 14px; }
  .shb-pill { font-size: 12.5px; min-width: 54px; }
}
</style>
