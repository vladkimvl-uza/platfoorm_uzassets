<script setup lang="ts">
/**
 * UnitCostDashboard — «Удельная себестоимость» (сайдбар Финансы).
 * Себестоимость продукции по компаниям: энергозатраты (норма×цена) + прочие
 * статьи, на единицу продукции. KPI-полоса, цены энергоносителей, список
 * компаний со сводкой, дрилл-редактор продуктов. Премиум UX.
 */
import { computed, inject, onMounted, ref } from "vue";
import { usePermissions } from "@/composables/usePermissions";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import Odometer from "@/components/Odometer.vue";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";
import { unitCostApi, type UCOverview, type UCCompany } from "@/api/unitCost";
import UnitCostCompanyModal from "@/components/UnitCost/UnitCostCompanyModal.vue";
import UnitCostPricesModal from "@/components/UnitCost/UnitCostPricesModal.vue";

const finPerm = usePermissions("financials");
const toggleSidebar = inject<() => void>("toggleSidebar", () => {});
const openMobileSidebar = inject<() => void>("openMobileSidebar", () => {});
function onBurger() {
  if (typeof window !== "undefined" && window.innerWidth <= 1023) openMobileSidebar();
  else toggleSidebar();
}

const data = ref<UCOverview | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);

async function load() {
  loading.value = true; error.value = null;
  try {
    data.value = await unitCostApi.overview();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally { loading.value = false; }
}
onMounted(() => { ensureFinancialsCss(); load(); });

const pf = computed(() => data.value?.portfolio || null);
const companies = computed(() => data.value?.companies || []);
const pricesOpen = ref(false);
const editCompany = ref<UCCompany | null>(null);

function fmtSum(v: number | null): string {
  if (v == null) return "—";
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toLocaleString("ru", { maximumFractionDigits: 1 }) + " трлн";
  if (a >= 1e3) return (v / 1e3).toLocaleString("ru", { maximumFractionDigits: 1 }) + " млрд";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 }) + " млн";
}
const priceRows = computed(() => {
  const p = data.value?.energyPrices || {}; const lbl = data.value?.fuel_labels || {};
  return Object.keys(lbl).filter((f) => p[f]).map((f) => ({
    fuel: f, label: lbl[f], price: p[f].price, unit: p[f].unit,
  }));
});
function shareColor(s: number | null): string {
  if (s == null) return "#9AA0AE";
  if (s >= 60) return "#E24B4A";
  if (s >= 35) return "#EF9F27";
  return "#1D9E75";
}

// мировые ориентиры (тикер + влияют на цены в USD)
const world = computed(() => data.value?.world || null);
function fmtNum(v: number | null | undefined, d = 0): string {
  return v == null ? "—" : Number(v).toLocaleString("ru", { maximumFractionDigits: d });
}

// графики
const FUEL_PAL: Record<string, string> = {
  electricity: "#EF9F27", gas: "#378ADD", diesel: "#E24B4A",
  mazut: "#8B7FFF", coal: "#4B5468", kerosene: "#1D9E75",
};
const mixDonut = computed<DonutEntry[]>(() =>
  (data.value?.energy_mix || []).map((m) => ({
    label: m.label, color: FUEL_PAL[m.fuel] || "#7F77DD", value: m.cost, sub: fmtSum(m.cost),
  })),
);
const mixTotal = computed(() => (data.value?.energy_mix || []).reduce((a, m) => a + m.cost, 0));
const structDonut = computed<DonutEntry[]>(() => {
  const p = pf.value; if (!p) return [];
  const out: DonutEntry[] = [];
  if (p.energy_cost) out.push({ label: "Энергозатраты", color: "#EF9F27", value: p.energy_cost, sub: fmtSum(p.energy_cost) });
  if (p.components_cost && p.components_cost > 0) out.push({ label: "Прочие статьи", color: "#7F77DD", value: p.components_cost, sub: fmtSum(p.components_cost) });
  return out;
});
function donutHover(e: DonutEntry, total: number): [string, string] {
  return [e.sub || String(e.value), total ? Math.round((e.value / total) * 100) + "%" : ""];
}
</script>

<template>
  <div class="uc-page">
    <!-- Топбар в стиле financials -->
    <header class="uc-bar">
      <button class="uc-burger" @click="onBurger()" title="Меню / свернуть сайдбар">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
          <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
        </svg>
      </button>
      <div class="uc-head">
        <div class="uc-eyebrow">ФИНАНСЫ · СЕБЕСТОИМОСТЬ</div>
        <div class="uc-title-row">
          <span class="uc-title">Удельная себестоимость</span>
          <span class="uc-sub">энергозатраты + статьи на единицу продукции · FY 2025</span>
        </div>
      </div>
      <div class="uc-cluster">
        <div v-if="world" class="uc-ticker" title="Курс и мировые ориентиры — влияют на цены в USD (правятся в редакторе)">
          <span class="uc-tk"><b>USD</b>{{ fmtNum(world.usd_rate) }}</span>
          <span class="uc-tk"><b>Brent</b>${{ fmtNum(world.brent, 1) }}</span>
          <span class="uc-tk"><b>Gold</b>${{ fmtNum(world.gold) }}</span>
          <span class="uc-tk"><b>Cu</b>${{ fmtNum(world.copper) }}</span>
        </div>
        <button v-if="finPerm.canEdit.value" class="uc-prices-btn" type="button" @click="pricesOpen = true"
                title="Цены энергоносителей и мировые ориентиры">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
          Цены и курсы
        </button>
      </div>
    </header>

    <div v-if="loading && !data" class="uc-state">
      <div class="uc-skel" v-for="i in 3" :key="i" :style="{ '--d': (i * 90) + 'ms' }" />
    </div>
    <div v-else-if="error && !data" class="uc-state uc-err">
      {{ error }} <button class="uc-retry" type="button" @click="load">Повторить</button>
    </div>

    <template v-else-if="data && pf">
      <!-- KPI-полоса -->
      <section class="uc-section">
        <div class="uc-kpi-band kpi-rail">
          <div class="uc-kpi" style="--accent:#7F77DD; --d:0ms;">
            <div class="uc-kpi-l">Совокупная себестоимость</div>
            <div class="uc-kpi-v">{{ fmtSum(pf.total_cost) }}</div>
            <div class="uc-kpi-s">по заполненному выпуску</div>
          </div>
          <div class="uc-kpi" style="--accent:#EF9F27; --d:80ms;">
            <div class="uc-kpi-l">Энергозатраты</div>
            <div class="uc-kpi-v">{{ fmtSum(pf.energy_cost) }}</div>
            <div class="uc-kpi-s">из совокупной</div>
          </div>
          <div class="uc-kpi" style="--accent:#E24B4A; --d:160ms;">
            <div class="uc-kpi-l">Доля энергии</div>
            <div class="uc-kpi-v">
              <span v-if="pf.energy_share != null"><Odometer :value="pf.energy_share.toFixed(1)" /><span class="uc-kpi-u">%</span></span>
              <span v-else>—</span>
            </div>
            <div class="uc-kpi-s">энергоёмкость портфеля</div>
          </div>
          <div class="uc-kpi" style="--accent:#1D9E75; --d:240ms;">
            <div class="uc-kpi-l">Заполнено продуктов</div>
            <div class="uc-kpi-v">{{ pf.priced_count }}<span class="uc-kpi-u">/ {{ pf.product_count }}</span></div>
            <div class="uc-kpi-s">{{ pf.company_count }} компаний</div>
          </div>
        </div>
      </section>

      <!-- Цены энергоносителей -->
      <section v-if="priceRows.length" class="uc-section">
        <div class="uc-card">
          <div class="uc-card-hd">
            <div>
              <div class="uc-card-t">Цены энергоносителей</div>
              <div class="uc-card-s">применяются ко всем компаниям · клик «Цены…» для правки</div>
            </div>
          </div>
          <div class="uc-prices">
            <div v-for="(p, i) in priceRows" :key="p.fuel" class="uc-price" :style="{ '--d': (i * 50) + 'ms' }">
              <div class="uc-price-l">{{ p.label }}</div>
              <div class="uc-price-v">{{ p.price.toLocaleString("ru") }}</div>
              <div class="uc-price-u">{{ p.unit }}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Графики: энергомикс + структура -->
      <section v-if="mixDonut.length || structDonut.length" class="uc-section uc-2col">
        <div v-if="mixDonut.length" class="uc-card">
          <div class="uc-card-hd"><div>
            <div class="uc-card-t">Энергомикс портфеля</div>
            <div class="uc-card-s">доля видов топлива в энергозатратах</div>
          </div></div>
          <CreditDonut :entries="mixDonut" :center-value="fmtSum(mixTotal)" center-label="энергия"
            :hover-fmt="donutHover" :size="150" />
        </div>
        <div v-if="structDonut.length" class="uc-card">
          <div class="uc-card-hd"><div>
            <div class="uc-card-t">Структура себестоимости</div>
            <div class="uc-card-s">энергозатраты и прочие статьи</div>
          </div></div>
          <CreditDonut :entries="structDonut" :center-value="fmtSum(pf!.total_cost)" center-label="итого"
            :hover-fmt="donutHover" :size="150" />
        </div>
      </section>

      <!-- Компании -->
      <section class="uc-section">
        <div class="uc-card">
          <div class="uc-card-hd">
            <div>
              <div class="uc-card-t">Себестоимость по компаниям</div>
              <div class="uc-card-s">клик по компании — продукты и статьи · доля энергии в цвете</div>
            </div>
          </div>
          <div class="uc-cos">
            <div class="uc-cos-head">
              <span>Компания</span><span>Продуктов</span><span>Себестоимость</span>
              <span>Энергозатраты</span><span>Доля энергии</span>
            </div>
            <button v-for="(c, i) in companies" :key="c.code" type="button" class="uc-co"
                    :style="{ '--d': Math.min(i * 24, 400) + 'ms' }"
                    :title="'Редактировать: ' + c.name" @click="editCompany = c">
              <span class="uc-co-name"><i :style="{ background: c.color }" />{{ c.name }}</span>
              <span class="uc-co-n">{{ c.priced_count }}<span class="uc-co-nn">/{{ c.product_count }}</span></span>
              <span class="uc-co-cost">{{ fmtSum(c.total_cost) }}</span>
              <span class="uc-co-en">{{ fmtSum(c.energy_cost) }}</span>
              <span class="uc-co-share">
                <span v-if="c.energy_share != null" class="uc-share-chip"
                      :style="{ color: shareColor(c.energy_share), background: shareColor(c.energy_share) + '16' }">
                  {{ c.energy_share.toFixed(0) }}%
                </span>
                <span v-else class="uc-dash">н/д</span>
              </span>
            </button>
          </div>
        </div>
      </section>
    </template>

    <UnitCostCompanyModal
      :open="!!editCompany"
      :company="editCompany"
      :prices="data?.energyPrices || {}"
      :world="data?.world || null"
      :fuel-labels="data?.fuel_labels || {}"
      @close="editCompany = null"
      @saved="editCompany = null; load()"
    />
    <UnitCostPricesModal
      :open="pricesOpen"
      :prices="data?.energyPrices || {}"
      :world="data?.world || null"
      :fuel-labels="data?.fuel_labels || {}"
      @close="pricesOpen = false"
      @saved="pricesOpen = false; load()"
    />
  </div>
</template>

<style scoped>
.uc-page { padding: 0 0 32px; display: flex; flex-direction: column; gap: 12px; }
.uc-section { margin: 0 14px; animation: finFadeSlideIn .4s ease both; }

/* Топбар — 1:1 financials */
.uc-bar { display: flex; align-items: center; gap: 14px; row-gap: 10px; flex-wrap: wrap; padding: 10px 16px;
  min-height: 52px; background: linear-gradient(180deg, #1E2A4A 0%, #182039 100%); color: #fff;
  border-radius: 0 12px 12px 0; box-shadow: 0 4px 14px rgba(15,23,60,.15); }
.uc-burger { width: 34px; height: 34px; border-radius: 8px; flex-shrink: 0; border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.08); color: rgba(255,255,255,.85); cursor: pointer; display: inline-flex;
  align-items: center; justify-content: center; transition: background .15s; }
.uc-burger:hover { background: rgba(255,255,255,.14); }
.uc-head { flex: 1 1 280px; min-width: 0; display: flex; flex-direction: column; gap: 1px; overflow: hidden; }
.uc-eyebrow { font-size: 10px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: rgba(255,255,255,.55); }
.uc-title-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; row-gap: 2px; }
.uc-title { font-size: 19px; font-weight: 500; letter-spacing: -.01em; color: #fff; }
.uc-sub { font-size: 12px; color: rgba(255,255,255,.65); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.uc-cluster { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.uc-prices-btn { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600;
  font-family: inherit; color: rgba(255,255,255,.88); background: rgba(255,255,255,.08);
  border: 1px solid rgba(255,255,255,.16); border-radius: 9px; padding: 7px 13px; cursor: pointer; transition: all .15s; }
.uc-prices-btn:hover { background: rgba(255,255,255,.15); transform: translateY(-1px); }
.uc-ticker { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.uc-tk { font-size: 11.5px; font-weight: 600; color: rgba(255,255,255,.9); font-variant-numeric: tabular-nums; white-space: nowrap;
  padding: 3px 9px; border-radius: 7px; background: rgba(255,255,255,.06); }
.uc-tk b { font-size: 8.5px; font-weight: 700; color: rgba(255,255,255,.5); text-transform: uppercase; letter-spacing: .04em; margin-right: 5px; }
.uc-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .uc-2col { grid-template-columns: 1fr; } }

.uc-state { display: flex; flex-direction: column; gap: 10px; margin: 0 14px; }
.uc-skel { height: 92px; border-radius: 14px; background: linear-gradient(90deg,#F1F0F7 25%,#FAF9FE 50%,#F1F0F7 75%);
  background-size: 200% 100%; animation: ucShimmer 1.4s ease-in-out var(--d,0ms) infinite; }
@keyframes ucShimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.uc-err { flex-direction: row; align-items: center; gap: 12px; color: #E24B4A; font-size: 12.5px; }
.uc-retry { font-size: 12px; font-weight: 600; font-family: inherit; border: 1px solid #E5E7EB; background: #fff; border-radius: 9px; padding: 6px 14px; cursor: pointer; }

/* KPI */
.uc-kpi-band { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
@media (max-width: 1100px) { .uc-kpi-band { grid-template-columns: 1fr 1fr; } }
.uc-kpi { background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5); border-radius: 14px;
  padding: 14px 16px 12px; border: 1px solid rgba(255,255,255,.70);
  box-shadow: 0 2px 12px rgba(15,23,60,.07),0 1px 3px rgba(15,23,60,.04); position: relative; overflow: hidden;
  min-height: 92px; display: flex; flex-direction: column; justify-content: space-between;
  animation: finKpiCardIn .55s var(--ease-standard) var(--d,0ms) both; }
.uc-kpi::before { content:''; position: absolute; top:0; left:0; right:0; height:3px; background: var(--accent);
  border-radius: 14px 14px 0 0; animation: finKpi2DrawIn .8s var(--ease-standard) var(--d,0ms) both,
  finKpi2Breathe 2.8s ease-in-out calc(var(--d,0ms) + 1s) infinite; transform-origin: left center; }
.uc-kpi-l { font-size: 11px; font-weight: 500; text-transform: uppercase; letter-spacing: .06em; color: var(--t3,#94A3B8); }
.uc-kpi-v { font-size: 24px; font-weight: 400; letter-spacing: -.03em; color: var(--t1,#1E2A4A);
  font-variant-numeric: tabular-nums; display: flex; align-items: baseline; gap: 3px; margin: 4px 0 2px; }
.uc-kpi-u { font-size: 11px; color: var(--t3,#94A3B8); font-weight: 500; }
.uc-kpi-s { font-size: 10.5px; color: var(--t3,#94A3B8); }

/* Карточки */
.uc-card { background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 2px 12px rgba(15,23,60,.07); }
.uc-card-hd { margin-bottom: 12px; }
.uc-card-t { font-size: 13px; font-weight: 650; color: var(--t1,#1E2A4A); }
.uc-card-s { font-size: 10.5px; color: var(--t3,#94A3B8); margin-top: 2px; }

/* Цены */
.uc-prices { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
@media (max-width: 900px) { .uc-prices { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 560px) { .uc-prices { grid-template-columns: repeat(2, 1fr); } }
.uc-price { background: var(--bg2,#FAFAFD); border-radius: 11px; padding: 10px 12px;
  animation: finKpiCardIn .5s var(--ease-standard) var(--d,0ms) both; }
.uc-price-l { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); }
.uc-price-v { font-size: 16px; font-weight: 500; color: var(--t1,#1E2A4A); font-variant-numeric: tabular-nums; margin: 3px 0 1px; }
.uc-price-u { font-size: 9.5px; color: var(--t3,#94A3B8); }

/* Компании */
.uc-cos { display: flex; flex-direction: column; }
.uc-cos-head, .uc-co { display: grid; grid-template-columns: 2.2fr .8fr 1.2fr 1.2fr .9fr; align-items: center; gap: 10px; }
.uc-cos-head { padding: 0 8px 7px; border-bottom: 0.5px solid rgba(0,0,0,.07); }
.uc-cos-head span { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); text-align: right; }
.uc-cos-head span:first-child { text-align: left; }
.uc-co { width: 100%; text-align: left; background: none; border: 0; font-family: inherit; cursor: pointer;
  padding: 9px 8px; border-radius: 9px; border-bottom: 0.5px solid rgba(0,0,0,.04); transition: background .14s;
  animation: finFadeSlideIn .4s ease var(--d,0ms) both; }
.uc-co:hover { background: rgba(127,119,221,.05); }
.uc-co-name { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 500; color: var(--t1,#1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.uc-co-name i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.uc-co-n, .uc-co-cost, .uc-co-en { text-align: right; font-variant-numeric: tabular-nums; font-size: 12px; }
.uc-co-n { color: var(--t2,#4B5468); font-weight: 600; }
.uc-co-nn { font-size: 10px; color: var(--t3,#94A3B8); }
.uc-co-cost { font-weight: 700; color: var(--t1,#1E2A4A); }
.uc-co-en { color: var(--t2,#4B5468); }
.uc-co-share { text-align: right; }
.uc-share-chip { font-size: 11px; font-weight: 700; border-radius: 7px; padding: 2px 8px; font-variant-numeric: tabular-nums; }
.uc-dash { font-size: 11px; color: #C4C8D4; }

@media (max-width: 720px) { .uc-section, .uc-state { margin: 0 8px; } .uc-title { font-size: 15px; }
  .uc-cos-head, .uc-co { grid-template-columns: 2fr 1.2fr 1fr; }
  .uc-cos-head span:nth-child(4), .uc-cos-head span:nth-child(5), .uc-co-en, .uc-co-share { display: none; } }
</style>
