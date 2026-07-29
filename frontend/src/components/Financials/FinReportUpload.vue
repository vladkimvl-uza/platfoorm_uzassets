<script setup lang="ts">
/**
 * FinReportUpload — ручная загрузка файлов отчётности (МСФО/НСБУ) в воркспейсе.
 * Премиум drag-drop + список файлов с иконкой типа (Excel/PDF/Word/…) и именем.
 * Переиспользует attachments (kind="company", category="ifrs_report"/"nsbu_report").
 */
import { ref, computed, watch, onMounted } from "vue";
import { attachmentsApi, fileKind, formatBytes, type Attachment } from "@/api/attachments";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();

const props = defineProps<{
  companyId: string;
  category: string;      // ifrs_report | nsbu_report
  year: number | null;
  canEdit: boolean;
  title?: string;
}>();

const toast = useToast();
const { confirmDialog } = useConfirm();

const files = ref<Attachment[]>([]);
const loading = ref(false);
const uploading = ref(false);
const dragOver = ref(false);
const inputEl = ref<HTMLInputElement | null>(null);

async function load() {
  if (!props.companyId) { files.value = []; return; }
  loading.value = true;
  try {
    // Отчёты привязаны к году: показываем только за выбранный FY (бэкенд фильтрует).
    const r = await api.get(`/attachments/company/${props.companyId}`, {
      params: { category: props.category, year: props.year ?? undefined },
    });
    files.value = Array.isArray(r.data) ? r.data : [];
  } catch {
    files.value = [];
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => [props.companyId, props.category, props.year], load);

// ─── тип файла: расширение (из имени) + цвет (из mime) ───
const KIND_COLOR: Record<string, string> = {
  xls: "#1D6F42", pdf: "#E0453B", doc: "#2B579A", ppt: "#C43E1C",
  img: "#7F77DD", zip: "#6B7280", txt: "#64748B", other: "#94A3B8",
};
function ext(f: Attachment): string {
  const m = /\.([a-z0-9]{1,5})$/i.exec(f.filename || "");
  if (m) return m[1].toUpperCase();
  const k = fileKind(f.mime_type);
  return k === "other" ? "FILE" : k.toUpperCase();
}
function color(f: Attachment): string { return KIND_COLOR[fileKind(f.mime_type)] || KIND_COLOR.other; }
function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return ""; }
}

// ─── upload ───
function pick() { if (props.canEdit && !uploading.value) inputEl.value?.click(); }
async function onInput(e: Event) {
  const list = (e.target as HTMLInputElement).files;
  if (list) await uploadFiles(Array.from(list));
  if (inputEl.value) inputEl.value.value = "";
}
async function onDrop(e: DragEvent) {
  dragOver.value = false;
  if (!props.canEdit) return;
  const list = e.dataTransfer?.files;
  if (list && list.length) await uploadFiles(Array.from(list));
}
async function uploadFiles(list: File[]) {
  if (!props.companyId || uploading.value) return;
  uploading.value = true;
  let ok = 0;
  for (const file of list) {
    if (file.size > 50 * 1024 * 1024) { toast.error(t("«{name}» больше 50 МБ — пропущен", { name: file.name })); continue; }
    try {
      await attachmentsApi.upload("company", props.companyId, file, {
        title: file.name, category: props.category, year: props.year ?? undefined,
      });
      ok++;
    } catch (err: any) {
      toast.error(t("Не удалось загрузить «{name}»: {err}", { name: file.name, err: err?.response?.data?.detail || err?.message || t("ошибка") }));
    }
  }
  uploading.value = false;
  if (ok) { toast.success(ok === 1 ? t("Отчёт загружен") : t("Загружено файлов: {n}", { n: ok })); await load(); }
}

async function download(f: Attachment) {
  try {
    const r = await attachmentsApi.signedUrl("company", f.id);
    window.open(r.url, "_blank");
  } catch (err: any) {
    toast.error(t("Не удалось открыть файл: {err}", { err: err?.response?.data?.detail || err?.message || t("ошибка") }));
  }
}
async function remove(f: Attachment) {
  if (!props.canEdit) return;
  if (!(await confirmDialog({ message: t("Удалить «{name}»?", { name: f.filename }), danger: true, confirmText: t("Удалить") }))) return;
  try {
    await attachmentsApi.remove("company", f.id);
    files.value = files.value.filter(x => x.id !== f.id);
    toast.success(t("Файл удалён"));
  } catch (err: any) {
    toast.error(t("Не удалось удалить: {err}", { err: err?.response?.data?.detail || err?.message || t("ошибка") }));
  }
}

const heading = computed(() => t(props.title || i18nKey("Загруженные отчёты")));
</script>

<template>
  <div class="fru">
    <div class="fru-hd">
      <div class="fru-t">{{ heading }}<span v-if="files.length" class="fru-n">{{ files.length }}</span></div>
      <div class="fru-s"><template v-if="year">{{ t("за FY {y}", { y: year }) }} · </template>{{ t("Excel, PDF, Word и др.") }}</div>
    </div>

    <!-- зона загрузки -->
    <div v-if="canEdit" class="fru-drop" :class="{ over: dragOver, busy: uploading }"
         role="button" tabindex="0"
         @click="pick" @keydown.enter.prevent="pick"
         @dragover.prevent="dragOver = true" @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
      <input ref="inputEl" type="file" multiple class="fru-input" @change="onInput" />
      <svg class="fru-drop-ic" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
      </svg>
      <div class="fru-drop-txt">
        <b>{{ uploading ? t("Загрузка…") : t("Перетащите файл сюда или нажмите") }}</b>
        <span>{{ t("Excel, PDF, Word, изображения · до 50 МБ") }}</span>
      </div>
    </div>

    <!-- список файлов -->
    <div v-if="loading" class="fru-skel">
      <div v-for="i in 2" :key="i" class="fru-skel-row" :style="{ '--d': (i*80)+'ms' }" />
    </div>
    <transition-group v-else-if="files.length" name="fru-row" tag="div" class="fru-list">
      <div v-for="(f, i) in files" :key="f.id" class="fru-row" :style="{ '--d': Math.min(i*35, 350)+'ms' }">
        <div class="fru-ic" :style="{ '--fc': color(f) }">
          <svg width="30" height="34" viewBox="0 0 30 34" fill="none">
            <path d="M4 2h14l8 8v20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#fff" stroke="var(--fc)" stroke-width="1.4"/>
            <path d="M18 2v6a2 2 0 0 0 2 2h6" fill="none" stroke="var(--fc)" stroke-width="1.4"/>
            <rect x="1" y="18" width="24" height="12" rx="2.5" fill="var(--fc)"/>
          </svg>
          <span class="fru-ic-ext">{{ ext(f) }}</span>
        </div>
        <button class="fru-name" type="button" :title="t('Открыть {name}', { name: f.filename })" @click="download(f)">
          <span class="fru-name-t">{{ f.filename }}</span>
          <span class="fru-name-m">{{ formatBytes(f.size_bytes) }}<template v-if="f.uploader_name"> · {{ f.uploader_name }}</template> · {{ fmtDate(f.created_at) }}</span>
        </button>
        <button class="fru-act fru-dl" type="button" :title="t('Скачать')" @click="download(f)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
        </button>
        <button v-if="canEdit" class="fru-act fru-del" type="button" :title="t('Удалить')" @click="remove(f)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      </div>
    </transition-group>
    <div v-else class="fru-empty">{{ t("Отчёты ещё не загружены") }}</div>
  </div>
</template>

<style scoped>
.fru { background: rgba(255,255,255,.82); backdrop-filter: blur(16px) saturate(1.5); border: 1px solid rgba(255,255,255,.7);
  border-radius: 14px; padding: 14px 16px 16px; box-shadow: 0 2px 12px rgba(15,23,60,.07); position: relative; overflow: hidden;
  animation: finFadeSlideIn .4s ease both; }
.fru::before { content:''; position: absolute; top:0; left:0; right:0; height:3px; background: linear-gradient(90deg,#8B7FFF,#6C5CE7); border-radius: 14px 14px 0 0; }
.fru-hd { margin-bottom: 10px; }
.fru-t { font-size: 13px; font-weight: 650; color: var(--t1,#1E2A4A); display: flex; align-items: center; gap: 8px; }
.fru-n { font-size: 10.5px; font-weight: 700; color: var(--p-deep,#534AB7); background: rgba(124,111,247,.12); border-radius: 999px; padding: 1px 8px; }
.fru-s { font-size: 10.5px; color: var(--t3,#94A3B8); margin-top: 2px; }

.fru-drop { display: flex; align-items: center; gap: 12px; padding: 14px 16px; border: 1.5px dashed rgba(124,111,247,.4);
  border-radius: 12px; background: rgba(124,111,247,.04); color: var(--p-deep,#534AB7); cursor: pointer; outline: none;
  transition: background .16s, border-color .16s, transform .16s; margin-bottom: 12px; }
.fru-drop:hover { background: rgba(124,111,247,.09); border-color: rgba(124,111,247,.6); }
.fru-drop:focus-visible { box-shadow: 0 0 0 3px rgba(124,111,247,.25); }
.fru-drop.over { background: rgba(124,111,247,.14); border-color: #6C5CE7; transform: translateY(-1px); }
.fru-drop.busy { opacity: .6; pointer-events: none; }
.fru-input { display: none; }
.fru-drop-ic { flex-shrink: 0; color: var(--brand,#6C5CE7); }
.fru-drop-txt { display: flex; flex-direction: column; gap: 1px; }
.fru-drop-txt b { font-size: 12.5px; font-weight: 600; color: var(--t1,#1E2A4A); }
.fru-drop-txt span { font-size: 10.5px; color: var(--t3,#94A3B8); }

.fru-list { display: flex; flex-direction: column; gap: 7px; }
.fru-row { display: grid; grid-template-columns: 34px 1fr max-content max-content; align-items: center; gap: 11px;
  background: var(--bg2,#FAFAFD); border: 1px solid var(--border,#ECEAF5); border-radius: 11px; padding: 8px 11px;
  animation: finFadeSlideIn .4s ease var(--d,0ms) both; transition: box-shadow .16s, transform .16s, border-color .16s; }
.fru-row:hover { box-shadow: 0 4px 14px rgba(15,23,60,.08); transform: translateY(-1px); border-color: rgba(124,111,247,.3); }
.fru-ic { position: relative; width: 34px; height: 34px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.fru-ic-ext { position: absolute; bottom: 4px; left: 0; right: 0; text-align: center; font-size: 7px; font-weight: 800; color: #fff; letter-spacing: .02em; }
.fru-name { min-width: 0; display: flex; flex-direction: column; gap: 1px; text-align: left; background: none; border: 0; font-family: inherit; cursor: pointer; padding: 0; }
.fru-name-t { font-size: 12.5px; font-weight: 600; color: var(--t1,#1E2A4A); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fru-name:hover .fru-name-t { color: var(--p-deep,#534AB7); text-decoration: underline; }
.fru-name-m { font-size: 10px; color: var(--t3,#94A3B8); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.fru-act { width: 30px; height: 30px; border-radius: 8px; border: 1px solid var(--border,#ECEAF5); background: #fff; color: var(--t3,#94A3B8);
  cursor: pointer; display: inline-flex; align-items: center; justify-content: center; transition: all .14s; }
.fru-dl:hover { color: var(--p-deep,#534AB7); border-color: rgba(124,111,247,.4); background: rgba(124,111,247,.06); }
.fru-del:hover { color: #E24B4A; border-color: #F3C3C2; background: rgba(226,75,74,.05); }

.fru-empty { font-size: 11.5px; color: #C4C8D4; font-style: italic; padding: 8px 2px; }
.fru-skel { display: flex; flex-direction: column; gap: 7px; }
.fru-skel-row { height: 50px; border-radius: 11px; background: linear-gradient(90deg,#F1F0F7 25%,#FAF9FE 50%,#F1F0F7 75%);
  background-size: 200% 100%; animation: fruShim 1.4s ease-in-out var(--d,0ms) infinite; }
@keyframes fruShim { from { background-position: 200% 0; } to { background-position: -200% 0; } }

.fru-row-enter-active, .fru-row-leave-active { transition: all .28s var(--ease-standard,ease); }
.fru-row-enter-from { opacity: 0; transform: translateY(6px); }
.fru-row-leave-to { opacity: 0; transform: translateX(12px); }
</style>
