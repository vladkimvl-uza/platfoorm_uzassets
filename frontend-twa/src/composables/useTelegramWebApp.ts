/**
 * Telegram WebApp bridge (Phase C).
 *
 * Wraps window.Telegram.WebApp with a typed, mockable façade. When the page
 * is opened outside Telegram (regular browser, dev), bridge calls become
 * no-ops and `initData` is empty — useful for local development.
 */

export interface TgUser {
  id: number;
  first_name?: string;
  last_name?: string;
  username?: string;
  language_code?: string;
}

export interface TgThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { user?: TgUser; auth_date?: number; hash?: string };
  colorScheme: "light" | "dark";
  themeParams: TgThemeParams;
  isExpanded: boolean;
  viewportHeight: number;
  viewportStableHeight: number;
  platform: string;
  version: string;

  ready: () => void;
  expand: () => void;
  close: () => void;

  MainButton: {
    text: string;
    isVisible: boolean;
    setText: (text: string) => void;
    show: () => void;
    hide: () => void;
    enable: () => void;
    disable: () => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
    setParams: (p: { text?: string; color?: string; text_color?: string; is_active?: boolean; is_visible?: boolean }) => void;
  };

  BackButton: {
    isVisible: boolean;
    show: () => void;
    hide: () => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
  };

  HapticFeedback: {
    impactOccurred: (style: "light" | "medium" | "heavy" | "rigid" | "soft") => void;
    notificationOccurred: (type: "error" | "success" | "warning") => void;
    selectionChanged: () => void;
  };

  showAlert: (msg: string, cb?: () => void) => void;
  showConfirm: (msg: string, cb?: (ok: boolean) => void) => void;
  showPopup: (
    params: { title?: string; message: string; buttons?: Array<{ id?: string; type?: string; text?: string }> },
    cb?: (id: string) => void,
  ) => void;
  openLink: (url: string, options?: { try_instant_view?: boolean }) => void;
  openTelegramLink: (url: string) => void;

  setHeaderColor: (color: string) => void;
  setBackgroundColor: (color: string) => void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

// ──────────────────────────────────────────────────────────────────────

let _cachedWa: TelegramWebApp | null = null;

function _getWebApp(): TelegramWebApp | null {
  if (_cachedWa) return _cachedWa;
  const wa = (typeof window !== "undefined" && window.Telegram?.WebApp) || null;
  if (wa) _cachedWa = wa;
  return wa;
}

export function useTelegramWebApp() {
  const wa = _getWebApp();
  const inside = wa !== null;

  return {
    inside,
    raw: wa,

    initData: wa?.initData ?? "",
    user: wa?.initDataUnsafe?.user ?? null,
    themeParams: wa?.themeParams ?? {},
    colorScheme: wa?.colorScheme ?? "light",
    platform: wa?.platform ?? "unknown",

    ready: () => wa?.ready(),
    expand: () => wa?.expand(),
    close: () => wa?.close(),

    mainButton: wa?.MainButton ?? null,
    backButton: wa?.BackButton ?? null,
    haptics: wa?.HapticFeedback ?? null,

    showAlert: (msg: string, cb?: () => void) => wa?.showAlert(msg, cb),
    showConfirm: (msg: string, cb?: (ok: boolean) => void) => wa?.showConfirm(msg, cb),
    openLink: (url: string) => wa?.openLink(url),

    setHeaderColor: (color: string) => wa?.setHeaderColor(color),
  };
}
