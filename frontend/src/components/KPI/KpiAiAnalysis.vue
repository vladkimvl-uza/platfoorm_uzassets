<template>
  <button class="kpai-btn" @click="openModal" :disabled="loading" :title="t('ИИ-анализ KPI')">
    <span class="kpai-btn-ai">Ai</span>{{ loading ? t("Анализирую…") : t("Анализ ИИ") }}
  </button>

  <Teleport to="body">
    <div v-if="open" class="kpai-back" @click.self="open = false" role="dialog" aria-modal="true">
      <div class="kpai-card" :class="{ 'kpai-wide': mode === 'forecast' && html }">
        <header class="kpai-hd">
          <div class="kpai-hd-txt">
            <div class="kpai-eyebrow">{{ t("ИИ-АНАЛИЗ KPI") }} · {{ scope === 'company' ? t('КОМПАНИЯ') : t('ПОРТФЕЛЬ') }}</div>
            <h2 class="kpai-title">{{ titleText }}</h2>
            <div v-if="doneAt && !loading && html" class="kpai-sub">{{ t(MODE_LABEL[mode]) }} · FY {{ year }} · {{ doneAt }}</div>
          </div>
          <div class="kpai-hd-actions">
            <button v-if="html && !loading" class="kpai-act" @click="copyAnswer" :title="t('Скопировать ответ')">{{ t("Копировать") }}</button>
            <button v-if="html && !loading" class="kpai-act kpai-act-xls" @click="exportExcel" :title="t('Выгрузить таблицы в Excel')">Excel</button>
            <button class="kpai-x" @click="open = false" :aria-label="t('Закрыть')">×</button>
          </div>
        </header>

        <div class="kpai-ctrls">
          <!-- Охват: портфельный анализ и селектор компаний — только тем, кому
               они по области доступа положены (решение владельца 29.07.2026).
               Ограниченный одной компанией сразу анализирует свою. -->
          <div v-if="coScope.showPortfolioViews.value || coScope.showCompanyPicker.value" class="kpai-seg-row">
            <span class="kpai-seg-lbl">{{ t("Охват") }}</span>
            <div v-if="coScope.showPortfolioViews.value" class="kpai-seg">
              <button :class="{ on: scope === 'portfolio' }" :disabled="loading" @click="setScope('portfolio')">{{ t("Весь портфель") }}</button>
              <button :class="{ on: scope === 'company' }" :disabled="loading" @click="setScope('company')">{{ t("Одна компания") }}</button>
            </div>
            <select v-if="scope === 'company' && coScope.showCompanyPicker.value" v-model="pickedId" :disabled="loading" @change="onPickCompany" class="kpai-co-select">
              <option v-for="c in companies" :key="c.company_id" :value="c.company_id">{{ c.company_name_ru }}</option>
            </select>
          </div>
          <div class="kpai-seg-row">
            <span class="kpai-seg-lbl">{{ t("Режим") }}</span>
            <div class="kpai-seg">
              <button v-for="m in MODES" :key="m.id" :class="{ on: mode === m.id }" :disabled="loading" @click="setMode(m.id)" :title="t(m.hint)">{{ t(m.label) }}</button>
            </div>
            <button class="kpai-run" :disabled="loading" @click="run">
              {{ loading ? t("Анализирую…") : (html ? t("Пересчитать") : t("Запустить анализ")) }}
            </button>
          </div>
        </div>

        <div class="kpai-body">
          <div v-if="loading" class="kpai-loading"><span class="kpai-spin"></span><span>{{ step }}</span></div>
          <div v-else-if="error" class="kpai-error">{{ error }}</div>
          <template v-else-if="html">
            <!-- Режим «Прогноз»: траектория выполнения + модельная таблица движка -->
            <template v-if="mode === 'forecast'">
              <div v-if="fcTrend.length" class="kpai-chart">
                <div class="kpai-chart-title">{{ t("Прогноз сводного выполнения «{name}», % (история → прогноз)", { name: fcScopeName === 'Портфель' ? t('Портфель') : fcScopeName }) }}</div>
                <div v-for="(tr, i) in fcTrend" :key="i" class="kpai-bar-row">
                  <span class="kpai-bar-lbl">{{ tr.label }}<span v-if="tr.projected" class="kpai-fc-tag">{{ t("прогноз") }}</span></span>
                  <div class="kpai-bar-track">
                    <div class="kpai-bar-fill" :class="{ proj: tr.projected }"
                         :style="{ width: Math.min(tr.value / fcTrendMax * 100, 100) + '%', background: barColor(tr.value) }"></div>
                  </div>
                  <span class="kpai-bar-val">{{ tr.value }}%</span>
                </div>
              </div>
              <div v-if="fcView.length" class="kpai-fc">
                <div class="kpai-fc-head">
                  <div class="kpai-chart-title">{{ t("Модельный прогноз (движок)") }}{{ fcScopeName ? ' · ' + (fcScopeName === 'Портфель' ? t('Портфель') : fcScopeName) : '' }}</div>
                  <div v-if="hasFcQuarters" class="kpai-fc-toggle">
                    <div class="kpai-seg kpai-seg-sm">
                      <button :class="{ on: fcTblMode === 'years' }" @click="setFcTblMode('years')">{{ t("По годам") }}</button>
                      <button :class="{ on: fcTblMode === 'quarters' }" @click="setFcTblMode('quarters')">{{ t("По кварталам") }}</button>
                    </div>
                    <select v-if="fcTblMode === 'quarters'" v-model="fcQYear" class="kpai-co-select kpai-fc-yr" :aria-label="t('Год для квартальной разбивки')">
                      <option v-for="y in fcYears" :key="y" :value="y">{{ t("{y} г.", { y }) }}</option>
                    </select>
                  </div>
                </div>
                <div class="kpai-fc-scroll">
                  <table class="kpai-fc-tbl">
                    <thead><tr>
                      <th>{{ fcScopeName === 'Портфель' ? t('Компания') : t('Показатель') }}</th>
                      <th>{{ t("Тек. факт") }}</th>
                      <template v-if="fcTblMode === 'quarters'">
                        <th v-for="q in FC_Q" :key="q">{{ q }} · {{ fcQYear }}</th>
                      </template>
                      <template v-else>
                        <th v-if="fcScopeName !== 'Портфель'">{{ t("Ожид. {y}", { y: fcBaseYear }) }}</th>
                        <th v-for="y in fcYears" :key="y">{{ y }}</th>
                      </template>
                      <th>{{ t("Метод") }}</th>
                    </tr></thead>
                    <tbody>
                      <tr v-for="(r, i) in fcView" :key="i">
                        <td class="kpai-fc-nm">
                          <span class="kpai-fc-nm-t">{{ r.name }}<span v-if="fcUnit(r.unit)" class="kpai-fc-unit"> · {{ fcUnit(r.unit) }}</span></span>
                          <span v-if="r.manager" class="kpai-fc-mgr">{{ r.manager }}</span>
                        </td>
                        <td>{{ fcCell(r.fact, r.unit) }}</td>
                        <template v-if="fcTblMode === 'quarters'">
                          <td v-for="(q, qi) in FC_Q" :key="q">
                            <span class="kpai-fc-v">{{ fcCell(r.byYear[fcQYear]?.quarters?.[qi] ?? null, r.unit) }}</span>
                          </td>
                        </template>
                        <template v-else>
                          <td v-if="fcScopeName !== 'Портфель'">{{ fcCell(r.expected, r.unit) }}</td>
                          <td v-for="y in fcYears" :key="y">
                            <template v-if="r.byYear[y]">
                              <span class="kpai-fc-v">{{ fcCell(r.byYear[y].value, r.unit) }}</span>
                              <span v-if="r.byYear[y].low != null" class="kpai-fc-band">{{ fcCell(r.byYear[y].low, r.unit) }}…{{ fcCell(r.byYear[y].high, r.unit) }}</span>
                            </template>
                            <template v-else>—</template>
                          </td>
                        </template>
                        <td><span class="kpai-fc-conf" :class="'c-' + r.confidence">{{ t(fcMethodLabel(r.method)) }}</span></td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <div class="kpai-fc-note">
                  {{ t("Числа — детерминированный движок (воспроизводимо); коридор [low…high] — неопределённость прогноза.") }}
                  <template v-if="fcTblMode === 'quarters'">{{ t("Кварталы будущих лет — разбивка годового прогноза по сезонности показателя (план/факт прошлых лет).") }}</template>
                  {{ t("ИИ ниже интерпретирует и корректирует их.") }}
                </div>
              </div>
            </template>
            <!-- Прочие режимы: график выполнения -->
            <div v-else-if="chartRows.length" class="kpai-chart">
              <div class="kpai-chart-title">{{ scope === 'company' ? t("Выполнение по показателям, %") : t("Выполнение по компаниям, %") }}</div>
              <div v-for="(r, i) in chartRows" :key="i" class="kpai-bar-row">
                <span class="kpai-bar-lbl" :title="r.label">{{ r.label }}</span>
                <div class="kpai-bar-track">
                  <div class="kpai-bar-fill" :style="{ width: Math.min(r.value, 150) / 1.5 + '%', background: barColor(r.value) }"></div>
                </div>
                <span class="kpai-bar-val">{{ r.value }}%</span>
              </div>
            </div>
            <div class="kpai-md" v-html="html"></div>
          </template>
          <div v-else class="kpai-empty">
            <b>{{ t("Выберите охват и режим, затем запустите анализ.") }}</b>
            <span>{{ t("ИИ разберёт исполнение KPI, свяжет их с финансовыми показателями (через привязку к строкам ОФР) и — в режиме «Прогноз» — предскажет будущие KPI и предложит новые.") }}</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import * as XLSX from "xlsx";
import { kpiApi } from "@/api/bpKpi";
import type { CompanyForecast } from "@/api/bpKpi";
import { kpiCompletionRatio } from "@/utils/kpiRatio";
import { renderMarkdown } from "@/utils/renderMarkdown";
import { extractHlfHeadline, HLF_LABELS } from "@/utils/hlfHeadline";
import { useCompanyScope } from "@/composables/useCompanyScope";
import { useI18n } from "@/composables/useI18n";
import { useToast } from "@/composables/useToast";

type Mode = "performance" | "correlation" | "forecast";
type Co = { company_id: string; company_name_ru: string; company_code: string | null };
type QOut = { plan: number | null; fact: number | null; weight: number };
type IndOut = {
  name: string; unit: string | null; dir: string; weight: number;
  bp_key: string | null; bp_source: string | null;
  plan: number | null; fact: number | null; expect: number | null; pct: number | null;
  quarters: Record<string, QOut>;
};
type MgrOut = { title: string; role: string | null; indicators: IndOut[] };
type ChartRow = { label: string; value: number };
// Строка модельного прогноза (движок): значение + коридор + квартальная разбивка.
type FcCell = { value: number | null; low: number | null; high: number | null; quarters?: (number | null)[] | null };
type FcRow = {
  name: string; manager: string; unit: string | null;
  fact: number | null; expected: number | null;
  byYear: Record<string, FcCell>; method: string; confidence: string;
};
type FcTrend = { label: string; value: number; projected: boolean; low?: number; high?: number };
type FcSaved = { view: FcRow[]; years: string[]; trend: FcTrend[]; baseYear: number; scopeName: string };
type SavedRec = { raw: string; doneAt: string; year: number; chart?: ChartRow[]; fc?: FcSaved };

const props = defineProps<{ companies: Co[]; year: number; period: string; selectedId: string | null }>();

const { t } = useI18n();
const toast = useToast();
// Область доступа пользователя (не путать с локальным `scope` — охватом анализа).
const coScope = useCompanyScope();
const open = ref(false);
const loading = ref(false);
const error = ref("");
const html = ref("");
const rawMd = ref("");   // сырой Markdown ответа — для копирования и выгрузки в Excel
const chartRows = ref<ChartRow[]>([]);   // данные графика выполнения
const doneAt = ref("");

// ─── Модельный прогноз (детерминированный движок) ─────────────────
const fcView = ref<FcRow[]>([]);         // строки таблицы прогноза
const fcYears = ref<string[]>([]);       // столбцы будущих лет
const fcTrend = ref<FcTrend[]>([]);      // траектория сводного выполнения (компания)
const fcBaseYear = ref<number>(0);
const fcScopeName = ref<string>("");

function barColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 75) return "#D97706";
  return "#E24B4A";
}
// Компактное число с единицей (для Excel-выгрузки — там единица нужна в ячейке).
function fcFmt(v: number | null | undefined, unit: string | null): string {
  if (v == null) return "—";
  const u = unit || "";
  if (u === "%") return `${Math.round(v)}%`;
  const a = Math.abs(v);
  const s = a >= 1000 ? Math.round(v).toLocaleString("ru-RU").replace(/,/g, " ")
    : a >= 10 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "");
  return `${s}${u ? " " + u : ""}`;
}
// Ячейка таблицы — БЕЗ единицы (единица вынесена в название строки), чтобы
// колонки не разъезжались; проценты оставляем со знаком «%» (коротко и понятно).
function fcCell(v: number | null | undefined, unit: string | null): string {
  if (v == null) return "—";
  if ((unit || "") === "%") return `${Math.round(v)}%`;
  const a = Math.abs(v);
  return a >= 1000 ? Math.round(v).toLocaleString("ru-RU").replace(/,/g, " ")
    : a >= 10 ? v.toFixed(0) : v.toFixed(1).replace(/\.0$/, "");
}
// Единица для подписи строки (проценты и пустые не дублируем).
function fcUnit(unit: string | null): string {
  return unit && unit !== "%" ? unit : "";
}
const FC_METHOD: Record<string, string> = {
  pace: "темп", seasonal: "сезон", run_rate: "run-rate", plan: "план",
  actual: "факт", ols: "тренд", cagr: "CAGR", none: "нет данных",
};
function fcMethodLabel(m: string): string { return FC_METHOD[m] || m; }

function buildForecastView(fc: CompanyForecast): void {
  const yset = new Set<string>();
  const rows: FcRow[] = [];
  for (const m of fc.managers) for (const ind of m.indicators) {
    const byYear: Record<string, FcCell> = {};
    for (const p of ind.annual.projections) { byYear[p.period] = { value: p.value, low: p.low, high: p.high, quarters: p.quarters }; yset.add(p.period); }
    const useAnnual = ind.annual.method !== "none";
    rows.push({
      name: ind.name, manager: ind.manager, unit: ind.unit,
      fact: ind.fact_year, expected: ind.quarterly.expected_year, byYear,
      method: useAnnual ? ind.annual.method : ind.quarterly.method,
      confidence: useAnnual ? ind.annual.confidence : ind.quarterly.confidence,
    });
  }
  const trend: FcTrend[] = [];
  for (const h of fc.completion_history) if (h.fact != null) trend.push({ label: String(h.year), value: Math.round(h.fact), projected: false });
  if (fc.completion) for (const p of fc.completion.projections) if (p.value != null)
    trend.push({ label: p.period, value: Math.round(p.value), projected: true, low: p.low ?? undefined, high: p.high ?? undefined });
  fcView.value = rows; fcYears.value = Array.from(yset).sort();
  fcTrend.value = trend; fcBaseYear.value = fc.base_year; fcScopeName.value = fc.company_name;
}

function buildPortfolioForecastView(all: CompanyForecast[], baseYear: number): void {
  const yset = new Set<string>();
  const rows: FcRow[] = [];
  for (const f of all) {
    const byYear: Record<string, FcCell> = {};
    if (f.completion) for (const p of f.completion.projections) { byYear[p.period] = { value: p.value, low: p.low, high: p.high }; yset.add(p.period); }
    const lastHist = [...f.completion_history].reverse().find(h => h.fact != null);
    rows.push({
      name: f.company_name, manager: "", unit: "%",
      fact: lastHist?.fact ?? null, expected: null, byYear,
      method: f.completion?.method || "none", confidence: f.completion?.confidence || "none",
    });
  }
  fcView.value = rows.sort((a, b) => (b.fact ?? -1) - (a.fact ?? -1));
  fcYears.value = Array.from(yset).sort();
  fcTrend.value = []; fcBaseYear.value = baseYear; fcScopeName.value = "Портфель";
}
function resetForecastView(): void { fcView.value = []; fcYears.value = []; fcTrend.value = []; fcTblMode.value = "years"; }
const fcTrendMax = computed(() => Math.max(120, ...fcTrend.value.map(t => t.high ?? t.value)));

// Тоггл таблицы прогноза: по годам ↔ по кварталам выбранного будущего года.
const fcTblMode = ref<"years" | "quarters">("years");
const fcQYear = ref<string>("");
// Кварталы доступны только когда движок дал сезонную разбивку (режим компании).
const hasFcQuarters = computed(() =>
  fcScopeName.value !== "Портфель" &&
  fcView.value.some(r => fcYears.value.some(y => r.byYear[y]?.quarters)));
function setFcTblMode(m: "years" | "quarters"): void {
  fcTblMode.value = m;
  if (m === "quarters" && (!fcQYear.value || !fcYears.value.includes(fcQYear.value)))
    fcQYear.value = fcYears.value[0] || "";
}
const FC_Q = ["Q1", "Q2", "Q3", "Q4"];
const step = ref("");
// Портфельный охват — только для тех, кто видит весь портфель.
const scope = ref<"portfolio" | "company">(coScope.showPortfolioViews.value ? "portfolio" : "company");
const mode = ref<Mode>("performance");
const saved = ref<Record<string, SavedRec>>({});

const MODES: { id: Mode; label: string; hint: string }[] = [
  { id: "performance", label: "Исполнение", hint: "Разбор выполнения KPI: веса, риски, направление" },
  { id: "correlation", label: "KPI ↔ Финансы", hint: "Взаимосвязи операционных KPI и финансовых показателей" },
  { id: "forecast", label: "Прогноз", hint: "Прогноз будущих KPI + предложение новых показателей" },
];
const MODE_LABEL: Record<Mode, string> = { performance: "Исполнение", correlation: "KPI↔Финансы", forecast: "Прогноз" };

const pickedId = ref<string | null>(props.selectedId || (props.companies[0]?.company_id ?? null));
const selectedCompany = computed(() => props.companies.find(c => c.company_id === pickedId.value) || null);
const titleText = computed(() => scope.value === "company"
  ? (selectedCompany.value?.company_name_ru || t("Компания"))
  : t("Все компании портфеля"));

function savedKey(m: Mode = mode.value): string {
  return scope.value === "company" && pickedId.value ? `${m}__${pickedId.value}` : m;
}
// Смена компании в дропдауне — подставить её сохранённый анализ.
function onPickCompany(): void { applyMode(mode.value); }

async function fetchSaved(): Promise<void> {
  try {
    const { api } = await import("@/api/client");
    const r = await api.get("/ai/saved/kpi");
    saved.value = (r.data?.saved || {}) as Record<string, SavedRec>;
  } catch { /* нет доступа/оффлайн — игнор */ }
}
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

// Копировать ответ (Markdown) в буфер обмена.
async function copyAnswer(): Promise<void> {
  if (!rawMd.value) return;
  try { await navigator.clipboard.writeText(rawMd.value); toast.success(t("Анализ скопирован")); }
  catch { toast.error(t("Не удалось скопировать")); }
}

// Выгрузка в Excel: каждая Markdown-таблица ответа → отдельный лист + лист с
// полным текстом. Особенно полезно для прогнозов (структурированные таблицы).
function exportExcel(): void {
  if (!rawMd.value) return;
  const wb = XLSX.utils.book_new();
  // Лист «Модель прогноза» — детерминированные проекции движка (первым листом).
  if (mode.value === "forecast" && fcView.value.length) {
    const isPort = fcScopeName.value === "Портфель";
    const head = [isPort ? t("Компания") : t("Показатель"), ...(isPort ? [] : [t("Руководитель")]),
      t("Тек. факт"), ...(isPort ? [] : [t("Ожид. {y}", { y: fcBaseYear.value })]), ...fcYears.value, t("Метод"), t("Надёжность")];
    const aoa: (string | number)[][] = [head];
    for (const r of fcView.value) {
      const row: (string | number)[] = [r.name];
      if (!isPort) row.push(r.manager || "");
      row.push(fcFmt(r.fact, r.unit));
      if (!isPort) row.push(fcFmt(r.expected, r.unit));
      for (const y of fcYears.value) {
        const c = r.byYear[y];
        row.push(c ? (c.low != null ? `${fcFmt(c.value, r.unit)} [${fcFmt(c.low, r.unit)}…${fcFmt(c.high, r.unit)}]` : fcFmt(c.value, r.unit)) : "—");
      }
      row.push(t(fcMethodLabel(r.method)), r.confidence);
      aoa.push(row);
    }
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), t("Модель прогноза"));
  }
  const lines = rawMd.value.replace(/\r\n/g, "\n").split("\n");
  const tables: string[][][] = [];
  let cur: string[][] | null = null;
  for (const ln of lines) {
    if (/^\s*\|.*\|\s*$/.test(ln)) {
      if (/^\s*\|[\s:|-]+\|\s*$/.test(ln)) continue;  // разделитель |---|
      const row = ln.trim().replace(/^\||\|$/g, "").split("|").map(c =>
        c.trim().replace(/\*\*/g, "").replace(/`/g, ""));
      if (!cur) { cur = []; tables.push(cur); }
      cur.push(row);
    } else { cur = null; }
  }
  let sheetN = 0;
  for (const tbl of tables) {
    if (tbl.length < 2) continue;
    sheetN++;
    const ws = XLSX.utils.aoa_to_sheet(tbl);
    XLSX.utils.book_append_sheet(wb, ws, `${t("Таблица")} ${sheetN}`.slice(0, 31));
  }
  // Полный текст ответа отдельным листом (по строкам).
  const textWs = XLSX.utils.aoa_to_sheet(lines.map(l => [l]));
  textWs["!cols"] = [{ wch: 120 }];
  XLSX.utils.book_append_sheet(wb, textWs, t("Полный текст"));
  const scopeName = scope.value === "company" ? (selectedCompany.value?.company_name_ru || "company") : "портфель";
  XLSX.writeFile(wb, `KPI_${MODE_LABEL[mode.value]}_${scopeName}_${props.year}.xlsx`);
}
function setMode(m: Mode): void { if (!loading.value) applyMode(m); }
function setScope(s: "portfolio" | "company"): void {
  if (loading.value) return;
  scope.value = s;
  if (s === "company" && !pickedId.value) pickedId.value = props.companies[0]?.company_id ?? null;
  applyMode(mode.value);
}

async function openModal(): Promise<void> {
  open.value = true;
  // Страховка: портфельный охват недоступен ограниченному пользователю.
  if (!coScope.showPortfolioViews.value) {
    scope.value = "company";
    if (!pickedId.value) pickedId.value = props.companies[0]?.company_id ?? null;
  }
  await fetchSaved();
  applyMode(mode.value);
}

async function saveResult(raw: string): Promise<void> {
  const key = savedKey();
  const rec: SavedRec = { raw, doneAt: doneAt.value, year: props.year, chart: chartRows.value };
  if (mode.value === "forecast" && fcView.value.length) {
    rec.fc = {
      view: fcView.value, years: fcYears.value, trend: fcTrend.value,
      baseYear: fcBaseYear.value, scopeName: fcScopeName.value,
    };
  }
  saved.value = { ...saved.value, [key]: rec };
  try {
    const { api } = await import("@/api/client");
    await api.put(`/ai/saved/kpi/${key}`, { payload: rec });
  } catch { toast.error(t("Анализ не сохранён на сервере — исчезнет при обновлении. Повторите.")); }
}

async function run(): Promise<void> {
  if (loading.value) return;
  loading.value = true; error.value = ""; html.value = "";
  const single = scope.value === "company" && selectedCompany.value ? selectedCompany.value : null;
  step.value = single ? t("Загружаю KPI: {name}…", { name: single.company_name_ru }) : t("Загружаю KPI всех компаний…");
  try {
    const { api } = await import("@/api/client");
    const cos: Co[] = single ? [single] : props.companies;
    const num = (v: unknown): number | null =>
      (v === null || v === undefined || v === "") ? null : Number(v);
    const built = await Promise.all(cos.map(async (co) => {
      try {
        const { managers } = await kpiApi.getCompanyYear(co.company_id, props.year);
        const mgrsOut: MgrOut[] = [];
        for (const mgr of managers) {
          const inds: IndOut[] = [];
          for (const ind of (mgr.indicators || [])) {
            const linked = !!ind.bp_metric_key;
            const plan = linked && ind.bp_plan_resolved != null ? num(ind.bp_plan_resolved) : num(ind.plan_year);
            const fact = linked && ind.bp_fact_resolved != null ? num(ind.bp_fact_resolved) : num(ind.fact_year);
            const expect = num(ind.bp_expect_resolved);
            const ratio = kpiCompletionRatio(plan, fact, ind.direction);
            const iq = ind as unknown as Record<string, string | number | null>;
            const quarters: Record<string, QOut> = {};
            for (const q of ["q1", "q2", "q3", "q4"]) {
              const qp = num(iq[`${q}_plan`]);
              const qf = num(iq[`${q}_fact`]);
              if (qp != null || qf != null) quarters[q] = { plan: qp, fact: qf, weight: num(iq[`${q}_weight`]) ?? 0 };
            }
            inds.push({
              name: ind.name, unit: ind.unit, dir: ind.direction || "up", weight: num(ind.weight) ?? 0,
              bp_key: ind.bp_metric_key || null, bp_source: ind.bp_source || null,
              plan, fact, expect, pct: ratio != null ? Math.round(ratio * 100) : null, quarters,
            });
          }
          if (inds.length) mgrsOut.push({ title: mgr.title, role: mgr.role, indicators: inds });
        }
        return mgrsOut.length ? { code: co.company_code, name: co.company_name_ru, managers: mgrsOut } : null;
      } catch { return null; }
    }));
    const kpi_rows = built.filter((r): r is NonNullable<typeof r> => r != null);
    if (!kpi_rows.length) {
      error.value = t("Нет KPI-данных за этот год. Заведите показатели в редакторе.");
      loading.value = false; return;
    }
    // График выполнения: по показателям (компания) или взвешенно по компаниям (портфель)
    const cr: ChartRow[] = [];
    if (single) {
      for (const r of kpi_rows) for (const m of r.managers) for (const ind of m.indicators)
        if (ind.pct != null) cr.push({ label: ind.name, value: ind.pct });
    } else {
      for (const r of kpi_rows) {
        let sw = 0, swtd = 0;
        for (const m of r.managers) for (const ind of m.indicators)
          if (ind.pct != null && ind.weight > 0) { sw += ind.weight; swtd += Math.max(0, Math.min(ind.pct, 150)) * ind.weight; }
        if (sw > 0) cr.push({ label: r.name, value: Math.round(swtd / sw) });
      }
    }
    chartRows.value = cr.sort((a, b) => b.value - a.value).slice(0, 20);
    step.value = t("Подтягиваю финансы (HLF) для связки KPI↔финансы…");
    const fin_rows = (await Promise.all(cos.map(async (co) => {
      if (!co.company_code) return null;
      try {
        const r = await api.get(`/financials/companies/${co.company_code}/hlf`);
        const ext = extractHlfHeadline(r.data?.hlf || null);
        return ext ? { code: co.company_code, name: co.company_name_ru, kpis: ext.kpis } : null;
      } catch { return null; }
    }))).filter((r): r is NonNullable<typeof r> => r != null);

    // Модельный прогноз (детерминированный движок) — опора для режима «Прогноз».
    let forecastPayload: unknown = null;
    if (mode.value === "forecast") {
      step.value = t("Считаю модельный прогноз (кварталы + будущие годы)…");
      try {
        if (single) {
          const fc = await kpiApi.getForecast(single.company_id, props.year, 3);
          buildForecastView(fc);
          forecastPayload = fc;
        } else {
          const fcs = (await Promise.all(props.companies.map(async (c) => {
            try { return await kpiApi.getForecast(c.company_id, props.year, 3); } catch { return null; }
          }))).filter((x): x is CompanyForecast => x != null);
          buildPortfolioForecastView(fcs, props.year);
          forecastPayload = {
            portfolio: fcs.map(f => ({
              name: f.company_name, completion: f.completion,
              indicators: f.managers.flatMap(m => m.indicators.map(i => ({
                name: i.name, unit: i.unit, manager: i.manager,
                quarterly: i.quarterly, annual: i.annual,
              }))).slice(0, 10),
            })),
          };
        }
      } catch { resetForecastView(); }
    } else {
      resetForecastView();
    }

    step.value = t("ИИ анализирует KPI и связь с финансами…");
    const resp = await api.post("/ai/kpi-analysis", {
      year: props.year, period: props.period, mode: mode.value,
      focus: single ? single.company_name_ru : null,
      kpi_rows, fin_rows, fin_labels: HLF_LABELS, forecast: forecastPayload,
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
.kpai-btn {
  display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px;
  border: none; border-radius: 9px; cursor: pointer; font-size: 13px; font-weight: 600;
  color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0);
  box-shadow: 0 2px 8px -2px rgba(99, 85, 224, .5);
}
.kpai-btn:disabled { opacity: .6; cursor: default; }
.kpai-btn-ai {
  display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px;
  border-radius: 5px; background: rgba(255, 255, 255, .22); font-size: 10px; font-weight: 700;
}

.kpai-back {
  position: fixed; inset: 0; z-index: var(--z-modal, 9100); display: flex;
  align-items: flex-start; justify-content: center; padding: 6vh 16px 40px;
  background: rgba(20, 20, 34, .5); backdrop-filter: blur(3px);
}
.kpai-card {
  width: min(900px, 100%); max-height: 88vh; display: flex; flex-direction: column;
  background: var(--surface, #fff); border-radius: 18px; overflow: hidden;
  box-shadow: 0 24px 64px -20px rgba(20, 20, 34, .5);
  transition: width .2s ease;
}
/* Режим «Прогноз»: шире, чтобы таблица годов/кварталов помещалась без обрезки */
.kpai-card.kpai-wide { width: min(1180px, 100%); }
.kpai-hd {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 20px 24px 14px;
}
.kpai-eyebrow { font-size: 11px; letter-spacing: .14em; color: #7C6FF7; font-weight: 700; }
.kpai-title { margin: 4px 0 0; font-size: 21px; font-weight: 650; color: var(--ink, #1A1A26); }
.kpai-sub { margin-top: 5px; font-size: 12.5px; color: #8A90A0; }
.kpai-hd-actions { display: flex; align-items: center; gap: 8px; }
.kpai-act {
  height: 30px; padding: 0 12px; border: 1px solid var(--line, #ECECF3); border-radius: 8px;
  background: #fff; cursor: pointer; font-size: 12.5px; font-weight: 600; color: #5A6172;
}
.kpai-act:hover { border-color: #7C6FF7; color: #6355E0; }
.kpai-act-xls { color: #1D7C4D; border-color: #C7E6D5; }
.kpai-act-xls:hover { border-color: #1D9E75; color: #157A48; }
.kpai-x {
  border: none; background: transparent; font-size: 24px; line-height: 1; color: #9AA3B2;
  cursor: pointer; padding: 0 4px;
}

.kpai-ctrls { padding: 0 24px 14px; border-bottom: 1px solid var(--line, #ECECF3); }
.kpai-seg-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 10px; }
.kpai-seg-lbl { font-size: 11px; letter-spacing: .1em; text-transform: uppercase; color: #9AA3B2; font-weight: 600; min-width: 56px; }
.kpai-seg { display: inline-flex; background: #F2F2F8; border-radius: 10px; padding: 3px; }
.kpai-seg button {
  border: none; background: transparent; padding: 6px 13px; border-radius: 8px; cursor: pointer;
  font-size: 13px; font-weight: 600; color: #5A6172;
}
.kpai-seg button.on { background: #fff; color: #6355E0; box-shadow: 0 1px 4px -1px rgba(20, 20, 34, .18); }
.kpai-seg button:disabled { opacity: .45; cursor: default; }
.kpai-run {
  margin-left: auto; height: 36px; padding: 0 18px; border: none; border-radius: 9px; cursor: pointer;
  font-size: 13px; font-weight: 650; color: #fff; background: linear-gradient(135deg, #7C6FF7, #6355E0);
}
.kpai-run:disabled { opacity: .6; cursor: default; }
.kpai-co-select {
  height: 32px; padding: 0 10px; border: 1px solid var(--line, #ECECF3); border-radius: 9px;
  background: #fff; font-size: 13px; color: var(--ink, #1A1A26); max-width: 300px;
}

.kpai-chart { margin-bottom: 18px; padding: 14px 16px; background: #FAFAFD; border: 1px solid var(--line, #ECECF3); border-radius: 12px; }
.kpai-chart-title { font-size: 12px; letter-spacing: .04em; text-transform: uppercase; color: #8A90A0; font-weight: 600; margin-bottom: 10px; }
.kpai-bar-row { display: grid; grid-template-columns: 200px 1fr 46px; align-items: center; gap: 10px; margin: 5px 0; font-size: 12.5px; }
.kpai-bar-lbl { color: var(--ink2, #2C2C3A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpai-bar-track { height: 12px; background: #ECECF3; border-radius: 6px; overflow: hidden; }
.kpai-bar-fill { height: 100%; border-radius: 6px; transition: width .5s ease; }
.kpai-bar-val { text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink2, #2C2C3A); }
@media (max-width: 620px) { .kpai-bar-row { grid-template-columns: 116px 1fr 40px; } }

.kpai-bar-fill.proj { opacity: .55; background-image: repeating-linear-gradient(45deg, rgba(255,255,255,.35) 0 5px, transparent 5px 10px); }
.kpai-fc-tag { margin-left: 6px; font-size: 9.5px; letter-spacing: .04em; text-transform: uppercase; color: #7C6FF7; font-weight: 700; }

/* ─── Модельная таблица прогноза ─── */
.kpai-fc { margin-bottom: 18px; }
.kpai-fc-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.kpai-fc-head .kpai-chart-title { margin-bottom: 0; }
.kpai-fc-toggle { display: flex; align-items: center; gap: 8px; }
.kpai-seg-sm { padding: 2px; }
.kpai-seg-sm button { padding: 4px 10px; font-size: 12px; }
.kpai-fc-yr { height: 28px; padding: 0 8px; font-size: 12px; }
.kpai-fc-scroll { overflow-x: auto; border: 1px solid var(--line, #ECECF3); border-radius: 12px; }
.kpai-fc-tbl { border-collapse: collapse; width: 100%; font-size: 12px; min-width: 520px; }
.kpai-fc-tbl th, .kpai-fc-tbl td { padding: 7px 10px; text-align: right; border-bottom: 1px solid var(--line, #ECECF3); white-space: nowrap; }
.kpai-fc-tbl th:first-child, .kpai-fc-tbl td:first-child { text-align: left; }
.kpai-fc-tbl thead th { background: #F7F7FB; font-weight: 650; color: #5A6172; position: sticky; top: 0; }
.kpai-fc-tbl tbody tr:last-child td { border-bottom: none; }
.kpai-fc-tbl tbody tr:hover td { background: #FAFAFD; }
.kpai-fc-nm { display: flex; flex-direction: column; gap: 1px; max-width: 340px; }
.kpai-fc-nm-t { white-space: normal; }
.kpai-fc-unit { color: #9AA3B2; font-weight: 500; }
.kpai-fc-mgr { font-size: 10.5px; color: #9AA3B2; }
.kpai-fc-v { font-variant-numeric: tabular-nums; font-weight: 600; color: var(--ink, #1A1A26); }
.kpai-fc-band { display: block; font-size: 10px; color: #A0A6B4; font-variant-numeric: tabular-nums; }
.kpai-fc-conf { display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 10.5px; font-weight: 600; }
.kpai-fc-conf.c-high { background: #E3F5EC; color: #157A48; }
.kpai-fc-conf.c-medium { background: #FEF2E0; color: #B4690E; }
.kpai-fc-conf.c-low { background: #FCE9E8; color: #C0392B; }
.kpai-fc-conf.c-none { background: #EEF0F4; color: #8A90A0; }
.kpai-fc-note { margin-top: 8px; font-size: 11.5px; line-height: 1.5; color: #8A90A0; }

.kpai-body { padding: 18px 24px 26px; overflow-y: auto; }
.kpai-loading { display: flex; align-items: center; gap: 12px; color: #6E6D80; font-size: 14px; padding: 30px 0; }
.kpai-spin {
  width: 18px; height: 18px; border: 2.5px solid #E2E1F0; border-top-color: #7C6FF7;
  border-radius: 50%; animation: kpaiSpin .8s linear infinite;
}
@keyframes kpaiSpin { to { transform: rotate(360deg); } }
.kpai-error { color: #E24B4A; font-size: 14px; padding: 16px 0; }
.kpai-empty { display: flex; flex-direction: column; gap: 8px; text-align: center; padding: 36px 8px; color: #8A90A0; }
.kpai-empty b { color: var(--ink, #1A1A26); font-size: 15px; }
.kpai-empty span { max-width: 60ch; margin: 0 auto; font-size: 13px; line-height: 1.6; }

.kpai-md { font-size: 14px; line-height: 1.65; color: var(--ink2, #2C2C3A); }
.kpai-md :deep(h1), .kpai-md :deep(h2), .kpai-md :deep(h3), .kpai-md :deep(h4) {
  margin: 18px 0 8px; font-weight: 650; color: var(--ink, #1A1A26); line-height: 1.3;
}
.kpai-md :deep(h1) { font-size: 20px; } .kpai-md :deep(h2) { font-size: 17px; } .kpai-md :deep(h3) { font-size: 15px; }
.kpai-md :deep(p) { margin: 8px 0; }
.kpai-md :deep(ul), .kpai-md :deep(ol) { margin: 8px 0; padding-left: 22px; }
.kpai-md :deep(li) { margin: 4px 0; }
.kpai-md :deep(strong) { color: var(--ink, #1A1A26); font-weight: 650; }
.kpai-md :deep(code) { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; background: #F2F2F8; padding: 1px 5px; border-radius: 5px; }
.kpai-md :deep(table) { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 12.5px; display: block; overflow-x: auto; }
.kpai-md :deep(th), .kpai-md :deep(td) { border: 1px solid var(--line, #ECECF3); padding: 6px 10px; text-align: left; }
.kpai-md :deep(th) { background: #F7F7FB; font-weight: 650; }

@media (max-width: 620px) { .kpai-run { margin-left: 0; } }
</style>
