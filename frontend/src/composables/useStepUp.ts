import { reactive } from "vue";
import { authApi } from "@/api/auth";
import { t } from "@/locale/i18n";


/**
 * useStepUp — контроллер модалки повторной аутентификации (step-up, 841 п.5.2.4).
 *
 * Бэкенд защищает чувствительные операции зависимостью require_recent_auth: если
 * «сильная» аутентификация старше окна — возвращает 403 detail="step_up_required".
 * Интерсептор перехватывает это, вызывает requestStepUp(), показывает модалку
 * (пользователь вводит пароль → /auth/reauth), и при успехе ретраит исходный запрос.
 *
 * Промис-API: requestStepUp() резолвится true (подтверждено) или false (отмена).
 */

interface StepUpState {
  open: boolean;
  busy: boolean;
  error: string | null;
}

const state = reactive<StepUpState>({ open: false, busy: false, error: null });

let resolver: ((ok: boolean) => void) | null = null;
let pending: Promise<boolean> | null = null;

/** Открыть модалку и дождаться результата. Совмещает параллельные вызовы. */
function requestStepUp(): Promise<boolean> {
  if (pending) return pending;
  state.open = true;
  state.error = null;
  state.busy = false;
  pending = new Promise<boolean>((resolve) => {
    resolver = resolve;
  });
  return pending;
}

async function submit(password: string): Promise<void> {
  if (!password) {
    state.error = t('Введите пароль');
    return;
  }
  state.busy = true;
  state.error = null;
  try {
    await authApi.reauth(password);
    _finish(true);
  } catch (e: any) {
    state.busy = false;
    state.error = e?.response?.data?.detail || t('Неверный пароль');
  }
}

function cancel(): void {
  _finish(false);
}

function _finish(ok: boolean): void {
  state.open = false;
  state.busy = false;
  state.error = null;
  const r = resolver;
  resolver = null;
  pending = null;
  if (r) r(ok);
}

export function useStepUp() {
  return { state, requestStepUp, submit, cancel };
}
