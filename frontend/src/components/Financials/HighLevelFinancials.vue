<script setup lang="ts">
/**
 * HighLevelFinancials — Pack 7.66 + 7.67.
 *
 * Renders + edits per-company hierarchical financial statements (HLF).
 *
 * Features:
 *  - Inline cell editing (numeric)
 *  - Edit row labels
 *  - Add/remove rows (line/subheader/subtotal/total)
 *  - Reorder rows (↑↓)
 *  - Add/remove year column
 *  - Add/remove section
 *  - KPI band (12 metrics: gross/EBITDA/net margins · ROA · ROE · Debt/EBITDA · Current ratio · Equity ratio · FCF · CapEx/Rev · YoY)
 *  - Persist via PUT /financials/companies/{code}/hlf
 *  - Import full XLSX template via POST /financials/hlf-import
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { CompanyListItem } from "@/api/companies";
import NumMixed from "@/components/NumMixed.vue";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import DOMPurify from "dompurify";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";

const toast = useToast();
const { confirmDialog } = useConfirm();

const props = defineProps<{
  companies: CompanyListItem[];
  initialCode?: string;
}>();

interface HlfRow {
  type: string;
  label: string;
  values: (number | null)[];
  mapping?: string;
  // Автосумма для total/subtotal: true=вкл, false=выкл, undefined=эвристика по метке.
  auto?: boolean;
  // Годы ВЛАДЕЮЩЕЙ секции (проставляются в allRows() при уплощении). row.values
  // выровнены по НИМ, а не по глобальным data.years — нужно для честного маппинга
  // год→значение в KPI при расхождении наборов лет секций.
  _secYears?: number[];
}
interface HlfSection { id: string; title: string; years: number[]; rows: HlfRow[]; }
interface HlfData {
  version?: string;
  imported_at?: string;
  imported_by?: string;
  updated_at?: string;
  updated_by?: string;
  filename?: string;
  currency?: string;
  unit?: "bln" | "mln";
  years: number[];
  sections: HlfSection[];
}

// ─── Local state ───
const selectedCode = ref<string>(props.initialCode || (props.companies[0]?.code || ""));
const loading      = ref(false);
const error        = ref<string>("");
const data         = ref<HlfData | null>(null);
const collapsedSec = ref<Set<string>>(new Set());
const editMode     = ref(false);
const dirty        = ref(false);
const saving       = ref(false);
// Optimistic-lock: HLF save — full-blob replace; токен из X-Editor-Token на load,
// эхом If-Match на save → 409 если кто-то сохранил, пока редактировали.
const editorToken  = ref<string | null>(null);
const showAddYear  = ref(false);
const newYearValue = ref<number>(new Date().getFullYear());
const importLoading = ref(false);
const importResult  = ref<{ imported_count?: number; skipped_sheets?: string[]; log?: string[] } | null>(null);
const importFileRef = ref<HTMLInputElement | null>(null);

const displayCompanies = computed(() => {
  return props.companies
    .filter(c => c.is_active !== false)
    .sort((a, b) => (a.name_short || a.code).localeCompare(b.name_short || b.code, "ru"));
});

// ─── Кастомный комбобокс выбора компании (нативный <select> не стилизуется) ───
const coOpen = ref(false);
const coSearch = ref("");
const coHighlight = ref(0);
const coTrigger = ref<HTMLElement | null>(null);
const coPanel = ref<HTMLElement | null>(null);
const coSearchInp = ref<HTMLInputElement | null>(null);
const coPos = ref({ top: 0, left: 0, width: 300 });

const selectedCompany = computed(() =>
  displayCompanies.value.find(c => c.code === selectedCode.value) || null);

const coFiltered = computed(() => {
  const q = coSearch.value.trim().toLowerCase();
  if (!q) return displayCompanies.value;
  return displayCompanies.value.filter(c =>
    (c.code || "").toLowerCase().includes(q) ||
    (c.name_short || c.name_ru || "").toLowerCase().includes(q));
});
watch(coSearch, () => { coHighlight.value = 0; });

function coPlace() {
  const el = coTrigger.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  const width = Math.max(r.width, 300);
  let left = r.right - width;
  if (left < 8) left = 8;
  coPos.value = { top: r.bottom + 6, left, width };
}
async function coOpenMenu() {
  coSearch.value = "";
  coOpen.value = true;
  coPlace();
  const idx = displayCompanies.value.findIndex(c => c.code === selectedCode.value);
  coHighlight.value = idx >= 0 ? idx : 0;
  await nextTick();
  coSearchInp.value?.focus();
  window.addEventListener("scroll", coPlace, true);
  window.addEventListener("resize", coPlace);
  document.addEventListener("mousedown", coDocDown, true);
}
function coClose() {
  coOpen.value = false;
  window.removeEventListener("scroll", coPlace, true);
  window.removeEventListener("resize", coPlace);
  document.removeEventListener("mousedown", coDocDown, true);
}
function coToggle() { coOpen.value ? coClose() : coOpenMenu(); }
function coPick(code: string) { selectedCode.value = code; coClose(); }
function coDocDown(e: MouseEvent) {
  const t = e.target as Node;
  if (coTrigger.value?.contains(t) || coPanel.value?.contains(t)) return;
  coClose();
}
function coKeydown(e: KeyboardEvent) {
  if (!coOpen.value) {
    if (e.key === "ArrowDown" || e.key === "Enter") { e.preventDefault(); coOpenMenu(); }
    return;
  }
  if (e.key === "ArrowDown") { e.preventDefault(); coHighlight.value = Math.min(coHighlight.value + 1, coFiltered.value.length - 1); coScrollHi(); }
  else if (e.key === "ArrowUp") { e.preventDefault(); coHighlight.value = Math.max(coHighlight.value - 1, 0); coScrollHi(); }
  else if (e.key === "Enter") { e.preventDefault(); const c = coFiltered.value[coHighlight.value]; if (c) coPick(c.code); }
  else if (e.key === "Escape") { e.preventDefault(); coClose(); }
}
function coScrollHi() {
  nextTick(() => coPanel.value?.querySelector(".hlf-co-opt.hi")?.scrollIntoView({ block: "nearest" }));
}

// ─── Меню действий над строкой («⋯») ───
// Одна кнопка на строку → выпадающее меню с ПОДПИСАННЫМИ пунктами (Teleport в
// body, чтобы overflow таблицы не обрезал). Раньше был плотный кластер безымянных
// иконок (＋ ∑ ↑ ↓ ×) — непонятно и легко промахнуться.
const rowMenu = ref<{ sec: HlfSection; rowIdx: number; row: HlfRow } | null>(null);
const rowMenuPos = ref({ top: 0, left: 0 });
function openRowMenu(ev: MouseEvent, sec: HlfSection, rowIdx: number) {
  const sameRow = !!rowMenu.value && rowMenu.value.sec === sec && rowMenu.value.rowIdx === rowIdx;
  closeRowMenu();
  if (sameRow) return;   // повторный клик по той же «⋯» — закрыть (toggle)
  const btn = ev.currentTarget as HTMLElement;
  const r = btn.getBoundingClientRect();
  const MENU_W = 236;
  let left = r.right - MENU_W;
  if (left < 8) left = 8;
  rowMenuPos.value = { top: r.bottom + 6, left };
  rowMenu.value = { sec, rowIdx, row: sec.rows[rowIdx] };
  window.addEventListener("scroll", closeRowMenu, true);
  window.addEventListener("resize", closeRowMenu);
  document.addEventListener("mousedown", rowMenuDocDown, true);
  document.addEventListener("keydown", rowMenuKey, true);
}
function closeRowMenu() {
  if (!rowMenu.value) return;
  rowMenu.value = null;
  window.removeEventListener("scroll", closeRowMenu, true);
  window.removeEventListener("resize", closeRowMenu);
  document.removeEventListener("mousedown", rowMenuDocDown, true);
  document.removeEventListener("keydown", rowMenuKey, true);
}
function rowMenuDocDown(e: MouseEvent) {
  const t = e.target as HTMLElement;
  if (document.getElementById("hlf-rowmenu")?.contains(t)) return;
  if (t.closest?.(".hlf-rowmenu-trigger")) return;  // триггер сам делает toggle через @click
  closeRowMenu();
}
function rowMenuKey(e: KeyboardEvent) { if (e.key === "Escape") closeRowMenu(); }
function menuInsert()     { const m = rowMenu.value; if (!m) return; insertRow(m.sec, m.rowIdx + 1, "line"); closeRowMenu(); }
function menuToggleAuto() { const m = rowMenu.value; if (!m) return; toggleAuto(m.row); closeRowMenu(); }
function menuUp()         { const m = rowMenu.value; if (!m) return; moveRow(m.sec, m.rowIdx, -1); closeRowMenu(); }
function menuDown()       { const m = rowMenu.value; if (!m) return; moveRow(m.sec, m.rowIdx, 1); closeRowMenu(); }
async function menuDelete() { const m = rowMenu.value; if (!m) return; closeRowMenu(); await removeRow(m.sec, m.rowIdx); }

onBeforeUnmount(() => { coClose(); closeRowMenu(); });

// ─── Лёгкий Markdown → HTML (для ответа ИИ-анализа), как в FinSectorTable ───
function _esc(t: string): string {
  return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
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
      let tbl = '<table class="hlf-an-tbl"><thead><tr>' + hdr.map((h) => `<th>${_inline(h)}</th>`).join("") + "</tr></thead><tbody>";
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

// ─── ИИ-анализ: полная кросс-компанийная аналитика всех показателей ───
type AnScenario = "cfo" | "investor" | "shareholder";
const AN_SCENARIOS: { id: AnScenario; label: string; hint: string }[] = [
  { id: "cfo", label: "Senior CFO", hint: "Здоровье портфеля, риски, план действий" },
  { id: "investor", label: "Инвестор", hint: "Куда направить капитал, инвест-идеи" },
  { id: "shareholder", label: "Акционер", hint: "Дивиденды, стоимость, возврат капитала" },
];
type AnRow = { code: string; name: string; kpis: Record<string, number | null> };
type AnDef = { key: string; label: string; unit: string };

const anOpen = ref(false);
const anLoading = ref(false);
const anError = ref("");
const anHtml = ref("");
const anRaw = ref("");
const anYear = ref<number | null>(null);
const anCount = ref(0);
const anScenario = ref<AnScenario>("cfo");
// Охват анализа: весь портфель (все компании) ИЛИ только выбранная компания.
const anScope = ref<"portfolio" | "company">("portfolio");
// Ключ хранилища сохранённого анализа: роль (портфель) или роль+код компании
// (чтобы у каждой компании и портфеля был свой сохранённый анализ на роль).
function anSavedKey(sc: AnScenario = anScenario.value): string {
  return anScope.value === "company" && selectedCode.value
    ? `${sc}__${selectedCode.value}` : sc;
}
const anMatrix = ref<AnRow[]>([]);
const anDefs = ref<AnDef[]>([]);
const anDoneAt = ref<string>("");
const anCopyOk = ref(false);

// «Думающий» тикер: шаги, которые ИИ сейчас выполняет (скролл-лента)
const anSteps = ref<string[]>([]);
const anStepShown = ref(0);
let anStepTimer: number | null = null;
function startTicker(steps: string[]) {
  anSteps.value = steps;
  anStepShown.value = 1;
  if (anStepTimer) window.clearInterval(anStepTimer);
  anStepTimer = window.setInterval(() => {
    if (anStepShown.value < anSteps.value.length) anStepShown.value++;
  }, 1600);
}
function stopTicker() { if (anStepTimer) { window.clearInterval(anStepTimer); anStepTimer = null; } }
onBeforeUnmount(() => stopTicker());

// Сохранение результатов анализа — на СЕРВЕРЕ, ОБЩЕЕ для всех, ПО КАЖДОЙ роли
// (scenario). Один прогнал по роли → все видят последний результат этой роли до
// новой генерации. Переключение вкладки-роли показывает её сохранённый анализ.
type AnSavedRec = {
  raw?: string; year?: number | null; count?: number; doneAt?: string;
  matrix?: AnRow[]; defs?: AnDef[];
};
const anSaved = ref<Record<string, AnSavedRec>>({});

async function fetchSaved(): Promise<void> {
  try {
    const { api } = await import("@/api/client");
    const resp = await api.get("/ai/saved/hlf");
    anSaved.value = resp.data?.saved || {};
  } catch { /* нет доступа/оффлайн — игнор */ }
}

// Показать вкладку-роль: подставить её сохранённый анализ (или очистить, если нет).
function applyScenario(sc: AnScenario): void {
  anScenario.value = sc;
  const o = anSaved.value[anSavedKey(sc)];
  if (o?.raw) {
    anRaw.value = o.raw; anHtml.value = renderMd(o.raw);
    anYear.value = o.year ?? null; anCount.value = o.count ?? 0;
    anDoneAt.value = o.doneAt || ""; anMatrix.value = o.matrix || []; anDefs.value = o.defs || [];
  } else {
    anRaw.value = ""; anHtml.value = ""; anYear.value = null; anCount.value = 0;
    anDoneAt.value = ""; anMatrix.value = []; anDefs.value = [];
  }
  anError.value = "";
}

// Переключить охват (портфель ↔ компания) и подставить его сохранённый анализ.
function setAnScope(s: "portfolio" | "company"): void {
  if (anLoading.value) return;
  anScope.value = s;
  applyScenario(anScenario.value);
}

async function saveAnalysis(): Promise<void> {
  const payload: AnSavedRec = {
    raw: anRaw.value, year: anYear.value, count: anCount.value,
    doneAt: anDoneAt.value, matrix: anMatrix.value, defs: anDefs.value,
  };
  const key = anSavedKey();
  anSaved.value = { ...anSaved.value, [key]: payload };
  try {
    const { api } = await import("@/api/client");
    await api.put(`/ai/saved/hlf/${key}`, { payload });
  } catch {
    // P1 аудита (тихие сбои): в памяти обновлено, но на сервере НЕ сохранено —
    // после reload анализ исчезнет. Тост (не anError: он в шаблоне перекрыл бы
    // сам анализ, т.к. v-else-if anError идёт раньше anHtml).
    toast.error("Анализ не сохранён на сервере — при обновлении страницы он исчезнет. Повторите.");
  }
}
async function openAnalysis() {
  anOpen.value = true;
  await fetchSaved();
  if (!anLoading.value) applyScenario(anScenario.value);
}

function latestDataYearIdx(hlf: HlfData): number {
  const rows = hlf.sections.flatMap(s => s.rows);
  const rev = matchRow(rows, "revenue") || matchRow(rows, "net_profit") || matchRow(rows, "total_assets");
  // ВАЖНО: возвращаем индекс в ГЛОБАЛЬНОМ hlf.years (buildKpis индексирует свои
  // values именно по нему через rowValueForYear), а НЕ позицию в row.values.
  // Прежний код брал позицию в rev.values: у ряда с малым числом лет (напр.
  // только 2024 → values длиной 1) возвращал 0, а buildKpis[0] = hlf.years[0] =
  // старейший год (2021, обычно пусто) → все KPI null → «Нет данных для анализа».
  if (rev) {
    for (let yi = hlf.years.length - 1; yi >= 0; yi--) {
      if (rowValueForYear(rev, hlf.years[yi]) != null) return yi;
    }
  }
  return Math.max(0, hlf.years.length - 1);
}

function buildSteps(companyNames: string[], metricLabels: string[]): string[] {
  const s: string[] = [
    "Загружаю отчётность всех компаний портфеля…",
    "Свожу показатели в единую матрицу…",
  ];
  for (const m of metricLabels) s.push(`Сверяю «${m}» с отраслевыми бенчмарками…`);
  for (const n of companyNames.slice(0, 10)) s.push(`Оцениваю профиль: ${n}…`);
  s.push("Ищу выбросы и аномалии по портфелю…");
  s.push("Оцениваю долговую нагрузку и ликвидность…");
  s.push("Сопоставляю качество прибыли (FCF против маржи)…");
  if (anScenario.value === "investor") s.push("Формирую инвест-тезис и аллокацию капитала…");
  else if (anScenario.value === "shareholder") s.push("Оцениваю дивидендный потенциал и создание стоимости…");
  else s.push("Формулирую план действий для инвесткомитета…");
  return s;
}

// Цвет показателя по порогам (для графиков), зеркалит kpiColor.
function metricColorHex(key: string, v: number | null): string {
  if (v == null) return "#94A3B8";
  if (["gm", "ebitda_m", "nm", "roa", "roe", "er", "rev_yoy", "np_yoy"].includes(key)) {
    if (v < 0) return "#A32D2D"; if (v < 5) return "#854F0B"; return "#0F6E56";
  }
  if (key === "de") { if (v > 5) return "#A32D2D"; if (v > 3) return "#854F0B"; return "#0F6E56"; }
  if (key === "cr") { if (v < 1) return "#A32D2D"; if (v < 1.5) return "#854F0B"; return "#0F6E56"; }
  if (key === "fcf") return v < 0 ? "#A32D2D" : "#0F6E56";
  if (key === "capex_rev") return v > 30 ? "#854F0B" : "#534AB7";
  return "#1E2A4A";
}
function fmtMetric(v: number | null, unit: string): string {
  if (v == null) return "—";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(2)}×`;
  return fmtNum(v);
}
// Премиум-графики (ранжированные полосы) — inline-стили, чтобы корректно
// переносились и в печать (PDF), и в Word.
const AN_CHART_KEYS = ["gm", "ebitda_m", "nm", "roe", "de"];
const anChartsHtml = computed(() => {
  if (!anMatrix.value.length) return "";
  const blocks: string[] = [];
  for (const key of AN_CHART_KEYS) {
    const def = anDefs.value.find(d => d.key === key);
    if (!def) continue;
    let items = anMatrix.value
      .map(r => ({ name: r.name, v: r.kpis[key] }))
      .filter(x => x.v != null) as { name: string; v: number }[];
    if (items.length < 2) continue;
    items.sort((a, b) => (key === "de" ? a.v - b.v : b.v - a.v));
    items = items.slice(0, 10);
    const maxAbs = Math.max(...items.map(x => Math.abs(x.v)), 1e-9);
    const rowsHtml = items.map(it => {
      const w = Math.max(2, Math.round(Math.abs(it.v) / maxAbs * 100));
      const c = metricColorHex(key, it.v);
      return `<div style="display:flex;align-items:center;gap:8px;margin:3px 0;font-size:11.5px">`
        + `<span style="flex:0 0 132px;color:#1E2A4A;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${_esc(it.name)}</span>`
        + `<span style="flex:1;height:13px;background:#EEF0F7;border-radius:3px;overflow:hidden;display:block;-webkit-print-color-adjust:exact;print-color-adjust:exact"><span style="display:block;height:100%;width:${w}%;background:${c};border-radius:3px;-webkit-print-color-adjust:exact;print-color-adjust:exact"></span></span>`
        + `<span style="flex:0 0 58px;text-align:right;color:${c};font-weight:600;font-variant-numeric:tabular-nums">${fmtMetric(it.v, def.unit)}</span>`
        + `</div>`;
    }).join("");
    blocks.push(`<div style="margin:0 0 16px"><div style="font-size:12px;font-weight:600;color:#534AB7;text-transform:uppercase;letter-spacing:.04em;margin:0 0 6px">${_esc(def.label)}</div>${rowsHtml}</div>`);
  }
  return blocks.join("");
});

async function copyAnalysis() {
  try {
    await navigator.clipboard.writeText(anRaw.value || "");
    anCopyOk.value = true;
    window.setTimeout(() => { anCopyOk.value = false; }, 1600);
  } catch { /* ignore */ }
}
// Статичный логотип ЕПТ (стрелка-градиент + строки + пиксели) — inline SVG,
// чтобы шапка экспорта была фирменной и в PDF, и в Word.
const EPT_LOGO_SVG = `<svg width="44" height="40" viewBox="0 0 240 220" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="eptg" x1="0" y1="0.5" x2="1" y2="0.5"><stop offset="0%" stop-color="#7F77DD"/><stop offset="100%" stop-color="#1D9E75"/></linearGradient><clipPath id="eptc"><path d="M80 30L210 110L80 190L115 110Z"/></clipPath></defs><path d="M80 30L210 110L80 190L115 110Z" fill="url(#eptg)"/><g clip-path="url(#eptc)"><rect x="80" y="50" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="68" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="86" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="104" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="122" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="140" width="130" height="2" fill="#1E2A4A" opacity="0.5"/><rect x="80" y="158" width="130" height="2" fill="#1E2A4A" opacity="0.5"/></g><g fill="#AFA9EC"><rect x="56" y="50" width="6" height="6"/><rect x="42" y="62" width="6" height="6"/><rect x="28" y="82" width="6" height="6"/><rect x="50" y="94" width="6" height="6"/><rect x="18" y="106" width="5" height="5"/><rect x="36" y="116" width="6" height="6"/><rect x="44" y="138" width="6" height="6"/><rect x="48" y="162" width="6" height="6"/></g></svg>`;

function buildExportHtml(): string {
  const scen = AN_SCENARIOS.find(s => s.id === anScenario.value)?.label || "";
  const head = `<meta charset="utf-8"><title>Анализ ИИ — Единая платформа трансформации</title><style>`
    + `@page{margin:14mm}`
    + `body{font-family:Geist,Arial,sans-serif;color:#1E2A4A;font-size:13px;line-height:1.6;padding:0;max-width:900px;margin:0 auto}`
    + `.ept-hd{display:flex;align-items:center;gap:14px;padding-bottom:14px;border-bottom:2px solid #EEF0F7;margin-bottom:20px}`
    + `.ept-brand{font-size:10px;font-weight:600;letter-spacing:.12em;text-transform:uppercase;color:#7F77DD}`
    + `.ept-h1{font-size:21px;font-weight:600;color:#1E2A4A;letter-spacing:-.01em;margin:2px 0 0}`
    + `.ept-sub{font-size:11.5px;color:#64748B;margin-top:4px}`
    + `h3{font-size:15px;color:#534AB7;margin:18px 0 8px}h4{font-size:12.5px;text-transform:uppercase;letter-spacing:.04em;margin:14px 0 6px}`
    + `table{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:12px}`
    + `th{text-align:left;padding:6px 10px;background:#F4F5FA;border-bottom:1px solid #E5E7F0;font-size:10.5px;text-transform:uppercase}`
    + `td{padding:6px 10px;border-bottom:1px solid #E5E7F0}ul{padding-left:20px}li{margin:3px 0}strong{font-weight:600}hr{border:none;border-top:1px solid #E5E7F0;margin:16px 0}`
    + `</style>`;
  const header = `<div class="ept-hd"><div style="flex-shrink:0;line-height:0">${EPT_LOGO_SVG}</div>`
    + `<div><div class="ept-brand">Единая платформа трансформации</div>`
    + `<div class="ept-h1">Высокоуровневые показатели — анализ ИИ</div>`
    + `<div class="ept-sub">${_esc(scen)} · ${anCount.value} компаний · ${anYear.value ?? ""}<span>${anDoneAt.value ? " · " + _esc(anDoneAt.value) : ""}</span></div></div></div>`;
  const charts = anChartsHtml.value ? `<h3>Визуализация показателей</h3>${anChartsHtml.value}` : "";
  return `<!DOCTYPE html><html><head>${head}</head><body>${header}${charts}${anHtml.value}</body></html>`;
}
function exportWord() {
  const blob = new Blob(["﻿", buildExportHtml()], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `analiz_${anScenario.value}_${anYear.value ?? ""}.doc`;
  document.body.appendChild(a); a.click(); a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function exportPrint() {
  // Печать из скрытого iframe — без popup-окна about:blank.
  const iframe = document.createElement("iframe");
  iframe.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(iframe);
  const doc = iframe.contentWindow?.document;
  if (!doc) { iframe.remove(); return; }
  doc.open(); doc.write(buildExportHtml()); doc.close();
  const win = iframe.contentWindow as Window;
  win.onafterprint = () => window.setTimeout(() => iframe.remove(), 800);
  window.setTimeout(() => { try { win.focus(); win.print(); } catch { iframe.remove(); } }, 400);
}

async function runAnalysis() {
  if (anLoading.value) return;
  anOpen.value = true;
  anLoading.value = true;
  anError.value = "";
  anHtml.value = "";
  anRaw.value = "";
  const _single = anScope.value === "company" && selectedCompany.value ? selectedCompany.value : null;
  startTicker([_single
    ? `Загружаю отчётность: ${_single.name_short || _single.code}…`
    : "Загружаю отчётность всех компаний портфеля…"]);
  try {
    const { api } = await import("@/api/client");
    const cos = _single ? [_single] : displayCompanies.value;
    const results = await Promise.all(cos.map(async (co) => {
      try {
        const resp = await api.get(`/financials/companies/${co.code}/hlf`);
        return { co, hlf: (resp.data?.hlf || null) as HlfData | null };
      } catch { return { co, hlf: null as HlfData | null }; }
    }));
    const defs: AnDef[] = buildKpis([], []).map(k => ({ key: k.key, label: k.label, unit: k.unit }));
    const rows: AnRow[] = [];
    let maxYear = 0;
    for (const { co, hlf } of results) {
      if (!hlf || !hlf.years?.length) continue;
      const krows = hlf.sections.flatMap(s => s.rows);
      const ks = buildKpis(hlf.years, krows);
      const yi = latestDataYearIdx(hlf);
      const kobj: Record<string, number | null> = {};
      for (const k of ks) kobj[k.key] = k.values[yi] ?? null;
      if (Object.values(kobj).some(v => v != null)) {
        rows.push({ code: co.code, name: co.name_short || co.name_ru, kpis: kobj });
        if (hlf.years[yi] > maxYear) maxYear = hlf.years[yi];
      }
    }
    if (!rows.length) { anError.value = "Нет данных для анализа — загрузите отчётность компаний."; stopTicker(); return; }
    const metric_labels: Record<string, string> = {};
    const metric_units: Record<string, string> = {};
    for (const d of defs) { metric_labels[d.key] = d.label; metric_units[d.key] = d.unit; }
    anYear.value = maxYear || null;
    anCount.value = rows.length;
    anMatrix.value = rows;
    anDefs.value = defs;
    startTicker(buildSteps(rows.map(r => r.name), defs.map(d => d.label)));
    const resp = await api.post("/ai/hlf-analysis", {
      year: maxYear || null, metric_labels, metric_units, rows, scenario: anScenario.value,
      focus: _single ? (_single.name_short || _single.name_ru || _single.code) : null,
    }, { timeout: 235000 });
    const raw = resp.data?.analysis || "";
    anRaw.value = raw;
    anHtml.value = renderMd(raw);
    anDoneAt.value = new Date().toLocaleString("ru-RU");
    if (!anHtml.value) anError.value = "ИИ вернул пустой ответ.";
    else await saveAnalysis();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    anError.value = err?.response?.data?.detail || err?.message || "Ошибка анализа";
  } finally {
    anLoading.value = false;
    stopTicker();
  }
}

// ─── Fetch ───
async function load() {
  if (!selectedCode.value) return;
  loading.value = true;
  error.value = "";
  try {
    const { api } = await import("@/api/client");
    const resp = await api.get(`/financials/companies/${selectedCode.value}/hlf`);
    data.value = resp.data?.hlf || null;
    editorToken.value = (resp.headers["x-editor-token"] as string) || null;  // axios lowercases keys
    collapsedSec.value = new Set();
    dirty.value = false;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
    data.value = null;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(selectedCode, async () => {
  if (dirty.value && !(await confirmDialog("Есть несохранённые изменения. Сменить компанию?"))) return;
  await load();
});

// ─── Save ───
async function save() {
  if (!data.value || !selectedCode.value || saving.value) return;
  saving.value = true;
  try {
    // Материализуем авто-суммы в values (бэкенд хранит числа; экспорт/др. консьюмеры
    // видят итог, новая колонка заполняется). Флаг auto сохраняется отдельно.
    for (const sec of data.value.sections) {
      sec.rows.forEach((row, idx) => {
        if (effectiveAuto(row)) row.values = autoSumRow(sec, idx);
      });
    }
    const { api } = await import("@/api/client");
    const resp = await api.put(
      `/financials/companies/${selectedCode.value}/hlf`,
      {
        years: data.value.years,
        sections: data.value.sections,
        currency: data.value.currency || "UZS",
        unit: data.value.unit || "bln",
      },
      editorToken.value ? { headers: { "If-Match": editorToken.value } } : undefined,
    );
    dirty.value = false;
    const newTok = resp.headers?.["x-editor-token"] as string | undefined;
    if (newTok) editorToken.value = newTok;  // re-issue → keep saving without reload
    // Успех = бэкенд закоммитил (API 2xx). Подтверждаем визуально.
    toast.success("Финансовая отчётность сохранена");
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string };
    // Конфликт: кто-то сохранил, пока редактировали. Не сбрасываем dirty →
    // правки на экране целы; просим перезагрузить, чтобы не затереть чужое.
    if (err?.response?.status === 409) {
      error.value = "Данные изменились, пока вы редактировали. Перезагрузите, чтобы не затереть чужие правки.";
      toast.error("Конфликт: отчётность изменена. Перезагрузите, чтобы увидеть актуальные данные.");
      return;
    }
    const reason = err?.response?.data?.detail || err?.message || "неизвестная ошибка";
    error.value = `Не сохранено: ${reason}`;
    toast.error(`Отчётность не сохранена: ${reason}`);
  } finally {
    saving.value = false;
  }
}

async function toggleEditMode() {
  if (editMode.value && dirty.value) {
    if (!(await confirmDialog("Выйти из режима редактирования? Несохранённые изменения будут потеряны."))) return;
    load();
  }
  editMode.value = !editMode.value;
}

// ─── Cell editing ───
function onCellInput(row: HlfRow, yearIdx: number, raw: string) {
  const cleaned = raw.replace(/\s/g, "").replace(",", ".").trim();
  if (cleaned === "" || cleaned === "-") {
    row.values[yearIdx] = null;
  } else {
    const num = Number(cleaned);
    row.values[yearIdx] = isFinite(num) ? num : null;
  }
  dirty.value = true;
}

function getCellDisplay(v: number | null): string {
  if (v == null) return "";
  if (!isFinite(v)) return "";
  return v.toString().replace(".", ",");
}

// Фокус-осознанное отображение ячейки в режиме правки: вне фокуса — читаемый
// формат (округление + разряды, как в просмотре), в фокусе — сырое значение для
// точной правки. Раньше все ячейки показывали сырое «90533,33489» → нечитаемо и
// обрезалось узкой колонкой.
const editingCell = ref<string | null>(null);
function cellKey(secId: string, rowIdx: number, j: number): string { return `${secId}#${rowIdx}#${j}`; }
function cellInputValue(sec: HlfSection, rowIdx: number, j: number, v: number | null): string {
  if (editingCell.value === cellKey(sec.id, rowIdx, j)) return getCellDisplay(v);
  const cv = cellValue(sec, rowIdx, j);
  return cv == null ? "" : fmtNum(cv);
}
function onCellFocus(sec: HlfSection, rowIdx: number, j: number) { editingCell.value = cellKey(sec.id, rowIdx, j); }
function onCellBlur() { editingCell.value = null; }

function onLabelInput(row: HlfRow, raw: string) {
  row.label = raw;
  dirty.value = true;
}

function onSectionTitleInput(sec: HlfSection, raw: string) {
  sec.title = raw;
  dirty.value = true;
}

// ─── Year management ───
function openAddYear() {
  if (!data.value) return;
  const maxYear = Math.max(...data.value.years, new Date().getFullYear() - 1);
  newYearValue.value = maxYear + 1;
  showAddYear.value = true;
}

function commitAddYear() {
  if (!data.value || !newYearValue.value) return;
  const yr = Number(newYearValue.value);
  if (!isFinite(yr) || yr < 1990 || yr > 2100) {
    toast.error("Год должен быть от 1990 до 2100");
    return;
  }
  if (data.value.years.includes(yr)) {
    toast.error(`Год ${yr} уже есть в данных`);
    return;
  }
  data.value.years = [...data.value.years, yr].sort((a, b) => a - b);
  for (const sec of data.value.sections) {
    // Индекс вставки — ПО СВОИМ годам секции, не по глобальным data.years:
    // при расхождении наборов лет глобальный индекс сдвигал значения строки
    // (v под чужим годом). Зеркалит per-section логику removeYear.
    sec.years = [...sec.years, yr].sort((a, b) => a - b);
    const secIdx = sec.years.indexOf(yr);
    for (const row of sec.rows) {
      row.values.splice(secIdx, 0, null);
    }
  }
  dirty.value = true;
  showAddYear.value = false;
}

async function removeYear(yr: number) {
  if (!data.value) return;
  if (!(await confirmDialog({ message: `Удалить колонку «${yr}» во всех секциях? Значения будут потеряны.`, danger: true }))) return;
  data.value.years = data.value.years.filter(y => y !== yr);
  for (const sec of data.value.sections) {
    const idx = sec.years.indexOf(yr);
    if (idx !== -1) {
      sec.years.splice(idx, 1);
      for (const row of sec.rows) {
        row.values.splice(idx, 1);
      }
    }
  }
  dirty.value = true;
}

// ─── Row + section management ───
function _newRow(sec: HlfSection, type: "line" | "subheader" | "subtotal" | "section_header" | "total"): HlfRow {
  return {
    type,
    label: type === "line" ? "Новая строка" :
           type === "subheader" ? "Новая подсекция" :
           type === "subtotal" ? "Итого" :
           type === "section_header" ? "НОВЫЙ ЗАГОЛОВОК" : "ИТОГО",
    values: sec.years.map(() => null),
    // Новые итоговые строки по умолчанию авто-суммируются.
    ...(type === "total" || type === "subtotal" ? { auto: true } : {}),
  };
}
function addRow(sec: HlfSection, type: "line" | "subheader" | "subtotal" | "section_header" | "total") {
  sec.rows.push(_newRow(sec, type));
  dirty.value = true;
}
// Вставка строки на конкретную позицию (по «+» между строками).
function insertRow(sec: HlfSection, idx: number, type: "line" | "subheader" | "subtotal" | "section_header" | "total" = "line") {
  sec.rows.splice(idx, 0, _newRow(sec, type));
  dirty.value = true;
}

// ─── Автосумма итоговых строк (total / subtotal) ───
// Балансовые «Total ...» суммируются автоматически (assets/liabilities/equity),
// но грандтотал «...and equity» и P&L-подытоги (Gross profit и т.п.) — НЕ авто.
function isAdditiveTotalLabel(label: string): boolean {
  const l = (label || "").toLowerCase();
  if (/\band\s+equity|equity\s+and\b|и\s+капитал|капитал\s+и/.test(l)) return false;
  return /total[\s\S]*(asset|liabilit|equit)/i.test(l)
      || /(жами|итого)[\s\S]*(актив|мажб|капитал)/i.test(l);
}
function effectiveAuto(row: HlfRow): boolean {
  if (row.type !== "total" && row.type !== "subtotal") return false;
  return row.auto != null ? row.auto : isAdditiveTotalLabel(row.label);
}
// Сумма строк-line в области итога:
//  • subtotal — назад до ПЕРВОЙ границы (любая не-line строка);
//  • total    — назад до section_header (перешагивая подсекции/подытоги).
function autoSumRow(sec: HlfSection, rowIdx: number): (number | null)[] {
  const row = sec.rows[rowIdx];
  const n = (sec.years || []).length;
  const lineIdxs: number[] = [];
  for (let j = rowIdx - 1; j >= 0; j--) {
    const t = sec.rows[j].type;
    if (t === "line") { lineIdxs.push(j); continue; }
    if (row.type === "subtotal") break;            // подытог: стоп на любой границе
    if (t === "section_header") break;              // итого: стоп только на заголовке секции
    // subheader/subtotal/total — перешагиваем (сами не line)
  }
  const out: (number | null)[] = new Array(n).fill(null);
  for (let yi = 0; yi < n; yi++) {
    let sum = 0, any = false;
    for (const li of lineIdxs) {
      const v = sec.rows[li].values[yi];
      if (v != null && isFinite(v)) { sum += v; any = true; }
    }
    out[yi] = any ? sum : null;
  }
  return out;
}
// Отображаемое значение ячейки: авто-сумма для авто-итогов, иначе хранимое.
function cellValue(sec: HlfSection, rowIdx: number, yearIdx: number): number | null {
  const row = sec.rows[rowIdx];
  if (effectiveAuto(row)) return autoSumRow(sec, rowIdx)[yearIdx];
  return row.values[yearIdx];
}
function toggleAuto(row: HlfRow) {
  row.auto = !effectiveAuto(row);
  dirty.value = true;
}

async function removeRow(sec: HlfSection, rowIdx: number) {
  if (!(await confirmDialog({ message: `Удалить строку «${sec.rows[rowIdx].label}»?`, danger: true }))) return;
  sec.rows.splice(rowIdx, 1);
  dirty.value = true;
}

function moveRow(sec: HlfSection, rowIdx: number, dir: -1 | 1) {
  const newIdx = rowIdx + dir;
  if (newIdx < 0 || newIdx >= sec.rows.length) return;
  const t = sec.rows[rowIdx];
  sec.rows[rowIdx] = sec.rows[newIdx];
  sec.rows[newIdx] = t;
  dirty.value = true;
}

// ─── Сворачиваемый «Cost of sales» ───
// Подстатьи (Consumables, Royalty, Labour, D&A, Utilities, Fuel, Other …) — это
// идущие подряд строки type='line' сразу после «Cost of sales» до первого не-line
// (обычно «Gross profit» = subtotal). Работает для всех компаний без правки данных.
function isCostOfSalesLabel(label: string): boolean {
  const l = (label || "").trim().toLowerCase();
  return l === "cost of sales" || l === "cost of goods sold" || l.includes("себестоимост");
}
const costGroups = computed<Record<string, { parentIdx: number; childIdxs: number[] }>>(() => {
  const out: Record<string, { parentIdx: number; childIdxs: number[] }> = {};
  if (!data.value) return out;
  for (const sec of data.value.sections) {
    const rows = sec.rows;
    for (let i = 0; i < rows.length; i++) {
      if (!isCostOfSalesLabel(rows[i].label)) continue;
      const childIdxs: number[] = [];
      for (let j = i + 1; j < rows.length; j++) {
        if (rows[j].type === "line") childIdxs.push(j);
        else break;  // первый не-line (Gross profit и т.п.) завершает группу
      }
      if (childIdxs.length) out[sec.id] = { parentIdx: i, childIdxs };
      break;  // одна группа «Cost of sales» на секцию
    }
  }
  return out;
});
// По умолчанию РАЗВЁРНУТО (подстатьи видны вложенными); можно свернуть.
const collapsedCost = ref<Set<string>>(new Set());
function isCostParent(secId: string, idx: number): boolean {
  return costGroups.value[secId]?.parentIdx === idx;
}
function isCostChild(secId: string, idx: number): boolean {
  return !!costGroups.value[secId]?.childIdxs.includes(idx);
}
function costChildCount(secId: string): number {
  return costGroups.value[secId]?.childIdxs.length ?? 0;
}
function costCollapsed(secId: string): boolean {
  return collapsedCost.value.has(secId);
}
function toggleCost(secId: string): void {
  const s = new Set(collapsedCost.value);
  s.has(secId) ? s.delete(secId) : s.add(secId);
  collapsedCost.value = s;
}

function addSection() {
  if (!data.value) return;
  data.value.sections.push({
    id: `custom_${Date.now()}`,
    title: "Новая секция",
    years: [...data.value.years],
    rows: [],
  });
  dirty.value = true;
}

async function removeSection(secIdx: number) {
  if (!data.value) return;
  if (!(await confirmDialog({ message: `Удалить секцию «${data.value.sections[secIdx].title}»?`, danger: true }))) return;
  data.value.sections.splice(secIdx, 1);
  dirty.value = true;
}

// ─── Display helpers ───
function fmtNum(v: number | null): string {
  if (v == null || !isFinite(v)) return "—";
  if (v === 0) return "0";
  const abs = Math.abs(v);
  let str: string;
  if (abs >= 1000) str = Math.round(v).toLocaleString("ru", { maximumFractionDigits: 0 });
  else if (abs >= 10) str = v.toLocaleString("ru", { maximumFractionDigits: 1 });
  else str = v.toLocaleString("ru", { maximumFractionDigits: 2 });
  // \u0422\u043e\u043b\u044c\u043a\u043e \u0440\u0430\u0437\u0440\u044f\u0434\u044b (NBSP) \u2192 \u043e\u0431\u044b\u0447\u043d\u044b\u0439 \u043f\u0440\u043e\u0431\u0435\u043b; \u0434\u0435\u0441\u044f\u0442\u0438\u0447\u043d\u0443\u044e \u0437\u0430\u043f\u044f\u0442\u0443\u044e \u041d\u0415 \u0442\u0440\u043e\u0433\u0430\u0435\u043c,
  // \u0438\u043d\u0430\u0447\u0435 \u00ab325,1\u00bb \u043f\u0440\u0435\u0432\u0440\u0430\u0449\u0430\u043b\u043e\u0441\u044c \u0432 \u00ab325 1\u00bb (\u043d\u0435\u043e\u0442\u043b\u0438\u0447\u0438\u043c\u043e \u043e\u0442 \u0442\u044b\u0441\u044f\u0447).
  return str.replace(/\u00a0/g, " ");
}

function toggleSection(id: string) {
  const s = new Set(collapsedSec.value);
  if (s.has(id)) s.delete(id); else s.add(id);
  collapsedSec.value = s;
}

function formatDate(iso?: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru", {
      day: "2-digit", month: "2-digit", year: "numeric",
      hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}

// ─── Import ───
function triggerFilePick() { importFileRef.value?.click(); }

async function onFileChange(evt: Event) {
  const input = evt.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  importLoading.value = true;
  importResult.value = null;
  try {
    const { api } = await import("@/api/client");
    const fd = new FormData();
    fd.append("file", file);
    const resp = await api.post("/financials/hlf-import", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    importResult.value = resp.data;
    await load();
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || "Не удалось импортировать";
  } finally {
    importLoading.value = false;
    if (input) input.value = "";
  }
}

// ════════════════════════════════════════════════════════════════════════
// KPI EXTRACTION
// ════════════════════════════════════════════════════════════════════════
const LABEL_MATCHERS: Record<string, string[]> = {
  revenue: ["выручка", "revenue", "тушум", "sales revenue"],
  cogs: ["себестоимость", "cost of sales", "cost of goods", "cost of revenue", "таннарх", "cos"],
  gross_profit: ["gross profit", "валовая прибыль"],
  operating_profit: ["operating profit", "операционная прибыль", "profit from operations"],
  depreciation: [
    "depreciation, depletion", "depreciation and amortization", "depreciation and amortisation",
    "depreciation, depletion and amortization", "амортизация", "d&a", "d & a",
  ],
  finance_costs: ["finance costs", "finance cost", "финансовые расходы", "interest expense"],
  net_profit: [
    "profit for the year", "net profit for the year", "net income for the year",
    "соф фойда", "profit attributable to", "чистая прибыль"
  ],
  total_assets: ["total assets", "жами активлар"],
  total_equity: ["total equity", "капитал", "shareholders' equity", "shareholders equity"],
  total_current_assets: ["total current assets", "жорий активлар"],
  total_current_liabilities: ["total current liabilities", "қисқа муддатли мажб"],
  cash: [
    "денежные средства и их эквиваленты", "cash and cash equivalents at the end",
    "cash and cash equivalents", "нақд пул",
  ],
  operating_cf: [
    "operating cash flow", "cash from operating activities", "net cash from operating",
    "cash generated from operating", "cash flows from operating",
  ],
  capex: [
    "purchase of ppe", "purchases of property", "purchases of ppe",
    "purchase of property, plant", "capital expenditures", "capex",
    "капитальные затраты", "капитал қўйилмалар",
    "additions to property, plant", "additions to ppe",
  ],
  dividends_paid: ["dividends paid", "тўланган дивидендл"],
};

function matchRow(rows: HlfRow[], key: string): HlfRow | null {
  const patterns = LABEL_MATCHERS[key];
  if (!patterns) return null;
  for (const p of patterns) {
    const lp = p.toLowerCase();
    const found = rows.find(r =>
      r.type !== "section_header" && r.type !== "subheader" &&
      (r.label.toLowerCase().includes(lp) ||
       (r.mapping || "").toLowerCase().includes(lp))
    );
    if (found) return found;
  }
  return null;
}

function allRows(): HlfRow[] {
  if (!data.value) return [];
  // Уплощаем в КОПИИ с проставленными _secYears — так каждый ряд знает годы
  // своей секции (values выровнены по ним). Копии, чтобы не мутировать источник;
  // потребители (buildKpis, авто-выбор года) только читают.
  return data.value.sections.flatMap(s => s.rows.map(r => ({ ...r, _secYears: s.years })));
}

// Значение ряда за КОНКРЕТНЫЙ год (не по глобальному индексу): маппим год через
// годы владеющей секции. targetYear === null → fallback к позиционному индексу.
function rowValueForYear(r: HlfRow, targetYear: number | null): number | null {
  if (targetYear == null) return null;
  const sy = r._secYears;
  if (!sy) return null;
  const li = sy.indexOf(targetYear);
  return li === -1 ? null : (r.values[li] ?? null);
}

function totalDebtIn(rows: HlfRow[], targetYear: number): number | null {
  const matched = rows.filter(r =>
    r.type !== "section_header" && r.type !== "subheader" &&
    (r.label.toLowerCase().includes("займ") ||
     r.label.toLowerCase().includes("borrowing") ||
     (r.mapping || "").toLowerCase().includes("қарзлар"))
  );
  let sum = 0, any = false;
  for (const r of matched) {
    const v = rowValueForYear(r, targetYear);
    // 2026-05-26: Number-coerce — backend numeric может приходить строкой.
    if (v != null) { sum += Number(v); any = true; }
  }
  return any ? sum : null;
}

interface KpiVal { label: string; key: string; unit: "%" | "x" | "money"; values: (number | null)[]; }

// Чистая функция: считает 12 KPI для любого набора (годы + строки). Используется
// и для выбранной компании (computed kpis), и для кросс-компанийного ИИ-анализа.
function buildKpis(years: number[], rows: HlfRow[]): KpiVal[] {
  // yi — индекс в ГЛОБАЛЬНОМ массиве years; значение ряда берём по годовому
  // ЗНАЧЕНИЮ (years[yi]) через годы его секции, а не по позиции yi в row.values —
  // иначе при расхождении наборов лет секций числитель и знаменатель KPI брались
  // бы из РАЗНЫХ годов (ROA = чистая прибыль одного года / активы другого).
  const get = (key: string, yi: number): number | null => {
    const r = matchRow(rows, key);
    return r ? rowValueForYear(r, years[yi] ?? null) : null;
  };
  const computeMetric = (fn: (yi: number) => number | null): (number | null)[] => years.map((_, yi) => fn(yi));

  return [
    {
      label: "Gross margin", key: "gm", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), g = get("gross_profit", yi);
        return (r != null && g != null && r > 0) ? (g / r) * 100 : null;
      }),
    },
    {
      label: "EBITDA margin", key: "ebitda_m", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), op = get("operating_profit", yi), d = get("depreciation", yi);
        if (r == null || r <= 0 || op == null) return null;
        return ((op + (d == null ? 0 : Math.abs(d))) / r) * 100;
      }),
    },
    {
      label: "Net margin", key: "nm", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), np = get("net_profit", yi);
        return (r != null && np != null && r > 0) ? (np / r) * 100 : null;
      }),
    },
    {
      label: "ROA", key: "roa", unit: "%",
      values: computeMetric(yi => {
        const ta = get("total_assets", yi), np = get("net_profit", yi);
        return (ta != null && np != null && ta > 0) ? (np / ta) * 100 : null;
      }),
    },
    {
      label: "ROE", key: "roe", unit: "%",
      values: computeMetric(yi => {
        const eq = get("total_equity", yi), np = get("net_profit", yi);
        return (eq != null && np != null && eq > 0) ? (np / eq) * 100 : null;
      }),
    },
    {
      label: "Debt / EBITDA", key: "de", unit: "x",
      values: computeMetric(yi => {
        const debt = totalDebtIn(rows, years[yi]);
        const op = get("operating_profit", yi), d = get("depreciation", yi);
        if (debt == null || op == null) return null;
        const ebitda = op + (d == null ? 0 : Math.abs(d));
        return ebitda > 0 ? debt / ebitda : null;
      }),
    },
    {
      label: "Current ratio", key: "cr", unit: "x",
      values: computeMetric(yi => {
        const ca = get("total_current_assets", yi), cl = get("total_current_liabilities", yi);
        return (ca != null && cl != null && cl > 0) ? ca / cl : null;
      }),
    },
    {
      label: "Equity ratio", key: "er", unit: "%",
      values: computeMetric(yi => {
        const ta = get("total_assets", yi), eq = get("total_equity", yi);
        return (ta != null && eq != null && ta > 0) ? (eq / ta) * 100 : null;
      }),
    },
    {
      label: "FCF", key: "fcf", unit: "money",
      values: computeMetric(yi => {
        const cfo = get("operating_cf", yi), cx = get("capex", yi);
        if (cfo == null) return null;
        return cfo - (cx == null ? 0 : Math.abs(cx));
      }),
    },
    {
      label: "CapEx / Revenue", key: "capex_rev", unit: "%",
      values: computeMetric(yi => {
        const r = get("revenue", yi), cx = get("capex", yi);
        return (r != null && cx != null && r > 0) ? (Math.abs(cx) / r) * 100 : null;
      }),
    },
    {
      label: "Revenue YoY", key: "rev_yoy", unit: "%",
      values: computeMetric(yi => {
        if (yi === 0) return null;
        const r = get("revenue", yi), p = get("revenue", yi - 1);
        return (r != null && p != null && p > 0) ? ((r - p) / p) * 100 : null;
      }),
    },
    {
      label: "Net profit YoY", key: "np_yoy", unit: "%",
      values: computeMetric(yi => {
        if (yi === 0) return null;
        const n = get("net_profit", yi), p = get("net_profit", yi - 1);
        return (n != null && p != null && p !== 0) ? ((n - p) / Math.abs(p)) * 100 : null;
      }),
    },
  ];
}

const kpis = computed<KpiVal[]>(() =>
  data.value ? buildKpis(data.value.years, allRows()) : []);

function fmtKpi(v: number | null, unit: string): string {
  if (v == null) return "—";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(2)}×`;
  return fmtNum(v);
}

function kpiColor(kpi: KpiVal, yi: number): string {
  const v = kpi.values[yi];
  if (v == null) return "#94A3B8";
  if (kpi.unit === "%" && ["gm", "ebitda_m", "nm", "roa", "roe", "er", "rev_yoy", "np_yoy"].includes(kpi.key)) {
    if (v < 0) return "#A32D2D";
    if (v < 5) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "de") {
    if (v > 5) return "#A32D2D";
    if (v > 3) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "cr") {
    if (v < 1) return "#A32D2D";
    if (v < 1.5) return "#854F0B";
    return "#0F6E56";
  }
  if (kpi.key === "fcf") return v < 0 ? "#A32D2D" : "#0F6E56";
  if (kpi.key === "capex_rev") return v > 30 ? "#854F0B" : "#534AB7";
  return "#1E2A4A";
}

// Premium: directional delta vs prior year. For most metrics higher = better;
// Debt/EBITDA and CapEx/Revenue are inverted (lower = better).
interface KpiDelta { txt: string; dir: 1 | -1 | 0; good: boolean; }
function kpiDelta(k: KpiVal, yi: number): KpiDelta | null {
  if (yi <= 0) return null;
  const cur = k.values[yi], prev = k.values[yi - 1];
  if (cur == null || prev == null) return null;
  const diff = cur - prev;
  if (Math.abs(diff) < 1e-9) return { txt: "—", dir: 0, good: true };
  const lowerBetter = k.key === "de" || k.key === "capex_rev";
  const good = lowerBetter ? diff < 0 : diff > 0;
  let txt: string;
  if (k.unit === "%") txt = `${Math.abs(diff).toFixed(1)} пп`;
  else if (k.unit === "x") txt = `${Math.abs(diff).toFixed(2)}×`;
  else txt = fmtNum(Math.abs(diff));
  return { txt, dir: diff > 0 ? 1 : -1, good };
}

const activeKpiYearIdx = ref<number>(0);

// Auto-select most recent year with data when data loads/changes
watch(data, () => {
  if (!data.value || data.value.years.length === 0) {
    activeKpiYearIdx.value = 0;
    return;
  }
  // Find revenue or any KPI row; pick last year that has a value
  const rows = allRows();
  const revenueRow = matchRow(rows, "revenue") || matchRow(rows, "net_profit") || matchRow(rows, "total_assets");
  if (revenueRow) {
    // Идём по ГЛОБАЛЬНЫМ годам от свежих к старым; значение берём через годы
    // секции (activeKpiYearIdx — глобальный индекс, им же индексируются kpis).
    const gYears = data.value.years;
    for (let i = gYears.length - 1; i >= 0; i--) {
      if (rowValueForYear(revenueRow, gYears[i]) != null) {
        activeKpiYearIdx.value = i;
        return;
      }
    }
  }
  activeKpiYearIdx.value = data.value.years.length - 1;
}, { deep: true, immediate: true });

// Count how many KPIs have a value at this year
function kpiCoverage(yi: number): number {
  return kpis.value.filter(k => k.values[yi] != null).length;
}

// Premium: bundle per-card render data for the active year (avoids repeated
// function calls in the template).
const kpiCards = computed(() => kpis.value.map(k => ({
  k,
  color: kpiColor(k, activeKpiYearIdx.value),
  valStr: fmtKpi(k.values[activeKpiYearIdx.value], k.unit),
  delta: kpiDelta(k, activeKpiYearIdx.value),
})));
</script>

<template>
  <div class="hlf-card">

    <!-- Header -->
    <div class="hlf-hdr">
      <div class="hlf-hdr-left">
        <div class="hlf-eyebrow">ВЫСОКОУРОВНЕВЫЕ ПОКАЗАТЕЛИ</div>
        <div class="hlf-title">Финансовая отчётность по компаниям</div>
        <div class="hlf-sub">
          Иерархия из консолидированного шаблона
          <template v-if="data?.updated_at"> · ред. {{ formatDate(data.updated_at) }}</template>
          <template v-else-if="data?.imported_at"> · импорт {{ formatDate(data.imported_at) }}</template>
          <span v-if="dirty" class="hlf-dirty"> · есть несохранённые изменения</span>
        </div>
      </div>
      <div class="hlf-hdr-right">
        <div ref="coTrigger" class="hlf-co">
          <button type="button" class="hlf-co-trigger" :class="{ open: coOpen }"
                  @click="coToggle" @keydown="coKeydown">
            <CompanyAvatar v-if="selectedCompany"
              :name="selectedCompany.name_short || selectedCompany.name_ru"
              :code="selectedCompany.code" :color="selectedCompany.sector_color || undefined" :size="20" />
            <span class="hlf-co-trig-name">{{ selectedCompany ? (selectedCompany.name_short || selectedCompany.name_ru) : "Выберите компанию" }}</span>
            <span v-if="selectedCompany" class="hlf-co-trig-code">{{ selectedCompany.code }}</span>
            <svg class="hlf-co-chev" :class="{ up: coOpen }" viewBox="0 0 12 12" width="11" height="11"
                 fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4.5L6 7.5l3-3"/></svg>
          </button>
        </div>
        <button class="hlf-btn-analyze" @click="openAnalysis" :disabled="anLoading">
          <svg viewBox="0 0 14 14" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9l3-3 2.5 2.5L12 4M12 4H8.5M12 4v3.5"/></svg>
          {{ anLoading ? "Анализирую…" : "Анализ ИИ" }}
        </button>
        <button v-if="data" class="hlf-btn-mode" :class="{ on: editMode }"
                @click="toggleEditMode">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M2 11L9 4l3 3-7 7H2v-3zM8 5l3 3"/></svg>
          {{ editMode ? "Просмотр" : "Редактировать" }}
        </button>
        <button v-if="editMode && data" class="hlf-btn-year" @click="openAddYear">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M7 2v10M2 7h10"/></svg>
          + год
        </button>
        <button v-if="editMode && data" class="hlf-btn-section" @click="addSection">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="3" width="10" height="8" rx="1"/><path d="M7 5v4M5 7h4"/></svg>
          + секция
        </button>
        <button v-if="dirty && data" class="hlf-btn-save" @click="save" :disabled="saving">
          {{ saving ? "Сохраняю…" : "Сохранить" }}
        </button>
        <button class="hlf-btn-import" @click="triggerFilePick" :disabled="importLoading">
          <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M7 2v8M3 6l4-4 4 4M2 12h10"/></svg>
          {{ importLoading ? "Импорт…" : "Импорт" }}
        </button>
        <input ref="importFileRef" type="file" accept=".xlsx" style="display:none" @change="onFileChange" />
      </div>
    </div>

    <!-- Add year inline form -->
    <div v-if="showAddYear" class="hlf-add-year">
      <span>Добавить колонку для года:</span>
      <input type="number" v-model.number="newYearValue" min="1990" max="2100" class="hlf-year-inp" />
      <button class="hlf-btn-save" @click="commitAddYear">Добавить</button>
      <button class="hlf-btn-g" @click="showAddYear = false">Отмена</button>
    </div>

    <!-- Import banner -->
    <div v-if="importResult" class="hlf-import-result">
      <strong>✓ Импорт завершён.</strong>
      Обработано компаний: {{ importResult.imported_count || 0 }}.
      <button class="hlf-banner-x" @click="importResult = null">×</button>
    </div>

    <!-- KPI band -->
    <div v-if="data && !error" class="hlf-kpis-wrap">
      <div class="hlf-kpis-hdr">
        <span class="hlf-kpis-lbl">KEY METRICS · {{ data.years[activeKpiYearIdx] }} (млрд UZS · derived)</span>
        <div class="hlf-kpi-yr-pills">
          <button v-for="(y, idx) in data.years" :key="y"
                  class="hlf-yr-pill" :class="{ on: idx === activeKpiYearIdx, weak: kpiCoverage(idx) < 4 }"
                  @click="activeKpiYearIdx = idx"
                  :title="`Покрытие: ${kpiCoverage(idx)}/${kpis.length} KPI`">{{ y }}</button>
        </div>
        <span class="hlf-coverage">{{ kpiCoverage(activeKpiYearIdx) }}/{{ kpis.length }} KPI</span>
      </div>
      <div class="hlf-kpis">
        <div v-for="c in kpiCards" :key="c.k.key" class="hlf-kpi" :title="c.k.label"
             :style="{ '--kpi-accent': c.color }">
          <div class="hlf-kpi-lbl">{{ c.k.label }}</div>
          <div class="hlf-kpi-val" :style="{ color: c.color }"><NumMixed :value="c.valStr" /></div>
          <div v-if="activeKpiYearIdx > 0" class="hlf-kpi-foot">
            <span v-if="c.delta && c.delta.dir !== 0" class="hlf-kpi-delta"
                  :class="c.delta.good ? 'good' : 'bad'">
              <svg viewBox="0 0 10 10" width="8" height="8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path v-if="c.delta.dir === 1" d="M5 8V2M2.5 4.5L5 2l2.5 2.5"/>
                <path v-else d="M5 2v6M2.5 5.5L5 8l2.5-2.5"/>
              </svg>{{ c.delta.txt }}
            </span>
            <span class="hlf-kpi-prev-y">vs {{ data.years[activeKpiYearIdx - 1] }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- States -->
    <div v-if="loading" class="hlf-state">Загрузка…</div>
    <div v-else-if="error" class="hlf-state hlf-state-error">{{ error }}</div>
    <div v-else-if="!data" class="hlf-state hlf-state-empty">
      <div class="hlf-empty-icon">
        <svg viewBox="0 0 32 32" width="40" height="40" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><rect x="5" y="4" width="22" height="24" rx="2"/><path d="M10 11h12M10 15h12M10 19h8M10 23h6"/></svg>
      </div>
      <div class="hlf-empty-title">Данные не загружены</div>
      <div class="hlf-empty-text">
        Загрузи XLSX-шаблон с консолидированными показателями (SOFP / P&amp;L / Cash Flow)
        через кнопку «Импорт» наверху. Парсер обработает все 22 листа автоматически.
      </div>
    </div>

    <!-- Data sections -->
    <template v-else>
      <div v-for="(sec, secIdx) in data.sections" :key="sec.id" class="hlf-section">

        <div class="hlf-sec-hdr">
          <button v-if="!editMode" type="button" class="hlf-sec-toggle"
                  @click="toggleSection(sec.id)" :aria-expanded="!collapsedSec.has(sec.id)">
            <svg class="hlf-chevron" :class="{ collapsed: collapsedSec.has(sec.id) }"
                 viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor"
                 stroke-width="1.8" stroke-linecap="round"><path d="M4 3l4 3-4 3"/></svg>
            <span class="hlf-sec-title">{{ sec.title }}</span>
          </button>
          <template v-else>
            <button type="button" class="hlf-chevron-btn"
                    @click="toggleSection(sec.id)" :aria-expanded="!collapsedSec.has(sec.id)"
                    :aria-label="collapsedSec.has(sec.id) ? 'Развернуть секцию' : 'Свернуть секцию'">
              <svg class="hlf-chevron" :class="{ collapsed: collapsedSec.has(sec.id) }"
                   viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor"
                   stroke-width="1.8" stroke-linecap="round"><path d="M4 3l4 3-4 3"/></svg>
            </button>
            <input type="text" class="hlf-sec-title-inp" :value="sec.title"
                   @input="onSectionTitleInput(sec, ($event.target as HTMLInputElement).value)" />
          </template>
          <span class="hlf-sec-meta">{{ sec.rows.length }} строк · {{ data.unit === 'bln' ? 'млрд UZS' : data.unit }}</span>
          <button v-if="editMode" class="hlf-sec-remove" @click="removeSection(secIdx)" title="Удалить секцию">×</button>
        </div>

        <div v-if="!collapsedSec.has(sec.id)" class="hlf-table-wrap">
          <table class="hlf-table">
            <thead>
              <tr>
                <th class="hlf-th-name">ПОКАЗАТЕЛЬ</th>
                <th v-for="(y, idx) in sec.years" :key="y" class="hlf-th-num"
                    :class="{ current: idx === sec.years.length - 1 }">
                  {{ y }}
                  <button v-if="editMode" class="hlf-th-x" @click="removeYear(y)" title="Удалить год">×</button>
                </th>
                <th v-if="editMode" class="hlf-th-actions"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIdx) in sec.rows" :key="`${sec.id}-${rowIdx}`"
                  v-show="editMode || !(isCostChild(sec.id, rowIdx) && costCollapsed(sec.id))"
                  :class="[`hlf-row-${row.type}`, { 'hlf-cost-child': isCostChild(sec.id, rowIdx) }]">
                <td class="hlf-td-name">
                  <input v-if="editMode" type="text" class="hlf-label-inp" :value="row.label"
                         @input="onLabelInput(row, ($event.target as HTMLInputElement).value)" />
                  <template v-else>
                    <button v-if="isCostParent(sec.id, rowIdx)" type="button" class="hlf-cost-toggle"
                            :class="{ collapsed: costCollapsed(sec.id) }"
                            :title="costCollapsed(sec.id) ? 'Развернуть подстатьи' : 'Свернуть подстатьи'"
                            @click="toggleCost(sec.id)">
                      <svg width="9" height="9" viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2l4 3-4 3"/></svg>
                    </button>
                    <span :class="{ 'hlf-cost-child-lbl': isCostChild(sec.id, rowIdx) }">{{ row.label }}</span>
                    <span v-if="isCostParent(sec.id, rowIdx) && costCollapsed(sec.id)" class="hlf-cost-badge">{{ costChildCount(sec.id) }}</span>
                  </template>
                </td>
                <template v-if="['section_header', 'subheader'].includes(row.type) && !editMode">
                  <td :colspan="sec.years.length" class="hlf-td-empty"></td>
                </template>
                <template v-else>
                  <td v-for="(v, j) in row.values" :key="j" class="hlf-td-num"
                      :data-label="sec.years[j]"
                      :class="{ current: j === sec.years.length - 1, negative: (cellValue(sec, rowIdx, j) ?? 0) < 0, empty: cellValue(sec, rowIdx, j) == null, auto: effectiveAuto(row) }">
                    <input v-if="editMode && !effectiveAuto(row)" type="text" class="hlf-cell-inp"
                           :value="cellInputValue(sec, rowIdx, j, v)"
                           @focus="onCellFocus(sec, rowIdx, j)"
                           @blur="onCellBlur"
                           @input="onCellInput(row, j, ($event.target as HTMLInputElement).value)"
                           placeholder="—" />
                    <template v-else>{{ fmtNum(cellValue(sec, rowIdx, j)) }}</template>
                  </td>
                </template>
                <td v-if="editMode" class="hlf-td-actions">
                  <button class="hlf-rowmenu-trigger"
                          :class="{ open: rowMenu && rowMenu.sec === sec && rowMenu.rowIdx === rowIdx }"
                          @click="openRowMenu($event, sec, rowIdx)"
                          title="Действия со строкой" aria-haspopup="menu">
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                      <circle cx="3" cy="8" r="1.4"/><circle cx="8" cy="8" r="1.4"/><circle cx="13" cy="8" r="1.4"/>
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="editMode" class="hlf-add-row">
                <td :colspan="sec.years.length + 2">
                  <button class="hlf-add-btn" @click="addRow(sec, 'line')">+ строка</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'subheader')">+ подсекция</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'subtotal')">+ подытог</button>
                  <button class="hlf-add-btn" @click="addRow(sec, 'total')">+ итого</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

  </div>

  <!-- Кастомный выпадающий список компаний (Teleport — карта overflow:hidden) -->
  <Teleport to="body">
    <div v-if="coOpen" ref="coPanel" class="hlf-co-panel"
         :style="{ top: coPos.top + 'px', left: coPos.left + 'px', width: coPos.width + 'px' }"
         @keydown="coKeydown">
      <div class="hlf-co-search">
        <svg viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><circle cx="6" cy="6" r="4"/><path d="M11 11L9 9"/></svg>
        <input ref="coSearchInp" v-model="coSearch" type="text" class="hlf-co-search-inp"
               placeholder="Поиск компании…" @keydown="coKeydown" />
      </div>
      <div class="hlf-co-list">
        <button v-for="(co, i) in coFiltered" :key="co.code" type="button"
                class="hlf-co-opt" :class="{ sel: co.code === selectedCode, hi: i === coHighlight }"
                @click="coPick(co.code)" @mousemove="coHighlight = i">
          <CompanyAvatar :name="co.name_short || co.name_ru" :code="co.code" :color="co.sector_color || undefined" :size="22" />
          <span class="hlf-co-opt-name">{{ co.name_short || co.name_ru }}</span>
          <span class="hlf-co-opt-code">{{ co.code }}</span>
          <svg v-if="co.code === selectedCode" class="hlf-co-check" viewBox="0 0 14 14" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 7.5L6 11l5.5-7"/></svg>
        </button>
        <div v-if="!coFiltered.length" class="hlf-co-empty">Ничего не найдено</div>
      </div>
    </div>
  </Teleport>

  <!-- Меню действий над строкой («⋯») — Teleport, чтобы overflow таблицы не резал -->
  <Teleport to="body">
    <div v-if="rowMenu" id="hlf-rowmenu" class="hlf-rowmenu" role="menu"
         :style="{ top: rowMenuPos.top + 'px', left: rowMenuPos.left + 'px' }">
      <button class="hlf-rowmenu-item" role="menuitem" @click="menuInsert">
        <span class="hlf-rowmenu-ico">＋</span><span>Вставить строку ниже</span>
      </button>
      <button v-if="['total','subtotal'].includes(rowMenu.row.type)"
              class="hlf-rowmenu-item" role="menuitem" @click="menuToggleAuto">
        <span class="hlf-rowmenu-ico">∑</span>
        <span>{{ effectiveAuto(rowMenu.row) ? 'Автосумма: включена' : 'Включить автосумму' }}</span>
        <span v-if="effectiveAuto(rowMenu.row)" class="hlf-rowmenu-on">вкл</span>
      </button>
      <div class="hlf-rowmenu-sep"></div>
      <button class="hlf-rowmenu-item" role="menuitem" :disabled="rowMenu.rowIdx === 0" @click="menuUp">
        <span class="hlf-rowmenu-ico">↑</span><span>Переместить вверх</span>
      </button>
      <button class="hlf-rowmenu-item" role="menuitem"
              :disabled="rowMenu.rowIdx === rowMenu.sec.rows.length - 1" @click="menuDown">
        <span class="hlf-rowmenu-ico">↓</span><span>Переместить вниз</span>
      </button>
      <div class="hlf-rowmenu-sep"></div>
      <button class="hlf-rowmenu-item danger" role="menuitem" @click="menuDelete">
        <span class="hlf-rowmenu-ico">✕</span><span>Удалить строку</span>
      </button>
    </div>
  </Teleport>

  <!-- Модалка ИИ-анализа высокоуровневых показателей -->
  <Teleport to="body">
    <div v-if="anOpen" class="hlf-an-back" @click.self="anOpen = false" role="dialog" aria-modal="true">
      <div class="hlf-an-card">
        <header class="hlf-an-hd">
          <div class="hlf-an-hd-txt">
            <div class="hlf-an-eyebrow">ИИ-АНАЛИЗ {{ anScope === 'company' ? 'КОМПАНИИ' : 'ПОРТФЕЛЯ' }}</div>
            <h2 class="hlf-an-title">Высокоуровневые показатели — {{ anScope === 'company' ? (selectedCompany?.name_short || selectedCompany?.name_ru || selectedCompany?.code || 'компания') : 'все компании' }}</h2>
            <div v-if="anYear && !anLoading && anHtml" class="hlf-an-sub">{{ anScope === 'company' ? '1 компания' : anCount + ' компаний' }} · {{ anYear }}<span v-if="anDoneAt"> · {{ anDoneAt }}</span></div>
          </div>
          <button class="hlf-an-x" @click="anOpen = false" aria-label="Закрыть">×</button>
        </header>

        <!-- Охват: весь портфель / только выбранная компания -->
        <div class="hlf-an-scen">
          <span class="hlf-an-scen-lbl">Охват</span>
          <div class="hlf-an-scen-seg">
            <button class="hlf-an-scen-opt" :class="{ on: anScope === 'portfolio' }"
                    :disabled="anLoading" @click="setAnScope('portfolio')">Весь портфель</button>
            <button class="hlf-an-scen-opt" :class="{ on: anScope === 'company' }"
                    :disabled="anLoading || !selectedCompany" @click="setAnScope('company')">
              Только «{{ selectedCompany?.name_short || selectedCompany?.code || 'компания' }}»
            </button>
          </div>
        </div>

        <!-- Сценарий анализа: senior CFO / инвестор / акционер -->
        <div class="hlf-an-scen">
          <span class="hlf-an-scen-lbl">Сценарий</span>
          <div class="hlf-an-scen-seg">
            <button v-for="s in AN_SCENARIOS" :key="s.id" class="hlf-an-scen-opt"
                    :class="{ on: anScenario === s.id }" :disabled="anLoading"
                    @click="applyScenario(s.id)" :title="s.hint">{{ s.label }}</button>
          </div>
          <button class="hlf-an-run" :disabled="anLoading" @click="runAnalysis">
            {{ anLoading ? 'Анализирую…' : (anHtml ? 'Пересчитать' : 'Запустить анализ') }}
          </button>
        </div>

        <div class="hlf-an-body">
          <!-- Думающий процесс: скролл-лента шагов -->
          <div v-if="anLoading" class="hlf-an-think">
            <div class="hlf-an-think-feed">
              <div v-for="(st, i) in anSteps.slice(0, anStepShown)" :key="i"
                   class="hlf-an-think-line" :class="{ cur: i === anStepShown - 1 }">
                <span class="hlf-an-think-dot"></span><span>{{ st }}</span>
              </div>
            </div>
            <div class="hlf-an-hint">Аналитик ИИ читает отчётность всех компаний, сверяет с отраслевыми бенчмарками (web) и оценивает риски. До минуты.</div>
          </div>
          <div v-else-if="anError" class="hlf-an-error">{{ anError }}</div>
          <template v-else-if="anHtml">
            <div v-if="anChartsHtml" class="hlf-an-charts">
              <div class="hlf-an-charts-hd">Визуализация показателей</div>
              <div v-html="anChartsHtml"></div>
            </div>
            <div class="hlf-an-md" v-html="anHtml"></div>
          </template>
          <div v-else class="hlf-an-empty">
            <div class="hlf-an-empty-t">Выберите сценарий и запустите анализ</div>
            <div class="hlf-an-hint">ИИ разберёт каждый показатель по всем компаниям, построит графики и даст выводы под выбранную роль.</div>
          </div>
        </div>

        <footer v-if="!anLoading && anHtml" class="hlf-an-ft">
          <div class="hlf-an-ft-actions">
            <button class="hlf-an-tool" @click="copyAnalysis">{{ anCopyOk ? 'Скопировано' : 'Копировать' }}</button>
            <button class="hlf-an-tool" @click="exportWord">Word</button>
            <button class="hlf-an-tool" @click="exportPrint">PDF / печать</button>
          </div>
          <span class="hlf-an-disc">Сгенерировано ИИ-движком с web-поиском · сверяйте цифры</span>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Design code (the design guide §6):
 *   Cards 11-14px, buttons 8px, palette #7F77DD/var(--p-deep)/var(--green)/var(--amber)/var(--sev-high),
 *   borders var(--border-hard), surface light #FAFAFC, muted text var(--t-muted),
 *   headings 15px/500 letter-spacing -.01em, section labels 10px/500/uppercase/.08em,
 *   font-weight max 500, easing var(--ease-standard) */
.hlf-card {
  background: var(--bg1, #fff);
  border-radius: 14px;
  border: 1px solid var(--border-hard);
  overflow: hidden;
  margin-top: 16px;
  box-shadow: 0 1px 2px rgba(15, 23, 60, 0.04), 0 8px 28px rgba(15, 23, 60, 0.05);
  transition: box-shadow 0.2s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1));
}
.hlf-card:hover { box-shadow: 0 2px 6px rgba(15, 23, 60, 0.06), 0 14px 40px rgba(15, 23, 60, 0.08); }

.hlf-hdr {
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-hard);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}
/* min-width не 0: иначе при нехватке ширины заголовок схлопывался в столбик
   по словам, а контролы наезжали. Теперь при нехватке места ВЕСЬ правый кластер
   контролов переносится во 2-й ряд (flex-wrap у .hlf-hdr), заголовок цел. */
.hlf-hdr-left { min-width: 220px; flex: 1 1 220px; }
.hlf-eyebrow {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.08em;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
}
.hlf-title {
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  margin-top: 4px;
  color: var(--t1, #1E2A4A);
}
.hlf-sub { font-size: 12px; color: var(--t3, var(--t-muted)); margin-top: 4px; }
.hlf-dirty { color: var(--amber); font-weight: 500; }

.hlf-hdr-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
/* ─── Кастомный комбобокс выбора компании ─── */
.hlf-co { display: inline-flex; }
.hlf-co-trigger {
  display: inline-flex; align-items: center; gap: 8px;
  min-width: 240px; max-width: 300px;
  padding: 5px 10px 5px 6px;
  border: 1px solid var(--border-hard);
  border-radius: 9px;
  background: var(--bg1, #fff);
  cursor: pointer; font-family: inherit;
  transition: border-color .14s ease, box-shadow .14s ease, background .14s ease;
}
.hlf-co-trigger:hover { border-color: #B9B3F0; background: rgba(127, 119, 221, 0.03); }
.hlf-co-trigger.open { border-color: #7F77DD; box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.14); }
.hlf-co-trig-name { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: 1; text-align: left; }
.hlf-co-trig-code {
  font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  color: var(--p-deep, #534AB7); background: rgba(127, 119, 221, 0.10);
  padding: 2px 6px; border-radius: 5px; font-feature-settings: 'tnum'; flex-shrink: 0;
}
.hlf-co-chev { color: var(--t3, var(--t-muted)); transition: transform .2s var(--ease-standard); flex-shrink: 0; }
.hlf-co-chev.up { transform: rotate(180deg); }

/* ─── Кнопка «Анализ ИИ» ─── */
.hlf-btn-analyze {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 6px 13px; font-size: 11px; font-weight: 500;
  border-radius: 8px; cursor: pointer; font-family: inherit;
  border: 1px solid transparent;
  color: #fff;
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7);
  box-shadow: 0 2px 8px rgba(108, 92, 231, 0.28);
  transition: filter .14s ease, box-shadow .14s ease, transform .14s ease;
}
.hlf-btn-analyze:hover { filter: brightness(1.05); box-shadow: 0 4px 14px rgba(108, 92, 231, 0.36); transform: translateY(-1px); }
.hlf-btn-analyze:disabled { opacity: .6; cursor: default; transform: none; box-shadow: none; }

.hlf-btn-mode, .hlf-btn-year, .hlf-btn-section, .hlf-btn-import, .hlf-btn-save, .hlf-btn-g {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-btn-mode { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-mode:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }
.hlf-btn-mode.on { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.hlf-btn-year, .hlf-btn-section { border-color: #7F77DD; background: rgba(127, 119, 221, 0.08); color: var(--p-deep); }
.hlf-btn-year:hover, .hlf-btn-section:hover { background: rgba(127, 119, 221, 0.16); }
.hlf-btn-import { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-import:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }
.hlf-btn-save { border-color: var(--green); background: var(--green); color: #fff; }
.hlf-btn-save:hover { background: #178D69; }
.hlf-btn-save:disabled { opacity: 0.6; cursor: not-allowed; }
.hlf-btn-g { border-color: var(--border-input); background: var(--bg1, #fff); color: var(--t3, var(--t3)); }
.hlf-btn-g:hover { background: #F1F5F9; }

.hlf-add-year {
  padding: 10px 20px;
  background: rgba(127, 119, 221, 0.06);
  border-bottom: 1px solid var(--border-hard);
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: var(--p-deep);
}
.hlf-year-inp {
  width: 80px;
  padding: 5px 9px;
  font-size: 12px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  font-family: inherit;
  outline: none;
  transition: border-color 0.12s ease;
}
.hlf-year-inp:focus { border-color: #7F77DD; }

.hlf-import-result {
  margin: 12px 20px 0; padding: 9px 14px;
  background: rgba(29, 158, 117, 0.08);
  border: 1px solid rgba(29, 158, 117, 0.25);
  color: #0F6E56; font-size: 11.5px;
  border-radius: 8px; position: relative;
}
.hlf-banner-x {
  position: absolute; top: 6px; right: 8px;
  width: 20px; height: 20px;
  border: none; background: transparent;
  color: #0F6E56; cursor: pointer;
  font-size: 16px; line-height: 1;
}

.hlf-kpis-wrap { border-bottom: 1px solid var(--border-hard); background: var(--bg2, #FAFAFC); }
.hlf-kpis-hdr {
  padding: 10px 20px 6px;
  display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
}
.hlf-kpis-lbl {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hlf-kpi-yr-pills { display: inline-flex; gap: 2px; padding: 2px; background: var(--bg2, #FAFAFC); border-radius: 8px; }
.hlf-yr-pill {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  font-family: inherit;
  transition: background 0.12s ease, color 0.12s ease;
}
.hlf-yr-pill:hover { background: rgba(127, 119, 221, 0.10); color: var(--p-deep); }
.hlf-yr-pill.on { background: var(--bg1, #fff); color: var(--t1, #1E2A4A); box-shadow: 0 1px 2px rgba(15, 23, 60, 0.08); }
.hlf-yr-pill.weak { color: #C9C8C0; }
.hlf-yr-pill.weak.on { color: var(--t3, var(--t-muted)); }
.hlf-coverage {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  padding: 3px 9px;
  background: rgba(127, 119, 221, 0.08);
  border-radius: 11px;
  margin-left: auto;
}
.hlf-kpis {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 1px; background: var(--border-hard); padding: 0 0 1px;
}
.hlf-kpi {
  background: var(--bg1, #fff);
  padding: 12px 13px 11px;
  position: relative;
  overflow: hidden;
  transition: background 0.16s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1)),
              transform 0.16s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1));
}
/* Accent bar — health colour of the metric. Всегда видна (тихо), на hover ярче:
   полоса здоровья превращает банд в «приборную панель». */
.hlf-kpi::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: var(--kpi-accent, #7F77DD);
  opacity: 0.4;
  transition: opacity 0.16s ease;
}
.hlf-kpi:hover {
  background: linear-gradient(180deg, rgba(127, 119, 221, 0.045), rgba(127, 119, 221, 0.015));
  transform: translateY(-1px);
}
.hlf-kpi:hover::before { opacity: 1; }
.hlf-kpi-lbl {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.hlf-kpi-val {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.025em;
  margin-top: 5px;
  line-height: 1;
  font-feature-settings: 'tnum';
}
.hlf-kpi-foot {
  display: flex; align-items: center; gap: 7px;
  margin-top: 7px;
}
.hlf-kpi-delta {
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 10px; font-weight: 500;
  padding: 1.5px 6px 1.5px 4px;
  border-radius: 11px;
  font-feature-settings: 'tnum';
  line-height: 1.3;
}
.hlf-kpi-delta.good { color: #0F6E56; background: rgba(29, 158, 117, 0.10); }
.hlf-kpi-delta.bad  { color: #A32D2D; background: rgba(226, 75, 74, 0.10); }
.hlf-kpi-prev-y { font-size: 10px; color: var(--t4, #C9C8C0); letter-spacing: 0.02em; }

.hlf-state { padding: 40px 24px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 12px; }
.hlf-state-error { color: var(--sev-high); }
.hlf-state-empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 50px 24px; }
.hlf-empty-icon { color: #C9C8C0; }
.hlf-empty-title { color: var(--t1, #1E2A4A); font-size: 15px; font-weight: 500; letter-spacing: -0.01em; margin-top: 8px; }
.hlf-empty-text { color: var(--t3, var(--t-muted)); font-size: 12px; max-width: 480px; line-height: 1.55; }

.hlf-section { border-top: 1px solid var(--border-hard); }
.hlf-section:first-of-type { border-top: none; }

.hlf-sec-hdr {
  padding: 12px 20px;
  background: var(--bg2, #FAFAFC);
  display: flex; align-items: center; gap: 10px;
  border-bottom: 1px solid var(--border-hard);
}
.hlf-sec-toggle {
  display: flex; align-items: center; gap: 10px;
  padding: 0; margin: 0; border: none; background: none;
  font: inherit; text-align: left; cursor: pointer;
}
.hlf-chevron-btn {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 0; margin: 0; border: none; background: none; cursor: pointer;
}
.hlf-chevron {
  color: var(--t3, var(--t-muted));
  transition: transform 0.22s var(--ease-standard), color 0.12s ease;
  transform: rotate(90deg);
  cursor: pointer;
}
.hlf-chevron.collapsed { transform: rotate(0deg); }
.hlf-sec-title { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); letter-spacing: -0.01em; cursor: pointer; }
.hlf-sec-toggle:hover .hlf-sec-title,
.hlf-sec-title:hover { color: var(--p-deep); }
.hlf-sec-toggle:hover .hlf-chevron { color: var(--p-deep); }
.hlf-sec-title-inp {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  padding: 5px 9px;
  border: 1px solid var(--border-hard);
  border-radius: 8px;
  background: var(--bg1, #fff);
  outline: none;
  font-family: inherit;
  flex: 1;
  max-width: 400px;
  transition: border-color 0.12s ease;
}
.hlf-sec-title-inp:focus { border-color: #7F77DD; }
.hlf-sec-meta { font-size: 11px; color: var(--t3, var(--t-muted)); margin-left: auto; }
.hlf-sec-remove {
  width: 22px; height: 22px;
  border: 1px solid var(--border-hard); background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted)); cursor: pointer; border-radius: 8px;
  font-size: 15px; line-height: 1;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-sec-remove:hover { background: rgba(226, 75, 74, 0.06); border-color: var(--sev-high); color: var(--sev-high); }

.hlf-table-wrap { overflow-x: auto; }
.hlf-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.hlf-table thead { background: var(--bg2, #FAFAFC); }
.hlf-table th {
  padding: 8px 12px;
  text-align: left;
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  border-bottom: 1px solid var(--border-hard);
  position: relative;
}
.hlf-th-name { padding-left: 20px; min-width: 280px; }
/* Специфичность: .hlf-table th (0,1,1) перебивала text-align:right у .hlf-th-num
   (0,1,0) → годы в шапке выравнивались влево, а данные вправо → «съезжали».
   Поднимаем специфичность до .hlf-table th.hlf-th-num (0,2,1). */
.hlf-table th.hlf-th-num { text-align: right; width: 110px; }
.hlf-th-num.current { color: var(--t1, #1E2A4A); padding-right: 20px; }
.hlf-th-actions { width: 46px; }
.hlf-th-x {
  position: absolute; top: 50%; right: 4px; transform: translateY(-50%);
  width: 16px; height: 16px; border: none; background: transparent;
  color: var(--t3, var(--t-muted)); cursor: pointer; font-size: 14px; line-height: 1; border-radius: 4px;
  opacity: 0; transition: opacity 0.12s ease, background 0.12s ease, color 0.12s ease;
}
.hlf-th-num:hover .hlf-th-x, .hlf-th-x:focus-visible { opacity: 1; }  /* показываем «×» года только при наведении — меньше промахов */
.hlf-th-x:hover { background: rgba(226, 75, 74, 0.10); color: var(--sev-high); }

.hlf-table td { padding: 6px 12px; border-bottom: 1px solid var(--border-hard); vertical-align: middle; }
.hlf-td-name { padding-left: 20px; color: var(--t1, #1E2A4A); font-size: 12px; max-width: 480px; white-space: normal; word-break: normal; overflow-wrap: break-word; hyphens: none; }
.hlf-td-num { text-align: right; font-feature-settings: 'tnum'; color: var(--t1, #1E2A4A); white-space: nowrap; font-size: 12px; }
.hlf-td-num.current { padding-right: 20px; font-weight: 500; }
.hlf-td-num.negative { color: var(--sev-high); }
.hlf-td-empty { background: transparent; }

/* Premium: row hover for data lines + subtle current-year column tint. */
.hlf-table tbody tr.hlf-row-line td,
.hlf-table tbody tr.hlf-row-subtotal td {
  transition: background 0.1s ease;
}
.hlf-table tbody tr.hlf-row-line:hover td { background: rgba(127, 119, 221, 0.05); }
.hlf-table tbody tr.hlf-row-subtotal:hover td { background: rgba(127, 119, 221, 0.07); }
.hlf-th-num.current { background: rgba(127, 119, 221, 0.05); }
.hlf-row-line .hlf-td-num.current,
.hlf-row-subtotal .hlf-td-num.current { background: rgba(127, 119, 221, 0.035); }
.hlf-table tbody tr.hlf-row-line:hover .hlf-td-num.current { background: rgba(127, 119, 221, 0.085); }

.hlf-cell-inp {
  width: 100%;
  padding: 4px 7px;
  text-align: right;
  border: 1px solid transparent;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  font-feature-settings: 'tnum';
  transition: border-color 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
}
.hlf-cell-inp:focus { background: var(--bg1, #fff); border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15); }
.hlf-label-inp {
  width: 100%;
  padding: 4px 7px;
  border: 1px solid transparent;
  background: rgba(127, 119, 221, 0.04);
  border-radius: 6px;
  font-family: inherit;
  font-size: 12px;
  color: var(--t1, #1E2A4A);
  outline: none;
  transition: border-color 0.12s ease, background 0.12s ease, box-shadow 0.12s ease;
}
.hlf-label-inp:focus { background: var(--bg1, #fff); border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15); }

.hlf-row-section_header td { background: rgba(127, 119, 221, 0.08); padding-top: 9px; padding-bottom: 9px; }
.hlf-row-section_header .hlf-td-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--p-deep);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.hlf-row-subheader td { background: rgba(127, 119, 221, 0.03); padding-top: 7px; padding-bottom: 7px; }
.hlf-row-subheader .hlf-td-name {
  font-size: 11px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding-left: 20px;
}
.hlf-row-line .hlf-td-name { padding-left: 36px; color: var(--t1, #1E2A4A); }

/* Сворачиваемый «Cost of sales» */
.hlf-cost-toggle {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; margin-right: 5px; padding: 0;
  border: none; background: rgba(127, 119, 221, .10); border-radius: 4px;
  color: var(--p-deep, #534AB7); cursor: pointer; vertical-align: middle;
  transition: background .14s, transform .18s var(--ease-out, cubic-bezier(.16,1,.3,1));
}
.hlf-cost-toggle:hover { background: rgba(127, 119, 221, .2); }
.hlf-cost-toggle svg { transform: rotate(90deg); transition: transform .2s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.hlf-cost-toggle.collapsed svg { transform: rotate(0deg); }
.hlf-cost-badge {
  margin-left: 6px; font-size: 9.5px; font-weight: 600; color: var(--p-deep, #534AB7);
  background: rgba(127, 119, 221, .12); border-radius: 8px; padding: 1px 6px;
  font-feature-settings: "tnum"; vertical-align: middle;
}
/* Подстатьи — глубже отступ + приглушённый текст */
.hlf-table tbody tr.hlf-cost-child .hlf-td-name { padding-left: 54px; }
.hlf-cost-child-lbl { color: var(--t2, #5B6478); font-size: 11.5px; }
.hlf-table tbody tr.hlf-cost-child .hlf-td-num { color: var(--t2, #5B6478); }
.hlf-row-subtotal td { background: rgba(127, 119, 221, 0.04); padding-top: 6px; padding-bottom: 6px; }
.hlf-row-subtotal .hlf-td-name { padding-left: 20px; font-weight: 500; color: var(--t1, #1E2A4A); }
.hlf-row-subtotal .hlf-td-num { font-weight: 500; }
.hlf-row-total td {
  background: rgba(29, 158, 117, 0.07);
  border-top: 1px solid rgba(29, 158, 117, 0.30);
  padding-top: 8px;
  padding-bottom: 8px;
  color: var(--green);
}
.hlf-row-total .hlf-td-name {
  padding-left: 20px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11px;
}
.hlf-row-total .hlf-td-num { color: var(--green); font-weight: 500; }

.hlf-td-actions { text-align: center; white-space: nowrap; }
.hlf-act-btn {
  width: 22px;
  height: 22px;
  border: 1px solid var(--border-hard);
  background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1;
  margin: 0 1px;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-act-btn:hover { background: rgba(127, 119, 221, 0.08); color: var(--p-deep); border-color: #7F77DD; }
.hlf-act-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.hlf-act-btn.act-x:hover { background: rgba(226, 75, 74, 0.06); color: var(--sev-high); border-color: var(--sev-high); }
.hlf-act-btn.act-add { font-weight: 700; color: var(--p-deep, #534AB7); }
.hlf-act-btn.act-add:hover { background: rgba(29, 158, 117, 0.08); color: var(--green, #1D9E75); border-color: var(--green, #1D9E75); }
.hlf-act-btn.act-sum.on { background: rgba(127, 119, 221, 0.14); color: var(--p-deep, #534AB7); border-color: #7F77DD; }

/* Триггер «⋯» действий над строкой */
.hlf-rowmenu-trigger {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 26px; padding: 0;
  border: 1px solid transparent; border-radius: 7px;
  background: transparent; color: var(--t3, var(--t-muted));
  cursor: pointer; transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-rowmenu-trigger:hover { background: rgba(127, 119, 221, 0.10); color: var(--p-deep, #534AB7); }
.hlf-rowmenu-trigger.open { background: rgba(127, 119, 221, 0.14); color: var(--p-deep, #534AB7); border-color: #7F77DD; }

/* Панель меню (Teleport → body) */
.hlf-rowmenu {
  position: fixed; z-index: 9600;
  min-width: 236px; padding: 5px;
  background: var(--bg1, #fff);
  border: 1px solid var(--border-hard);
  border-radius: 11px;
  box-shadow: 0 18px 50px -12px rgba(20, 16, 55, 0.30), 0 2px 8px rgba(15, 23, 60, 0.08);
  font-family: Geist, system-ui, sans-serif;
  animation: hlfCoIn 0.14s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1)) both;
}
.hlf-rowmenu-item {
  display: flex; align-items: center; gap: 10px; width: 100%;
  padding: 8px 10px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; font-family: inherit; text-align: left;
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  transition: background 0.1s ease;
}
.hlf-rowmenu-item:hover:not(:disabled) { background: rgba(127, 119, 221, 0.08); }
.hlf-rowmenu-item:disabled { opacity: 0.4; cursor: not-allowed; }
.hlf-rowmenu-item.danger { color: var(--sev-high, #E24B4A); }
.hlf-rowmenu-item.danger:hover:not(:disabled) { background: rgba(226, 75, 74, 0.08); }
.hlf-rowmenu-ico {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; flex-shrink: 0; font-size: 14px; line-height: 1;
  color: var(--t3, var(--t-muted));
}
.hlf-rowmenu-item.danger .hlf-rowmenu-ico { color: var(--sev-high, #E24B4A); }
.hlf-rowmenu-on {
  margin-left: auto; font-size: 9.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
  color: var(--p-deep, #534AB7); background: rgba(127, 119, 221, 0.14);
  padding: 2px 6px; border-radius: 6px;
}
.hlf-rowmenu-sep { height: 1px; margin: 4px 6px; background: var(--border-hard); }

.hlf-add-row td { padding: 8px 20px; background: rgba(127, 119, 221, 0.03); border-bottom: 1px dashed rgba(127, 119, 221, 0.20); }
.hlf-add-btn {
  margin-right: 6px;
  padding: 4px 11px;
  font-size: 11px;
  font-weight: 500;
  border: 1px dashed var(--border-hard);
  background: var(--bg1, #fff);
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  border-radius: 8px;
  font-family: inherit;
  transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
}
.hlf-add-btn:hover { background: rgba(127, 119, 221, 0.06); color: var(--p-deep); border-color: #7F77DD; }

/* ═══════════ MOBILE / TABLET (Phase 2) ═══════════ */
@media (max-width: 768px) {
  /* Шапка: заголовок сверху, контролы — отдельной строкой на всю ширину */
  .hlf-hdr { padding: 12px 14px; flex-direction: column; align-items: stretch; gap: 10px; }
  .hlf-hdr-right { width: 100%; }
  .hlf-co, .hlf-co-trigger { flex: 1 1 100%; min-width: 0; max-width: none; }

  /* KPI-band плотнее */
  .hlf-kpis-hdr { padding: 8px 14px 5px; }
  .hlf-kpi { padding: 10px 11px; }

  /* Таблица: первая колонка (показатель) фиксируется при горизонтальном
     скролле по годам — её всегда видно. Фон делаем непрозрачным под каждый
     тип строки, иначе цифры просвечивают. */
  .hlf-table { font-size: 12px; }
  .hlf-th, .hlf-table td { padding-left: 12px; padding-right: 10px; }
  .hlf-th-name { min-width: 150px; padding-left: 14px; }
  .hlf-td-name { padding-left: 14px; max-width: 200px; white-space: normal; }

  .hlf-th-name, .hlf-td-name {
    position: sticky;
    left: 0;
    z-index: 2;
  }
  .hlf-th-name { z-index: 3; background: #FAFAFC; }
  .hlf-row-line .hlf-td-name,
  .hlf-td-name { background: var(--bg1, #fff); }
  .hlf-row-subheader .hlf-td-name { background: #F9F8FE; }
  .hlf-row-subtotal .hlf-td-name  { background: #F7F6FD; }
  .hlf-row-section_header .hlf-td-name { background: #F1EFFB; }
  .hlf-row-total .hlf-td-name { background: #EFF8F4; }
  /* лёгкая тень-разделитель у залипшей колонки */
  .hlf-td-name, .hlf-th-name { box-shadow: 1px 0 0 var(--border-hard); }

  .hlf-section .hlf-sec-hdr { padding: 10px 14px; }
}

/* ── Card-режим таблицы (≤640): строка-показатель → карточка «год: значение»,
   БЕЗ горизонтального скролла. Перебивает sticky-табличный режим ≤768. ── */
@media (max-width: 640px) {
  .hlf-table-wrap { overflow: visible; max-height: none; }
  .hlf-table, .hlf-table tbody, .hlf-table tbody tr { display: block; width: 100%; }
  .hlf-table thead { display: none; }

  /* сброс sticky/таблично-специфичного из ≤768 */
  .hlf-th-name, .hlf-td-name {
    position: static; box-shadow: none; background: transparent !important;
    max-width: none; min-width: 0;
  }
  /* строки-данные → карточки */
  .hlf-table tbody tr.hlf-row-line,
  .hlf-table tbody tr.hlf-row-subtotal,
  .hlf-table tbody tr.hlf-row-total {
    padding: 8px 14px;
    border-bottom: 1px solid var(--border-hard);
  }
  .hlf-td-name {
    display: block; padding: 0 0 4px 0 !important;
    font-size: 12.5px; color: var(--t1, #1E2A4A);
  }
  .hlf-row-subtotal .hlf-td-name, .hlf-row-total .hlf-td-name { font-weight: 500; }
  /* год: значение — инлайн-чипы, переносятся */
  .hlf-td-num {
    display: inline-flex; align-items: baseline; gap: 4px;
    width: auto; text-align: left;
    padding: 1px 0 !important; margin: 0 14px 2px 0;
    font-size: 12.5px; white-space: nowrap;
  }
  .hlf-td-num::before {
    content: attr(data-label);
    color: var(--t3, var(--t-muted)); font-size: 10px; font-weight: 600; letter-spacing: .02em;
  }
  .hlf-td-num.current { background: transparent; font-weight: 500; }
  .hlf-td-num.empty { display: none; }   /* «—» не засоряют карточку */
  .hlf-td-empty { display: none; }
  /* секционные заголовки/подсекции → разделители на всю ширину */
  .hlf-table tbody tr.hlf-row-section_header,
  .hlf-table tbody tr.hlf-row-subheader { padding: 8px 14px; }
  .hlf-row-section_header .hlf-td-name,
  .hlf-row-subheader .hlf-td-name { padding: 0 !important; }
  .hlf-row-total { background: rgba(29, 158, 117, .06); }
}

@media (max-width: 480px) {
  .hlf-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* ═══════════ Комбобокс-панель (Teleport to body) ═══════════ */
.hlf-co-panel {
  position: fixed; z-index: 9600;
  background: var(--bg1, #fff);
  border: 1px solid var(--border-hard);
  border-radius: 12px;
  box-shadow: 0 18px 50px -12px rgba(20, 16, 55, 0.30), 0 2px 8px rgba(15, 23, 60, 0.08);
  overflow: hidden;
  display: flex; flex-direction: column;
  max-height: 384px;
  font-family: Geist, system-ui, sans-serif;
  animation: hlfCoIn 0.16s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1)) both;
}
@keyframes hlfCoIn { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: translateY(0); } }
.hlf-co-search { display: flex; align-items: center; gap: 7px; padding: 9px 12px; border-bottom: 1px solid var(--border-hard); color: var(--t3, var(--t-muted)); }
.hlf-co-search-inp { border: none; outline: none; background: transparent; font-family: inherit; font-size: 12.5px; color: var(--t1, #1E2A4A); width: 100%; }
.hlf-co-list { overflow-y: auto; padding: 5px; scrollbar-width: thin; }
.hlf-co-opt {
  display: flex; align-items: center; gap: 9px; width: 100%;
  padding: 7px 9px; border: none; background: transparent;
  border-radius: 8px; cursor: pointer; font-family: inherit; text-align: left;
  transition: background 0.1s ease;
}
.hlf-co-opt.hi { background: rgba(127, 119, 221, 0.08); }
.hlf-co-opt.sel { background: rgba(127, 119, 221, 0.12); }
.hlf-co-opt-name { font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hlf-co-opt.sel .hlf-co-opt-name { color: var(--p-deep, #534AB7); }
.hlf-co-opt-code { font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-feature-settings: 'tnum'; flex-shrink: 0; }
.hlf-co-check { color: var(--p-deep, #534AB7); flex-shrink: 0; }
.hlf-co-empty { padding: 18px; text-align: center; font-size: 12px; color: var(--t3, var(--t-muted)); font-style: italic; }

/* ═══════════ ИИ-анализ: модалка (Teleport to body) ═══════════ */
.hlf-an-back {
  position: fixed; inset: 0; z-index: 9550;
  background: rgba(20, 16, 40, 0.5); -webkit-backdrop-filter: blur(5px); backdrop-filter: blur(5px);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.hlf-an-card {
  width: min(860px, 96vw); max-height: 90dvh; display: flex; flex-direction: column;
  background: var(--bg1, #fff); border-radius: 16px;
  box-shadow: 0 30px 80px -18px rgba(20, 16, 55, 0.55);
  font-family: Geist, system-ui, sans-serif; overflow: hidden;
  animation: hlfCoIn 0.2s var(--ease-standard, cubic-bezier(.34, 1.2, .64, 1)) both;
}
.hlf-an-hd { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; padding: 18px 22px 14px; border-bottom: 1px solid var(--border-hard); }
.hlf-an-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.hlf-an-title { font-size: 17px; font-weight: 600; margin: 3px 0 0; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.hlf-an-sub { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-top: 4px; }
.hlf-an-x { background: transparent; border: none; font-size: 22px; line-height: 1; color: var(--t3, var(--t-muted)); cursor: pointer; padding: 0 6px; flex-shrink: 0; }
.hlf-an-body { overflow-y: auto; padding: 18px 24px; scrollbar-width: thin; }
.hlf-an-loading { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 48px 24px; text-align: center; }
.hlf-an-spinner { width: 30px; height: 30px; border: 3px solid rgba(127, 119, 221, 0.18); border-top-color: #6C5CE7; border-radius: 50%; animation: hlfSpin 0.8s linear infinite; }
@keyframes hlfSpin { to { transform: rotate(360deg); } }
.hlf-an-prog { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); }
.hlf-an-hint { font-size: 11.5px; color: var(--t3, var(--t-muted)); max-width: 440px; line-height: 1.5; }
.hlf-an-error { padding: 28px 16px; text-align: center; color: var(--sev-high); font-size: 13px; }
.hlf-an-md { font-size: 13px; line-height: 1.6; color: var(--t1, #1E2A4A); }
.hlf-an-md :deep(h3) { font-size: 14.5px; font-weight: 600; margin: 18px 0 8px; color: var(--p-deep, #534AB7); letter-spacing: -.01em; }
.hlf-an-md :deep(h3:first-child) { margin-top: 0; }
.hlf-an-md :deep(h4) { font-size: 12.5px; font-weight: 600; margin: 14px 0 6px; color: var(--t1, #1E2A4A); text-transform: uppercase; letter-spacing: .04em; }
.hlf-an-md :deep(p) { margin: 0 0 10px; }
.hlf-an-md :deep(ul) { margin: 0 0 10px; padding-left: 20px; }
.hlf-an-md :deep(li) { margin: 3px 0; }
.hlf-an-md :deep(strong) { font-weight: 600; color: var(--t1, #1E2A4A); }
.hlf-an-md :deep(hr) { border: none; border-top: 1px solid var(--border-hard); margin: 16px 0; }
.hlf-an-md :deep(table.hlf-an-tbl) { width: 100%; border-collapse: collapse; margin: 8px 0 14px; font-size: 12px; }
.hlf-an-md :deep(.hlf-an-tbl th) { text-align: left; padding: 6px 10px; background: var(--bg2, #FAFAFC); color: var(--t3, var(--t-muted)); font-weight: 600; font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; border-bottom: 1px solid var(--border-hard); }
.hlf-an-md :deep(.hlf-an-tbl td) { padding: 6px 10px; border-bottom: 1px solid var(--border-hard); font-feature-settings: 'tnum'; }
.hlf-an-ft { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 22px; border-top: 1px solid var(--border-hard); background: var(--bg2, #FAFAFC); }
.hlf-an-disc { font-size: 10.5px; color: var(--t3, var(--t-muted)); }
.hlf-an-redo { padding: 6px 14px; font-size: 11px; font-weight: 500; border-radius: 8px; border: 1px solid var(--border-hard); background: var(--bg1, #fff); color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; transition: background .12s ease; }
.hlf-an-redo:hover { background: rgba(127, 119, 221, 0.08); }

/* Сценарий: лейбл + сегмент-контрол + кнопка запуска */
.hlf-an-scen { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 22px; border-bottom: 1px solid var(--border-hard); }
.hlf-an-scen-lbl { font-size: 10px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, var(--t-muted)); }
.hlf-an-scen-seg { display: inline-flex; gap: 2px; padding: 2px; background: var(--bg2, #FAFAFC); border: 1px solid var(--border-hard); border-radius: 9px; }
.hlf-an-scen-opt { padding: 5px 12px; font-size: 11.5px; font-weight: 500; border: none; background: transparent; color: var(--t2, #4B5468); border-radius: 7px; cursor: pointer; font-family: inherit; transition: background .12s ease, color .12s ease; }
.hlf-an-scen-opt:hover:not(.on) { background: rgba(127, 119, 221, 0.08); color: var(--p-deep); }
.hlf-an-scen-opt.on { background: var(--bg1, #fff); color: var(--p-deep, #534AB7); box-shadow: 0 1px 2px rgba(15, 23, 60, 0.10); }
.hlf-an-scen-opt:disabled { opacity: .6; cursor: default; }
.hlf-an-run { margin-left: auto; padding: 6px 16px; font-size: 12px; font-weight: 500; border: none; border-radius: 9px; color: #fff; background: linear-gradient(135deg, #8B7FF0, #6C5CE7); box-shadow: 0 2px 8px rgba(108, 92, 231, 0.28); cursor: pointer; font-family: inherit; transition: filter .12s ease; }
.hlf-an-run:hover:not(:disabled) { filter: brightness(1.06); }
.hlf-an-run:disabled { opacity: .6; cursor: default; box-shadow: none; }

/* Думающий процесс — скролл-лента шагов */
.hlf-an-think { padding: 18px 4px; display: flex; flex-direction: column; align-items: center; gap: 14px; }
.hlf-an-think-feed { width: 100%; max-width: 520px; display: flex; flex-direction: column; gap: 6px; min-height: 120px; }
.hlf-an-think-line { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--t3, var(--t-muted)); opacity: .55; animation: hlfThinkIn .32s var(--ease-standard, ease) both; }
.hlf-an-think-line.cur { color: var(--t1, #1E2A4A); font-weight: 500; opacity: 1; }
.hlf-an-think-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--border-hard); flex-shrink: 0; }
.hlf-an-think-line.cur .hlf-an-think-dot { background: #6C5CE7; box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.18); animation: hlfPulse 1.2s ease-in-out infinite; }
@keyframes hlfThinkIn { from { opacity: 0; transform: translateY(6px); } to { opacity: var(--o, .55); transform: translateY(0); } }
@keyframes hlfPulse { 0%, 100% { box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.18); } 50% { box-shadow: 0 0 0 5px rgba(108, 92, 231, 0.06); } }

/* Графики */
.hlf-an-charts { margin-bottom: 18px; padding-bottom: 14px; border-bottom: 1px solid var(--border-hard); }
.hlf-an-charts-hd { font-size: 14.5px; font-weight: 600; color: var(--p-deep, #534AB7); letter-spacing: -.01em; margin: 0 0 12px; }

/* Пусто */
.hlf-an-empty { padding: 40px 24px; text-align: center; display: flex; flex-direction: column; gap: 8px; align-items: center; }
.hlf-an-empty-t { font-size: 14px; font-weight: 500; color: var(--t1, #1E2A4A); }

/* Тулбар экспорта */
.hlf-an-ft-actions { display: inline-flex; gap: 8px; }
.hlf-an-tool { padding: 6px 13px; font-size: 11.5px; font-weight: 500; border-radius: 8px; border: 1px solid var(--border-hard); background: var(--bg1, #fff); color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; transition: background .12s ease, border-color .12s ease; }
.hlf-an-tool:hover { background: rgba(127, 119, 221, 0.08); border-color: #7F77DD; }

@media (max-width: 620px) {
  .hlf-an-scen { gap: 8px; }
  .hlf-an-run { margin-left: 0; width: 100%; }
  .hlf-an-ft { flex-direction: column-reverse; align-items: stretch; gap: 8px; }
  .hlf-an-ft-actions { justify-content: center; }
}
</style>
