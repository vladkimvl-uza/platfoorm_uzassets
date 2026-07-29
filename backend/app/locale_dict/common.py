"""Общий словарь бэкенда — канон терминологии (ru → uz-latn / en).

Зеркалит frontend/src/locale/dict/common.ts + частые серверные фразы
(ошибки доступа, валидация, статусы операций). Модульные словари не
дублируют эти ключи. Кириллица — транслитерацией, в CYR только исключения.
"""

UZ: dict[str, str] = {
    # ── Серверные ошибки/статусы ──
    "Недостаточно прав": "Huquqlar yetarli emas",
    "Доступ запрещён": "Ruxsat berilmagan",
    "Не найдено": "Topilmadi",
    "Файл не найден": "Fayl topilmadi",
    "Компания не найдена": "Kompaniya topilmadi",
    "Пользователь не найден": "Foydalanuvchi topilmadi",
    "Некорректный запрос": "Notoʻgʻri soʻrov",
    "Внутренняя ошибка сервера": "Serverning ichki xatoligi",
    "Сохранено": "Saqlandi",
    "Удалено": "Oʻchirildi",
    "Обновлено": "Yangilandi",
    "Отправлено": "Yuborildi",
    "Операция выполнена": "Amal bajarildi",
    "Слишком много запросов, попробуйте позже": "Soʻrovlar juda koʻp, keyinroq urinib koʻring",
    "Сессия истекла, войдите заново": "Seans muddati tugadi, qaytadan kiring",
    "Неверный логин или пароль": "Login yoki parol notoʻgʻri",

    # ── Уведомления/каналы ──
    "Уведомление": "Bildirishnoma",
    "Новое уведомление": "Yangi bildirishnoma",
    "Вас упомянули": "Sizni tilga olishdi",
    "Назначена задача": "Vazifa biriktirildi",
    "Приближается срок": "Muddat yaqinlashmoqda",
    "Срок истёк": "Muddat oʻtdi",
    "Новый комментарий": "Yangi izoh",

    # ── Базовые сущности (совпадают с фронтом) ──
    "Компания": "Kompaniya",
    "Задача": "Vazifa",
    "Проект": "Loyiha",
    "Отчёт": "Hisobot",
    "Показатель": "Koʻrsatkich",
    "План": "Reja",
    "Факт": "Fakt",
    "Прогноз": "Prognoz",
    "Год": "Yil",
    "Квартал": "Chorak",
    "Итого": "Jami",
    "Бизнес-план": "Biznes-reja",
    "Выручка": "Tushum",
    "Чистая прибыль": "Sof foyda",
    "Себестоимость": "Tannarx",
}

EN: dict[str, str] = {
    "Недостаточно прав": "Insufficient permissions",
    "Доступ запрещён": "Access denied",
    "Не найдено": "Not found",
    "Файл не найден": "File not found",
    "Компания не найдена": "Company not found",
    "Пользователь не найден": "User not found",
    "Некорректный запрос": "Invalid request",
    "Внутренняя ошибка сервера": "Internal server error",
    "Сохранено": "Saved",
    "Удалено": "Deleted",
    "Обновлено": "Updated",
    "Отправлено": "Sent",
    "Операция выполнена": "Operation completed",
    "Слишком много запросов, попробуйте позже": "Too many requests, try again later",
    "Сессия истекла, войдите заново": "Session expired, please sign in again",
    "Неверный логин или пароль": "Invalid login or password",

    "Уведомление": "Notification",
    "Новое уведомление": "New notification",
    "Вас упомянули": "You were mentioned",
    "Назначена задача": "Task assigned",
    "Приближается срок": "Deadline approaching",
    "Срок истёк": "Deadline passed",
    "Новый комментарий": "New comment",

    "Компания": "Company",
    "Задача": "Task",
    "Проект": "Project",
    "Отчёт": "Report",
    "Показатель": "Indicator",
    "План": "Plan",
    "Факт": "Actual",
    "Прогноз": "Forecast",
    "Год": "Year",
    "Квартал": "Quarter",
    "Итого": "Total",
    "Бизнес-план": "Business plan",
    "Выручка": "Revenue",
    "Чистая прибыль": "Net profit",
    "Себестоимость": "Cost of sales",
}

CYR: dict[str, str] = {
    # Заимствования, где транслит латиницы даёт неверную форму
    "Сессия истекла, войдите заново": "Сеанс муддати тугади, қайтадан киринг",
}
