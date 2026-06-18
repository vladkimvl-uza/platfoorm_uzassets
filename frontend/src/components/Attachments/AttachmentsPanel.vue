<template>
  <div class="ap-root">
    <header v-if="title || $slots.header" class="ap-head">
      <slot name="header">
        <div class="ap-title">{{ title }}</div>
        <div v-if="hint" class="ap-hint">{{ hint }}</div>
      </slot>
      <div class="ap-head-spacer" />
      <label class="ap-upload-btn" :class="{ 'is-disabled': uploading }">
        <input
          type="file"
          class="ap-file-input"
          :disabled="uploading"
          @change="onFilePicked"
          :accept="acceptAttr"
        />
        <span v-if="uploading">Загрузка…</span>
        <span v-else>+ Загрузить</span>
      </label>
    </header>

    <div v-if="error" class="ap-error">{{ error }}</div>

    <div v-if="loading" class="ap-empty">Загрузка…</div>
    <div v-else-if="items.length === 0" class="ap-empty">{{ emptyText }}</div>
    <ul v-else class="ap-list">
      <li v-for="a in items" :key="a.id" class="ap-item">
        <div class="ap-icon" :class="`ap-icon-${fileKind(a.mime_type)}`">
          {{ kindLabel(a.mime_type) }}
        </div>
        <div class="ap-body">
          <a
            href="#"
            class="ap-name"
            :title="a.filename"
            @click.prevent="onDownload(a)"
          >{{ a.filename }}</a>
          <div class="ap-meta">
            <span>{{ formatBytes(a.size_bytes) }}</span>
            <span class="ap-meta-sep">·</span>
            <span :title="a.created_at">{{ fmtDate(a.created_at) }}</span>
            <span v-if="a.uploader_name" class="ap-meta-sep">·</span>
            <span v-if="a.uploader_name" class="ap-uploader">{{ a.uploader_name }}</span>
          </div>
        </div>
        <button
          v-if="isAdmin"
          class="ap-lock"
          :class="{ 'is-locked': (a.denied_user_count || 0) > 0 }"
          :title="(a.denied_user_count || 0) > 0
            ? `Скрыт от ${a.denied_user_count} польз.`
            : 'Управление доступом'"
          @click="openDenyModal(a)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="2"
               stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
          <span v-if="(a.denied_user_count || 0) > 0" class="ap-lock-cnt">{{ a.denied_user_count }}</span>
        </button>
        <button
          v-if="canDelete(a)"
          class="ap-del"
          title="Удалить файл"
          @click="onDelete(a)"
          :disabled="deletingId === a.id"
        >×</button>
      </li>
    </ul>

    <AttachmentDenyModal
      v-if="denyModalFor"
      :kind="kind"
      :att-id="denyModalFor.id"
      :filename="denyModalFor.filename"
      @close="denyModalFor = null"
      @changed="load"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import {
  attachmentsApi,
  formatBytes,
  fileKind,
  type Attachment,
  type AttachmentKind,
} from "@/api/attachments";
import { useConfirm } from "@/composables/useConfirm";
import AttachmentDenyModal from "./AttachmentDenyModal.vue";

const { confirmDialog } = useConfirm();

const props = withDefaults(defineProps<{
  /** Parent kind — task / project / company. */
  kind: AttachmentKind;
  /** Parent entity id (UUID). */
  parentId: string;
  /** Mark uploads as result-docs (true) or regular attachments (false).
   *  Only used for task/project; ignored for company. */
  isResultDoc?: boolean;
  /** Card title displayed in header. */
  title?: string;
  /** Optional sub-hint under the title. */
  hint?: string;
  /** Pre-filter the list: 'result' | 'regular' | 'all'. */
  filter?: "result" | "regular" | "all";
  /** Empty-state label. */
  emptyText?: string;
  /** Optional: parent passes the current user id so we can show delete only on own files. */
  currentUserId?: string | null;
  /** Optional: parent passes admin flag to allow delete on any file. */
  isAdmin?: boolean;
}>(), {
  isResultDoc: false,
  filter: "all",
  emptyText: "Файлов нет",
  isAdmin: false,
});

const emit = defineEmits<{
  changed: [];
}>();

const rawItems = ref<Attachment[]>([]);
const items = computed(() => {
  if (props.filter === "result") return rawItems.value.filter(a => a.is_result_doc);
  if (props.filter === "regular") return rawItems.value.filter(a => !a.is_result_doc);
  return rawItems.value;
});

const loading = ref(false);
const uploading = ref(false);
const deletingId = ref<string | null>(null);
const error = ref<string | null>(null);
const denyModalFor = ref<Attachment | null>(null);

function openDenyModal(a: Attachment) {
  denyModalFor.value = a;
}

async function load() {
  if (!props.parentId) {
    rawItems.value = [];
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    rawItems.value = await attachmentsApi.list(props.kind, props.parentId);
  } catch (e: any) {
    if (e?.response?.status === 403) {
      rawItems.value = [];   // no access — silent empty
    } else if (e?.response?.status !== 404) {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить файлы";
    }
  } finally {
    loading.value = false;
  }
}

watch(() => props.parentId, load);
onMounted(load);

async function onFilePicked(e: Event) {
  const input = e.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";  // allow re-uploading the same file
  if (!file) return;
  if (file.size > 25 * 1024 * 1024) {
    error.value = "Файл больше 25 МБ — отклонён";
    return;
  }
  uploading.value = true;
  error.value = null;
  try {
    const opts: Parameters<typeof attachmentsApi.upload>[3] =
      props.kind === "company"
        ? { title: file.name }
        : { isResultDoc: props.isResultDoc };
    const att = await attachmentsApi.upload(props.kind, props.parentId, file, opts);
    rawItems.value = [att, ...rawItems.value];
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить файл";
  } finally {
    uploading.value = false;
  }
}

async function onDownload(a: Attachment) {
  try {
    const r = await attachmentsApi.signedUrl(props.kind, a.id);
    const link = document.createElement("a");
    link.href = r.url;
    link.download = r.filename;
    link.target = "_blank";
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось получить ссылку";
  }
}

async function onDelete(a: Attachment) {
  if (!(await confirmDialog({ message: `Удалить файл «${a.filename}»?`, danger: true }))) return;
  deletingId.value = a.id;
  try {
    await attachmentsApi.remove(props.kind, a.id);
    rawItems.value = rawItems.value.filter(x => x.id !== a.id);
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось удалить файл";
  } finally {
    deletingId.value = null;
  }
}

function canDelete(a: Attachment): boolean {
  if (props.isAdmin) return true;
  return !!(props.currentUserId && a.uploader_id === props.currentUserId);
}

function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return ""; }
}

function kindLabel(mime: string | null | undefined): string {
  const k = fileKind(mime);
  return { pdf: "PDF", doc: "DOC", xls: "XLS", ppt: "PPT", img: "IMG", zip: "ZIP", txt: "TXT", other: "FILE" }[k];
}

const acceptAttr = ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.webp,.zip,.txt,.csv";
</script>

<style scoped>
.ap-root {
  display: flex; flex-direction: column; gap: 8px;
}
.ap-head {
  display: flex; align-items: center; gap: 10px;
}
.ap-title {
  font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .08em;
  color: var(--t3, var(--t-muted));
}
.ap-hint { font-size: 10.5px; color: var(--t3, var(--t-muted)); }
.ap-head-spacer { flex: 1; }
.ap-upload-btn {
  display: inline-flex; align-items: center;
  font-size: 11px; font-weight: 500;
  padding: 5px 11px; border-radius: 7px;
  background: rgba(127, 119, 221, .10);
  color: var(--p-deep); cursor: pointer;
  border: 0.5px solid rgba(127, 119, 221, .25);
  transition: background .12s, border-color .12s;
}
.ap-upload-btn:hover { background: rgba(127, 119, 221, .18); border-color: rgba(127, 119, 221, .35); }
.ap-upload-btn.is-disabled { opacity: .6; cursor: default; pointer-events: none; }
.ap-file-input { display: none; }

.ap-error {
  font-size: 11px; color: var(--sev-high);
  padding: 6px 10px; border-radius: 6px;
  background: rgba(226, 75, 74, .07);
}
.ap-empty {
  font-size: 11.5px; color: rgba(30, 42, 74, 0.42);
  padding: 16px 12px; text-align: center;
  border: 1.5px dashed #D8DCE8;
  border-radius: 10px;
  background: #FAFAFE;
}

.ap-list {
  list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: 4px;
}
.ap-item {
  display: grid; grid-template-columns: 36px 1fr auto auto;
  align-items: center; gap: 8px;
  padding: 7px 8px; border-radius: 8px;
  transition: background .1s;
}
.ap-item:hover { background: var(--bg2, #FAFAFC); }
.ap-icon {
  width: 36px; height: 36px;
  border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; font-weight: 500;
  letter-spacing: .04em;
  color: #fff;
  flex-shrink: 0;
}
.ap-icon-pdf  { background: var(--sev-high); }
.ap-icon-doc  { background: var(--blue); }
.ap-icon-xls  { background: var(--green); }
.ap-icon-ppt  { background: var(--amber); }
.ap-icon-img  { background: #7F77DD; }
.ap-icon-zip  { background: var(--t-muted); }
.ap-icon-txt  { background: var(--p-deep); }
.ap-icon-other{ background: var(--t-muted); }

.ap-body { min-width: 0; }
.ap-name {
  display: block;
  font-size: 12.5px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  text-decoration: none;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ap-name:hover { color: var(--p-deep); text-decoration: underline; }
.ap-meta {
  font-size: 10.5px; color: var(--t3, var(--t-muted));
  margin-top: 1px;
  display: flex; gap: 4px; flex-wrap: wrap;
}
.ap-meta-sep { opacity: .35; }
.ap-uploader { color: var(--p-deep); }

.ap-del {
  background: transparent; border: none; cursor: pointer;
  width: 22px; height: 22px;
  border-radius: 4px;
  font-size: 16px; line-height: 1; color: var(--t3, var(--t-muted));
  font-family: inherit;
  transition: background .12s, color .12s;
}
.ap-del:hover { background: rgba(226, 75, 74, .10); color: var(--sev-high); }
.ap-del:disabled { opacity: .4; cursor: default; }

.ap-lock {
  background: transparent; border: none; cursor: pointer;
  display: inline-flex; align-items: center; gap: 3px;
  padding: 0 6px; height: 22px;
  border-radius: 4px;
  color: var(--t3, var(--t-muted));
  font-family: inherit;
  transition: background .12s, color .12s;
}
.ap-lock:hover { background: rgba(127, 119, 221, .10); color: var(--p-deep); }
.ap-lock.is-locked { color: var(--amber); }
.ap-lock.is-locked:hover { background: rgba(239, 159, 39, .10); }
.ap-lock-cnt {
  font-size: 9.5px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}
</style>
