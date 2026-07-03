<script setup lang="ts">
/**
 * UnitCostDashboard — «Удельная себестоимость» (сайдбар Финансы).
 * Себестоимость продукции по компаниям: энергозатраты (норма×цена) + прочие
 * статьи, на единицу продукции. KPI-полоса, цены энергоносителей, список
 * компаний со сводкой, дрилл-редактор продуктов. Премиум UX.
 */
import { computed, inject, onMounted, ref, watch } from "vue";
import { usePermissions } from "@/composables/usePermissions";
import { useSavedFilter } from "@/composables/useSavedFilter";
import { ensureFinancialsCss } from "@/components/Financials/financialsHelpers";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import Odometer from "@/components/Odometer.vue";
import CreditDonut, { type DonutEntry } from "@/components/CreditPortfolio/CreditDonut.vue";
import FuelIcon from "@/components/UnitCost/FuelIcon.vue";
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

// годы: с 2021 по следующий год включительно (новый год появляется сам —
// напр. в 2026-м доступен 2027). Данные period-keyed, любой год валиден на бэке.
const YEARS = (() => {
  const next = new Date().getFullYear() + 1;
  const out: number[] = [];
  for (let y = 2021; y <= Math.max(next, 2026); y++) out.push(y);
  return out;
})();
const QUARTERS = [
  { value: "annual", label: "Год" }, { value: "q1", label: "I кв" },
  { value: "q2", label: "II кв" }, { value: "q3", label: "III кв" }, { value: "q4", label: "IV кв" },
] as const;
const year = useSavedFilter<number>("unitCost.year", 2025);
const quarter = useSavedFilter<string>("unitCost.quarter", "annual");

const data = ref<UCOverview | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
let seq = 0;

async function load() {
  const my = ++seq;
  loading.value = true; error.value = null;
  try {
    const r = await unitCostApi.overview(year.value, quarter.value);
    if (my !== seq) return;
    data.value = r;
  } catch (e: unknown) {
    if (my !== seq) return;
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally { if (my === seq) loading.value = false; }
}
onMounted(() => { ensureFinancialsCss(); load(); });
watch([year, quarter], load);

const pf = computed(() => data.value?.portfolio || null);
const companies = computed(() => data.value?.companies || []);
const pricesOpen = ref(false);
const editCompany = ref<UCCompany | null>(null);
function onKpiClick() { if (finPerm.canEdit.value) pricesOpen.value = true; }

// компактное представление суммы в СУМАХ (сырьё уже в сумах)
function scaleSum(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e12) return (v / 1e12).toLocaleString("ru", { maximumFractionDigits: 2 }) + " трлн";
  if (a >= 1e9) return (v / 1e9).toLocaleString("ru", { maximumFractionDigits: 1 }) + " млрд";
  if (a >= 1e6) return (v / 1e6).toLocaleString("ru", { maximumFractionDigits: 1 }) + " млн";
  if (a >= 1e3) return (v / 1e3).toLocaleString("ru", { maximumFractionDigits: 1 }) + " тыс";
  return v.toLocaleString("ru", { maximumFractionDigits: 0 });
}
function fmtSum(v: number | null): string { return v == null ? "—" : scaleSum(v); }

// перерасход/экономия к норме (знак: + перерасход / − экономия)
const overrun = computed(() => pf.value?.overrun_cost ?? null);
const overrunState = computed<"over" | "save" | "none">(() => {
  const v = overrun.value; if (v == null) return "none";
  return v > 0 ? "over" : "save";
});
const overrunColor = computed(() =>
  overrunState.value === "over" ? "#E24B4A" : overrunState.value === "save" ? "#1D9E75" : "#94A3B8");
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

// живой тикер (авто-обновление, best-effort); правки — в редакторе (per-period)
const worldLive = computed(() => data.value?.world_live || null);
const liveFresh = computed(() => {
  const t = worldLive.value?.updated_at; if (!t) return "";
  try { return new Date(t).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
});
function fmtNum(v: number | null | undefined, d = 0): string {
  return v == null ? "—" : Number(v).toLocaleString("ru", { maximumFractionDigits: d });
}
// честный тикер: помечаем только реально живые поля (USD — ЦБ, золото — спот);
// Brent/медь — ориентиры без живого источника (правятся в «Цены и курсы»).
const LIVE_SRC: Record<string, string> = { usd_rate: "курс ЦБ РУз", gold: "спот-рынок" };
const tickerItems = computed(() => {
  const w = worldLive.value; if (!w) return [];
  const lf = w.live_fields || [];
  return [
    { key: "usd_rate", label: "USD", val: fmtNum(w.usd_rate) },
    { key: "brent", label: "Brent", val: "$" + fmtNum(w.brent, 1) },
    { key: "gold", label: "Gold", val: "$" + fmtNum(w.gold) },
    { key: "copper", label: "Cu", val: "$" + fmtNum(w.copper) },
  ].map((t) => ({ ...t, live: lf.includes(t.key), src: LIVE_SRC[t.key] || "ориентир" }));
});

// фильтр по секторам (для списка компаний)
const sectorFilter = ref<string>("");
const sectors = computed(() => {
  const set = new Map<string, string>();  // sector → цвет
  for (const c of companies.value) if (c.sector && c.sector !== "—") set.set(c.sector, c.color);
  return Array.from(set, ([name, color]) => ({ name, color })).sort((a, b) => a.name.localeCompare(b.name, "ru"));
});
const visibleCompanies = computed(() =>
  sectorFilter.value ? companies.value.filter((c) => c.sector === sectorFilter.value) : companies.value);
watch([year, quarter], () => { sectorFilter.value = ""; });

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
// себестоимость по секторам
const SECTOR_PAL = ["#7F77DD", "#1D9E75", "#EF9F27", "#378ADD", "#E24B4A", "#8B7FFF", "#5DC093", "#4B5468"];
const sectorDonut = computed<DonutEntry[]>(() => {
  const by: Record<string, number> = {};
  for (const c of companies.value) if (c.total_cost) by[c.sector] = (by[c.sector] || 0) + c.total_cost;
  return Object.entries(by).sort((a, b) => b[1] - a[1])
    .map(([name, v], i) => ({ label: name, color: SECTOR_PAL[i % SECTOR_PAL.length], value: v, sub: fmtSum(v) }));
});
const sectorTotal = computed(() => companies.value.reduce((a, c) => a + (c.total_cost || 0), 0));
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
        <div v-if="worldLive" class="uc-ticker"
             :title="'Зелёная точка — живой источник; остальное — ориентир, правится в «Цены и курсы»' + (liveFresh ? '. Обновлено ' + liveFresh : '')">
          <span v-for="t in tickerItems" :key="t.key" class="uc-tk" :class="t.live ? 'uc-tk-live' : 'uc-tk-off'"
                :title="t.live ? ('Живой источник: ' + t.src + (liveFresh ? ', ' + liveFresh : '')) : 'Ориентир: нет живого источника — задаётся вручную в «Цены и курсы»'">
            <span v-if="t.live" class="uc-live"><i /></span>
            <span v-else class="uc-offdot" aria-hidden="true"></span>
            <b>{{ t.label }}</b>{{ t.val }}
            <span v-if="t.live" class="uc-tag uc-tag-live">live</span>
            <span v-else class="uc-tag uc-tag-off">ориентир</span>
          </span>
        </div>
        <div class="uc-div" aria-hidden="true"></div>
        <UzaSegment :model-value="quarter" :options="QUARTERS as never" size="sm" tone="dark"
                    @update:model-value="quarter = $event as string" />
        <UzaYearStepper tone="dark" :model-value="year" :years="YEARS" prefix="FY "
                        @update:model-value="year = ($event as number) ?? year" />
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
          <div class="uc-kpi uc-kpi-clk" role="button" tabindex="0" @click="onKpiClick" style="--accent:#7F77DD; --d:0ms;">
            <div class="uc-kpi-l">Совокупная себестоимость</div>
            <div class="uc-kpi-v">{{ fmtSum(pf.total_cost) }}</div>
            <div class="uc-kpi-s">по заполненному выпуску</div>
          </div>
          <div class="uc-kpi uc-kpi-clk" role="button" tabindex="0" @click="onKpiClick" style="--accent:#EF9F27; --d:80ms;">
            <div class="uc-kpi-l">Энергозатраты</div>
            <div class="uc-kpi-v">{{ fmtSum(pf.energy_cost) }}</div>
            <div class="uc-kpi-s">из совокупной</div>
          </div>
          <div class="uc-kpi uc-kpi-clk" role="button" tabindex="0" @click="onKpiClick" style="--accent:#E24B4A; --d:160ms;">
            <div class="uc-kpi-l">Доля энергии</div>
            <div class="uc-kpi-v">
              <span v-if="pf.energy_share != null"><Odometer :value="pf.energy_share.toFixed(1)" /><span class="uc-kpi-u">%</span></span>
              <span v-else>—</span>
            </div>
            <div class="uc-kpi-s">энергоёмкость портфеля</div>
          </div>
          <div class="uc-kpi uc-kpi-clk" role="button" tabindex="0" @click="onKpiClick" style="--accent:#1D9E75; --d:240ms;">
            <div class="uc-kpi-l">Заполнено продуктов</div>
            <div class="uc-kpi-v">{{ pf.priced_count }}<span class="uc-kpi-u">/ {{ pf.product_count }}</span></div>
            <div class="uc-kpi-s">{{ pf.company_count }} компаний</div>
          </div>
          <div class="uc-kpi"
               :style="{ '--accent': overrunColor, '--d': '320ms' }"
               title="Отклонение фактического удельного расхода от нормы, в деньгах">
            <div class="uc-kpi-l">Перерасход / Экономия</div>
            <div class="uc-kpi-v" :style="{ color: overrunColor }">
              <template v-if="overrun != null">
                <span class="uc-ov-sign">{{ overrunState === 'over' ? '+' : '−' }}</span>{{ fmtSum(Math.abs(overrun)) }}
              </template>
              <span v-else>—</span>
            </div>
            <div class="uc-kpi-s">
              <template v-if="overrunState === 'over'">перерасход к норме расхода</template>
              <template v-else-if="overrunState === 'save'">экономия против нормы</template>
              <template v-else>заполните выпуск и нормы</template>
            </div>
          </div>
        </div>
      </section>

      <!-- Пайчарты: между KPI и ценами -->
      <section class="uc-section uc-3col">
        <div class="uc-card">
          <div class="uc-card-hd"><div>
            <div class="uc-card-t">Энергомикс портфеля</div>
            <div class="uc-card-s">доля видов топлива в энергозатратах</div>
          </div></div>
          <CreditDonut v-if="mixDonut.length" :entries="mixDonut" :center-value="fmtSum(mixTotal)"
            center-label="энергия" :hover-fmt="donutHover" :size="150" />
          <div v-else class="uc-chart-empty">заполните выпуск продуктов</div>
        </div>
        <div class="uc-card">
          <div class="uc-card-hd"><div>
            <div class="uc-card-t">Структура себестоимости</div>
            <div class="uc-card-s">энергозатраты и прочие статьи</div>
          </div></div>
          <CreditDonut v-if="structDonut.length" :entries="structDonut" :center-value="fmtSum(pf!.total_cost)"
            center-label="итого" :hover-fmt="donutHover" :size="150" />
          <div v-else class="uc-chart-empty">заполните статьи себестоимости</div>
        </div>
        <div class="uc-card">
          <div class="uc-card-hd"><div>
            <div class="uc-card-t">Себестоимость по секторам</div>
            <div class="uc-card-s">распределение по отраслям</div>
          </div></div>
          <CreditDonut v-if="sectorDonut.length" :entries="sectorDonut" :center-value="fmtSum(sectorTotal)"
            center-label="итого" :hover-fmt="donutHover" :size="150" />
          <div v-else class="uc-chart-empty">нет данных по себестоимости</div>
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
            <div v-for="(p, i) in priceRows" :key="p.fuel" class="uc-price" :style="{ '--d': (i * 50) + 'ms', '--fc': FUEL_PAL[p.fuel] || '#7F77DD' }">
              <div class="uc-price-l"><FuelIcon :fuel="p.fuel" :size="13" />{{ p.label }}</div>
              <div class="uc-price-v">{{ p.price.toLocaleString("ru") }}</div>
              <div class="uc-price-u">{{ p.unit }}</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Компании -->
      <section class="uc-section">
        <div class="uc-card">
          <div class="uc-card-hd uc-card-hd-row">
            <div>
              <div class="uc-card-t">Себестоимость по компаниям</div>
              <div class="uc-card-s">клик по компании — продукты и статьи · доля энергии в цвете</div>
            </div>
            <div v-if="sectors.length > 1" class="uc-secfilter">
              <button type="button" class="uc-sec" :class="{ on: sectorFilter === '' }" @click="sectorFilter = ''">
                Все<span class="uc-sec-n">{{ companies.length }}</span>
              </button>
              <button v-for="s in sectors" :key="s.name" type="button" class="uc-sec"
                      :class="{ on: sectorFilter === s.name }" @click="sectorFilter = s.name">
                <i :style="{ background: s.color }" />{{ s.name }}
              </button>
            </div>
          </div>
          <div class="uc-cos">
            <div class="uc-cos-head">
              <span>Компания</span><span>Продуктов</span><span>Себестоимость</span>
              <span>Энергозатраты</span><span>Доля энергии</span>
            </div>
            <button v-for="(c, i) in visibleCompanies" :key="c.code" type="button" class="uc-co"
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
            <div v-if="!visibleCompanies.length" class="uc-chart-empty">в секторе «{{ sectorFilter }}» нет компаний</div>
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
      :year="year" :quarter="quarter"
      @close="editCompany = null"
      @saved="editCompany = null; load()"
    />
    <UnitCostPricesModal
      :open="pricesOpen"
      :prices="data?.energyPrices || {}"
      :world="data?.world || null"
      :live="data?.world_live || null"
      :fuel-labels="data?.fuel_labels || {}"
      :year="year" :quarter="quarter"
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
.uc-ticker { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.uc-tk { display: inline-flex; align-items: center; font-size: 11.5px; font-weight: 600; color: rgba(255,255,255,.9); font-variant-numeric: tabular-nums; white-space: nowrap;
  padding: 3px 9px; border-radius: 7px; background: rgba(255,255,255,.06); }
.uc-tk-live { background: rgba(74,222,128,.10); box-shadow: inset 0 0 0 1px rgba(74,222,128,.22); }
.uc-tk-off { opacity: .82; }
.uc-tk b { font-size: 8.5px; font-weight: 700; color: rgba(255,255,255,.5); text-transform: uppercase; letter-spacing: .04em; margin-right: 5px; }
.uc-live { display: inline-flex; align-items: center; margin-right: 5px; }
.uc-offdot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; box-sizing: border-box;
  border: 1.5px solid rgba(255,255,255,.34); margin-right: 5px; flex-shrink: 0; }
.uc-tag { margin-left: 6px; font-size: 7.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  border-radius: 5px; padding: 1px 5px; line-height: 1.5; }
.uc-tag-live { color: #4ADE80; background: rgba(74,222,128,.16); }
.uc-tag-off { color: rgba(255,255,255,.62); background: rgba(255,255,255,.10); }
.uc-live i { width: 7px; height: 7px; border-radius: 50%; background: #4ADE80; box-shadow: 0 0 0 0 rgba(74,222,128,.6);
  animation: ucLivePulse 2s ease-in-out infinite; }
@keyframes ucLivePulse { 0%,100% { box-shadow: 0 0 0 0 rgba(74,222,128,.5); } 50% { box-shadow: 0 0 0 4px rgba(74,222,128,0); } }
.uc-div { width: 1px; height: 20px; background: rgba(255,255,255,.14); margin: 0 2px; flex-shrink: 0; }
.uc-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .uc-2col { grid-template-columns: 1fr; } }

.uc-state { display: flex; flex-direction: column; gap: 10px; margin: 0 14px; }
.uc-skel { height: 92px; border-radius: 14px; background: linear-gradient(90deg,#F1F0F7 25%,#FAF9FE 50%,#F1F0F7 75%);
  background-size: 200% 100%; animation: ucShimmer 1.4s ease-in-out var(--d,0ms) infinite; }
@keyframes ucShimmer { from { background-position: 200% 0; } to { background-position: -200% 0; } }
.uc-err { flex-direction: row; align-items: center; gap: 12px; color: #E24B4A; font-size: 12.5px; }
.uc-retry { font-size: 12px; font-weight: 600; font-family: inherit; border: 1px solid #E5E7EB; background: #fff; border-radius: 9px; padding: 6px 14px; cursor: pointer; }

/* KPI */
.uc-kpi-band { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }
@media (max-width: 1280px) { .uc-kpi-band { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 720px) { .uc-kpi-band { grid-template-columns: 1fr 1fr; } }
.uc-ov-sign { font-size: 16px; font-weight: 500; margin-right: 1px; }
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
.uc-kpi-clk { cursor: pointer; transition: transform .16s ease, box-shadow .16s ease; outline: none; }
.uc-kpi-clk:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(15,23,60,.10), 0 1px 3px rgba(15,23,60,.04); }
.uc-kpi-clk:focus-visible { box-shadow: 0 0 0 2px rgba(127,119,221,.45); }

/* Карточки */
.uc-card { background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid rgba(255,255,255,.70); border-radius: 14px; padding: 16px 18px;
  box-shadow: 0 2px 12px rgba(15,23,60,.07); }
.uc-card-hd { margin-bottom: 12px; }
.uc-card-hd-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.uc-card-t { font-size: 13px; font-weight: 650; color: var(--t1,#1E2A4A); }
.uc-card-s { font-size: 10.5px; color: var(--t3,#94A3B8); margin-top: 2px; }

/* Фильтр по секторам */
.uc-secfilter { display: flex; flex-wrap: wrap; gap: 5px; }
.uc-sec { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; font-family: inherit;
  color: var(--t2,#4B5468); background: var(--bg2,#FAFAFD); border: 1px solid var(--border,#ECEAF5); border-radius: 8px;
  padding: 5px 10px; cursor: pointer; transition: all .14s; white-space: nowrap; }
.uc-sec i { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.uc-sec:hover { border-color: rgba(124,111,247,.4); background: rgba(124,111,247,.05); }
.uc-sec.on { color: #fff; background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border-color: transparent;
  box-shadow: 0 2px 8px rgba(108,92,231,.28); }
.uc-sec.on i { box-shadow: 0 0 0 1.5px rgba(255,255,255,.7); }
.uc-sec-n { font-size: 9.5px; opacity: .7; font-variant-numeric: tabular-nums; }

/* Цены */
.uc-prices { display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }
@media (max-width: 900px) { .uc-prices { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 560px) { .uc-prices { grid-template-columns: repeat(2, 1fr); } }
.uc-price { background: var(--bg2,#FAFAFD); border-radius: 11px; padding: 10px 12px;
  animation: finKpiCardIn .5s var(--ease-standard) var(--d,0ms) both; }
.uc-3col { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
@media (max-width: 1000px) { .uc-3col { grid-template-columns: 1fr; } }
.uc-chart-empty { padding: 40px 16px; text-align: center; font-size: 11.5px; color: #C4C8D4; font-style: italic; }
.uc-price-l { display: flex; align-items: center; gap: 6px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--t3,#94A3B8); }
.uc-price-l :deep(.fi) { color: var(--fc, #7F77DD); }
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
