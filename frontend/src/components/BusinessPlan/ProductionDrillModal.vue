<script setup lang="ts">
/** ProductionDrillModal — детализация производства одной компании (дерево продуктов,
 *  натура + деньги, план→ожидаемое, честное исполнение с зонами). Данные приходят
 *  в company.lines из overview — доп. запрос не нужен. */
import { computed } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import { usePermissions } from "@/composables/usePermissions";
import type { ProdCompany, ProdLine } from "@/api/production";
import { execCol as pctCol, execZone as pctZone } from "@/utils/execBand";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";


const { t } = useI18n();

const props = defineProps<{ company: ProdCompany; year: number; period: string }>();
const emit = defineEmits<{ (e: "close"): void; (e: "edit"): void }>();

const canEdit = usePermissions("bp").canEdit;

const PERIOD_LABEL: Record<string, string> = { h1: i18nKey("1 полугодие"), h2: i18nKey("2 полугодие"), annual: i18nKey("год") };
const periodLabel = computed(() => PERIOD_LABEL[props.period] || props.period);

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

// products = non-total lines; total shown in header
const products = computed(() => props.company.lines.filter((l) => !l.total));
</script>

<template>
  <ModalShell :open="true" size="lg" @close="emit('close')">
    <template #header>
      <div class="pdm-hd">
        <CompanyAvatar :name="company.n" :color="company.sector_color || '#888780'" :size="30" />
        <div class="pdm-hd-txt">
          <div class="pdm-eyebrow">{{ t("Производственный план") }} · FY{{ year }} · {{ t(periodLabel) }}</div>
          <div class="pdm-title">{{ company.n }}</div>
        </div>
        <span v-if="company.execPct != null" class="pdm-badge"
              :style="{ color: pctCol(company.execPct), background: pctCol(company.execPct) + '18' }"
              :title="t(pctZone(company.execPct))">{{ company.execPct }}%</span>
      </div>
    </template>

    <!-- KPI row -->
    <div class="pdm-kpis">
      <div class="pdm-k"><div class="pdm-k-l">{{ t("План") }}</div><div class="pdm-k-v">{{ fmtM(company.planM) }}</div><div class="pdm-k-u">{{ t("млрд сум") }}</div></div>
      <div class="pdm-k"><div class="pdm-k-l">{{ t("Ожидаемое") }}</div><div class="pdm-k-v">{{ fmtM(company.expM) }}</div><div class="pdm-k-u">{{ t("млрд сум") }}</div></div>
      <div class="pdm-k pdm-k-fact"><div class="pdm-k-l">{{ t("Факт") }}</div>
        <div class="pdm-k-v">{{ fmtM(company.factM) }}</div>
        <div class="pdm-k-u">{{ company.factM != null ? t('млрд сум') : t('не введён') }}</div></div>
      <div class="pdm-k"><div class="pdm-k-l">{{ t("Темп роста") }}</div>
        <div class="pdm-k-v" :style="{ color: company.growthPct != null && company.growthPct >= 100 ? '#1D9E75' : 'var(--t1)' }">
          {{ company.growthPct != null ? company.growthPct + '%' : '—' }}</div><div class="pdm-k-u">{{ t("к пред. периоду") }}</div></div>
      <div class="pdm-k"><div class="pdm-k-l">{{ t("Исполнение") }}</div>
        <div class="pdm-k-v" :style="{ color: pctCol(company.execPct) }">{{ company.execPct != null ? company.execPct + '%' : '—' }}</div>
        <div class="pdm-k-u">{{ t(company.execKind === 'fact' ? t('факт / план') : t('ожид / план')) + (company.execBasis === 'natura' ? ' · ' + t('нат') : '') }}</div></div>
    </div>

    <!-- Product table -->
    <div class="pdm-tbl-wrap">
      <table class="pdm-tbl">
        <thead>
          <tr>
            <th class="lt">{{ t("Продукция") }}</th><th class="rt">{{ t("Ед.") }}</th>
            <th class="rt">{{ t("План (нат.)") }}</th><th class="rt">{{ t("Ожид. (нат.)") }}</th><th class="rt pdm-fact-h">{{ t("Факт (нат.)") }}</th>
            <th class="rt">{{ t("План (млрд)") }}</th><th class="rt">{{ t("Ожид. (млрд)") }}</th><th class="rt pdm-fact-h">{{ t("Факт (млрд)") }}</th>
            <th class="rt">{{ t("Темп") }}</th><th class="rt">{{ t("Исп.") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(l, i) in products" :key="i" :class="{ child: l.parent != null }"
              :style="{ animationDelay: (Math.min(i, 24) * 20) + 'ms' }">
            <td class="lt"><span :class="{ 'pdm-child-lbl': l.parent != null }">{{ l.name }}</span></td>
            <td class="rt muted">{{ l.unit || '—' }}</td>
            <td class="rt num muted">{{ fmtN(l.planN) }}</td>
            <td class="rt num muted">{{ fmtN(l.expN) }}</td>
            <td class="rt num pdm-fact">{{ fmtN(l.factN) }}</td>
            <td class="rt num muted">{{ fmtM(l.planM) }}</td>
            <td class="rt num muted">{{ fmtM(l.expM) }}</td>
            <td class="rt num pdm-fact">{{ fmtM(l.factM) }}</td>
            <td class="rt num" :style="{ color: l.growthPct != null && l.growthPct >= 100 ? '#1D9E75' : 'var(--t3,#94A3B8)' }">
              {{ l.growthPct != null ? l.growthPct + '%' : '—' }}</td>
            <td class="rt num" :style="{ color: pctCol(l.execPct), fontWeight: 600 }" :title="t(pctZone(l.execPct))">{{ execText(l) }}</td>
          </tr>
          <tr v-if="!products.length"><td colspan="10" class="pdm-empty">{{ t("Нет детализации по продукции") }}</td></tr>
        </tbody>
      </table>
    </div>

    <div class="pdm-foot">
      <button v-if="canEdit" class="pdm-edit" @click="emit('edit')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
        {{ t("Редактировать данные") }}
      </button>
    </div>
  </ModalShell>
</template>

<style scoped>
.pdm-hd { display: flex; align-items: center; gap: 12px; }
.pdm-hd-txt { flex: 1; min-width: 0; }
.pdm-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.pdm-title { font-size: 16px; font-weight: 600; color: var(--t1, #1E2A4A); margin-top: 2px; }
.pdm-badge { font-size: 15px; font-weight: 700; padding: 4px 11px; border-radius: 9px; font-feature-settings: 'tnum'; }

.pdm-kpis { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 14px; }
@media (max-width: 760px) { .pdm-kpis { grid-template-columns: repeat(2, 1fr); } }
.pdm-k { background: var(--bg2, #FAFAFC); border: 1px solid rgba(0,0,0,.05); border-radius: 10px; padding: 10px 12px; }
.pdm-k-fact { background: rgba(127,119,221,.06); border-color: rgba(127,119,221,.16); }
.pdm-fact-h { color: var(--p-deep, #534AB7) !important; }
.pdm-tbl td.pdm-fact { color: var(--t1, #1E2A4A); font-weight: 500; background: rgba(127,119,221,.03); }
.pdm-k-l { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted)); }
.pdm-k-v { font-size: 22px; font-weight: 400; color: var(--t1, #1E2A4A); letter-spacing: -.02em; font-feature-settings: 'tnum'; margin-top: 2px; }
.pdm-k-u { font-size: 10.5px; color: var(--t3, var(--t-muted)); margin-top: 1px; }

.pdm-tbl-wrap { max-height: 46vh; overflow: auto; scrollbar-width: thin; border: 1px solid rgba(0,0,0,.05); border-radius: 10px; }
.pdm-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pdm-tbl thead th { position: sticky; top: 0; background: var(--bg2, #FAFAFC); padding: 8px 10px; font-size: 9.5px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .04em; color: var(--t3, var(--t-muted)); border-bottom: 0.5px solid rgba(0,0,0,.06); white-space: nowrap; }
.pdm-tbl th.lt { text-align: left; } .pdm-tbl th.rt { text-align: right; }
.pdm-tbl tbody td { padding: 6px 10px; border-bottom: 0.5px solid rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }
.pdm-tbl td.lt { text-align: left; } .pdm-tbl td.rt { text-align: right; } .pdm-tbl td.num { font-feature-settings: 'tnum'; }
.pdm-tbl td.muted { color: var(--t3, var(--t-muted)); }
.pdm-tbl tbody tr { animation: pdmRow .3s ease both; }
@keyframes pdmRow { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: none; } }
.pdm-tbl tr.child td { background: rgba(127,119,221,.03); }
.pdm-child-lbl { padding-left: 16px; color: var(--t2, #475569); font-size: 11.5px; }
.pdm-child-lbl::before { content: "└ "; color: var(--t3, #94A3B8); }
.pdm-empty { text-align: center; padding: 24px; color: var(--t3, var(--t-muted)); font-style: italic; }

.pdm-foot { display: flex; justify-content: flex-end; margin-top: 14px; }
.pdm-edit { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border-radius: 8px; border: 1px solid #7F77DD;
  background: #7F77DD; color: #fff; font-size: 12.5px; font-weight: 600; font-family: inherit; cursor: pointer; transition: all .13s; }
.pdm-edit:hover { background: #6D62D6; box-shadow: 0 4px 12px rgba(127,119,221,.3); }
</style>
