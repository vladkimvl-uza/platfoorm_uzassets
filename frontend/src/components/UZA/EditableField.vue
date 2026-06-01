<script setup lang="ts">
/**
 * EditableField.vue
 * ─────────────────────────────────────────────────────────────────
 * Универсальный компонент inline-редактирования одного поля.
 *
 * Поведение для админа:
 *   • Hover на значении → появляется pencil-иконка
 *   • Клик на значении или pencil → переход в edit mode (input/textarea)
 *   • Enter → save  ·  Esc → cancel  ·  blur → save
 *   • Во время save: тонкий спиннер, поле disabled
 *   • Success: краткая teal-вспышка ✓
 *   • Error: красная нижняя кайма + tooltip с текстом ошибки
 *
 * Для не-админа: только display, никаких affordances.
 *
 * Pack 7.29: применяется в CompanyDrillModal, рассчитан на все будущие
 * модалки где админ правит scope-данные in-place.
 */
import { computed, ref, nextTick } from "vue";
import { useInlineEdit } from "@/composables/useInlineEdit";

type FieldType = "text" | "number" | "year" | "url" | "textarea" | "email";

interface Props {
  modelValue: string | number | null | undefined;
  saveFn: (value: string | number | null) => Promise<void>;
  editable?: boolean;
  type?: FieldType;
  placeholder?: string;
  hint?: string;
  align?: "left" | "right";
  validate?: (v: string | number | null) => string | null;
  displayFormat?: (v: string | number | null | undefined) => string;
  inputMinWidth?: string;
  maxlength?: number;
  fontSize?: string;
}

const props = withDefaults(defineProps<Props>(), {
  editable: false,
  type: "text",
  placeholder: "Не задано",
  align: "left",
  inputMinWidth: "140px",
  maxlength: 255,
  fontSize: "11.5px",
});

const emit = defineEmits<{
  "update:modelValue": [value: string | number | null];
  saved: [value: string | number | null];
}>();

const inputEl = ref<HTMLInputElement | HTMLTextAreaElement | null>(null);

const currentVal = computed<string | number | null>(() =>
  props.modelValue === undefined ? null : (props.modelValue as string | number | null),
);

const {
  draft,
  errorMsg,
  editing,
  saving,
  isError,
  isSuccess,
  start,
  cancel,
  save,
} = useInlineEdit<string | number | null>({
  value: currentVal,
  validate: (v) => {
    if (props.validate) return props.validate(v) ?? null;
    if (props.type === "year" && v !== null && v !== "") {
      const n = Number(v);
      const cy = new Date().getFullYear();
      if (!Number.isFinite(n) || n < 1800 || n > cy + 5) {
        return `Год должен быть в диапазоне 1800–${cy + 5}`;
      }
    }
    if (props.type === "number" && v !== null && v !== "") {
      const n = Number(v);
      if (!Number.isFinite(n) || n < 0) return "Должно быть неотрицательное число";
    }
    if (props.type === "url" && v && typeof v === "string") {
      const s = v.trim();
      if (s && !/^https?:\/\//i.test(s) && !/^[\w-]+(\.[\w-]+)+/.test(s)) {
        return "Введите корректный URL (https://… или domain.tld)";
      }
    }
    return null;
  },
  saveFn: async (v) => {
    const normalised: string | number | null =
      (props.type === "number" || props.type === "year")
        ? (v === "" || v === null ? null : Number(v))
        : (typeof v === "string" ? v.trim() : v);
    await props.saveFn(normalised);
    emit("update:modelValue", normalised);
    emit("saved", normalised);
  },
});

async function startEdit() {
  if (!props.editable) return;
  start();
  await nextTick();
  inputEl.value?.focus();
  if (inputEl.value && "select" in inputEl.value && props.type !== "textarea") {
    (inputEl.value as HTMLInputElement).select?.();
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === "Enter" && props.type !== "textarea") {
    e.preventDefault();
    void save();
  } else if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && props.type === "textarea") {
    e.preventDefault();
    void save();
  } else if (e.key === "Escape") {
    e.preventDefault();
    cancel();
  }
}

let saveLock = false;
async function onBlur() {
  if (saveLock) return;
  saveLock = true;
  await save();
  setTimeout(() => { saveLock = false; }, 60);
}

const displayText = computed(() => {
  if (props.displayFormat) return props.displayFormat(props.modelValue);
  const v = props.modelValue;
  if (v === null || v === undefined || v === "") return "";
  return String(v);
});

const isEmpty = computed(() => {
  const v = props.modelValue;
  return v === null || v === undefined || v === "";
});

const inputType = computed(() => {
  if (props.type === "number" || props.type === "year") return "number";
  if (props.type === "url") return "url";
  if (props.type === "email") return "email";
  return "text";
});
</script>

<template>
  <span
    class="ef"
    :class="{
      'ef--editable': editable && !editing,
      'ef--editing': editing,
      'ef--saving': saving,
      'ef--success': isSuccess,
      'ef--error': isError,
      'ef--empty': isEmpty,
      'ef--right': align === 'right',
    }"
    :title="isError ? (errorMsg || '') : (editable && !editing ? (hint || 'Нажмите для редактирования') : '')"
  >
    <span v-if="!editing" class="ef-val" @click="startEdit">
      <slot name="display" :value="modelValue" :empty="isEmpty" :text="displayText">
        <template v-if="isEmpty">
          <span class="ef-placeholder">{{ placeholder }}</span>
        </template>
        <template v-else>{{ displayText }}</template>
      </slot>
      <span v-if="editable" class="ef-pencil" aria-hidden="true">
        <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8.5 1.5l2 2L4 10H2v-2z"/>
        </svg>
      </span>
      <span v-if="isSuccess" class="ef-check" aria-hidden="true">
        <svg viewBox="0 0 12 12" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2.5 6.5l2.5 2.5 4.5-5"/>
        </svg>
      </span>
    </span>

    <template v-else>
      <textarea
        v-if="type === 'textarea'"
        ref="inputEl"
        v-model="draft"
        :disabled="saving"
        :maxlength="maxlength"
        class="ef-input ef-textarea"
        :style="{ minWidth: inputMinWidth, fontSize: fontSize }"
        @keydown="onKey"
        @blur="onBlur"
        rows="3"
      />
      <input
        v-else
        ref="inputEl"
        v-model="draft"
        :type="inputType"
        :disabled="saving"
        :maxlength="maxlength"
        :min="type === 'year' ? 1800 : (type === 'number' ? 0 : undefined)"
        :max="type === 'year' ? (new Date().getFullYear() + 5) : undefined"
        class="ef-input"
        :style="{ minWidth: inputMinWidth, fontSize: fontSize }"
        @keydown="onKey"
        @blur="onBlur"
      />
      <span v-if="saving" class="ef-spin" aria-hidden="true">
        <svg viewBox="0 0 14 14" width="11" height="11" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
          <path d="M7 1.5a5.5 5.5 0 1 1-3.9 1.6"/>
        </svg>
      </span>
    </template>
  </span>
</template>

<style scoped>
.ef {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-feature-settings: "tnum";
  min-width: 0;
  max-width: 100%;
}
.ef--right { justify-content: flex-end; }

.ef-val {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  line-height: 1.35;
  border-radius: 4px;
  padding: 1px 3px;
  margin: -1px -3px;
  transition: background 0.15s, color 0.15s;
  cursor: default;
  min-width: 0;
}
.ef--editable .ef-val { cursor: text; }
.ef--editable .ef-val:hover {
  background: rgba(127,119,221,0.06);
}
.ef--success .ef-val { color: #0F6E56; }
.ef--error .ef-val { color: #A32D2D; border-bottom: 1px solid #E24B4A; }

.ef-placeholder {
  color: #B4B2A9;
  font-weight: 400;
  font-style: italic;
}

.ef-pencil {
  display: inline-flex;
  opacity: 0;
  color: #7F77DD;
  transition: opacity 0.15s;
  transform: translateY(0.5px);
  flex-shrink: 0;
}
.ef--editable .ef-val:hover .ef-pencil { opacity: 0.85; }

.ef-check {
  display: inline-flex;
  color: #1D9E75;
  animation: efCheckIn 0.35s cubic-bezier(0.34, 1.2, 0.64, 1);
  flex-shrink: 0;
}

.ef-input {
  font-family: inherit;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff);
  border: 1px solid #7F77DD;
  border-radius: 5px;
  padding: 3px 7px;
  outline: none;
  box-shadow: 0 0 0 3px rgba(127,119,221,0.14);
  transition: border-color 0.15s, box-shadow 0.15s;
  font-feature-settings: "tnum";
  max-width: 100%;
}
.ef-input:focus {
  border-color: #534AB7;
  box-shadow: 0 0 0 3px rgba(127,119,221,0.22);
}
.ef-textarea {
  font-feature-settings: normal;
  resize: vertical;
  line-height: 1.4;
}
.ef--saving .ef-input {
  border-color: #B4B2A9;
  box-shadow: 0 0 0 3px rgba(180,178,169,0.18);
}
.ef--error .ef-input {
  border-color: #E24B4A;
  box-shadow: 0 0 0 3px rgba(226,75,74,0.16);
}

.ef-spin {
  display: inline-flex;
  color: var(--t3, #888780);
  animation: efSpin 0.9s linear infinite;
  flex-shrink: 0;
}

@keyframes efCheckIn {
  0% { opacity: 0; transform: scale(0.5) translateY(0.5px); }
  100% { opacity: 1; transform: scale(1) translateY(0.5px); }
}
@keyframes efSpin {
  to { transform: rotate(360deg); }
}
</style>
