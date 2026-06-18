<script setup lang="ts">
// ============================================================================
// Big sector-grouped financials table.
//
// Layout (1:1 legacy):
//   Header: Компания | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 | YoY% |  bar  | %портфеля
//   For each sector group:
//     – Sector header strip (colored, with sector total + % of portfolio)
//     – Per-company rows with year values, YoY%, mini-bar (relative magnitude)
//
// All numbers are for the selected metric. Component re-derives values from
// props instead of doing API call — orchestrator passes already-aggregated
// SectorBucket[].
// ============================================================================

import { computed, ref, watch, onBeforeUnmount } from "vue";
import DOMPurify from "dompurify";
import type { SectorBucket } from "./financialsHelpers";
import { fmtCompact, fmtPctSigned } from "./financialsHelpers";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import { runForecast, type ForecastModel } from "@/utils/forecast";
import { api } from "@/api/client";

type FcSel = ForecastModel | "off" | "ai";

const props = defineProps<{
  buckets: SectorBucket[];
  years: number[];
  unit: "bln" | "mln";
  metricLabel: string;
  /** Stable metric key (slug) — scope для сохранённого ИИ-прогноза */
  metricKey?: string;
  /** Year used for YoY calc (current vs current-1) */
  currentYear: number;
  /** Portfolio-wide total of metric across ALL years (for % share calc) */
  grandTotalAllYears: number;
}>();

// Grid-шаблон: число year-колонок = years.length (с прогнозными годами их
// больше 6 → жёсткий repeat(6) ломал сетку и колонка «%портф.» съезжала вниз).
// Компактные минимумы, чтобы таблица помещалась на 13–14" без гор.скролла
// (иначе правая колонка «%портф.» уходила за край и обрезалась). Бар-колонка
// со схлопывающимся min (0) — отдаёт место первой при нехватке ширины.
const gridCols = computed(
  () =>
    `minmax(120px, 1.8fr) repeat(${props.years.length || 1}, minmax(44px, 1fr)) 50px minmax(0px, 0.7fr) 54px`,
);

// Find max abs value across ALL companies for bar scaling
const maxAbsAllYears = computed(() => {
  let max = 0;
  for (const b of props.buckets) {
    for (const c of b.companies) {
      const v = Math.abs(c.sumAllYears);
      if (v > max) max = v;
    }
  }
  return max || 1;
});

// Bar width % helper
function barWidthPct(value: number): number {
  return Math.min(100, Math.round(Math.abs(value) / maxAbsAllYears.value * 100));
}

// Sector total for selected year (used for sector header)
// 2026-05-26: Number-coerce — defensive против string-from-Postgres-numeric.
function bucketSumAllYears(b: SectorBucket): number {
  return b.companies.reduce((s, c) => s + Number(c.sumAllYears ?? 0), 0);
}

function bucketShareOfPortfolio(b: SectorBucket): number {
  if (!props.grandTotalAllYears) return 0;
  return Math.round(Math.abs(bucketSumAllYears(b)) / Math.abs(props.grandTotalAllYears) * 100);
}

// YoY color (positive=green, negative=red, zero=gray)
function yoyColor(yoy: number | null): string {
  if (yoy == null) return "var(--t3, #64748B)";
  if (yoy > 0.5) return "#1D9E75";
  if (yoy < -0.5) return "#E24B4A";
  return "var(--t3, #64748B)";
}

// ── Прогнозные колонки: заполняем будущие годы прогнозом по выбранной модели ──
const FORECAST_OPTS: { id: FcSel; label: string }[] = [
  { id: "off", label: "Прогноз: выкл" },
  { id: "ai", label: "Прогноз: ИИ" },
  { id: "runrate", label: "Прогноз: Run-rate" },
  { id: "cagr", label: "Прогноз: CAGR" },
  { id: "linear", label: "Прогноз: линейный" },
];
const forecastModel = ref<FcSel>("off");

// Последний год факта = макс. год с ненулевыми данными по любой компании.
const lastActualYear = computed(() => {
  let last = props.years[0] ?? 0;
  for (const b of props.buckets)
    for (const c of b.companies)
      for (const y of props.years)
        if (c.valuesByYear[y] != null && c.valuesByYear[y] !== 0 && y > last) last = y;
  return last;
});
function isForecastYear(y: number): boolean { return y > lastActualYear.value; }
function cellIsForecast(y: number): boolean { return forecastModel.value !== "off" && isForecastYear(y); }

const forecastMap = computed(() => {
  const map = new Map<string, Map<number, number>>();
  if (forecastModel.value === "off" || forecastModel.value === "ai") return map;
  const histY = props.years.filter((y) => !isForecastYear(y));
  const fcY = props.years.filter(isForecastYear);
  if (!fcY.length) return map;
  for (const b of props.buckets)
    for (const c of b.companies) {
      const hist = histY.map((y) => ({ year: y, value: c.valuesByYear[y] ?? null }));
      const fc = runForecast(forecastModel.value as ForecastModel, hist, fcY);
      map.set(c.company_code, new Map(fc.map((p) => [p.year, p.value])));
    }
  return map;
});

// ИИ-прогноз: бэкенд возвращает структурные значения — заполняем колонки авто.
const aiForecastMap = ref<Map<string, Map<number, number>>>(new Map());
const aiLoading = ref(false);
const aiError = ref("");
const aiRationale = ref("");
const rationaleOpen = ref(false);
const norm = (s: string) => String(s ?? "").trim().toUpperCase();
async function fetchAiForecast() {
  aiLoading.value = true;
  aiError.value = "";
  aiRationale.value = "";
  aiForecastMap.value = new Map();
  try {
    const histY = props.years.filter((y) => !isForecastYear(y));
    const fcY = props.years.filter(isForecastYear);
    const series: Array<{ code: string; history: Record<number, number> }> = [];
    for (const b of props.buckets)
      for (const c of b.companies) {
        const history: Record<number, number> = {};
        for (const y of histY) {
          const v = c.valuesByYear[y];
          if (v != null && v !== 0) history[y] = Math.round(Number(v) / 1e9); // → млрд
        }
        if (Object.keys(history).length) series.push({ code: c.company_code, history });
      }
    if (!series.length || !fcY.length) { aiError.value = "Недостаточно истории для прогноза"; return; }
    const { data } = await api.post("/ai/forecast", {
      metric_label: props.metricLabel, target_years: fcY, series,
    }, { timeout: 230000 }); // web-поиск долгий — даём бэкенду досчитать
    const fc = (data?.forecast ?? {}) as Record<string, Record<string, number>>;
    const map = new Map<string, Map<number, number>>();
    for (const code of Object.keys(fc)) {
      const ym = new Map<number, number>();
      for (const yStr of Object.keys(fc[code] || {})) {
        const v = Number(fc[code][yStr]);
        if (!isNaN(v)) ym.set(Number(yStr), v * 1e9); // млрд → абсолют
      }
      if (ym.size) map.set(norm(code), ym); // нормализуем код (регистр/пробелы)
    }
    aiForecastMap.value = map;
    aiRationale.value = String(data?.rationale || "").trim();
    if (!map.size) aiError.value = "ИИ не вернул прогноз — попробуйте ещё раз";
    else await saveForecast(); // ← сохраняем на сервере (общее, до новой генерации)
  } catch (e: any) {
    aiError.value = e?.response?.data?.detail || "Ошибка ИИ-прогноза";
    aiForecastMap.value = new Map();
  } finally {
    aiLoading.value = false;
  }
}

// ── Сохранение ИИ-прогноза на СЕРВЕРЕ (общее, ПО МЕТРИКЕ, до новой генерации) ──
function _fcScope(): string { return props.metricKey || "default"; }
function _applyForecast(fc: Record<string, Record<string, number>>): boolean {
  const map = new Map<string, Map<number, number>>();
  for (const code of Object.keys(fc)) {
    const ym = new Map<number, number>();
    for (const yStr of Object.keys(fc[code] || {})) {
      const v = Number(fc[code][yStr]);
      if (!isNaN(v)) ym.set(Number(yStr), v * 1e9);
    }
    if (ym.size) map.set(norm(code), ym);
  }
  aiForecastMap.value = map;
  return map.size > 0;
}
async function saveForecast(): Promise<void> {
  const fc: Record<string, Record<string, number>> = {};
  for (const [code, ym] of aiForecastMap.value) {
    fc[code] = {};
    for (const [y, v] of ym) fc[code][String(y)] = v / 1e9; // абсолют → млрд (как с бэка)
  }
  try {
    await api.put(`/ai/saved/forecast/${_fcScope()}`, {
      payload: { forecast: fc, rationale: aiRationale.value, metric: props.metricLabel },
    });
  } catch { /* кэш на клиенте уже есть — игнор сетевой ошибки */ }
}
async function loadSavedForecast(): Promise<boolean> {
  try {
    const { data } = await api.get("/ai/saved/forecast");
    const saved = (data?.saved || {})[_fcScope()];
    if (!saved?.forecast) return false;
    aiError.value = "";
    aiRationale.value = String(saved.rationale || "");
    return _applyForecast(saved.forecast as Record<string, Record<string, number>>);
  } catch { return false; }
}
// Выбор «ИИ» (или смена метрики на «ИИ») → показываем СОХРАНЁННЫЙ прогноз без
// нового вызова; если сохранённого нет — генерируем впервые.
watch([forecastModel, () => props.metricKey], async ([m]) => {
  if (m !== "ai") return;
  const had = await loadSavedForecast();
  if (!had) await fetchAiForecast();
});

// Сменяющийся статус: что именно сейчас «делает» ИИ.
const BUSY_PHRASES = [
  "Анализирую историю компаний",
  "Цены на золото и металлы",
  "Нефть Brent и природный газ",
  "Курс USD/UZS и инфляцию",
  "Геополитику и санкционный фон",
  "Текущие показатели компаний",
  "Отраслевые темпы роста",
  "Строю базовый сценарий",
];
const busyIdx = ref(0);
let busyTimer: ReturnType<typeof setInterval> | undefined;
watch(aiLoading, (v) => {
  if (busyTimer) { clearInterval(busyTimer); busyTimer = undefined; }
  if (v) {
    busyIdx.value = 0;
    busyTimer = setInterval(() => { busyIdx.value = (busyIdx.value + 1) % BUSY_PHRASES.length; }, 2300);
  }
});
onBeforeUnmount(() => { if (busyTimer) clearInterval(busyTimer); });

// Рендер markdown-обоснования прогноза (заголовки/жирный/списки/таблицы), без эмодзи.
function _esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function _inline(t: string): string {
  return _esc(t).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
}
function renderMd(src: string): string {
  const lines = (src || "").replace(/\r/g, "").split("\n");
  const out: string[] = [];
  let para: string[] = [];
  const flush = () => { if (para.length) { out.push("<p>" + _inline(para.join(" ")) + "</p>"); para = []; } };
  let i = 0;
  while (i < lines.length) {
    const t = lines[i].trim();
    if (!t) { flush(); i++; continue; }
    if (/^#{1,6}\s/.test(t)) {
      flush();
      const lvl = (t.match(/^#+/) as RegExpMatchArray)[0].length;
      const tag = lvl <= 2 ? "h3" : "h4";
      out.push(`<${tag}>${_inline(t.replace(/^#+\s*/, ""))}</${tag}>`);
      i++; continue;
    }
    if (/^-{3,}$/.test(t)) { flush(); out.push("<hr>"); i++; continue; }
    if (/^[-*]\s+/.test(t)) {
      flush();
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) { items.push("<li>" + _inline(lines[i].trim().replace(/^[-*]\s+/, "")) + "</li>"); i++; }
      out.push("<ul>" + items.join("") + "</ul>"); continue;
    }
    if (t.startsWith("|") && i + 1 < lines.length && /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1])) {
      flush();
      const hdr = t.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      i += 2;
      let tbl = '<table class="fst-ra-tbl"><thead><tr>' + hdr.map((h) => `<th>${_inline(h)}</th>`).join("") + "</tr></thead><tbody>";
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const cells = lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        tbl += "<tr>" + cells.map((c) => `<td>${_inline(c)}</td>`).join("") + "</tr>"; i++;
      }
      out.push(tbl + "</tbody></table>"); continue;
    }
    para.push(t); i++;
  }
  flush();
  return DOMPurify.sanitize(out.join("\n"), {
    ALLOWED_TAGS: ["p", "strong", "em", "h3", "h4", "hr", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "br"],
    ALLOWED_ATTR: ["class"],
  });
}
const rationaleHtml = computed(() => renderMd(aiRationale.value));

function cellValue(c: SectorBucket["companies"][number], y: number): number | null {
  if (!isForecastYear(y)) return c.valuesByYear[y] ?? null;
  if (forecastModel.value === "ai") return aiForecastMap.value.get(norm(c.company_code))?.get(y) ?? null;
  if (forecastModel.value === "off") return null;
  return forecastMap.value.get(c.company_code)?.get(y) ?? null;
}
</script>

<template>
  <div class="fst-card">
    <!-- Header -->
    <div class="fst-head">
      <div class="fst-eyebrow">{{ years[0] }}–{{ years[years.length - 1] }}, {{ unit === 'bln' ? 'МЛРД' : 'МЛН' }} UZS</div>
      <div class="fst-fc-ctl">
        <span v-if="aiLoading" class="fst-ai-busy">
          <span class="fst-ai-orbit"><i></i></span>
          <span class="fst-ai-busy-stage">
            <Transition name="fst-ai-cyc" mode="out-in">
              <span :key="busyIdx" class="fst-ai-busy-txt">{{ BUSY_PHRASES[busyIdx] }}</span>
            </Transition>
          </span>
          <span class="fst-ai-dots"><i></i><i></i><i></i></span>
        </span>
        <template v-else>
          <span v-if="aiError" class="fst-fc-err">{{ aiError }}</span>
          <span v-else-if="forecastModel === 'ai' && aiForecastMap.size" class="fst-fc-aibadge">
            Прогнозные данные ИИ
            <button v-if="aiRationale" class="fst-fc-info" type="button" title="Что ИИ учёл при прогнозе" @click="rationaleOpen = true">i</button>
            <button class="fst-fc-info" type="button" title="Перегенерировать прогноз ИИ" @click="fetchAiForecast">↻</button>
          </span>
          <select v-model="forecastModel" class="fst-fc-select" title="Прогноз будущих лет">
            <option v-for="o in FORECAST_OPTS" :key="o.id" :value="o.id">{{ o.label }}</option>
          </select>
        </template>
      </div>

      <Teleport to="body">
        <div v-if="rationaleOpen" class="fst-ra-back" @click.self="rationaleOpen = false" role="dialog" aria-modal="true">
          <div class="fst-ra-card">
            <div class="fst-ra-hd">
              <span>Что ИИ учёл при прогнозе</span>
              <button class="fst-ra-x" type="button" @click="rationaleOpen = false" aria-label="Закрыть">×</button>
            </div>
            <div class="fst-ra-body fst-ra-md" v-html="rationaleHtml"></div>
            <div class="fst-ra-foot">Прогноз — расчётная оценка ИИ (история компаний + цены на сырьё, курсы, макропоказатели, геополитика через web). Проверяйте перед использованием.</div>
          </div>
        </div>
      </Teleport>
    </div>

    <!-- Горизонтальный скролл (моб.): шапка + строки скроллятся по X синхронно,
         иначе на узких экранах правые колонки обрезались (card overflow:hidden). -->
    <div class="fst-scroll">
    <!-- Column headers -->
    <div class="fst-col-row" :style="{ gridTemplateColumns: gridCols }">
      <div class="fst-col fst-col-co">Компания</div>
      <div v-for="y in years" :key="y" class="fst-col fst-col-num" :class="{ 'fst-col-fc': cellIsForecast(y) }">{{ y }}<span v-if="cellIsForecast(y)" class="fst-fc-tag">П</span></div>
      <div class="fst-col fst-col-yoy">YoY</div>
      <div class="fst-col fst-col-bar"></div>
      <div class="fst-col fst-col-share">%портф.</div>
    </div>

    <!-- Sector groups -->
    <div class="fst-body">
      <template v-for="b in buckets" :key="b.sectorCode">
        <!-- Sector strip -->
        <div class="fst-sec uza-side-stripe uza-side-stripe-tight"
             :style="{
               background: b.color + '0E',
               '--stripe-color': b.color,
               borderBottomColor: b.color + '24',
             }">
          <span class="fst-sec-label" :style="{ color: b.color }">
            {{ b.label }} <span class="fst-sec-cnt">({{ b.companies.length }})</span>
          </span>
          <div class="fst-sec-meta">
            <span class="fst-sec-tot">Σ {{ fmtCompact(bucketSumAllYears(b), unit) }}</span>
            <span class="fst-sec-share">· {{ bucketShareOfPortfolio(b) }}% портф.</span>
            <span class="fst-sec-pct" :style="{ color: b.color }">{{ bucketShareOfPortfolio(b) }}%</span>
          </div>
        </div>

        <!-- Company rows -->
        <div v-for="(c, i) in b.companies"
             :key="c.company_code"
             class="fst-row uza-side-stripe uza-side-stripe-tight"
             :style="{
               '--stripe-color': `${b.color}1F`,
               animationDelay: (i * 25) + 'ms',
               gridTemplateColumns: gridCols,
             }">
          <div class="fst-cell-co" style="display:flex; align-items:center; gap:8px; min-width:0;">
            <CompanyAvatar :name="c.company_name_short || c.company_name" :color="b.color" :size="20" />
            <span style="min-width:0; overflow:hidden; text-overflow:ellipsis;">{{ c.company_name_short || c.company_name }}</span>
          </div>

          <div v-for="y in years" :key="y" class="fst-cell-num" :class="{ 'fst-cell-fc': cellIsForecast(y) }">
            <span v-if="aiLoading && cellIsForecast(y)" class="fst-cell-shimmer"></span>
            <span v-else :class="{ 'fst-num-empty': cellValue(c, y) == null }">
              {{ fmtCompact(cellValue(c, y), unit) }}
            </span>
          </div>

          <div class="fst-cell-yoy" :style="{ color: yoyColor(c.yoyPct) }">
            {{ c.yoyPct == null ? '—' : fmtPctSigned(c.yoyPct) }}
          </div>

          <div class="fst-cell-bar">
            <div class="fst-bar-track">
              <div class="fst-bar-fill"
                   :style="{
                     '--w': barWidthPct(c.sumAllYears) + '%',
                     background: b.color,
                     opacity: c.sumAllYears < 0 ? 0.5 : 0.85,
                   }" />
            </div>
          </div>

          <div class="fst-cell-share">
            {{ Math.round(Math.abs(c.sumAllYears) / Math.max(grandTotalAllYears, 1) * 100) }}%
          </div>
        </div>
      </template>

      <div v-if="!buckets.length" class="fst-empty">
        Нет данных по выбранной метрике «{{ metricLabel }}»
      </div>
    </div>
    </div><!-- /.fst-scroll -->
  </div>
</template>

<style scoped>
.fst-card {
  background: var(--card-bg, rgba(255, 255, 255, .82));
  backdrop-filter: blur(16px) saturate(1.5);
  -webkit-backdrop-filter: blur(16px) saturate(1.5);
  border: 1px solid var(--card-border, rgba(255, 255, 255, .70));
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(15, 23, 60, .07), 0 1px 3px rgba(15, 23, 60, .04);
  overflow: hidden;
  animation: finFadeSlideIn .4s ease 280ms both;
}

.fst-head {
  padding: 9px 14px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.fst-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.fst-fc-ctl { display: inline-flex; align-items: center; gap: 8px; }
.fst-fc-err { font-size: 10.5px; font-weight: 600; color: #D14343; }
/* премиум-индикатор расчёта ИИ (компактный, без обрезки) */
.fst-ai-busy {
  display: inline-flex; align-items: center; gap: 7px; white-space: nowrap;
  font-size: 11px; font-weight: 600; color: #6C5CE7;
  background: rgba(108,92,231,.1); border-radius: 999px; padding: 4px 12px;
}
.fst-ai-orbit { position: relative; width: 13px; height: 13px; flex-shrink: 0; }
.fst-ai-orbit i {
  position: absolute; top: 0; left: 50%; width: 4px; height: 4px; margin-left: -2px;
  border-radius: 50%; background: #6C5CE7; transform-origin: 2px 6.5px;
  animation: fstOrbit .8s linear infinite;
}
@keyframes fstOrbit { to { transform: rotate(360deg); } }
.fst-ai-dots { display: inline-flex; gap: 2px; }
.fst-ai-dots i { width: 3px; height: 3px; border-radius: 50%; background: #6C5CE7; animation: fstDot 1.2s ease-in-out infinite; }
.fst-ai-dots i:nth-child(2) { animation-delay: .2s; }
.fst-ai-dots i:nth-child(3) { animation-delay: .4s; }
@keyframes fstDot { 0%, 60%, 100% { opacity: .25; } 30% { opacity: 1; } }
.fst-fc-aibadge {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: 10.5px; font-weight: 700; color: #6C5CE7;
  background: rgba(108,92,231,.1); border-radius: 999px; padding: 3px 6px 3px 11px;
}
.fst-fc-info {
  width: 16px; height: 16px; border-radius: 50%; border: none; cursor: pointer;
  background: #6C5CE7; color: #fff; font-size: 10px; font-weight: 700; font-style: italic;
  font-family: Georgia, serif; line-height: 1; display: inline-flex; align-items: center; justify-content: center;
}
.fst-fc-info:hover { background: #5b4fd0; }
.fst-ra-back {
  position: fixed; inset: 0; z-index: 9600; background: rgba(20,16,40,.5); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center; padding: 20px;
}
.fst-ra-card {
  width: min(560px, 95vw); max-height: 82vh; display: flex; flex-direction: column;
  background: var(--bg1, #fff); border-radius: 16px; box-shadow: 0 30px 70px -15px rgba(30,20,70,.5);
  font-family: Geist, system-ui, sans-serif; animation: fstRaPop .28s cubic-bezier(.34,1.4,.5,1);
}
@keyframes fstRaPop { from { opacity:0; transform: translateY(12px) scale(.97); } to { opacity:1; transform:none; } }
.fst-ra-hd { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid rgba(15,23,60,.07); font-size: 14px; font-weight: 600; color: var(--t1, #1e2a4a); }
.fst-ra-x { background: transparent; border: none; font-size: 20px; color: rgba(15,23,60,.45); cursor: pointer; }
.fst-ra-body { padding: 16px 20px; overflow-y: auto; font-size: 12.5px; line-height: 1.55; color: var(--t1, #1e2a4a); white-space: pre-wrap; }
.fst-ra-foot { padding: 10px 20px 16px; font-size: 10.5px; color: rgba(15,23,60,.55); border-top: 1px solid rgba(15,23,60,.06); line-height: 1.4; }

/* сменяющийся статус ИИ */
.fst-ai-busy-stage { display: inline-block; min-width: 220px; text-align: left; }
.fst-ai-busy-txt { display: inline-block; white-space: nowrap; }
.fst-ai-cyc-enter-active, .fst-ai-cyc-leave-active { transition: opacity .35s ease, transform .35s ease; }
.fst-ai-cyc-enter-from { opacity: 0; transform: translateY(6px); }
.fst-ai-cyc-leave-to { opacity: 0; transform: translateY(-6px); }

/* premium-рендер обоснования (markdown без эмодзи) */
.fst-ra-md { white-space: normal; }
.fst-ra-md :deep(h3) { font-size: 13.5px; font-weight: 700; color: #1e2a4a; margin: 14px 0 6px; }
.fst-ra-md :deep(h3:first-child) { margin-top: 0; }
.fst-ra-md :deep(h4) { font-size: 12px; font-weight: 700; color: #4B4193; margin: 12px 0 5px; }
.fst-ra-md :deep(p) { margin: 0 0 9px; }
.fst-ra-md :deep(strong) { color: #1e2a4a; font-weight: 700; }
.fst-ra-md :deep(ul) { margin: 0 0 9px; padding-left: 18px; }
.fst-ra-md :deep(li) { margin: 2px 0; }
.fst-ra-md :deep(hr) { border: none; border-top: 1px solid rgba(15,23,60,.1); margin: 12px 0; }
.fst-ra-md :deep(.fst-ra-tbl) { width: 100%; border-collapse: collapse; margin: 8px 0 12px; font-size: 11.5px; border: 1px solid rgba(15,23,60,.1); border-radius: 8px; overflow: hidden; }
.fst-ra-md :deep(.fst-ra-tbl th) { background: #F4F3F9; text-align: left; padding: 6px 10px; font-weight: 600; color: #4B4193; border-bottom: 1px solid rgba(15,23,60,.1); white-space: nowrap; }
.fst-ra-md :deep(.fst-ra-tbl td) { padding: 6px 10px; border-bottom: 1px solid rgba(15,23,60,.05); }
.fst-spin {
  width: 11px; height: 11px; border-radius: 50%;
  border: 2px solid rgba(108,92,231,.25); border-top-color: #6C5CE7;
  animation: fstSpin .7s linear infinite; display: inline-block;
}
@keyframes fstSpin { to { transform: rotate(360deg); } }
/* шиммер в прогнозных ячейках во время расчёта ИИ */
.fst-cell-shimmer {
  display: inline-block; width: 70%; height: 11px; border-radius: 4px;
  background: linear-gradient(90deg, rgba(108,92,231,.08) 25%, rgba(108,92,231,.22) 50%, rgba(108,92,231,.08) 75%);
  background-size: 200% 100%; animation: fstShine 1.1s ease-in-out infinite;
}
@keyframes fstShine { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
.fst-fc-select {
  font-size: 11px; font-weight: 600; font-family: inherit;
  color: #4B4193; background: #ECEAFB; border: 1px solid #B9B4E8;
  border-radius: 8px; padding: 4px 9px; cursor: pointer;
}
/* Прогнозные колонки — янтарная подсветка + «П» */
.fst-col-fc { color: #A36500 !important; }
.fst-fc-tag {
  font-size: 8px; font-weight: 700; color: #A36500; background: rgba(224,146,47,.16);
  border-radius: 3px; padding: 0 3px; margin-left: 3px; vertical-align: super;
}
.fst-cell-fc { background: rgba(224,146,47,.05); border-left: 1px dashed rgba(224,146,47,.4); }
.fst-cell-fc span { color: #8A5A12; font-style: italic; }
.fst-cell-fc span.fst-num-empty { color: var(--t3, #94A3B8); font-style: normal; }

/* Column headers */
.fst-col-row {
  display: grid;
  grid-template-columns: minmax(160px, 2fr)
                         repeat(6, minmax(60px, 1fr))
                         60px
                         minmax(80px, 1.2fr)
                         60px;
  background: var(--bg3, #F1F5F9);
  border-bottom: 1px solid var(--border, var(--border-input));
  padding: 6px 12px;
  position: sticky;   /* frozen-шапка при вертикальном скролле внутри .fst-scroll */
  top: 0;
  z-index: 2;
}
.fst-col {
  font-size: 10px;
  font-weight: 600;
  color: var(--t3, var(--t3));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0 4px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.fst-col-co { text-align: left; }
.fst-col-yoy { text-align: right; }
.fst-col-share { text-align: right; }
.fst-col-bar { text-align: left; }

/* Scroll-обёртка: вертикаль (как было у body) + горизонталь (для узких экранов).
   Один контейнер на шапку+тело → они скроллятся по X синхронно и выровнены. */
.fst-scroll {
  /* Только горизонтальный скролл (для широкой таблицы с прогнозными колонками).
     Вертикального внутреннего скролла НЕТ — таблица рендерится целиком, страница
     скроллит сама. Иначе max-height резал последние строки по середине и значения
     «%портф.» выглядели обрезанными. padding-bottom уводит последнюю строку
     из-под горизонтального скроллбара. */
  overflow-x: auto;
  overflow-y: visible;
  scrollbar-width: thin;
  padding-bottom: 10px;
}
.fst-scroll::-webkit-scrollbar { height: 8px; width: 8px; }
.fst-scroll::-webkit-scrollbar-thumb { background: rgba(15, 23, 60, .18); border-radius: 4px; }

/* Body */
.fst-body { /* скролл перенесён на .fst-scroll */ }

.fst-sec {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 14px 6px 18px;
  border-bottom: 0.5px solid;
  animation: finFadeSlideIn .25s ease both;
}
.fst-sec-label {
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.fst-sec-cnt { font-weight: 400; opacity: 0.7; }
.fst-sec-meta {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 11px; font-weight: 500;
  color: var(--t2, #4B5468);
}
.fst-sec-tot { font-variant-numeric: tabular-nums; }
.fst-sec-share { color: var(--t3, var(--t3)); }
.fst-sec-pct {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  min-width: 36px;
  text-align: right;
}

/* Row */
.fst-row {
  display: grid;
  grid-template-columns: minmax(160px, 2fr)
                         repeat(6, minmax(60px, 1fr))
                         60px
                         minmax(80px, 1.2fr)
                         60px;
  padding: 5px 12px 5px 18px;
  border-bottom: 0.5px solid var(--border, var(--border-input));
  align-items: center;
  transition: background .12s;
  font-size: 12px;
  animation: finFadeSlideIn .22s ease both;
}
.fst-row:hover { background: rgba(127, 119, 221, .06); }

/* Планшет/телефон (≤1023): при гор.скролле (прогнозные year-колонки) первая
   колонка «Компания» липкая — имя не уезжает. Непрозрачный фон обязателен. */
@media (max-width: 1023px) {
  .fst-col-co, .fst-cell-co {
    position: sticky; left: 0; z-index: 2;
    background: var(--card-bg, #fff);
    box-shadow: 1px 0 0 var(--border, var(--border-input));
  }
}

.fst-cell-co {
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding-right: 4px;
}
.fst-cell-num, .fst-cell-yoy, .fst-cell-share {
  text-align: right;
  font-variant-numeric: tabular-nums;
  padding: 0 4px;
}
.fst-num-empty { color: var(--t3, var(--t3)); }

.fst-cell-yoy { font-weight: 600; }
.fst-cell-share { color: var(--t3, var(--t3)); font-weight: 500; font-size: 11px; }

.fst-cell-bar {
  padding: 0 4px;
}
.fst-bar-track {
  height: 6px;
  background: rgba(241, 245, 249, 0.5);
  border-radius: 3px;
  overflow: hidden;
}
.fst-bar-fill {
  height: 100%;
  border-radius: 3px;
  width: var(--w, 0%);
  animation: finBarGrow .65s var(--ease-standard) both;
}

.fst-empty {
  padding: 30px 14px;
  text-align: center;
  color: var(--t3, var(--t3));
  font-size: 12px;
  font-style: italic;
}
</style>
