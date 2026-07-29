/**
 * Словарь модуля Executive Dashboard (часть B): блоки KPI / прогноз KPI /
 * производство / рейтинги / секторы / стандарты / налоговый вклад / топбар.
 * Общеплатформенные термины (План/Факт/Нет данных/…) — в common.ts.
 */

export const uz: Record<string, string> = {
  // ── ExecDashKpiBlock ──
  "Общее выполнение KPI": "KPI umumiy bajarilishi",
  "За выбранный FY данных по KPI нет — показан последний год с данными":
    "Tanlangan FY uchun KPI maʼlumotlari yoʻq — maʼlumot mavjud oxirgi yil koʻrsatilgan",
  "данные за FY {y}": "FY {y} maʼlumotlari",
  "компаний": "kompaniya",
  "Не удалось загрузить KPI": "KPI yuklanmadi",
  "Произошёл сбой при загрузке сводки KPI. Проверьте подключение и повторите.":
    "KPI yigʻma maʼlumotini yuklashda xatolik yuz berdi. Ulanishni tekshirib, qayta urinib koʻring.",
  "Нет данных KPI": "KPI maʼlumotlari yoʻq",
  "За {p} FY {y} индикаторы с весом не заполнены.":
    "{p} FY {y} uchun salmoqli indikatorlar toʻldirilmagan.",
  "Открыть модуль KPI": "KPI modulini ochish",
  "Критично": "Kritik",
  "Риск": "Risk",
  "Зона внимания": "Eʼtibor zonasi",
  "На цели": "Maqsadda",
  "Превышено": "Oshirilgan",
  "В риске": "Risk ostida",
  "Провал": "Bajarilmagan",
  "индикаторов с весом": "salmoqli indikator",
  "превышено": "oshirilgan",
  "на цели": "maqsadda",
  "в риске": "risk ostida",
  "критично": "kritik",
  "провалено": "bajarilmagan",
  "Драйверы:": "Drayverlar:",
  "Зоны риска:": "Risk zonalari:",

  // ── ExecDashKpiForecastBlock ──
  "Прогноз KPI": "KPI prognozi",
  "FY {y} · детерминированный тренд · ожидаемое выполнение FY {fy}":
    "FY {y} · deterministik trend · FY {fy} kutilayotgan bajarilish",
  "{a} / {b} с прогнозом": "{a} / {b} prognoz bilan",
  "Прогноз KPI недоступен за FY {y}": "FY {y} uchun KPI prognozi mavjud emas",
  "Нужно ≥2 лет истории KPI по компаниям —": "Kompaniyalar boʻyicha ≥2 yillik KPI tarixi kerak —",
  "тренд рассчитается автоматически.": "trend avtomatik hisoblanadi.",
  "Ожид. выполнение FY {y}": "FY {y} kutil. bajarilish",
  "тек. {v} по портфелю": "joriy {v} portfel boʻyicha",
  "В зоне риска": "Risk zonasida",
  "прогноз ниже 75%": "prognoz 75% dan past",
  "Динамика тренда": "Trend dinamikasi",
  "улучшаются / ухудшаются": "yaxshilanmoqda / yomonlashmoqda",
  "Покрытие прогнозом": "Prognoz qamrovi",
  "{n} без истории": "{n} tarixsiz",
  "Прогноз выполнения FY {y} · топ-{n}": "FY {y} bajarilish prognozi · top-{n}",
  "Открыть KPI: {name}": "KPI ochish: {name}",
  "Риски недостижения": "Bajarilmaslik risklari",
  "надёжность прогноза": "prognoz ishonchliligi",
  "нет компаний в зоне риска": "risk zonasida kompaniyalar yoʻq",
  "Лидеры прогноза": "Prognoz yetakchilari",
  "Числа — детерминированный движок (OLS-тренд по годовому ряду выполнения); коридор надёжности учтён. Разбор и прогноз по показателям — в модуле KPI, режим «Прогноз».":
    "Raqamlar — deterministik mexanizm (bajarilishning yillik qatori boʻyicha OLS-trend); ishonchlilik koridori hisobga olingan. Koʻrsatkichlar boʻyicha tahlil va prognoz — KPI modulida, «Prognoz» rejimida.",
  "высокая": "yuqori",
  "средняя": "oʻrtacha",
  "низкая": "past",
  // «нет данных» — в common.ts

  // ── ExecDashProductionBlock ──
  "Открыть вкладку «Производственные показатели»": "«Ishlab chiqarish koʻrsatkichlari» boʻlimini ochish",
  "Производственный план · FY {y} · 1 полугодие": "Ishlab chiqarish rejasi · FY {y} · I yarim yillik",
  "Исполнение производственного плана": "Ishlab chiqarish rejasining ijrosi",
  "Нет доступа к производственным данным": "Ishlab chiqarish maʼlumotlariga ruxsat yoʻq",
  "Производственные данные не заведены — импортируйте «Свод» во вкладке БП":
    "Ishlab chiqarish maʼlumotlari kiritilmagan — «Svod» faylini Biznes-reja boʻlimida import qiling",
  "переисполнение": "oshirib bajarilish",
  "в норме": "meʼyorida",
  "отставание": "ortda qolish",
  "трлн план": "trln reja",
  "ожид.": "kutil.",
  "Покрытие:": "Qamrov:",
  "Лидеры": "Yetakchilar",
  "Отстающие": "Ortda qolganlar",

  // ── ExecDashRatings ──
  "Рейтинги компаний": "Kompaniyalar reytinglari",
  "Кредитный и ESG": "Kredit va ESG",
  "Кредитный и ESG · {n} компаний": "Kredit va ESG · {n} kompaniya",
  "Рейтинги пока не загружены в систему": "Reytinglar hali tizimga yuklanmagan",
  "Открыть отчёт по рейтингу: {v}": "Reyting hisobotini ochish: {v}",
  "было: {v}": "avval: {v}",
  "Нет табличных рейтингов компаний": "Kompaniyalar boʻyicha jadval reytinglari yoʻq",

  // ── ExecDashRingCard ──
  "+{n} к 2024": "2024 ga nisbatan +{n}",
  "= к 2024": "2024 bilan teng",
  "{n} не охвачено": "{n} qamrab olinmagan",
  "полное покрытие": "toʻliq qamrov",

  // ── ExecDashSectorCard / SectorCompanyRow / SectorGrid ──
  "{n} из {total} компания": "{total} tadan {n} ta kompaniya",
  "{n} из {total} компании": "{total} tadan {n} ta kompaniya",
  "{n} из {total} компаний": "{total} tadan {n} ta kompaniya",
  "средний": "oʻrtacha",
  "Свернуть список компаний": "Kompaniyalar roʻyxatini yigʻish",
  "Показать ещё {n}": "Yana {n} ta koʻrsatish",
  "Открыть карточку компании {name}": "{name} kompaniyasi kartasini ochish",
  "Открыть карточку компании": "Kompaniya kartasini ochish",
  "{a} задач · {b} завершено · {c}% средний прогресс":
    "{a} vazifa · {b} yakunlangan · {c}% oʻrtacha progress",
  "Исполнение задач Ожиданий Акционера": "Aksiyador kutilmalari vazifalarining ijrosi",
  "Нет данных о задачах для FY {y}": "FY {y} uchun vazifalar boʻyicha maʼlumot yoʻq",

  // ── ExecDashStandardsBlock ──
  "+{n} в процессе": "+{n} jarayonda",
  "+{n} процесс": "+{n} jarayonda",
  "{n} тендер": "{n} tender",
  "{k} в процессе": "{k} jarayonda",
  "Forensic тендер": "Forensic tenderi",
  "{k} не начат": "{k} boshlanmagan",
  "Внедрение стандартов": "Standartlarni joriy etish",
  "Аудит проводится с лагом в год — показаны данные за предыдущий завершённый год":
    "Audit bir yillik kechikish bilan oʻtkaziladi — oldingi yakunlangan yil maʼlumotlari koʻrsatilgan",
  "Нет данных по стандартам": "Standartlar boʻyicha maʼlumot yoʻq",
  "Для FY {y} нет информации о внедрении МСФО / Forensic":
    "FY {y} uchun MHXS / Forensic joriy etilishi haqida maʼlumot yoʻq",
  "аудит завершён": "audit yakunlangan",
  "Требуют внимания": "Eʼtibor talab qiladi",
  "Все компании завершили МСФО и Forensic": "Barcha kompaniyalar MHXS va Forensic auditini yakunlagan",

  // ── ExecDashTaxContributionBlock ──
  "Налоговый вклад портфеля": "Portfelning soliq hissasi",
  "вклад в бюджет Республики Узбекистан": "Oʻzbekiston Respublikasi byudjetiga hissa",
  "Без NSBU PL за {y}:": "{y} uchun NSBU PL yoʻq:",
  "Все компании портфеля учтены": "Portfeldagi barcha kompaniyalar hisobga olingan",
  "Нет налоговых данных за FY {y}": "FY {y} uchun soliq maʼlumotlari yoʻq",
  "Заполните поля «Выручка» и «Налог на прибыль»": "«Tushum» va «Foyda soligʻi» maydonlarini toʻldiring",
  "в финансовой отчётности портфеля (IFRS / NSBU PL).": "portfel moliyaviy hisobotida (IFRS / NSBU PL).",
  "Подробнее: Налог на прибыль": "Batafsil: Foyda soligʻi",
  "Налог на прибыль": "Foyda soligʻi",
  "{v} к {y}": "{y} ga nisbatan {v}",
  "Расчётная оценка: 12% × выручка (НСБУ). Не учитывает нулевую ставку НДС на экспорт и зачёт входящего НДС — фактический НДС к уплате ниже.":
    "Hisob-kitob bahosi: 12% × tushum (BHMS). Eksportga nol stavkali QQS va kiruvchi QQS hisobga olinmaydi — toʻlanadigan haqiqiy QQS pastroq.",
  "НДС (12% от выручки)": "QQS (tushumning 12%)",
  "оценка": "taxmin",
  "Налог на прибыль (факт по отчётности НСБУ) + НДС (расчётная оценка). Не включает НДПИ, акцизы, роялти и дивиденды — итог является оценкой.":
    "Foyda soligʻi (BHMS hisoboti boʻyicha fakt) + QQS (hisob-kitob bahosi). Yer qaʼri soligʻi, aksizlar, royalti va dividendlar kirmaydi — jami taxminiy baho hisoblanadi.",
  "Итоговый налоговый вклад": "Jami soliq hissasi",
  "Подробнее: Доля портфеля в бюджете Республики": "Batafsil: Portfelning Respublika byudjetidagi ulushi",
  "Процент бюджета Республики Узбекистан": "Oʻzbekiston Respublikasi byudjetidagi ulush",
  "из {v} {u}": "{v} {u} ichidan",
  "Топ-5 плательщиков": "Top-5 toʻlovchilar",

  // ── ExecDashTopbar ──
  "Программа трансформации государственных предприятий": "Davlat korxonalarini transformatsiya qilish dasturi",
  "Сбросить все фильтры": "Barcha filtrlarni qayta tiklash",
  "Фильтр по секторам": "Tarmoqlar boʻyicha filtr",
  "Все секторы": "Barcha tarmoqlar",
  "Поиск компании…": "Kompaniya qidirish…",
  "Выберите 1 — фокус, 2+ — сравнение (бенчмарк)": "1 ta tanlang — fokus, 2+ — taqqoslash (benchmark)",
  "Выбор компаний": "Kompaniyalarni tanlash",
  "Выбрано: {n}": "Tanlangan: {n}",

  // ── ExecutiveDashboard ──
  "Ошибка загрузки:": "Yuklash xatoligi:",
  "Повторить": "Qayta urinish",
  "Нет данных за FY {y}": "FY {y} uchun maʼlumot yoʻq",
  "Доступные годы:": "Mavjud yillar:",
  "Сводка по портфелю": "Portfel boʻyicha xulosa",
  "Топ-3 риска по портфелю": "Portfel boʻyicha top-3 risk",
  "IPO-готовность компаний": "Kompaniyalarning IPO ga tayyorligi",
  "Сравни 2025 vs 2026": "2025 vs 2026 ni taqqosla",
  "Что важного сегодня?": "Bugun nima muhim?",
};

export const en: Record<string, string> = {
  // ── ExecDashKpiBlock ──
  "Общее выполнение KPI": "Overall KPI performance",
  "За выбранный FY данных по KPI нет — показан последний год с данными":
    "No KPI data for the selected FY — showing the latest year with data",
  "данные за FY {y}": "FY {y} data",
  "компаний": "companies",
  "Не удалось загрузить KPI": "Failed to load KPI",
  "Произошёл сбой при загрузке сводки KPI. Проверьте подключение и повторите.":
    "An error occurred while loading the KPI summary. Check your connection and try again.",
  "Нет данных KPI": "No KPI data",
  "За {p} FY {y} индикаторы с весом не заполнены.":
    "No weighted indicators filled in for {p} FY {y}.",
  "Открыть модуль KPI": "Open KPI module",
  "Критично": "Critical",
  "Риск": "Risk",
  "Зона внимания": "Watch zone",
  "На цели": "On target",
  "Превышено": "Exceeded",
  "В риске": "At risk",
  "Провал": "Failed",
  "индикаторов с весом": "weighted indicators",
  "превышено": "exceeded",
  "на цели": "on target",
  "в риске": "at risk",
  "критично": "critical",
  "провалено": "failed",
  "Драйверы:": "Drivers:",
  "Зоны риска:": "Risk zones:",

  // ── ExecDashKpiForecastBlock ──
  "Прогноз KPI": "KPI forecast",
  "FY {y} · детерминированный тренд · ожидаемое выполнение FY {fy}":
    "FY {y} · deterministic trend · expected completion FY {fy}",
  "{a} / {b} с прогнозом": "{a} / {b} with forecast",
  "Прогноз KPI недоступен за FY {y}": "KPI forecast unavailable for FY {y}",
  "Нужно ≥2 лет истории KPI по компаниям —": "Requires ≥2 years of KPI history per company —",
  "тренд рассчитается автоматически.": "the trend is calculated automatically.",
  "Ожид. выполнение FY {y}": "Exp. completion FY {y}",
  "тек. {v} по портфелю": "current {v} portfolio-wide",
  "В зоне риска": "At risk",
  "прогноз ниже 75%": "forecast below 75%",
  "Динамика тренда": "Trend dynamics",
  "улучшаются / ухудшаются": "improving / declining",
  "Покрытие прогнозом": "Forecast coverage",
  "{n} без истории": "{n} without history",
  "Прогноз выполнения FY {y} · топ-{n}": "Completion forecast FY {y} · top {n}",
  "Открыть KPI: {name}": "Open KPI: {name}",
  "Риски недостижения": "Underachievement risks",
  "надёжность прогноза": "forecast confidence",
  "нет компаний в зоне риска": "no companies at risk",
  "Лидеры прогноза": "Forecast leaders",
  "Числа — детерминированный движок (OLS-тренд по годовому ряду выполнения); коридор надёжности учтён. Разбор и прогноз по показателям — в модуле KPI, режим «Прогноз».":
    "Figures come from a deterministic engine (OLS trend over the annual completion series); the confidence band is applied. Indicator-level breakdown and forecasts are in the KPI module, Forecast mode.",
  "высокая": "high",
  "средняя": "medium",
  "низкая": "low",
  // «нет данных» — в common.ts

  // ── ExecDashProductionBlock ──
  "Открыть вкладку «Производственные показатели»": "Open the Production indicators tab",
  "Производственный план · FY {y} · 1 полугодие": "Production plan · FY {y} · H1",
  "Исполнение производственного плана": "Production plan execution",
  "Нет доступа к производственным данным": "No access to production data",
  "Производственные данные не заведены — импортируйте «Свод» во вкладке БП":
    "No production data yet — import the summary file in the Business plan tab",
  "переисполнение": "overperformance",
  "в норме": "on track",
  "отставание": "behind",
  "трлн план": "trn plan",
  "ожид.": "exp.",
  "Покрытие:": "Coverage:",
  "Лидеры": "Leaders",
  "Отстающие": "Laggards",

  // ── ExecDashRatings ──
  "Рейтинги компаний": "Company ratings",
  "Кредитный и ESG": "Credit & ESG",
  "Кредитный и ESG · {n} компаний": "Credit & ESG · {n} companies",
  "Рейтинги пока не загружены в систему": "Ratings have not been uploaded yet",
  "Открыть отчёт по рейтингу: {v}": "Open rating report: {v}",
  "было: {v}": "was: {v}",
  "Нет табличных рейтингов компаний": "No company rating table data",

  // ── ExecDashRingCard ──
  "+{n} к 2024": "+{n} vs 2024",
  "= к 2024": "= vs 2024",
  "{n} не охвачено": "{n} not covered",
  "полное покрытие": "full coverage",

  // ── ExecDashSectorCard / SectorCompanyRow / SectorGrid ──
  "{n} из {total} компания": "{n} of {total} company",
  "{n} из {total} компании": "{n} of {total} companies",
  "{n} из {total} компаний": "{n} of {total} companies",
  "средний": "average",
  "Свернуть список компаний": "Collapse company list",
  "Показать ещё {n}": "Show {n} more",
  "Открыть карточку компании {name}": "Open company card {name}",
  "Открыть карточку компании": "Open company card",
  "{a} задач · {b} завершено · {c}% средний прогресс":
    "{a} tasks · {b} completed · {c}% average progress",
  "Исполнение задач Ожиданий Акционера": "Shareholder Expectations task execution",
  "Нет данных о задачах для FY {y}": "No task data for FY {y}",

  // ── ExecDashStandardsBlock ──
  "+{n} в процессе": "+{n} in progress",
  "+{n} процесс": "+{n} in progress",
  "{n} тендер": "{n} tender",
  "{k} в процессе": "{k} in progress",
  "Forensic тендер": "Forensic tender",
  "{k} не начат": "{k} not started",
  "Внедрение стандартов": "Standards adoption",
  "Аудит проводится с лагом в год — показаны данные за предыдущий завершённый год":
    "Audits lag by one year — data for the previous completed year is shown",
  "Нет данных по стандартам": "No standards data",
  "Для FY {y} нет информации о внедрении МСФО / Forensic":
    "No IFRS / Forensic adoption info for FY {y}",
  "аудит завершён": "audit completed",
  "Требуют внимания": "Need attention",
  "Все компании завершили МСФО и Forensic": "All companies completed IFRS and Forensic",

  // ── ExecDashTaxContributionBlock ──
  "Налоговый вклад портфеля": "Portfolio tax contribution",
  "вклад в бюджет Республики Узбекистан": "contribution to the budget of the Republic of Uzbekistan",
  "Без NSBU PL за {y}:": "No NSBU PL for {y}:",
  "Все компании портфеля учтены": "All portfolio companies included",
  "Нет налоговых данных за FY {y}": "No tax data for FY {y}",
  "Заполните поля «Выручка» и «Налог на прибыль»": "Fill in the Revenue and Income tax fields",
  "в финансовой отчётности портфеля (IFRS / NSBU PL).": "in the portfolio financial statements (IFRS / NSBU PL).",
  "Подробнее: Налог на прибыль": "Details: Income tax",
  "Налог на прибыль": "Income tax",
  "{v} к {y}": "{v} vs {y}",
  "Расчётная оценка: 12% × выручка (НСБУ). Не учитывает нулевую ставку НДС на экспорт и зачёт входящего НДС — фактический НДС к уплате ниже.":
    "Estimate: 12% × revenue (NAS). Does not account for zero-rated export VAT or input VAT offset — actual VAT payable is lower.",
  "НДС (12% от выручки)": "VAT (12% of revenue)",
  "оценка": "estimate",
  "Налог на прибыль (факт по отчётности НСБУ) + НДС (расчётная оценка). Не включает НДПИ, акцизы, роялти и дивиденды — итог является оценкой.":
    "Income tax (actual per NAS reporting) + VAT (estimate). Excludes mineral extraction tax, excise, royalties and dividends — the total is an estimate.",
  "Итоговый налоговый вклад": "Total tax contribution",
  "Подробнее: Доля портфеля в бюджете Республики": "Details: portfolio share of the national budget",
  "Процент бюджета Республики Узбекистан": "Share of Uzbekistan's state budget",
  "из {v} {u}": "of {v} {u}",
  "Топ-5 плательщиков": "Top 5 payers",

  // ── ExecDashTopbar ──
  "Программа трансформации государственных предприятий": "State-owned enterprise transformation program",
  "Сбросить все фильтры": "Reset all filters",
  "Фильтр по секторам": "Filter by sector",
  "Все секторы": "All sectors",
  "Поиск компании…": "Search company…",
  "Выберите 1 — фокус, 2+ — сравнение (бенчмарк)": "Pick 1 to focus, 2+ to compare (benchmark)",
  "Выбор компаний": "Company selection",
  "Выбрано: {n}": "Selected: {n}",

  // ── ExecutiveDashboard ──
  "Ошибка загрузки:": "Load error:",
  "Повторить": "Retry",
  "Нет данных за FY {y}": "No data for FY {y}",
  "Доступные годы:": "Available years:",
  "Сводка по портфелю": "Portfolio summary",
  "Топ-3 риска по портфелю": "Top 3 portfolio risks",
  "IPO-готовность компаний": "Company IPO readiness",
  "Сравни 2025 vs 2026": "Compare 2025 vs 2026",
  "Что важного сегодня?": "What's important today?",
};

/**
 * Исключения кириллицы: только слова, где авто-транслит латиницы даёт
 * неверную форму (заимствования с «ь»: фильтр, портфель; с «ц»: акциядор,
 * трансформация). Акронимы (KPI, FY, IFRS…) транслит не трогает сам.
 */
export const cyr: Record<string, string> = {
  "Сбросить все фильтры": "Барча фильтрларни қайта тиклаш",
  "Фильтр по секторам": "Тармоқлар бўйича фильтр",
  "Программа трансформации государственных предприятий": "Давлат корхоналарини трансформация қилиш дастури",
  "тек. {v} по портфелю": "жорий {v} портфель бўйича",
  "в финансовой отчётности портфеля (IFRS / NSBU PL).": "портфель молиявий ҳисоботида (IFRS / NSBU PL).",
  "Сводка по портфелю": "Портфель бўйича хулоса",
  "Топ-3 риска по портфелю": "Портфель бўйича топ-3 риск",
  "Исполнение задач Ожиданий Акционера": "Акциядор кутилмалари вазифаларининг ижроси",
  // «портфель» в суффиксальных формах (транслит дал бы «портфелнинг/портфелдаги»)
  "Налоговый вклад портфеля": "Портфельнинг солиқ ҳиссаси",
  "Все компании портфеля учтены": "Портфельдаги барча компаниялар ҳисобга олинган",
  "Подробнее: Доля портфеля в бюджете Республики": "Батафсил: Портфельнинг Республика бюджетидаги улуши",
  // «акцизлар» — транслит «aksizlar» дал бы «аксизлар»
  "Налог на прибыль (факт по отчётности НСБУ) + НДС (расчётная оценка). Не включает НДПИ, акцизы, роялти и дивиденды — итог является оценкой.":
    "Фойда солиғи (BHMS ҳисоботи бўйича факт) + QQS (ҳисоб-китоб баҳоси). Ер қаъри солиғи, акцизлар, роялти ва дивидендлар кирмайди — жами тахминий баҳо ҳисобланади.",
  // «Forensic» — бренд-термин, остаётся латиницей (транслит дал бы «Форенсис»)
  "Forensic тендер": "Forensic тендери",
  "Для FY {y} нет информации о внедрении МСФО / Forensic":
    "FY {y} учун MHXS / Forensic жорий этилиши ҳақида маълумот йўқ",
  "Все компании завершили МСФО и Forensic": "Барча компаниялар MHXS ва Forensic аудитини якунлаган",
  // «vs» остаётся латиницей (транслит дал бы «вс»)
  "Сравни 2025 vs 2026": "2025 vs 2026 ни таққосла",
};
