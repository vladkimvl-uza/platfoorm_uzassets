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

// Реальные статусы задач/проектов платформы (синхронно с tasks/notifications.py).
const STATUS_RU: Record<string, string> = {
  new: "Не начато",
  init: "Инициирование",
  active: "В процессе",
  review: "На согласовании",
  done: "Завершено",
  quarterly: "Ежеквартально",
  monthly: "Ежемесячно",
  ongoing: "Постоянно",
  deferred: "Перенесено",
  // запасная совместимость с англоязычными статусами
  todo: "Не начато",
  in_progress: "В процессе",
  blocked: "Заблокировано",
  cancelled: "Отменено",
  completed: "Завершено",
};

function statusLabel(s?: string | null): string {
  if (!s) return "—";
  return STATUS_RU[s] || s;
}

function statusColor(s?: string | null): string {
  if (!s) return C.grey;
  if (/done|complete/i.test(s)) return C.green;
  if (/active|progress|review/i.test(s)) return C.purple;
  if (/block|cancel|reject/i.test(s)) return C.red;
  if (/defer|hold|pause/i.test(s)) return C.amber;
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
  // Название сущности из заголовка вида «Статус задачи: <name>».
  const titleEntity = (s?: string | null): string | undefined => {
    const x = (s || "").split(": ").slice(1).join(": ").trim();
    return x || undefined;
  };
  const bodyDetail = (): NotifDetail | undefined => (n.body ? { kind: "text", text: n.body } : undefined);

  // — Смена статуса (watch.status / task.status_changed) —
  if (action === "status_changed" || t === "watch.status" || t === "task.status_changed") {
    const from = p.old_status ? statusLabel(p.old_status) : undefined;
    const to = p.new_status ? statusLabel(p.new_status) : undefined;
    const detail: NotifDetail | undefined = (from && to)
      ? { kind: "status", from, to }
      : to ? { kind: "text", text: `Новый статус: ${to}` }
      : bodyDetail();
    return { verb: "Сменил статус", accent: statusColor(p.new_status), icon: "status",
             entity: entity || titleEntity(n.title), detail };
  }
  // — Изменение срока —
  if (action === "deadline_changed" || t === "watch.deadline") {
    return { verb: "Изменил срок", accent: C.amber, icon: "deadline", entity,
             detail: { kind: "deadline", from: shortDate(p.old_due), to: shortDate(p.new_due) } };
  }
  // — Обновление хода —
  if (action === "progress" || t === "watch.progress") {
    return { verb: "Обновил ход", accent: C.purple, icon: "progress", entity,
             detail: p.excerpt ? { kind: "text", text: String(p.excerpt) } : bodyDetail() };
  }
  // — Результат —
  if (action === "result" || t === "watch.result") {
    return { verb: "Отметил результат", accent: C.green, icon: "result", entity };
  }
  // — Файл (watch.comment, но в теле/заголовке — файл) —
  if (t === "watch.comment" && /файл/i.test((n.title || "") + " " + (n.body || ""))) {
    return { verb: "Загрузил файл", accent: C.deep, icon: "assign", entity, detail: bodyDetail() };
  }
  // — Комментарий —
  if (t === "watch.comment" || t === "comment.replied" || t.startsWith("comment")) {
    return { verb: t === "comment.replied" ? "Ответил на комментарий" : "Оставил комментарий",
             accent: C.blue, icon: "comment", entity, detail: bodyDetail() };
  }
  // — Упоминание —
  if (t === "mention") {
    return { verb: "Упомянул вас", accent: C.purple, icon: "mention", entity, detail: bodyDetail() };
  }
  // — Модерация: отправлено на согласование —
  if (t === "moderation.pending") {
    return { verb: "Отправил на согласование", accent: C.amber, icon: "moderation",
             entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  // — Модерация: решение —
  if (t === "approved") {
    return { verb: "Согласовал", accent: C.green, icon: "result", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  if (t === "rejected") {
    return { verb: "Отклонил", accent: C.red, icon: "moderation", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  if (t === "review_requested") {
    return { verb: "Вернул на доработку", accent: C.amber, icon: "moderation", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  // — Дедлайны (шедулер) —
  if (t === "deadline.approaching") {
    return { verb: "Приближается срок", accent: C.amber, icon: "deadline", entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  if (t === "deadline.missed") {
    return { verb: "Срок пропущен", accent: C.red, icon: "deadline", entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  // — Назначение —
  if (t === "task" || t === "project" || t === "assignment" || t.includes("assign")) {
    return { verb: "Назначил вам " + (t === "project" ? "проект" : "задачу"), accent: C.deep, icon: "assign",
             entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  // — Объявление / рассылка —
  if (t.startsWith("broadcast") || t === "system.announcement") {
    return { verb: "Объявление", accent: C.deep, icon: "bell", entity: n.title || undefined, detail: bodyDetail() };
  }
  // — Фид активности (owner.activity: «{модуль}: {действие}», actor в аватаре) —
  if (t === "owner.activity") {
    const rawVerb = String(p.verb || (n.title || "").split(":").pop() || "").trim() || "изменение";
    const label = String(p.label || (n.title || "").split(":")[0] || "").trim();
    // Размытые отглагольные существительные → понятный глагол прошедшего времени.
    // При создании названия новой записи нет в URL → честное «Добавил запись».
    const verb = /коммент/i.test(rawVerb) ? "Прокомментировал"
      : /файл/i.test(rawVerb) ? "Загрузил файл"
      : /добав|нов/i.test(rawVerb) ? (p.entity_title ? "Добавил" : "Добавил запись")
      : /удал/i.test(rawVerb) ? "Удалил"
      : "Изменил";
    const acc = verb === "Добавил" ? C.green
      : verb === "Удалил" ? C.red
      : verb === "Прокомментировал" ? C.blue
      : verb === "Загрузил файл" ? C.deep
      : C.purple;
    const ic = verb === "Добавил" ? "result"
      : verb === "Удалил" ? "moderation"
      : verb === "Прокомментировал" ? "comment"
      : verb === "Загрузил файл" ? "assign"
      : "progress";
    // Сущность: конкретное название (если бэк смог его подтянуть) → «… в Задачи».
    const ent = p.entity_title
      ? `${p.entity_title}${label ? " · " + label : ""}`
      : (label || undefined);
    // Деталь: какие поля изменены (бэк кладёт p.fields = список рус. лейблов).
    // Фильтр внутренних/служебных полей (и для СТАРЫХ уведомлений, где бэк ещё
    // не фильтровал): num, *_id, год и т.п. не несут смысла читателю.
    const HIDDEN_FIELDS = new Set([
      "num", "id", "project_id", "board_id", "parent_id", "company_id",
      "portfolio_year", "weight", "sort_order", "position", "order", "updated_at",
    ]);
    const FIELD_RU: Record<string, string> = {
      title: "название", name: "название", description: "описание", status: "статус",
      due_date: "срок", assignee_id: "исполнитель", assignee_email: "исполнитель",
      priority: "приоритет", direction_id: "направление", tags: "теги",
      progress: "прогресс", result: "результат",
    };
    const fields = (Array.isArray(p.fields) ? p.fields : [])
      .filter((f: any) => f && !HIDDEN_FIELDS.has(String(f)) && !/_id$/.test(String(f)))
      .map((f: any) => FIELD_RU[String(f)] || String(f));
    const fieldsU = [...new Set(fields)];
    const detail: NotifDetail | undefined = fieldsU.length
      ? { kind: "text", text: `Изменено: ${fieldsU.slice(0, 6).join(", ")}` }
      : undefined;
    return { verb, accent: acc, icon: ic, entity: ent, detail };
  }
  // — Фолбэк: нейтральный чип + заголовок как сущность (без дублирования) —
  return { verb: "Уведомление", accent: C.grey, icon: "bell", entity: n.title || undefined, detail: n.body ? { kind: "text", text: n.body } : undefined };
}
