<script setup lang="ts">
/**
 * BpProductionDashboard — вкладка «Производственные показатели» модуля Бизнес-план.
 * Свод исполнения производственного плана (натура + деньги, план→ожидаемое) +
 * визуальное сравнение 2025→2026. Честный расчёт исполнения приходит с бэка
 * (3-state + execBasis money/natura); фронт красит зоны (overpar>110 — отдельная).
 * Интерактив: чипы секторов, фильтр по компании, кликабельные KPI, тумблер чарта.
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import UzaSegment from "@/components/UZA/UzaSegment.vue";
import UzaYearStepper from "@/components/UZA/UzaYearStepper.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import ForensicUploadModal from "@/components/Procurement/ForensicUploadModal.vue";
import { useCountUpScan } from "@/composables/useCountUp";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useProductionData } from "@/composables/useProductionData";
import type { ProdCompany } from "@/api/production";
import { execCol as pctCol, execZone as pctZone } from "@/utils/execBand";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";


const { t } = useI18n();

defineProps<{ canImport?: boolean }>();
const emit = defineEmits<{
  (e: "drill", p: { company: ProdCompany; year: number; period: string }): void;
  (e: "edit", p: { company: ProdCompany; year: number; period: string }): void;
}>();
function ctx(c: ProdCompany) { return { company: c, year: st.year.value, period: st.period.value }; }

const st = useProductionData();
// Область доступа: пользователю с одной компанией фильтры «сектор»/«компания»
// не нужны — выбирать не из чего (решение владельца 29.07.2026).
const scope = useCompanyScope();

// ─── Excel-импорт «Свода» (лист на компанию) ──────────────────
const uploadOpen = ref(false);
const importEndpoint = computed(
  () => `/production/import?year=${st.year.value}&period=${st.period.value}`,
);
function prodImportResult(data: unknown): string {
  const d = (data || {}) as {
    matched?: number; with_data?: number; lines_total?: number; unmatched?: string[];
  };
  const un = d.unmatched?.length ? ` · ${t("не распознано листов: {n}", { n: d.unmatched.length })}` : "";
  return t("Загружено: {a} компаний · {b} с данными · {c} строк", {
    a: d.matched ?? 0, b: d.with_data ?? 0, c: d.lines_total ?? 0,
  }) + un;
}
async function onImported() {
  await st.loadAvailable();
  await st.load();
}

const PERIOD_OPTS = computed(() => [
  { value: "h1", label: t("1 полугодие") },
  { value: "h2", label: t("2 полугодие") },
  { value: "annual", label: t("Год") },
]);
const SECTOR_META: Record<string, { label: string; color: string }> = {
  mining: { label: i18nKey("Горнодоб."), color: "#9B8EC4" },
  oilgas: { label: i18nKey("Нефтегаз"), color: "#1D9E75" },
  energy: { label: i18nKey("Энергетика"), color: "#EF9F27" },
  transport: { label: i18nKey("Транспорт"), color: "#378ADD" },
  other: { label: i18nKey("Прочие"), color: "#888780" },
};

onMounted(async () => { await st.loadAvailable(); await st.load(); });

// ─── filters + interactivity ──────────────────────────────────
const sectorFilter = ref<string | null>(null);
const companyFilter = ref<string | null>(null);
const overparOnly = ref(false);
const sortKey = ref<"exec" | "plan" | "exp" | "growth">("exp");
const chartMode = ref<"yoy" | "plan">("yoy");

const CHART_MODES = [
  { value: "yoy", label: "2025 → 2026" },
  { value: "plan", label: i18nKey("План · Ожид") },
];

// ─── formatting ───────────────────────────────────────────────
function fmtMlrd(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "—";
  return Math.round(v).toLocaleString(getCurrentIntlLocale(), { maximumFractionDigits: 0 });
}
function fmtTrln(v: number | null | undefined): number {
  if (v == null || !isFinite(v)) return 0;
  return Math.round(v / 100) / 10;
}

// ─── execution zones ──────────────────────────────────────────
// P0 аудита: пороги исполнения — единый платформенный канон execBand (80/50,
// >110 переисполнение), pctCol/pctZone импортированы. Раньше был инлайн 90/75 с
// врущим комментарием «mirror forensic» (форензик давно на 80/50) → расхождение.
function growthCol(g: number | null | undefined): string {
  if (g == null) return "var(--t3, #94A3B8)";
  if (g >= 100) return "#1D9E75"; if (g >= 85) return "#D97706"; return "#993D3D";
}

// ─── derived ──────────────────────────────────────────────────
const companies = computed(() => st.data.value?.companies || []);

const sectorChips = computed(() => {
  const cnt: Record<string, number> = {};
  for (const c of companies.value) cnt[c.s] = (cnt[c.s] || 0) + 1;
  return Object.keys(SECTOR_META).filter((s) => cnt[s]).map((s) => ({
    key: s, label: SECTOR_META[s].label, color: SECTOR_META[s].color, count: cnt[s],
  }));
});
const companyOptions = computed(() =>
  companies.value.slice().sort((a, b) => a.n.localeCompare(b.n, getCurrentIntlLocale())).map((c) => ({ value: c.k, label: c.n })));

const filtered = computed(() => {
  let list = companies.value;
  if (sectorFilter.value) list = list.filter((c) => c.s === sectorFilter.value);
  if (companyFilter.value) list = list.filter((c) => c.k === companyFilter.value);
  if (overparOnly.value) list = list.filter((c) => c.execPct != null && c.execPct > 110);
  return list;
});

// KPI пересчитываются от отфильтрованного набора — карточки реагируют на фильтр
const fKpis = computed(() => {
  let plan = 0, exp = 0, base = 0, wd = 0, overpar = 0, over = 0, under = 0;
  for (const c of filtered.value) {
    if (c.has_data) wd++;
    if (c.planM != null) plan += c.planM;
    if (c.expM != null) exp += c.expM;
    if (c.baseM != null && c.expM != null) base += c.baseM;
    if (c.execPct != null) {
      if (c.execPct > 110) { overpar++; over++; }
      else if (c.execPct >= 90) over++;
      else under++;
    }
  }
  const execPct = plan > 0 ? Math.round(exp / plan * 1000) / 10 : null;
  const yoy = base > 0 ? Math.round(exp / base * 1000) / 10 : null;
  return { present: filtered.value.length, with_data: wd, plan_total: plan, expect_total: exp,
    exec_pct: execPct, yoy, over, under, overpar };
});

// ─── «факт-режим» (год без плана: 2025 = только фактические объёмы) ───
// В базовом году план/ожидаемое/исполнение не заводятся — чтобы не плодить
// пустые колонки и вопросы, дашборд переключается на компактный вид:
// фактический выпуск + доля в портфеле (вместо план/ожид/темп/исполнение).
const factOnly = computed(() => {
  const list = companies.value;
  return list.length > 0 && !list.some((c) => c.planM != null) && list.some((c) => c.expM != null);
});
const factTotal = computed(() => filtered.value.reduce((s, c) => s + (c.expM || 0), 0));
function shareOf(v: number | null | undefined): number | null {
  const t = factTotal.value;
  if (v == null || t <= 0) return null;
  return Math.round((v / t) * 1000) / 10;
}
const factRows = computed(() =>
  filtered.value.filter((c) => c.expM != null).slice().sort((a, b) => (b.expM || 0) - (a.expM || 0)));
const factChartRows = computed(() => {
  const rows = factRows.value;
  const max = Math.max(1, ...rows.map((c) => c.expM || 0));
  return rows.slice(0, 12).map((c) => ({ c, w: ((c.expM || 0) / max) * 100, share: shareOf(c.expM) }));
});

const sortedRows = computed(() => {
  const key = sortKey.value;
  return filtered.value.slice().sort((a, b) => {
    const va = key === "exec" ? (a.execPct ?? -1) : key === "growth" ? (a.growthPct ?? -1) : key === "plan" ? (a.planM ?? -1) : (a.expM ?? -1);
    const vb = key === "exec" ? (b.execPct ?? -1) : key === "growth" ? (b.growthPct ?? -1) : key === "plan" ? (b.planM ?? -1) : (b.expM ?? -1);
    return vb - va;
  });
});

const chartRows = computed(() => {
  const rows = filtered.value.filter((c) => (c.expM != null || c.planM != null || c.baseM != null));
  const max = Math.max(1, ...rows.map((c) => Math.max(c.planM || 0, c.expM || 0, c.baseM || 0)));
  return rows.slice()
    .sort((a, b) => (b.expM || b.planM || 0) - (a.expM || a.planM || 0))
    .slice(0, 12)
    .map((c) => ({
      c,
      baseW: ((c.baseM || 0) / max) * 100,
      planW: ((c.planM || 0) / max) * 100,
      expW: ((c.expM || 0) / max) * 100,
    }));
});

// ─── readout строки графика: показать план/ожид/исполнение вместе ───
// «План·Ожид»: базовая = план, %-число = исполнение (exp/plan).
// «2025→2026»: базовая = факт 2025, %-число = темп роста (exp/base).
function rowBaseM(c: ProdCompany): number | null | undefined { return chartMode.value === "yoy" ? c.baseM : c.planM; }
function rowPct(c: ProdCompany): number | null | undefined { return chartMode.value === "yoy" ? c.growthPct : c.execPct; }
function rowPctCol(c: ProdCompany): string { return chartMode.value === "yoy" ? growthCol(c.growthPct) : pctCol(c.execPct); }

function setSector(s: string | null) { sectorFilter.value = sectorFilter.value === s ? null : s; }
function clearFilters() { sectorFilter.value = null; companyFilter.value = null; overparOnly.value = false; }
const hasFilter = computed(() => !!(sectorFilter.value || companyFilter.value || overparOnly.value));

// ─── count-up (re-scan on data / filter change) ───────────────
const scanRoot = ref<HTMLElement | null>(null);
const { rescan } = useCountUpScan(scanRoot, { baseDelay: 50, stagger: 70 });
watch([() => st.data.value, filtered], async () => { await nextTick(); rescan(); });
</script>

<template>
  <div class="pd">
    <!-- ═══ Control row ═══ -->
    <div class="pd-ctrl">
      <UzaSegment :options="PERIOD_OPTS" :model-value="st.period.value"
                  @update:model-value="(v) => st.setPeriod(v as string)" :label="t('Период')" />
      <UzaYearStepper :years="st.availableYears.value" :model-value="st.year.value"
                      @update:model-value="(v) => st.setYear(v)" prefix="FY " :label="t('Год')" />
      <button v-if="canImport" class="pd-import" @click="uploadOpen = true" :title="t('Импорт «Свода» из Excel')">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
        {{ t("Импорт") }}
      </button>
    </div>

    <ForensicUploadModal
      v-if="uploadOpen"
      :endpoint="importEndpoint"
      :title="t('Импорт производственного «Свода» · Excel')"
      :description="t('Файл с листом на компанию (натура + деньги: база → план → ожидаемое). Загрузится в период FY {y} · {p}.', { y: st.year.value, p: st.period.value.toUpperCase() })"
      :sheet-match="null"
      :format-result="prodImportResult"
      @uploaded="onImported"
      @close="uploadOpen = false"
    />

    <UzaStateBlock v-if="st.loading.value && !st.data.value" state="loading" variant="text" :loadingText="t('Загрузка…')" />
    <UzaStateBlock v-else-if="st.error.value" state="error" variant="block" :text="st.error.value" />
    <UzaStateBlock v-else-if="st.data.value && !companies.length" state="empty" variant="block"
                   :text="t('Нет производственных данных за выбранный период.')" />

    <div v-else-if="st.data.value" ref="scanRoot" class="pd-body">
      <!-- ═══ Filter chips ═══ -->
      <!-- Селекторы секторов и компаний скрыты, если пользователь ограничен
           одной компанией: выбирать не из чего, данные и так только её. -->
      <div v-if="scope.showSectorPicker.value || scope.showCompanyPicker.value || hasFilter" class="pd-filters">
        <template v-if="scope.showSectorPicker.value">
          <span class="pd-fl-l">{{ t("Сектор") }}:</span>
          <button class="pd-chip" :class="{ on: !sectorFilter }" @click="setSector(null)">{{ t("Все") }} <b>{{ companies.length }}</b></button>
          <button v-for="s in sectorChips" :key="s.key" class="pd-chip" :class="{ on: sectorFilter === s.key }"
                  :style="sectorFilter === s.key ? { background: s.color + '18', borderColor: s.color, color: s.color } : {}"
                  @click="setSector(s.key)">
            <span class="pd-chip-dot" :style="{ background: s.color }" />{{ t(s.label) }} <b>{{ s.count }}</b>
          </button>
        </template>
        <span class="pd-fl-sp" />
        <select v-if="scope.showCompanyPicker.value" class="pd-co-select" :value="companyFilter || ''" @change="companyFilter = ($event.target as HTMLSelectElement).value || null">
          <option value="">{{ t("Все компании") }}</option>
          <option v-for="o in companyOptions" :key="o.value" :value="o.value">{{ t(o.label) }}</option>
        </select>
        <button v-if="hasFilter" class="pd-clear" @click="clearFilters">× {{ t("сбросить") }}</button>
      </div>

      <!-- ═══ Fact-only notice (базовый год без плана) ═══ -->
      <div v-if="factOnly" class="pd-note">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
        <span>{{ t("За {y} заведены только фактические объёмы выпуска — плановый год ещё не открыт. План, ожидаемое и исполнение появятся для планового периода (2026).", { y: st.year.value }) }}</span>
      </div>

      <!-- ═══ KPI strip — факт-режим (только объём) ═══ -->
      <div v-if="factOnly" class="pd-kpi-rail kpi-rail">
        <div class="kpi2 fin-shimmer pd-kpi-click" :class="{ act: true }" style="--kpi2-accent:#1D9E75; --kpi2-d:0ms" :title="t('Совокупный фактический выпуск')">
          <div class="kpi2-lbl">{{ t("Фактический выпуск") }}</div>
          <div class="kpi2-val"><span :data-countup="fmtTrln(fKpis.expect_total)">{{ fmtTrln(fKpis.expect_total) }}</span></div>
          <div class="kpi2-sub">{{ t("трлн сум") }} · {{ st.year.value }}</div>
        </div>
        <div class="kpi2 fin-shimmer" style="--kpi2-accent:#378ADD; --kpi2-d:80ms">
          <div class="kpi2-lbl">{{ t("Компаний с фактом") }}</div>
          <div class="kpi2-val"><span :data-countup="fKpis.with_data">{{ fKpis.with_data }}</span><span class="pd-of"> / {{ fKpis.present }}</span></div>
          <div class="kpi2-sub">{{ t("заполнено в периметре") }}</div>
        </div>
        <div class="kpi2 fin-shimmer" style="--kpi2-accent:#9B8EC4; --kpi2-d:160ms">
          <div class="kpi2-lbl">{{ t("Секторов") }}</div>
          <div class="kpi2-val"><span :data-countup="sectorChips.length">{{ sectorChips.length }}</span></div>
          <div class="kpi2-sub">{{ t("в периметре") }}</div>
        </div>
        <div v-if="factRows.length" class="kpi2 fin-shimmer" style="--kpi2-accent:#EF9F27; --kpi2-d:240ms">
          <div class="kpi2-lbl">{{ t("Крупнейший выпуск") }}</div>
          <div class="kpi2-val pd-lead-name" :title="factRows[0].n">{{ factRows[0].n }}</div>
          <div class="kpi2-sub">{{ t("{n}% портфеля", { n: shareOf(factRows[0].expM) }) }}</div>
        </div>
      </div>

      <!-- ═══ KPI strip (clickable) ═══ -->
      <div v-else class="pd-kpi-rail kpi-rail">
        <div class="kpi2 fin-shimmer pd-kpi-click" :style="{ '--kpi2-accent': pctCol(fKpis.exec_pct), '--kpi2-d': '0ms' }"
             @click="sortKey = 'exec'" :class="{ act: sortKey === 'exec' }" :title="t('Сортировать по исполнению')">
          <div class="kpi2-lbl">{{ t("Сводное исполнение") }}</div>
          <div class="kpi2-val" :style="{ color: pctCol(fKpis.exec_pct) }">
            <span :data-countup="fKpis.exec_pct ?? 0">{{ fKpis.exec_pct ?? 0 }}</span><span class="pd-pct">%</span>
          </div>
          <div class="kpi2-sub">{{ t(pctZone(fKpis.exec_pct)) || t('ожид / план') }}</div>
        </div>
        <div class="kpi2 fin-shimmer pd-kpi-click" style="--kpi2-accent:#7F77DD; --kpi2-d:80ms"
             @click="sortKey = 'plan'" :class="{ act: sortKey === 'plan' }" :title="t('Сортировать по плану')">
          <div class="kpi2-lbl">{{ t("План выпуска") }}</div>
          <div class="kpi2-val"><span :data-countup="fmtTrln(fKpis.plan_total)">{{ fmtTrln(fKpis.plan_total) }}</span></div>
          <div class="kpi2-sub">{{ t("трлн сум") }}</div>
        </div>
        <div class="kpi2 fin-shimmer pd-kpi-click" style="--kpi2-accent:#1D9E75; --kpi2-d:160ms"
             @click="sortKey = 'exp'" :class="{ act: sortKey === 'exp' }" :title="t('Сортировать по ожидаемому')">
          <div class="kpi2-lbl">{{ t("Ожидаемое") }}</div>
          <div class="kpi2-val"><span :data-countup="fmtTrln(fKpis.expect_total)">{{ fmtTrln(fKpis.expect_total) }}</span></div>
          <div class="kpi2-sub">{{ t("трлн сум") }}
            <span v-if="fKpis.yoy != null" class="pd-yoy" :style="{ color: growthCol(fKpis.yoy) }">
              · {{ fKpis.yoy >= 100 ? '↑' : '↓' }} {{ t("{n}% к 2025", { n: fKpis.yoy }) }}</span>
          </div>
        </div>
        <div class="kpi2 fin-shimmer" :class="{ 'pd-kpi-click': fKpis.overpar > 0, act: overparOnly }"
             style="--kpi2-accent:#378ADD; --kpi2-d:240ms"
             @click="fKpis.overpar > 0 && (overparOnly = !overparOnly)"
             :title="fKpis.overpar > 0 ? t('Показать переисполнение') : ''">
          <div class="kpi2-lbl">{{ t("Покрытие данными") }}</div>
          <div class="kpi2-val">
            <span :data-countup="fKpis.with_data">{{ fKpis.with_data }}</span><span class="pd-of"> / {{ fKpis.present }}</span>
          </div>
          <div class="kpi2-sub" v-if="fKpis.overpar" :style="{ color: overparOnly ? '#7C3AED' : '' }">⚑ {{ t("переисполнение: {n}", { n: fKpis.overpar }) }}</div>
          <div class="kpi2-sub" v-else>{{ t("компаний с данными") }}</div>
        </div>
      </div>

      <!-- ═══ Two-col: table + chart ═══ -->
      <div class="pd-grid">
        <!-- Company table -->
        <div class="pd-card">
          <div class="pd-card-h">
            <span class="pd-card-t">{{ t("Свод по компаниям") }}</span>
            <span class="pd-card-meta">{{ factOnly ? factRows.length : filtered.length }} · {{ t("млрд UZS") }}</span>
          </div>
          <div class="pd-tbl-wrap">
            <!-- Плановый год: план / ожид / темп / исполнение -->
            <table v-if="!factOnly" class="pd-tbl">
              <thead>
                <tr>
                  <th class="lt">{{ t("Компания") }}</th>
                  <th class="rt srt" :class="{ on: sortKey === 'plan' }" @click="sortKey = 'plan'">{{ t("План") }}</th>
                  <th class="rt srt" :class="{ on: sortKey === 'exp' }" @click="sortKey = 'exp'">{{ t("Ожид.") }}</th>
                  <th class="rt srt" :class="{ on: sortKey === 'growth' }" @click="sortKey = 'growth'">{{ t("Темп") }}</th>
                  <th class="rt srt" :class="{ on: sortKey === 'exec' }" @click="sortKey = 'exec'">{{ t("Исполнение") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(c, i) in sortedRows" :key="c.k"
                    class="pd-row" :class="{ 'no-data': !c.has_data }"
                    :style="{ animationDelay: (Math.min(i, 24) * 22) + 'ms' }"
                    @click="c.has_data ? emit('drill', ctx(c)) : emit('edit', ctx(c))"
                    :title="c.has_data ? t('Открыть детализацию') : t('Заполнить данные')">
                  <td class="lt">
                    <CompanyAvatar :name="c.n" :color="c.sector_color || '#888780'" :size="20" />
                    <span class="pd-co-name">{{ c.n }}</span>
                  </td>
                  <td class="rt num muted">{{ fmtMlrd(c.planM) }}</td>
                  <td class="rt num muted">{{ fmtMlrd(c.expM) }}</td>
                  <td class="rt num" :style="{ color: growthCol(c.growthPct) }">
                    {{ c.growthPct != null ? c.growthPct + '%' : '—' }}
                  </td>
                  <td class="rt num" :style="{ color: pctCol(c.execPct), fontWeight: 600 }" :title="t(pctZone(c.execPct))">
                    <template v-if="c.execState === 'pct'">
                      {{ c.execPct }}%<span v-if="c.execBasis === 'natura'" class="pd-basis" :title="t('по натуральному объёму')">{{ t("н") }}</span>
                    </template>
                    <span v-else-if="c.execState === 'nofact'" class="pd-nd">{{ t("факт —") }}</span>
                    <span v-else class="pd-nd">{{ t("нет данных") }}</span>
                  </td>
                </tr>
                <tr v-if="!sortedRows.length"><td colspan="5"><UzaStateBlock state="empty" variant="inline" :text="t('Нет компаний по фильтру')" /></td></tr>
              </tbody>
            </table>

            <!-- Базовый год (2025): только факт + доля портфеля -->
            <table v-else class="pd-tbl">
              <thead>
                <tr>
                  <th class="lt">{{ t("Компания") }}</th>
                  <th class="rt">{{ t("Факт выпуска") }}</th>
                  <th class="rt pd-share-h">{{ t("Доля портфеля") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(c, i) in factRows" :key="c.k" class="pd-row"
                    :style="{ animationDelay: (Math.min(i, 24) * 22) + 'ms' }"
                    @click="emit('drill', ctx(c))" :title="t('Открыть детализацию')">
                  <td class="lt">
                    <CompanyAvatar :name="c.n" :color="c.sector_color || '#888780'" :size="20" />
                    <span class="pd-co-name">{{ c.n }}</span>
                  </td>
                  <td class="rt num">{{ fmtMlrd(c.expM) }}</td>
                  <td class="rt">
                    <div class="pd-share">
                      <div class="pd-share-track"><div class="pd-share-bar" :style="{ width: (shareOf(c.expM) || 0) + '%', background: c.sector_color || '#7F77DD' }" /></div>
                      <span class="pd-share-v">{{ shareOf(c.expM) != null ? shareOf(c.expM) + '%' : '—' }}</span>
                    </div>
                  </td>
                </tr>
                <tr v-if="!factRows.length"><td colspan="3"><UzaStateBlock state="empty" variant="inline" :text="t('Нет компаний по фильтру')" /></td></tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Comparison chart -->
        <div class="pd-card">
          <div class="pd-card-h">
            <span class="pd-card-t">{{ factOnly ? t('Структура выпуска') : t('Сравнение') }}</span>
            <div v-if="!factOnly" class="uza-seg is-sm">
              <button v-for="(m, i) in CHART_MODES" :key="m.value" type="button" class="uza-seg-btn" :class="{ on: chartMode === m.value }"
                      :style="{ '--i': i }" @click="chartMode = m.value as 'yoy' | 'plan'">{{ t(m.label) }}</button>
            </div>
          </div>

          <!-- Плановый год: два бара (база/план vs ожид.) -->
          <template v-if="!factOnly">
            <div class="pd-chart-legend">
              <span class="pd-lg"><i :style="{ background: chartMode === 'yoy' ? '#B8C0D9' : '#C7C2F0' }" /> {{ chartMode === 'yoy' ? t('2025 факт') : t('план') }}</span>
              <span class="pd-lg"><i style="background:#7F77DD" /> {{ chartMode === 'yoy' ? t('2026 ожид.') : t('ожид.') }}</span>
              <span class="pd-lg pd-lg-txt">% {{ chartMode === 'yoy' ? t('темп роста') : t('исполнение') }}</span>
            </div>
            <div class="pd-chart">
              <div v-for="(r, i) in chartRows" :key="r.c.k" class="pd-bar-row"
                   :style="{ animationDelay: (i * 40) + 'ms' }" @click="emit('drill', ctx(r.c))" :title="t('Открыть детализацию')">
                <span class="pd-bar-name">{{ r.c.n }}</span>
                <div class="pd-bar-track">
                  <div class="pd-bar b1" :style="{ width: (chartMode === 'yoy' ? r.baseW : r.planW) + '%', background: chartMode === 'yoy' ? '#B8C0D9' : '#C7C2F0' }" />
                  <div class="pd-bar exp" :style="{ width: r.expW + '%', background: rowPctCol(r.c) }" />
                </div>
                <div class="pd-readout">
                  <span class="pd-readout-pct" :style="{ color: rowPctCol(r.c) }">{{ rowPct(r.c) != null ? rowPct(r.c) + '%' : '—' }}</span>
                  <span class="pd-readout-vals" :title="chartMode === 'yoy' ? t('факт 2025 → ожид. 2026') : t('план → ожид., млрд UZS')">
                    {{ fmtMlrd(rowBaseM(r.c)) }}<b>→</b>{{ fmtMlrd(r.c.expM) }}
                  </span>
                </div>
              </div>
              <div v-if="!chartRows.length" class="pd-chart-empty">{{ t("Нет числовых данных для графика") }}</div>
            </div>
          </template>

          <!-- Базовый год: один бар (доля фактического выпуска) -->
          <template v-else>
            <div class="pd-chart-legend"><span class="pd-lg"><i style="background:#7F77DD" /> {{ t("факт выпуска · доля в портфеле") }}</span></div>
            <div class="pd-chart">
              <div v-for="(r, i) in factChartRows" :key="r.c.k" class="pd-bar-row pd-bar-row-1"
                   :style="{ animationDelay: (i * 40) + 'ms' }" @click="emit('drill', ctx(r.c))" :title="t('Открыть детализацию')">
                <span class="pd-bar-name">{{ r.c.n }}</span>
                <div class="pd-bar-track pd-track-1">
                  <div class="pd-bar single" :style="{ width: r.w + '%', background: r.c.sector_color || '#7F77DD' }" />
                </div>
                <span class="pd-bar-pct">{{ r.share != null ? r.share + '%' : '—' }}</span>
              </div>
              <div v-if="!factChartRows.length" class="pd-chart-empty">{{ t("Нет числовых данных для графика") }}</div>
            </div>
          </template>
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
.pd-import {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 13px; border-radius: 999px;
  border: 1px solid rgba(127,119,221,.28); background: var(--bg1, #fff);
  font: 600 12px inherit; color: var(--p-deep, #534AB7);
  cursor: pointer; transition: all .14s;
}
.pd-import:hover { background: rgba(127,119,221,.08); border-color: #7F77DD; }
.pd-import svg { opacity: .85; }
.pd-body { padding: 14px 20px 24px; }

/* Filters */
.pd-filters { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; margin-bottom: 12px; }
.pd-fl-l { font-size: 10.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #64748b); margin-right: 2px; }
.pd-fl-sp { flex: 1; min-width: 10px; }
.pd-chip { display: inline-flex; align-items: center; gap: 6px; padding: 4px 11px; border-radius: 999px;
  border: 1px solid rgba(99,102,180,.20); background: var(--bg1, #fff); font: 500 12px inherit; color: var(--t2, #475569);
  cursor: pointer; transition: background .13s, border-color .13s, color .13s, box-shadow .13s; }
.pd-chip:hover { border-color: rgba(99,102,180,.42); background: rgba(127,119,221,.04); }
.pd-chip.on { font-weight: 600; box-shadow: 0 1px 5px rgba(15,23,60,.09); }
.pd-chip b { font-weight: 700; font-feature-settings: 'tnum'; opacity: .7; }
.pd-chip-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pd-co-select { padding: 5px 10px; border-radius: 8px; border: 1px solid rgba(99,102,180,.22); background: var(--bg1, #fff);
  font: 500 12px inherit; color: var(--t1, #1E2A4A); cursor: pointer; max-width: 220px; }
.pd-clear { border: none; background: transparent; color: var(--t3, #94A3B8); font: 500 12px inherit; cursor: pointer; padding: 4px 6px; }
.pd-clear:hover { color: var(--sev-high, #E24B4A); }

/* KPI */
.pd-kpi-rail { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }
@media (max-width: 1100px) { .pd-kpi-rail { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px)  { .pd-kpi-rail { grid-template-columns: 1fr; } }
.pd-kpi-click { cursor: pointer; transition: transform .18s, box-shadow .18s, border-color .18s; }
.pd-kpi-click:hover { transform: translateY(-3px) scale(1.01); box-shadow: 0 12px 30px rgba(15,23,60,.12); }
.pd-kpi-click.act { box-shadow: 0 0 0 1.5px rgba(124,111,247,.4), 0 8px 22px rgba(15,23,60,.10); }
.pd-pct { font-size: 18px; color: var(--t3, var(--t-muted)); font-weight: 400; margin-left: 1px; }
.pd-of { font-size: 16px; color: var(--t3, var(--t-muted)); font-weight: 500; }
.pd-yoy { font-weight: 600; font-feature-settings: 'tnum'; }
.pd-lead-name { font-size: 15px !important; font-weight: 600; line-height: 1.2; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* Fact-only notice */
.pd-note {
  display: flex; align-items: center; gap: 9px; margin-bottom: 12px;
  padding: 9px 13px; border-radius: 10px;
  background: linear-gradient(135deg, rgba(127,119,221,.07), rgba(127,119,221,.03));
  border: 1px solid rgba(127,119,221,.18);
  font-size: 12px; color: var(--t2, #475569); line-height: 1.35;
  animation: pdCardIn .4s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both;
}
.pd-note svg { color: var(--p-deep, #7F77DD); flex-shrink: 0; }
.pd-note b { color: var(--t1, #1E2A4A); font-weight: 600; }

/* Fact-only share column (доля портфеля) */
.pd-share-h { min-width: 130px; }
.pd-share { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }
.pd-share-track { flex: 1; max-width: 84px; height: 6px; border-radius: 3px; background: var(--bg2, #F1F0F7); overflow: hidden; }
.pd-share-bar { height: 100%; border-radius: 3px; transform-origin: left center;
  animation: pdBarPour .55s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both; }
.pd-share-v { font-size: 12px; font-weight: 600; font-feature-settings: 'tnum'; color: var(--t1, #1E2A4A); min-width: 40px; text-align: right; }

.pd-grid { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 12px; }
@media (max-width: 1200px) { .pd-grid { grid-template-columns: 1fr; } }
.pd-card { background: var(--bg1, #fff); border: 1px solid rgba(0,0,0,.05); border-radius: 12px; overflow: hidden;
  display: flex; flex-direction: column; animation: pdCardIn .5s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both; }
@keyframes pdCardIn { 0% { opacity: 0; transform: translateY(10px) scale(.99); } 100% { opacity: 1; transform: none; } }
.pd-card-h { padding: 12px 16px; border-bottom: 0.5px solid rgba(0,0,0,.06); display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.pd-card-t { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); text-transform: uppercase; letter-spacing: .04em; }
.pd-card-meta { font-size: 11px; color: var(--t3, var(--t-muted)); }
.pd-chart-legend { display: flex; gap: 14px; padding: 8px 16px 0; font-size: 11px; color: var(--t3, var(--t-muted)); }
.pd-lg { display: inline-flex; align-items: center; gap: 5px; }
.pd-lg i { width: 9px; height: 9px; border-radius: 2px; display: inline-block; }
.pd-lg-txt { margin-left: auto; font-weight: 600; letter-spacing: .01em; }

/* Table */
.pd-tbl-wrap { max-height: 460px; overflow-y: auto; scrollbar-width: thin; }
.pd-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.pd-tbl thead th { position: sticky; top: 0; z-index: 1; background: var(--bg2, #FAFAFC); padding: 8px 12px; font-size: 10px;
  font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, var(--t-muted)); border-bottom: 0.5px solid rgba(0,0,0,.05); }
.pd-tbl th.lt { text-align: left; } .pd-tbl th.rt { text-align: right; }
.pd-tbl th.srt { cursor: pointer; user-select: none; transition: color .12s; }
.pd-tbl th.srt:hover { color: var(--p-deep, #534AB7); }
.pd-tbl th.srt.on { color: var(--p-deep, #534AB7); }
.pd-tbl tbody td { padding: 7px 12px; border-bottom: 0.5px solid rgba(0,0,0,.04); color: var(--t1, #1E2A4A); }
.pd-tbl td.lt { display: flex; align-items: center; gap: 7px; }
.pd-tbl td.rt { text-align: right; } .pd-tbl td.num { font-feature-settings: 'tnum'; }
.pd-tbl td.muted { color: var(--t3, var(--t-muted)); }
.pd-co-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 500; }
.pd-row { cursor: pointer; transition: background .12s; animation: pdRowIn .3s cubic-bezier(.34,1.1,.64,1) both; }
@keyframes pdRowIn { 0% { opacity: 0; transform: translateX(-4px); } 100% { opacity: 1; transform: none; } }
.pd-row:hover { background: rgba(127,119,221,.05); }
.pd-row.no-data { opacity: .6; }
.pd-nd { color: var(--t3, var(--t-muted)); font-style: italic; font-weight: 400; font-size: 11px; }
.pd-basis { font-size: 9px; vertical-align: super; margin-left: 1px; color: var(--t3, var(--t-muted)); }

/* Chart */
.pd-chart { padding: 10px 16px 14px; overflow-y: auto; max-height: 430px; scrollbar-width: thin; }
.pd-bar-row { display: grid; grid-template-columns: 104px 1fr 118px; align-items: center; gap: 10px; padding: 5px 0; cursor: pointer;
  animation: pdRowIn .3s cubic-bezier(.34,1.1,.64,1) both; border-radius: 6px; transition: background .12s; }
.pd-bar-row-1 { grid-template-columns: 104px 1fr 56px; }
.pd-bar-row:hover { background: rgba(127,119,221,.05); }
.pd-bar-name { font-size: 11.5px; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-left: 4px; }
.pd-bar-track { position: relative; height: 16px; }
.pd-bar { position: absolute; left: 0; height: 7px; border-radius: 4px;
  animation: pdBarPour .55s var(--ease-standard, cubic-bezier(.34,1.1,.64,1)) both; transform-origin: left center; }
.pd-bar.b1 { top: 0; } .pd-bar.exp { top: 9px; }
.pd-track-1 { height: 14px; } .pd-bar.single { top: 3px; height: 8px; }
@keyframes pdBarPour { 0% { transform: scaleX(0); opacity: 0; } 100% { transform: scaleX(1); opacity: 1; } }
.pd-bar-pct { font-size: 11.5px; font-weight: 600; text-align: right; font-feature-settings: 'tnum'; }
/* readout: исполнение% (крупно) + план→ожид (мелко) — все три метрики в строке */
.pd-readout { display: flex; flex-direction: column; align-items: flex-end; gap: 0; line-height: 1.15; }
.pd-readout-pct { font-size: 12.5px; font-weight: 600; font-feature-settings: 'tnum'; }
.pd-readout-vals { font-size: 10px; color: var(--t3, var(--t-muted)); font-feature-settings: 'tnum'; white-space: nowrap; }
.pd-readout-vals b { color: var(--t3, #B8B4C8); font-weight: 400; margin: 0 3px; }
.pd-chart-empty { padding: 30px; text-align: center; font-size: 12px; color: var(--t3, var(--t-muted)); font-style: italic; }
</style>
