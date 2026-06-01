<script setup lang="ts">
/**
 * InlineCell — universal editable cell for the library table.
 *
 * Renders display mode by default. Double-click / Enter → edit mode.
 * Save on blur / Enter. Cancel on Esc. Rollback on backend error.
 *
 * Read-only cells (formula type, or user lacks edit permission, or
 * source_module is set but not directly editable here) show with
 * cursor: not-allowed and no edit affordance.
 */
import { computed, nextTick, ref } from "vue";
import { useCompanyLibraryStore } from "@/stores/companyLibrary";
import { useFormatters } from "@/composables/useFormatters";
import type { FieldDefinition } from "@/api/companyLibrary";
import SyncIndicator from "./SyncIndicator.vue";

const fmt = useFormatters();

const props = defineProps<{
  companyId: string;
  fieldCode: string;
  fieldDef: FieldDefinition;
  value: any;
  /** if true, cell never enters edit mode (overrides editability heuristics) */
  readonly?: boolean;
}>();

const emit = defineEmits<{
  (e: "saved", value: any): void;
  (e: "error", err: any): void;
}>();

const store = useCompanyLibraryStore();
const editing = ref(false);
const saving  = ref(false);
const draft   = ref<any>("");
const inputEl = ref<HTMLInputElement | HTMLSelectElement | null>(null);

const isReadonly = computed(() => {
  if (props.readonly) return true;
  // formula → always read-only
  if (props.fieldDef.field_type === "formula") return true;
  // sector enum is currently managed via Company.sector_id, not editable inline
  if (props.fieldDef.code === "sector") return true;
  // boolean — TODO checkbox; for now allow but render as text
  return false;
});

const displayValue = computed(() => {
  // Reading fmt.locale.value here makes the computed reactive to locale switch.
  void fmt.locale;
  const v = props.value;
  if (v === null || v === undefined || v === "") return "—";
  if (props.fieldDef.field_type === "number") {
    const n = typeof v === "number" ? v : parseFloat(String(v));
    if (Number.isNaN(n)) return String(v);
    const abs = Math.abs(n);
    // Auto-scale big numbers via locale-aware compact formatter
    const formatted = abs >= 1e4
      ? fmt.fmtNumberCompact(n, { decimals: abs >= 1e6 ? 2 : 0 })
      : fmt.fmtNumber(n, { decimals: abs % 1 === 0 ? 0 : 2 });
    return props.fieldDef.unit ? `${formatted} ${props.fieldDef.unit}` : formatted;
  }
  if (props.fieldDef.field_type === "date") {
    return fmt.fmtDateNumeric(String(v));
  }
  if (props.fieldDef.field_type === "boolean") {
    return v ? "✓" : "—";
  }
  return String(v);
});

const isNumeric = computed(() => props.fieldDef.field_type === "number");

async function startEdit() {
  if (isReadonly.value) return;
  draft.value = props.value ?? "";
  editing.value = true;
  await nextTick();
  inputEl.value?.focus();
  if (inputEl.value instanceof HTMLInputElement) inputEl.value.select();
}

function cancelEdit() {
  editing.value = false;
  draft.value = "";
}

async function commit() {
  if (!editing.value || saving.value) return;
  let newValue: any = draft.value;
  if (props.fieldDef.field_type === "number") {
    if (newValue === "" || newValue === null) {
      newValue = null;
    } else {
      const n = typeof newValue === "number" ? newValue : parseFloat(String(newValue).replace(",", "."));
      if (Number.isNaN(n)) {
        cancelEdit();
        return;
      }
      newValue = n;
    }
  } else if (props.fieldDef.field_type === "boolean") {
    newValue = !!newValue;
  } else if (newValue === "") {
    newValue = null;
  }

  // No-op if unchanged
  if (JSON.stringify(newValue) === JSON.stringify(props.value)) {
    cancelEdit();
    return;
  }

  saving.value = true;
  try {
    await store.updateField(props.companyId, props.fieldCode, newValue);
    editing.value = false;
    emit("saved", newValue);
  } catch (e: any) {
    emit("error", e);
  } finally {
    saving.value = false;
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter")  { e.preventDefault(); commit(); }
  if (e.key === "Escape") { e.preventDefault(); cancelEdit(); }
}
</script>

<template>
  <div
    class="cl-cell"
    :class="{
      'cl-cell-numeric':  isNumeric,
      'cl-cell-readonly': isReadonly,
      'cl-cell-editing':  editing,
      'cl-cell-saving':   saving,
    }"
    @dblclick="startEdit"
  >
    <template v-if="!editing">
      <span class="cl-cell-value" @click="startEdit">{{ displayValue }}</span>
      <SyncIndicator
        v-if="fieldDef.source_module !== undefined"
        class="cl-cell-dot"
        :source-module="fieldDef.source_module"
        :size="5"
      />
    </template>

    <!-- Edit mode -->
    <template v-else>
      <!-- Enum dropdown -->
      <select
        v-if="fieldDef.field_type === 'enum' && fieldDef.enum_values"
        ref="inputEl"
        v-model="draft"
        class="cl-cell-input cl-cell-select"
        :disabled="saving"
        @blur="commit"
        @keydown="onKey"
      >
        <option value="">—</option>
        <option v-for="v in fieldDef.enum_values" :key="v" :value="v">{{ v }}</option>
      </select>

      <!-- Date picker -->
      <input
        v-else-if="fieldDef.field_type === 'date'"
        ref="inputEl"
        v-model="draft"
        type="date"
        class="cl-cell-input"
        :disabled="saving"
        @blur="commit"
        @keydown="onKey"
      />

      <!-- Boolean -->
      <input
        v-else-if="fieldDef.field_type === 'boolean'"
        ref="inputEl"
        v-model="draft"
        type="checkbox"
        class="cl-cell-checkbox"
        :disabled="saving"
        @change="commit"
        @keydown="onKey"
      />

      <!-- Number or text -->
      <input
        v-else
        ref="inputEl"
        v-model="draft"
        :type="isNumeric ? 'text' : 'text'"
        :inputmode="isNumeric ? 'decimal' : 'text'"
        class="cl-cell-input"
        :class="{ 'cl-cell-input-num': isNumeric }"
        :disabled="saving"
        @blur="commit"
        @keydown="onKey"
      />
    </template>
  </div>
</template>

<style scoped>
.cl-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
  cursor: text;
  min-height: 26px;
  width: 100%;
  transition: background 120ms;
  position: relative;
}
.cl-cell:hover { background: rgba(127, 119, 221, 0.05); }
.cl-cell-numeric  { justify-content: flex-end; text-align: right; }
.cl-cell-readonly { cursor: not-allowed; }
.cl-cell-readonly:hover { background: transparent; }
.cl-cell-editing  { background: rgba(127, 119, 221, 0.10); cursor: text; }
.cl-cell-saving   { opacity: 0.65; pointer-events: none; }
.cl-cell-value {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cl-cell-numeric .cl-cell-value { text-align: right; }
.cl-cell-dot { margin-left: 2px; }

.cl-cell-input {
  border: 1px solid rgba(127, 119, 221, 0.4);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: inherit;
  font-family: inherit;
  font-variant-numeric: tabular-nums;
  background: white;
  color: var(--t1, #1E2A4A);
  width: 100%;
  outline: none;
}
.cl-cell-input:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, 0.15); }
.cl-cell-input-num   { text-align: right; }
.cl-cell-select      { padding: 1px 4px; }
.cl-cell-checkbox    { transform: scale(1.2); margin: 0 4px; }
</style>
