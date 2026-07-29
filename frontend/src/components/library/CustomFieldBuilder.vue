<script setup lang="ts">
/**
 * CustomFieldBuilder — modal form for creating a new custom field definition.
 * POSTs to /field-definitions. On success: refresh fieldDefs and add code
 * to the active view's visible_columns so the column appears immediately.
 */
import { ref, watch, computed } from "vue";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import ModalShell from "@/components/ModalShell.vue";
import {
  companyLibraryApi,
  type FieldType,
  type ScopeType,
} from "@/api/companyLibrary";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


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
  if (!name_ru.value.trim()) { error.value = t('Введите название'); return; }
  if (!code.value) autoCode();
  if (!validCode.value) {
    error.value = t('Код должен быть на латинице (a-z, 0-9, _), начинаться с буквы');
    return;
  }
  if (field_type.value === "enum" && !enum_values.value.trim()) {
    error.value = t('Для enum укажите значения через запятую');
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
      error.value = t('Код "{value0}" уже занят', { value0: code.value });
    } else if (e?.response?.status === 403) {
      error.value = t('Нет права library.fields.manage');
    } else {
      error.value = e?.response?.data?.detail || e?.message || t('Не удалось создать поле');
    }
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <ModalShell :open="open" size="md" @close="emit('close')">
    <template #header>
      <div>
        <div class="cl-modal-eyebrow">{{ t('Библиотека · Новая колонка') }}</div>
        <h3 class="cl-modal-title">{{ t('Создать пользовательское поле') }}</h3>
      </div>
    </template>

    <div class="cl-modal-body">
      <div class="cl-form-row">
              <label class="cl-form-label">{{ t('Название') }}</label>
              <input
                v-model="name_ru"
                @blur="autoCode"
                type="text"
                class="cl-form-input"
                :placeholder="t('Au-эквивалент, выбросы CO₂…')"
                maxlength="255"
              />
            </div>

            <div class="cl-form-row">
              <label class="cl-form-label">{{ t('Код') }} <span class="cl-form-hint">{{ t('(латиница, генерируется автоматически)') }}</span></label>
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
                <label class="cl-form-label">{{ t('Тип') }}</label>
                <select v-model="field_type" class="cl-form-input">
                  <option value="number">{{ t('Число') }}</option>
                  <option value="text">{{ t('Текст') }}</option>
                  <option value="date">{{ t('Дата') }}</option>
                  <option value="enum">{{ t('Список') }}</option>
                  <option value="boolean">{{ t('Да / Нет') }}</option>
                  <option value="formula">{{ t('Формула') }}</option>
                </select>
              </div>
              <div>
                <label class="cl-form-label">{{ t('Единица') }} <span class="cl-form-hint">{{ t('(опц.)') }}</span></label>
                <input
                  v-model="unit"
                  type="text"
                  class="cl-form-input"
                  :placeholder="t('т, %, млрд UZS')"
                  maxlength="32"
                />
              </div>
            </div>

            <div v-if="field_type === 'enum'" class="cl-form-row">
              <label class="cl-form-label">{{ t('Значения') }} <span class="cl-form-hint">{{ t('(через запятую)') }}</span></label>
              <input
                v-model="enum_values"
                type="text"
                class="cl-form-input"
                placeholder="AAA, AA+, AA, AA-, A+…"
              />
            </div>

            <div class="cl-form-row">
              <label class="cl-form-label">{{ t('Видимость') }}</label>
              <div class="cl-form-chips">
                <button
                  type="button"
                  class="cl-chip"
                  :class="{ active: scope_type === 'all' }"
                  @click="scope_type = 'all'"
                >{{ t('Все компании') }}</button>
                <button
                  type="button"
                  class="cl-chip"
                  :class="{ active: scope_type === 'sector' }"
                  @click="scope_type = 'sector'"
                >{{ t('Сектор') }}</button>
              </div>
            </div>

            <div v-if="scope_type === 'sector' && availableSectors.length" class="cl-form-row">
              <label class="cl-form-label">{{ t('Какие сектора?') }}</label>
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

    <template #footer>
      <span v-if="error" class="cl-modal-err">{{ error }}</span>
      <button class="cl-btn cl-btn-secondary" @click="emit('close')">{{ t('Отмена') }}</button>
      <button class="cl-btn cl-btn-primary" :disabled="saving || !name_ru" @click="submit">
        {{ saving ? t('Создаём…') : t('Создать колонку') }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
/* Обёртка/шапка/футер — из ModalShell (Teleport + ESC + фокус-трап + --z-top). */
.cl-modal-eyebrow { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; }
.cl-modal-title { font-size: 16px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 0 0; }

.cl-modal-body { display: flex; flex-direction: column; gap: 14px; }
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

.cl-modal-err  { font-size: 11px; color: #A82C2B; align-self: center; margin-right: auto; }
.cl-btn        { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.cl-btn-secondary { background: transparent; color: var(--t1, #1E2A4A); border-color: var(--border-hard); }
.cl-btn-secondary:hover { background: rgba(15,23,60,.04); }
.cl-btn-primary  { background: #7F77DD; color: white; }
.cl-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.cl-btn-primary:disabled { opacity: 0.6; cursor: wait; }
</style>
