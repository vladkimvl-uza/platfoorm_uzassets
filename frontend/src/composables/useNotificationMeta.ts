import { i18nKey } from "@/locale/keys";
import { fmtDate } from "@/locale";
import { getCurrentLocale, t as translateUi } from "@/locale/i18n";
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
  new: i18nKey("Не начато"),
  init: i18nKey("Инициирование"),
  active: i18nKey("В процессе"),
  review: i18nKey("На согласовании"),
  done: i18nKey("Завершено"),
  quarterly: i18nKey("Ежеквартально"),
  monthly: i18nKey("Ежемесячно"),
  ongoing: i18nKey("Постоянно"),
  deferred: i18nKey("Перенесено"),
  // запасная совместимость с англоязычными статусами
  todo: i18nKey("Не начато"),
  in_progress: i18nKey("В процессе"),
  blocked: i18nKey("Заблокировано"),
  cancelled: i18nKey("Отменено"),
  completed: i18nKey("Завершено"),
};

function statusLabel(s?: string | null): string {
  if (!s) return "—";
  return STATUS_RU[s] ? translateUi(STATUS_RU[s]) : s;
}

function statusColor(s?: string | null): string {
  if (!s) return C.grey;
  if (/done|complete/i.test(s)) return C.green;
  if (/active|progress|review/i.test(s)) return C.purple;
  if (/block|cancel|reject/i.test(s)) return C.red;
  if (/defer|hold|pause/i.test(s)) return C.amber;
  return C.navy;
}

// i18n-exempt-start -- canonical classifiers for legacy persisted audit payloads.
const OWNER_MODULE_LABELS: Record<string, string> = {
  "Бизнес-план": i18nKey("Бизнес-план"),
  "Кредитный портфель": i18nKey("Кредитный портфель"),
  "Инвест-проекты": i18nKey("Инвест-проекты"),
  "Задачи": i18nKey("Задачи"),
  "Проекты": i18nKey("Проекты"),
  "Комментарии": i18nKey("Комментарии"),
  "Файлы": i18nKey("Файлы"),
  "Финансы": i18nKey("Финансы"),
  "Корпоративное управление": i18nKey("Корпоративное управление"),
  "Рейтинги": i18nKey("Рейтинги"),
  "Финмодель": i18nKey("Финмодель"),
  "Казначейство": i18nKey("Казначейство"),
  "Закупки": i18nKey("Закупки"),
  "Компании": i18nKey("Компании"),
  "Заметки": i18nKey("Заметки"),
  "Эластичность": i18nKey("Эластичность"),
};

const OWNER_FIELD_LABELS: Record<string, string> = {
  title: i18nKey("название"), name: i18nKey("название"), "название": i18nKey("название"),
  description: i18nKey("описание"), "описание": i18nKey("описание"),
  status: i18nKey("статус"), "статус": i18nKey("статус"),
  due_date: i18nKey("срок"), "срок": i18nKey("срок"),
  start_date: i18nKey("дата начала"), "дата начала": i18nKey("дата начала"),
  assignee_id: i18nKey("исполнитель"), assignee_email: i18nKey("исполнитель"), "исполнитель": i18nKey("исполнитель"),
  assignees: i18nKey("исполнители"), "исполнители": i18nKey("исполнители"),
  consultant_ids: i18nKey("консультанты"), consultants: i18nKey("консультанты"), "консультанты": i18nKey("консультанты"),
  priority: i18nKey("приоритет"), "приоритет": i18nKey("приоритет"),
  direction_id: i18nKey("направление"), direction: i18nKey("направление"), "направление": i18nKey("направление"),
  tags: i18nKey("теги"), "теги": i18nKey("теги"),
  progress: i18nKey("прогресс"), progress_pct: i18nKey("прогресс"), "прогресс": i18nKey("прогресс"),
  result: i18nKey("результат"), is_result: i18nKey("результат"), "результат": i18nKey("результат"),
  notes: i18nKey("примечание"), "примечание": i18nKey("примечание"),
  comment: i18nKey("комментарий"), "комментарий": i18nKey("комментарий"),
  comments: i18nKey("комментарии"), "комментарии": i18nKey("комментарии"),
  color: i18nKey("цвет"), "цвет": i18nKey("цвет"), sector: i18nKey("сектор"), "сектор": i18nKey("сектор"),
  is_active: i18nKey("активность"), "активность": i18nKey("активность"),
  revenue: i18nKey("выручка"), "выручка": i18nKey("выручка"), ebitda: "EBITDA",
  net_profit: i18nKey("чистая прибыль"), "чистая прибыль": i18nKey("чистая прибыль"),
  gross_profit: i18nKey("валовая прибыль"), "валовая прибыль": i18nKey("валовая прибыль"),
  assets: i18nKey("активы"), "активы": i18nKey("активы"), liabilities: i18nKey("обязательства"), "обязательства": i18nKey("обязательства"),
  equity: i18nKey("капитал"), "капитал": i18nKey("капитал"), cash: i18nKey("денежные средства"), "денежные средства": i18nKey("денежные средства"),
  opex: i18nKey("операц. расходы"), "операц. расходы": i18nKey("операц. расходы"), capex: i18nKey("капзатраты"), "капзатраты": i18nKey("капзатраты"),
  debt: i18nKey("долг"), "долг": i18nKey("долг"), plan: i18nKey("план"), "план": i18nKey("план"), fact: i18nKey("факт"), "факт": i18nKey("факт"),
  metric_key: i18nKey("показатель"), "показатель": i18nKey("показатель"), metrics: i18nKey("показатели"), indicators: i18nKey("показатели"), "показатели": i18nKey("показатели"),
  records: i18nKey("записи"), "записи": i18nKey("записи"), lines: i18nKey("статьи"), "статьи": i18nKey("статьи"),
  values: i18nKey("значения"), "значения": i18nKey("значения"), amount: i18nKey("сумма"), "сумма": i18nKey("сумма"), currency: i18nKey("валюта"), "валюта": i18nKey("валюта"),
  weight: i18nKey("вес"), "вес": i18nKey("вес"), managers: i18nKey("ответственные"), "ответственные": i18nKey("ответственные"), target: i18nKey("цель"), "цель": i18nKey("цель"),
  issues: i18nKey("риски/вопросы"), "риски/вопросы": i18nKey("риски/вопросы"), swot: "SWOT",
  pillar: i18nKey("компонент"), "компонент": i18nKey("компонент"), score: i18nKey("оценка"), "оценка": i18nKey("оценка"),
  e: i18nKey("экология"), "экология": i18nKey("экология"), s: i18nKey("социальное"), "социальное": i18nKey("социальное"), g: i18nKey("управление"), "управление": i18nKey("управление"),
  rating: i18nKey("рейтинг"), "рейтинг": i18nKey("рейтинг"), agency: i18nKey("агентство"), "агентство": i18nKey("агентство"), outlook: i18nKey("прогноз"), "прогноз": i18nKey("прогноз"),
  scale: i18nKey("шкала"), "шкала": i18nKey("шкала"), report_url: i18nKey("ссылка на отчёт"), "ссылка на отчёт": i18nKey("ссылка на отчёт"),
  is_esg: i18nKey("ESG-флаг"), "ESG-флаг": i18nKey("ESG-флаг"), date: i18nKey("дата"), "дата": i18nKey("дата"),
  board_members: i18nKey("совет директоров"), "совет директоров": i18nKey("совет директоров"), committees: i18nKey("комитеты"), "комитеты": i18nKey("комитеты"),
  meetings: i18nKey("заседания"), "заседания": i18nKey("заседания"), decisions: i18nKey("решения"), "решения": i18nKey("решения"),
  chairman: i18nKey("председатель"), "председатель": i18nKey("председатель"), members: i18nKey("состав"), "состав": i18nKey("состав"),
  is_independent: i18nKey("независимость"), "независимость": i18nKey("независимость"), email: "e-mail", phone: i18nKey("телефон"), "телефон": i18nKey("телефон"),
  contracts: i18nKey("договоры"), "договоры": i18nKey("договоры"), savings: i18nKey("экономия"), "экономия": i18nKey("экономия"),
  suppliers: i18nKey("поставщики"), "поставщики": i18nKey("поставщики"), lots: i18nKey("лоты"), "лоты": i18nKey("лоты"),
  products: i18nKey("продукты"), "продукты": i18nKey("продукты"), imports: i18nKey("импорт"), "импорт": i18nKey("импорт"),
  energy: i18nKey("энергоресурсы"), "энергоресурсы": i18nKey("энергоресурсы"), norm: i18nKey("норма расхода"), "норма расхода": i18nKey("норма расхода"),
  output: i18nKey("выпуск"), "выпуск": i18nKey("выпуск"), components: i18nKey("статьи затрат"), "статьи затрат": i18nKey("статьи затрат"),
  assignments: i18nKey("назначения"), "назначения": i18nKey("назначения"), consultant: i18nKey("консультант"), "консультант": i18nKey("консультант"),
  tasks: i18nKey("задачи"), "задачи": i18nKey("задачи"),
};

const ACTIVITY_STATUS_LABELS: Record<string, string> = {
  "Инициация": i18nKey("Инициация"), "Новая": i18nKey("Новая"),
  "В работе": i18nKey("В работе"), "На проверке": i18nKey("На проверке"),
  "Завершено": i18nKey("Завершено"), "Квартальная": i18nKey("Квартальная"),
  "Ежемесячная": i18nKey("Ежемесячная"), "Постоянная": i18nKey("Постоянная"),
  "Перенесена": i18nKey("Перенесена"), "Заблокирована": i18nKey("Заблокирована"),
  "только владелец": i18nKey("только владелец"),
  "по правам (ai.view)": i18nKey("по правам (ai.view)"),
  "включён": i18nKey("включён"), "выключен": i18nKey("выключен"),
  "включены": i18nKey("включены"), "выключены": i18nKey("выключены"),
};

function translateActivityValue(value: string): string {
  const key = ACTIVITY_STATUS_LABELS[value];
  return key ? translateUi(key) : value;
}

/** Translate known server-generated audit text while preserving DB/user values. */
export function translateActivityDetail(rawValue: unknown): string {
  const raw = String(rawValue || "").trim();
  if (!raw) return raw;
  let match = raw.match(/^Статус:\s*(.*?)\s*→\s*(.*?)$/);
  if (match) return translateUi("Статус: {from} → {to}", {
    from: translateActivityValue(match[1]), to: translateActivityValue(match[2]),
  });
  match = raw.match(/^Режим доступа к ИИ:\s*(.*?)\s*→\s*(.*?)$/);
  if (match) return translateUi("Режим доступа к ИИ: {from} → {to}", {
    from: translateActivityValue(match[1]), to: translateActivityValue(match[2]),
  });
  match = raw.match(/^Ассистент:\s*(.*?)\s*→\s*(.*?)$/);
  if (match) return translateUi("Ассистент: {from} → {to}", {
    from: translateActivityValue(match[1]), to: translateActivityValue(match[2]),
  });
  match = raw.match(/^ИИ-инструменты:\s*(.*?)\s*→\s*(.*?)$/);
  if (match) return translateUi("ИИ-инструменты: {from} → {to}", {
    from: translateActivityValue(match[1]), to: translateActivityValue(match[2]),
  });
  match = raw.match(/^Обновлено (\d+) показателей за (\d{4})$/);
  if (match) return translateUi("Обновлено {count} показателей за {year}", { count: match[1], year: match[2] });
  match = raw.match(/^Обновлено KPI за (\d{4}) · (\d+) руководителей$/);
  if (match) return translateUi("Обновлено KPI за {year} · {count} руководителей", { year: match[1], count: match[2] });
  match = raw.match(/^Удалён срез прогресса «(.*)» \((\d{4})\)$/);
  if (match) return translateUi("Удалён срез прогресса «{label}» ({year})", { label: match[1], year: match[2] });

  // Business-plan detail: metric label is canonical; amounts remain untouched.
  match = raw.match(/^(.+?) (\d{4}): (.+)$/);
  if (match) {
    const parts = match[3].split(", ").map((part) => {
      if (part === "обновлено") return translateUi("обновлено");
      if (part.startsWith("план ")) return translateUi("план {value}", { value: part.slice(5) });
      if (part.startsWith("факт ")) return translateUi("факт {value}", { value: part.slice(5) });
      return part;
    });
    return `${translateUi(match[1])} ${match[2]}: ${parts.join(", ")}`;
  }
  return raw;
}
// i18n-exempt-end

/** Locale-aware short date for notification details. */
function shortDate(s?: string | null): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return fmtDate(d, getCurrentLocale(), { includeYear: false });
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
      : to ? { kind: "text", text: translateUi("Новый статус: {status}", { status: to }) }
      : bodyDetail();
    return { verb: translateUi("Сменил статус"), accent: statusColor(p.new_status), icon: "status",
             entity: entity || titleEntity(n.title), detail };
  }
  // — Изменение срока —
  if (action === "deadline_changed" || t === "watch.deadline") {
    return { verb: translateUi("Изменил срок"), accent: C.amber, icon: "deadline", entity,
             detail: { kind: "deadline", from: shortDate(p.old_due), to: shortDate(p.new_due) } };
  }
  // — Обновление хода —
  if (action === "progress" || t === "watch.progress") {
    return { verb: translateUi("Обновил ход"), accent: C.purple, icon: "progress", entity,
             detail: p.excerpt ? { kind: "text", text: String(p.excerpt) } : bodyDetail() };
  }
  // — Результат —
  if (action === "result" || t === "watch.result") {
    return { verb: translateUi("Отметил результат"), accent: C.green, icon: "result", entity };
  }
  // — Файл (watch.comment, но в теле/заголовке — файл) —
  // i18n-exempt-start -- classification of canonical legacy notification text.
  if (t === "watch.comment" && /файл/i.test((n.title || "") + " " + (n.body || ""))) {
    return { verb: translateUi("Загрузил файл"), accent: C.deep, icon: "assign", entity, detail: bodyDetail() };
  }
  // i18n-exempt-end
  // — Комментарий —
  if (t === "watch.comment" || t === "comment.replied" || t.startsWith("comment")) {
    return { verb: t === "comment.replied" ? translateUi("Ответил на комментарий") : translateUi("Оставил комментарий"),
             accent: C.blue, icon: "comment", entity, detail: bodyDetail() };
  }
  // — Упоминание —
  if (t === "mention") {
    return { verb: translateUi("Упомянул вас"), accent: C.purple, icon: "mention", entity, detail: bodyDetail() };
  }
  // — Модерация: отправлено на согласование —
  if (t === "moderation.pending") {
    return { verb: translateUi("Отправил на согласование"), accent: C.amber, icon: "moderation",
             entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  // — Модерация: автору, что его правка ушла на согласование —
  if (t === "moderation.submitted") {
    return { verb: translateUi("Ждёт согласования"), accent: C.amber, icon: "moderation",
             entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  // — Модерация: решение автору. Бэкенд шлёт типы С префиксом
  //   (moderation.approved/rejected/review_requested), поэтому матчим обе формы —
  //   иначе ветка мертва и автор видит серый фолбэк «Уведомление» вместо
  //   зелёного «Согласовал» / красного «Отклонил» (и в колокольчике, и в тосте).
  if (t === "approved" || t === "moderation.approved") {
    return { verb: translateUi("Согласовал"), accent: C.green, icon: "result", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  if (t === "rejected" || t === "moderation.rejected") {
    return { verb: translateUi("Отклонил"), accent: C.red, icon: "moderation", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  if (t === "review_requested" || t === "moderation.review_requested") {
    return { verb: translateUi("Вернул на доработку"), accent: C.amber, icon: "moderation", entity: entity || titleEntity(n.title) || n.title || undefined, detail: bodyDetail() };
  }
  // — Дедлайны (шедулер) —
  if (t === "deadline.approaching") {
    return { verb: translateUi("Приближается срок"), accent: C.amber, icon: "deadline", entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  if (t === "deadline.missed") {
    return { verb: translateUi("Срок пропущен"), accent: C.red, icon: "deadline", entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  // — Назначение —
  if (t === "task" || t === "project" || t === "assignment" || t.includes("assign")) {
    return { verb: t === "project" ? translateUi("Назначил вам проект") : translateUi("Назначил вам задачу"), accent: C.deep, icon: "assign",
             entity: entity || titleEntity(n.title) || n.title || undefined };
  }
  // — Объявление / рассылка —
  if (t.startsWith("broadcast") || t === "system.announcement") {
    return { verb: translateUi("Объявление"), accent: C.deep, icon: "bell", entity: n.title || undefined, detail: bodyDetail() };
  }
  // — Фид активности (owner.activity: «{модуль}: {действие}», actor в аватаре) —
  if (t === "owner.activity") {
    // i18n-exempt-start -- Russian values below classify legacy persisted payloads.
    const rawVerb = String(p.verb || (n.title || "").split(":").pop() || "").trim() || "изменение";
    const label = String(p.label || (n.title || "").split(":")[0] || "").trim();
    const displayLabel = OWNER_MODULE_LABELS[label] ? translateUi(OWNER_MODULE_LABELS[label]) : label;
    // Размытые отглагольные существительные → понятный глагол прошедшего времени.
    // При создании названия новой записи нет в URL → честное «Добавил запись».
    const verbKind = /коммент/i.test(rawVerb) ? "comment"
      : /файл/i.test(rawVerb) ? "file"
      : /добав|нов/i.test(rawVerb) ? (p.entity_title ? "add" : "add-record")
      : /удал/i.test(rawVerb) ? "delete"
      : "change";
    const verb = verbKind === "comment" ? translateUi("Прокомментировал")
      : verbKind === "file" ? translateUi("Загрузил файл")
      : verbKind === "add" ? translateUi("Добавил")
      : verbKind === "add-record" ? translateUi("Добавил запись")
      : verbKind === "delete" ? translateUi("Удалил")
      : translateUi("Изменил");
    const acc = verbKind === "add" || verbKind === "add-record" ? C.green
      : verbKind === "delete" ? C.red
      : verbKind === "comment" ? C.blue
      : verbKind === "file" ? C.deep
      : C.purple;
    const ic = verbKind === "add" || verbKind === "add-record" ? "result"
      : verbKind === "delete" ? "moderation"
      : verbKind === "comment" ? "comment"
      : verbKind === "file" ? "assign"
      : "progress";
    // Сущность: конкретное название (если бэк смог его подтянуть) → «… · Задачи
    // · Компания». Компания — отдельный контекст (p.company), не дублируем, если
    // она уже и есть название записи.
    const co = p.company && p.company !== p.entity_title ? String(p.company) : "";
    const ent = p.entity_title
      ? `${p.entity_title}${displayLabel ? " · " + displayLabel : ""}${co ? " · " + co : ""}`
      : ([displayLabel, co].filter(Boolean).join(" · ") || undefined);
    // Деталь: какие поля изменены (бэк кладёт p.fields = список рус. лейблов).
    // Фильтр внутренних/служебных полей (и для СТАРЫХ уведомлений, где бэк ещё
    // не фильтровал): num, *_id, год и т.п. не несут смысла читателю.
    const HIDDEN_FIELDS = new Set([
      "num", "id", "project_id", "board_id", "parent_id", "company_id",
      "portfolio_year", "weight", "sort_order", "position", "order", "updated_at",
    ]);
    const fields = (Array.isArray(p.fields) ? p.fields : [])
      .filter((f: any) => f && !HIDDEN_FIELDS.has(String(f)) && !/_id$/.test(String(f)))
      .map((f: any) => {
        const raw = String(f);
        const key = OWNER_FIELD_LABELS[raw];
        return key ? translateUi(key) : raw;
      });
    const fieldsU = [...new Set(fields)];
    // Деталь от бэка («Выручка 2025: план 1 200, факт 1 100», «Статус: Новая →
    // Завершено») приоритетнее общей сводки «Изменено: …».
    const detail: NotifDetail | undefined = p.detail_text
      ? { kind: "text", text: translateActivityDetail(p.detail_text) }
      : fieldsU.length
      ? { kind: "text", text: translateUi("Изменено: {fields}", { fields: fieldsU.slice(0, 6).join(", ") }) }
      : undefined;
    // i18n-exempt-end
    return { verb, accent: acc, icon: ic, entity: ent, detail };
  }
  // — Фолбэк: нейтральный чип + заголовок как сущность (без дублирования) —
  return { verb: translateUi("Уведомление"), accent: C.grey, icon: "bell", entity: n.title || undefined, detail: n.body ? { kind: "text", text: n.body } : undefined };
}
