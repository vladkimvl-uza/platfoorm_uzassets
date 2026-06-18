/**
 * useConfirm.ts — singleton confirm/prompt диалоги в дизайн-токенах платформы
 * (замена нативных confirm()/prompt(), которые ломали премиум-UX).
 *
 * Архитектура — как useToast: module-level state + один <ConfirmHost /> в корне.
 * Любой компонент: `const { confirmDialog } = useConfirm();
 *   if (!(await confirmDialog({ message: "Удалить?", danger: true }))) return;`
 *
 * Одновременно показывается один диалог (новый запрос вытесняет предыдущий и
 * резолвит его как отказ) — для UI этого достаточно.
 */
import { ref, readonly } from "vue";

export interface ConfirmOptions {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean; // красная кнопка подтверждения для деструктивных действий
}

export interface PromptOptions {
  title?: string;
  message: string;
  defaultValue?: string;
  placeholder?: string;
  confirmText?: string;
  cancelText?: string;
}

export type ConfirmRequest =
  | { kind: "confirm"; opts: ConfirmOptions; resolve: (v: boolean) => void }
  | { kind: "prompt"; opts: PromptOptions; resolve: (v: string | null) => void };

const current = ref<ConfirmRequest | null>(null);

function _open(req: ConfirmRequest) {
  // Вытесняем предыдущий незакрытый диалог как отказ.
  const prev = current.value;
  if (prev) (prev.resolve as (v: unknown) => void)(prev.kind === "prompt" ? null : false);
  current.value = req;
}

function confirmDialog(o: ConfirmOptions | string): Promise<boolean> {
  const opts = typeof o === "string" ? { message: o } : o;
  return new Promise<boolean>((resolve) => _open({ kind: "confirm", opts, resolve }));
}

function promptDialog(o: PromptOptions | string): Promise<string | null> {
  const opts = typeof o === "string" ? { message: o } : o;
  return new Promise<string | null>((resolve) => _open({ kind: "prompt", opts, resolve }));
}

// Используется только хостом ConfirmHost.vue.
function _resolve(value: boolean | string | null) {
  const req = current.value;
  current.value = null;
  if (req) (req.resolve as (v: unknown) => void)(value);
}

export function useConfirm() {
  return { confirmDialog, promptDialog };
}

export function useConfirmHost() {
  return { current: readonly(current), resolveDialog: _resolve };
}
