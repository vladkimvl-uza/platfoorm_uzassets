<script setup lang="ts">
/**
 * ForensicUploadModal — Excel-импорт plan/fact данных в /forensic.
 * UI с drag-drop + file picker + format info. POST endpoint = Phase 3.
 *
 * При выборе файла парсим preview client-side через xlsx-lib (показываем
 * первые 5 строк) и блокируем submit пока не подтвердишь.
 */
import { ref } from "vue";
import * as XLSX from "xlsx";
import { api } from "@/api/client";

const props = withDefaults(
  defineProps<{
    year?: number | null;
    /** Backend endpoint URL — default = forensic. */
    endpoint?: string;
    /** Modal heading. */
    title?: string;
    /** Sub-heading under title (format hint). */
    description?: string;
    /** Sheet name to look for in xlsx for the preview (regex). */
    sheetMatch?: RegExp | null;
    /** Format the backend response into a user-facing success line. */
    formatResult?: (data: unknown) => string;
  }>(),
  {
    endpoint:    "/forensic/import-excel",
    title:       "Импорт плана/факта закупок · Excel",
    description: "3-листовой файл: Инструкция · Компании · Данные. Скачайте шаблон ниже если ещё нет.",
    sheetMatch:  () => /данные/i,
    formatResult: () => (data: unknown) => `Загружено: ${(data as { inserted?: number })?.inserted ?? "?"} строк`,
  },
);
const emit = defineEmits<{
  (e: "close"): void;
  (e: "uploaded"): void;
}>();

const dragOver = ref(false);
const selectedFile = ref<File | null>(null);
const previewRows = ref<unknown[][]>([]);
const previewHeaders = ref<string[]>([]);
const parseError = ref<string | null>(null);
const uploading = ref(false);
const uploadResult = ref<string | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);

function onDragOver(e: DragEvent) {
  e.preventDefault();
  dragOver.value = true;
}
function onDragLeave() { dragOver.value = false; }
function onDrop(e: DragEvent) {
  e.preventDefault();
  dragOver.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) handleFile(file);
}
function onFilePick(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0];
  if (file) handleFile(file);
}
function pickFile() { fileInputRef.value?.click(); }

async function handleFile(file: File) {
  selectedFile.value = file;
  parseError.value = null;
  previewRows.value = [];
  previewHeaders.value = [];
  try {
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(buf, { type: "array" });
    // Look for the configured sheet match first; fallback to first sheet.
    const matcher = props.sheetMatch;
    const sheetName = (matcher && wb.SheetNames.find(n => matcher.test(n))) || wb.SheetNames[0];
    if (!sheetName) {
      parseError.value = "В файле нет листов.";
      return;
    }
    const sheet = wb.Sheets[sheetName!];
    const rawRows = XLSX.utils.sheet_to_json<(string | number)[]>(sheet, { header: 1 });
    // Normalize header row — trim stray leading/trailing spaces (xarid format).
    const rows: (string | number)[][] = rawRows.map((r, i) =>
      i === 0 ? r.map(c => String(c ?? "").trim()) : r,
    );
    if (!rows.length) {
      parseError.value = "Лист пуст.";
      return;
    }
    previewHeaders.value = rows[0].map(c => String(c ?? ""));
    previewRows.value = rows.slice(1, 6) as unknown[][];
  } catch (e) {
    parseError.value = (e as Error).message || "Не удалось распарсить файл.";
  }
}

async function submit() {
  if (!selectedFile.value) return;
  uploading.value = true;
  uploadResult.value = null;
  try {
    const fd = new FormData();
    fd.append("file", selectedFile.value);
    const r = await api.post(props.endpoint, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    uploadResult.value = props.formatResult(r.data);
    emit("uploaded");
    setTimeout(() => emit("close"), 1800);
  } catch (e: unknown) {
    const err = e as { response?: { status?: number; data?: { detail?: string } }; message?: string };
    if (err?.response?.status === 404) {
      uploadResult.value = `⚠ Backend-эндпоинт ${props.endpoint} не найден. Файл валиден и распарсен.`;
    } else {
      uploadResult.value = "Ошибка: " + (err?.response?.data?.detail || err?.message || "—");
    }
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <Transition name="pa-modal" appear>
    <div class="pa-modal-bg" @click.self="emit('close')">
      <div class="pa-modal-card">
        <div class="pa-mh">
          <div class="pa-mh-l">
            <div class="pa-mh-t">{{ title }}</div>
            <div class="pa-mh-s">{{ description }}</div>
          </div>
          <button class="pa-mh-x" @click="emit('close')">✕</button>
        </div>

        <div class="pa-mb">
          <!-- Drop zone -->
          <div
            class="up-drop"
            :class="{ over: dragOver, has: !!selectedFile }"
            @dragover="onDragOver"
            @dragleave="onDragLeave"
            @drop="onDrop"
            @click="pickFile"
          >
            <input
              ref="fileInputRef"
              type="file"
              accept=".xlsx,.xls"
              style="display:none"
              @change="onFilePick"
            />
            <template v-if="!selectedFile">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#7F77DD" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
              <div class="up-drop-t">Перетащите Excel-файл сюда</div>
              <div class="up-drop-s">или кликните чтобы выбрать (.xlsx / .xls)</div>
            </template>
            <template v-else>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#1D9E75" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <polyline points="9 15 11 17 15 13"/>
              </svg>
              <div class="up-drop-t">{{ selectedFile.name }}</div>
              <div class="up-drop-s">{{ (selectedFile.size / 1024).toFixed(0) }} KB · клик чтобы заменить</div>
            </template>
          </div>

          <div v-if="parseError" class="up-err">⚠ {{ parseError }}</div>

          <!-- Preview -->
          <div v-if="previewHeaders.length && !parseError" class="up-preview">
            <div class="up-prev-h">
              Предпросмотр · первые {{ previewRows.length }} {{ previewRows.length === 1 ? 'строка' : 'строк' }}
            </div>
            <div class="up-prev-wrap">
              <table class="up-prev-tbl">
                <thead>
                  <tr>
                    <th v-for="(h, i) in previewHeaders.slice(0, 8)" :key="i">{{ h || `col ${i + 1}` }}</th>
                    <th v-if="previewHeaders.length > 8" class="muted">+{{ previewHeaders.length - 8 }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, i) in previewRows" :key="i">
                    <td v-for="(cell, ci) in (row as unknown[]).slice(0, 8)" :key="ci">
                      {{ cell ?? '—' }}
                    </td>
                    <td v-if="previewHeaders.length > 8" class="muted">…</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="uploadResult" class="up-result" :class="{ err: uploadResult.startsWith('⚠') || uploadResult.startsWith('Ошибка') }">
            {{ uploadResult }}
          </div>
        </div>

        <div class="pa-mf">
          <div class="pa-mf-meta">
            <span v-if="!selectedFile">Выберите файл</span>
            <span v-else-if="parseError">Файл невалиден</span>
            <span v-else-if="!uploadResult">Готов к загрузке</span>
          </div>
          <div class="pa-mf-actions">
            <button class="pa-mf-btn" @click="emit('close')">Отмена</button>
            <button
              class="pa-mf-btn primary"
              :disabled="!selectedFile || !!parseError || uploading"
              @click="submit"
            >
              {{ uploading ? 'Загрузка…' : 'Загрузить' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.pa-modal-bg {
  position: fixed; inset: 0;
  background: rgba(0, 0, 0, .35);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
  z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.pa-modal-card {
  background: #fff;
  border-radius: 16px;
  border: 1px solid rgba(0, 0, 0, .08);
  box-shadow: 0 24px 64px rgba(0, 0, 0, .22);
  width: 680px; max-width: 100%;
  max-height: 88vh;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.pa-mh {
  padding: 16px 22px;
  border-bottom: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
}
.pa-mh-l { min-width: 0; flex: 1; }
.pa-mh-t { font-size: 15px; font-weight: 600; color: #1E2A4A; }
.pa-mh-s { font-size: 11.5px; color: #888780; margin-top: 4px; }
.pa-mh-x {
  border: 0; background: #F4F3F9;
  width: 30px; height: 30px; border-radius: 8px;
  cursor: pointer; font-size: 14px; color: #888780;
  flex-shrink: 0;
}
.pa-mh-x:hover { background: rgba(226, 75, 74, .12); color: #A32D2D; }

.pa-mb { flex: 1; overflow-y: auto; padding: 16px 22px; }

.up-drop {
  border: 2px dashed rgba(127, 119, 221, .35);
  border-radius: 12px;
  padding: 32px 20px;
  text-align: center;
  cursor: pointer;
  background: #FAFAFC;
  transition: all .15s;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}
.up-drop:hover, .up-drop.over {
  border-color: #7F77DD;
  background: rgba(127, 119, 221, .06);
}
.up-drop.has {
  border-style: solid;
  border-color: #1D9E75;
  background: rgba(29, 158, 117, .04);
}
.up-drop-t { font-size: 14px; font-weight: 600; color: #1E2A4A; }
.up-drop-s { font-size: 11.5px; color: #888780; }

.up-err {
  margin-top: 12px;
  padding: 10px 14px;
  background: rgba(226, 75, 74, .08);
  border-left: 3px solid #E24B4A;
  border-radius: 6px;
  color: #A32D2D;
  font-size: 12px;
}

.up-preview {
  margin-top: 16px;
  background: #fff;
  border: 1px solid rgba(0, 0, 0, .06);
  border-radius: 8px;
  overflow: hidden;
}
.up-prev-h {
  padding: 8px 14px;
  font-size: 11px; font-weight: 600;
  color: #888780;
  text-transform: uppercase; letter-spacing: .04em;
  border-bottom: 1px solid rgba(0, 0, 0, .04);
  background: #FAFAFC;
}
.up-prev-wrap { overflow-x: auto; max-height: 220px; overflow-y: auto; }
.up-prev-tbl { width: 100%; border-collapse: collapse; font-size: 11px; }
.up-prev-tbl thead th {
  padding: 6px 10px;
  background: #FAFAFA;
  font-size: 10px; font-weight: 600;
  color: #888780;
  text-align: left;
  white-space: nowrap;
  border-bottom: 0.5px solid rgba(0, 0, 0, .06);
}
.up-prev-tbl tbody td {
  padding: 6px 10px;
  border-bottom: 0.5px solid rgba(0, 0, 0, .03);
  color: #1E2A4A;
  font-feature-settings: "tnum";
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden; text-overflow: ellipsis;
}
.up-prev-tbl .muted { color: #888780; font-style: italic; }

.up-result {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 12px;
  background: rgba(29, 158, 117, .08);
  border-left: 3px solid #1D9E75;
  color: #0F6E56;
}
.up-result.err {
  background: rgba(239, 159, 39, .08);
  border-left-color: #EF9F27;
  color: #B07415;
}

.pa-mf {
  padding: 12px 22px;
  border-top: 1px solid rgba(0, 0, 0, .06);
  display: flex; align-items: center; justify-content: space-between;
  background: #FAFAFC;
}
.pa-mf-meta { font-size: 11px; color: #888780; }
.pa-mf-actions { display: flex; gap: 8px; }
.pa-mf-btn {
  font-size: 12px; font-weight: 500;
  padding: 7px 14px;
  border-radius: 7px;
  border: 1px solid rgba(15, 23, 60, .12);
  background: #fff;
  color: #1E2A4A;
  cursor: pointer;
  font-family: inherit;
}
.pa-mf-btn:hover:not(:disabled) { background: #F4F3F9; }
.pa-mf-btn.primary { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.pa-mf-btn.primary:hover:not(:disabled) { background: #6F66D0; }
.pa-mf-btn:disabled { opacity: .4; cursor: not-allowed; }

.pa-modal-enter-active, .pa-modal-leave-active { transition: opacity .2s; }
.pa-modal-enter-active .pa-modal-card,
.pa-modal-leave-active .pa-modal-card { transition: transform .2s, opacity .2s; }
.pa-modal-enter-from .pa-modal-card,
.pa-modal-leave-to .pa-modal-card { transform: scale(.96); opacity: 0; }
.pa-modal-enter-from, .pa-modal-leave-to { opacity: 0; }
</style>
