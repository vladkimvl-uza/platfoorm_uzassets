import { reactive } from "vue";
import { directoryApi, type UserCard } from "@/api/directory";

/**
 * useUserModal — контроллер премиум-модалки профиля пользователя.
 *
 * Наведение на аватар/имя показывает быструю карточку (useUserCard), а КЛИК
 * открывает полноценную модалку с расширенной информацией (контакты, соцсети,
 * принадлежность, активность). Один глобальный UserViewModal в AppShell.
 */
interface ModalState {
  open: boolean;
  loading: boolean;
  userId: string | null;
  data: UserCard | null;
  preview: Partial<UserCard> | null;
}

const state = reactive<ModalState>({
  open: false, loading: false, userId: null, data: null, preview: null,
});

const cache = new Map<string, UserCard>();

async function fetchCard(id: string) {
  if (cache.has(id)) {
    if (state.userId === id) state.data = cache.get(id)!;
    return;
  }
  state.loading = true;
  try {
    const d = await directoryApi.userCard(id);
    cache.set(id, d);
    if (state.userId === id) state.data = d;
  } catch {
    /* модалка покажет превью/«—» */
  } finally {
    if (state.userId === id) state.loading = false;
  }
}

function open(userId: string, preview?: Partial<UserCard> | null) {
  state.userId = userId;
  state.preview = preview || null;
  state.data = cache.get(userId) || null;
  state.open = true;
  void fetchCard(userId);
}

function close() {
  state.open = false;
}

export function useUserModal() {
  return { state, open, close };
}
