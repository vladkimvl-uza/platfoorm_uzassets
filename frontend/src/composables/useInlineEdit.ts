/**
 * composables/useInlineEdit.ts
 * ─────────────────────────────────────────────────────────────────
 * Generic composable для inline-редактирования любого поля.
 *
 * Поведение:
 *   • start()  → переход в режим editing, копирование value в draft
 *   • Enter    → save()
 *   • Esc      → cancel()
 *   • blur     → save() (debounce-safe против повторного fire)
 *   • Save     → вызывает saveFn(draft) → optimistic update value + closing
 *               → при ошибке: rollback value, ставит error
 *
 * Состояния: idle | editing | saving | success(flash) | error
 *
 * Pack 7.29: первое применение в CompanyDrillModal, заложено как
 * единый паттерн для всех будущих модалок с inline-редактированием.
 */
import { ref, computed, type Ref } from "vue";
import { t } from "@/locale/i18n";


export type InlineEditState = "idle" | "editing" | "saving" | "success" | "error";

export interface UseInlineEditOptions<T> {
  /** Текущее значение поля (читаем из родителя через computed/ref). */
  value: Ref<T>;
  /** Функция сохранения, должна вернуть Promise. На ошибку — кинуть throw. */
  saveFn: (newValue: T) => Promise<void>;
  /** Опц. валидация перед save. Вернуть string ошибки или null/undef если ок. */
  validate?: (draft: T) => string | null | undefined;
  /** Сравнение двух значений (по умолчанию ===). */
  equals?: (a: T, b: T) => boolean;
  /** Сколько ms показывать success-вспышку. По умолчанию 1100. */
  successDurationMs?: number;
}

export function useInlineEdit<T>(opts: UseInlineEditOptions<T>) {
  const state = ref<InlineEditState>("idle");
  const draft = ref<T>(opts.value.value) as Ref<T>;
  const errorMsg = ref<string | null>(null);
  const successDur = opts.successDurationMs ?? 1100;
  const equals = opts.equals ?? ((a: T, b: T) => a === b);

  const editing = computed(() => state.value === "editing");
  const saving = computed(() => state.value === "saving");
  const isError = computed(() => state.value === "error");
  const isSuccess = computed(() => state.value === "success");

  function start() {
    if (state.value === "saving") return;
    draft.value = opts.value.value;
    errorMsg.value = null;
    state.value = "editing";
  }

  function cancel() {
    if (state.value === "saving") return;
    draft.value = opts.value.value;
    errorMsg.value = null;
    state.value = "idle";
  }

  async function save() {
    if (state.value !== "editing") return;

    // No change → silent close
    if (equals(draft.value, opts.value.value)) {
      state.value = "idle";
      return;
    }

    // Validate
    if (opts.validate) {
      const err = opts.validate(draft.value);
      if (err) {
        errorMsg.value = err;
        state.value = "error";
        return;
      }
    }

    const pending = draft.value;
    state.value = "saving";
    errorMsg.value = null;

    try {
      await opts.saveFn(pending);
      state.value = "success";
      setTimeout(() => {
        if (state.value === "success") state.value = "idle";
      }, successDur);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (e as Error)?.message || t('Не удалось сохранить');
      errorMsg.value = String(msg);
      state.value = "error";
    }
  }

  function clearError() {
    if (state.value === "error") {
      state.value = "idle";
      errorMsg.value = null;
    }
  }

  return {
    state,
    draft,
    errorMsg,
    editing,
    saving,
    isError,
    isSuccess,
    start,
    cancel,
    save,
    clearError,
  };
}
