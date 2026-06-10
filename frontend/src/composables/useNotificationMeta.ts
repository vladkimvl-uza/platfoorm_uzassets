/**
 * useNotificationMeta — превращает уведомление (type + payload) в премиальный
 * дескриптор: ЧТО конкретно сделал пользователь (сменил статус / изменил срок /
 * добавил комментарий / обновил ход …) + акцентный цвет, иконка и деталь.
 *
 * Используется в NotificationBell, NotificationsView и NotificationToast —
 * единый язык карточки во всех местах.
 */

export interface NotifEntity {
  type: string;
  priority?: string;
  title?: string | null;
  body?: string | null;
  payload?: Record<string, any> | null;
}

export type NotifDetail =
  | { kind: "status"; from?: string; to?: string }
  | { kind: "deadline"; from?: string; to?: string }
  | { kind: "text"; text: string }
  | { kind: "health"; health: string };

export interface NotifDescriptor {
  verb: string; // «Сменил статус», «Изменил срок», «Оставил комментарий» …
  accent: string; // hex акцента действия
  icon: string; // ключ SVG-иконки (см. NOTIF_ICON_PATHS)
  entity?: string; // название задачи/проекта
  detail?: NotifDetail;
}

// Палитра действий (дизайн-система UzAssets)
const C = {
  green: "#1D9E75",
  amber: "#EF9F27",
  red: "#E24B4A",
  purple: "#7C6FF7",
  deep: "#534AB7",
  blue: "#378ADD",
  navy: "#1E2A4A",
  grey: "#888780",
} as const;

const STATUS_RU: Record<string, string> = {
  todo: "К выполнению",
  backlog: "Бэклог",
  planned: "Запланировано",
  in_progress: "В работе",
  in_review: "На проверке",
  review: "На проверке",
  blocked: "Заблокировано",
  on_hold: "Приостановлено",
  done: "Выполнено",
  completed: "Выполнено",
  cancelled: "Отменено",
  canceled: "Отменено",
};

function statusLabel(s?: string | null): string {
  if (!s) return "—";
  return STATUS_RU[s] || s;
}

function statusColor(s?: string | null): string {
  if (!s) return C.grey;
  if (/done|complete/i.test(s)) return C.green;
  if (/progress|review/i.test(s)) return C.purple;
  if (/block|cancel|reject/i.test(s)) return C.red;
  if (/hold|pause/i.test(s)) return C.amber;
  return C.navy;
}

/** «2026-04-11» / ISO → «11 апр» */
const _MON = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
function shortDate(s?: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return `${d.getDate()} ${_MON[d.getMonth()]}`;
}

/** SVG path(ы) по ключу иконки — stroke-only, 24×24 viewBox. */
export const NOTIF_ICON_PATHS: Record<string, string> = {
  status: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
  deadline: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  progress: '<path d="M3 3v18h18"/><path d="M7 14l3-3 3 3 5-6"/>',
  result: '<path d="M20 6L9 17l-5-5"/>',
  comment: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  mention: '<circle cx="12" cy="12" r="4"/><path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94"/>',
  moderation: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  assign: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M19 8v6M22 11h-6"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
};

/** Главный маппер: уведомление → дескриптор действия. */
export function describeNotification(n: NotifEntity): NotifDescriptor {
  const p = (n.payload || {}) as Record<string, any>;
  const action = String(p.action || "");
  const t = n.type || "";
  const entity: string | undefined = p.entity_title || undefined;

  // — Смена статуса —
  if (action === "status_changed" || t === "watch.status" || t === "task.status_changed") {
    return {
      verb: "Сменил статус",
      accent: statusColor(p.new_status),
      icon: "status",
      entity,
      detail: { kind: "status", from: statusLabel(p.old_status), to: statusLabel(p.new_status) },
    };
  }
  // — Изменение срока —
  if (action === "deadline_changed" || t === "watch.deadline") {
    return {
      verb: "Изменил срок",
      accent: C.amber,
      icon: "deadline",
      entity,
      detail: { kind: "deadline", from: shortDate(p.old_due), to: shortDate(p.new_due) },
    };
  }
  // — Обновление хода —
  if (action === "progress" || t === "watch.progress") {
    return {
      verb: "Обновил ход",
      accent: C.purple,
      icon: "progress",
      entity,
      detail: p.excerpt ? { kind: "text", text: String(p.excerpt) } : undefined,
    };
  }
  // — Результат —
  if (action === "result" || t === "watch.result") {
    return { verb: "Отметил результат", accent: C.green, icon: "result", entity };
  }
  // — Комментарий —
  if (t === "watch.comment" || t === "comment.replied" || t.startsWith("comment")) {
    return {
      verb: t === "comment.replied" ? "Ответил на комментарий" : "Оставил комментарий",
      accent: C.blue,
      icon: "comment",
      entity,
      detail: n.body ? { kind: "text", text: n.body } : undefined,
    };
  }
  // — Упоминание —
  if (t === "mention") {
    return { verb: "Упомянул вас", accent: C.purple, icon: "mention", entity, detail: n.body ? { kind: "text", text: n.body } : undefined };
  }
  // — Модерация —
  if (t.startsWith("moderation")) {
    return { verb: "Отправил на модерацию", accent: C.red, icon: "moderation", entity };
  }
  // — Дедлайны (шедулер) —
  if (t === "deadline.approaching") {
    return { verb: "Приближается срок", accent: C.amber, icon: "deadline", entity };
  }
  if (t === "deadline.missed") {
    return { verb: "Срок пропущен", accent: C.red, icon: "deadline", entity };
  }
  // — Назначение —
  if (t === "task" || t === "project" || t.includes("assign")) {
    return { verb: "Назначил вам " + (t === "project" ? "проект" : "задачу"), accent: C.deep, icon: "assign", entity };
  }
  // — Фолбэк: заголовок как действие —
  return { verb: n.title || "Уведомление", accent: C.grey, icon: "bell", entity, detail: n.body ? { kind: "text", text: n.body } : undefined };
}
