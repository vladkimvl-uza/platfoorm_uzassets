<script setup lang="ts">
/**
 * CustomTabBuilder — Phase 3 modal for adding a new tab to the Library Detail.
 *
 * Form:
 *  • Название (text)
 *  • Layout (radio: one_col | two_col | grid)
 *  • Поля — checkboxes from all available fields
 *  • Видимость (chips: all / sector / companies)
 *
 * POSTs to /library-tabs.
 */
import { computed, ref, watch } from "vue";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import {
  companyLibraryApi,
  type TabLayout,
  type ScopeType,
} from "@/api/companyLibrary";

const props = defineProps<{ open: boolean }>();
const emit  = defineEmits<{ (e: "close"): void; (e: "created", code: string): void }>();

const store = useCompanyLibraryStore();

const code        = ref("");
const name_ru     = ref("");
const layout      = ref<TabLayout>("two_col");
const pickedFields = ref<string[]>([]);
const scope_type  = ref<ScopeType>("all");
const sectorPicked = ref<string[]>([]);

const saving = ref(false);
const error  = ref<string | null>(null);

watch(() => props.open, async (open) => {
  if (open) {
    code.value = "";
    name_ru.value = "";
    layout.value = "two_col";
    pickedFields.value = [];
    scope_type.value = "all";
    sectorPicked.value = [];
    error.value = null;
    if (store.allFields.length === 0) {
      await store.loadAllFields(store.sectorFilter || undefined);
    }
  }
});

function autoCode() {
  if (code.value) return;
  const slug = name_ru.value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .substring(0, 64);
  code.value = slug || `tab_${Math.floor(Math.random() * 100000)}`;
}

const validCode = computed(() => /^[a-z][a-z0-9_]{0,127}$/.test(code.value));

function togglePicked(c: string) {
  const i = pickedFields.value.indexOf(c);
  if (i >= 0) pickedFields.value.splice(i, 1);
  else        pickedFields.value.push(c);
}

const availableSectors = computed(() => {
  const set = new Set<string>();
  for (const f of store.allFields) {
    if (f.scope_type === "sector" && Array.isArray(f.scope_value)) {
      for (const s of f.scope_value) set.add(String(s));
    }
  }
  if (store.sectorFilter) set.add(store.sectorFilter);
  return Array.from(set);
});

const baseFields = computed(() => store.allFields.filter(f => f.scope_type === "all"));
const sectorFields = computed(() => store.allFields.filter(f => f.scope_type === "sector"));

async function submit() {
  if (saving.value) return;
  error.value = null;
  if (!name_ru.value.trim()) { error.value = "Введите название"; return; }
  if (!code.value) autoCode();
  if (!validCode.value) { error.value = "Некорректный код"; return; }
  if (pickedFields.value.length === 0) { error.value = "Выберите хотя бы одно поле"; return; }
  saving.value = true;
  try {
    await companyLibraryApi.createTab({
      code: code.value,
      name_ru: name_ru.value.trim(),
      field_codes: pickedFields.value,
      layout: layout.value,
      scope_type: scope_type.value,
      scope_value: scope_type.value === "sector" ? sectorPicked.value : null,
      sort_order: 600,
    });
    emit("created", code.value);
    emit("close");
  } catch (e: any) {
    if (e?.response?.status === 409)      error.value = `Tab "${code.value}" уже существует`;
    else if (e?.response?.status === 403) error.value = "Нет права library.tabs.manage";
    else error.value = e?.response?.data?.detail || e?.message || "Не удалось создать раздел";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="ctb-modal">
      <div v-if="open" class="ctb-back" @click.self="emit('close')">
        <div class="ctb-card">
          <header class="ctb-head">
            <div>
              <div class="ctb-eyebrow">Библиотека · Новый раздел</div>
              <h3 class="ctb-title">Создать раздел в карточке компании</h3>
            </div>
            <button class="ctb-close" @click="emit('close')">×</button>
          </header>

          <div class="ctb-body">
            <div class="ctb-row">
              <label class="ctb-label">Название</label>
              <input
                v-model="name_ru"
                @blur="autoCode"
                type="text"
                class="ctb-input"
                placeholder="Compliance, Documents, ESG детали…"
                maxlength="255"
              />
            </div>

            <div class="ctb-row">
              <label class="ctb-label">Код <span class="ctb-hint">(латиница, авто)</span></label>
              <input
                v-model="code"
                type="text"
                class="ctb-input ctb-input-mono"
                placeholder="compliance"
                maxlength="128"
              />
            </div>

            <div class="ctb-row">
              <label class="ctb-label">Расположение</label>
              <div class="ctb-chips">
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: layout === 'one_col' }"
                  @click="layout = 'one_col'"
                >Одна колонка</button>
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: layout === 'two_col' }"
                  @click="layout = 'two_col'"
                >Две колонки</button>
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: layout === 'grid' }"
                  @click="layout = 'grid'"
                >Сетка</button>
              </div>
            </div>

            <div class="ctb-row">
              <label class="ctb-label">
                Поля
                <span class="ctb-hint">· выбрано {{ pickedFields.length }}</span>
              </label>
              <div class="ctb-fields">
                <div v-if="baseFields.length" class="ctb-field-section">
                  <div class="ctb-field-section-h">Базовые</div>
                  <label
                    v-for="f in baseFields"
                    :key="f.code"
                    class="ctb-field-row"
                    :class="{ active: pickedFields.includes(f.code) }"
                  >
                    <input
                      type="checkbox"
                      :checked="pickedFields.includes(f.code)"
                      @change="togglePicked(f.code)"
                    />
                    <span>{{ f.name_ru }}</span>
                    <span v-if="f.unit" class="ctb-field-unit">{{ f.unit }}</span>
                  </label>
                </div>

                <div v-if="sectorFields.length" class="ctb-field-section">
                  <div class="ctb-field-section-h">Отраслевые</div>
                  <label
                    v-for="f in sectorFields"
                    :key="f.code"
                    class="ctb-field-row ctb-field-row-sector"
                    :class="{ active: pickedFields.includes(f.code) }"
                  >
                    <input
                      type="checkbox"
                      :checked="pickedFields.includes(f.code)"
                      @change="togglePicked(f.code)"
                    />
                    <span>{{ f.name_ru }}</span>
                    <span v-if="f.unit" class="ctb-field-unit">{{ f.unit }}</span>
                  </label>
                </div>
              </div>
            </div>

            <div class="ctb-row">
              <label class="ctb-label">Видимость</label>
              <div class="ctb-chips">
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: scope_type === 'all' }"
                  @click="scope_type = 'all'"
                >Все компании</button>
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: scope_type === 'sector' }"
                  @click="scope_type = 'sector'"
                >Сектор</button>
                <button
                  type="button"
                  class="ctb-chip"
                  :class="{ active: scope_type === 'companies' }"
                  @click="scope_type = 'companies'"
                  disabled
                  title="Скоро"
                >Список SOE</button>
              </div>
            </div>

            <div v-if="scope_type === 'sector' && availableSectors.length" class="ctb-row">
              <label class="ctb-label">Какие сектора?</label>
              <div class="ctb-chips">
                <label
                  v-for="s in availableSectors"
                  :key="s"
                  class="ctb-chip"
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

          <footer class="ctb-foot">
            <span v-if="error" class="ctb-err">{{ error }}</span>
            <button class="ctb-btn ctb-btn-secondary" @click="emit('close')">Отмена</button>
            <button class="ctb-btn ctb-btn-primary" :disabled="saving || !name_ru" @click="submit">
              {{ saving ? "Создаём…" : "Создать раздел" }}
            </button>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ctb-back {
  position: fixed; inset: 0;
  background: rgba(15,18,40,.45);
  backdrop-filter: blur(8px);
  z-index: 1001;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.ctb-card {
  background: white;
  border-radius: 14px;
  width: 100%; max-width: 560px;
  max-height: calc(100vh - 48px);
  display: flex; flex-direction: column;
  overflow: hidden;
  box-shadow: 0 24px 64px rgba(15,23,60,0.18);
  animation: ctbIn .45s cubic-bezier(0.34, 1.2, 0.64, 1);
}
@keyframes ctbIn { 0% { opacity: 0; transform: translateY(20px) scale(.97); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
.ctb-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 18px 20px; border-bottom: 0.5px solid #F1EFE8; }
.ctb-eyebrow { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, #888780); font-weight: 500; }
.ctb-title   { font-size: 16px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 0 0; }
.ctb-close   { background: transparent; border: none; cursor: pointer; font-size: 24px; line-height: 1; color: var(--t3, #888780); padding: 0 4px; }

.ctb-body { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 14px; }
.ctb-row { display: flex; flex-direction: column; gap: 5px; }
.ctb-label { font-size: 10.5px; letter-spacing: 0.04em; font-weight: 500; color: var(--t3, #888780); text-transform: uppercase; }
.ctb-hint  { text-transform: none; color: #C8C7C0; font-weight: 400; }
.ctb-input {
  border: 1px solid #E5E7EB; border-radius: 8px; padding: 8px 10px;
  font-size: 13px; color: var(--t1, #1E2A4A); outline: none; background: white;
  font-family: inherit;
}
.ctb-input:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }
.ctb-input-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 12px; }

.ctb-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ctb-chip {
  background: white; border: 1px solid #E5E7EB; color: var(--t1, #1E2A4A);
  padding: 5px 11px; border-radius: 11px; font-size: 11.5px; cursor: pointer; transition: all 150ms;
}
.ctb-chip:disabled { opacity: .55; cursor: not-allowed; }
.ctb-chip.active   { background: #7F77DD; color: white; border-color: #7F77DD; }

.ctb-fields {
  display: flex; flex-direction: column; gap: 12px;
  max-height: 260px; overflow-y: auto;
  padding: 8px; background: rgba(127,119,221,.03); border-radius: 8px;
}
.ctb-field-section-h { font-size: 10px; letter-spacing: 0.05em; text-transform: uppercase; font-weight: 600; color: var(--t3, #888780); margin-bottom: 4px; }
.ctb-field-row {
  display: flex; align-items: center; gap: 8px;
  padding: 5px 8px; border-radius: 6px;
  cursor: pointer; transition: background 120ms;
  font-size: 12px; color: var(--t1, #1E2A4A);
}
.ctb-field-row:hover { background: rgba(127,119,221,.06); }
.ctb-field-row.active { background: rgba(127,119,221,.10); }
.ctb-field-row-sector { background: rgba(127,119,221,.04); }
.ctb-field-row input { accent-color: #7F77DD; }
.ctb-field-unit { color: var(--t3, #888780); font-size: 10.5px; margin-left: auto; }

.ctb-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 0.5px solid #F1EFE8; }
.ctb-err  { font-size: 11px; color: #A82C2B; align-self: center; margin-right: auto; }
.ctb-btn  { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.ctb-btn-secondary { background: transparent; color: var(--t1, #1E2A4A); border-color: #E5E7EB; }
.ctb-btn-secondary:hover { background: rgba(15,23,60,.04); }
.ctb-btn-primary   { background: #7F77DD; color: white; }
.ctb-btn-primary:hover:not(:disabled) { background: #534AB7; }
.ctb-btn-primary:disabled { opacity: .6; cursor: wait; }

.ctb-modal-enter-active { animation: ctbFade .25s ease both; }
.ctb-modal-leave-active { animation: ctbFadeOut .18s ease both; }
@keyframes ctbFade    { 0% { opacity: 0; } 100% { opacity: 1; } }
@keyframes ctbFadeOut { 0% { opacity: 1; } 100% { opacity: 0; } }
</style>
