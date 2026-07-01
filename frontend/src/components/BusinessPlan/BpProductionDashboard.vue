<script setup lang="ts">
/**
 * BpProductionDashboard — вкладка «Производственные показатели» модуля Бизнес-план.
 * Свод исполнения производственного плана (натура + деньги, план→ожидаемое).
 * Честный расчёт исполнения приходит с бэка (3-state + execBasis money/natura);
 * фронт красит зоны (overpar>110 — отдельная зона, не «успех»).
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { useCountUpScan } from "@/composables/useCountUp";
import { usePermissions } from "@/composables/usePermissions";
import { useProductionData } from "@/composables/useProductionData";
import type { ProdCompany } from "@/api/production";

const emit = defineEmits<{
  (e: "drill", p: { company: ProdCompany; year: number; period: string }): void;
  (e: "edit", p: { company: ProdCompany; year: number; period: string }): void;
  (e: "import"): void;
}>();
function ctx(c: ProdCompany) { return { company: c, year: st.year.value, period: st.period.value }; }

const perm = usePermissions("bp");
const canEdit = perm.canEdit;

const st = useProductionData();

const PERIOD_OPTS = [
  { value: "h1", label: "1 полугодие" },
  { value: "h2", label: "2 полугодие" },
  { value: "annual", label: "Год" },
];

onMounted(async () => {
  await st.loadAvailable();
  await st.load();
});

// ─── formatting ───────────────────────────────────────────────
function fmtMlrd(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  return Math.round(v).toLocaleString("ru", { maximumFractionDigits: 0 }).replace(/ /g, " ");
}
function fmtTrln(v: number | null | undefined): number {
  if (v == null || !isFinite(v)) return 0;
  return Math.round(v / 100) / 10; // млрд → трлн, 1 знак
}
function fmtNat(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const abs = Math.abs(v);
  const d = abs >= 1000 ? 0 : abs >= 10 ? 1 : 2;
  return v.toLocaleString("ru", { maximumFractionDigits: d }).replace(/ /g, " ");
}

// ─── execution zones (mirror forensic pctCol/pctZone) ─────────
function pctCol(p: number | null | undefined): string {
  if (p == null) return "var(--t3, #94A3B8)";
  if (p > 110) return "#7C3AED";      // переисполнение — отдельная зона
  if (p >= 90) return "#1D9E75";      // норма
  if (p >= 75) return "#D97706";      // отставание
  return "#993D3D";                    // критично
}
function pctZone(p: number | null | undefined): string {
  if (p == null) return "";
  if (p > 110) return "переисполнение — проверить единицы/двойной ввод";
  if (p >= 90) return "в норме";
  if (p >= 75) return "отставание";
  return "критично";
}

// ─── derived ──────────────────────────────────────────────────
const companies = computed(() => st.data.value?.companies || []);
const kpis = computed(() => st.data.value?.kpis || null);

// bar chart data: top companies by expected money volume
const chartRows = computed(() => {
  const rows = companies.value.filter((c) => (c.expM != null || c.planM != null));
  const max = Math.max(1, ...rows.map((c) => Math.max(c.planM || 0, c.expM || 0)));
  return rows
    .slice()
    .sort((a, b) => (b.expM || b.planM || 0) - (a.expM || a.planM || 0))
    .slice(0, 10)
    .map((c) => ({ c, planW: ((c.planM || 0) / max) * 100, expW: ((c.expM || 0) / max) * 100 }));
});

// ─── count-up ─────────────────────────────────────────────────
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 50, stagger: 70 });
watch(() => st.data.value, async () => { await nextTick(); rescan(); });
</script>

<template>
  <div class="pd">
    <!-- ═══ Control row ═══ -->
    <div class="pd-ctrl">
      <UzaSegment :options="PERIOD_OPTS" :model-value="st.period.value"
                  @update:model-value="(v) => st.setPeriod(v as string)" label="Период" />
      <UzaYearStepper :years="st.availableYears.value" :model-value="st.year.value"
                      @update:model-value="(v) => st.setYear(v)" prefix="FY " label="Год" />
      <div class="pd-ctrl-sp" />
      <button v-if="canEdit" class="pd-btn" @click="emit('import')" title="Импорт из Excel">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>
        Импорт
      </button>
    </div>

    <UzaStateBlock v-if="st.loading.value && !st.data.value" state="loading" variant="text" loadingText="Загрузка…" />
    <UzaStateBlock v-else-if="st.error.value" state="error" variant="block" :text="st.error.value" />
    <UzaStateBlock v-else-if="st.data.value && !companies.length" state="empty" variant="block"
                   text="Нет производственных данных. Импортируйте «Свод бизнес-плана» через кнопку «Импорт»." />

    <div v-else-if="kpis" ref="scanRoot" class="pd-body">
      <!-- ═══ KPI strip ═══ -->
      <div class="pd-kpi-rail kpi-rail">
        <div class="kpi2 fin-shimmer" :style="{ '--kpi2-accent': pctCol(kpis.exec_pct), '--kpi2-d': '0ms' }">
          <div class="kpi2-lbl">Сводное исполнение</div>
          <div class="kpi2-val" :style="{ color: pctCol(kpis.exec_pct) }">
            <span :data-countup="kpis.exec_pct ?? 0">{{ kpis.exec_pct ?? 0 }}</span><span class="pd-pct">%</span>
          </div>
          <div class="kpi2-sub">ожидаемое / план (деньги)</div>
        </div>
        <div class="kpi2 fin-shimmer" style="--kpi2-accent:#7F77DD; --kpi2-d:80ms">
          <div class="kpi2-lbl">План выпуска</div>
          <div class="kpi2-val"><span :data-countup="fmtTrln(kpis.plan_total)">{{ fmtTrln(kpis.plan_total) }}</span></div>
          <div class="kpi2-sub">трлн сум</div>
        </div>
        <div class="kpi2 fin-shimmer" style="--kpi2-accent:#1D9E75; --kpi2-d:160ms">
          <div class="kpi2-lbl">Ожидаемое</div>
          <div class="kpi2-val"><span :data-countup="fmtTrln(kpis.expect_total)">{{ fmtTrln(kpis.expect_total) }}</span></div>
          <div class="kpi2-sub">трлн сум</div>
        </div>
        <div class="kpi2 fin-shimmer" style="--kpi2-accent:#378ADD; --kpi2-d:240ms">
          <div class="kpi2-lbl">Покрытие данными</div>
          <div class="kpi2-val">
            <span :data-countup="kpis.with_data">{{ kpis.with_data }}</span><span class="pd-of"> / {{ kpis.present }}</span>
          </div>
          <div class="kpi2-sub" v-if="kpis.overpar">⚑ переисполнение: {{ kpis.overpar }}</div>
          <div class="kpi2-sub" v-else>компаний с данными</div>
        </div>
      </div>

      <!-- ═══ Two-col: table + chart ═══ -->
      <div class="pd-grid">
        <!-- Company table -->
        <div class="pd-card">
          <div class="pd-card-h">
            <span class="pd-card-t">Свод по компаниям</span>
            <span class="pd-card-meta">{{ companies.length }} компаний · млрд UZS</span>
          </div>
          <div class="pd-tbl-wrap">
            <table class="pd-tbl">
              <thead>
                <tr>
                  <th class="lt">Компания</th>
                  <th class="rt">План</th>
                  <th class="rt">Ожид.</th>
                  <th class="rt">Темп</th>
                  <th class="rt">Исполнение</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(c, i) in companies" :key="c.k"
                    class="pd-row" :class="{ 'no-data': !c.has_data }"
                    :style="{ animationDelay: (Math.min(i, 24) * 22) + 'ms' }"
                    @click="c.has_data ? emit('drill', ctx(c)) : (canEdit ? emit('edit', ctx(c)) : null)"
                    :title="c.has_data ? 'Открыть детализацию' : (canEdit ? 'Заполнить данные' : 'Нет данных')">
                  <td class="lt">
                    <CompanyAvatar :name="c.n" :color="c.sector_color || '#888780'" :size="20" />
                    <span class="pd-co-name">{{ c.n }}</span>
                  </td>
                  <td class="rt num muted">{{ fmtMlrd(c.planM) }}</td>
                  <td class="rt num muted">{{ fmtMlrd(c.expM) }}</td>
                  <td class="rt num" :style="{ color: c.growthPct != null && c.growthPct >= 100 ? '#1D9E75' : 'var(--t3,#94A3B8)' }">
                    {{ c.growthPct != null ? c.growthPct + '%' : '—' }}
                  </td>
                  <td class="rt num" :style="{ color: pctCol(c.execPct), fontWeight: 600 }" :title="pctZone(c.execPct)">
                    <template v-if="c.execState === 'pct'">
                      {{ c.execPct }}%<span v-if="c.execBasis === 'natura'" class="pd-basis" title="по натуральному объёму">н</span>
                    </template>
                    <span v-else-if="c.execState === 'nofact'" class="pd-nd">факт —</span>
                    <span v-else class="pd-nd">нет данных</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Bar chart: plan vs expected -->
        <div class="pd-card">
          <div class="pd-card-h">
            <span class="pd-card-t">План vs Ожидаемое</span>
            <span class="pd-card-legend">
              <span class="pd-lg"><i style="background:#C7C2F0" /> план</span>
              <span class="pd-lg"><i style="background:#7F77DD" /> ожид.</span>
            </span>
          </div>
          <div class="pd-chart">
            <div v-for="(r, i) in chartRows" :key="r.c.k" class="pd-bar-row"
                 :style="{ animationDelay: (i * 45) + 'ms' }" @click="emit('drill', ctx(r.c))">
              <span class="pd-bar-name">{{ r.c.n }}</span>
              <div class="pd-bar-track">
                <div class="pd-bar plan" :style="{ width: r.planW + '%' }" />
                <div class="pd-bar exp" :style="{ width: r.expW + '%', background: pctCol(r.c.execPct) }" />
              </div>
              <span class="pd-bar-pct" :style="{ color: pctCol(r.c.execPct) }">
                {{ r.c.execPct != null ? r.c.execPct + '%' : '—' }}
              </span>
            </div>
            <div v-if="!chartRows.length" class="pd-chart-empty">Нет числовых данных для графика</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pd { display: flex; flex-direction: column; }
.pd-ctrl {
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 12px 20px; border-bottom: 0.5px solid var(--border-hard, rgba(0,0,0,.06));
}
.pd-ctrl-sp { flex: 1; }
.pd-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 13px; border-radius: 8px; border: 1px solid var(--border-input, #E2E8F0);
  background: var(--bg1, #fff); color: var(--p-deep, #534AB7);
  font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer;
  transition: all .13s;
}
.pd-btn:hover { border-color: #7C6FF7; background: rgba(124,111,247,.06); }

.pd-body { padding: 16px 20px 24px; }

.pd-kpi-rail {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px;
}
@media (max-width: 1100px) { .pd-kpi-rail { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px)  { .pd-kpi-rail { grid-template-columns: 1fr; } }
.pd-pct { font-size: 18px; color: var(--t3, var(--t-muted)); font-weight: 400; margin-left: 1px; }
.pd-of { font-size: 16px; color: var(--t3, var(--t-muted)); font-weight: 500; }

.pd-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 12px; }
@media (max-width: 1200px) { .pd-grid { grid-template-columns: 1fr; } }

.pd-card {
  background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05); border-radius: 12px;
  overflow: hidden; display: flex; flex-direction: column;
  animation: pdCardIn .5s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both;
}
@keyframes pdCardIn { 0% { opacity: 0; transform: translateY(10px) scale(.99); } 100% { opacity: 1; transform: none; } }
.pd-card-h {
  padding: 12px 16px; border-bottom: 0.5px solid rgba(0,0,0,.06);
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.pd-card-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); text-transform: uppercase; letter-spacing: .04em; }
.pd-card-meta { font-size: 11px; color: var(--t3, var(--t-muted)); }
.pd-card-legend { display: flex; gap: 12px; font-size: 11px; color: var(--t3, var(--t-muted)); }
.pd-lg { display: inline-flex; align-items: center; gap: 5px; }
.pd-lg i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }

/* Table */
.pd-tbl-wrap { max-height: 460px; overflow-y: auto; scrollbar-width: thin; }
.pd-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pd-tbl thead th {
  position: sticky; top: 0; z-index: 1;
  background: var(--bg2, #FAFAFC);
  padding: 8px 12px; font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .05em; color: var(--t3, var(--t-muted));
  border-bottom: 0.5px solid rgba(0,0,0,.05);
}
.pd-tbl th.lt { text-align: left; }
.pd-tbl th.rt { text-align: right; }
.pd-tbl tbody td { padding: 7px 12px; border-bottom: 0.5px solid rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }
.pd-tbl td.lt { display: flex; align-items: center; gap: 7px; }
.pd-tbl td.rt { text-align: right; }
.pd-tbl td.num { font-feature-settings: 'tnum'; }
.pd-tbl td.muted { color: var(--t3, var(--t-muted)); }
.pd-co-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 500; }
.pd-row { cursor: pointer; transition: background .12s; animation: pdRowIn .3s cubic-bezier(.34,1.1,.64,1) both; }
@keyframes pdRowIn { 0% { opacity: 0; transform: translateX(-4px); } 100% { opacity: 1; transform: none; } }
.pd-row:hover { background: rgba(127,119,221,.05); }
.pd-row.no-data { opacity: .6; }
.pd-nd { color: var(--t3, var(--t-muted)); font-style: italic; font-weight: 400; font-size: 11px; }
.pd-basis { font-size: 9px; vertical-align: super; margin-left: 1px; color: var(--t3, var(--t-muted)); }

/* Chart */
.pd-chart { padding: 12px 16px; overflow-y: auto; max-height: 460px; scrollbar-width: thin; }
.pd-bar-row {
  display: grid; grid-template-columns: 120px 1fr 44px; align-items: center; gap: 10px;
  padding: 5px 0; cursor: pointer; animation: pdRowIn .3s cubic-bezier(.34,1.1,.64,1) both;
}
.pd-bar-name { font-size: 11.5px; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pd-bar-track { position: relative; height: 16px; }
.pd-bar {
  position: absolute; left: 0; height: 7px; border-radius: 4px;
  animation: pdBarPour .5s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both;
  transform-origin: left center;
}
.pd-bar.plan { top: 0; background: #C7C2F0; }
.pd-bar.exp { top: 9px; }
@keyframes pdBarPour { 0% { transform: scaleX(0); opacity: 0; } 100% { transform: scaleX(1); opacity: 1; } }
.pd-bar-pct { font-size: 11.5px; font-weight: 600; text-align: right; font-feature-settings: 'tnum'; }
.pd-chart-empty { padding: 30px; text-align: center; font-size: 12px; color: var(--t3, var(--t-muted)); font-style: italic; }
</style>
