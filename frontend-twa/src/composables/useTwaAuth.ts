/**
 * TWA auth lifecycle (Phase C).
 *
 * Flow:
 *   1. View `TwaLogin` calls `ensureLogin()`
 *   2. Pulls initData from window.Telegram.WebApp.initData
 *   3. POST /api/auth/twa-login → { access_token, refresh_token, ... }
 *   4. Persists tokens in localStorage so they survive page reloads inside
 *      Telegram (it does cache the WebApp container per-session).
 *   5. axios instance attaches Authorization: Bearer ${token} automatically.
 */
import { ref, computed } from "vue";
import { useTelegramWebApp } from "./useTelegramWebApp";
import { api } from "@/api/client";

const LS_TOKEN = "uza-twa-access";
const LS_REFRESH = "uza-twa-refresh";

const _token = ref<string | null>(localStorage.getItem(LS_TOKEN));
const _refresh = ref<string | null>(localStorage.getItem(LS_REFRESH));

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

function _persist(pair: TokenPair) {
  _token.value = pair.access_token;
  _refresh.value = pair.refresh_token;
  localStorage.setItem(LS_TOKEN, pair.access_token);
  localStorage.setItem(LS_REFRESH, pair.refresh_token);
}

function _clear() {
  _token.value = null;
  _refresh.value = null;
  localStorage.removeItem(LS_TOKEN);
  localStorage.removeItem(LS_REFRESH);
}

export function useTwaAuth() {
  const tg = useTelegramWebApp();

  const isAuthed = computed(() => !!_token.value);

  async function loginWithInitData(): Promise<TokenPair> {
    if (!tg.inside) {
      throw new Error("Откройте приложение из Telegram (вне Telegram авторизация невозможна).");
    }
    const initData = tg.initData;
    if (!initData) {
      throw new Error("Telegram WebApp вернул пустой initData — попробуйте перезайти.");
    }
    const { data } = await api.post<TokenPair>("/auth/twa-login", { init_data: initData });
    _persist(data);
    return data;
  }

  async function ensureLogin(): Promise<void> {
    if (_token.value) return;
    await loginWithInitData();
  }

  function logout() {
    _clear();
  }

  return {
    token: _token,
    refresh: _refresh,
    isAuthed,
    loginWithInitData,
    ensureLogin,
    logout,
  };
}
