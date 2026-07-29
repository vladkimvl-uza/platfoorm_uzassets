<script setup lang="ts">
/**
 * «Документы» — библиотека компании (вкладка воркспейса).
 *
 * Логика (SharePoint-подобная, но своя):
 *  • ДВЕ структуры одновременно: папки (где лежит) и типы файлов (что это).
 *    Пользователь ищет либо так, либо так — обе доступны одним кликом;
 *  • у каждого файла видно КТО загрузил и КОГДА, размер и откуда файл пришёл
 *    (чипы привязок: «Задача: …», «МСФО 2025») — файл, загруженный в карточке,
 *    лежит здесь же, а не в отдельном хранилище;
 *  • загрузка перетаскиванием на всю область + прогресс;
 *  • удаление мягкое (Корзина) с восстановлением — файл-документ компании
 *    слишком дорого терять по неверному клику.
 */
import { computed, onMounted, ref, watch } from "vue";
import {
  documentsApi, fmtBytes, KIND_META,
  type DocFolder, type DocItem,
} from "@/api/documents";
import { useFormatters } from "@/composables/useFormatters";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import ModalShell from "@/components/ModalShell.vue";

const props = defineProps<{ companyCode: string; canEdit?: boolean }>();

const fmt = useFormatters();
const toast = useToast();
const { confirmDialog } = useConfirm();

const folders = ref<DocFolder[]>([]);
const items = ref<DocItem[]>([]);
const total = ref(0);
const kindCounts = ref<Record<string, number>>({});
const trashCount = ref(0);
const totalFiles = ref(0);
const stats = ref<{ files: number; size_bytes: number; last_upload_at: string | null } | null>(null);

const loading = ref(true);
const activeFolder = ref<string | null>(null);     // null = все файлы
const activeKind = ref<string | null>(null);
const inTrash = ref(false);
const search = ref("");
const view = ref<"list" | "grid">("list");
const dragOver = ref(false);
const uploads = ref<{ name: string; pct: number }[]>([]);
const preview = ref<{ url: string; name: string; mime: string | null } | null>(null);
const renaming = ref<DocItem | null>(null);
const renameValue = ref("");
const newFolderOpen = ref(false);
const newFolderName = ref("");

let searchTimer: number | undefined;

const breadcrumb = computed(() => {
  if (inTrash.value) return "Корзина";
  if (activeKind.value) return KIND_META[activeKind.value]?.label || activeKind.value;
  if (!activeFolder.value) return "Все файлы";
  return folders.value.find((f) => f.id === activeFolder.value)?.name || "Папка";
});

async function loadTree() {
  const t = await documentsApi.tree(props.companyCode);
  folders.value = t.folders;
  totalFiles.value = t.total_files;
  trashCount.value = t.trash_count;
}

async function loadKinds() {
  const k = await documentsApi.kinds(props.companyCode);
  kindCounts.value = k.counts || {};
}

async function loadItems() {
  loading.value = true;
  try {
    const r = await documentsApi.list(props.companyCode, {
      folder_id: activeKind.value || inTrash.value ? undefined : (activeFolder.value ?? undefined),
      kind: activeKind.value ?? undefined,
      q: search.value.trim() || undefined,
      trash: inTrash.value,
      limit: 300,
    });
    items.value = r.items;
    total.value = r.total;
  } catch {
    items.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

async function loadAll() {
  await Promise.all([loadTree(), loadKinds(), loadItems()]);
  try { stats.value = await documentsApi.stats(props.companyCode); } catch { stats.value = null; }
}

onMounted(loadAll);
watch(() => props.companyCode, loadAll);
watch([activeFolder, activeKind, inTrash], loadItems);
watch(search, () => {
  if (searchTimer !== undefined) clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadItems, 280);
});

function pickFolder(id: string | null) {
  activeFolder.value = id; activeKind.value = null; inTrash.value = false;
}
function pickKind(k: string | null) {
  activeKind.value = k; activeFolder.value = null; inTrash.value = false;
}
function openTrash() {
  inTrash.value = true; activeFolder.value = null; activeKind.value = null;
}

// ─── загрузка ───────────────────────────────────────────────────
async function uploadFiles(files: FileList | File[]) {
  if (!props.canEdit) {
    toast.error("Недостаточно прав для загрузки документов");
    return;
  }
  const list = Array.from(files);
  for (const f of list) {
    const entry = { name: f.name, pct: 0 };
    uploads.value.push(entry);
    try {
      await documentsApi.upload(props.companyCode, f, {
        folderId: activeFolder.value,
        onProgress: (p) => { entry.pct = p; },
      });
      toast.success(`Загружено: ${f.name}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || `Не удалось загрузить ${f.name}`);
    } finally {
      uploads.value = uploads.value.filter((u) => u !== entry);
    }
  }
  await loadAll();
}

function onDrop(e: DragEvent) {
  dragOver.value = false;
  if (e.dataTransfer?.files?.length) void uploadFiles(e.dataTransfer.files);
}
function onFilePick(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.length) void uploadFiles(input.files);
  input.value = "";
}

// ─── действия над файлом ────────────────────────────────────────
async function openItem(it: DocItem) {
  try {
    const r = await documentsApi.url(props.companyCode, it.id);
    const previewable = /^image\//.test(r.mime_type || "") || /pdf$/i.test(it.ext);
    if (previewable) preview.value = { url: r.url, name: it.name, mime: r.mime_type };
    else window.open(r.url, "_blank", "noopener");
  } catch {
    toast.error("Не удалось открыть файл");
  }
}
async function download(it: DocItem) {
  try {
    const r = await documentsApi.url(props.companyCode, it.id);
    const a = document.createElement("a");
    a.href = r.url; a.download = it.name; a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
  } catch {
    toast.error("Не удалось скачать файл");
  }
}
function startRename(it: DocItem) { renaming.value = it; renameValue.value = it.name; }
async function saveRename() {
  const it = renaming.value; if (!it) return;
  const name = renameValue.value.trim();
  if (!name || name === it.name) { renaming.value = null; return; }
  try {
    await documentsApi.patch(props.companyCode, it.id, { name });
    toast.success("Переименовано");
    renaming.value = null;
    await loadItems();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось переименовать");
  }
}
async function moveTo(it: DocItem, folderId: string | null) {
  try {
    await documentsApi.patch(props.companyCode, it.id, { folder_id: folderId } as any);
    toast.success("Перемещено");
    await loadAll();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось переместить");
  }
}
async function removeItem(it: DocItem) {
  const hard = inTrash.value;
  const ok = await confirmDialog({
    title: hard ? "Удалить безвозвратно?" : "Переместить в корзину?",
    message: hard
      ? `«${it.name}» будет удалён вместе с файлом. Действие необратимо.`
      : `«${it.name}» уйдёт в корзину — его можно будет восстановить.`,
    danger: true,
  });
  if (!ok) return;
  try {
    await documentsApi.remove(props.companyCode, it.id, hard);
    toast.success(hard ? "Удалено безвозвратно" : "Перемещено в корзину");
    await loadAll();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось удалить");
  }
}
async function restoreItem(it: DocItem) {
  try {
    await documentsApi.restore(props.companyCode, it.id);
    toast.success("Восстановлено");
    await loadAll();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось восстановить");
  }
}
async function createFolder() {
  const name = newFolderName.value.trim();
  if (!name) return;
  try {
    const f = await documentsApi.createFolder(props.companyCode, name, null);
    toast.success(`Папка «${f.name}» создана`);
    newFolderOpen.value = false; newFolderName.value = "";
    await loadTree();
    pickFolder(f.id);
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Не удалось создать папку");
  }
}

const kindList = computed(() =>
  Object.entries(KIND_META)
    .map(([k, meta]) => ({ key: k, ...meta, count: kindCounts.value[k] || 0 }))
    .filter((x) => x.count > 0),
);
function linkHint(it: DocItem): string {
  if (!it.links.length) return "";
  const first = it.links[0];
  const kindRu = first.entity_type === "task" ? "Задача"
    : first.entity_type === "project" ? "Проект"
    : first.entity_type === "financial_report" ? "Отчётность"
    : "Компания";
  return first.label ? `${kindRu}: ${first.label}` : kindRu;
}
</script>

<template>
  <div
    class="doc-root"
    :class="{ 'is-drag': dragOver }"
    @dragover.prevent="dragOver = true"
    @dragleave.prevent="dragOver = false"
    @drop.prevent="onDrop"
  >
    <!-- Шапка: где мы + сводка + поиск + действия -->
    <header class="doc-head">
      <div class="doc-head-main">
        <div class="doc-crumb">
          <span class="doc-crumb-root">Документы</span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>
          <span class="doc-crumb-cur">{{ breadcrumb }}</span>
          <span class="doc-crumb-count">{{ total }}</span>
        </div>
        <div v-if="stats" class="doc-stats">
          {{ stats.files }} файл(ов) · {{ fmtBytes(stats.size_bytes) }}
          <template v-if="stats.last_upload_at">
            · последняя загрузка {{ fmt.fmtRelativeTime(stats.last_upload_at) }}
          </template>
        </div>
      </div>
      <div class="doc-head-tools">
        <label class="doc-search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
          <input v-model="search" type="search" placeholder="Поиск по названию" />
        </label>
        <div class="doc-viewsw" role="group" aria-label="Вид">
          <button :class="{ on: view === 'list' }" title="Список" @click="view = 'list'">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>
          </button>
          <button :class="{ on: view === 'grid' }" title="Плитка" @click="view = 'grid'">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
          </button>
        </div>
        <button v-if="canEdit" class="doc-btn ghost" @click="newFolderOpen = true">Новая папка</button>
        <label v-if="canEdit" class="doc-btn primary">
          Загрузить
          <input type="file" multiple hidden @change="onFilePick" />
        </label>
      </div>
    </header>

    <div class="doc-body">
      <!-- Левая колонка: две структуры — папки и типы -->
      <aside class="doc-rail">
        <div class="doc-rail-lbl">Папки</div>
        <button class="doc-rail-item" :class="{ on: !activeFolder && !activeKind && !inTrash }" @click="pickFolder(null)">
          <span class="doc-rail-name">Все файлы</span>
          <span class="doc-rail-num">{{ totalFiles }}</span>
        </button>
        <button
          v-for="f in folders"
          :key="f.id"
          class="doc-rail-item"
          :class="{ on: activeFolder === f.id }"
          @click="pickFolder(f.id)"
        >
          <svg class="doc-rail-ic" width="14" height="14" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          </svg>
          <span class="doc-rail-name">{{ f.name }}</span>
          <span class="doc-rail-num">{{ f.file_count ?? 0 }}</span>
        </button>

        <div v-if="kindList.length" class="doc-rail-lbl">По типу</div>
        <button
          v-for="k in kindList"
          :key="k.key"
          class="doc-rail-item"
          :class="{ on: activeKind === k.key }"
          @click="pickKind(k.key)"
        >
          <span class="doc-kind-dot" :style="{ background: k.color }"></span>
          <span class="doc-rail-name">{{ k.label }}</span>
          <span class="doc-rail-num">{{ k.count }}</span>
        </button>

        <button class="doc-rail-item doc-rail-trash" :class="{ on: inTrash }" @click="openTrash">
          <svg class="doc-rail-ic" width="14" height="14" viewBox="0 0 24 24" fill="none"
               stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>
          <span class="doc-rail-name">Корзина</span>
          <span class="doc-rail-num">{{ trashCount }}</span>
        </button>
      </aside>

      <!-- Правая часть: файлы -->
      <section class="doc-main">
        <div v-if="uploads.length" class="doc-uploads">
          <div v-for="(u, i) in uploads" :key="i" class="doc-upload">
            <span class="doc-upload-name">{{ u.name }}</span>
            <span class="doc-upload-bar"><i :style="{ width: u.pct + '%' }"></i></span>
            <span class="doc-upload-pct">{{ u.pct }}%</span>
          </div>
        </div>

        <div v-if="loading" class="doc-skel">
          <div v-for="n in 5" :key="n" class="doc-skel-row" :style="{ '--d': n * 60 + 'ms' }"></div>
        </div>

        <div v-else-if="!items.length" class="doc-empty">
          <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>
          </svg>
          <div class="doc-empty-t">{{ inTrash ? 'Корзина пуста' : 'Здесь пока нет документов' }}</div>
          <div v-if="canEdit && !inTrash" class="doc-empty-s">Перетащите файлы сюда или нажмите «Загрузить»</div>
        </div>

        <!-- Список -->
        <div v-else-if="view === 'list'" class="doc-table">
          <div class="doc-tr doc-th">
            <span>Название</span>
            <span>Кто загрузил</span>
            <span>Когда</span>
            <span>Размер</span>
            <span></span>
          </div>
          <div
            v-for="(it, i) in items"
            :key="it.id"
            class="doc-tr doc-row"
            :style="{ '--d': Math.min(i, 14) * 30 + 'ms', '--acc': KIND_META[it.kind]?.color }"
            @dblclick="openItem(it)"
          >
            <span class="doc-cell-name">
              <span class="doc-badge" :style="{ background: (KIND_META[it.kind]?.color || '#94A3B8') + '18', color: KIND_META[it.kind]?.color }">
                {{ it.ext ? it.ext.toUpperCase().slice(0, 4) : 'FILE' }}
              </span>
              <button class="doc-name" :title="it.name" @click="openItem(it)">{{ it.name }}</button>
              <span v-if="linkHint(it)" class="doc-linkchip" :title="linkHint(it)">{{ linkHint(it) }}</span>
            </span>
            <span class="doc-cell-who">{{ it.uploader_name || '—' }}</span>
            <span class="doc-cell-when" :title="it.created_at ? fmt.fmtDateTime(it.created_at) : ''">
              {{ it.created_at ? fmt.fmtRelativeTime(it.created_at) : '—' }}
            </span>
            <span class="doc-cell-size">{{ fmtBytes(it.size_bytes) }}</span>
            <span class="doc-cell-act">
              <button class="doc-act" title="Скачать" @click.stop="download(it)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12M7 11l5 5 5-5M4 21h16"/></svg>
              </button>
              <button v-if="canEdit && !inTrash" class="doc-act" title="Переименовать" @click.stop="startRename(it)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
              </button>
              <button v-if="canEdit && inTrash" class="doc-act" title="Восстановить" @click.stop="restoreItem(it)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>
              </button>
              <button v-if="canEdit" class="doc-act danger" :title="inTrash ? 'Удалить безвозвратно' : 'В корзину'" @click.stop="removeItem(it)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>
              </button>
            </span>
          </div>
        </div>

        <!-- Плитка -->
        <div v-else class="doc-grid">
          <button
            v-for="(it, i) in items"
            :key="it.id"
            class="doc-tile"
            :style="{ '--d': Math.min(i, 18) * 26 + 'ms', '--acc': KIND_META[it.kind]?.color }"
            @click="openItem(it)"
          >
            <span class="doc-tile-badge" :style="{ background: (KIND_META[it.kind]?.color || '#94A3B8') + '18', color: KIND_META[it.kind]?.color }">
              {{ it.ext ? it.ext.toUpperCase().slice(0, 4) : 'FILE' }}
            </span>
            <span class="doc-tile-name" :title="it.name">{{ it.name }}</span>
            <span class="doc-tile-meta">{{ it.uploader_name || '—' }}</span>
            <span class="doc-tile-meta">
              {{ it.created_at ? fmt.fmtRelativeTime(it.created_at) : '—' }} · {{ fmtBytes(it.size_bytes) }}
            </span>
          </button>
        </div>
      </section>
    </div>

    <!-- Оверлей перетаскивания -->
    <div v-if="dragOver" class="doc-drop">
      <div class="doc-drop-card">
        <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 20h16"/>
        </svg>
        <div>Отпустите файлы — они попадут в «{{ breadcrumb }}»</div>
      </div>
    </div>

    <!-- Просмотр -->
    <ModalShell :open="!!preview" size="lg" :title="preview?.name || 'Просмотр'" @close="preview = null">
      <div v-if="preview" class="doc-prev">
        <img v-if="/^image\//.test(preview.mime || '')" :src="preview.url" :alt="preview.name" />
        <iframe v-else :src="preview.url" :title="preview.name"></iframe>
      </div>
    </ModalShell>

    <!-- Переименование -->
    <ModalShell :open="!!renaming" size="sm" title="Переименовать" @close="renaming = null">
      <input v-model="renameValue" class="doc-input" @keyup.enter="saveRename" />
      <template #footer>
        <button class="doc-btn ghost" @click="renaming = null">Отмена</button>
        <button class="doc-btn primary" @click="saveRename">Сохранить</button>
      </template>
    </ModalShell>

    <!-- Новая папка -->
    <ModalShell :open="newFolderOpen" size="sm" title="Новая папка" @close="newFolderOpen = false">
      <input v-model="newFolderName" class="doc-input" placeholder="Название папки" @keyup.enter="createFolder" />
      <template #footer>
        <button class="doc-btn ghost" @click="newFolderOpen = false">Отмена</button>
        <button class="doc-btn primary" @click="createFolder">Создать</button>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.doc-root { position: relative; font-family: var(--font, system-ui); padding: 18px 24px 44px; }

/* ── Шапка ── */
.doc-head {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 16px; flex-wrap: wrap; margin-bottom: 16px;
}
.doc-crumb { display: flex; align-items: center; gap: 7px; }
.doc-crumb-root { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.doc-crumb svg { color: var(--t4, #CBD5E1); }
.doc-crumb-cur { font-size: 17px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.doc-crumb-count {
  font-size: 10.5px; font-weight: 700; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.12); border-radius: 999px; padding: 2px 8px;
}
.doc-stats { font-size: 11.5px; color: var(--t3, #94A3B8); margin-top: 4px; }
.doc-head-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.doc-search {
  display: inline-flex; align-items: center; gap: 7px;
  background: var(--bg2, #F8F9FC); border: 1px solid var(--border, #EEF0F5);
  border-radius: 10px; padding: 7px 11px; color: var(--t3, #94A3B8);
  transition: border-color .15s, box-shadow .15s;
}
.doc-search:focus-within { border-color: rgba(124,111,247,.45); box-shadow: 0 0 0 3px rgba(124,111,247,.10); }
.doc-search input {
  border: 0; outline: 0; background: transparent; font-family: inherit;
  font-size: 12.5px; color: var(--t1, #1E2A4A); width: 190px;
}
.doc-viewsw {
  display: inline-flex; background: var(--bg2, #F8F9FC);
  border: 1px solid var(--border, #EEF0F5); border-radius: 10px; padding: 2px;
}
.doc-viewsw button {
  border: 0; background: transparent; cursor: pointer; padding: 5px 9px;
  border-radius: 8px; color: var(--t3, #94A3B8); line-height: 0;
  transition: background .15s, color .15s;
}
.doc-viewsw button.on { background: #fff; color: var(--p-deep, #534AB7); box-shadow: 0 1px 3px rgba(15,23,60,.10); }
.doc-btn {
  font-family: inherit; font-size: 12.5px; font-weight: 600;
  border-radius: 10px; padding: 8px 15px; cursor: pointer;
  transition: transform .14s, box-shadow .14s, background .14s, border-color .14s;
}
.doc-btn.ghost { color: var(--t2, #4B5468); background: #fff; border: 1px solid var(--border-hard, #E5E7EB); }
.doc-btn.ghost:hover { border-color: rgba(124,111,247,.35); color: var(--p-deep, #534AB7); }
.doc-btn.primary {
  color: #fff; border: 0;
  background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%);
  box-shadow: 0 3px 12px rgba(108,92,231,.30);
}
.doc-btn.primary:hover { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.42); }

/* ── Тело ── */
.doc-body { display: grid; grid-template-columns: 216px 1fr; gap: 18px; align-items: start; }
.doc-rail { display: flex; flex-direction: column; gap: 2px; position: sticky; top: 8px; }
.doc-rail-lbl {
  font-size: 9.5px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--t4, #B4B2A9); margin: 12px 0 4px 10px;
}
.doc-rail-lbl:first-child { margin-top: 0; }
.doc-rail-item {
  display: flex; align-items: center; gap: 8px; width: 100%;
  border: 1px solid transparent; background: transparent; cursor: pointer;
  font-family: inherit; font-size: 12.5px; color: var(--t2, #4B5468);
  padding: 8px 10px; border-radius: 10px; text-align: left;
  transition: background .14s, color .14s, border-color .14s, transform .14s;
}
.doc-rail-item:hover { background: rgba(124,111,247,.06); transform: translateX(2px); }
.doc-rail-item.on {
  background: rgba(124,111,247,.11); color: var(--p-deep, #534AB7);
  border-color: rgba(124,111,247,.20); font-weight: 600;
}
.doc-rail-ic { color: currentColor; opacity: .75; flex-shrink: 0; }
.doc-rail-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-rail-num { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.doc-kind-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-left: 3px; }
.doc-rail-trash { margin-top: 12px; }

/* ── Таблица ── */
.doc-main { min-width: 0; }
.doc-table { display: flex; flex-direction: column; }
.doc-tr {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 150px 110px 84px 108px;
  gap: 10px; align-items: center; padding: 9px 12px;
}
.doc-th {
  font-size: 9.5px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase;
  color: var(--t4, #B4B2A9); border-bottom: 1px solid var(--border, #EEF0F5);
}
.doc-row {
  border-radius: 11px; border: 1px solid transparent; position: relative; overflow: hidden;
  animation: docIn .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d, 0ms);
  transition: background .15s, border-color .15s, transform .15s, box-shadow .15s;
}
.doc-row::before {
  content: ""; position: absolute; left: 0; top: 7px; bottom: 7px; width: 2.5px;
  background: var(--acc, #7C6FF7); border-radius: 0 3px 3px 0;
  transform: scaleY(0); transition: transform .2s;
}
.doc-row:hover::before { transform: scaleY(1); }
.doc-row:hover {
  background: rgba(124,111,247,.045); border-color: rgba(124,111,247,.14);
  transform: translateX(2px); box-shadow: 0 4px 14px rgba(15,23,60,.06);
}
@keyframes docIn { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }
.doc-cell-name { display: flex; align-items: center; gap: 9px; min-width: 0; }
.doc-badge {
  font-size: 9px; font-weight: 800; letter-spacing: .04em;
  padding: 4px 6px; border-radius: 7px; flex-shrink: 0; min-width: 34px; text-align: center;
}
.doc-name {
  border: 0; background: transparent; cursor: pointer; font-family: inherit;
  font-size: 13px; color: var(--t1, #1E2A4A); padding: 0; text-align: left;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0;
}
.doc-name:hover { color: var(--p-deep, #534AB7); text-decoration: underline; }
.doc-linkchip {
  font-size: 9.5px; color: var(--t3, #888780); background: var(--bg2, #F1F2F6);
  border-radius: 6px; padding: 2px 7px; white-space: nowrap; flex-shrink: 0;
  max-width: 170px; overflow: hidden; text-overflow: ellipsis;
}
.doc-cell-who, .doc-cell-when, .doc-cell-size { font-size: 11.5px; color: var(--t2, #4B5468); }
.doc-cell-size { font-variant-numeric: tabular-nums; }
.doc-cell-act { display: flex; gap: 3px; justify-content: flex-end; opacity: 0; transition: opacity .15s; }
.doc-row:hover .doc-cell-act { opacity: 1; }
.doc-act {
  border: 0; background: transparent; cursor: pointer; padding: 5px;
  border-radius: 7px; color: var(--t3, #94A3B8); line-height: 0;
  transition: background .14s, color .14s;
}
.doc-act:hover { background: rgba(124,111,247,.10); color: var(--p-deep, #534AB7); }
.doc-act.danger:hover { background: rgba(226,75,74,.10); color: #E24B4A; }

/* ── Плитка ── */
.doc-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 12px; }
.doc-tile {
  display: flex; flex-direction: column; gap: 5px; align-items: flex-start;
  background: #fff; border: 1px solid var(--border, #EEF0F5); border-radius: 13px;
  padding: 13px; cursor: pointer; font-family: inherit; text-align: left;
  animation: docIn .4s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d, 0ms);
  transition: transform .16s, box-shadow .16s, border-color .16s;
}
.doc-tile:hover {
  transform: translateY(-3px); border-color: rgba(124,111,247,.28);
  box-shadow: 0 10px 26px rgba(15,23,60,.10);
}
.doc-tile-badge {
  font-size: 9.5px; font-weight: 800; padding: 5px 8px; border-radius: 8px; margin-bottom: 3px;
}
.doc-tile-name {
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A); line-height: 1.35;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.doc-tile-meta { font-size: 10.5px; color: var(--t3, #94A3B8); }

/* ── Загрузка / пустое / скелет ── */
.doc-uploads { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.doc-upload { display: flex; align-items: center; gap: 10px; font-size: 11.5px; color: var(--t2, #4B5468); }
.doc-upload-name { max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-upload-bar { flex: 1; height: 5px; background: var(--bg2, #F1F2F6); border-radius: 999px; overflow: hidden; }
.doc-upload-bar i {
  display: block; height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, #8B7FFF, #6C5CE7); transition: width .2s;
}
.doc-upload-pct { font-variant-numeric: tabular-nums; width: 34px; text-align: right; }
.doc-empty {
  display: flex; flex-direction: column; align-items: center; gap: 7px;
  padding: 54px 20px; color: var(--t4, #B4B2A9);
  border: 1.5px dashed var(--border-hard, #E5E7EB); border-radius: 14px;
}
.doc-empty-t { font-size: 13.5px; font-weight: 500; color: var(--t2, #4B5468); }
.doc-empty-s { font-size: 11.5px; }
.doc-skel { display: flex; flex-direction: column; gap: 8px; }
.doc-skel-row {
  height: 42px; border-radius: 11px;
  background: linear-gradient(90deg, #F4F5F9 25%, #EDEFF5 37%, #F4F5F9 63%);
  background-size: 400% 100%; animation: docShimmer 1.3s ease-in-out infinite;
  animation-delay: var(--d, 0ms);
}
@keyframes docShimmer { 0% { background-position: 100% 0; } 100% { background-position: -100% 0; } }

/* ── Drag & drop ── */
.doc-root.is-drag::after {
  content: ""; position: absolute; inset: 8px; border-radius: 16px;
  border: 2px dashed rgba(124,111,247,.55); background: rgba(124,111,247,.05);
  pointer-events: none;
}
.doc-drop {
  position: absolute; inset: 8px; display: flex; align-items: center; justify-content: center;
  pointer-events: none; z-index: 3;
}
.doc-drop-card {
  display: flex; flex-direction: column; align-items: center; gap: 9px;
  background: #fff; border-radius: 16px; padding: 22px 30px;
  box-shadow: 0 16px 40px rgba(15,23,60,.16); color: var(--p-deep, #534AB7);
  font-size: 13px; font-weight: 500;
  animation: docPop .22s var(--ease-standard, cubic-bezier(.34,1.4,.64,1)) both;
}
@keyframes docPop { from { transform: scale(.94); opacity: 0; } to { transform: scale(1); opacity: 1; } }

/* ── Просмотр / инпут ── */
.doc-prev { display: flex; justify-content: center; }
.doc-prev img { max-width: 100%; max-height: 68vh; border-radius: 10px; }
.doc-prev iframe { width: 100%; height: 68vh; border: 0; border-radius: 10px; }
.doc-input {
  width: 100%; font-family: inherit; font-size: 13px; color: var(--t1, #1E2A4A);
  border: 1px solid var(--border-hard, #E5E7EB); border-radius: 10px; padding: 9px 12px; outline: 0;
}
.doc-input:focus { border-color: rgba(124,111,247,.45); box-shadow: 0 0 0 3px rgba(124,111,247,.10); }

@media (max-width: 900px) {
  .doc-body { grid-template-columns: 1fr; }
  .doc-rail { position: static; flex-direction: row; flex-wrap: wrap; }
  .doc-rail-lbl { width: 100%; margin-left: 2px; }
  .doc-tr { grid-template-columns: minmax(0, 1fr) 92px 78px; }
  .doc-cell-who, .doc-cell-act { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .doc-row, .doc-tile, .doc-drop-card, .doc-skel-row { animation: none; }
  .doc-row:hover, .doc-tile:hover, .doc-rail-item:hover { transform: none; }
}
</style>
