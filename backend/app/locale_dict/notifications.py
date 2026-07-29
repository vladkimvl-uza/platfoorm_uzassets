"""Системные уведомления, email и Telegram (ru -> uz-latn / en).

В словарь входят только строки, создаваемые платформой. Имена, названия
компаний, комментарии и другие пользовательские/БД-значения передаются в
плейсхолдерах и не переводятся.
"""

UZ: dict[str, str] = {
    # Общая оболочка каналов
    "Откройте платформу для деталей.": "Tafsilotlar uchun platformani oching.",
    "Открыть в платформе": "Platformada ochish",
    "Открыть в платформе →": "Platformada ochish →",
    "Открыть в Mini App": "Mini App'da ochish",
    "[КРИТИЧНО]": "[JUDA MUHIM]",
    "[ВАЖНО]": "[MUHIM]",
    "[Уведомление]": "[Bildirishnoma]",
    "Принять": "Qabul qilish",
    "Отклонить": "Rad etish",
    "Утвердить": "Tasdiqlash",
    "На доработку": "Qayta ishlashga",
    "Одобрить": "Ma'qullash",
    "Ответить в чате": "Chatda javob berish",
    "Бизнес-план": "Biznes-reja",
    "Кредит": "Kredit",
    "Закупки": "Xaridlar",
    "Задачи": "Vazifalar",
    "Проекты": "Loyihalar",
    "Дедлайн": "Muddat",
    "Модерация": "Moderatsiya",
    "Безопасность": "Xavfsizlik",
    "Доступ": "Kirish huquqi",
    "Аудит": "Audit",
    "Корп. упр.": "Korporativ boshqaruv",
    "Система": "Tizim",
    "Готово": "Tayyor",
    "Требует внимания": "E'tibor talab qiladi",
    "Критично": "Juda muhim",

    # Email: оболочка, MFA, приглашение, восстановление
    "Это письмо в формате HTML. Откройте его в почтовом клиенте с поддержкой HTML.":
        "Bu xat HTML formatida. Uni HTML'ni qo'llab-quvvatlaydigan pochta dasturida oching.",
    "Единая платформа управления портфелем государственных активов":
        "Davlat aktivlari portfelini boshqarishning yagona platformasi",
    "Автоматическое письмо — отвечать не нужно. Если действие выполнили не вы — обратитесь к администратору платформы.":
        "Bu avtomatik xat, unga javob berish shart emas. Agar amalni siz bajarmagan bo'lsangiz, platforma administratoriga murojaat qiling.",
    "Аккаунт": "Akkaunt",
    "IP-адрес": "IP manzil",
    "Время": "Vaqt",
    "Ваш одноразовый код для входа на платформу UzAssets:":
        "UzAssets platformasiga kirish uchun bir martalik kodingiz:",
    "Код действителен <b>5 минут</b>. Никому не сообщайте его — сотрудники UzAssets никогда не запрашивают код.":
        "Kod <b>5 daqiqa</b> amal qiladi. Uni hech kimga bermang — UzAssets xodimlari hech qachon kodni so'ramaydi.",
    "Код доступа": "Kirish kodi",
    "Код подтверждения входа": "Kirishni tasdiqlash kodi",
    "UzAssets · код доступа": "UzAssets · kirish kodi",
    "Здравствуйте, <b>{full_name}</b>! Для вас создан доступ к платформе UzAssets.":
        "Assalomu alaykum, <b>{full_name}</b>! Siz uchun UzAssets platformasiga kirish yaratildi.",
    "Логин (email)": "Login (email)",
    "Временный пароль:": "Vaqtinchalik parol:",
    "При первом входе система попросит <b>сменить пароль</b>.":
        "Birinchi kirishda tizim <b>parolni o'zgartirishni</b> so'raydi.",
    "Войти на платформу": "Platformaga kirish",
    "Если кнопка не работает, откройте ссылку: {url}":
        "Agar tugma ishlamasa, havolani oching: {url}",
    "Приглашение": "Taklif",
    "Доступ к платформе UzAssets": "UzAssets platformasiga kirish",
    "UzAssets · доступ к платформе": "UzAssets · platformaga kirish",
    "Здравствуйте, <b>{full_name}</b>. Мы получили запрос на сброс пароля для вашего аккаунта UzAssets.":
        "Assalomu alaykum, <b>{full_name}</b>. UzAssets akkauntingiz parolini tiklash so'rovini oldik.",
    "Сбросить пароль": "Parolni tiklash",
    "Ссылка действительна <b>{minutes} минут</b>. Если вы не запрашивали сброс — просто проигнорируйте письмо, пароль останется прежним.":
        "Havola <b>{minutes} daqiqa</b> amal qiladi. Agar tiklashni so'ramagan bo'lsangiz, xatni e'tiborsiz qoldiring — parol o'zgarmaydi.",
    "Сброс пароля": "Parolni tiklash",
    "Восстановление доступа": "Kirishni tiklash",
    "UzAssets · сброс пароля": "UzAssets · parolni tiklash",
    "Проверка": "Tekshiruv",
    "Тестовое письмо UzAssets": "UzAssets sinov xati",
    "Это тестовое письмо из интерфейса настройки почты.":
        "Bu pochta sozlamalari interfeysidan yuborilgan sinov xati.",
    "Если вы его получили — SMTP настроен корректно, уведомления будут доставляться.":
        "Agar xatni olgan bo'lsangiz, SMTP to'g'ri sozlangan va bildirishnomalar yetkaziladi.",
    "Не удалось отправить письмо. Проверьте, что SMTP включён и параметры верны (детали — в логах backend).":
        "Xatni yuborib bo'lmadi. SMTP yoqilganini va parametrlar to'g'riligini tekshiring (tafsilotlar backend loglarida).",

    # Задачи, заметки, упоминания и комментарии
    "Задача назначена: {title}": "Vazifa biriktirildi: {title}",
    "Новая задача: {title}": "Yangi vazifa: {title}",
    "Статус задачи: {title}": "Vazifa holati: {title}",
    "Не начато": "Boshlanmagan",
    "Инициирование": "Boshlash",
    "В процессе": "Jarayonda",
    "На согласовании": "Kelishuvda",
    "Завершено": "Yakunlangan",
    "Ежеквартально": "Har chorakda",
    "Ежемесячно": "Har oyda",
    "Постоянно": "Doimiy",
    "Перенесено": "Ko'chirilgan",
    "Вы ответственный: {title}": "Siz mas'ulsiz: {title}",
    "{actor} назначил(а) вас ответственным · {kind}":
        "{actor} sizni mas'ul etib tayinladi · {kind}",
    "Пункт назначен на вас: {item}": "Band sizga biriktirildi: {item}",
    "{actor} · в заметке «{title}»": "{actor} · «{title}» qaydida",
    "Событие": "Hodisa",
    "Решение": "Qaror",
    "Риск": "Xavf",
    "Наблюдение": "Kuzatuv",
    "Запись": "Qayd",
    "Заметка": "Qayd",
    "Кто-то": "Kimdir",
    "(без названия)": "(nomsiz)",
    "задаче": "vazifada",
    "проекте": "loyihada",
    "комментарии": "izohda",
    "записи": "qaydda",
    "{actor} упомянул вас в {kind}: «{entity}»{company}":
        "{actor} sizni {kind} tilga oldi: «{entity}»{company}",
    "{actor} оставил комментарий в {kind}: «{entity}»{company}":
        "{actor} {kind} izoh qoldirdi: «{entity}»{company}",

    # Отслеживание проектов и задач
    "Файл в отслеживаемой задаче": "Kuzatilayotgan vazifadagi fayl",
    "Файл в отслеживаемом проекте": "Kuzatilayotgan loyihadagi fayl",
    "{actor} загрузил(а) файл: {filename}": "{actor} fayl yukladi: {filename}",
    "Новый комментарий в отслеживаемом {kind}":
        "Kuzatilayotgan {kind} yangi izoh",
    "проекта": "loyihada",
    "задачи": "vazifada",
    "Статус отслеживаемой задачи изменён":
        "Kuzatilayotgan vazifa holati o'zgartirildi",
    "Статус отслеживаемого проекта изменён":
        "Kuzatilayotgan loyiha holati o'zgartirildi",
    "{actor}: новый статус «{status}»": "{actor}: yangi holat «{status}»",
    "Результат отслеживаемого проекта обновлён":
        "Kuzatilayotgan loyiha natijasi yangilandi",
    "Результат отслеживаемой задачи обновлён":
        "Kuzatilayotgan vazifa natijasi yangilandi",
    "{actor} отметил(а) результат": "{actor} natijani belgiladi",
    "Обновлён ход отслеживаемого {kind}":
        "Kuzatilayotgan {kind} jarayoni yangilandi",
    "Срок отслеживаемой задачи изменён":
        "Kuzatilayotgan vazifa muddati o'zgartirildi",

    # Дедлайны
    "До дедлайна {days} дн: {title}": "Muddatgacha {days} kun: {title}",
    "{kind} · срок через {days} дн — {date}":
        "{kind} · muddat {days} kundan so'ng — {date}",
    "Дедлайн завтра: {title}": "Muddat ertaga: {title}",
    "{kind} · срок завтра, {date}": "{kind} · muddat ertaga, {date}",
    "Дедлайн приближается: {title}": "Muddat yaqinlashmoqda: {title}",
    "{kind} · до {date} ({days} дн)": "{kind} · {date} gacha ({days} kun)",
    "{kind} · до {date} (сегодня)": "{kind} · {date} gacha (bugun)",
    "Дедлайн пропущен: {title}": "Muddat o'tkazib yuborildi: {title}",
    "{kind} · просрочено {days} дн (до {date})":
        "{kind} · {days} kun kechikkan ({date} gacha)",

    # Модерация и системные уведомления
    "Новое предложение: {entity}": "Yangi taklif: {entity}",
    "Открыть в очереди модерации": "Moderatsiya navbatida ochish",
    "Ваше предложение одобрено": "Taklifingiz ma'qullandi",
    "Ваше предложение отклонено": "Taklifingiz rad etildi",
    "Запрошено дополнительное рассмотрение": "Qo'shimcha ko'rib chiqish so'raldi",
    "Комментарий в модерации: {entity}": "Moderatsiyadagi izoh: {entity}",
    "Тестовое уведомление": "Sinov bildirishnomasi",
    "Если вы это видите — система уведомлений работает корректно.":
        "Agar buni ko'rayotgan bo'lsangiz, bildirishnomalar tizimi to'g'ri ishlamoqda.",
    "Новый вход в аккаунт": "Akkauntga yangi kirish",
    "Выполнен вход с нового IP-адреса {ip} · {device}. Если это были не вы — смените пароль и обратитесь к администратору.":
        "Yangi {ip} IP manzilidan kirildi · {device}. Agar bu siz bo'lmasangiz, parolni o'zgartiring va administratorga murojaat qiling.",
    "Выполнен вход с нового IP-адреса {ip} · {browser} · {os}. Если это были не вы — смените пароль и обратитесь к администратору.":
        "Yangi {ip} IP manzilidan kirildi · {browser} · {os}. Agar bu siz bo'lmasangiz, parolni o'zgartiring va administratorga murojaat qiling.",
    "неизвестное устройство": "noma'lum qurilma",
    "браузер": "brauzer",
    "Пароль изменён": "Parol o'zgartirildi",
    "Пароль вашего аккаунта был сброшен. Если это были не вы — немедленно обратитесь к администратору.":
        "Akkauntingiz paroli tiklandi. Agar bu siz bo'lmasangiz, darhol administratorga murojaat qiling.",
    "Код восстановления пароля": "Parolni tiklash kodi",
    "Код отправлен в Telegram.": "Kod Telegram'ga yuborildi.",
    "Код отправлен на email.": "Kod email manziliga yuborildi.",
    "Ваш код для восстановления доступа: {code}": "Kirishni tiklash kodingiz: {code}",
    "Код действителен {minutes} минут. Если вы не запрашивали сброс — проигнорируйте письмо.":
        "Kod {minutes} daqiqa amal qiladi. Agar tiklashni so'ramagan bo'lsangiz, xatni e'tiborsiz qoldiring.",
    "Аккаунт с таким email или логином не найден.":
        "Bunday email yoki loginli akkaunt topilmadi.",
    "К аккаунту не привязан Telegram.": "Akkauntga Telegram ulanmagan.",
    "Отправка на email недоступна.": "Email orqali yuborish mavjud emas.",
    "Нет доступного канала восстановления. Обратитесь к администратору.":
        "Tiklash uchun mavjud kanal yo'q. Administratorga murojaat qiling.",
    "Неверный код или истёк срок действия": "Kod noto'g'ri yoki muddati tugagan",
    "Код истёк. Запросите новый.": "Kod muddati tugagan. Yangi kod so'rang.",
    "Превышено количество попыток. Запросите новый код.":
        "Urinishlar soni oshib ketdi. Yangi kod so'rang.",
    "Неверный код. Осталось попыток: {remaining}":
        "Kod noto'g'ri. Qolgan urinishlar: {remaining}",
    "Telegram должен быть привязан до включения 2FA. Сначала вызовите /mfa/link-telegram.":
        "2FA'ni yoqishdan oldin Telegram ulanishi kerak. Avval /mfa/link-telegram ni chaqiring.",
    "Введите recovery code для подтверждения отключения 2FA.":
        "2FA'ni o'chirishni tasdiqlash uchun tiklash kodini kiriting.",
    "Подтверждение обязательно (передайте confirm=true).":
        "Tasdiqlash shart (confirm=true qiymatini yuboring).",
    "2FA должна быть включена для генерации recovery codes.":
        "Tiklash kodlarini yaratish uchun 2FA yoqilgan bo'lishi kerak.",
    "Telegram не привязан. Сначала /mfa/link-telegram.":
        "Telegram ulanmagan. Avval /mfa/link-telegram ni chaqiring.",
    "Тестовое уведомление UzAssets": "UzAssets sinov bildirishnomasi",
    "Если вы видите это сообщение, доставка через Telegram настроена корректно.":
        "Agar bu xabarni ko'rayotgan bo'lsangiz, Telegram orqali yetkazish to'g'ri sozlangan.",
    "Telegram должен быть привязан до отправки кода.":
        "Kod yuborilishidan oldin Telegram ulanishi kerak.",
    "Неверный код или срок действия истёк. Запросите код заново.":
        "Kod noto'g'ri yoki muddati tugagan. Yangi kod so'rang.",
}

EN: dict[str, str] = {
    "Откройте платформу для деталей.": "Open the platform for details.",
    "Открыть в платформе": "Open in platform",
    "Открыть в платформе →": "Open in platform →",
    "Открыть в Mini App": "Open in Mini App",
    "[КРИТИЧНО]": "[CRITICAL]",
    "[ВАЖНО]": "[IMPORTANT]",
    "[Уведомление]": "[Notification]",
    "Принять": "Accept",
    "Отклонить": "Reject",
    "Утвердить": "Approve",
    "На доработку": "Request changes",
    "Одобрить": "Approve",
    "Ответить в чате": "Reply in chat",
    "Бизнес-план": "Business plan",
    "Кредит": "Credit",
    "Закупки": "Procurement",
    "Задачи": "Tasks",
    "Проекты": "Projects",
    "Дедлайн": "Deadline",
    "Модерация": "Moderation",
    "Безопасность": "Security",
    "Доступ": "Access",
    "Аудит": "Audit",
    "Корп. упр.": "Corporate governance",
    "Система": "System",
    "Готово": "Complete",
    "Требует внимания": "Requires attention",
    "Критично": "Critical",

    "Это письмо в формате HTML. Откройте его в почтовом клиенте с поддержкой HTML.":
        "This message is in HTML format. Open it in an email client that supports HTML.",
    "Единая платформа управления портфелем государственных активов":
        "Unified public asset portfolio management platform",
    "Автоматическое письмо — отвечать не нужно. Если действие выполнили не вы — обратитесь к администратору платформы.":
        "This is an automated email; no reply is needed. If you did not perform the action, contact the platform administrator.",
    "Аккаунт": "Account",
    "IP-адрес": "IP address",
    "Время": "Time",
    "Ваш одноразовый код для входа на платформу UzAssets:":
        "Your one-time code for signing in to the UzAssets platform:",
    "Код действителен <b>5 минут</b>. Никому не сообщайте его — сотрудники UzAssets никогда не запрашивают код.":
        "The code is valid for <b>5 minutes</b>. Do not share it; UzAssets staff will never ask for this code.",
    "Код доступа": "Access code",
    "Код подтверждения входа": "Sign-in verification code",
    "UzAssets · код доступа": "UzAssets · access code",
    "Здравствуйте, <b>{full_name}</b>! Для вас создан доступ к платформе UzAssets.":
        "Hello, <b>{full_name}</b>! Access to the UzAssets platform has been created for you.",
    "Логин (email)": "Login (email)",
    "Временный пароль:": "Temporary password:",
    "При первом входе система попросит <b>сменить пароль</b>.":
        "You will be asked to <b>change your password</b> when you first sign in.",
    "Войти на платформу": "Sign in to the platform",
    "Если кнопка не работает, откройте ссылку: {url}":
        "If the button does not work, open this link: {url}",
    "Приглашение": "Invitation",
    "Доступ к платформе UzAssets": "Access to the UzAssets platform",
    "UzAssets · доступ к платформе": "UzAssets · platform access",
    "Здравствуйте, <b>{full_name}</b>. Мы получили запрос на сброс пароля для вашего аккаунта UzAssets.":
        "Hello, <b>{full_name}</b>. We received a request to reset the password for your UzAssets account.",
    "Сбросить пароль": "Reset password",
    "Ссылка действительна <b>{minutes} минут</b>. Если вы не запрашивали сброс — просто проигнорируйте письмо, пароль останется прежним.":
        "The link is valid for <b>{minutes} minutes</b>. If you did not request a reset, ignore this email and your password will remain unchanged.",
    "Сброс пароля": "Password reset",
    "Восстановление доступа": "Restore access",
    "UzAssets · сброс пароля": "UzAssets · password reset",
    "Проверка": "Test",
    "Тестовое письмо UzAssets": "UzAssets test email",
    "Это тестовое письмо из интерфейса настройки почты.":
        "This is a test email from the mail settings interface.",
    "Если вы его получили — SMTP настроен корректно, уведомления будут доставляться.":
        "If you received it, SMTP is configured correctly and notifications will be delivered.",
    "Не удалось отправить письмо. Проверьте, что SMTP включён и параметры верны (детали — в логах backend).":
        "The email could not be sent. Check that SMTP is enabled and the settings are correct (see backend logs for details).",

    "Задача назначена: {title}": "Task assigned: {title}",
    "Новая задача: {title}": "New task: {title}",
    "Статус задачи: {title}": "Task status: {title}",
    "Не начато": "Not started",
    "Инициирование": "Initiation",
    "В процессе": "In progress",
    "На согласовании": "Under review",
    "Завершено": "Completed",
    "Ежеквартально": "Quarterly",
    "Ежемесячно": "Monthly",
    "Постоянно": "Ongoing",
    "Перенесено": "Deferred",
    "Вы ответственный: {title}": "You are responsible: {title}",
    "{actor} назначил(а) вас ответственным · {kind}":
        "{actor} assigned you as the responsible person · {kind}",
    "Пункт назначен на вас: {item}": "Item assigned to you: {item}",
    "{actor} · в заметке «{title}»": "{actor} · in note “{title}”",
    "Событие": "Event",
    "Решение": "Decision",
    "Риск": "Risk",
    "Наблюдение": "Observation",
    "Запись": "Entry",
    "Заметка": "Note",
    "Кто-то": "Someone",
    "(без названия)": "(untitled)",
    "задаче": "task",
    "проекте": "project",
    "комментарии": "comment",
    "записи": "entry",
    "{actor} упомянул вас в {kind}: «{entity}»{company}":
        "{actor} mentioned you in the {kind}: “{entity}”{company}",
    "{actor} оставил комментарий в {kind}: «{entity}»{company}":
        "{actor} left a comment in the {kind}: “{entity}”{company}",

    "Файл в отслеживаемой задаче": "File in a watched task",
    "Файл в отслеживаемом проекте": "File in a watched project",
    "{actor} загрузил(а) файл: {filename}": "{actor} uploaded a file: {filename}",
    "Новый комментарий в отслеживаемом {kind}":
        "New comment in a watched {kind}",
    "проекта": "project",
    "задачи": "task",
    "Статус отслеживаемой задачи изменён": "Watched task status changed",
    "Статус отслеживаемого проекта изменён": "Watched project status changed",
    "{actor}: новый статус «{status}»": "{actor}: new status “{status}”",
    "Результат отслеживаемого проекта обновлён": "Watched project result updated",
    "Результат отслеживаемой задачи обновлён": "Watched task result updated",
    "{actor} отметил(а) результат": "{actor} marked the result",
    "Обновлён ход отслеживаемого {kind}": "Watched {kind} progress updated",
    "Срок отслеживаемой задачи изменён": "Watched task deadline changed",

    "До дедлайна {days} дн: {title}": "{days} days until deadline: {title}",
    "{kind} · срок через {days} дн — {date}":
        "{kind} · due in {days} days — {date}",
    "Дедлайн завтра: {title}": "Deadline tomorrow: {title}",
    "{kind} · срок завтра, {date}": "{kind} · due tomorrow, {date}",
    "Дедлайн приближается: {title}": "Deadline approaching: {title}",
    "{kind} · до {date} ({days} дн)": "{kind} · due {date} ({days} days)",
    "{kind} · до {date} (сегодня)": "{kind} · due {date} (today)",
    "Дедлайн пропущен: {title}": "Deadline missed: {title}",
    "{kind} · просрочено {days} дн (до {date})":
        "{kind} · {days} days overdue (due {date})",

    "Новое предложение: {entity}": "New proposal: {entity}",
    "Открыть в очереди модерации": "Open in moderation queue",
    "Ваше предложение одобрено": "Your proposal was approved",
    "Ваше предложение отклонено": "Your proposal was rejected",
    "Запрошено дополнительное рассмотрение": "Additional review requested",
    "Комментарий в модерации: {entity}": "Moderation comment: {entity}",
    "Тестовое уведомление": "Test notification",
    "Если вы это видите — система уведомлений работает корректно.":
        "If you can see this, the notification system is working correctly.",
    "Новый вход в аккаунт": "New account sign-in",
    "Выполнен вход с нового IP-адреса {ip} · {device}. Если это были не вы — смените пароль и обратитесь к администратору.":
        "A sign-in was made from a new IP address {ip} · {device}. If this was not you, change your password and contact the administrator.",
    "Выполнен вход с нового IP-адреса {ip} · {browser} · {os}. Если это были не вы — смените пароль и обратитесь к администратору.":
        "A sign-in was made from a new IP address {ip} · {browser} · {os}. If this was not you, change your password and contact the administrator.",
    "неизвестное устройство": "unknown device",
    "браузер": "browser",
    "Пароль изменён": "Password changed",
    "Пароль вашего аккаунта был сброшен. Если это были не вы — немедленно обратитесь к администратору.":
        "Your account password was reset. If this was not you, contact the administrator immediately.",
    "Код восстановления пароля": "Password recovery code",
    "Код отправлен в Telegram.": "The code was sent to Telegram.",
    "Код отправлен на email.": "The code was sent by email.",
    "Ваш код для восстановления доступа: {code}": "Your access recovery code: {code}",
    "Код действителен {minutes} минут. Если вы не запрашивали сброс — проигнорируйте письмо.":
        "The code is valid for {minutes} minutes. If you did not request a reset, ignore this email.",
    "Аккаунт с таким email или логином не найден.":
        "No account was found with that email or login.",
    "К аккаунту не привязан Telegram.": "Telegram is not linked to the account.",
    "Отправка на email недоступна.": "Email delivery is unavailable.",
    "Нет доступного канала восстановления. Обратитесь к администратору.":
        "No recovery channel is available. Contact the administrator.",
    "Неверный код или истёк срок действия": "The code is invalid or has expired",
    "Код истёк. Запросите новый.": "The code has expired. Request a new one.",
    "Превышено количество попыток. Запросите новый код.":
        "Too many attempts. Request a new code.",
    "Неверный код. Осталось попыток: {remaining}":
        "Invalid code. Attempts remaining: {remaining}",
    "Telegram должен быть привязан до включения 2FA. Сначала вызовите /mfa/link-telegram.":
        "Telegram must be linked before enabling 2FA. Call /mfa/link-telegram first.",
    "Введите recovery code для подтверждения отключения 2FA.":
        "Enter a recovery code to confirm that 2FA should be disabled.",
    "Подтверждение обязательно (передайте confirm=true).":
        "Confirmation is required (send confirm=true).",
    "2FA должна быть включена для генерации recovery codes.":
        "2FA must be enabled to generate recovery codes.",
    "Telegram не привязан. Сначала /mfa/link-telegram.":
        "Telegram is not linked. Call /mfa/link-telegram first.",
    "Тестовое уведомление UzAssets": "UzAssets test notification",
    "Если вы видите это сообщение, доставка через Telegram настроена корректно.":
        "If you can see this message, Telegram delivery is configured correctly.",
    "Telegram должен быть привязан до отправки кода.":
        "Telegram must be linked before sending a code.",
    "Неверный код или срок действия истёк. Запросите код заново.":
        "The code is invalid or has expired. Request a new code.",
}

CYR: dict[str, str] = {}
