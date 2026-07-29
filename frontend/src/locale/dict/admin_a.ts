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
  // «Удельная себестоимость» и «Сводный обзор портфеля» уже переведены в
  // shell.ts / controltower.ts — здесь не дублируем (ключи перетёрлись бы).
  "Финансы (МСФО/НСБУ)": "Moliya (MHXS/BHMS)",
  "Экран министра (Executive Dashboard)": "Vazir ekrani (Executive Dashboard)",
  "SOE Health Check Tool": "SOE Health Check Tool",
  "Корпуправление": "Korporativ boshqaruv",
  "Анализ закупок": "Xaridlar tahlili",
  "PMO (расписание/Гантт)": "PMO (jadval/Gantt)",
  "Мониторинг (Execution Summary)": "Monitoring (Execution Summary)",
  "AI-чат": "AI-chat",

  // ── Фидбэк сохранения ──
  "Доступ к модулям сохранён": "Modullarga ruxsat saqlandi",
  "Не удалось сохранить доступ к модулям": "Modullarga ruxsatni saqlab boʻlmadi",

  // ── Реестр пользователей ──
  "{age} дн. без смены": "{age} kun davomida oʻzgartirilmagan",
  "Активности ещё не было": "Hali faollik kuzatilmagan",
  "Активность": "Faollik",
  "Активны: {count}": "Faol: {count}",
  "Активные": "Faol",
  "Без назначенных ролей": "Tayinlangan rollarsiz",
  "Без подразделения": "Boʻlinma koʻrsatilmagan",
  "Без привязки к компании": "Kompaniyaga biriktirilmagan",
  "Без ролей": "Rollarsiz",
  "Владелец": "Egasi",
  "Всего пользователей": "Jami foydalanuvchilar",
  "Выбрать {name}": "Tanlash: {name}",
  "Выбрать видимые записи": "Koʻrinib turgan yozuvlarni tanlash",
  "Выбрать всех видимых пользователей": "Koʻrinib turgan barcha foydalanuvchilarni tanlash",
  "Выбрать пользователей компании {company}": "{company} kompaniyasi foydalanuvchilarini tanlash",
  "Данные актуальны": "Maʼlumotlar dolzarb",
  "Деактивация...": "Faolsizlantirilmoqda...",
  "Деактивировано: {completed}; не удалось: {failed}. Причина: {reason}":
    "Faolsizlantirildi: {completed}; bajarilmadi: {failed}. Sabab: {reason}",
  "Деактивировать": "Faolsizlantirish",
  "Деактивировать выбранных пользователей: {count}? Активные сессии будут отозваны, пользователей можно реактивировать позже.":
    "Tanlangan foydalanuvchilar faolsizlantirilsinmi: {count}? Faol seanslar bekor qilinadi, foydalanuvchilarni keyinroq qayta faollashtirish mumkin.",
  "Действия применятся ко всем отмеченным": "Amallar barcha belgilanganlarga qoʻllanadi",
  "Для этого фильтра пока нет записей.": "Bu filtr uchun hozircha yozuvlar yoʻq.",
  "Есть входы": "Kirishlar mavjud",
  "Заблокированные": "Bloklangan",
  "Заблокированы: {count}": "Bloklangan: {count}",
  "Загружено {loaded} из {total} записей. Для точного результата уточните поиск.":
    "{total} yozuvdan {loaded} tasi yuklandi. Aniq natija olish uchun qidiruvni aniqlashtiring.",
  "Закрыть карточку пользователя": "Foydalanuvchi kartasini yopish",
  "Измените запрос или очистите поиск.": "Soʻrovni oʻzgartiring yoki qidiruvni tozalang.",
  "Изменить роли": "Rollarni oʻzgartirish",
  "Имя, email, подразделение": "Ism, email, boʻlinma",
  "Истекает · {age} дн.": "Muddati tugamoqda · {age} kun",
  "Найдено: {shown} из {total}": "Topildi: {shown} / {total}",
  "Найдено: {shown} из {total} · Компаний: {companies}":
    "Topildi: {shown} / {total} · Kompaniyalar: {companies}",
  "Не входил": "Tizimga kirmagan",
  "Не удалось загрузить пользователей": "Foydalanuvchilarni yuklab boʻlmadi",
  "Не указана": "Koʻrsatilmagan",
  "Нет истории входа": "Kirish tarixi yoʻq",
  "Ни разу не входил": "Hali tizimga kirmagan",
  "Область": "Qamrov",
  "Обновить список": "Roʻyxatni yangilash",
  "Обновление": "Yangilanmoqda",
  "Открыть карточку пользователя {name}": "{name} foydalanuvchi kartasini ochish",
  "Очистить поиск": "Qidiruvni tozalash",
  "По активности": "Faollik boʻyicha",
  "Подразделение": "Boʻlinma",
  "Показано: {shown} · Загружено: {loaded} из {total}":
    "Koʻrsatildi: {shown} · Yuklandi: {loaded} / {total}",
  "Показано: {shown} · Загружено: {loaded} из {total} · Компаний: {companies}":
    "Koʻrsatildi: {shown} · Yuklandi: {loaded} / {total} · Kompaniyalar: {companies}",
  "Показано: {shown} из {total}": "Koʻrsatildi: {shown} / {total}",
  "Показано: {shown} из {total} · Компаний: {companies}":
    "Koʻrsatildi: {shown} / {total} · Kompaniyalar: {companies}",
  "Показать единым списком": "Yagona roʻyxatda koʻrsatish",
  "Показать: {label}": "Koʻrsatish: {label}",
  "Пользователей: {count}": "Foydalanuvchilar: {count}",
  "Пользователи не найдены": "Foydalanuvchilar topilmadi",
  "Последний вход: {date}": "Oxirgi kirish: {date}",
  "Последняя активность: {date}": "Oxirgi faollik: {date}",
  "Представление пользователей": "Foydalanuvchilar koʻrinishi",
  "Развернуть компанию {company}": "{company} kompaniyasini yoyish",
  "Реестр доступа": "Ruxsatlar reyestri",
  "Роли": "Rollar",
  "Роли не назначены": "Rollar tayinlanmagan",
  "Роль в компании": "Kompaniyadagi rol",
  "Свернуть компанию {company}": "{company} kompaniyasini yigʻish",
  "Сводка по пользователям": "Foydalanuvchilar boʻyicha jamlama",
  "Сгруппировать по компаниям доступа": "Ruxsat kompaniyalari boʻyicha guruhlash",
  "Сначала новые": "Avval yangilari",
  "Сортировка": "Saralash",
  "Сортировка пользователей": "Foydalanuvchilarni saralash",
  "Список пользователей": "Foydalanuvchilar roʻyxati",
  "Статус пользователей": "Foydalanuvchilar holati",
  "Требуется смена": "Oʻzgartirish talab etiladi",
  "Требуют внимания: {count}": "Eʼtibor talab qiladi: {count}",
  "Учётные записи, роли и состояние безопасности": "Hisoblar, rollar va xavfsizlik holati",
  "Фильтры пользователей": "Foydalanuvchi filtrlari",
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
  "Экран министра (Executive Dashboard)": "Executive Dashboard",
  "SOE Health Check Tool": "SOE Health Check Tool",
  "Корпуправление": "Governance",
  "Анализ закупок": "Procurement analysis",
  "PMO (расписание/Гантт)": "PMO (schedule/Gantt)",
  "Мониторинг (Execution Summary)": "Monitoring (Execution Summary)",
  "AI-чат": "AI chat",

  "Доступ к модулям сохранён": "Module access saved",
  "Не удалось сохранить доступ к модулям": "Could not save module access",

  "{age} дн. без смены": "Unchanged for {age} days",
  "Активности ещё не было": "No activity yet",
  "Активность": "Activity",
  "Активны: {count}": "Active: {count}",
  "Активные": "Active",
  "Без назначенных ролей": "No assigned roles",
  "Без подразделения": "No department",
  "Без привязки к компании": "Not linked to a company",
  "Без ролей": "No roles",
  "Владелец": "Owner",
  "Всего пользователей": "Total users",
  "Выбрать {name}": "Select {name}",
  "Выбрать видимые записи": "Select visible records",
  "Выбрать всех видимых пользователей": "Select all visible users",
  "Выбрать пользователей компании {company}": "Select users from {company}",
  "Данные актуальны": "Data is up to date",
  "Деактивация...": "Deactivating...",
  "Деактивировано: {completed}; не удалось: {failed}. Причина: {reason}":
    "Deactivated: {completed}; failed: {failed}. Reason: {reason}",
  "Деактивировать": "Deactivate",
  "Деактивировать выбранных пользователей: {count}? Активные сессии будут отозваны, пользователей можно реактивировать позже.":
    "Deactivate selected users: {count}? Active sessions will be revoked, and users can be reactivated later.",
  "Действия применятся ко всем отмеченным": "Actions apply to all selected users",
  "Для этого фильтра пока нет записей.": "There are no records for this filter yet.",
  "Есть входы": "Login history available",
  "Заблокированные": "Blocked",
  "Заблокированы: {count}": "Blocked: {count}",
  "Загружено {loaded} из {total} записей. Для точного результата уточните поиск.":
    "Loaded {loaded} of {total} records. Refine your search for an exact result.",
  "Закрыть карточку пользователя": "Close user details",
  "Измените запрос или очистите поиск.": "Change the query or clear the search.",
  "Изменить роли": "Change roles",
  "Имя, email, подразделение": "Name, email, department",
  "Истекает · {age} дн.": "Expiring · {age} days",
  "Найдено: {shown} из {total}": "Found: {shown} of {total}",
  "Найдено: {shown} из {total} · Компаний: {companies}":
    "Found: {shown} of {total} · Companies: {companies}",
  "Не входил": "Never signed in",
  "Не удалось загрузить пользователей": "Could not load users",
  "Не указана": "Not specified",
  "Нет истории входа": "No login history",
  "Ни разу не входил": "Never signed in",
  "Область": "Scope",
  "Обновить список": "Refresh list",
  "Обновление": "Updating",
  "Открыть карточку пользователя {name}": "Open details for {name}",
  "Очистить поиск": "Clear search",
  "По активности": "By activity",
  "Подразделение": "Department",
  "Показано: {shown} · Загружено: {loaded} из {total}":
    "Showing: {shown} · Loaded: {loaded} of {total}",
  "Показано: {shown} · Загружено: {loaded} из {total} · Компаний: {companies}":
    "Showing: {shown} · Loaded: {loaded} of {total} · Companies: {companies}",
  "Показано: {shown} из {total}": "Showing: {shown} of {total}",
  "Показано: {shown} из {total} · Компаний: {companies}":
    "Showing: {shown} of {total} · Companies: {companies}",
  "Показать единым списком": "Show as a single list",
  "Показать: {label}": "Show: {label}",
  "Пользователей: {count}": "Users: {count}",
  "Пользователи не найдены": "No users found",
  "Последний вход: {date}": "Last sign-in: {date}",
  "Последняя активность: {date}": "Last activity: {date}",
  "Представление пользователей": "User view",
  "Развернуть компанию {company}": "Expand {company}",
  "Реестр доступа": "Access registry",
  "Роли": "Roles",
  "Роли не назначены": "No roles assigned",
  "Роль в компании": "Company role",
  "Свернуть компанию {company}": "Collapse {company}",
  "Сводка по пользователям": "User summary",
  "Сгруппировать по компаниям доступа": "Group by access company",
  "Сначала новые": "Newest first",
  "Сортировка": "Sort",
  "Сортировка пользователей": "Sort users",
  "Список пользователей": "User list",
  "Статус пользователей": "User status",
  "Требуется смена": "Change required",
  "Требуют внимания: {count}": "Need attention: {count}",
  "Учётные записи, роли и состояние безопасности": "Accounts, roles, and security status",
  "Фильтры пользователей": "User filters",
};
