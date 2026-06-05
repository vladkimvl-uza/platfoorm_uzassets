/**
 * usePresence — индикаторы присутствия online / away / offline.
 *
 * Две части:
 *  1. presenceStatus(lastSeen) — чистая функция: из давности last_seen_at
 *     вычисляет статус. Используется везде, где рисуем аватар.
 *  2. useHeartbeat() — фоновый пинг POST /presence/heartbeat пока вкладка
 *     активна И пользователь не «отошёл» (нет ввода > IDLE_MS). Когда вкладка
 *     скрыта / простой — пинги прекращаются, и человек естественно «сползает»
 *     online → away → offline по времени. Монтируется один раз в AppShell.
 */
import { onMounted, onUnmounted } from 'vue';
import { api } from '@/api/client';

export type PresenceStatus = 'online' | 'away' | 'offline';

// Окна статусов (мс). online должно покрывать ~2 пропущенных heartbeat'а.
const ONLINE_MS = 100 * 1000;   // < 100 c — онлайн
const AWAY_MS = 6 * 60 * 1000;  // < 6 мин — отошёл; дальше — офлайн

/** Статус присутствия из ISO-строки last_seen_at (или null). */
export function presenceStatus(lastSeen?: string | null): PresenceStatus {
  if (!lastSeen) return 'offline';
  const t = Date.parse(lastSeen);
  if (Number.isNaN(t)) return 'offline';
  const age = Date.now() - t;
  if (age < ONLINE_MS) return 'online';
  if (age < AWAY_MS) return 'away';
  return 'offline';
}

/** Человекочитаемая подпись статуса (ru). */
export function presenceLabel(status: PresenceStatus): string {
  return status === 'online' ? 'В сети'
    : status === 'away' ? 'Отошёл'
    : 'Не в сети';
}

const HEARTBEAT_MS = 45 * 1000;  // частота пинга
const IDLE_MS = 5 * 60 * 1000;   // нет ввода дольше → считаем «отошёл», пинги стоп

/**
 * Фоновый heartbeat-цикл. Вызвать ОДИН раз в корневом layout (AppShell)
 * после авторизации. Автоматически чистится при unmount.
 */
export function useHeartbeat() {
  let timer: number | undefined;
  let lastActivity = Date.now();

  const markActivity = () => { lastActivity = Date.now(); };

  const beat = async (force = false) => {
    if (document.hidden) return;                      // вкладка скрыта — не пингуем
    if (!force && Date.now() - lastActivity > IDLE_MS) return;  // простой — «отошёл»
    try {
      await api.post('/presence/heartbeat');
    } catch {
      /* офлайн / 401 — молча игнорируем, цикл продолжится */
    }
  };

  const onVisibility = () => {
    if (!document.hidden) { markActivity(); beat(true); }
  };

  const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'] as const;

  onMounted(() => {
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));
    document.addEventListener('visibilitychange', onVisibility);
    beat(true);                                       // сразу отметиться
    timer = window.setInterval(() => beat(false), HEARTBEAT_MS);
  });

  onUnmounted(() => {
    ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, markActivity));
    document.removeEventListener('visibilitychange', onVisibility);
    if (timer) window.clearInterval(timer);
  });
}
