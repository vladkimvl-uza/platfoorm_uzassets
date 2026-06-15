import { reactive } from "vue";
import { companiesApi, type CompanyCard } from "@/api/companies";

/**
 * useCompanyCard — единый контроллер поповера-карточки компании (по тикеру).
 *
 * Зеркало useUserCard: один глобальный CompanyCardHost в AppShell, любой
 * CompanyTicker с :code открывает карточку с hover-intent и якорит к элементу.
 * Данные кэшируются по code на сессию.
 */

export interface AnchorRect {
  top: number; left: number; bottom: number; right: number; width: number; height: number;
}

interface CardState {
  visible: boolean;
  loading: boolean;
  code: string | null;
  data: CompanyCard | null;
  preview: Partial<CompanyCard> | null;
  anchor: AnchorRect | null;
  pinned: boolean;
}

const state = reactive<CardState>({
  visible: false, loading: false, code: null,
  data: null, preview: null, anchor: null, pinned: false,
});

const cache = new Map<string, CompanyCard>();
let openTimer: number | undefined;
let closeTimer: number | undefined;
let overCard = false;

const OPEN_DELAY = 220;
const CLOSE_DELAY = 200;

function rectOf(el: HTMLElement): AnchorRect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, bottom: r.bottom, right: r.right, width: r.width, height: r.height };
}

async function fetchCard(code: string) {
  if (cache.has(code)) {
    if (state.code === code) state.data = cache.get(code)!;
    return;
  }
  state.loading = true;
  try {
    const d = await companiesApi.getCard(code);
    cache.set(code, d);
    if (state.code === code) state.data = d;
  } catch {
    /* карточка опциональна */
  } finally {
    if (state.code === code) state.loading = false;
  }
}

function apply(code: string, el: HTMLElement, preview?: Partial<CompanyCard> | null, pinned = false) {
  state.code = code;
  state.anchor = rectOf(el);
  state.preview = preview || null;
  state.data = cache.get(code) || null;
  state.pinned = pinned;
  state.visible = true;
  void fetchCard(code);
}

function open(code: string, el: HTMLElement, preview?: Partial<CompanyCard> | null) {
  window.clearTimeout(closeTimer);
  window.clearTimeout(openTimer);
  openTimer = window.setTimeout(() => apply(code, el, preview, false), OPEN_DELAY);
}

function openNow(code: string, el: HTMLElement, preview?: Partial<CompanyCard> | null) {
  window.clearTimeout(closeTimer);
  window.clearTimeout(openTimer);
  apply(code, el, preview, true);
}

function scheduleClose() {
  window.clearTimeout(openTimer);
  if (state.pinned) return;
  closeTimer = window.setTimeout(() => { if (!overCard) state.visible = false; }, CLOSE_DELAY);
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

export function useCompanyCard() {
  return { state, open, openNow, scheduleClose, setOverCard, closeNow };
}
