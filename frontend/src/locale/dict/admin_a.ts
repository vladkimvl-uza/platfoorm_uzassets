/**
 * Словарь администрирования (RBAC v3): карточка пользователя, сетка «Доступ к
 * модулям», роли и группы.
 *
 * Общие термины (Редактировать, Дашборд, Задачи, Отчёты, Закупки, Рейтинги,
 * Консультанты, Кредитный портфель, Бизнес-план, Инвест-проекты) живут в
 * common.ts / shell.ts и здесь НЕ дублируются — иначе ключи перетрут друг
 * друга при сборке словаря.
 *
 * Узбекский — официальная латиница (oʻ/gʻ, U+02BB); кириллица генерируется
 * транслитерацией, исключений тут нет.
 */

export const uz: Record<string, string> = {
  // ── Уровни доступа сетки (две ступени + «нет доступа») ──
  "Наблюдать": "Kuzatish",
  "Нет доступа": "Ruxsat yoʻq",
  "Для этого модуля доступен только просмотр": "Bu modul uchun faqat koʻrish mumkin",

  // ── Сетка модулей ──
  "Поиск модуля…": "Modul qidirish…",
  "{n} из {total} с доступом": "{total} tadan {n} tasida ruxsat bor",
  "Модули не найдены": "Modullar topilmadi",
  "+ персональный grant": "+ shaxsiy ruxsat",

  // ── Массовая выдача уровня (редактор ролей + создание роли) ──
  "ВСЕМ РЕДАКТИРОВАТЬ": "HAMMASIGA TAHRIRLASH",
  "ВСЕМ НАБЛЮДАТЬ": "HAMMASIGA KUZATISH",
  "СБРОС": "TOZALASH",

  // ── Источник доступа (подпись под названием модуля) ──
  "нет доступа": "ruxsat yoʻq",
  "персональный доступ": "shaxsiy ruxsat",
  "по роли: {role}": "rol boʻyicha: {role}",
  "полный доступ по роли": "rol boʻyicha toʻliq ruxsat",
  "владелец платформы": "platforma egasi",

  // ── Названия модулей, которых нет в общем словаре ──
  "Финансы (МСФО/НСБУ)": "Moliya (MHXS/BHMS)",
  "Корпуправление": "Korporativ boshqaruv",
  "Анализ закупок": "Xaridlar tahlili",
  "PMO (расписание/Гантт)": "PMO (jadval/Gantt)",
  "Мониторинг (Execution Summary)": "Monitoring (Execution Summary)",
  "AI-чат": "AI-chat",

  // ── Фидбэк сохранения ──
  "Доступ к модулям сохранён": "Modullarga ruxsat saqlandi",
  "Не удалось сохранить доступ к модулям": "Modullarga ruxsatni saqlab boʻlmadi",
};

export const en: Record<string, string> = {
  "Наблюдать": "View",
  "Нет доступа": "No access",
  "Для этого модуля доступен только просмотр": "This module supports view access only",

  "Поиск модуля…": "Search module…",
  "{n} из {total} с доступом": "{n} of {total} with access",
  "Модули не найдены": "No modules found",
  "+ персональный grant": "+ personal grant",

  "ВСЕМ РЕДАКТИРОВАТЬ": "ALL — EDIT",
  "ВСЕМ НАБЛЮДАТЬ": "ALL — VIEW",
  "СБРОС": "RESET",

  "нет доступа": "no access",
  "персональный доступ": "personal grant",
  "по роли: {role}": "by role: {role}",
  "полный доступ по роли": "full access by role",
  "владелец платформы": "platform owner",

  "Финансы (МСФО/НСБУ)": "Financials (IFRS/NAS)",
  "Корпуправление": "Governance",
  "Анализ закупок": "Procurement analysis",
  "PMO (расписание/Гантт)": "PMO (schedule/Gantt)",
  "Мониторинг (Execution Summary)": "Monitoring (Execution Summary)",
  "AI-чат": "AI chat",

  "Доступ к модулям сохранён": "Module access saved",
  "Не удалось сохранить доступ к модулям": "Could not save module access",
};
