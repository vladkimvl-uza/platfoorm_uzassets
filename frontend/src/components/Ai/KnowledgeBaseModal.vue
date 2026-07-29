<script setup lang="ts">
/**
 * KnowledgeBaseModal — управление базой знаний ИИ (RAG).
 * Owner/admin загружает документы (txt/md/csv/xlsx), ассистент ищет по ним
 * инструментом search_knowledge_base. Поиск — Postgres FTS.
 */
import { ref, onMounted } from "vue";
import { api } from "@/api/client";
import { useConfirm } from "@/composables/useConfirm";
import { useFormatters } from "@/composables/useFormatters";
import { useI18n } from "@/composables/useI18n";
import { useToast } from "@/composables/useToast";
import ModalShell from "@/components/ModalShell.vue";

const { t } = useI18n();
const fmt = useFormatters();
const emit = defineEmits<{ (e: "close"): void }>();
const { confirmDialog } = useConfirm();
const toast = useToast();

interface KbDoc { id: string; title: string; filename: string | null; chunks: number; chars: number; created_at: string | null; }

const docs = ref<KbDoc[]>([]);
const loading = ref(false);
const uploading = ref(false);
const error = ref("");
const fileInput = ref<HTMLInputElement | null>(null);
const title = ref("");

async function load() {
  loading.value = true;
  try {
    const { data } = await api.get("/knowledge");
    docs.value = data || [];
  } catch (e: any) {
    const detail = e?.response?.data?.detail;
    error.value = detail ? t(detail) : t("Не удалось загрузить список");
  } finally { loading.value = false; }
}

async function onUpload() {
  const f = fileInput.value?.files?.[0];
  if (!f) { error.value = t("Выберите файл"); return; }
  uploading.value = true;
  error.value = "";
  try {
    const fd = new FormData();
    fd.append("file", f);
    if (title.value.trim()) fd.append("title", title.value.trim());
    await api.post("/knowledge/upload", fd);
    title.value = "";
    if (fileInput.value) fileInput.value.value = "";
    await load();
  } catch (e: any) {
    const detail = e?.response?.data?.detail;
    error.value = detail ? t(detail) : t("Ошибка загрузки файла");
  } finally { uploading.value = false; }
}

async function remove(id: string) {
  const doc = docs.value.find((d) => d.id === id);
  const ok = await confirmDialog({
    message: t("Удалить документ «{title}» из базы знаний? Действие необратимо.", {
      title: doc?.title || doc?.filename || id,
    }),
    danger: true,
  });
  if (!ok) return;
  try {
    await api.delete(`/knowledge/${id}`);
    docs.value = docs.value.filter((d) => d.id !== id);
    toast.success(t("Документ удалён из базы знаний"));
  } catch (e: any) {
    const detail = e?.response?.data?.detail;
    const msg = detail ? t(detail) : t("Не удалось удалить документ");
    error.value = msg; toast.error(msg);
  }
}

function formatDocMeta(doc: KbDoc): string {
  return t("{chunks} фрагм. · {chars} симв. · {date}", {
    chunks: fmt.fmtNumber(doc.chunks),
    chars: fmt.fmtNumber(doc.chars),
    date: doc.created_at ? fmt.fmtDate(doc.created_at) : "",
  });
}

onMounted(load);
</script>

<template>
  <ModalShell :open="true" size="md" @close="emit('close')">
    <template #header>
      <div>
        <div class="kb-eyebrow">{{ t('База знаний ИИ') }}</div>
        <h2 class="kb-title">{{ t('Документы для ассистента') }}</h2>
      </div>
    </template>

    <p class="kb-hint"> {{ t('Загрузите документы (PDF, Word, txt, md, csv, Excel) — ассистент будет искать по ним и опираться на них в ответах. Поддерживается русский полнотекстовый поиск.') }} </p>

    <div class="kb-upload">
      <input ref="fileInput" type="file" accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.xlsm,.json,.log" class="kb-file" />
      <input v-model="title" type="text" :placeholder="t('Название (необязательно)')" class="kb-titlein" />
      <button class="kb-up-btn" :disabled="uploading" @click="onUpload">
        {{ uploading ? t("Загрузка…") : t("Загрузить") }}
      </button>
    </div>
    <div v-if="error" class="kb-err">{{ error }}</div>

    <div class="kb-list">
      <div v-if="loading" class="kb-empty">{{ t('Загрузка…') }}</div>
      <div v-else-if="!docs.length" class="kb-empty">{{ t('База знаний пуста — загрузите первый документ.') }}</div>
      <div v-for="d in docs" :key="d.id" class="kb-row">
        <div class="kb-row-main">
          <div class="kb-row-title">{{ d.title }}</div>
          <div class="kb-row-meta">{{ formatDocMeta(d) }}</div>
        </div>
        <button class="kb-del" :title="t('Удалить')" @click="remove(d.id)">×</button>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.kb-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: rgba(15,23,60,.5); }
.kb-title { font-size: 17px; font-weight: 600; margin: 3px 0 0; color: var(--t1, #1e2a4a); }
.kb-hint { font-size: 12px; color: rgba(15,23,60,.6); line-height: 1.45; margin: 0 0 14px; }
.kb-upload { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.kb-file { font-size: 12px; }
.kb-titlein { flex: 1; min-width: 140px; padding: 7px 10px; border: 1px solid rgba(15,23,60,.14); border-radius: 8px; font-size: 12px; font-family: inherit; }
.kb-up-btn { background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff; border: none; border-radius: 9px; padding: 8px 16px; font-size: 12px; font-weight: 600; font-family: inherit; cursor: pointer; }
.kb-up-btn:disabled { opacity: .55; cursor: default; }
.kb-err { margin-top: 10px; font-size: 12px; color: #C5352F; }
.kb-list { margin-top: 16px; display: flex; flex-direction: column; gap: 6px; }
.kb-empty { font-size: 12px; color: rgba(15,23,60,.5); font-style: italic; padding: 16px 0; text-align: center; }
.kb-row { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: var(--bg2, #F7F7FB); border-radius: 10px; }
.kb-row-main { flex: 1; min-width: 0; }
.kb-row-title { font-size: 13px; font-weight: 600; color: var(--t1, #1e2a4a); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kb-row-meta { font-size: 10.5px; color: rgba(15,23,60,.55); margin-top: 2px; }
.kb-del { background: transparent; border: none; font-size: 18px; color: rgba(15,23,60,.4); cursor: pointer; padding: 0 6px; flex-shrink: 0; }
.kb-del:hover { color: #C5352F; }
</style>
