<script setup lang="ts">
/**
 * Column manager — two-section modal:
 *   1) Базовые (system fields, scope=all)
 *   2) Отраслевые · {sector} (sector-scoped applicable to current sector filter)
 *
 * Each row: drag-handle (placeholder), label, toggle. Footer: "+ Создать новую колонку".
 *
 * Drag-reorder kept light-weight (mouse-down → up swap by hover) — sufficient
 * for v1; can promote to vue-draggable later if needed.
 */
import { computed, ref, watch } from "vue";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import { companyLibraryApi, type FieldDefinition } from "@/api/companyLibrary";

const props = defineProps<{ open: boolean }>();
const emit  = defineEmits<{ (e: "close"): void; (e: "open-builder"): void }>();

const store = useCompanyLibraryStore();

// Local working copies — committed only on Save
const visible    = ref<string[]>([]);
const saving     = ref(false);
const saveError  = ref<string | null>(null);

watch(() => props.open, async (open) => {
  if (open) {
    visible.value = [...store.visibleColumnCodes];
    // Make sure we have a fresh list of ALL fields (system + sector + custom)
    await store.loadAllFields(store.sectorFilter || undefined);
  }
});

const baseFields = computed<FieldDefinition[]>(() =>
  store.allFields.filter(f => f.scope_type === "all"),
);
const sectorFields = computed<FieldDefinition[]>(() =>
  store.allFields.filter(f => f.scope_type === "sector"),
);
const customFields = computed<FieldDefinition[]>(() =>
  store.allFields.filter(f => f.scope_type === "companies" || !f.is_system),
);

function isVisible(code: string) { return visible.value.includes(code); }
function toggle(code: string) {
  const i = visible.value.indexOf(code);
  if (i >= 0) visible.value.splice(i, 1);
  else        visible.value.push(code);
}

function moveUp(code: string) {
  const i = visible.value.indexOf(code);
  if (i > 0) {
    const tmp = visible.value[i - 1];
    visible.value[i - 1] = code;
    visible.value[i]     = tmp;
  }
}
function moveDown(code: string) {
  const i = visible.value.indexOf(code);
  if (i >= 0 && i < visible.value.length - 1) {
    const tmp = visible.value[i + 1];
    visible.value[i + 1] = code;
    visible.value[i]     = tmp;
  }
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  saveError.value = null;
  try {
    if (store.activeView) {
      await companyLibraryApi.updateView(store.activeView.id, {
        visible_columns: visible.value,
      });
    } else {
      // No active view — create a "Default" one
      await companyLibraryApi.createView({
        name: "Default",
        is_default: true,
        visible_columns: visible.value,
      });
    }
    await store.load();
    emit("close");
  } catch (e: any) {
    saveError.value = e?.response?.data?.detail || e?.message || "Не удалось сохранить набор колонок";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div v-if="open" class="cl-modal-back" @click.self="emit('close')">
        <div class="cl-modal-card" role="dialog" aria-modal="true">
          <header class="cl-modal-head">
            <div>
              <div class="cl-modal-eyebrow">Библиотека</div>
              <h3 class="cl-modal-title">Настройка колонок</h3>
            </div>
            <button class="cl-modal-close" @click="emit('close')">×</button>
          </header>

          <div class="cl-modal-body">
            <!-- BASIC -->
            <section class="cl-cm-section">
              <h4 class="cl-cm-section-h">Базовые · для всех</h4>
              <ul class="cl-cm-list">
                <li
                  v-for="f in baseFields"
                  :key="f.code"
                  class="cl-cm-row"
                >
                  <span class="cl-cm-drag" aria-hidden="true">⋮⋮</span>
                  <span class="cl-cm-label">
                    {{ f.name_ru }}
                    <span v-if="f.unit" class="cl-cm-unit">· {{ f.unit }}</span>
                  </span>
                  <div class="cl-cm-actions">
                    <button class="cl-cm-arrow" @click="moveUp(f.code)" title="Вверх">↑</button>
                    <button class="cl-cm-arrow" @click="moveDown(f.code)" title="Вниз">↓</button>
                    <label class="cl-cm-toggle">
                      <input type="checkbox" :checked="isVisible(f.code)" @change="toggle(f.code)" />
                      <span class="cl-cm-slider"></span>
                    </label>
                  </div>
                </li>
              </ul>
            </section>

            <!-- SECTOR-SCOPED -->
            <section v-if="sectorFields.length" class="cl-cm-section">
              <h4 class="cl-cm-section-h">
                Отраслевые<span v-if="store.sectorFilter"> · {{ store.sectorFilter }}</span>
              </h4>
              <ul class="cl-cm-list">
                <li
                  v-for="f in sectorFields"
                  :key="f.code"
                  class="cl-cm-row cl-cm-row-sector"
                >
                  <span class="cl-cm-drag" aria-hidden="true">⋮⋮</span>
                  <span class="cl-cm-label">
                    {{ f.name_ru }}
                    <span v-if="f.unit" class="cl-cm-unit">· {{ f.unit }}</span>
                  </span>
                  <label class="cl-cm-toggle">
                    <input type="checkbox" :checked="isVisible(f.code)" @change="toggle(f.code)" />
                    <span class="cl-cm-slider"></span>
                  </label>
                </li>
              </ul>
            </section>

            <!-- CUSTOM -->
            <section v-if="customFields.length" class="cl-cm-section">
              <h4 class="cl-cm-section-h">Пользовательские</h4>
              <ul class="cl-cm-list">
                <li v-for="f in customFields" :key="f.code" class="cl-cm-row cl-cm-row-custom">
                  <span class="cl-cm-drag" aria-hidden="true">⋮⋮</span>
                  <span class="cl-cm-label">
                    {{ f.name_ru }}
                    <span v-if="f.unit" class="cl-cm-unit">· {{ f.unit }}</span>
                  </span>
                  <label class="cl-cm-toggle">
                    <input type="checkbox" :checked="isVisible(f.code)" @change="toggle(f.code)" />
                    <span class="cl-cm-slider"></span>
                  </label>
                </li>
              </ul>
            </section>

            <button class="cl-cm-create" @click="emit('open-builder')">
              + Создать новую колонку
            </button>
          </div>

          <footer class="cl-modal-foot">
            <span v-if="saveError" class="cl-modal-err">{{ saveError }}</span>
            <button class="cl-btn cl-btn-secondary" @click="emit('close')">Отмена</button>
            <button class="cl-btn cl-btn-primary" :disabled="saving" @click="save">
              {{ saving ? "Сохраняем…" : "Сохранить" }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cl-modal-back {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.cl-modal-card {
  background: white;
  border-radius: 14px;
  width: 100%; max-width: 560px;
  max-height: calc(100vh - 48px);
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18), 0 8px 24px rgba(15, 23, 60, 0.08);
  animation: clModalIn .45s var(--ease-standard);
}
@keyframes clModalIn {
  0%   { opacity: 0; transform: translateY(20px) scale(0.97); }
  60%  { opacity: 1; transform: translateY(-2px) scale(1.005); }
  100% { opacity: 1; transform: translateY(0)   scale(1); }
}
.cl-modal-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  padding: 18px 20px; border-bottom: 0.5px solid #F1EFE8;
}
.cl-modal-eyebrow { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; }
.cl-modal-title { font-size: 16px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 0 0; }
.cl-modal-close { background: transparent; border: none; cursor: pointer; font-size: 24px; line-height: 1; color: var(--t3, var(--t-muted)); padding: 0 4px; }
.cl-modal-close:hover { color: var(--t1, #1E2A4A); }

.cl-modal-body { flex: 1; overflow-y: auto; padding: 16px 20px; }
.cl-cm-section + .cl-cm-section { margin-top: 16px; }
.cl-cm-section-h { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); letter-spacing: .06em; text-transform: uppercase; margin: 0 0 8px 0; }

.cl-cm-list { list-style: none; padding: 0; margin: 0; }
.cl-cm-row { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 8px; transition: background 120ms; }
.cl-cm-row:hover { background: rgba(127, 119, 221, .05); }
.cl-cm-row-sector { background: rgba(127, 119, 221, .04); }
.cl-cm-row-custom { background: rgba(250, 199, 117, .07); }
.cl-cm-drag    { color: #C8C7C0; cursor: grab; font-family: ui-monospace, Menlo, monospace; font-size: 10px; user-select: none; }
.cl-cm-label   { flex: 1; font-size: 13px; color: var(--t1, #1E2A4A); }
.cl-cm-unit    { color: var(--t3, var(--t-muted)); font-size: 11px; }
.cl-cm-actions { display: flex; align-items: center; gap: 6px; }
.cl-cm-arrow   { background: transparent; border: 1px solid transparent; cursor: pointer; padding: 0 4px; color: var(--t3, var(--t-muted)); border-radius: 4px; font-size: 12px; }
.cl-cm-arrow:hover { background: rgba(127, 119, 221, .12); color: var(--t1, #1E2A4A); }

.cl-cm-toggle  { position: relative; width: 30px; height: 16px; cursor: pointer; }
.cl-cm-toggle input { opacity: 0; width: 0; height: 0; }
.cl-cm-slider  { position: absolute; inset: 0; background: var(--border-hard); border-radius: 16px; transition: background 180ms; }
.cl-cm-slider::before { content: ""; position: absolute; left: 2px; top: 2px; width: 12px; height: 12px; background: white; border-radius: 50%; transition: transform 180ms; }
.cl-cm-toggle input:checked + .cl-cm-slider { background: #7F77DD; }
.cl-cm-toggle input:checked + .cl-cm-slider::before { transform: translateX(14px); }

.cl-cm-create  { width: 100%; margin-top: 14px; padding: 10px; background: transparent; border: 1px dashed rgba(127, 119, 221, 0.4); border-radius: 8px; color: var(--p-deep); font-size: 13px; font-weight: 500; cursor: pointer; transition: all 150ms; }
.cl-cm-create:hover { background: rgba(127, 119, 221, .06); border-color: #7F77DD; }

.cl-modal-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 0.5px solid #F1EFE8; }
.cl-modal-err  { font-size: 11px; color: #A82C2B; align-self: center; margin-right: auto; }
.cl-btn        { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.cl-btn-secondary { background: transparent; color: var(--t1, #1E2A4A); border-color: var(--border-hard); }
.cl-btn-secondary:hover { background: rgba(15,23,60,.04); }
.cl-btn-primary  { background: #7F77DD; color: white; }
.cl-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.cl-btn-primary:disabled { opacity: 0.6; cursor: wait; }

.cl-modal-enter-active { animation: clModalFade .25s ease both; }
.cl-modal-leave-active { animation: clModalFadeOut .18s ease both; }
@keyframes clModalFade   { 0% { opacity: 0; } 100% { opacity: 1; } }
@keyframes clModalFadeOut{ 0% { opacity: 1; } 100% { opacity: 0; } }
</style>
