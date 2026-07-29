/**
 * Словарь модуля «Control Tower» (Execution Summary + Сводный обзор портфеля).
 * Файлы: ControlTower.vue, CtCompanyModal.vue, CtPeriodDrill.vue, ExecOverview.vue.
 * Общеплатформенные термины — в common.ts (здесь НЕ дублируются).
 */

export const uz: Record<string, string> = {
  // ── ControlTower: топбар / периоды ──
  "ЕДИНЫЙ МОНИТОРИНГ": "YAGONA MONITORING",
  "Весь год": "Butun yil",
  "I квартал": "I chorak",
  "II квартал": "II chorak",
  "III квартал": "III chorak",
  "IV квартал": "IV chorak",
  // месяцы (полные и короткие) — в common.ts, здесь не дублируются

  // ── ControlTower: hero / статусы ──
  "Исполнение обязательств": "Majburiyatlar ijrosi",
  "обязательства выполняются": "majburiyatlar bajarilmoqda",
  "в целом по графику": "umuman jadval boʻyicha",
  
  "сильное отставание": "jiddiy ortda qolish",
  "нет наступивших сроков": "muddatlar hali kelmagan",
  "выполнено {done} из {total} задач с наступившим сроком": "muddati kelgan {total} ta vazifadan {done} tasi bajarildi",
  "сроков ещё не наступало · {n} задач в работе": "muddatlar hali kelmagan · {n} ta vazifa jarayonda",
  "{n} не в срок": "{n} ta muddatida emas",
  "Взвешенный прогресс": "Vaznli progress",
  "учитывает задачи в работе (нач. 25% · в работе 50% · проверка 75%)": "jarayondagi vazifalarni hisobga oladi (bosh. 25% · jarayonda 50% · tekshiruv 75%)",
  "просрочено": "muddati oʻtgan",

  // ── ControlTower: плитки ──
  "задач полностью завершено": "vazifa toʻliq yakunlandi",
  "просрочено сейчас": "hozir muddati oʻtgan",
  "компаний в зоне риска": "kompaniya xavf zonasida",
  "компаний в портфеле": "kompaniya portfelda",

  // ── ControlTower: AI-бриф ──
  "Сводка для Совета директоров на основе реальных цифр": "Direktorlar kengashi uchun real raqamlarga asoslangan xulosa",
  "Генерирую…": "Generatsiya qilinmoqda…",
  "Сгенерировать": "Generatsiya qilish",
  "Анализирую исполнение портфеля…": "Portfel ijrosi tahlil qilinmoqda…",
  "Нажмите «Сгенерировать» — ИИ соберёт executive-бриф: статус, риски, траектория, рекомендации.": "«Generatsiya qilish» tugmasini bosing — AI executive-brif tayyorlaydi: holat, xavflar, traektoriya, tavsiyalar.",
  "Ошибка генерации брифа": "Brif yaratishda xatolik",

  // ── ControlTower: динамика ──
  "ДИНАМИКА ИСПОЛНЕНИЯ": "IJRO DINAMIKASI",
  "накопительный % выполнено от портфеля · стрелка — прирост за период · клик — детали": "portfeldan bajarilgan jamlanma % · strelka — davr ichidagi oʻsish · bosish — tafsilotlar",
  "Весь портфель": "Butun portfel",
  "Кварталы": "Choraklar",
  "Месяцы": "Oylar",
  "не наступил": "hali kelmagan",
  "старт": "start",
  "пп": "f.p.",
  "{n} кв": "{n} ch.",
  "{n} проср.": "{n} kech.",
  "Детали периода {p}": "Davr tafsilotlari: {p}",
  "пп за период": "f.p. davrda",
  "прогресс растёт": "progress oʻsmoqda",
  "прогресс снижается": "progress pasaymoqda",
  "без прироста": "oʻsishsiz",
  "% = задач завершено накопительно / портфель (без ежемес./постоянных) · по дате завершения, для задач без неё — по плановому сроку · клик — детали": "% = jamlanma yakunlangan vazifalar / portfel (oylik/doimiylarsiz) · yakunlanish sanasi boʻyicha, sanasi yoʻqlar uchun — reja muddati boʻyicha · bosish — tafsilotlar",
  "Не удалось загрузить динамику: {err}": "Dinamikani yuklab boʻlmadi: {err}",
  "Не удалось загрузить детали периода: {err}": "Davr tafsilotlarini yuklab boʻlmadi: {err}",

  // ── ControlTower: «Что изменилось» ──
  "ЧТО ИЗМЕНИЛОСЬ": "NIMA OʻZGARDI",
  "Улучшились": "Yaxshilanganlar",
  "Провалились": "Yomonlashganlar",
  "Лента изменений: {name}": "Oʻzgarishlar lentasi: {name}",
  "{n} проект(ов) закрыто": "{n} ta loyiha yopildi",
  "+{n} пр.": "+{n} loy.",
  "Никто не вырос": "Hech kim oʻsmadi",
  "Закрыто проектов": "Yopilgan loyihalar",
  "Никто не провалился — хорошо": "Hech kim yomonlashmadi — yaxshi",
  "задач закрыто": "vazifa yopildi",
  "проектов закрыто": "loyiha yopildi",
  "комментариев": "izoh",
  "Зафиксируйте срез — и здесь появится «было → стало»: кто вырос, кто провалился. Срезы фиксируются и автоматически (раз в день).": "Kesimni qayd eting — bu yerda «avval → endi» paydo boʻladi: kim oʻsdi, kim yomonlashdi. Kesimlar avtomatik ham qayd etiladi (kuniga bir marta).",

  // ── ControlTower: список компаний ──
  "ПО КОМПАНИЯМ": "KOMPANIYALAR BOʻYICHA",
  "клик — лента изменений": "bosish — oʻzgarishlar lentasi",
  "Сначала риск": "Avval xavflilar",
  "Лучшие": "Eng yaxshilari",
  "По имени": "Nomi boʻyicha",
  "Нет компаний с данными за этот период.": "Bu davr boʻyicha maʼlumotli kompaniyalar yoʻq.",
  "риск": "xavf",
  "задачи": "vazifalar",
  "проекты": "loyihalar",
  "комм.": "izoh",

  // ── ControlTower: срезы ──
  "срез прогресса": "progress kesimi",
  "среза прогресса": "progress kesimi",
  "срезов прогресса": "progress kesimi",
  "скрыть": "yashirish",
  "управлять": "boshqarish",
  "Фиксирую…": "Qayd etilmoqda…",
  "Зафиксировать срез": "Kesimni qayd etish",
  "Удалить срез": "Kesimni oʻchirish",
  "Удалить срез «{label}»?": "«{label}» kesimini oʻchirasizmi?",
  "Срез зафиксирован · прогресс {n}%": "Kesim qayd etildi · progress {n}%",
  "Срез удалён": "Kesim oʻchirildi",
  "Не удалось зафиксировать: {err}": "Qayd etib boʻlmadi: {err}",
  "Не удалось удалить: {err}": "Oʻchirib boʻlmadi: {err}",
  
  "Сейчас": "Hozir",

  // ── CtCompanyModal ──
  "сменил статус": "holatini oʻzgartirdi",
  "обновил": "yangiladi",
  "создал": "yaratdi",
  "архивировал": "arxivladi",
  "Было": "Avval",
  "Стало": "Endi",
  
  
  "было": "avval",
  "Лента изменений": "Oʻzgarishlar lentasi",
  "последние 120 дней": "oxirgi 120 kun",
  "Изменений нет.": "Oʻzgarishlar yoʻq.",
  "Нет доступа к ленте": "Lentaga ruxsat yoʻq",
  "Не удалось загрузить ленту": "Lentani yuklab boʻlmadi",

  // ── CtPeriodDrill ──
  "Завершено в периоде": "Davr ichida yakunlangan",
  "Просрочено в периоде": "Davr ichida muddati oʻtgan",
  "нет завершённых": "yakunlanganlari yoʻq",
  "нет просроченных": "muddati oʻtganlari yoʻq",
  "свернуть": "yigʻish",
  "+{n} ещё": "yana {n} ta",

  // ── ExecOverview: топбар / состояния ──
  "Сводный обзор портфеля": "Portfel boʻyicha jamlanma sharh",
  "Единая платформа трансформации": "Yagona transformatsiya platformasi",
  "на {d}": "{d} holatiga",
  "Предыдущий год": "Oldingi yil",
  "Следующий год": "Keyingi yil",
  "Заполнить отчёт": "Hisobotni toʻldirish",
  "Заполнить отчёт: {name}": "Hisobotni toʻldirish: {name}",
  "Сначала выберите компанию в списке ниже": "Avval quyidagi roʻyxatdan kompaniyani tanlang",
  "Отчёт заполнен": "Hisobot toʻldirilgan",
  "Печать заполненного отчёта": "Toʻldirilgan hisobotni chop etish",
  "Нет заполненного отчёта для печати": "Chop etish uchun toʻldirilgan hisobot yoʻq",
  "Собираем обзор…": "Sharh tayyorlanmoqda…",
  "Не удалось загрузить обзор": "Sharhni yuklab boʻlmadi",
  "Нет текущих проектов": "Joriy loyihalar yoʻq",
  "За выбранный год не найдено открытых проектов. Смените год или проверьте портфель.": "Tanlangan yil uchun ochiq loyihalar topilmadi. Yilni oʻzgartiring yoki portfelni tekshiring.",
  "Нет заполненных отчётов": "Toʻldirilgan hisobotlar yoʻq",
  "Компания не выбрана": "Kompaniya tanlanmagan",
  "Заполнено отчётов: {a} из {b}. Выберите компанию выше и нажмите «Заполнить отчёт».": "Toʻldirilgan hisobotlar: {b} tadan {a} ta. Yuqoridan kompaniyani tanlang va «Hisobotni toʻldirish» tugmasini bosing.",
  "Выберите компанию в списке выше, чтобы увидеть превью отчёта.": "Hisobot koʻrinishini koʻrish uchun yuqoridagi roʻyxatdan kompaniyani tanlang.",

  // ── ExecOverview: отчёт / матрица / печать ──
  "требует решения": "qaror talab qiladi",
  "Направление": "Yoʻnalish",
  "· янв–мар": "· yan–mar",
  "· апр–июн": "· apr–iyun",
  "· июл–сен": "· iyul–sen",
  "· окт–дек": "· okt–dek",
  "срок": "muddat",
  "В графике": "Jadval boʻyicha",
  "Заблокирован": "Bloklangan",
  "(без названия)": "(nomsiz)",
  "Детали проекта": "Loyiha tafsilotlari",
  "Цель / результат": "Maqsad / natija",
  "Требуется распоряжение": "Farmoyish talab etiladi",
  "не назначен": "tayinlanmagan",
  "ochiq — цель не указана": "ochiq — maqsad koʻrsatilmagan",
  "Распоряжений не требуется": "Farmoyish talab etilmaydi",
  "Отчёт ещё не заполнен. Нажмите «Заполнить отчёт» в шапке, чтобы внести направления и проекты по кварталам.": "Hisobot hali toʻldirilmagan. Yoʻnalishlar va loyihalarni choraklar boʻyicha kiritish uchun yuqoridagi «Hisobotni toʻldirish» tugmasini bosing.",
  "сводный обзор": "jamlanma sharh",
  "проект": "loyiha",
  "проекта": "loyiha",
  "проектов": "loyiha",
};

export const en: Record<string, string> = {
  // ── ControlTower: топбар / периоды ──
  "ЕДИНЫЙ МОНИТОРИНГ": "UNIFIED MONITORING",
  "Весь год": "Full year",
  "I квартал": "Q1",
  "II квартал": "Q2",
  "III квартал": "Q3",
  "IV квартал": "Q4",
  // месяцы (полные и короткие) — в common.ts, здесь не дублируются

  // ── ControlTower: hero / статусы ──
  "Исполнение обязательств": "Commitment fulfillment",
  "обязательства выполняются": "commitments on track",
  "в целом по графику": "broadly on schedule",
  
  "сильное отставание": "far behind",
  "нет наступивших сроков": "no due dates yet",
  "выполнено {done} из {total} задач с наступившим сроком": "{done} of {total} due tasks completed",
  "сроков ещё не наступало · {n} задач в работе": "no deadlines reached yet · {n} tasks in progress",
  "{n} не в срок": "{n} not on time",
  "Взвешенный прогресс": "Weighted progress",
  "учитывает задачи в работе (нач. 25% · в работе 50% · проверка 75%)": "includes in-progress tasks (init 25% · active 50% · review 75%)",
  "просрочено": "overdue",

  // ── ControlTower: плитки ──
  "задач полностью завершено": "tasks fully completed",
  "просрочено сейчас": "overdue now",
  "компаний в зоне риска": "companies at risk",
  "компаний в портфеле": "companies in portfolio",

  // ── ControlTower: AI-бриф ──
  "Сводка для Совета директоров на основе реальных цифр": "A board-level summary based on real numbers",
  "Генерирую…": "Generating…",
  "Сгенерировать": "Generate",
  "Анализирую исполнение портфеля…": "Analyzing portfolio execution…",
  "Нажмите «Сгенерировать» — ИИ соберёт executive-бриф: статус, риски, траектория, рекомендации.": "Click “Generate” — the AI will compile an executive brief: status, risks, trajectory, recommendations.",
  "Ошибка генерации брифа": "Brief generation failed",

  // ── ControlTower: динамика ──
  "ДИНАМИКА ИСПОЛНЕНИЯ": "EXECUTION DYNAMICS",
  "накопительный % выполнено от портфеля · стрелка — прирост за период · клик — детали": "cumulative % of portfolio completed · arrow — growth per period · click for details",
  "Весь портфель": "Entire portfolio",
  "Кварталы": "Quarters",
  "Месяцы": "Months",
  "не наступил": "upcoming",
  "старт": "start",
  "пп": "pp",
  "{n} кв": "{n} qtr",
  "{n} проср.": "{n} overdue",
  "Детали периода {p}": "Period details: {p}",
  "пп за период": "pp per period",
  "прогресс растёт": "progress is rising",
  "прогресс снижается": "progress is falling",
  "без прироста": "no growth",
  "% = задач завершено накопительно / портфель (без ежемес./постоянных) · по дате завершения, для задач без неё — по плановому сроку · клик — детали": "% = tasks completed cumulatively / portfolio (excl. monthly/ongoing) · by completion date, or planned due date if missing · click for details",
  "Не удалось загрузить динамику: {err}": "Failed to load dynamics: {err}",
  "Не удалось загрузить детали периода: {err}": "Failed to load period details: {err}",

  // ── ControlTower: «Что изменилось» ──
  "ЧТО ИЗМЕНИЛОСЬ": "WHAT CHANGED",
  "Улучшились": "Improved",
  "Провалились": "Declined",
  "Лента изменений: {name}": "Change feed: {name}",
  "{n} проект(ов) закрыто": "{n} project(s) closed",
  "+{n} пр.": "+{n} proj.",
  "Никто не вырос": "No one improved",
  "Закрыто проектов": "Projects closed",
  "Никто не провалился — хорошо": "No one declined — good",
  "задач закрыто": "tasks closed",
  "проектов закрыто": "projects closed",
  "комментариев": "comments",
  "Зафиксируйте срез — и здесь появится «было → стало»: кто вырос, кто провалился. Срезы фиксируются и автоматически (раз в день).": "Take a snapshot — “before → after” will appear here: who improved, who declined. Snapshots are also taken automatically (once a day).",

  // ── ControlTower: список компаний ──
  "ПО КОМПАНИЯМ": "BY COMPANY",
  "клик — лента изменений": "click — change feed",
  "Сначала риск": "Risk first",
  "Лучшие": "Best first",
  "По имени": "By name",
  "Нет компаний с данными за этот период.": "No companies with data for this period.",
  "риск": "risk",
  "задачи": "tasks",
  "проекты": "projects",
  "комм.": "comments",

  // ── ControlTower: срезы ──
  "срез прогресса": "progress snapshot",
  "среза прогресса": "progress snapshots",
  "срезов прогресса": "progress snapshots",
  "скрыть": "hide",
  "управлять": "manage",
  "Фиксирую…": "Saving…",
  "Зафиксировать срез": "Take snapshot",
  "Удалить срез": "Delete snapshot",
  "Удалить срез «{label}»?": "Delete snapshot “{label}”?",
  "Срез зафиксирован · прогресс {n}%": "Snapshot saved · progress {n}%",
  "Срез удалён": "Snapshot deleted",
  "Не удалось зафиксировать: {err}": "Failed to save snapshot: {err}",
  "Не удалось удалить: {err}": "Failed to delete: {err}",
  
  "Сейчас": "Now",

  // ── CtCompanyModal ──
  "сменил статус": "changed status",
  "обновил": "updated",
  "создал": "created",
  "архивировал": "archived",
  "Было": "Before",
  "Стало": "After",
  "Задачи завершено": "Tasks completed",
  "Проекты завершено": "Projects completed",
  "было": "was",
  "Лента изменений": "Change feed",
  "последние 120 дней": "last 120 days",
  "Изменений нет.": "No changes.",
  "Нет доступа к ленте": "No access to the feed",
  "Не удалось загрузить ленту": "Failed to load the feed",

  // ── CtPeriodDrill ──
  "Завершено в периоде": "Completed in period",
  "Просрочено в периоде": "Overdue in period",
  "нет завершённых": "none completed",
  "нет просроченных": "none overdue",
  "свернуть": "collapse",
  "+{n} ещё": "+{n} more",

  // ── ExecOverview: топбар / состояния ──
  "Сводный обзор портфеля": "Consolidated portfolio overview",
  "Единая платформа трансформации": "Unified Transformation Platform",
  "на {d}": "as of {d}",
  "Предыдущий год": "Previous year",
  "Следующий год": "Next year",
  "Заполнить отчёт": "Fill in report",
  "Заполнить отчёт: {name}": "Fill in report: {name}",
  "Сначала выберите компанию в списке ниже": "First select a company in the list below",
  "Отчёт заполнен": "Report filled in",
  "Печать заполненного отчёта": "Print the filled report",
  "Нет заполненного отчёта для печати": "No filled report to print",
  "Собираем обзор…": "Building the overview…",
  "Не удалось загрузить обзор": "Failed to load the overview",
  "Нет текущих проектов": "No current projects",
  "За выбранный год не найдено открытых проектов. Смените год или проверьте портфель.": "No open projects found for the selected year. Change the year or check the portfolio.",
  "Нет заполненных отчётов": "No filled reports",
  "Компания не выбрана": "No company selected",
  "Заполнено отчётов: {a} из {b}. Выберите компанию выше и нажмите «Заполнить отчёт».": "Reports filled: {a} of {b}. Select a company above and click “Fill in report”.",
  "Выберите компанию в списке выше, чтобы увидеть превью отчёта.": "Select a company in the list above to preview the report.",

  // ── ExecOverview: отчёт / матрица / печать ──
  "требует решения": "need a decision",
  "Направление": "Direction",
  "· янв–мар": "· Jan–Mar",
  "· апр–июн": "· Apr–Jun",
  "· июл–сен": "· Jul–Sep",
  "· окт–дек": "· Oct–Dec",
  
  "В графике": "On track",
  "Заблокирован": "Blocked",
  "(без названия)": "(untitled)",
  "Детали проекта": "Project details",
  "Цель / результат": "Goal / outcome",
  "Требуется распоряжение": "Directive required",
  "не назначен": "not assigned",
  "ochiq — цель не указана": "open — goal not specified",
  "Распоряжений не требуется": "No directive required",
  "Отчёт ещё не заполнен. Нажмите «Заполнить отчёт» в шапке, чтобы внести направления и проекты по кварталам.": "The report is not filled in yet. Click “Fill in report” in the header to add directions and projects by quarter.",
  "сводный обзор": "summary overview",
  "проект": "project",
  "проекта": "projects",
  "проектов": "projects",
};

/**
 * Исключения узбекской кириллицы (транслит латиницы даёт неверную форму):
 *  - ALL-CAPS фразы: транслит принимает слова за акронимы и оставляет латиницей;
 *  - «portfel»: в уз-кириллице «портфель» с «ь», которого транслит не даёт;
 *  - фразы с латинскими словами (AI, executive) — чтобы не транслитерировались.
 * Месяцы — в common.ts.
 */
export const cyr: Record<string, string> = {
  "I квартал": "I чорак",
  "ЕДИНЫЙ МОНИТОРИНГ": "ЯГОНА МОНИТОРИНГ",
  "ДИНАМИКА ИСПОЛНЕНИЯ": "ИЖРО ДИНАМИКАСИ",
  "ЧТО ИЗМЕНИЛОСЬ": "НИМА ЎЗГАРДИ",
  "ПО КОМПАНИЯМ": "КОМПАНИЯЛАР БЎЙИЧА",
  "Сгенерировать": "Генерация қилиш",
  "Генерирую…": "Генерация қилинмоқда…",
  "Нажмите «Сгенерировать» — ИИ соберёт executive-бриф: статус, риски, траектория, рекомендации.": "«Генерация қилиш» тугмасини босинг — AI executive-бриф тайёрлайди: ҳолат, хавфлар, траектория, тавсиялар.",
  "Единая платформа трансформации": "Ягона трансформация платформаси",
  // «портфель» — «ь» не порождается транслитом (portfel → «портфел»)
  "Весь портфель": "Бутун портфель",
  "Сводный обзор портфеля": "Портфель бўйича жамланма шарҳ",
  "компаний в портфеле": "компания портфельда",
  "Анализирую исполнение портфеля…": "Портфель ижроси таҳлил қилинмоқда…",
  "накопительный % выполнено от портфеля · стрелка — прирост за период · клик — детали":
    "портфельдан бажарилган жамланма % · стрелка — давр ичидаги ўсиш · босиш — тафсилотлар",
  "% = задач завершено накопительно / портфель (без ежемес./постоянных) · по дате завершения, для задач без неё — по плановому сроку · клик — детали":
    "% = жамланма якунланган вазифалар / портфель (ойлик/доимийларсиз) · якунланиш санаси бўйича, санаси йўқлар учун — режа муддати бўйича · босиш — тафсилотлар",
};
