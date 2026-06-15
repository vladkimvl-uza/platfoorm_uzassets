import { reactive } from "vue";
import { directoryApi, type UserCard } from "@/api/directory";

/**
 * useUserCard — единый контроллер поповера-карточки пользователя.
 *
 * Архитектура: один глобальный хост (UserCardHost) монтируется в AppShell и
 * рендерит карточку поверх всего. Любой аватар/имя оборачивается в
 * <UserCardAnchor :user-id="…">, который через этот composable открывает/закрывает
 * карточку с задержкой (hover-intent) и якорит её к своему DOM-элементу.
 *
 * Данные карточки кэшируются по id на время сессии (один fetch на пользователя).
 */

export interface AnchorRect {
  top: number; left: number; bottom: number; right: number; width: number; height: number;
}

interface CardState {
  visible: boolean;
  loading: boolean;
  userId: string | null;
  data: UserCard | null;
  preview: Partial<UserCard> | null;
  anchor: AnchorRect | null;
  pinned: boolean; // открыт кликом — закрывается только кликом вне/Esc
}

const state = reactive<CardState>({
  visible: false,
  loading: false,
  userId: null,
  data: null,
  preview: null,
  anchor: null,
  pinned: false,
});

const cache = new Map<string, UserCard>();
let openTimer: number | undefined;
let closeTimer: number | undefined;
let overCard = false;

const OPEN_DELAY = 220;
const CLOSE_DELAY = 200;

function rectOf(el: HTMLElement): AnchorRect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, bottom: r.bottom, right: r.right, width: r.width, height: r.height };
}

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
    /* карточка опциональна — молча игнорируем сбой */
  } finally {
    if (state.userId === id) state.loading = false;
  }
}

function apply(userId: string, el: HTMLElement, preview?: Partial<UserCard> | null, pinned = false) {
  state.userId = userId;
  state.anchor = rectOf(el);
  state.preview = preview || null;
  state.data = cache.get(userId) || null;
  state.pinned = pinned;
  state.visible = true;
  void fetchCard(userId);
}

/** Открыть по наведению (с задержкой hover-intent). */
function open(userId: string, el: HTMLElement, preview?: Partial<UserCard> | null) {
  window.clearTimeout(closeTimer);
  window.clearTimeout(openTimer);
  openTimer = window.setTimeout(() => apply(userId, el, preview, false), OPEN_DELAY);
}

/** Открыть сразу по клику и «закрепить». */
function openNow(userId: string, el: HTMLElement, preview?: Partial<UserCard> | null) {
  window.clearTimeout(closeTimer);
  window.clearTimeout(openTimer);
  apply(userId, el, preview, true);
}

function scheduleClose() {
  window.clearTimeout(openTimer);
  if (state.pinned) return; // закреплённую карточку наведение не закрывает
  closeTimer = window.setTimeout(() => {
    if (!overCard) state.visible = false;
  }, CLOSE_DELAY);
}

function setOverCard(v: boolean) {
  overCard = v;
  if (v) window.clearTimeout(closeTimer);
  else scheduleClose();
}

function closeNow() {
  window.clearTimeout(openTimer);
  window.clearTimeout(closeTimer);
  state.visible = false;
  state.pinned = false;
}

export function useUserCard() {
  return { state, open, openNow, scheduleClose, setOverCard, closeNow };
}
