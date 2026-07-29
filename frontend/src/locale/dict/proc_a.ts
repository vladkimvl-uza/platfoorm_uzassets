/**
 * proc_a — словарь модуля «Закупки» (часть A): таблица сравнения компаний,
 * профиль компании, форензик-редактор/импорт, сетка категорий, лидеры.
 * Общие термины (Сохранить/Отмена/План/Факт/сум/…) — в common.ts, здесь их НЕТ.
 */

export const uz: Record<string, string> = {
  // ── CategoryCompareTable ──
  "Сравнение компаний": "Kompaniyalarni taqqoslash",
  "Рейтинг по среднему отклонению": "Oʻrtacha ogʻish boʻyicha reyting",
  "1 строка на компанию · sparkline = отклонения по 15 категориям · высота столбика = модуль отклонения, цвет = знак":
    "1 qator = 1 kompaniya · sparkline = 15 kategoriya boʻyicha ogʻishlar · ustun balandligi = ogʻish moduli, rang = ishora",
  "Топ:": "Top:",
  "Откл. ср.": "Oʻrt. ogʻish",
  "Переплата": "Ortiqcha toʻlov",
  "Откл. по 15 категориям": "15 kategoriya boʻyicha ogʻish",
  "Красных": "Qizil",
  "Объём": "Hajm",
  "Нет компаний для сравнения": "Taqqoslash uchun kompaniyalar yoʻq",
  "Показано {shown} из {total} компаний · клик по строке — профиль компании":
    "{total} kompaniyadan {shown} tasi koʻrsatilgan · qator ustiga bosish — kompaniya profili",
  "нет данных": "maʼlumot yoʻq",

  // ── CompanyProfileModal ──
  "Ранг": "Oʻrin",
  "Средн. отклонение": "Oʻrtacha ogʻish",
  "Экономия": "Tejash",
  "Категорий": "Kategoriyalar",
  "Закупок": "Xaridlar",
  "Обзор": "Sharh",
  "Категории": "Kategoriyalar",
  "Поставщики": "Yetkazib beruvchilar",
  "Отклонение цен по категориям": "Kategoriyalar boʻyicha narx ogʻishi",
  "по сопоставимым товарам · база {sum} сум": "taqqoslanadigan tovarlar boʻyicha · baza {sum} soʻm",
  "Категория": "Kategoriya",
  "Объём (сум)": "Hajm (soʻm)",
  "Median рынка": "Bozor medianasi",
  "Δ сумма": "Δ summa",
  "Нет поставщиков": "Yetkazib beruvchilar yoʻq",
  "Поставщик": "Yetkazib beruvchi",
  "Цена / ед.": "Narx / birlik",
  "Подробнее о закупке": "Xarid haqida batafsil",
  "ед": "birlik",
  "Услуга/работа или несопоставимый код — отклонение по цене за единицу неинформативно":
    "Xizmat/ish yoki taqqoslab boʻlmaydigan kod — birlik narxidagi ogʻish informativ emas",
  "Нет закупок": "Xaridlar yoʻq",

  // ── ForensicEditModal ──
  "Есть несохранённые изменения. Закрыть без сохранения?": "Saqlanmagan oʻzgarishlar bor. Saqlamasdan yopilsinmi?",
  "Горнодобывающий": "Togʻ-kon",
  "Нефтегазовый": "Neft-gaz",
  "Энергетика": "Energetika",
  "Транспорт": "Transport",
  "Прочие": "Boshqalar",
  "{co}: недопустимое значение в поле «{field}» (год {year}) — суммы не бывают отрицательными.":
    "{co}: «{field}» maydonida notoʻgʻri qiymat ({year}-yil) — summalar manfiy boʻlmaydi.",
  "Список компаний не загружен — сохранение отменено.": "Kompaniyalar roʻyxati yuklanmagan — saqlash bekor qilindi.",
  "{co}: кварталы {sum} ≠ год {plan}": "{co}: choraklar {sum} ≠ yil {plan}",
  "Сумма квартальных планов ≠ годовому плану (>5%):\n\n{list}\n\nСохранить всё равно?":
    "Choraklik rejalar yigʻindisi yillik rejaga teng emas (>5%):\n\n{list}\n\nBaribir saqlansinmi?",
  "Редактирование данных закупок": "Xarid maʼlumotlarini tahrirlash",
  "{n} компаний · год {year} · все суммы в млрд сум": "{n} kompaniya · {year}-yil · barcha summalar mlrd soʻmda",
  "изменений": "oʻzgarish",
  "изменение": "oʻzgarish",
  "{n} изм.": "{n} oʻzg.",
  "План есть, факт не заведён": "Reja bor, fakt kiritilmagan",
  "факт —": "fakt —",
  "Год {year}": "{year}-yil",
  "План год": "Yillik reja",
  "Факт год": "Yillik fakt",
  "План 9 мес": "9 oylik reja",
  "Факт 9 мес": "9 oylik fakt",
  "Поквартально": "Choraklar boʻyicha",
  "{q} план": "{q} reja",
  "{q} факт": "{q} fakt",
  "Метаданные": "Metamaʼlumotlar",
  "Статус плана": "Reja holati",
  "Утверждён": "Tasdiqlangan",
  "Не утверждён": "Tasdiqlanmagan",
  "Числовой план (флагман) — план утверждён на эту сумму; редактируется как «План год», не как статус":
    "Raqamli reja (flagman) — reja shu summaga tasdiqlangan; holat sifatida emas, «Yillik reja» sifatida tahrirlanadi",
  "Статус форензика": "Forenzik holati",
  "В процессе": "Jarayonda",
  "Тендер": "Tender",
  "Не начат": "Boshlanmagan",
  "Аудитор": "Auditor",
  "Период аудита": "Audit davri",
  "Нет изменений": "Oʻzgarishlar yoʻq",
  "в {n} компаниях": "{n} ta kompaniyada",
  "Сохранить изменения": "Oʻzgarishlarni saqlash",

  // ── ForensicUploadModal ──
  "Импорт плана/факта закупок · Excel": "Xaridlar reja/faktini import qilish · Excel",
  "3-листовой файл: Инструкция · Компании · Данные. Скачайте шаблон ниже если ещё нет.":
    "3 varaqli fayl: Yoʻriqnoma · Kompaniyalar · Maʼlumotlar. Shablon boʻlmasa, quyida yuklab oling.",
  "В файле нет листов.": "Faylda varaqlar yoʻq.",
  "Лист пуст.": "Varaq boʻsh.",
  "Не удалось распарсить файл.": "Faylni tahlil qilib boʻlmadi.",
  "Загружено: {n} строк": "Yuklandi: {n} qator",
  "Backend-эндпоинт {ep} не найден. Файл валиден и распарсен.":
    "Backend endpoint {ep} topilmadi. Fayl yaroqli va tahlil qilingan.",
  "Ошибка: {msg}": "Xatolik: {msg}",
  "Перетащите Excel-файл сюда": "Excel faylni shu yerga tashlang",
  "или кликните чтобы выбрать (.xlsx / .xls)": "yoki tanlash uchun bosing (.xlsx / .xls)",
  "{kb} KB · клик чтобы заменить": "{kb} KB · almashtirish uchun bosing",
  "Предпросмотр · первая строка": "Oldindan koʻrish · birinchi qator",
  "Предпросмотр · первые {n} строк": "Oldindan koʻrish · dastlabki {n} qator",
  "Выберите файл": "Faylni tanlang",
  "Файл невалиден": "Fayl yaroqsiz",
  "Готов к загрузке": "Yuklashga tayyor",

  // ── PaCategoryDeviationBars ──
  "Нет сопоставимых категорий": "Taqqoslanadigan kategoriyalar yoʻq",
  "{name}: {dev} · {sum} сум · {n} закуп.": "{name}: {dev} · {sum} soʻm · {n} xarid",
  "экономия": "tejash",
  "переплата": "ortiqcha toʻlov",

  // ── PaCategoryGrid ──
  "{n} товаров с benchmark": "benchmark bilan {n} tovar",
  "{n} закупок": "{n} xarid",
  "макс": "maks",
  "мин": "min",
  "Диапазон средних цен товаров с чистым benchmark (spread<200%)":
    "Toza benchmarkka ega tovarlar oʻrtacha narxlari diapazoni (spread<200%)",
  "Все товары — clean выборки нет": "Barcha tovarlar — toza tanlanma yoʻq",
  "Товар": "Tovar",
  "Средняя": "Oʻrtacha",
  "Диапазон": "Diapazon",
  "Покупатели": "Xaridorlar",
  "Δ макс": "Δ maks",
  "{n} SOE × {m} закупок": "{n} SOE × {m} xarid",
  "{n} компания": "{n} kompaniya",
  "{n} компаний": "{n} kompaniya",
  "{kept} товаров с benchmark из {raw}": "{raw} tovardan {kept} tasi benchmark bilan",
  "отсечено {n}: n_co<2 или n<3": "{n} tasi chiqarib tashlandi: n_co<2 yoki n<3",
  "клик по товару — все покупатели": "tovar ustiga bosish — barcha xaridorlar",
  "{n} товаров": "{n} tovar",
  "Цена": "Narx",
  "vs рынок": "vs bozor",
  "клик по строке — детализация": "qator ustiga bosish — tafsilotlar",

  // ── PaEditTableModal ──
  "Редактирование закупок": "Xaridlarni tahrirlash",
  "{n} строк · клик по ячейке → редактирование · Enter — сохранить":
    "{n} qator · katak ustiga bosish → tahrirlash · Enter — saqlash",
  "Поиск: компания / поставщик / продукт / код…": "Qidiruv: kompaniya / yetkazib beruvchi / mahsulot / kod…",
  "Сохранение…": "Saqlanmoqda…",
  "сохранено": "saqlandi",
  "только что": "hozirgina",
  "{sec}s назад": "{sec} s oldin",
  "Продукт": "Mahsulot",
  "Кол-во": "Miqdor",
  "Откл. %": "Ogʻish %",
  "Нет строк по фильтру": "Filtr boʻyicha qatorlar topilmadi",
  "Показано {shown} из {total} · изменения сохраняются автоматически":
    "{total} tadan {shown} tasi koʻrsatilgan · oʻzgarishlar avtomatik saqlanadi",
  "Ошибка сохранения закупки: {msg}": "Xaridni saqlashda xatolik: {msg}",

  // ── PaLeaders ──
  "Нет компаний с экономией": "Tejashga erishgan kompaniyalar yoʻq",
  "{n} категорий": "{n} kategoriya",
  "{pct}% закупок ниже median": "xaridlarning {pct}% mediandan past",
  "образец в {cat} ({dev}%)": "{cat} boʻyicha namuna ({dev}%)",
};

export const en: Record<string, string> = {
  // ── CategoryCompareTable ──
  "Сравнение компаний": "Company comparison",
  "Рейтинг по среднему отклонению": "Ranking by average deviation",
  "1 строка на компанию · sparkline = отклонения по 15 категориям · высота столбика = модуль отклонения, цвет = знак":
    "1 row per company · sparkline = deviations across 15 categories · bar height = deviation magnitude, color = sign",
  "Топ:": "Top:",
  "Откл. ср.": "Avg dev.",
  "Переплата": "Overpayment",
  "Откл. по 15 категориям": "Deviation across 15 categories",
  "Красных": "Red",
  "Объём": "Volume",
  "Нет компаний для сравнения": "No companies to compare",
  "Показано {shown} из {total} компаний · клик по строке — профиль компании":
    "Showing {shown} of {total} companies · click a row for the company profile",
  "нет данных": "no data",

  // ── CompanyProfileModal ──
  "Ранг": "Rank",
  "Средн. отклонение": "Avg deviation",
  "Экономия": "Savings",
  "Категорий": "Categories",
  "Закупок": "Purchases",
  "Обзор": "Overview",
  "Категории": "Categories",
  "Поставщики": "Suppliers",
  "Отклонение цен по категориям": "Price deviation by category",
  "по сопоставимым товарам · база {sum} сум": "comparable products only · base {sum} UZS",
  "Категория": "Category",
  "Объём (сум)": "Volume (UZS)",
  "Median рынка": "Market median",
  "Δ сумма": "Δ amount",
  "Нет поставщиков": "No suppliers",
  "Поставщик": "Supplier",
  "Цена / ед.": "Price / unit",
  "Подробнее о закупке": "Purchase details",
  "ед": "unit",
  "Услуга/работа или несопоставимый код — отклонение по цене за единицу неинформативно":
    "Service/work or non-comparable code — unit-price deviation is not informative",
  "Нет закупок": "No purchases",

  // ── ForensicEditModal ──
  "Есть несохранённые изменения. Закрыть без сохранения?": "There are unsaved changes. Close without saving?",
  "Горнодобывающий": "Mining",
  "Нефтегазовый": "Oil & gas",
  "Энергетика": "Energy",
  "Транспорт": "Transport",
  "Прочие": "Other",
  "{co}: недопустимое значение в поле «{field}» (год {year}) — суммы не бывают отрицательными.":
    "{co}: invalid value in field “{field}” (year {year}) — amounts cannot be negative.",
  "Список компаний не загружен — сохранение отменено.": "Company list is not loaded — save cancelled.",
  "{co}: кварталы {sum} ≠ год {plan}": "{co}: quarters {sum} ≠ year {plan}",
  "Сумма квартальных планов ≠ годовому плану (>5%):\n\n{list}\n\nСохранить всё равно?":
    "Sum of quarterly plans ≠ annual plan (>5%):\n\n{list}\n\nSave anyway?",
  "Редактирование данных закупок": "Edit procurement data",
  "{n} компаний · год {year} · все суммы в млрд сум": "{n} companies · year {year} · all amounts in bn UZS",
  "изменений": "changes",
  "изменение": "change",
  "{n} изм.": "{n} chg.",
  "План есть, факт не заведён": "Plan set, actual not entered",
  "факт —": "actual —",
  "Год {year}": "Year {year}",
  "План год": "Annual plan",
  "Факт год": "Annual actual",
  "План 9 мес": "9M plan",
  "Факт 9 мес": "9M actual",
  "Поквартально": "By quarter",
  "{q} план": "{q} plan",
  "{q} факт": "{q} actual",
  "Метаданные": "Metadata",
  "Статус плана": "Plan status",
  "Утверждён": "Approved",
  "Не утверждён": "Not approved",
  "Числовой план (флагман) — план утверждён на эту сумму; редактируется как «План год», не как статус":
    "Numeric plan (flagship) — the plan is approved for this amount; edit it via “Annual plan”, not as a status",
  "Статус форензика": "Forensic status",
  "В процессе": "In progress",
  "Тендер": "Tender",
  "Не начат": "Not started",
  "Аудитор": "Auditor",
  "Период аудита": "Audit period",
  "Нет изменений": "No changes",
  "в {n} компаниях": "in {n} companies",
  "Сохранить изменения": "Save changes",

  // ── ForensicUploadModal ──
  "Импорт плана/факта закупок · Excel": "Import procurement plan/actual · Excel",
  "3-листовой файл: Инструкция · Компании · Данные. Скачайте шаблон ниже если ещё нет.":
    "3-sheet file: Instructions · Companies · Data. Download the template below if you don't have one yet.",
  "В файле нет листов.": "The file has no sheets.",
  "Лист пуст.": "The sheet is empty.",
  "Не удалось распарсить файл.": "Failed to parse the file.",
  "Загружено: {n} строк": "Loaded: {n} rows",
  "Backend-эндпоинт {ep} не найден. Файл валиден и распарсен.":
    "Backend endpoint {ep} not found. The file is valid and parsed.",
  "Ошибка: {msg}": "Error: {msg}",
  "Перетащите Excel-файл сюда": "Drop the Excel file here",
  "или кликните чтобы выбрать (.xlsx / .xls)": "or click to choose (.xlsx / .xls)",
  "{kb} KB · клик чтобы заменить": "{kb} KB · click to replace",
  "Предпросмотр · первая строка": "Preview · first row",
  "Предпросмотр · первые {n} строк": "Preview · first {n} rows",
  "Выберите файл": "Choose a file",
  "Файл невалиден": "Invalid file",
  "Готов к загрузке": "Ready to upload",

  // ── PaCategoryDeviationBars ──
  "Нет сопоставимых категорий": "No comparable categories",
  "{name}: {dev} · {sum} сум · {n} закуп.": "{name}: {dev} · {sum} UZS · {n} purchases",
  "экономия": "savings",
  "переплата": "overpayment",

  // ── PaCategoryGrid ──
  "{n} товаров с benchmark": "{n} products with benchmark",
  "{n} закупок": "{n} purchases",
  "макс": "max",
  "мин": "min",
  "Диапазон средних цен товаров с чистым benchmark (spread<200%)":
    "Range of average prices for products with a clean benchmark (spread<200%)",
  "Все товары — clean выборки нет": "All products — no clean sample",
  "Товар": "Product",
  "Средняя": "Average",
  "Диапазон": "Range",
  "Покупатели": "Buyers",
  "Δ макс": "Δ max",
  "{n} SOE × {m} закупок": "{n} SOEs × {m} purchases",
  "{n} компания": "{n} company",
  "{n} компаний": "{n} companies",
  "{kept} товаров с benchmark из {raw}": "{kept} of {raw} products with benchmark",
  "отсечено {n}: n_co<2 или n<3": "{n} excluded: n_co<2 or n<3",
  "клик по товару — все покупатели": "click a product for all buyers",
  "{n} товаров": "{n} products",
  "Цена": "Price",
  "vs рынок": "vs market",
  "клик по строке — детализация": "click a row for details",

  // ── PaEditTableModal ──
  "Редактирование закупок": "Edit purchases",
  "{n} строк · клик по ячейке → редактирование · Enter — сохранить":
    "{n} rows · click a cell to edit · Enter to save",
  "Поиск: компания / поставщик / продукт / код…": "Search: company / supplier / product / code…",
  "Сохранение…": "Saving…",
  "сохранено": "saved",
  "только что": "just now",
  "{sec}s назад": "{sec}s ago",
  "Продукт": "Product",
  "Кол-во": "Qty",
  "Откл. %": "Dev. %",
  "Нет строк по фильтру": "No rows match the filter",
  "Показано {shown} из {total} · изменения сохраняются автоматически":
    "Showing {shown} of {total} · changes are saved automatically",
  "Ошибка сохранения закупки: {msg}": "Failed to save the purchase: {msg}",

  // ── PaLeaders ──
  "Нет компаний с экономией": "No companies with savings",
  "{n} категорий": "{n} categories",
  "{pct}% закупок ниже median": "{pct}% of purchases below median",
  "образец в {cat} ({dev}%)": "exemplary in {cat} ({dev}%)",
};

/**
 * Исключения кириллицы: строки с латинскими токенами (Excel, Enter, spread,
 * n_co, vs, sparkline, Backend), которые авто-транслит исказил бы, и
 * заимствование «фильтр» (ь отсутствует в латинице).
 */
export const cyr: Record<string, string> = {
  "1 строка на компанию · sparkline = отклонения по 15 категориям · высота столбика = модуль отклонения, цвет = знак":
    "1 қатор = 1 компания · спарклайн = 15 категория бўйича оғишлар · устун баландлиги = оғиш модули, ранг = ишора",
  "Импорт плана/факта закупок · Excel": "Харидлар режа/фактини импорт қилиш · Excel",
  "Перетащите Excel-файл сюда": "Excel файлни шу ерга ташланг",
  "или кликните чтобы выбрать (.xlsx / .xls)": "ёки танлаш учун босинг (.xlsx / .xls)",
  "Backend-эндпоинт {ep} не найден. Файл валиден и распарсен.":
    "Backend endpoint {ep} топилмади. Файл яроқли ва таҳлил қилинган.",
  "Диапазон средних цен товаров с чистым benchmark (spread<200%)":
    "Тоза бенчмаркка эга товарлар ўртача нархлари диапазони (спред<200%)",
  "отсечено {n}: n_co<2 или n<3": "{n} таси чиқариб ташланди: n_co<2 ёки n<3",
  "vs рынок": "vs бозор",
  "{n} строк · клик по ячейке → редактирование · Enter — сохранить":
    "{n} қатор · катак устига босиш → таҳрирлаш · Enter — сақлаш",
  "Нет строк по фильтру": "Фильтр бўйича қаторлар топилмади",
};
