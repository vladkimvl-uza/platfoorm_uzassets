/**
 * useVersionCheck — обнаружение нового деплоя фронтенда без ручной чистки кэша.
 *
 * Как работает (без build-time версии):
 *   - «Наша» версия = хеш entry-чанка `index-<hash>.js`, реально загруженного
 *     в DOM (то, на чём мы сейчас работаем).
 *   - Периодически тянем `/` (index.html отдаётся с no-cache — см. nginx) и
 *     достаём хеш entry-чанка, который сервер отдаёт СЕЙЧАС.
 *   - Если серверный хеш ≠ нашего → задеплоен новый билд → показываем баннер
 *     «Доступна новая версия» с кнопкой «Обновить».
 *
 * Намеренно НЕ авто-релоадим: пользователь может редактировать финмодель/KPI с
 * несохранёнными данными (см. anti-data-loss в редакторах). Перезагрузку
 * инициирует только сам пользователь.
 *
 * В dev (Vite) entry — `/src/main.ts`, хеша нет → фича сама отключается.
 */
import { ref } from "vue";

export const updateAvailable = ref(false);

const ENTRY_RE = /\/assets\/index-([\w-]+)\.js/;

function ownEntryHash(): string | null {
  for (const s of Array.from(document.scripts)) {
    const m = s.src.match(ENTRY_RE);
    if (m) return m[1];
  }
  return null;
}

async function serverEntryHash(): Promise<string | null> {
  try {
    const res = await fetch("/", {
      cache: "no-store",
      headers: { "Cache-Control": "no-cache" },
      credentials: "same-origin",
    });
    if (!res.ok) return null;
    const html = await res.text();
    const m = html.match(ENTRY_RE);
    return m ? m[1] : null;
  } catch {
    return null; // offline / network blip — не считаем новой версией
  }
}

let started = false;

export function initVersionCheck(intervalMs = 5 * 60_000): void {
  if (started) return;
  const mine = ownEntryHash();
  if (!mine) return; // dev-режим или неизвестный entry — фича выключена
  started = true;

  const check = async (): Promise<void> => {
    if (updateAvailable.value) return;
    const server = await serverEntryHash();
    if (server && server !== mine) updateAvailable.value = true;
  };

  // первая проверка вскоре после загрузки + периодически + при возврате на вкладку
  window.setTimeout(() => void check(), 15_000);
  window.setInterval(() => void check(), intervalMs);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void check();
  });
}
