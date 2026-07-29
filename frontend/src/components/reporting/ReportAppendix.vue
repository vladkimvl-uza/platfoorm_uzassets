<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();
/**
 * ReportAppendix — опциональные премиум-секции в конце «Отчёта по проектам»:
 *   1. Статус-матрица (направления × статусы) — тепловая сетка.
 *   2. Основные фин. показатели (последний доступный год) — редактируемые.
 *   3. Исполнение KPI (за выбранный период) — редактируемое.
 *   4. Исполнение бизнес-плана (за выбранный период) — редактируемое.
 *
 * Чистый presentation-компонент: получает готовые view-model'и от родителя,
 * рендерит. `readonly` → печатный/экспортный вид (без инпутов). Правки уходят
 * наверх через emit('edit', kind, key, value) — родитель пишет их в оверрайды
 * report_wizard config. Палитра — СТРОГО фирменная монохромная (без «светофора»).
 */
interface MatrixCol { key: string; label: string }
interface MatrixData { dirRows: any[]; colTotals: Record<string, number>; grand: number; maxCell: number }
interface FinRow { key: string; label: string; cur: number | null; prev: number | null; yoy: number | null; curKey: string; prevKey: string }
interface FinData { loading: boolean; standard: string; year: number; prev: number; rows: FinRow[]; empty: boolean }
interface KpiInd { id: string; name: string; unit: string | null; weight: number; plan: number | null; fact: number | null; ratio: number | null; planKey: string; factKey: string }
interface KpiGroup { id: string; title: string; role: string | null; inds: KpiInd[] }
interface KpiData { loading: boolean; overall: number | null; periodLabel: string; year: number; groups: KpiGroup[]; empty: boolean }
interface BpRow { key: string; label: string; group: string; auto: boolean; plan: number | null; expect: number | null; fact: number | null; ratio: number | null; planKey: string; expectKey: string; factKey: string }
interface BpData { loading: boolean; overall: number | null; periodLabel: string; year: number; rows: BpRow[]; empty: boolean }
interface RatRow { agency: string; rating: string; outlook: string; date: string; ratingKey: string; outlookKey: string; dateKey: string }
interface RatData { empty: boolean; credit: RatRow[]; esg: RatRow[] }

const props = defineProps<{
  readonly?: boolean;
  show: { matrix: boolean; fin: boolean; kpi: boolean; bp: boolean; ratings: boolean };
  matrix: MatrixData;
  matrixCols: MatrixCol[];
  fin: FinData;
  kpi: KpiData;
  bp: BpData;
  rat: RatData;
}>();

const emit = defineEmits<{ (e: "edit", kind: "fin" | "kpi" | "bp" | "rat", key: string, value: string): void }>();
function onEdit(kind: "fin" | "kpi" | "bp" | "rat", key: string, ev: Event) {
  emit("edit", kind, key, (ev.target as HTMLInputElement).value);
}

// ─── Форматирование (млрд / %), всё в фирменной монохромной палитре ──
function money(v: number | null): string {
  if (v == null) return "—";
  const a = Math.abs(v);
  let s: string;
  if (a >= 1000) s = Math.round(v).toLocaleString("ru-RU");
  else if (a >= 10) s = v.toLocaleString("ru-RU", { maximumFractionDigits: 1 });
  else s = v.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
  return s.replace(/,/g, " ");
}
function pct(r: number | null): string { return r == null ? "—" : Math.round(r * 100) + "%"; }
function yoyText(r: number | null): string { if (r == null) return ""; const p = Math.round(r * 100); return (p > 0 ? "+" : p < 0 ? "−" : "") + Math.abs(p) + "%"; }
// Бренд-моно «исполнение»: интенсивность индиго растёт с показателем (без свет-фора).
function pctStyle(r: number | null): Record<string, string> {
  if (r == null) return { color: "#9AA0B4" };
  const a = 0.12 + 0.46 * Math.min(Math.max(r, 0), 1.2) / 1.2;
  return { background: `rgba(30,39,135,${a.toFixed(3)})`, color: a > 0.40 ? "#FFFFFF" : "#23264A" };
}
function mxCellStyle(colKey: string, n: number): Record<string, string> {
  if (!n) return {};
  const a = 0.10 + 0.42 * (n / (props.matrix.maxCell || 1));
  const rgb = colKey === "done" ? "30,39,135" : "83,74,183";
  return { background: `rgba(${rgb},${a.toFixed(3)})`, color: a > 0.42 ? "#FFFFFF" : "#23264A", fontWeight: "600" };
}
const BP_GROUP_LABEL: Record<string, string> = {
  opRevenue: i18nKey("Операционная выручка"), opExpenses: i18nKey("Расходы периода"),
  opResult: i18nKey("Операционный результат"), finActivity: i18nKey("Финансовая деятельность"), final: i18nKey("Итоговый результат"),
};
</script>

<template>
  <div class="apx" :class="{ ro: readonly }">
    <!-- ═══ 1. Статус-матрица ═══ -->
    <section v-if="show.matrix && matrix.grand" class="apx-sec">
      <div class="apx-head">
        <span class="apx-title">{{ t('Статус-матрица') }}</span>
        <span class="apx-sub">{{ t('направления × статусы ·') }} {{ matrix.grand }} {{ t('элементов') }}</span>
      </div>
      <div class="apx-scroll">
        <table class="apx-tbl mx">
          <thead>
            <tr>
              <th class="c-left">{{ t('Направление') }}</th>
              <th v-for="c in matrixCols" :key="c.key">{{ t(c.label) }}</th>
              <th class="c-tot">{{ t('Всего') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="d in matrix.dirRows" :key="d.code">
              <td class="c-left"><span class="apx-dot" :style="{ background: d.color }" />{{ t(d.label) }}</td>
              <td v-for="c in matrixCols" :key="c.key" class="c-num" :style="mxCellStyle(c.key, d.counts[c.key] || 0)">{{ d.counts[c.key] || "·" }}</td>
              <td class="c-tot">{{ d.total }}</td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td class="c-left">{{ t('Итого') }}</td>
              <td v-for="c in matrixCols" :key="c.key" class="c-num">{{ matrix.colTotals[c.key] || 0 }}</td>
              <td class="c-tot">{{ matrix.grand }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <!-- ═══ 2. Основные фин. показатели ═══ -->
    <section v-if="show.fin" class="apx-sec">
      <div class="apx-head">
        <span class="apx-title">{{ t('Основные финансовые показатели') }}</span>
        <span class="apx-sub">{{ t('за') }} {{ fin.year }} {{ t('год · млрд сум ·') }} {{ fin.standard }}</span>
      </div>
      <div v-if="fin.loading" class="apx-state">{{ t('Загрузка…') }}</div>
      <div v-else-if="fin.empty" class="apx-state">{{ t('Нет финансовых данных для компании.') }}</div>
      <div v-else class="apx-scroll">
        <table class="apx-tbl fin">
          <thead>
            <tr><th class="c-left">{{ t('Показатель') }}</th><th class="c-prev">{{ fin.prev }}</th><th class="c-cur">{{ fin.year }}</th><th class="c-yoy">{{ t('Δ г/г') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in fin.rows" :key="r.key">
              <td class="c-left">{{ t(r.label) }}</td>
              <td class="c-prev">
                <template v-if="readonly">{{ money(r.prev) }}</template>
                <input v-else class="apx-in" :value="r.prev ?? ''" @change="onEdit('fin', r.prevKey, $event)" />
              </td>
              <td class="c-cur">
                <template v-if="readonly">{{ money(r.cur) }}</template>
                <input v-else class="apx-in strong" :value="r.cur ?? ''" @change="onEdit('fin', r.curKey, $event)" />
              </td>
              <td class="c-yoy" :class="{ neg: (r.yoy ?? 0) < 0 }">{{ yoyText(r.yoy) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ═══ 3. Исполнение KPI ═══ -->
    <section v-if="show.kpi" class="apx-sec">
      <div class="apx-head">
        <span class="apx-title">{{ t('Исполнение KPI') }}</span>
        <span class="apx-sub">{{ kpi.year }} · {{ t(kpi.periodLabel) }}</span>
        <span v-if="kpi.overall != null" class="apx-badge" :style="pctStyle(kpi.overall)">{{ t('Итого') }} {{ pct(kpi.overall) }}</span>
      </div>
      <div v-if="kpi.loading" class="apx-state">{{ t('Загрузка…') }}</div>
      <div v-else-if="kpi.empty" class="apx-state">{{ t('Нет данных KPI за выбранный год.') }}</div>
      <div v-else class="apx-scroll">
        <table class="apx-tbl kpi">
          <thead>
            <tr><th class="c-left">{{ t('КПЭ') }}</th><th class="c-unit">{{ t('Ед.') }}</th><th class="c-pf">{{ t('План') }}</th><th class="c-pf">{{ t('Факт') }}</th><th class="c-w">{{ t('Вес') }}</th><th class="c-exec">{{ t('Исполн.') }}</th></tr>
          </thead>
          <tbody>
            <template v-for="g in kpi.groups" :key="g.id">
              <tr class="apx-grp"><td colspan="6">{{ g.title }}<span v-if="g.role" class="apx-grp-role"> · {{ g.role }}</span></td></tr>
              <tr v-for="ind in g.inds" :key="ind.id">
                <td class="c-left">{{ ind.name }}</td>
                <td class="c-unit">{{ ind.unit || "—" }}</td>
                <td class="c-pf">
                  <template v-if="readonly">{{ money(ind.plan) }}</template>
                  <input v-else class="apx-in" :value="ind.plan ?? ''" @change="onEdit('kpi', ind.planKey, $event)" />
                </td>
                <td class="c-pf">
                  <template v-if="readonly">{{ money(ind.fact) }}</template>
                  <input v-else class="apx-in" :value="ind.fact ?? ''" @change="onEdit('kpi', ind.factKey, $event)" />
                </td>
                <td class="c-w">{{ ind.weight || "—" }}</td>
                <td class="c-exec"><span class="apx-pill" :style="pctStyle(ind.ratio)">{{ pct(ind.ratio) }}</span></td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ═══ 4. Исполнение бизнес-плана ═══ -->
    <section v-if="show.bp" class="apx-sec">
      <div class="apx-head">
        <span class="apx-title">{{ t('Исполнение бизнес-плана') }}</span>
        <span class="apx-sub">{{ bp.year }} · {{ t(bp.periodLabel) }} {{ t('· млрд сум') }}</span>
        <span v-if="bp.overall != null" class="apx-badge" :style="pctStyle(bp.overall)">{{ t('Выручка') }} {{ pct(bp.overall) }}</span>
      </div>
      <div v-if="bp.loading" class="apx-state">{{ t('Загрузка…') }}</div>
      <div v-else-if="bp.empty" class="apx-state">{{ t('Нет данных бизнес-плана за выбранный период.') }}</div>
      <div v-else class="apx-scroll">
        <table class="apx-tbl bp">
          <thead>
            <tr><th class="c-left">{{ t('Показатель') }}</th><th class="c-pf">{{ t('План') }}</th><th class="c-pf">{{ t('Ожид.') }}</th><th class="c-pf">{{ t('Факт') }}</th><th class="c-exec">{{ t('Исполн.') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in bp.rows" :key="r.key" :class="{ 'apx-auto': r.auto }">
              <td class="c-left">{{ t(r.label) }}</td>
              <td class="c-pf">
                <template v-if="readonly">{{ money(r.plan) }}</template>
                <input v-else class="apx-in" :value="r.plan ?? ''" @change="onEdit('bp', r.planKey, $event)" />
              </td>
              <td class="c-pf">
                <template v-if="readonly">{{ money(r.expect) }}</template>
                <input v-else class="apx-in" :value="r.expect ?? ''" @change="onEdit('bp', r.expectKey, $event)" />
              </td>
              <td class="c-pf">
                <template v-if="readonly">{{ money(r.fact) }}</template>
                <input v-else class="apx-in" :value="r.fact ?? ''" @change="onEdit('bp', r.factKey, $event)" />
              </td>
              <td class="c-exec"><span class="apx-pill" :style="pctStyle(r.ratio)">{{ pct(r.ratio) }}</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- ═══ 5. Рейтинги (кредитные + ESG) ═══ -->
    <section v-if="show.ratings && !rat.empty" class="apx-sec">
      <div class="apx-head">
        <span class="apx-title">{{ t('Рейтинги') }}</span>
        <span class="apx-sub">{{ t('кредитные и ESG') }}</span>
      </div>
      <template v-for="grp in [{ t: i18nKey('Кредитные рейтинги'), rows: rat.credit }, { t: i18nKey('ESG-рейтинги'), rows: rat.esg }]" :key="grp.t">
        <div v-if="grp.rows.length" class="apx-scroll apx-rat-block">
          <div class="apx-subcap">{{ t(grp.t) }}</div>
          <table class="apx-tbl rat">
            <thead>
              <tr><th class="c-left">{{ t('Агентство') }}</th><th class="c-rt">{{ t('Рейтинг') }}</th><th class="c-rt">{{ t('Прогноз') }}</th><th class="c-rt">{{ t('Дата') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in grp.rows" :key="r.agency">
                <td class="c-left">{{ r.agency }}</td>
                <td class="c-rt rt-val">
                  <template v-if="readonly">{{ r.rating || "—" }}</template>
                  <input v-else class="apx-in" :value="r.rating" @change="onEdit('rat', r.ratingKey, $event)" />
                </td>
                <td class="c-rt">
                  <template v-if="readonly">{{ r.outlook || "—" }}</template>
                  <input v-else class="apx-in" :value="r.outlook" @change="onEdit('rat', r.outlookKey, $event)" />
                </td>
                <td class="c-rt">
                  <template v-if="readonly">{{ r.date || "—" }}</template>
                  <input v-else class="apx-in" :value="r.date" @change="onEdit('rat', r.dateKey, $event)" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.apx { display: flex; flex-direction: column; gap: 16px; }
.apx-sec { background: #fff; border: 1px solid rgba(99,102,180,.14); border-radius: 14px; padding: 16px 18px; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.apx.ro .apx-sec { border: none; border-radius: 0; padding: 0; box-shadow: none; margin-top: 18px; }
.apx-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 11px; flex-wrap: wrap; }
.apx-title { font-size: 13px; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; color: var(--t1, #1e2a4a); }
.apx.ro .apx-title { font-size: 12px; }
.apx-sub { font-size: 11px; color: var(--t3, #8A8C99); }
.apx-badge { margin-left: auto; font-size: 11px; font-weight: 700; padding: 3px 11px; border-radius: 999px; }
.apx-state { font-size: 12px; color: var(--t3, #8A8C99); font-style: italic; padding: 8px 2px; }
.apx-scroll { overflow-x: auto; }
/* Печать: ничего не обрезаем — таблица переносит текст и помещается в лист. */
.apx.ro .apx-scroll { overflow: visible; }

.apx-tbl { border-collapse: collapse; width: 100%; font-size: 11.5px; table-layout: fixed; }
.apx.ro .apx-tbl { font-size: 10px; }
.apx-tbl th { background: #1e2a4a; color: #fff; font-size: 9.5px; font-weight: 700; letter-spacing: .02em; text-transform: uppercase; text-align: center; padding: 6px 8px; border: 1px solid #2a375a; }
.apx.ro .apx-tbl th { font-size: 8.5px; padding: 4px 6px; }
.apx-tbl th.c-left { text-align: left; }
.apx-tbl td { border: 1px solid #E2E4EE; padding: 5px 8px; text-align: center; color: #23264A; font-variant-numeric: tabular-nums; }
.apx.ro .apx-tbl td { padding: 3px 6px; border-color: #d7d9e0; }
/* Текстовая колонка ПЕРЕНОСИТСЯ (длинные КПЭ иначе растягивают таблицу и режутся на печати). */
.apx-tbl th.c-left, .apx-tbl td.c-left { text-align: left; font-weight: 500; white-space: normal; word-break: break-word; line-height: 1.3; }
/* Числовые колонки — фикс-ширина, не переносятся; остаток ширины отдаём названию. */
.apx-tbl th.c-unit, .apx-tbl td.c-unit { width: 7%; white-space: nowrap; }
.apx-tbl th.c-pf, .apx-tbl td.c-pf { width: 12%; white-space: nowrap; }
.apx-tbl th.c-w, .apx-tbl td.c-w { width: 6%; white-space: nowrap; }
.apx-tbl th.c-exec, .apx-tbl td.c-exec { width: 9%; white-space: nowrap; }
.apx-tbl th.c-prev, .apx-tbl td.c-prev, .apx-tbl th.c-cur, .apx-tbl td.c-cur { width: 17%; white-space: nowrap; }
.apx-tbl th.c-yoy, .apx-tbl td.c-yoy { width: 9%; white-space: nowrap; }
.apx-tbl td.c-num { width: 8.5%; white-space: nowrap; }
.apx-tbl th.c-tot, .apx-tbl td.c-tot { width: 7%; white-space: nowrap; }
.apx-tbl th.c-rt, .apx-tbl td.c-rt { width: 20%; white-space: nowrap; }
.apx-tbl.rat td.rt-val { font-weight: 700; color: #1e2787; }
.apx-rat-block { margin-bottom: 10px; }
.apx-rat-block:last-child { margin-bottom: 0; }
.apx-subcap { font-size: 11px; font-weight: 700; color: #3A3D48; margin: 4px 0 5px; }
.apx-dot { display: inline-block; width: 7px; height: 7px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.apx-in { box-sizing: border-box; }

/* matrix */
.apx-tbl.mx td.c-num { font-weight: 600; }
.apx-tbl.mx td.c-tot, .apx-tbl.mx tfoot td { background: #f3f2fb; font-weight: 700; }
.apx-tbl.mx tfoot td { background: #eceaf6; font-weight: 800; }
.apx-tbl.mx tfoot td.c-tot { background: #e3e0f4; }

/* fin */
.apx-tbl.fin td.c-cur { font-weight: 700; }
.apx-tbl .c-yoy { color: #5F6270; font-size: 11px; }
.apx-tbl .c-yoy.neg { color: #8A8C99; }

/* kpi / bp groups + auto rows */
.apx-grp td { background: linear-gradient(90deg, rgba(83,74,183,.08), transparent 70%); text-align: left; font-weight: 700; font-size: 10.5px; color: var(--t1, #1e2a4a); }
.apx-grp-role { font-weight: 500; color: var(--t3, #8A8C99); }
.apx-tbl.bp tr.apx-auto td.c-left { font-weight: 700; }
.apx-tbl.bp tr.apx-auto { background: #f7f7fc; }

/* execution pill */
.apx-pill { display: inline-block; min-width: 42px; padding: 2px 9px; border-radius: 999px; font-size: 10.5px; font-weight: 700; }

/* inline edit */
.apx-in { width: 92%; max-width: 120px; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; text-align: center; border-radius: 6px; padding: 2px 4px; font-variant-numeric: tabular-nums; }
.apx-in.strong { font-weight: 700; }
.apx-in:hover { background: rgba(127,119,221,.07); }
.apx-in:focus { outline: none; border-color: #7F77DD; background: #fff; }
</style>
