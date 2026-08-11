<script setup lang="ts">
/**
 * EsgStageDocsPanel — документы по ЭТАПАМ ESG-зрелости компании.
 *
 * Три группы этапов (Климатические стратегии D4 · Управление ESG-рисками D5 ·
 * Внедрение ISO D1). Под каждым этапом: статус «есть документы / нет», загрузка
 * (drag-drop + прогресс), история файлов (кто/когда), скачивание и удаление.
 *
 * Файлы НЕ хранятся отдельно — идут в общую библиотеку «Документы» компании
 * (documentsApi.upload с тегом entity_type='esg_stage', entity_id="<dim>:<idx>"),
 * поэтому автоматически видны и во вкладке «Документы», и здесь. Год в ключ НЕ
 * входит — этапы программные (план декарбонизации/ISO — не годовой снимок).
 */
import { ref, reactive, computed } from "vue";
import { documentsApi, type DocItem } from "@/api/documents";
import { useI18n } from "@/composables/useI18n";
import { useToast } from "@/composables/useToast";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();
const toast = useToast();

const props = defineProps<{
  companyCode: string;
  /** {"D4:2":3, ...} — счётчики из ESGMaturityCompany.stage_doc_counts (для бейджей без запросов). */
  stageDocCounts?: Record<string, number>;
  canEdit?: boolean;
}>();
const emit = defineEmits<{ (e: "changed"): void }>();

interface Stage { key: string; num: number | string; label: string }
interface Group { title: string; accent: string; stages: Stage[] }

// Ключи-этапы 1:1 с бэкендом (dim:index). Метки — слово-в-слово со скрина зрелости.
const GROUPS: Group[] = [
  {
    title: i18nKey("Климатические стратегии"), accent: "#0A7B5E",
    stages: [
      { key: "D4:1", num: 1, label: i18nKey("Количественная оценка выбросов ПГ (Охваты 1, 2)") },
      { key: "D4:2", num: 2, label: i18nKey("Оценка климат-рисков") },
      { key: "D4:3", num: 3, label: i18nKey("Разработка плана декарбонизации") },
      { key: "D4:4", num: 4, label: i18nKey("Реализация плана декарбонизации") },
    ],
  },
  {
    title: i18nKey("Управление ESG-рисками"), accent: "#7F77DD",
    stages: [
      { key: "D5:1", num: 1, label: i18nKey("Double-materiality assessment") },
      { key: "D5:2", num: 2, label: i18nKey("Количественная оценка рисков устойчивого развития") },
      { key: "D5:3", num: 3, label: i18nKey("Интеграция контроля за рисками в ERM (СУР)") },
    ],
  },
  {
    title: i18nKey("Внедрение ISO"), accent: "#EF9F27",
    stages: [
      { key: "D1:iso14001", num: "14001", label: i18nKey("ISO 14001 · Экологический менеджмент") },
      { key: "D1:iso45001", num: "45001", label: i18nKey("ISO 45001 · Охрана труда и здоровья") },
      { key: "D1:iso50001", num: "50001", label: i18nKey("ISO 50001 · Энергоменеджмент") },
    ],
  },
];

// Локальные счётчики: старт из props, потом синхронно правим при загрузке/удалении.
const counts = reactive<Record<string, number>>({ ...(props.stageDocCounts || {}) });
const expanded = ref<Set<string>>(new Set());
const filesByStage = reactive<Record<string, DocItem[]>>({});
const loadingStage = ref<string | null>(null);
const uploadingStage = ref<string | null>(null);
const uploadPct = ref(0);
const dragStage = ref<string | null>(null);
const delId = ref<string | null>(null);

const totalDocs = computed(() => Object.values(counts).reduce((s, n) => s + (n || 0), 0));

function labelFor(key: string): string {
  for (const g of GROUPS) for (const s of g.stages) if (s.key === key) return `${t(g.title)} · ${t(s.label)}`;
  return key;
}

async function toggle(key: string) {
  if (expanded.value.has(key)) { expanded.value.delete(key); expanded.value = new Set(expanded.value); return; }
  expanded.value.add(key); expanded.value = new Set(expanded.value);
  if (filesByStage[key] === undefined) await loadStage(key);
}

async function loadStage(key: string) {
  loadingStage.value = key;
  try {
    const { items } = await documentsApi.list(props.companyCode, { entity_type: "esg_stage", entity_id: key });
    filesByStage[key] = items;
    counts[key] = items.length;
  } catch {
    filesByStage[key] = [];
  } finally {
    loadingStage.value = null;
  }
}

async function doUpload(key: string, files: FileList | File[]) {
  if (!props.canEdit || !files || !files.length) return;
  const list = Array.from(files);
  uploadingStage.value = key; uploadPct.value = 0;
  let ok = 0;
  try {
    for (const f of list) {
      const doc = await documentsApi.upload(props.companyCode, f, {
        entityType: "esg_stage", entityId: key, entityLabel: labelFor(key),
        onProgress: (p) => { uploadPct.value = p; },
      });
      (filesByStage[key] ||= []).unshift(doc);
      counts[key] = (counts[key] || 0) + 1;
      ok++;
    }
    if (!expanded.value.has(key)) { expanded.value.add(key); expanded.value = new Set(expanded.value); }
    toast.success(t(ok > 1 ? "Загружено файлов: {n}" : "Файл загружен", { n: ok }));
    emit("changed");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось загрузить файл"));
  } finally {
    uploadingStage.value = null; uploadPct.value = 0;
  }
}

function onDrop(key: string, e: DragEvent) {
  dragStage.value = null;
  const files = e.dataTransfer?.files;
  if (files && files.length) doUpload(key, files);
}
function onPick(key: string, e: Event) {
  const inp = e.target as HTMLInputElement;
  if (inp.files) doUpload(key, inp.files);
  inp.value = "";
}

async function download(doc: DocItem) {
  try {
    const { url } = await documentsApi.url(props.companyCode, doc.id);
    window.open(url, "_blank");
  } catch { toast.error(t("Не удалось открыть файл")); }
}

async function removeDoc(key: string, doc: DocItem) {
  try {
    await documentsApi.remove(props.companyCode, doc.id);
    filesByStage[key] = (filesByStage[key] || []).filter(d => d.id !== doc.id);
    counts[key] = Math.max(0, (counts[key] || 1) - 1);
    delId.value = null;
    toast.success(t("Документ перемещён в корзину"));
    emit("changed");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t("Не удалось удалить"));
  }
}

const KIND_ICON: Record<string, string> = {
  pdf: "📄", doc: "📝", sheet: "📊", slide: "📽", image: "🖼", archive: "🗜", other: "📎",
};
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
        <button type="button" class="esd-row" @click="toggle(s.key)">
          <span class="esd-num">{{ s.num }}</span>
          <span class="esd-name">{{ t(s.label) }}</span>
          <span class="esd-badge" :class="{ has: (counts[s.key] || 0) > 0 }">
            <svg v-if="(counts[s.key] || 0) > 0" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
            {{ (counts[s.key] || 0) > 0 ? counts[s.key] : t("нет") }}
          </span>
          <svg class="esd-chev" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
        </button>

        <Transition name="esd-exp">
          <div v-if="expanded.has(s.key)" class="esd-body">
            <!-- Drag-drop загрузка -->
            <label v-if="canEdit" class="esd-drop" :class="{ over: dragStage === s.key, busy: uploadingStage === s.key }"
                   @dragover.prevent="dragStage = s.key" @dragleave="dragStage = null" @drop.prevent="onDrop(s.key, $event)">
              <input type="file" multiple class="esd-file" @change="onPick(s.key, $event)" :disabled="uploadingStage === s.key" />
              <template v-if="uploadingStage === s.key">
                <div class="esd-prog"><div class="esd-prog-bar" :style="{ width: uploadPct + '%' }"></div></div>
                <span class="esd-drop-t">{{ t("Загрузка… {p}%", { p: uploadPct }) }}</span>
              </template>
              <template v-else>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="M17 8l-5-5-5 5"/><path d="M12 3v12"/></svg>
                <span class="esd-drop-t">{{ t("Перетащите файлы или нажмите для загрузки") }}</span>
              </template>
            </label>

            <!-- История файлов -->
            <div v-if="loadingStage === s.key" class="esd-load">{{ t("Загрузка…") }}</div>
            <ul v-else-if="(filesByStage[s.key] || []).length" class="esd-files">
              <li v-for="(d, di) in filesByStage[s.key]" :key="d.id" class="esd-fitem" :style="{ animationDelay: di * 35 + 'ms' }">
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
                    <button type="button" class="esd-ok" @click="removeDoc(s.key, d)" :title="t('Удалить')">✓</button>
                    <button type="button" class="esd-no" @click="delId = null" :title="t('Отмена')">✕</button>
                  </span>
                  <button v-else type="button" class="esd-fdel" @click="delId = d.id" :title="t('В корзину')">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                  </button>
                </template>
              </li>
            </ul>
            <div v-else class="esd-empty">{{ t("По этому этапу документов пока нет") }}</div>
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

.esd-stage { border-radius: 9px; overflow: hidden; margin-bottom: 4px; background: var(--bg1, #fff); border: 0.5px solid rgba(0,0,0,.06); transition: border-color .15s, box-shadow .15s; }
.esd-stage.open { border-color: color-mix(in srgb, var(--acc) 40%, transparent); box-shadow: 0 3px 12px rgba(15,23,60,.06); }
.esd-row { width: 100%; display: flex; align-items: center; gap: 10px; padding: 9px 11px; background: transparent; border: 0; cursor: pointer; font-family: inherit; text-align: left; transition: background .12s; }
.esd-row:hover { background: color-mix(in srgb, var(--acc) 6%, transparent); }
.esd-num { flex: none; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; color: #fff; background: var(--acc); }
.esd-name { flex: 1; min-width: 0; font-size: 12.5px; color: var(--t1, #1E2A4A); line-height: 1.35; }
.esd-badge { flex: none; display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px; color: var(--t3, #888780); background: rgba(0,0,0,.05); }
.esd-badge.has { color: #0F6E56; background: rgba(29,158,117,.12); }
.esd-chev { flex: none; color: var(--t4, #B4B2A9); transition: transform .2s; }
.esd-stage.open .esd-chev { transform: rotate(180deg); }

.esd-body { padding: 4px 11px 12px; }
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
.esd-exp-enter-active, .esd-exp-leave-active { transition: opacity .2s ease, max-height .24s var(--ease-standard, cubic-bezier(.4,0,.2,1)); overflow: hidden; }
.esd-exp-enter-from, .esd-exp-leave-to { opacity: 0; max-height: 0; }
.esd-exp-enter-to, .esd-exp-leave-from { opacity: 1; max-height: 620px; }

@media (prefers-color-scheme: dark) {
  .esd-stage { background: var(--bg1, #232433); border-color: rgba(255,255,255,.08); }
}
@media (prefers-reduced-motion: reduce) {
  .esd-fitem, .esd-drop.over { animation: none; transform: none; }
  .esd-exp-enter-active, .esd-exp-leave-active { transition: none; }
}
</style>
