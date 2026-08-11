<script setup lang="ts">
/**
 * CwProductionSection — производственные показатели ОДНОЙ компании внутри
 * вкладки «Бизнес-план» карточки компании (/company/:id?tab=bp).
 *
 * Переиспользует снапшот производства (засеян по всем компаниям) через scoped
 * per-company эндпоинт GET /production/companies/{code}. Визуальный язык 1:1 с
 * ProductionDrillModal (дерево продуктов, зоны исполнения, count-up). Честный
 * расчёт приходит с бэка (3-state + execBasis). Пустые компании (НГМК и т.п.) →
 * аккуратный empty-state с CTA «Заполнить». Редактор встроен (ProductionEditModal).
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import {
  productionApi, type ProdCompany, type ProdLine,
  PRODUCTION_PERIOD_KEYS, productionPeriodLabel,
} from "@/api/production";
import { useCountUpScan } from "@/composables/useCountUp";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ProductionEditModal from "@/components/BusinessPlan/ProductionEditModal.vue";
import { execCol as pctCol, execZone as pctZone } from "@/utils/execBand";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
const { t } = useI18n();

const props = defineProps<{
  companyCode: string;
  companyName: string;
  year: number;
  canEdit?: boolean;
}>();

const loading = ref(false);
const error = ref<string | null>(null);
const company = ref<ProdCompany | null>(null);
const combos = ref<{ year: number; period: string }[]>([]);
const period = ref<string>("h1");
const editorOpen = ref(false);
let seq = 0;

const hasData = computed(() => !!company.value && company.value.has_data);
const products = computed(() => (company.value?.lines || []).filter((l) => !l.total));

// периоды, доступные ИМЕННО этой компании в выбранном году
const periodOpts = computed(() => {
  const ps = combos.value.filter((c) => c.year === props.year).map((c) => c.period);
  const uniq = Array.from(new Set(ps));
  // Показываем в каноническом порядке (кварталы → полугодия → год).
  uniq.sort((a, b) => PRODUCTION_PERIOD_KEYS.indexOf(a) - PRODUCTION_PERIOD_KEYS.indexOf(b));
  return uniq.map((p) => ({ value: p, label: t(productionPeriodLabel(p)) }));
});

async function load() {
  const my = ++seq;
  loading.value = true; error.value = null;
  try {
    const d = await productionApi.companyDetail(props.companyCode, props.year, period.value);
    if (my !== seq) return;
    company.value = d.company;
    combos.value = d.combos || [];
    // если выбранного периода нет у компании в этом году — переключиться на первый доступный
    const opts = (d.combos || []).filter((c) => c.year === props.year).map((c) => c.period);
    if (opts.length && !opts.includes(period.value)) {
      period.value = opts.includes("h1") ? "h1" : opts[0];
      return load();
    }
  } catch (e: any) {
    if (my !== seq) return;
    error.value = e?.response?.data?.detail || e?.message || t("Не удалось загрузить производственные показатели");
    company.value = null;
  } finally {
    if (my === seq) loading.value = false;
  }
}

onMounted(load);
watch(() => [props.year, props.companyCode], load);
watch(period, (n, o) => { if (n !== o) load(); });

// ─── formatting + zones (1:1 с ProductionDrillModal) ──────────
function fmtM(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  return Math.round(v).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 0 });
}
function fmtN(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  const abs = Math.abs(v);
  return v.toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: abs >= 1000 ? 0 : abs >= 10 ? 1 : 2 });
}
// P0 аудита: пороги исполнения — единый канон execBand (80/50, >110), импортом
// pctCol/pctZone. Раньше инлайн 90/75 с врущим комментарием «mirror forensic».
function execText(l: ProdLine): string {
  if (l.execState === "pct") return (l.execPct ?? 0) + "%";
  if (l.execState === "nofact") return t("факт —");
  return "—";
}

// ─── count-up (re-scan on data/period change) ─────────────────
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 40, stagger: 60 });
watch([company, period], async () => { await nextTick(); rescan(); });

function openEditor() { editorOpen.value = true; }
function onSaved() { editorOpen.value = false; load(); }
</script>

<template>
  <section class="cwp">
    <!-- Divider header -->
    <div class="cwp-head">
      <div class="cwp-head-l">
        <span class="cwp-eyebrow">{{ t("Бизнес-план · натуральные показатели") }}</span>
        <h3 class="cwp-title">{{ t("Производственные показатели") }}</h3>
      </div>
      <div class="cwp-head-r">
        <div v-if="periodOpts.length > 1" class="uza-seg is-sm">
          <button v-for="(p, i) in periodOpts" :key="p.value" type="button" class="uza-seg-btn"
                  :class="{ on: period === p.value }" :style="{ '--i': i }" @click="period = p.value">{{ t(p.label) }}</button>
        </div>
        <span v-if="hasData && company && company.execPct != null" class="cwp-badge"
              :style="{ color: pctCol(company.execPct), background: pctCol(company.execPct) + '18' }"
              :title="t(pctZone(company.execPct))">{{ company.execPct }}%</span>
        <button v-if="canEdit && hasData" class="cwp-edit" type="button" @click="openEditor" :title="t('Редактировать данные')">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
          {{ t("Редактировать") }}
        </button>
      </div>
    </div>

    <UzaStateBlock v-if="loading && !company" state="loading" variant="text" :loadingText="t('Загрузка производственных показателей…')" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" retry @retry="load" />

    <!-- Empty: у компании нет производственных данных за период -->
    <div v-else-if="!hasData" class="cwp-empty">
      <div class="cwp-empty-ic">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="7" y="12" width="3" height="6"/><rect x="12" y="8" width="3" height="10"/><rect x="17" y="5" width="3" height="13"/></svg>
      </div>
      <div class="cwp-empty-t">{{ t("Производственные показатели за {y} не заведены", { y: year }) }}</div>
      <div class="cwp-empty-s">{{ t("Данные по выпуску продукции (натура + деньги, план → ожидаемое) для «{name}» пока не заполнены.", { name: companyName }) }}</div>
      <button v-if="canEdit" class="cwp-empty-cta" type="button" @click="openEditor">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t("Заполнить показатели") }}
      </button>
    </div>

    <!-- Content -->
    <div v-else ref="scanRoot" class="cwp-body">
      <!-- KPI cards -->
      <div class="cwp-kpis">
        <div class="cwp-k"><div class="cwp-k-l">{{ t("План выпуска") }}</div>
          <div class="cwp-k-v"><span :data-countup="Math.round(company!.planM || 0)">{{ fmtM(company!.planM) }}</span></div>
          <div class="cwp-k-u">{{ t("млрд сум") }}</div></div>
        <div class="cwp-k"><div class="cwp-k-l">{{ t("Ожидаемое") }}</div>
          <div class="cwp-k-v"><span :data-countup="Math.round(company!.expM || 0)">{{ fmtM(company!.expM) }}</span></div>
          <div class="cwp-k-u">{{ t("млрд сум") }}</div></div>
        <div class="cwp-k cwp-k-fact"><div class="cwp-k-l">{{ t("Факт") }}</div>
          <div class="cwp-k-v"><span :data-countup="Math.round(company!.factM || 0)">{{ fmtM(company!.factM) }}</span></div>
          <div class="cwp-k-u">{{ company!.factM != null ? t('млрд сум') : t('не введён') }}</div></div>
        <div class="cwp-k"><div class="cwp-k-l">{{ t("Темп роста") }}</div>
          <div class="cwp-k-v" :style="{ color: company!.growthPct != null && company!.growthPct >= 100 ? '#1D9E75' : 'var(--t1, #1E2A4A)' }">
            {{ company!.growthPct != null ? company!.growthPct + '%' : '—' }}</div>
          <div class="cwp-k-u">{{ t("к пред. периоду") }}</div></div>
        <div class="cwp-k cwp-k-exec" :style="{ '--exec': pctCol(company!.execPct) }">
          <div class="cwp-k-l">{{ t("Исполнение") }}</div>
          <div class="cwp-k-v" :style="{ color: pctCol(company!.execPct) }">{{ company!.execPct != null ? company!.execPct + '%' : '—' }}</div>
          <div class="cwp-k-u">{{ t(company!.execKind === 'fact' ? t('факт / план') : t('ожид / план')) + (company!.execBasis === 'natura' ? ' · ' + t('нат') : '') }}</div></div>
      </div>

      <!-- Product tree -->
      <div class="cwp-tbl-wrap">
        <table class="cwp-tbl">
          <thead>
            <tr>
              <th class="lt">{{ t("Продукция") }}</th><th class="rt">{{ t("Ед.") }}</th>
              <th class="rt">{{ t("План (нат.)") }}</th><th class="rt">{{ t("Ожид. (нат.)") }}</th><th class="rt cwp-fact-h">{{ t("Факт (нат.)") }}</th>
              <th class="rt">{{ t("План (млрд)") }}</th><th class="rt">{{ t("Ожид. (млрд)") }}</th><th class="rt cwp-fact-h">{{ t("Факт (млрд)") }}</th>
              <th class="rt">{{ t("Темп") }}</th><th class="rt">{{ t("Исп.") }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(l, i) in products" :key="i" :class="{ child: l.parent != null }"
                :style="{ animationDelay: (Math.min(i, 24) * 20) + 'ms' }">
              <td class="lt"><span :class="{ 'cwp-child-lbl': l.parent != null }">{{ l.name }}</span></td>
              <td class="rt muted">{{ l.unit || '—' }}</td>
              <td class="rt num muted">{{ fmtN(l.planN) }}</td>
              <td class="rt num muted">{{ fmtN(l.expN) }}</td>
              <td class="rt num cwp-fact">{{ fmtN(l.factN) }}</td>
              <td class="rt num muted">{{ fmtM(l.planM) }}</td>
              <td class="rt num muted">{{ fmtM(l.expM) }}</td>
              <td class="rt num cwp-fact">{{ fmtM(l.factM) }}</td>
              <td class="rt num" :style="{ color: l.growthPct != null && l.growthPct >= 100 ? '#1D9E75' : 'var(--t3,#94A3B8)' }">
                {{ l.growthPct != null ? l.growthPct + '%' : '—' }}</td>
              <td class="rt num" :style="{ color: pctCol(l.execPct), fontWeight: 600 }" :title="t(pctZone(l.execPct))">{{ execText(l) }}</td>
            </tr>
            <tr v-if="!products.length"><td colspan="10" class="cwp-tbl-empty">{{ t("Итоговые показатели без детализации по продукции") }}</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Editor (встроен) -->
    <ProductionEditModal v-if="editorOpen && company" :company="company" :year="year" :period="period"
                         @close="editorOpen = false" @saved="onSaved" />
  </section>
</template>

<style scoped>
.cwp { margin-top: 22px; padding-top: 20px; border-top: 1px solid rgba(0,0,0,.07);
  animation: cwpIn .45s cubic-bezier(.34,1.1,.64,1) both; }
@keyframes cwpIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

.cwp-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.cwp-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.cwp-title { font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A); margin: 2px 0 0; }
.cwp-head-r { display: flex; align-items: center; gap: 10px; }
.cwp-badge { font-size: 14px; font-weight: 700; padding: 4px 10px; border-radius: 8px; font-feature-settings: 'tnum'; }
.cwp-edit { display: inline-flex; align-items: center; gap: 6px; padding: 6px 13px; border-radius: 8px;
  border: 1px solid rgba(127,119,221,.30); background: rgba(127,119,221,.08); color: var(--p-deep, #534AB7);
  font: 600 12px inherit; cursor: pointer; transition: all .13s; }
.cwp-edit:hover { background: rgba(127,119,221,.16); border-color: rgba(127,119,221,.5); }

/* KPI cards */
.cwp-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 11px; margin-bottom: 14px; }
@media (max-width: 900px) { .cwp-kpis { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 560px) { .cwp-kpis { grid-template-columns: repeat(2, 1fr); } }
.cwp-k-fact { background: rgba(127,119,221,.06); border-color: rgba(127,119,221,.16); }
.cwp-k { position: relative; overflow: hidden; background: var(--bg2, #FAFAFC); border: 1px solid rgba(0,0,0,.05);
  border-radius: 11px; padding: 11px 13px; animation: cwpK .5s cubic-bezier(.34,1.1,.64,1) both; }
.cwp-k::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--kc, var(--accent, #7F77DD));
  border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0;
  pointer-events: none;
}

.cwp-k:nth-child(2) { animation-delay: .06s; } .cwp-k:nth-child(3) { animation-delay: .12s; } .cwp-k:nth-child(4) { animation-delay: .18s; }
@keyframes cwpK { from { opacity: 0; transform: translateY(8px) scale(.98); } to { opacity: 1; transform: none; } }
.cwp-k-exec::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: var(--exec, #7F77DD); opacity: .85; }
.cwp-k-l { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted)); }
.cwp-k-v { font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A); letter-spacing: -.02em; font-feature-settings: 'tnum'; margin-top: 3px; line-height: 1.1; }
.cwp-k-u { font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 2px; }

/* Product table */
.cwp-tbl-wrap { max-height: 52vh; overflow: auto; scrollbar-width: thin; border: 1px solid rgba(0,0,0,.05); border-radius: 11px; }
.cwp-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.cwp-tbl thead th { position: sticky; top: 0; z-index: 1; background: var(--bg2, #FAFAFC); padding: 8px 10px; font-size: 9.5px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em; color: var(--t3, var(--t-muted)); border-bottom: 0.5px solid rgba(0,0,0,.06); white-space: nowrap; }
.cwp-tbl th.lt { text-align: left; } .cwp-tbl th.rt { text-align: right; }
.cwp-tbl tbody td { padding: 6px 10px; border-bottom: 0.5px solid rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }
.cwp-tbl td.lt { text-align: left; } .cwp-tbl td.rt { text-align: right; } .cwp-tbl td.num { font-feature-settings: 'tnum'; }
.cwp-tbl td.muted { color: var(--t3, var(--t-muted)); }
.cwp-tbl tbody tr { animation: cwpRow .3s ease both; }
@keyframes cwpRow { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }
.cwp-tbl tr.child td { background: rgba(127,119,221,.03); }
.cwp-fact-h { color: var(--p-deep, #534AB7) !important; }
.cwp-tbl td.cwp-fact { color: var(--t1, #1E2A4A); font-weight: 500; background: rgba(127,119,221,.03); }
.cwp-child-lbl { padding-left: 16px; color: var(--t2, #475569); font-size: 11.5px; }
.cwp-child-lbl::before { content: "└ "; color: var(--t3, #94A3B8); }
.cwp-tbl-empty { text-align: center; padding: 20px; color: var(--t3, var(--t-muted)); font-style: italic; }

/* Empty state */
.cwp-empty { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px;
  padding: 30px 20px; background: linear-gradient(135deg, rgba(127,119,221,.05), rgba(127,119,221,.02));
  border: 1px dashed rgba(127,119,221,.25); border-radius: 14px; }
.cwp-empty-ic { width: 46px; height: 46px; border-radius: 12px; display: flex; align-items: center; justify-content: center;
  background: rgba(127,119,221,.10); color: var(--p-deep, #7F77DD); margin-bottom: 4px; }
.cwp-empty-t { font-size: 14px; font-weight: 600; color: var(--t1, #1E2A4A); }
.cwp-empty-s { font-size: 12px; color: var(--t3, var(--t-muted)); max-width: 460px; line-height: 1.4; }
.cwp-empty-cta { margin-top: 8px; display: inline-flex; align-items: center; gap: 6px; padding: 9px 18px; border-radius: 9px;
  border: none; background: #7F77DD; color: #fff; font: 600 12.5px inherit; cursor: pointer; transition: all .14s; }
.cwp-empty-cta:hover { background: #6D62D6; box-shadow: 0 6px 16px rgba(127,119,221,.32); transform: translateY(-1px); }
</style>
