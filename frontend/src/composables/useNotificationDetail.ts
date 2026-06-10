/**
 * useNotificationDetail — глобальное состояние модалки деталей уведомления.
 * Открывается, когда у уведомления нет конкретной сущности для перехода
 * (owner.activity без id, объявления и т.п.) — вместо «ничего не происходит»
 * показываем полную карточку: кто, что сделал, когда, где, подробности.
 */
import { reactive } from "vue";

interface NotifLike {
  id: string;
  type: string;
  priority?: string;
  title?: string | null;
  body?: string | null;
  payload?: Record<string, any> | null;
  source_user_id?: string | null;
  source_module?: string | null;
  company_id?: string | null;
  created_at: string;
  is_read?: boolean;
}

const state = reactive<{ open: boolean; notification: NotifLike | null }>({
  open: false,
  notification: null,
});

function open(n: NotifLike): void {
  state.notification = n;
  state.open = true;
}

function close(): void {
  state.open = false;
  state.notification = null;
}

export function useNotificationDetail() {
  return { state, open, close };
}
