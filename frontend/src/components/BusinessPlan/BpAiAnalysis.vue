<template>
  <button class="bpai-btn" @click="openModal" :disabled="loading" :title="t('ИИ-анализ бизнес-плана')">
    <span class="bpai-btn-ai">Ai</span>{{ loading ? t("Анализирую…") : t("Анализ ИИ") }}
  </button>

  <Teleport to="body">
    <div v-if="open" class="bpai-back" @click.self="open = false" role="dialog" aria-modal="true">
      <div class="bpai-card" :class="{ 'bpai-wide': mode === 'forecast' && html }">
        <header class="bpai-hd">
          <div class="bpai-hd-txt">
            <div class="bpai-eyebrow">{{ t("ИИ-АНАЛИЗ БИЗНЕС-ПЛАНА") }} · {{ scope === 'company' ? t('КОМПАНИЯ') : t('ПОРТФЕЛЬ') }}</div>
            <h2 class="bpai-title">{{ titleText }}</h2>
            <div v-if="doneAt && !loading && html" class="bpai-sub">{{ t(MODE_LABEL[mode]) }} · FY {{ year }} · {{ doneAt }}</div>
          </div>
          <div class="bpai-hd-actions">
            <button v-if="html && !loading" class="bpai-act" @click="copyAnswer" :title="t('Скопировать ответ')">{{ t("Копировать") }}</button>
            <button v-if="html && !loading" class="bpai-act bpai-act-xls" @click="exportExcel" :title="t('Выгрузить таблицы в Excel')">Excel</button>
            <button class="bpai-x" @click="open = false" :aria-label="t('Закрыть')">×</button>
          </div>
        </header>

        <div class="bpai-ctrls">
          <div class="bpai-seg-row">
            <span class="bpai-seg-lbl">{{ t("Охват") }}</span>
            <div class="bpai-seg">
              <button :class="{ on: scope === 'portfolio' }" :disabled="loading" @click="setScope('portfolio')">{{ t("Весь портфель") }}</button>
              <button :class="{ on: scope === 'company' }" :disabled="loading" @click="setScope('company')">{{ t("Одна компания") }}</button>
            </div>
            <select v-if="scope === 'company'" v-model="pickedId" :disabled="loading" @change="onPickCompany" class="bpai-co-select">
              <option v-for="c in companies" :key="c.company_id" :value="c.company_id">{{ c.company_name_ru }}</option>
            </select>
          </div>
          <div class="bpai-seg-row">
            <span class="bpai-seg-lbl">{{ t("Режим") }}</span>
            <div class="bpai-seg">
              <button v-for="m in MODES" :key="m.id" :class="{ on: mode === m.id }" :disabled="loading" @click="setMode(m.id)" :title="t(m.hint)">{{ t(m.label) }}</button>
            </div>
            <button class="bpai-run" :disabled="loading" @click="run">
              {{ loading ? t("Анализирую…") : (html ? t("Пересчитать") : t("Запустить анализ")) }}
            </button>
          </div>
        </div>

        <div class="bpai-body">
          <div v-if="loading" class="bpai-loading"><span class="bpai-spin"></span><span>{{ step }}</span></div>
          <div v-else-if="error" class="bpai-error">{{ error }}</div>
          <template v-else-if="html">
            <template v-if="mode === 'forecast'">
              <div v-if="fcTrend.length" class="bpai-chart">
                <div class="bpai-chart-title">{{ t("Прогноз выручки «{name}» (история → прогноз), млрд сум", { name: fcScopeName }) }}</div>
                <div v-for="(tr, i) in fcTrend" :key="i" class="bpai-bar-row">
                  <span class="bpai-bar-lbl">{{ tr.label }}<span v-if="tr.projected" class="bpai-fc-tag">{{ t("прогноз") }}</span></span>
                  <div class="bpai-bar-track">
                    <div class="bpai-bar-fill" :class="{ proj: tr.projected }"
                         :style="{ width: Math.min(tr.value / fcTrendMax * 100, 100) + '%', background: '#6355E0' }"></div>
                  </div>
                  <span class="bpai-bar-val">{{ fcCell(tr.value, null) }}</span>
                </div>
              </div>
              <div v-if="fcView.length" class="bpai-fc">
                <div class="bpai-fc-head">
                  <div class="bpai-chart-title">{{ t("Модельный прогноз БП (движок)") }}{{ fcScopeName ? ' · ' + t(fcScopeName) : '' }}</div>
                  <div v-if="hasFcQuarters" class="bpai-fc-toggle">
                    <div class="bpai-seg bpai-seg-sm">
                      <button :class="{ on: fcTblMode === 'years' }" @click="setFcTblMode('years')">{{ t("По годам") }}</button>
                      <button :class="{ on: fcTblMode === 'quarters' }" @click="setFcTblMode('quarters')">{{ t("По кварталам") }}</button>
                    </div>
                    <select v-if="fcTblMode === 'quarters'" v-model="fcQYear" class="bpai-co-select bpai-fc-yr">
                      <option v-for="y in fcYears" :key="y" :value="y">{{ t("{y} г.", { y }) }}</option>
                    </select>
                  </div>
                </div>
                <div class="bpai-fc-scroll">
                  <table class="bpai-fc-tbl">
                    <thead><tr>
                      <th>{{ fcScopeName === 'Портфель' ? t('Компания') : t('Метрика') }}</th>
                      <th>{{ t("Тек. факт") }}</th>
                      <template v-if="fcTblMode === 'quarters'">
                        <th v-for="q in FC_Q" :key="q">{{ q }} · {{ fcQYear }}</th>
                      </template>
                      <template v-else>
                        <th>{{ t("Ожид. {y}", { y: fcBaseYear }) }}</th>
                        <th v-for="y in fcYears" :key="y">{{ y }}</th>
                      </template>
                      <th>{{ t("Метод") }}</th>
                    </tr></thead>
                    <tbody>
                      <tr v-for="(r, i) in fcView" :key="i">
                        <td class="bpai-fc-nm">{{ t(r.name) }}</td>
                        <td>{{ fcCell(r.fact, null) }}</td>
                        <template v-if="fcTblMode === 'quarters'">
                          <td v-for="(q, qi) in FC_Q" :key="q">{{ fcCell(r.byYear[fcQYear]?.quarters?.[qi] ?? null, null) }}</td>
                        </template>
                        <template v-else>
                          <td>{{ fcCell(r.expected, null) }}</td>
                          <td v-for="y in fcYears" :key="y">
                            <template v-if="r.byYear[y]">
                              <span class="bpai-fc-v">{{ fcCell(r.byYear[y].value, null) }}</span>
                              <span v-if="r.byYear[y].low != null" class="bpai-fc-band">{{ fcCell(r.byYear[y].low, null) }}…{{ fcCell(r.byYear[y].high, null) }}</span>
                            </template>
                            <template v-else>—</template>
                          </td>
                        </template>
                        <td><span class="bpai-fc-conf" :class="'c-' + r.confidence">{{ fcMethodLabel(r.method) }}</span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="bpai-fc-note">
                  {{ t("Числа — детерминированный движок (воспроизводимо, деньги млрд сум); коридор [low…high] — неопределённость.") }}
                  <template v-if="fcTblMode === 'quarters'">{{ t("Кварталы будущих лет — разбивка годового прогноза по сезонности плана.") }}</template>
                  {{ t("ИИ ниже накладывает факторы (цены на сырьё, курс, санкции, макро) и корректирует.") }}
                </div>
              </div>
            </template>
            <div v-else-if="chartRows.length" class="bpai-chart">
              <div class="bpai-chart-title">{{ scope === 'company' ? t("Исполнение по метрикам, факт/план %") : t("Исполнение по компаниям (выручка), факт/план %") }}</div>
              <div v-for="(r, i) in chartRows" :key="i" class="bpai-bar-row">
                <span class="bpai-bar-lbl" :title="t(r.label)">{{ t(r.label) }}</span>
                <div class="bpai-bar-track">
                  <div class="bpai-bar-fill" :style="{ width: Math.min(r.value, 150) / 1.5 + '%', background: barColor(r.value) }"></div>
                </div>
                <span class="bpai-bar-val">{{ r.value }}%</span>
              </div>
            </div>
            <div class="bpai-md" v-html="html"></div>
          </template>
          <div v-else class="bpai-empty">
            <b>{{ t("Выберите охват и режим, затем запустите анализ.") }}</b>
            <span>{{ t("ИИ разберёт исполнение плана (план / ожидаемое / факт по ОФР и производству), свяжет производство с финансами и — в режиме «Прогноз» — предскажет будущие цели БП с учётом цен на сырьё, курса и санкций.") }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import * as XLSX from "xlsx";
import { bpApi } from "@/api/bpKpi";
import type { BpCompanyForecast, AvailableCompany } from "@/api/bpKpi";
import { productionApi } from "@/api/production";
import { renderMarkdown } from "@/utils/renderMarkdown";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/composables/useI18n";

type Mode = "performance" | "linkage" | "forecast";
type FcCell = { value: number | null; low: number | null; high: number | null; quarters?: (number | null)[] | null };
type FcRow = { name: string; fact: number | null; expected: number | null; byYear: Record<string, FcCell>; method: string; confidence: string };
type FcTrend = { label: string; value: number; projected: boolean };
type ChartRow = { label: string; value: number };
type FcSaved = { view: FcRow[]; years: string[]; trend: FcTrend[]; baseYear: number; scopeName: string };
type SavedRec = { raw: string; doneAt: string; year: number; chart?: ChartRow[]; fc?: FcSaved };

const props = defineProps<{ companies: AvailableCompany[]; year: number; period: string; selectedId: string | null }>();

const toast = useToast();
const { t } = useI18n();
const open = ref(false);
const loading = ref(false);
const error = ref("");
const html = ref("");
const rawMd = ref("");
const chartRows = ref<ChartRow[]>([]);
const doneAt = ref("");
const step = ref("");
const scope = ref<"portfolio" | "company">("portfolio");
const mode = ref<Mode>("performance");
const saved = ref<Record<string, SavedRec>>({});

// Прогнозная таблица (как в KPI-аналитике)
const fcView = ref<FcRow[]>([]);
const fcYears = ref<string[]>([]);
const fcTrend = ref<FcTrend[]>([]);
const fcBaseYear = ref<number>(0);
const fcScopeName = ref<string>("");
const fcTblMode = ref<"years" | "quarters">("years");
const fcQYear = ref<string>("");
const FC_Q = ["Q1", "Q2", "Q3", "Q4"];
const fcTrendMax = computed(() => Math.max(1, ...fcTrend.value.map(t => t.value)));
const hasFcQuarters = computed(() => fcView.value.some(r => fcYears.value.some(y => r.byYear[y]?.quarters)));

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "performance", label: "Исполнение", hint: "План / ожидаемое / факт по ОФР и производству" },
  { id: "linkage", label: "Произв. ↔ Финансы", hint: "Связь натурального объёма с выручкой/маржой/прибылью" },
  { id: "forecast", label: "Прогноз", hint: "Прогноз будущих целей БП + факторы (сырьё, курс, санкции)" },
];
const MODE_LABEL: Record<Mode, string> = { performance: "Исполнение", linkage: "Произв.↔Финансы", forecast: "Прогноз" };

const pickedId = ref<string | null>(props.selectedId || (props.companies[0]?.company_id ?? null));
const selectedCompany = computed(() => props.companies.find(c => c.company_id === pickedId.value) || null);
const titleText = computed(() => scope.value === "company"
  ? (selectedCompany.value?.company_name_ru || t("Компания"))
  : t("Все компании портфеля"));

const num = (v: unknown): number | null =>
  (v === null || v === undefined || v === "") ? null : Number(v);

function barColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 75) return "#D97706";
  return "#E24B4A";
}
function fcCell(v: number | null | undefined, unit: string | null): string {
  if (v == null) return "—";
  if ((unit || "") === "%") return `${Math.round(v)}%`;
  const a = Math.abs(v);
  return a >= 1000 ? Math.round(v).toLocaleString("ru-RU").replace(/,/g, " ")
    : a >= 10 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "");
}
const FC_METHOD: Record<string, string> = {
  pace: "темп", seasonal: "сезон", run_rate: "run-rate", plan: "план",
  actual: "факт", ols: "тренд", cagr: "CAGR", none: "нет данных",
};
function fcMethodLabel(m: string): string { return t(FC_METHOD[m] || m); }

function savedKey(m: Mode = mode.value): string {
  return scope.value === "company" && pickedId.value ? `${m}__${pickedId.value}` : m;
}
function onPickCompany(): void { applyMode(mode.value); }

async function fetchSaved(): Promise<void> {
  try {
    const { api } = await import("@/api/client");
    const r = await api.get("/ai/saved/bp");
    saved.value = (r.data?.saved || {}) as Record<string, SavedRec>;
  } catch { /* нет доступа/оффлайн — игнор */ }
}
function resetForecastView(): void { fcView.value = []; fcYears.value = []; fcTrend.value = []; fcTblMode.value = "years"; }
function applyMode(m: Mode): void {
  mode.value = m;
  const o = saved.value[savedKey(m)];
  if (o?.raw) {
    rawMd.value = o.raw; html.value = renderMarkdown(o.raw); doneAt.value = o.doneAt || ""; chartRows.value = o.chart || [];
    if (o.fc) {
      fcView.value = o.fc.view || []; fcYears.value = o.fc.years || []; fcTrend.value = o.fc.trend || [];
      fcBaseYear.value = o.fc.baseYear || props.year; fcScopeName.value = o.fc.scopeName || "";
    } else resetForecastView();
  } else {
    rawMd.value = ""; html.value = ""; doneAt.value = ""; chartRows.value = []; resetForecastView();
  }
  error.value = "";
}
function setMode(m: Mode): void { if (!loading.value) applyMode(m); }
function setScope(s: "portfolio" | "company"): void {
  if (loading.value) return;
  scope.value = s;
  if (s === "company" && !pickedId.value) pickedId.value = props.companies[0]?.company_id ?? null;
  applyMode(mode.value);
}
function setFcTblMode(m: "years" | "quarters"): void {
  fcTblMode.value = m;
  if (m === "quarters" && (!fcQYear.value || !fcYears.value.includes(fcQYear.value)))
    fcQYear.value = fcYears.value[0] || "";
}

async function openModal(): Promise<void> {
  open.value = true;
  if (props.selectedId && props.companies.some(c => c.company_id === props.selectedId)) pickedId.value = props.selectedId;
  await fetchSaved();
  applyMode(mode.value);
}

async function copyAnswer(): Promise<void> {
  if (!rawMd.value) return;
  try { await navigator.clipboard.writeText(rawMd.value); toast.success(t("Анализ скопирован")); }
  catch { toast.error(t("Не удалось скопировать")); }
}

function exportExcel(): void {
  if (!rawMd.value) return;
  const wb = XLSX.utils.book_new();
  if (mode.value === "forecast" && fcView.value.length) {
    const head = [fcScopeName.value === "Портфель" ? t("Компания") : t("Метрика"), t("Тек. факт"), t("Ожид. {y}", { y: fcBaseYear.value }), ...fcYears.value, t("Метод")];
    const aoa: (string | number)[][] = [head];
    for (const r of fcView.value) {
      const row: (string | number)[] = [t(r.name), fcCell(r.fact, null), fcCell(r.expected, null)];
      for (const y of fcYears.value) {
        const c = r.byYear[y];
        row.push(c ? (c.low != null ? `${fcCell(c.value, null)} [${fcCell(c.low, null)}…${fcCell(c.high, null)}]` : fcCell(c.value, null)) : "—");
      }
      row.push(fcMethodLabel(r.method));
      aoa.push(row);
    }
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), t("Модель прогноза"));
  }
  const lines = rawMd.value.replace(/\r\n/g, "\n").split("\n");
  const tables: string[][][] = [];
  let cur: string[][] | null = null;
  for (const ln of lines) {
    if (/^\s*\|.*\|\s*$/.test(ln)) {
      if (/^\s*\|[\s:|-]+\|\s*$/.test(ln)) continue;
      const row = ln.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim().replace(/\*\*/g, "").replace(/`/g, ""));
      if (!cur) { cur = []; tables.push(cur); }
      cur.push(row);
    } else { cur = null; }
  }
  let sheetN = 0;
  for (const tbl of tables) {
    if (tbl.length < 2) continue;
    sheetN++;
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(tbl), t("Таблица {n}", { n: sheetN }).slice(0, 31));
  }
  const textWs = XLSX.utils.aoa_to_sheet(lines.map(l => [l]));
  textWs["!cols"] = [{ wch: 120 }];
  XLSX.utils.book_append_sheet(wb, textWs, t("Полный текст"));
  const scopeName = scope.value === "company" ? (selectedCompany.value?.company_name_ru || "company") : t("портфель");
  XLSX.writeFile(wb, `БП_${t(MODE_LABEL[mode.value])}_${scopeName}_${props.year}.xlsx`);
}

async function saveResult(raw: string): Promise<void> {
  const key = savedKey();
  const rec: SavedRec = { raw, doneAt: doneAt.value, year: props.year, chart: chartRows.value };
  if (mode.value === "forecast" && fcView.value.length) {
    rec.fc = { view: fcView.value, years: fcYears.value, trend: fcTrend.value, baseYear: fcBaseYear.value, scopeName: fcScopeName.value };
  }
  saved.value = { ...saved.value, [key]: rec };
  try {
    const { api } = await import("@/api/client");
    await api.put(`/ai/saved/bp/${key}`, { payload: rec });
  } catch { toast.error(t("Анализ не сохранён на сервере — исчезнет при обновлении. Повторите.")); }
}

function buildForecastView(fc: BpCompanyForecast): void {
  const yset = new Set<string>();
  const rows: FcRow[] = [];
  for (const mt of fc.metrics) {
    const byYear: Record<string, FcCell> = {};
    for (const p of mt.annual.projections) { byYear[p.period] = { value: p.value, low: p.low, high: p.high, quarters: p.quarters }; yset.add(p.period); }
    const useAnnual = mt.annual.method !== "none";
    rows.push({ name: mt.label, fact: mt.fact, expected: mt.expect, byYear, method: useAnnual ? mt.annual.method : "none", confidence: mt.annual.confidence });
  }
  const rev = fc.metrics.find(m => m.key === "revenue") || fc.metrics[0];
  const trend: FcTrend[] = [];
  if (rev) {
    for (const h of rev.history) if (h.fact != null) trend.push({ label: String(h.year), value: Math.round(h.fact), projected: false });
    for (const p of rev.annual.projections) if (p.value != null) trend.push({ label: p.period, value: Math.round(p.value), projected: true });
  }
  fcView.value = rows; fcYears.value = Array.from(yset).sort();
  fcTrend.value = trend; fcBaseYear.value = fc.base_year; fcScopeName.value = fc.company_name;
}
function buildPortfolioForecastView(fcs: BpCompanyForecast[], baseYear: number): void {
  const yset = new Set<string>();
  const rows: FcRow[] = [];
  for (const fc of fcs) {
    const rev = fc.metrics.find(m => m.key === "revenue") || fc.metrics[0];
    if (!rev) continue;
    const byYear: Record<string, FcCell> = {};
    for (const p of rev.annual.projections) { byYear[p.period] = { value: p.value, low: p.low, high: p.high, quarters: p.quarters }; yset.add(p.period); }
    rows.push({ name: fc.company_name, fact: rev.fact, expected: rev.expect, byYear, method: rev.annual.method, confidence: rev.annual.confidence });
  }
  fcView.value = rows.sort((a, b) => (b.fact ?? -1) - (a.fact ?? -1));
  fcYears.value = Array.from(yset).sort();
  fcTrend.value = []; fcBaseYear.value = baseYear; fcScopeName.value = "Портфель";
}

async function run(): Promise<void> {
  if (loading.value) return;
  loading.value = true; error.value = ""; html.value = "";
  const single = scope.value === "company" && selectedCompany.value ? selectedCompany.value : null;
  step.value = single ? t("Загружаю БП: {name}…", { name: single.company_name_ru }) : t("Загружаю бизнес-план всех компаний…");
  try {
    const { api } = await import("@/api/client");
    const cos: AvailableCompany[] = single ? [single] : props.companies;
    // Метаданные метрик (label + направление) — headline (без sub-детализации).
    const meta = await bpApi.getMetrics();
    const headline = meta.filter(m => !m.sub);
    const labelOf: Record<string, string> = {};
    const dirOf: Record<string, string> = {};
    for (const m of headline) { labelOf[m.key] = m.label; dirOf[m.key] = m.positive ? "down" : "up"; }

    // Финансовая матрица БП (annual: план/ожидаемое/факт + источник факта).
    const bp_rows = (await Promise.all(cos.map(async (co) => {
      try {
        const c = await bpApi.getComputed(co.company_id, props.year, "annual");
        const metrics = headline.map((m) => {
          const cell = c.metrics[m.key] || {};
          return {
            key: m.key, label: labelOf[m.key], dir: dirOf[m.key],
            plan: num(cell.plan), expect: num(cell.expect), fact: num(cell.fact),
            fact_source: cell.fact_source || null,
          };
        }).filter(mt => mt.plan != null || mt.expect != null || mt.fact != null);
        return metrics.length ? { code: co.company_code, name: co.company_name_ru, metrics } : null;
      } catch { return null; }
    }))).filter((r): r is NonNullable<typeof r> => r != null);

    if (!bp_rows.length && mode.value !== "linkage") {
      error.value = t("Нет данных бизнес-плана за этот год. Заведите показатели в редакторе.");
      loading.value = false; return;
    }

    // График исполнения: по метрикам (компания) или по выручке компаний (портфель).
    const cr: ChartRow[] = [];
    if (single) {
      const row = bp_rows[0];
      if (row) for (const mt of row.metrics) {
        if (mt.plan != null && mt.plan !== 0 && mt.fact != null) cr.push({ label: mt.label, value: Math.round((mt.fact / mt.plan) * 100) });
      }
    } else {
      for (const row of bp_rows) {
        const rev = row.metrics.find(m => m.key === "revenue");
        if (rev && rev.plan != null && rev.plan !== 0 && rev.fact != null) cr.push({ label: row.name, value: Math.round((rev.fact / rev.plan) * 100) });
      }
    }
    chartRows.value = cr.sort((a, b) => b.value - a.value).slice(0, 20);

    // Производство (best-effort): свежий доступный период года.
    step.value = t("Подтягиваю производственный план…");
    let prod_rows: unknown[] = [];
    try {
      const avail = await productionApi.available();
      const rank: Record<string, number> = { annual: 0, h2: 1, h1: 2 };
      const combo = avail.combos.filter(c => c.year === props.year)
        .sort((a, b) => (rank[a.period] ?? 9) - (rank[b.period] ?? 9))[0];
      if (combo) {
        const ov = await productionApi.overview(props.year, combo.period);
        const wanted = single ? ov.companies.filter(c => c.k === single.company_code) : ov.companies;
        prod_rows = wanted.filter(c => c.has_data).map(c => ({
          code: c.k, name: c.n, exec_pct: c.execPct,
          lines: (c.lines || []).slice(0, 12).map(l => ({
            name: l.name, unit: l.unit, planN: l.planN, expN: l.expN, factN: l.factN,
            planM: l.planM, expM: l.expM, factM: l.factM, execPct: l.execPct,
          })),
        }));
      }
    } catch { prod_rows = []; }

    // Прогноз (детерминированный движок) — режим «Прогноз».
    let forecastPayload: unknown = null;
    if (mode.value === "forecast") {
      step.value = t("Считаю модельный прогноз БП (годы + кварталы)…");
      try {
        if (single) {
          const fc = await bpApi.getForecast(single.company_id, props.year, 3);
          buildForecastView(fc); forecastPayload = fc;
        } else {
          const fcs = (await Promise.all(props.companies.map(async (c) => {
            try { return await bpApi.getForecast(c.company_id, props.year, 3); } catch { return null; }
          }))).filter((x): x is BpCompanyForecast => x != null);
          buildPortfolioForecastView(fcs, props.year);
          forecastPayload = { portfolio: fcs };
        }
      } catch { resetForecastView(); }
    } else {
      resetForecastView();
    }

    step.value = t("ИИ анализирует бизнес-план…");
    const resp = await api.post("/ai/bp-analysis", {
      year: props.year, period: "annual", mode: mode.value,
      focus: single ? single.company_name_ru : null,
      bp_rows, prod_rows, forecast: forecastPayload,
    }, { timeout: 235000 });
    const raw = (resp.data?.analysis || "") as string;
    if (!raw) { error.value = t("ИИ вернул пустой ответ."); loading.value = false; return; }
    rawMd.value = raw;
    html.value = renderMarkdown(raw);
    doneAt.value = new Date().toLocaleString("ru-RU");
    await saveResult(raw);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || t("Ошибка анализа");
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.bpai-btn {
  display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px;
  border: none; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600;
  color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0);
  box-shadow: 0 2px 8px -2px rgba(99, 85, 224, .5);
}
.bpai-btn:disabled { opacity: .6; cursor: default; }
.bpai-btn-ai {
  display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
  border-radius: 5px; background: rgba(255, 255, 255, .22); font-size: 10px; font-weight: 700;
}

.bpai-back {
  position: fixed; inset: 0; z-index: var(--z-modal, 9100); display: flex;
  align-items: flex-start; justify-content: center; padding: 6vh 16px 40px;
  background: rgba(20, 20, 34, .5); backdrop-filter: blur(3px);
}
.bpai-card {
  width: min(900px, 100%); max-height: 88vh; display: flex; flex-direction: column;
  background: var(--surface, #fff); border-radius: 18px; overflow: hidden;
  box-shadow: 0 24px 64px -20px rgba(20, 20, 34, .5); transition: width .2s ease;
}
.bpai-card.bpai-wide { width: min(1180px, 100%); }
.bpai-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 20px 24px 14px; }
.bpai-eyebrow { font-size: 11px; letter-spacing: .14em; color: #7C6FF7; font-weight: 700; }
.bpai-title { margin: 4px 0 0; font-size: 21px; font-weight: 650; color: var(--ink, #1A1A26); }
.bpai-sub { margin-top: 5px; font-size: 12.5px; color: #8A90A0; }
.bpai-hd-actions { display: flex; align-items: center; gap: 8px; }
.bpai-act { height: 30px; padding: 0 12px; border: 1px solid var(--line, #ECECF3); border-radius: 8px; background: #fff; cursor: pointer; font-size: 12.5px; font-weight: 600; color: #5A6172; }
.bpai-act:hover { border-color: #7C6FF7; color: #6355E0; }
.bpai-act-xls { color: #1D7C4D; border-color: #C7E6D5; }
.bpai-act-xls:hover { border-color: #1D9E75; color: #157A48; }
.bpai-x { border: none; background: transparent; font-size: 24px; line-height: 1; color: #9AA3B2; cursor: pointer; padding: 0 4px; }

.bpai-ctrls { padding: 0 24px 14px; border-bottom: 1px solid var(--line, #ECECF3); }
.bpai-seg-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
.bpai-seg-lbl { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #9AA3B2; font-weight: 600; min-width: 56px; }
.bpai-seg { display: inline-flex; background: #F2F2F8; border-radius: 10px; padding: 3px; }
.bpai-seg button { border: none; background: transparent; padding: 6px 13px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 600; color: #5A6172; }
.bpai-seg button.on { background: #fff; color: #6355E0; box-shadow: 0 1px 4px -1px rgba(20, 20, 34, .18); }
.bpai-seg button:disabled { opacity: .45; cursor: default; }
.bpai-seg-sm { padding: 2px; }
.bpai-seg-sm button { padding: 4px 10px; font-size: 12px; }
.bpai-run { margin-left: auto; height: 36px; padding: 0 18px; border: none; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 650; color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0); }
.bpai-run:disabled { opacity: .6; cursor: default; }
.bpai-co-select { height: 32px; padding: 0 10px; border: 1px solid var(--line, #ECECF3); border-radius: 9px; background: #fff; font-size: 13px; color: var(--ink, #1A1A26); max-width: 300px; }
.bpai-fc-yr { height: 28px; padding: 0 8px; font-size: 12px; }

.bpai-chart { margin-bottom: 18px; padding: 14px 16px; background: #FAFAFD; border: 1px solid var(--line, #ECECF3); border-radius: 12px; }
.bpai-chart-title { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: #8A90A0; font-weight: 600; margin-bottom: 10px; }
.bpai-bar-row { display: grid; grid-template-columns: 220px 1fr 60px; align-items: center; gap: 10px; margin: 5px 0; font-size: 12.5px; }
.bpai-bar-lbl { color: var(--ink2, #2C2C3A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bpai-bar-track { height: 12px; background: #ECECF3; border-radius: 6px; overflow: hidden; }
.bpai-bar-fill { height: 100%; border-radius: 6px; transition: width .5s ease; }
.bpai-bar-fill.proj { opacity: .55; background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.35) 0 5px, transparent 5px 10px); }
.bpai-bar-val { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink2, #2C2C3A); }
.bpai-fc-tag { margin-left: 6px; font-size: 9.5px; letter-spacing: .04em; text-transform: uppercase; color: #7C6FF7; font-weight: 700; }
@media (max-width: 620px) { .bpai-bar-row { grid-template-columns: 130px 1fr 52px; } }

.bpai-fc { margin-bottom: 18px; }
.bpai-fc-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.bpai-fc-head .bpai-chart-title { margin-bottom: 0; }
.bpai-fc-toggle { display: flex; align-items: center; gap: 8px; }
.bpai-fc-scroll { overflow-x: auto; border: 1px solid var(--line, #ECECF3); border-radius: 12px; }
.bpai-fc-tbl { border-collapse: collapse; width: 100%; font-size: 12px; min-width: 520px; }
.bpai-fc-tbl th, .bpai-fc-tbl td { padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--line, #ECECF3); white-space: nowrap; }
.bpai-fc-tbl th:first-child, .bpai-fc-tbl td:first-child { text-align: left; }
.bpai-fc-tbl thead th { background: #F7F7FB; font-weight: 650; color: #5A6172; position: sticky; top: 0; }
.bpai-fc-tbl tbody tr:last-child td { border-bottom: none; }
.bpai-fc-tbl tbody tr:hover td { background: #FAFAFD; }
.bpai-fc-nm { max-width: 340px; white-space: normal; }
.bpai-fc-v { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink, #1A1A26); }
.bpai-fc-band { display: block; font-size: 10px; color: #A0A6B4; font-variant-numeric: tabular-nums; }
.bpai-fc-conf { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 10.5px; font-weight: 600; }
.bpai-fc-conf.c-high { background: #E3F5EC; color: #157A48; }
.bpai-fc-conf.c-medium { background: #FEF2E0; color: #B4690E; }
.bpai-fc-conf.c-low { background: #FCE9E8; color: #C0392B; }
.bpai-fc-conf.c-none { background: #EEF0F4; color: #8A90A0; }
.bpai-fc-note { margin-top: 8px; font-size: 11.5px; line-height: 1.5; color: #8A90A0; }

.bpai-body { padding: 18px 24px 26px; overflow-y: auto; }
.bpai-loading { display: flex; align-items: center; gap: 12px; color: #6E6D80; font-size: 14px; padding: 30px 0; }
.bpai-spin { width: 18px; height: 18px; border: 2.5px solid #E2E1F0; border-top-color: #7C6FF7; border-radius: 50%; animation: bpaiSpin .8s linear infinite; }
@keyframes bpaiSpin { to { transform: rotate(360deg); } }
.bpai-error { color: #E24B4A; font-size: 14px; padding: 16px 0; }
.bpai-empty { display: flex; flex-direction: column; gap: 8px; text-align: center; padding: 36px 8px; color: #8A90A0; }
.bpai-empty b { color: var(--ink, #1A1A26); font-size: 15px; }
.bpai-empty span { max-width: 62ch; margin: 0 auto; font-size: 13px; line-height: 1.6; }

.bpai-md { font-size: 14px; line-height: 1.65; color: var(--ink2, #2C2C3A); }
.bpai-md :deep(h1), .bpai-md :deep(h2), .bpai-md :deep(h3), .bpai-md :deep(h4) { margin: 18px 0 8px; font-weight: 650; color: var(--ink, #1A1A26); line-height: 1.3; }
.bpai-md :deep(h1) { font-size: 20px; } .bpai-md :deep(h2) { font-size: 17px; } .bpai-md :deep(h3) { font-size: 15px; }
.bpai-md :deep(p) { margin: 8px 0; }
.bpai-md :deep(ul), .bpai-md :deep(ol) { margin: 8px 0; padding-left: 22px; }
.bpai-md :deep(li) { margin: 4px 0; }
.bpai-md :deep(strong) { color: var(--ink, #1A1A26); font-weight: 650; }
.bpai-md :deep(code) { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; background: #F2F2F8; padding: 1px 5px; border-radius: 5px; }
.bpai-md :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12.5px; display: block; overflow-x: auto; }
.bpai-md :deep(th), .bpai-md :deep(td) { border: 1px solid var(--line, #ECECF3); padding: 6px 10px; text-align: left; }
.bpai-md :deep(th) { background: #F7F7FB; font-weight: 650; }

@media (max-width: 620px) { .bpai-run { margin-left: 0; } }
</style>
