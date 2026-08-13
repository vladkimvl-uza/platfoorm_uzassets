<script setup lang="ts">
/**
 * EsgStageDocsPanel — документы по ЭТАПАМ ESG-зрелости, организованные ПО ПЕРИОДАМ.
 *
 * Три группы (Климат D4 · Риски D5 · ISO D1). Режим загрузки — на этап:
 *   • year     — по годам (лента лет + панель периода);
 *   • quarter  — по годам И кварталам (год → Q1–Q4);
 *   • timeline — премиум-таймлайн по годам (ISO): годы-узлы, отмечены те, где
 *                уже есть файлы; документы за любой прошлый год можно добавить
 *                в любой момент — узел «загорается» на таймлайне.
 *
 * Файлы идут в общую библиотеку компании (documentsApi.upload), тег
 * entity_type='esg_stage', entity_id="<dim>:<idx>[:<year>[:Q<q>]]". Период
 * закодирован в ключе — БЭКЕНД НЕ МЕНЯЕТСЯ: stage_doc_counts группируется по
 * полному ключу (даёт счётчики по периодам), списки читаются точным совпадением.
 */
import { ref, reactive, computed, watch } from "vue";
import { documentsApi, type DocItem } from "@/api/documents";
import { useI18n } from "@/composables/useI18n";
import { useToast } from "@/composables/useToast";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();
const toast = useToast();

const props = defineProps<{
  companyCode: string;
  /** {"D4:2:2025":3, ...} — период-кодированные счётчики из ESGMaturityCompany.stage_doc_counts. */
  stageDocCounts?: Record<string, number>;
  canEdit?: boolean;
}>();
const emit = defineEmits<{ (e: "changed"): void }>();

type Mode = "year" | "quarter" | "timeline";
interface Stage { key: string; num: number | string; label: string; mode: Mode }
interface Group { title: string; accent: string; stages: Stage[] }

// Ключи-этапы 1:1 с бэкендом (dim:index). Режим = как организуется загрузка.
const GROUPS: Group[] = [
  {
    title: i18nKey("Климатические стратегии"), accent: "#0A7B5E",
    stages: [
      { key: "D4:1", num: 1, label: i18nKey("Количественная оценка выбросов ПГ (Охваты 1, 2)"), mode: "year" },
      { key: "D4:2", num: 2, label: i18nKey("Оценка климат-рисков"), mode: "year" },
      { key: "D4:3", num: 3, label: i18nKey("Разработка плана декарбонизации"), mode: "year" },
      { key: "D4:4", num: 4, label: i18nKey("Реализация плана декарбонизации"), mode: "quarter" },
    ],
  },
  {
    title: i18nKey("Управление ESG-рисками"), accent: "#7F77DD",
    stages: [
      { key: "D5:1", num: 1, label: i18nKey("Double-materiality assessment"), mode: "year" },
      { key: "D5:2", num: 2, label: i18nKey("Количественная оценка рисков устойчивого развития"), mode: "year" },
      { key: "D5:3", num: 3, label: i18nKey("Интеграция контроля за рисками в ERM (СУР)"), mode: "quarter" },
    ],
  },
  {
    title: i18nKey("Внедрение ISO"), accent: "#EF9F27",
    stages: [
      { key: "D1:iso14001", num: "14001", label: i18nKey("ISO 14001 · Экологический менеджмент"), mode: "timeline" },
      { key: "D1:iso45001", num: "45001", label: i18nKey("ISO 45001 · Охрана труда и здоровья"), mode: "timeline" },
      { key: "D1:iso50001", num: "50001", label: i18nKey("ISO 50001 · Энергоменеджмент"), mode: "timeline" },
    ],
  },
];

const START_YEAR = 2021;
const NOW = new Date();
const CUR_YEAR = NOW.getFullYear();
const CUR_Q = Math.floor(NOW.getMonth() / 3) + 1;

// Период-кодированные счётчики (ключ = полный entity_id) — из heatmap + оптимистично.
const counts = reactive<Record<string, number>>({ ...(props.stageDocCounts || {}) });

const expanded = ref<Set<string>>(new Set());
// Выбранный период на этап: base → {year|null, quarter|null}.
const sel = reactive<Record<string, { year: number | null; quarter: number | null }>>({});
const filesByPeriod = reactive<Record<string, DocItem[]>>({});
const loadingPeriod = ref<string | null>(null);
const uploadingPeriod = ref<string | null>(null);
const uploadPct = ref(0);
const dragPeriod = ref<string | null>(null);
const delId = ref<string | null>(null);
// Года, добавленные вручную кнопкой «+ год» (будущие / до 2021). Не персистятся —
// как только за такой год загружен файл, он и так виден из counts.
const manualYears = reactive<Record<string, number[]>>({});
const yearAdd = ref<string | null>(null);   // base в режиме ввода нового года
const yearAddVal = ref<string>("");

// Ресинк с сервером: локально загруженные периоды (filesByPeriod) — источник
// истины по количеству (учитывает оптимистичные +/−), исчезнувшие ключи удаляем
// (иначе бейдж «зависает» после удаления файла из другой вкладки).
watch(() => props.stageDocCounts, (v) => {
  const next: Record<string, number> = { ...(v || {}) };
  for (const pk of Object.keys(filesByPeriod)) next[pk] = filesByPeriod[pk].length;
  for (const k of Object.keys(counts)) if (!(k in next)) delete counts[k];
  for (const k in next) counts[k] = next[k];
});

function stageOf(base: string): Stage | undefined {
  for (const g of GROUPS) for (const s of g.stages) if (s.key === base) return s;
}
function labelFor(base: string): string {
  for (const g of GROUPS) for (const s of g.stages) if (s.key === base) return `${t(g.title)} · ${t(s.label)}`;
  return base;
}

// ── период ⇄ ключ ────────────────────────────────────────────────
function periodKey(base: string, year: number | null, quarter: number | null): string {
  let k = base;
  if (year != null) { k += ":" + year; if (quarter != null) k += ":Q" + quarter; }
  return k;
}
function parsePeriod(key: string, base: string): { year: number | null; quarter: number | null } {
  if (key === base || !key.startsWith(base + ":")) return { year: null, quarter: null };
  const parts = key.slice(base.length + 1).split(":");
  const year = /^\d{4}$/.test(parts[0] || "") ? parseInt(parts[0]) : null;
  const quarter = /^Q[1-4]$/.test(parts[1] || "") ? parseInt(parts[1].slice(1)) : null;
  return { year, quarter };
}
function keysForBase(base: string): string[] {
  return Object.keys(counts).filter((k) => (k === base || k.startsWith(base + ":")) && (counts[k] || 0) > 0);
}

// ── счётчики ─────────────────────────────────────────────────────
function stageTotal(base: string): number {
  return keysForBase(base).reduce((s, k) => s + (counts[k] || 0), 0);
}
function yearTotal(base: string, year: number): number {
  if (stageOf(base)?.mode === "quarter") {
    let n = counts[periodKey(base, year, null)] || 0;
    for (let q = 1; q <= 4; q++) n += counts[periodKey(base, year, q)] || 0;
    return n;
  }
  return counts[periodKey(base, year, null)] || 0;
}
function quarterCount(base: string, year: number, q: number): number { return counts[periodKey(base, year, q)] || 0; }
function legacyCount(base: string): number { return counts[base] || 0; }

// Годы этапа: 2021..текущий + встречающиеся в данных + добавленные вручную, по убыванию.
function yearsFor(base: string): number[] {
  const present = keysForBase(base).map((k) => parsePeriod(k, base).year).filter((y): y is number => y != null);
  const all = [...present, ...(manualYears[base] || [])];
  const maxY = Math.max(CUR_YEAR, START_YEAR, ...all);
  const minY = Math.min(START_YEAR, ...(all.length ? all : [START_YEAR]));
  const out: number[] = [];
  for (let y = maxY; y >= minY; y--) out.push(y);
  return out;
}

// «+ год» — открыть год за пределами авто-диапазона (будущий / до 2021).
function startAddYear(base: string) {
  ensureSel(base);
  const ys = yearsFor(base);
  yearAddVal.value = String((ys.length ? Math.max(...ys) : CUR_YEAR) + 1);
  yearAdd.value = base;
}
function cancelAddYear() { yearAdd.value = null; yearAddVal.value = ""; }
async function confirmAddYear(base: string) {
  const y = parseInt(yearAddVal.value, 10);
  yearAdd.value = null; yearAddVal.value = "";
  if (!Number.isFinite(y) || y < 1990 || y > 2100) return;
  const list = (manualYears[base] ||= []);
  if (!list.includes(y)) list.push(y);
  await pickYear(base, y);   // выбрать добавленный год и подгрузить
}
function focusInput(el: unknown) { const i = el as HTMLInputElement | null; if (i) { i.focus(); i.select(); } }

// ── выбор периода / загрузка ─────────────────────────────────────
function ensureSel(base: string) {
  if (sel[base]) return;
  const m = stageOf(base)?.mode;
  if (m === "timeline") {
    const ys = keysForBase(base).map((k) => parsePeriod(k, base).year).filter((y): y is number => y != null);
    sel[base] = { year: ys.length ? Math.max(...ys) : CUR_YEAR, quarter: null };
  } else if (m === "quarter") {
    sel[base] = { year: CUR_YEAR, quarter: CUR_Q };
  } else {
    sel[base] = { year: CUR_YEAR, quarter: null };
  }
}
function activeKey(base: string): string {
  const s = sel[base] || { year: null, quarter: null };
  return periodKey(base, s.year, s.quarter);
}

async function toggleStage(base: string) {
  if (expanded.value.has(base)) { expanded.value.delete(base); expanded.value = new Set(expanded.value); return; }
  ensureSel(base);
  expanded.value.add(base); expanded.value = new Set(expanded.value);
  await ensureLoaded(activeKey(base));
}
async function pickYear(base: string, year: number) {
  ensureSel(base);
  sel[base].year = year;
  if (stageOf(base)?.mode === "quarter") sel[base].quarter = (year === CUR_YEAR ? CUR_Q : 1);
  await ensureLoaded(activeKey(base));
}
async function pickQuarter(base: string, q: number) { ensureSel(base); sel[base].quarter = q; await ensureLoaded(activeKey(base)); }
async function pickLegacy(base: string) { ensureSel(base); sel[base].year = null; sel[base].quarter = null; await ensureLoaded(base); }

async function ensureLoaded(pk: string) {
  if (filesByPeriod[pk] !== undefined) return;
  loadingPeriod.value = pk;
  try {
    const { items } = await documentsApi.list(props.companyCode, { entity_type: "esg_stage", entity_id: pk });
    // За время запроса пользователь мог загрузить файл (doUpload во время
    // «Загрузка…») — не затираем его: объединяем по id, локальные (новые) впереди.
    const pending = filesByPeriod[pk] || [];
    const ids = new Set(items.map((d) => d.id));
    filesByPeriod[pk] = [...pending.filter((d) => !ids.has(d.id)), ...items];
    counts[pk] = filesByPeriod[pk].length;
  } catch { if (filesByPeriod[pk] === undefined) filesByPeriod[pk] = []; }
  finally { loadingPeriod.value = null; }
}

async function doUpload(pk: string, base: string, files: FileList | File[]) {
  if (!props.canEdit || !files || !files.length) return;
  const list = Array.from(files);
  uploadingPeriod.value = pk; uploadPct.value = 0;
  let ok = 0;
  try {
    for (const f of list) {
      const doc = await documentsApi.upload(props.companyCode, f, {
        entityType: "esg_stage", entityId: pk, entityLabel: labelFor(base),
        onProgress: (p) => { uploadPct.value = p; },
      });
      (filesByPeriod[pk] ||= []).unshift(doc);
      counts[pk] = (counts[pk] || 0) + 1;
      ok++;
    }
    toast.success(t(ok > 1 ? "Загружено файлов: {n}" : "Файл загружен", { n: ok }));
    emit("changed");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось загрузить файл"));
  } finally { uploadingPeriod.value = null; uploadPct.value = 0; }
}
function onDrop(pk: string, base: string, e: DragEvent) {
  dragPeriod.value = null;
  const files = e.dataTransfer?.files;
  if (files && files.length) doUpload(pk, base, files);
}
function onPick(pk: string, base: string, e: Event) {
  const inp = e.target as HTMLInputElement;
  if (inp.files) doUpload(pk, base, inp.files);
  inp.value = "";
}

async function download(doc: DocItem) {
  try { const { url } = await documentsApi.url(props.companyCode, doc.id); window.open(url, "_blank"); }
  catch { toast.error(t("Не удалось открыть файл")); }
}
async function removeDoc(pk: string, doc: DocItem) {
  try {
    await documentsApi.remove(props.companyCode, doc.id);
    filesByPeriod[pk] = (filesByPeriod[pk] || []).filter((d) => d.id !== doc.id);
    counts[pk] = Math.max(0, (counts[pk] || 1) - 1);
    delId.value = null;
    toast.success(t("Документ перемещён в корзину"));
    emit("changed");
  } catch (e: any) { toast.error(e?.response?.data?.detail || t("Не удалось удалить")); }
}

const totalDocs = computed(() => GROUPS.reduce((s, g) => s + g.stages.reduce((n, st) => n + stageTotal(st.key), 0), 0));

function modeTag(m: Mode): string { return m === "quarter" ? t("годы · кварталы") : m === "timeline" ? t("таймлайн") : t("по годам"); }
function periodLabel(base: string): string {
  const s = sel[base];
  if (!s) return "";
  if (s.year == null) return t("Ранее (без года)");
  return s.quarter != null ? `${s.year} · Q${s.quarter}` : `${s.year}`;
}

const KIND_ICON: Record<string, string> = { pdf: "📄", doc: "📝", sheet: "📊", slide: "📽", image: "🖼", archive: "🗜", other: "📎" };
function fmtSize(b: number | null): string {
  if (!b) return "";
  if (b < 1024) return `${b} B`;
  if (b < 1048576) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1048576).toFixed(1)} MB`;
}
function fmtDate(iso: string | null): string {
  if (!iso) return "";
  try { return new Date(iso).toLocaleDateString(getCurrentIntlLocale(), { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}
</script>

<template>
  <div class="esd">
    <div class="esd-head">
      <div class="esd-title">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
        {{ t("Документы по этапам") }}
      </div>
      <span class="esd-total" :class="{ has: totalDocs > 0 }">{{ totalDocs > 0 ? t("{n} файлов", { n: totalDocs }) : t("нет документов") }}</span>
    </div>
    <p class="esd-sub">{{ t("Загруженные файлы попадают в раздел «Документы» компании (папка «ESG»).") }}</p>

    <div v-for="g in GROUPS" :key="g.title" class="esd-group" :style="{ '--acc': g.accent }">
      <div class="esd-gtitle">{{ t(g.title) }}</div>

      <div v-for="s in g.stages" :key="s.key" class="esd-stage" :class="{ open: expanded.has(s.key) }">
        <button type="button" class="esd-row" @click="toggleStage(s.key)">
          <span class="esd-num">{{ s.num }}</span>
          <span class="esd-name">{{ t(s.label) }}</span>
          <span class="esd-mode">{{ modeTag(s.mode) }}</span>
          <span class="esd-badge" :class="{ has: stageTotal(s.key) > 0 }">
            <svg v-if="stageTotal(s.key) > 0" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            {{ stageTotal(s.key) > 0 ? stageTotal(s.key) : t("нет") }}
          </span>
          <svg class="esd-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>

        <Transition name="esd-exp">
          <div v-if="expanded.has(s.key)" class="esd-body">

            <!-- ISO — премиум-таймлайн по годам -->
            <div v-if="s.mode === 'timeline'" class="esd-tl">
              <div class="esd-tl-scroll">
                <div class="esd-tl-track">
                  <button v-if="legacyCount(s.key) > 0" type="button" class="esd-tl-node esd-tl-legacy"
                          :class="{ sel: sel[s.key]?.year === null }" @click="pickLegacy(s.key)" :title="t('Ранее (без года)')">
                    <span class="esd-tl-dot"><span class="esd-tl-cnt">{{ legacyCount(s.key) }}</span></span>
                    <span class="esd-tl-y">{{ t('Ранее') }}</span>
                  </button>
                  <button v-for="(y, yi) in yearsFor(s.key).slice().reverse()" :key="y" type="button"
                          class="esd-tl-node" :class="{ has: yearTotal(s.key, y) > 0, sel: sel[s.key]?.year === y, cur: y === CUR_YEAR }"
                          :style="{ '--i': yi }" @click="pickYear(s.key, y)"
                          :title="t('{y} · {n} документов', { y, n: yearTotal(s.key, y) })">
                    <span class="esd-tl-dot">
                      <span v-if="yearTotal(s.key, y) > 0" class="esd-tl-cnt">{{ yearTotal(s.key, y) }}</span>
                    </span>
                    <span class="esd-tl-y">{{ y }}</span>
                  </button>
                  <button v-if="canEdit && yearAdd !== s.key" type="button" class="esd-tl-node esd-tl-add"
                          @click="startAddYear(s.key)" :title="t('Добавить год')">
                    <span class="esd-tl-dot esd-tl-add-dot">+</span>
                    <span class="esd-tl-y">{{ t('год') }}</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Годы (year / quarter) -->
            <template v-else>
              <div class="esd-years">
                <button v-for="(y, yi) in yearsFor(s.key)" :key="y" type="button" class="esd-year"
                        :class="{ sel: sel[s.key]?.year === y, has: yearTotal(s.key, y) > 0, cur: y === CUR_YEAR }"
                        :style="{ '--i': yi }" @click="pickYear(s.key, y)">
                  <span class="esd-year-y">{{ y }}</span>
                  <span v-if="y === CUR_YEAR" class="esd-year-cur">{{ t("текущий") }}</span>
                  <span class="esd-year-b" :class="{ on: yearTotal(s.key, y) > 0 }">{{ yearTotal(s.key, y) || 0 }}</span>
                </button>
                <button v-if="legacyCount(s.key) > 0" type="button" class="esd-year esd-year-legacy"
                        :class="{ sel: sel[s.key]?.year === null }" @click="pickLegacy(s.key)">
                  <span class="esd-year-y">{{ t("Ранее") }}</span>
                  <span class="esd-year-b on">{{ legacyCount(s.key) }}</span>
                </button>
                <button v-if="canEdit && yearAdd !== s.key" type="button" class="esd-year esd-year-add"
                        @click="startAddYear(s.key)" :title="t('Добавить год')">+&nbsp;{{ t('год') }}</button>
              </div>
              <!-- Кварталы -->
              <div v-if="s.mode === 'quarter' && sel[s.key]?.year != null" class="esd-qs">
                <button v-for="q in 4" :key="q" type="button" class="esd-q"
                        :class="{ sel: sel[s.key]?.quarter === q, has: quarterCount(s.key, sel[s.key]!.year!, q) > 0 }"
                        @click="pickQuarter(s.key, q)">
                  Q{{ q }}<span v-if="quarterCount(s.key, sel[s.key]!.year!, q) > 0" class="esd-q-b">{{ quarterCount(s.key, sel[s.key]!.year!, q) }}</span>
                </button>
              </div>
            </template>

            <!-- Ввод нового года (любой режим): будущий / до 2021 -->
            <div v-if="yearAdd === s.key" class="esd-yr-add">
              <span class="esd-yr-add-l">{{ t('Добавить год') }}</span>
              <input :ref="focusInput" type="number" class="esd-yr-inp" v-model="yearAddVal" min="1990" max="2100"
                     @keydown.enter.prevent="confirmAddYear(s.key)" @keydown.esc.stop.prevent="cancelAddYear" @click.stop />
              <button type="button" class="esd-yr-ok" @click.stop="confirmAddYear(s.key)" :title="t('Добавить')">✓</button>
              <button type="button" class="esd-yr-no" @click.stop="cancelAddYear" :title="t('Отмена')">✕</button>
            </div>

            <!-- Панель периода: загрузка + файлы за выбранный период -->
            <div class="esd-panel">
              <div class="esd-panel-h">
                <span class="esd-panel-badge" :style="{ background: g.accent }"></span>{{ periodLabel(s.key) }}
              </div>
              <label v-if="canEdit" class="esd-drop"
                     :class="{ over: dragPeriod === activeKey(s.key), busy: uploadingPeriod === activeKey(s.key) }"
                     @dragover.prevent="dragPeriod = activeKey(s.key)" @dragleave="dragPeriod = null" @drop.prevent="onDrop(activeKey(s.key), s.key, $event)">
                <input type="file" multiple class="esd-file" @change="onPick(activeKey(s.key), s.key, $event)" :disabled="uploadingPeriod === activeKey(s.key)" />
                <template v-if="uploadingPeriod === activeKey(s.key)">
                  <div class="esd-prog"><div class="esd-prog-bar" :style="{ width: uploadPct + '%' }"></div></div>
                  <span class="esd-drop-t">{{ t("Загрузка… {p}%", { p: uploadPct }) }}</span>
                </template>
                <template v-else>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
                  <span class="esd-drop-t">{{ t("Перетащите файлы или нажмите для загрузки") }}</span>
                </template>
              </label>

              <div v-if="loadingPeriod === activeKey(s.key)" class="esd-load">{{ t("Загрузка…") }}</div>
              <ul v-else-if="(filesByPeriod[activeKey(s.key)] || []).length" class="esd-files">
                <li v-for="(d, di) in filesByPeriod[activeKey(s.key)]" :key="d.id" class="esd-fitem" :style="{ animationDelay: di * 35 + 'ms' }">
                  <span class="esd-fico">{{ KIND_ICON[d.kind] || "📎" }}</span>
                  <div class="esd-finfo">
                    <button type="button" class="esd-fname" @click="download(d)" :title="t('Скачать / открыть')">{{ d.name }}</button>
                    <div class="esd-fmeta">
                      <span v-if="d.uploader_name">{{ d.uploader_name }}</span>
                      <span v-if="d.created_at">· {{ fmtDate(d.created_at) }}</span>
                      <span v-if="d.size_bytes">· {{ fmtSize(d.size_bytes) }}</span>
                    </div>
                  </div>
                  <button type="button" class="esd-fdl" @click="download(d)" :title="t('Скачать')">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>
                  </button>
                  <template v-if="canEdit">
                    <span v-if="delId === d.id" class="esd-del-cfm">
                      <button type="button" class="esd-ok" @click="removeDoc(activeKey(s.key), d)" :title="t('Удалить')">✓</button>
                      <button type="button" class="esd-no" @click="delId = null" :title="t('Отмена')">✕</button>
                    </span>
                    <button v-else type="button" class="esd-fdel" @click="delId = d.id" :title="t('В корзину')">
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                    </button>
                  </template>
                </li>
              </ul>
              <div v-else class="esd-empty">{{ t("За этот период документов нет") }}</div>
            </div>

          </div>
        </Transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.esd { font-family: var(--font, system-ui); }
.esd-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px; }
.esd-title { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.esd-total { font-size: 11px; color: var(--t3, #888780); }
.esd-total.has { color: var(--p-deep, #534AB7); font-weight: 600; }
.esd-sub { font-size: 11px; color: var(--t3, #888780); margin: 0 0 12px; }

.esd-group { margin-bottom: 14px; padding-left: 10px; border-radius: 8px; position: relative; }
.esd-group::before { content: ""; position: absolute; left: 0; top: 4px; bottom: 4px; width: 3px; border-radius: 3px; background: var(--acc); opacity: .85; }
.esd-gtitle { font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--acc); margin-bottom: 5px; }

.esd-stage { border-radius: 9px; overflow: hidden; margin-bottom: 5px; background: var(--bg1, #fff); border: 0.5px solid rgba(0,0,0,.06); transition: border-color .15s, box-shadow .15s; }
.esd-stage.open { border-color: color-mix(in srgb, var(--acc) 40%, transparent); box-shadow: 0 3px 14px rgba(15,23,60,.07); }
.esd-row { width: 100%; display: flex; align-items: center; gap: 10px; padding: 9px 11px; background: transparent; border: 0; cursor: pointer; font-family: inherit; text-align: left; transition: background .12s; }
.esd-row:hover { background: color-mix(in srgb, var(--acc) 6%, transparent); }
.esd-num { flex: none; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; color: #fff; background: var(--acc); }
.esd-name { flex: 1; min-width: 0; font-size: 12.5px; color: var(--t1, #1E2A4A); line-height: 1.35; }
.esd-mode { flex: none; font-size: 8.5px; font-weight: 700; letter-spacing: .03em; text-transform: uppercase; color: var(--acc); background: color-mix(in srgb, var(--acc) 12%, transparent); padding: 2px 6px; border-radius: 5px; white-space: nowrap; }
.esd-badge { flex: none; display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; color: var(--t3, #888780); background: rgba(0,0,0,.05); }
.esd-badge.has { color: #0F6E56; background: rgba(29,158,117,.12); }
.esd-chev { flex: none; color: var(--t4, #B4B2A9); transition: transform .2s; }
.esd-stage.open .esd-chev { transform: rotate(180deg); }

.esd-body { padding: 8px 11px 12px; }

/* ── Годы: лента чипов ─────────────────────────────────────────── */
.esd-years { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
.esd-year { display: inline-flex; align-items: center; gap: 7px; padding: 6px 10px; border-radius: 9px; border: 1px solid rgba(0,0,0,.08);
  background: var(--bg1, #fff); cursor: pointer; font-family: inherit; transition: transform .14s var(--ease-standard, cubic-bezier(.4,0,.2,1)), border-color .14s, box-shadow .14s, background .14s;
  animation: esdYearIn .34s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; animation-delay: calc(var(--i) * 32ms); }
.esd-year:hover { transform: translateY(-1px); border-color: color-mix(in srgb, var(--acc) 45%, transparent); box-shadow: 0 4px 12px rgba(15,23,60,.08); }
.esd-year.sel { background: color-mix(in srgb, var(--acc) 12%, #fff); border-color: var(--acc); box-shadow: 0 4px 14px color-mix(in srgb, var(--acc) 24%, transparent); }
.esd-year-y { font-size: 13px; font-weight: 700; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; }
.esd-year.sel .esd-year-y { color: var(--acc); }
.esd-year-cur { font-size: 8px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; color: var(--acc); background: color-mix(in srgb, var(--acc) 14%, transparent); padding: 1px 5px; border-radius: 4px; }
.esd-year-b { min-width: 18px; text-align: center; font-size: 10.5px; font-weight: 700; color: var(--t4, #B4B2A9); background: rgba(0,0,0,.05); border-radius: 999px; padding: 1px 6px; font-variant-numeric: tabular-nums; }
.esd-year-b.on { color: #fff; background: var(--acc); }
.esd-year-legacy { border-style: dashed; }
.esd-year-add { border-style: dashed; color: var(--acc); font-size: 12px; font-weight: 700; padding: 6px 11px; }
.esd-year-add:hover { background: color-mix(in srgb, var(--acc) 10%, #fff); }

/* Ввод нового года (кнопка «+ год») */
.esd-yr-add { display: inline-flex; align-items: center; gap: 6px; margin-bottom: 10px; padding: 6px 8px; border-radius: 9px; background: color-mix(in srgb, var(--acc) 7%, transparent); animation: esdPanelIn .2s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; }
.esd-yr-add-l { font-size: 11px; font-weight: 600; color: var(--t2, #5F5E5A); }
.esd-yr-inp { width: 72px; padding: 4px 8px; border: 1px solid color-mix(in srgb, var(--acc) 40%, #d5d5df); border-radius: 7px; font-family: inherit; font-size: 12.5px; font-weight: 700; color: var(--t1, #1E2A4A); background: var(--bg1, #fff); font-variant-numeric: tabular-nums; }
.esd-yr-inp:focus { outline: none; border-color: var(--acc); box-shadow: 0 0 0 3px color-mix(in srgb, var(--acc) 18%, transparent); }
.esd-yr-ok, .esd-yr-no { width: 26px; height: 26px; border: 0; border-radius: 7px; cursor: pointer; font-size: 13px; font-weight: 700; }
.esd-yr-ok { background: color-mix(in srgb, var(--acc) 16%, transparent); color: var(--acc); }
.esd-yr-ok:hover { background: var(--acc); color: #fff; }
.esd-yr-no { background: rgba(0,0,0,.06); color: var(--t3, #5F5E5A); }

/* ── Кварталы: сегментированные табы ───────────────────────────── */
.esd-qs { display: flex; gap: 5px; margin-bottom: 10px; padding: 3px; background: color-mix(in srgb, var(--acc) 6%, transparent); border-radius: 10px; width: fit-content; }
.esd-q { position: relative; min-width: 46px; padding: 5px 11px; border: 0; border-radius: 7px; background: transparent; cursor: pointer; font-family: inherit; font-size: 12px; font-weight: 700; color: var(--t3, #888780); transition: color .14s, background .14s, box-shadow .14s; }
.esd-q:hover { color: var(--acc); }
.esd-q.sel { color: var(--acc); background: var(--bg1, #fff); box-shadow: 0 2px 8px rgba(15,23,60,.1); }
.esd-q.has::after { content: ""; position: absolute; top: 5px; right: 6px; width: 5px; height: 5px; border-radius: 50%; background: var(--acc); }
.esd-q-b { margin-left: 5px; font-size: 9.5px; font-weight: 700; color: #fff; background: var(--acc); border-radius: 999px; padding: 0 5px; vertical-align: 1px; }

/* ── ISO таймлайн ──────────────────────────────────────────────── */
.esd-tl { margin-bottom: 12px; }
.esd-tl-scroll { overflow-x: auto; padding: 22px 4px 4px; scrollbar-width: thin; }
.esd-tl-track { position: relative; display: flex; align-items: flex-start; gap: 0; min-width: min-content; padding: 0 14px; }
.esd-tl-track::before { content: ""; position: absolute; left: 24px; right: 24px; top: 9px; height: 2px; border-radius: 2px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--acc) 55%, #d9d9e3), color-mix(in srgb, var(--acc) 20%, #d9d9e3));
  transform-origin: left; animation: esdTlLine .5s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; }
.esd-tl-node { position: relative; flex: 1 0 58px; display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 0; border: 0; background: transparent; cursor: pointer; font-family: inherit;
  animation: esdTlNode .4s var(--ease-standard, cubic-bezier(.34,1.56,.64,1)) both; animation-delay: calc(var(--i) * 55ms + 120ms); }
.esd-tl-dot { position: relative; width: 20px; height: 20px; border-radius: 50%; background: var(--bg1, #fff); border: 2px solid color-mix(in srgb, var(--acc) 35%, #cfcfda); box-shadow: 0 0 0 3px var(--bg1, #fff); transition: transform .16s, border-color .16s, background .16s; }
.esd-tl-node:hover .esd-tl-dot { transform: scale(1.18); border-color: var(--acc); }
.esd-tl-node.has .esd-tl-dot { background: var(--acc); border-color: var(--acc); }
.esd-tl-node.cur .esd-tl-dot { border-color: var(--acc); border-style: dashed; }
.esd-tl-node.sel .esd-tl-dot { transform: scale(1.28); background: var(--acc); border-color: var(--acc); box-shadow: 0 0 0 3px var(--bg1, #fff), 0 0 0 6px color-mix(in srgb, var(--acc) 28%, transparent); }
.esd-tl-cnt { position: absolute; left: 50%; top: -20px; transform: translateX(-50%); font-size: 9.5px; font-weight: 800; color: var(--acc); background: color-mix(in srgb, var(--acc) 14%, #fff); border-radius: 999px; padding: 1px 6px; box-shadow: 0 1px 4px rgba(15,23,60,.12); }
.esd-tl-y { font-size: 11px; font-weight: 700; color: var(--t3, #888780); font-variant-numeric: tabular-nums; transition: color .16s; }
.esd-tl-node.sel .esd-tl-y, .esd-tl-node.has .esd-tl-y { color: var(--t1, #1E2A4A); }
.esd-tl-node.sel .esd-tl-y { color: var(--acc); }
/* Легаси-узел (документы без года) — слева, пунктирный */
.esd-tl-legacy { flex: 0 0 auto; }
.esd-tl-legacy .esd-tl-dot { background: color-mix(in srgb, var(--acc) 28%, #fff); border-style: dashed; border-color: var(--acc); }
.esd-tl-legacy.sel .esd-tl-dot { background: var(--acc); }
.esd-tl-legacy .esd-tl-cnt { color: var(--acc); }
.esd-tl-legacy .esd-tl-y { color: var(--t2, #5F5E5A); }
/* «+ год» узел таймлайна — справа, пунктирный */
.esd-tl-add { flex: 0 0 auto; }
.esd-tl-add-dot { display: inline-flex; align-items: center; justify-content: center; color: var(--acc); font-size: 14px; font-weight: 800; line-height: 1; background: var(--bg1, #fff); border-style: dashed; }
.esd-tl-add:hover .esd-tl-add-dot { background: color-mix(in srgb, var(--acc) 12%, #fff); }
.esd-tl-add .esd-tl-y { color: var(--acc); font-weight: 700; }

/* ── Панель периода ────────────────────────────────────────────── */
.esd-panel { animation: esdPanelIn .28s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; }
.esd-panel-h { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 700; color: var(--t1, #1E2A4A); margin-bottom: 8px; font-variant-numeric: tabular-nums; }
.esd-panel-badge { width: 8px; height: 8px; border-radius: 3px; flex: none; }

.esd-drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; padding: 14px; border: 1.5px dashed color-mix(in srgb, var(--acc) 45%, #d5d5df); border-radius: 9px; cursor: pointer; color: var(--t3, #888780); background: color-mix(in srgb, var(--acc) 4%, transparent); transition: all .15s; position: relative; margin-bottom: 8px; }
.esd-drop:hover, .esd-drop.over { border-color: var(--acc); color: var(--acc); background: color-mix(in srgb, var(--acc) 10%, transparent); }
.esd-drop.over { transform: scale(1.01); }
.esd-drop.busy { cursor: default; }
.esd-file { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
.esd-drop.busy .esd-file { pointer-events: none; }
.esd-drop-t { font-size: 11.5px; font-weight: 500; }
.esd-prog { width: 70%; height: 5px; border-radius: 3px; background: rgba(0,0,0,.08); overflow: hidden; }
.esd-prog-bar { height: 100%; border-radius: 3px; background: var(--acc); transition: width .2s ease; }

.esd-load, .esd-empty { font-size: 11.5px; color: var(--t3, #888780); padding: 6px 2px; text-align: center; }
.esd-files { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; }
.esd-fitem { display: flex; align-items: center; gap: 9px; padding: 6px 8px; border-radius: 7px; transition: background .12s; animation: esdIn .3s var(--ease-standard, cubic-bezier(.4,0,.2,1)) both; }
.esd-fitem:hover { background: rgba(127,119,221,.05); }
.esd-fico { flex: none; font-size: 15px; }
.esd-finfo { flex: 1; min-width: 0; }
.esd-fname { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; background: transparent; border: 0; padding: 0; font-family: inherit; font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); cursor: pointer; text-align: left; }
.esd-fname:hover { color: var(--p-deep, #534AB7); text-decoration: underline; }
.esd-fmeta { font-size: 10px; color: var(--t3, #888780); display: flex; gap: 4px; flex-wrap: wrap; margin-top: 1px; }
.esd-fdl, .esd-fdel { flex: none; width: 26px; height: 26px; border-radius: 6px; border: 0; background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; color: var(--t3, #888780); transition: background .12s, color .12s; }
.esd-fdl:hover { background: rgba(127,119,221,.1); color: var(--p-deep, #534AB7); }
.esd-fdel:hover { background: rgba(226,75,74,.1); color: var(--sev-critical, #A32D2D); }
.esd-del-cfm { flex: none; display: inline-flex; gap: 3px; }
.esd-ok, .esd-no { width: 24px; height: 24px; border-radius: 6px; border: 0; cursor: pointer; font-size: 12px; font-weight: 700; }
.esd-ok { background: rgba(226,75,74,.14); color: var(--sev-critical, #A32D2D); }
.esd-no { background: rgba(0,0,0,.06); color: var(--t3, #5F5E5A); }

@keyframes esdIn { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: none; } }
@keyframes esdYearIn { from { opacity: 0; transform: translateY(6px) scale(.96); } to { opacity: 1; transform: none; } }
@keyframes esdPanelIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
@keyframes esdTlLine { from { transform: scaleX(0); opacity: 0; } to { transform: scaleX(1); opacity: 1; } }
@keyframes esdTlNode { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
.esd-exp-enter-active, .esd-exp-leave-active { transition: opacity .2s ease, max-height .26s var(--ease-standard, cubic-bezier(.4,0,.2,1)); overflow: hidden; }
.esd-exp-enter-from, .esd-exp-leave-to { opacity: 0; max-height: 0; }
.esd-exp-enter-to, .esd-exp-leave-from { opacity: 1; max-height: 900px; }

@media (prefers-color-scheme: dark) {
  .esd-stage { background: var(--bg1, #232433); border-color: rgba(255,255,255,.08); }
  .esd-year { background: var(--bg1, #232433); border-color: rgba(255,255,255,.1); }
  .esd-q.sel { background: var(--bg2, #2c2d3f); }
  .esd-tl-dot { background: var(--bg1, #232433); box-shadow: 0 0 0 3px var(--bg1, #232433); }
  .esd-tl-node.sel .esd-tl-dot { box-shadow: 0 0 0 3px var(--bg1, #232433), 0 0 0 6px color-mix(in srgb, var(--acc) 28%, transparent); }
}
@media (prefers-reduced-motion: reduce) {
  .esd-fitem, .esd-year, .esd-tl-node, .esd-tl-track::before, .esd-panel { animation: none; }
  .esd-drop.over, .esd-year:hover, .esd-tl-node:hover .esd-tl-dot { transform: none; }
  .esd-exp-enter-active, .esd-exp-leave-active { transition: none; }
}
</style>
