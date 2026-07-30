<script setup lang="ts">
/** ExecDashProductionBlock — производственное исполнение (H1) в министерском дашборде.
 *  Независимый fetch /production/overview (как FinanceBlock/KpiBlock). Сводное
 *  исполнение, план→ожидаемое, лидеры/отстающие, покрытие. Клик → вкладка БП. */
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { useNumberTween } from "@/composables/useNumberTween";
import { productionApi, type ProdOverview, type ProdCompany } from "@/api/production";

const { t } = useI18n();
const exec = useExecutiveDashboard();
const router = useRouter();

const data = ref<ProdOverview | null>(null);
const loading = ref(false);
const failed = ref(false);
let seq = 0;

async function load() {
  loading.value = true; failed.value = false;
  const my = ++seq;
  try {
    const d = await productionApi.overview(exec.year.value, "h1");
    if (my !== seq) return;
    data.value = d;
  } catch {
    if (my !== seq) return;
    failed.value = true; data.value = null;
  } finally { if (my === seq) loading.value = false; }
}
onMounted(load);
watch(() => exec.year.value, load);

const kpis = computed(() => data.value?.kpis || null);
const hasData = computed(() => !!kpis.value && kpis.value.with_data > 0);
const execPct = computed(() => kpis.value?.exec_pct ?? null);

const tExec = useNumberTween(() => Number(execPct.value) || 0, { duration: 900 });
const tPlan = useNumberTween(() => (kpis.value ? kpis.value.plan_total / 100 : 0), { duration: 900 });
const tExp = useNumberTween(() => (kpis.value ? kpis.value.expect_total / 100 : 0), { duration: 900 });

function pctCol(p: number | null): string {
  if (p == null) return "#94A3B8";
  if (p > 110) return "#7C3AED"; if (p >= 90) return "#1D9E75"; if (p >= 75) return "#EF9F27"; return "#E24B4A";
}
function pctZone(p: number | null): string {
  if (p == null) return t("нет данных");
  if (p > 110) return t("переисполнение"); if (p >= 90) return t("в норме"); if (p >= 75) return t("отставание"); return t("критично");
}
const withPct = computed(() => (data.value?.companies || []).filter((c) => c.execPct != null && c.has_data));
const leaders = computed(() => withPct.value.slice().sort((a, b) => (b.execPct || 0) - (a.execPct || 0)).slice(0, 3));
const laggards = computed(() => withPct.value.slice().sort((a, b) => (a.execPct || 0) - (b.execPct || 0)).slice(0, 3));

function fmt1(v: number) { return (Math.round(v * 10) / 10).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 1 }); }
function go() { router.push({ path: "/business-plan", query: { tab: "production" } }); }
function coLabel(c: ProdCompany) { return c.n; }
</script>

<template>
  <section class="edp" :style="{ '--edp-accent': pctCol(execPct) }" @click="go" :title="t('Открыть вкладку «Производственные показатели»')">
    <div class="edp-head">
      <div>
        <div class="edp-eyebrow">{{ t("Производственный план · FY {y} · 1 полугодие", { y: exec.year.value }) }}</div>
        <div class="edp-title">{{ t("Исполнение производственного плана") }}</div>
      </div>
      <svg class="edp-go" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
    </div>

    <div v-if="loading && !data" class="edp-state">{{ t("Загрузка…") }}</div>
    <div v-else-if="failed" class="edp-state">{{ t("Нет доступа к производственным данным") }}</div>
    <div v-else-if="!hasData" class="edp-state">{{ t("Производственные данные не заведены — импортируйте «Свод» во вкладке БП") }}</div>

    <template v-else>
      <div class="edp-hero">
        <div class="edp-big">
          <span class="edp-big-v" :style="{ color: pctCol(execPct) }">{{ Math.round(tExec) }}</span><span class="edp-big-p">%</span>
        </div>
        <div class="edp-hero-r">
          <div class="edp-zone" :style="{ color: pctCol(execPct) }">{{ pctZone(execPct) }}</div>
          <div class="edp-flow">
            <span class="edp-flow-v">{{ fmt1(tPlan) }}</span><span class="edp-flow-u"> {{ t("трлн план") }}</span>
            <svg width="16" height="12" viewBox="0 0 24 16" fill="none" stroke="#94A3B8" stroke-width="2" stroke-linecap="round"><path d="M3 8h16M14 3l5 5-5 5"/></svg>
            <span class="edp-flow-v" :style="{ color: pctCol(execPct) }">{{ fmt1(tExp) }}</span><span class="edp-flow-u"> {{ t("ожид.") }}</span>
          </div>
          <div class="edp-cov">{{ t("Покрытие:") }} <b>{{ kpis!.with_data }}</b> / {{ kpis!.present }} {{ t("компаний") }}
            <span v-if="kpis!.overpar" class="edp-overpar">· ⚑ {{ t("переисполнение") }}: {{ kpis!.overpar }}</span>
          </div>
        </div>
      </div>

      <div class="edp-leaders">
        <div class="edp-col">
          <div class="edp-col-l">{{ t("Лидеры") }}</div>
          <div v-for="c in leaders" :key="c.k" class="edp-lrow">
            <span class="edp-dot" :style="{ background: c.sector_color }" />
            <span class="edp-lname">{{ t(coLabel(c)) }}</span>
            <span class="edp-lpct" :style="{ color: pctCol(c.execPct ?? null) }">{{ c.execPct }}%</span>
          </div>
        </div>
        <div class="edp-col">
          <div class="edp-col-l">{{ t("Отстающие") }}</div>
          <div v-for="c in laggards" :key="c.k" class="edp-lrow">
            <span class="edp-dot" :style="{ background: c.sector_color }" />
            <span class="edp-lname">{{ t(coLabel(c)) }}</span>
            <span class="edp-lpct" :style="{ color: pctCol(c.execPct ?? null) }">{{ c.execPct }}%</span>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.edp {
  background: rgba(255, 255, 255, .82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255, 255, 255, .70); border-radius: 16px; padding: 16px 18px 14px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, .07); position: relative; overflow: hidden; cursor: pointer;
  transition: transform .2s, box-shadow .2s, border-color .2s;
}
.edp:hover { transform: translateY(-3px) scale(1.005); box-shadow: 0 12px 32px rgba(15,23,60,.12); border-color: rgba(124,111,247,.25); }

.edp-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.edp-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.edp-title { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); margin-top: 3px; }
.edp-go { color: var(--t3, #94A3B8); flex-shrink: 0; transition: transform .15s, color .15s; }
.edp:hover .edp-go { color: var(--p-deep, #534AB7); transform: translateX(2px); }
.edp-state { padding: 20px 0 6px; font-size: 12.5px; color: var(--t3, var(--t-muted)); font-style: italic; }

.edp-hero { display: flex; align-items: center; gap: 20px; margin: 12px 0 14px; flex-wrap: wrap; }
.edp-big { display: flex; align-items: baseline; line-height: 1; }
.edp-big-v { font-size: 52px; font-weight: 400; letter-spacing: -.03em; font-feature-settings: 'tnum'; }
.edp-big-p { font-size: 24px; font-weight: 400; color: var(--t3, var(--t-muted)); margin-left: 2px; }
.edp-hero-r { flex: 1; min-width: 220px; display: flex; flex-direction: column; gap: 4px; }
.edp-zone { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; }
.edp-flow { display: flex; align-items: center; gap: 5px; font-feature-settings: 'tnum'; }
.edp-flow-v { font-size: 17px; font-weight: 500; color: var(--t1, #1E2A4A); }
.edp-flow-u { font-size: 11px; color: var(--t3, var(--t-muted)); }
.edp-cov { font-size: 11.5px; color: var(--t3, var(--t-muted)); }
.edp-cov b { color: var(--t1, #1E2A4A); font-weight: 600; }
.edp-overpar { color: #7C3AED; font-weight: 600; }

.edp-leaders { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; border-top: 0.5px solid rgba(0,0,0,.06); padding-top: 10px; }
.edp-col-l { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted)); margin-bottom: 5px; }
.edp-lrow { display: flex; align-items: center; gap: 7px; padding: 2px 0; }
.edp-dot { width: 7px; height: 7px; border-radius: 2px; flex-shrink: 0; }
.edp-lname { flex: 1; font-size: 12px; color: var(--t1, #1E2A4A); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.edp-lpct { font-size: 12px; font-weight: 600; font-feature-settings: 'tnum'; }
@media (max-width: 560px) { .edp-leaders { grid-template-columns: 1fr; } }
</style>
