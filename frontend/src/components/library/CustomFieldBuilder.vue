<script setup lang="ts">
/**
 * CustomFieldBuilder — modal form for creating a new custom field definition.
 * POSTs to /field-definitions. On success: refresh fieldDefs and add code
 * to the active view's visible_columns so the column appears immediately.
 */
import { ref, watch, computed } from "vue";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import {
  companyLibraryApi,
  type FieldType,
  type ScopeType,
} from "@/api/companyLibrary";

const props = defineProps<{ open: boolean }>();
const emit  = defineEmits<{ (e: "close"): void; (e: "created", code: string): void }>();

const store = useCompanyLibraryStore();

// Form state
const code        = ref("");
const name_ru     = ref("");
const field_type  = ref<FieldType>("number");
const unit        = ref("");
const scope_type  = ref<ScopeType>("all");
const sectorPicked = ref<string[]>([]);
const enum_values  = ref<string>(""); // comma-separated, parsed on submit

const saving = ref(false);
const error  = ref<string | null>(null);

watch(() => props.open, (open) => {
  if (open) {
    code.value = "";
    name_ru.value = "";
    field_type.value = "number";
    unit.value = "";
    scope_type.value = "all";
    sectorPicked.value = [];
    enum_values.value = "";
    error.value = null;
  }
});

// Auto-derive code from name (lowercase, latin-only stub)
function autoCode() {
  if (code.value) return;
  const slug = name_ru.value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .substring(0, 64);
  // Fallback for cyrillic-only names — just use 'field_<random>'
  if (!slug) {
    code.value = `field_${Math.floor(Math.random() * 100000)}`;
  } else {
    code.value = slug.startsWith("_") ? slug.replace(/^_+/, "") : slug;
  }
}

const validCode = computed(() => /^[a-z][a-z0-9_]{0,127}$/.test(code.value));

const availableSectors = computed(() => {
  // We don't have a separate sectors API client here, so list whatever sectors
  // we've already loaded via fields' scope_value
  const set = new Set<string>();
  for (const f of store.allFields) {
    if (f.scope_type === "sector" && Array.isArray(f.scope_value)) {
      for (const s of f.scope_value) set.add(String(s));
    }
  }
  // Add the currently-filtered sector if any
  if (store.sectorFilter) set.add(store.sectorFilter);
  return Array.from(set);
});

async function submit() {
  if (saving.value) return;
  error.value = null;
  if (!name_ru.value.trim()) { error.value = "Введите название"; return; }
  if (!code.value) autoCode();
  if (!validCode.value) {
    error.value = "Код должен быть на латинице (a-z, 0-9, _), начинаться с буквы";
    return;
  }
  if (field_type.value === "enum" && !enum_values.value.trim()) {
    error.value = "Для enum укажите значения через запятую";
    return;
  }
  saving.value = true;
  try {
    const payload = {
      code: code.value,
      name_ru: name_ru.value.trim(),
      field_type: field_type.value,
      unit: unit.value.trim() || null,
      scope_type: scope_type.value,
      scope_value: scope_type.value === "sector" ? sectorPicked.value : null,
      enum_values: field_type.value === "enum"
        ? enum_values.value.split(",").map(s => s.trim()).filter(Boolean)
        : null,
      sort_order: 600,
    };
    await companyLibraryApi.createField(payload);
    await store.loadAllFields(store.sectorFilter || undefined);
    // Auto-add to active view
    if (store.activeView) {
      const nextCols = [...store.activeView.visible_columns, code.value];
      await companyLibraryApi.updateView(store.activeView.id, { visible_columns: nextCols });
    }
    await store.load();
    emit("created", code.value);
    emit("close");
  } catch (e: any) {
    if (e?.response?.status === 409) {
      error.value = `Код "${code.value}" уже занят`;
    } else if (e?.response?.status === 403) {
      error.value = "Нет права library.fields.manage";
    } else {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось создать поле";
    }
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="uza-fade">
      <div v-if="open" class="cl-modal-back" @click.self="emit('close')">
        <div class="cl-modal-card cl-modal-card-narrow">
          <header class="cl-modal-head">
            <div>
              <div class="cl-modal-eyebrow">Библиотека · Новая колонка</div>
              <h3 class="cl-modal-title">Создать пользовательское поле</h3>
            </div>
            <button class="cl-modal-close" @click="emit('close')">×</button>
          </header>

          <div class="cl-modal-body">
            <div class="cl-form-row">
              <label class="cl-form-label">Название</label>
              <input
                v-model="name_ru"
                @blur="autoCode"
                type="text"
                class="cl-form-input"
                placeholder="Au-эквивалент, выбросы CO₂…"
                maxlength="255"
              />
            </div>

            <div class="cl-form-row">
              <label class="cl-form-label">Код <span class="cl-form-hint">(латиница, генерируется автоматически)</span></label>
              <input
                v-model="code"
                type="text"
                class="cl-form-input cl-form-input-mono"
                placeholder="au_equivalent"
                maxlength="128"
              />
            </div>

            <div class="cl-form-row cl-form-row-2col">
              <div>
                <label class="cl-form-label">Тип</label>
                <select v-model="field_type" class="cl-form-input">
                  <option value="number">Число</option>
                  <option value="text">Текст</option>
                  <option value="date">Дата</option>
                  <option value="enum">Список</option>
                  <option value="boolean">Да / Нет</option>
                  <option value="formula">Формула</option>
                </select>
              </div>
              <div>
                <label class="cl-form-label">Единица <span class="cl-form-hint">(опц.)</span></label>
                <input
                  v-model="unit"
                  type="text"
                  class="cl-form-input"
                  placeholder="т, %, млрд UZS"
                  maxlength="32"
                />
              </div>
            </div>

            <div v-if="field_type === 'enum'" class="cl-form-row">
              <label class="cl-form-label">Значения <span class="cl-form-hint">(через запятую)</span></label>
              <input
                v-model="enum_values"
                type="text"
                class="cl-form-input"
                placeholder="AAA, AA+, AA, AA-, A+…"
              />
            </div>

            <div class="cl-form-row">
              <label class="cl-form-label">Видимость</label>
              <div class="cl-form-chips">
                <button
                  type="button"
                  class="cl-chip"
                  :class="{ active: scope_type === 'all' }"
                  @click="scope_type = 'all'"
                >Все компании</button>
                <button
                  type="button"
                  class="cl-chip"
                  :class="{ active: scope_type === 'sector' }"
                  @click="scope_type = 'sector'"
                >Сектор</button>
                <button
                  type="button"
                  class="cl-chip"
                  :class="{ active: scope_type === 'companies' }"
                  @click="scope_type = 'companies'"
                  disabled
                  title="Скоро"
                >Список SOE</button>
              </div>
            </div>

            <div v-if="scope_type === 'sector' && availableSectors.length" class="cl-form-row">
              <label class="cl-form-label">Какие сектора?</label>
              <div class="cl-form-chips">
                <label
                  v-for="s in availableSectors"
                  :key="s"
                  class="cl-chip cl-chip-check"
                  :class="{ active: sectorPicked.includes(s) }"
                >
                  <input
                    type="checkbox"
                    :value="s"
                    :checked="sectorPicked.includes(s)"
                    @change="(e: any) => {
                      if (e.target.checked) sectorPicked.push(s);
                      else sectorPicked = sectorPicked.filter(x => x !== s);
                    }"
                    hidden
                  />
                  {{ s }}
                </label>
              </div>
            </div>
          </div>

          <footer class="cl-modal-foot">
            <span v-if="error" class="cl-modal-err">{{ error }}</span>
            <button class="cl-btn cl-btn-secondary" @click="emit('close')">Отмена</button>
            <button class="cl-btn cl-btn-primary" :disabled="saving || !name_ru" @click="submit">
              {{ saving ? "Создаём…" : "Создать колонку" }}
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
  z-index: 1001;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.cl-modal-card {
  background: white;
  border-radius: 14px;
  width: 100%; max-width: 480px;
  max-height: calc(100vh - 48px);
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15, 23, 60, 0.18);
  animation: clModalIn .45s var(--ease-standard);
}
.cl-modal-card-narrow { max-width: 480px; }
@keyframes clModalIn {
  0%   { opacity: 0; transform: translateY(20px) scale(.97); }
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

.cl-modal-body { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }
.cl-form-row { display: flex; flex-direction: column; gap: 5px; }
.cl-form-row-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.cl-form-row-2col > div { display: flex; flex-direction: column; gap: 5px; }
.cl-form-label { font-size: 10.5px; letter-spacing: 0.04em; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; }
.cl-form-hint  { text-transform: none; color: #C8C7C0; font-weight: 400; }
.cl-form-input {
  border: 1px solid var(--border-hard); border-radius: 8px; padding: 8px 10px;
  font-size: 13px; color: var(--t1, #1E2A4A); outline: none; background: white;
  font-family: inherit;
}
.cl-form-input:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.cl-form-input-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; }
.cl-form-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.cl-chip {
  background: white; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A);
  padding: 5px 11px; border-radius: 11px; font-size: 11.5px;
  cursor: pointer; transition: all 150ms;
}
.cl-chip:disabled  { opacity: 0.55; cursor: not-allowed; }
.cl-chip.active    { background: #7F77DD; color: white; border-color: #7F77DD; }
.cl-chip-check     { cursor: pointer; }

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
@keyframes clModalFade    { 0% { opacity: 0; } 100% { opacity: 1; } }
@keyframes clModalFadeOut { 0% { opacity: 1; } 100% { opacity: 0; } }
</style>
