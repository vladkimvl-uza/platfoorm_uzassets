<script setup lang="ts">
/**
 * KnowledgeBaseModal — управление базой знаний ИИ (RAG).
 * Owner/admin загружает документы (txt/md/csv/xlsx), ассистент ищет по ним
 * инструментом search_knowledge_base. Поиск — Postgres FTS.
 */
import { ref, onMounted } from "vue";
import { api } from "@/api/client";

const emit = defineEmits<{ (e: "close"): void }>();

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
    error.value = e?.response?.data?.detail || "Не удалось загрузить список";
  } finally { loading.value = false; }
}

async function onUpload() {
  const f = fileInput.value?.files?.[0];
  if (!f) { error.value = "Выберите файл"; return; }
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
    error.value = e?.response?.data?.detail || "Ошибка загрузки файла";
  } finally { uploading.value = false; }
}

async function remove(id: string) {
  try { await api.delete(`/knowledge/${id}`); docs.value = docs.value.filter((d) => d.id !== id); }
  catch { /* ignore */ }
}

function fmtDate(s: string | null): string {
  if (!s) return "";
  try { return new Date(s).toLocaleDateString("ru-RU"); } catch { return ""; }
}

onMounted(load);
</script>

<template>
  <div class="kb-back" @click.self="emit('close')" role="dialog" aria-modal="true">
    <div class="kb-card">
      <header class="kb-hd">
        <div>
          <div class="kb-eyebrow">База знаний ИИ</div>
          <h2 class="kb-title">Документы для ассистента</h2>
        </div>
        <button class="kb-x" @click="emit('close')" aria-label="Закрыть">×</button>
      </header>

      <div class="kb-body">
        <p class="kb-hint">
          Загрузите документы (txt, md, csv, xlsx) — ассистент будет искать по ним и
          опираться на них в ответах. Поддерживается русский полнотекстовый поиск.
        </p>

        <div class="kb-upload">
          <input ref="fileInput" type="file" accept=".txt,.md,.csv,.xlsx,.xlsm,.json,.log" class="kb-file" />
          <input v-model="title" type="text" placeholder="Название (необязательно)" class="kb-titlein" />
          <button class="kb-up-btn" :disabled="uploading" @click="onUpload">
            {{ uploading ? "Загрузка…" : "Загрузить" }}
          </button>
        </div>
        <div v-if="error" class="kb-err">{{ error }}</div>

        <div class="kb-list">
          <div v-if="loading" class="kb-empty">Загрузка…</div>
          <div v-else-if="!docs.length" class="kb-empty">База знаний пуста — загрузите первый документ.</div>
          <div v-for="d in docs" :key="d.id" class="kb-row">
            <div class="kb-row-main">
              <div class="kb-row-title">{{ d.title }}</div>
              <div class="kb-row-meta">{{ d.chunks }} фрагм. · {{ d.chars.toLocaleString('ru-RU') }} симв. · {{ fmtDate(d.created_at) }}</div>
            </div>
            <button class="kb-del" title="Удалить" @click="remove(d.id)">×</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kb-back { position: fixed; inset: 0; z-index: 9500; background: rgba(20,16,40,.5); backdrop-filter: blur(5px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.kb-card { width: min(640px, 96vw); max-height: 88vh; overflow-y: auto; background: var(--bg1, #fff); border-radius: 16px; box-shadow: 0 30px 70px -15px rgba(30,20,70,.5); font-family: Geist, system-ui, sans-serif; }
.kb-hd { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px 14px; border-bottom: 1px solid rgba(15,23,60,.07); }
.kb-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: rgba(15,23,60,.5); }
.kb-title { font-size: 17px; font-weight: 600; margin: 3px 0 0; color: var(--t1, #1e2a4a); }
.kb-x { background: transparent; border: none; font-size: 22px; color: rgba(15,23,60,.45); cursor: pointer; padding: 0 6px; }
.kb-body { padding: 16px 22px 22px; }
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
