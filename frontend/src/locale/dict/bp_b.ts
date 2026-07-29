/**
 * Словарь модуля «Бизнес-план» (bp_b): BpAiAnalysis, BpEditor, BusinessPlan.
 * Ключ — русская строка, как она передана в t(). Общеплатформенные термины
 * (Сохранить, План, Факт, Доходы, Расходы, НСБУ…) — в common.ts, здесь их НЕТ.
 */

export const uz: Record<string, string> = {
  // ── BpAiAnalysis: кнопка/шапка ──
  "ИИ-анализ бизнес-плана": "Biznes-rejaning AI tahlili",
  
  
  "ИИ-АНАЛИЗ БИЗНЕС-ПЛАНА": "BIZNES-REJA AI TAHLILI",
  
  "ПОРТФЕЛЬ": "PORTFEL",
  "Скопировать ответ": "Javobni nusxalash",
  "Выгрузить таблицы в Excel": "Jadvallarni Excelga yuklab olish",

  // ── BpAiAnalysis: контролы ──
  "Охват": "Qamrov",
  "Весь портфель": "Butun portfel",
  "Одна компания": "Bitta kompaniya",
  "Режим": "Rejim",
  "Пересчитать": "Qayta hisoblash",
  "Запустить анализ": "Tahlilni boshlash",
  "Произв. ↔ Финансы": "Ishlab chiq. ↔ Moliya",
  "Произв.↔Финансы": "Ishlab chiq.↔Moliya",
  "План / ожидаемое / факт по ОФР и производству": "Moliyaviy natijalar hisoboti va ishlab chiqarish boʻyicha reja / kutilayotgan / fakt",
  "Связь натурального объёма с выручкой/маржой/прибылью": "Natural hajmning tushum/marja/foyda bilan bogʻliqligi",
  "Прогноз будущих целей БП + факторы (сырьё, курс, санкции)": "Biznes-rejaning kelgusi maqsadlari prognozi + omillar (xomashyo, kurs, sanksiyalar)",
  "Все компании портфеля": "Portfeldagi barcha kompaniyalar",

  // ── BpAiAnalysis: прогнозная таблица/график ──
  "Прогноз выручки «{name}» (история → прогноз), млрд сум": "«{name}» tushum prognozi (tarix → prognoz), mlrd soʻm",
  "прогноз": "prognoz",
  "Модельный прогноз БП (движок)": "Biznes-rejaning model prognozi (hisoblash mexanizmi)",
  "По годам": "Yillar boʻyicha",
  "По кварталам": "Choraklar boʻyicha",
  
  
  "Тек. факт": "Joriy fakt",
  "Ожид. {y}": "Kutil. {y}",
  "Метод": "Metod",
  "Числа — детерминированный движок (воспроизводимо, деньги млрд сум); коридор [low…high] — неопределённость.": "Raqamlar — deterministik hisoblash mexanizmi (takrorlanadigan, pul mlrd soʻm); [low…high] koridori — noaniqlik.",
  "Кварталы будущих лет — разбивка годового прогноза по сезонности плана.": "Kelgusi yillar choraklari — yillik prognozning reja mavsumiyligi boʻyicha taqsimoti.",
  "ИИ ниже накладывает факторы (цены на сырьё, курс, санкции, макро) и корректирует.": "Quyida AI omillarni (xomashyo narxlari, valyuta kursi, sanksiyalar, makro) hisobga olib tuzatadi.",
  "Исполнение по метрикам, факт/план %": "Metrikalar boʻyicha ijro, fakt/reja %",
  "Исполнение по компаниям (выручка), факт/план %": "Kompaniyalar boʻyicha ijro (tushum), fakt/reja %",
  
  "ИИ разберёт исполнение плана (план / ожидаемое / факт по ОФР и производству), свяжет производство с финансами и — в режиме «Прогноз» — предскажет будущие цели БП с учётом цен на сырьё, курса и санкций.": "AI reja ijrosini tahlil qiladi (moliyaviy natijalar hisoboti va ishlab chiqarish boʻyicha reja / kutilayotgan / fakt), ishlab chiqarishni moliya bilan bogʻlaydi va «Prognoz» rejimida xomashyo narxlari, kurs va sanksiyalarni hisobga olgan holda biznes-rejaning kelgusi maqsadlarini bashorat qiladi.",

  // ── BpAiAnalysis: методы движка ──
  "темп": "surʼat",
  "сезон": "mavsum",
  "план": "reja",
  "факт": "fakt",
  "тренд": "trend",

  // ── BpAiAnalysis: шаги/ошибки/тосты/экспорт ──
  "Загружаю БП: {name}…": "Biznes-reja yuklanmoqda: {name}…",
  "Загружаю бизнес-план всех компаний…": "Barcha kompaniyalar biznes-rejasi yuklanmoqda…",
  "Подтягиваю производственный план…": "Ishlab chiqarish rejasi yuklanmoqda…",
  "Считаю модельный прогноз БП (годы + кварталы)…": "Biznes-rejaning model prognozi hisoblanmoqda (yillar + choraklar)…",
  "ИИ анализирует бизнес-план…": "AI biznes-rejani tahlil qilmoqda…",
  "Нет данных бизнес-плана за этот год. Заведите показатели в редакторе.": "Bu yil uchun biznes-reja maʼlumotlari yoʻq. Koʻrsatkichlarni muharrirda kiriting.",
  "ИИ вернул пустой ответ.": "AI boʻsh javob qaytardi.",
  "Ошибка анализа": "Tahlil xatosi",
  "Анализ скопирован": "Tahlil nusxalandi",
  "Не удалось скопировать": "Nusxalab boʻlmadi",
  
  "Модель прогноза": "Prognoz modeli",
  "Таблица {n}": "Jadval {n}",
  "Полный текст": "Toʻliq matn",
  "портфель": "portfel",

  // ── BpEditor: шапка/контролы ──
  "Редактор бизнес-плана": "Biznes-reja muharriri",
  "Переключить компанию": "Kompaniyani almashtirish",
  "Только доходные статьи (revenue, finIncome + subs)": "Faqat daromad moddalari (revenue, finIncome + subs)",
  "Только расходные статьи (cogs, opExpenses, finCost, tax + sub-items)": "Faqat xarajat moddalari (cogs, opExpenses, finCost, tax + sub-items)",
  "Черновик плана из истории фактов (CAGR/OLS + историческая сезонность). Заполняет только пустые ячейки плана; ничего не сохраняет сам.": "Fakt tarixidan reja qoralamasi (CAGR/OLS + tarixiy mavsumiylik). Faqat boʻsh reja kataklarini toʻldiradi; oʻzi hech narsani saqlamaydi.",
  "Расчёт…": "Hisoblanmoqda…",
  "Рассчитать план": "Rejani hisoblash",
  "Сумма (план)": "Summa (reja)",
  "Сумма (факт)": "Summa (fakt)",
  "Δ план→факт": "Δ reja→fakt",
  "% выручки": "Tushumga nisbatan %",
  "Повторить": "Qayta urinish",

  // ── BpEditor: ячейки/бейджи ──
  "Рассчитывается автоматически: {formula}": "Avtomatik hisoblanadi: {formula}",
  "∑ расчёт": "∑ hisob",
  "Итог по формуле ({formula}), но можно переопределить вручную по компании. Факт — автоподстановка из НСБУ.": "Formula boʻyicha jami ({formula}), lekin kompaniya boʻyicha qoʻlda oʻzgartirish mumkin. Fakt — BHMSdan avtomatik olinadi.",
  "итог · правится": "jami · tahrirlanadi",
  "Расчёт по формуле ({formula}): {value}. Введите своё значение, чтобы переопределить.": "Formula boʻyicha hisob ({formula}): {value}. Oʻzgartirish uchun oʻz qiymatingizni kiriting.",
  "Подставить расчёт: {value}": "Hisobni qoʻyish: {value}",
  "Автоподстановка ({src}): {value}. Введите своё значение, чтобы переопределить.": "Avtomatik qiymat ({src}): {value}. Oʻzgartirish uchun oʻz qiymatingizni kiriting.",
  "Источник обновился: {value} ({src}). Введено вручную: {manual}.": "Manba yangilandi: {value} ({src}). Qoʻlda kiritilgan: {manual}.",
  "Автоподстановка из {src}": "{src} manbasidan avtomatik",
  "авто": "avto",
  "Введено вручную": "Qoʻlda kiritilgan",
  "✎ вручную": "✎ qoʻlda",
  "Применить значение источника ({src}): {value}": "Manba qiymatini qoʻllash ({src}): {value}",
  "↻ обновить": "↻ yangilash",
  "нараст. итог (Q4)": "oʻsib bor. jami (Q4)",

  // ── BpEditor: черновик плана ──
  "Черновик плана": "Reja qoralamasi",
  "Из истории {years} · движок CAGR/OLS + историческая сезонность · применяется только в": "{years} tarixidan · CAGR/OLS mexanizmi + tarixiy mavsumiylik · faqat",
  "пустые": "boʻsh",
  "ячейки плана · ничего не сохраняется до «Сохранить все периоды»": "reja kataklariga qoʻllanadi · «Barcha davrlarni saqlash» bosilmaguncha hech narsa saqlanmaydi",
  "Год (план)": "Yil (reja)",
  "Коридор": "Koridor",
  "Годовой план уже введён — черновик его не тронет": "Yillik reja allaqachon kiritilgan — qoralama unga tegmaydi",
  "занято": "band",
  "сезонности нет — только год": "mavsumiylik yoʻq — faqat yil",
  "OLS-тренд": "OLS-trend",
  "высокая": "yuqori",
  "средняя": "oʻrtacha",
  "низкая": "past",
  
  "Пустых ячеек плана нет — всё уже введено": "Boʻsh reja kataklari yoʻq — hammasi kiritilgan",
  "Заполнить пустые планы": "Boʻsh rejalarni toʻldirish",
  "Не удалось построить черновик плана: {reason}": "Reja qoralamasini tuzib boʻlmadi: {reason}",
  
  "Пустых ячеек плана нет — черновик ничего не менял": "Boʻsh reja kataklari yoʻq — qoralama hech narsani oʻzgartirmadi",

  // ── BpEditor: футер/статусы/сохранение ──
  "Несохранённые изменения": "Saqlanmagan oʻzgarishlar",
  "Отличается от источника:": "Manbadan farq qiladi:",
  "ячейка": "katak",
  "ячеек": "katak",
  "«обновить» в ячейке возьмёт значение источника (НСБУ/кварталы)": "katakdagi «yangilash» manba qiymatini oladi (BHMS/choraklar)",
  "Автоподставлено фактов:": "Avtomatik olingan faktlar:",
  "пустой «Факт» берётся из источника, можно переопределить вручную": "boʻsh «Fakt» manbadan olinadi, qoʻlda oʻzgartirish mumkin",
  "Данных источника (НСБУ / закрытые кварталы) за {year} пока нет — ручной ввод": "{year} uchun manba maʼlumotlari (BHMS / yopilgan choraklar) hozircha yoʻq — qoʻlda kiritish",
  "Квартальный период — значения НАРАСТАЮЩИМ ИТОГОМ с начала года (Q1 = 1 кв, Q2 = полугодие, Q3 = 9 мес, Q4 = год)": "Chorak davri — qiymatlar yil boshidan oʻsib boruvchi jami (Q1 = 1-chorak, Q2 = yarim yillik, Q3 = 9 oy, Q4 = yil)",
  
  "Сохранить все периоды": "Barcha davrlarni saqlash",
  "Только просмотр · нет прав на редактирование": "Faqat koʻrish · tahrirlash huquqi yoʻq",
  "Есть несохранённые изменения. Переключить компанию и потерять их?": "Saqlanmagan oʻzgarishlar bor. Kompaniya almashtirilib, ular yoʻqotilsinmi?",
  
  "Не удалось загрузить сохранённые данные. Не сохраняйте, чтобы не затереть существующие значения — нажмите «Повторить».": "Saqlangan maʼlumotlarni yuklab boʻlmadi. Mavjud qiymatlarni yoʻqotmaslik uchun saqlamang — «Qayta urinish» tugmasini bosing.",
  "Нет данных для сохранения": "Saqlash uchun maʼlumot yoʻq",
  "Кто-то сохранил изменения, пока вы редактировали. Перезагрузите редактор.": "Siz tahrirlayotganda kimdir oʻzgarishlarni saqladi. Muharrirni qayta yuklang.",
  "Конфликт: данные изменились. Перезагрузите редактор, чтобы не затереть чужие правки.": "Konflikt: maʼlumotlar oʻzgardi. Boshqalar kiritgan oʻzgarishlarni yoʻqotmaslik uchun muharrirni qayta yuklang.",
  "Сохранено · {n} ячеек записано": "Saqlandi · {n} katak yozildi",
  "Бизнес-план сохранён": "Biznes-reja saqlandi",
  "Не сохранено: {reason}": "Saqlanmadi: {reason}",
  "Бизнес-план не сохранён: {reason}": "Biznes-reja saqlanmadi: {reason}",

  // ── Статьи ОФР (BP_FIELDS, BHMS-терминология) ──
  
  "Себестоимость реализованной продукции": "Sotilgan mahsulot tannarxi",
  "Расходы периода": "Davr xarajatlari",
  "— расходы на реализацию": "— sotish xarajatlari",
  "— административные расходы": "— maʼmuriy xarajatlar",
  "— прочие операционные расходы": "— boshqa operatsion xarajatlar",
  "Прочие доходы от основной деятельности": "Asosiy faoliyatdan boshqa daromadlar",
  "Финансовые доходы": "Moliyaviy daromadlar",
  
  
  
  "— прочие фин. доходы": "— boshqa moliyaviy daromadlar",
  "Финансовые расходы": "Moliyaviy xarajatlar",
  
  
  "— прочие фин. расходы": "— boshqa moliyaviy xarajatlar",
  "Прибыль от общехоз. деятельности": "Umumxoʻjalik faoliyatidan foyda",
  
  "Налог на прибыль": "Foyda soligʻi",
  

  // ── BusinessPlan.vue: топбар/пикер/пустые состояния ──
  "Удалить год": "Yilni oʻchirish",
  "— выберите компанию —": "— kompaniyani tanlang —",
  "Добавить новую компанию": "Yangi kompaniya qoʻshish",
  "Нет данных бизнес-плана. Перейдите в режим «По компании» и заведите данные.": "Biznes-reja maʼlumotlari yoʻq. «Kompaniya boʻyicha» rejimiga oʻting va maʼlumotlarni kiriting.",
  "Выберите компанию для просмотра деталей.": "Tafsilotlarni koʻrish uchun kompaniyani tanlang.",
  "Финансовые": "Moliyaviy",
  "Производственные": "Ishlab chiqarish",
  
  "По компании": "Kompaniya boʻyicha",
  
  "Выберите компанию": "Kompaniyani tanlang",
  "годовой итог": "yillik jami",
  "за квартал {q}": "{q} choragi uchun",
  "FY {year} · {period} · {n} компаний · млрд сум": "FY {year} · {period} · {n} ta kompaniya · mlrd soʻm",
  "FY {year} · {period} · млрд сум": "FY {year} · {period} · mlrd soʻm",
  "Сначала выберите компанию в режиме «По компании»": "Avval «Kompaniya boʻyicha» rejimida kompaniyani tanlang",
  "Удалить весь бизнес-план {name} за {year}?": "{name} kompaniyasining {year} yilgi butun biznes-rejasi oʻchirilsinmi?",
  "Не удалось удалить": "Oʻchirib boʻlmadi",
  "План vs Факт по портфелю": "Portfel boʻyicha Reja vs Fakt",
  "Где провал?": "Qayerda ortda qolinmoqda?",
  
  "Сводка расходов": "Xarajatlar jamlanmasi",
};

export const en: Record<string, string> = {
  // ── BpAiAnalysis: кнопка/шапка ──
  "ИИ-анализ бизнес-плана": "AI analysis of the business plan",
  "Анализирую…": "Analyzing…",
  "Анализ ИИ": "AI analysis",
  "ИИ-АНАЛИЗ БИЗНЕС-ПЛАНА": "BUSINESS PLAN AI ANALYSIS",
  
  "ПОРТФЕЛЬ": "PORTFOLIO",
  "Скопировать ответ": "Copy answer",
  "Выгрузить таблицы в Excel": "Export tables to Excel",

  // ── BpAiAnalysis: контролы ──
  "Охват": "Scope",
  "Весь портфель": "Entire portfolio",
  "Одна компания": "Single company",
  "Режим": "Mode",
  "Пересчитать": "Recalculate",
  "Запустить анализ": "Run analysis",
  "Произв. ↔ Финансы": "Production ↔ Finance",
  "Произв.↔Финансы": "Production↔Finance",
  "План / ожидаемое / факт по ОФР и производству": "Plan / expected / actual for P&L and production",
  "Связь натурального объёма с выручкой/маржой/прибылью": "Link between physical volumes and revenue/margin/profit",
  "Прогноз будущих целей БП + факторы (сырьё, курс, санкции)": "Forecast of future BP targets + factors (commodities, FX, sanctions)",
  "Все компании портфеля": "All portfolio companies",

  // ── BpAiAnalysis: прогнозная таблица/график ──
  "Прогноз выручки «{name}» (история → прогноз), млрд сум": "Revenue forecast “{name}” (history → forecast), bn UZS",
  "прогноз": "forecast",
  "Модельный прогноз БП (движок)": "Model BP forecast (engine)",
  
  
  "{y} г.": "{y}",
  "Метрика": "Metric",
  
  "Ожид. {y}": "Exp. {y}",
  "Метод": "Method",
  "Числа — детерминированный движок (воспроизводимо, деньги млрд сум); коридор [low…high] — неопределённость.": "Figures come from a deterministic engine (reproducible, money in bn UZS); the [low…high] band reflects uncertainty.",
  "Кварталы будущих лет — разбивка годового прогноза по сезонности плана.": "Future-year quarters split the annual forecast by plan seasonality.",
  "ИИ ниже накладывает факторы (цены на сырьё, курс, санкции, макро) и корректирует.": "Below, the AI overlays factors (commodity prices, FX rate, sanctions, macro) and adjusts.",
  "Исполнение по метрикам, факт/план %": "Execution by metric, actual/plan %",
  "Исполнение по компаниям (выручка), факт/план %": "Execution by company (revenue), actual/plan %",
  "Выберите охват и режим, затем запустите анализ.": "Choose scope and mode, then run the analysis.",
  "ИИ разберёт исполнение плана (план / ожидаемое / факт по ОФР и производству), свяжет производство с финансами и — в режиме «Прогноз» — предскажет будущие цели БП с учётом цен на сырьё, курса и санкций.": "The AI reviews plan execution (plan / expected / actual for P&L and production), links production to financials and — in Forecast mode — projects future BP targets factoring in commodity prices, FX and sanctions.",

  // ── BpAiAnalysis: методы движка ──
  "темп": "pace",
  "сезон": "seasonal",
  "план": "plan",
  "факт": "actual",
  "тренд": "trend",

  // ── BpAiAnalysis: шаги/ошибки/тосты/экспорт ──
  "Загружаю БП: {name}…": "Loading BP: {name}…",
  "Загружаю бизнес-план всех компаний…": "Loading all companies' business plans…",
  "Подтягиваю производственный план…": "Fetching production plan…",
  "Считаю модельный прогноз БП (годы + кварталы)…": "Computing model BP forecast (years + quarters)…",
  "ИИ анализирует бизнес-план…": "AI is analyzing the business plan…",
  "Нет данных бизнес-плана за этот год. Заведите показатели в редакторе.": "No business plan data for this year. Enter indicators in the editor.",
  
  "Ошибка анализа": "Analysis error",
  "Анализ скопирован": "Analysis copied",
  "Не удалось скопировать": "Failed to copy",
  
  "Модель прогноза": "Forecast model",
  "Таблица {n}": "Table {n}",
  "Полный текст": "Full text",
  "портфель": "portfolio",

  // ── BpEditor: шапка/контролы ──
  "Редактор бизнес-плана": "Business plan editor",
  "Переключить компанию": "Switch company",
  "Только доходные статьи (revenue, finIncome + subs)": "Income items only (revenue, finIncome + subs)",
  "Только расходные статьи (cogs, opExpenses, finCost, tax + sub-items)": "Expense items only (cogs, opExpenses, finCost, tax + sub-items)",
  "Черновик плана из истории фактов (CAGR/OLS + историческая сезонность). Заполняет только пустые ячейки плана; ничего не сохраняет сам.": "Plan draft from actuals history (CAGR/OLS + historical seasonality). Fills only empty plan cells; saves nothing by itself.",
  "Расчёт…": "Calculating…",
  
  "Сумма (план)": "Total (plan)",
  "Сумма (факт)": "Total (actual)",
  "Δ план→факт": "Δ plan→actual",
  "% выручки": "% of revenue",
  "Повторить": "Retry",

  // ── BpEditor: ячейки/бейджи ──
  "Рассчитывается автоматически: {formula}": "Calculated automatically: {formula}",
  "∑ расчёт": "∑ calc",
  "Итог по формуле ({formula}), но можно переопределить вручную по компании. Факт — автоподстановка из НСБУ.": "Formula total ({formula}), but can be overridden manually per company. Actual is auto-filled from NAS.",
  "итог · правится": "total · editable",
  "Расчёт по формуле ({formula}): {value}. Введите своё значение, чтобы переопределить.": "Formula value ({formula}): {value}. Enter your own value to override.",
  "Подставить расчёт: {value}": "Insert calculated value: {value}",
  "Автоподстановка ({src}): {value}. Введите своё значение, чтобы переопределить.": "Auto-filled ({src}): {value}. Enter your own value to override.",
  "Источник обновился: {value} ({src}). Введено вручную: {manual}.": "Source updated: {value} ({src}). Entered manually: {manual}.",
  "Автоподстановка из {src}": "Auto-filled from {src}",
  "авто": "auto",
  "Введено вручную": "Entered manually",
  "✎ вручную": "✎ manual",
  "Применить значение источника ({src}): {value}": "Apply source value ({src}): {value}",
  "↻ обновить": "↻ update",
  

  // ── BpEditor: черновик плана ──
  "Черновик плана": "Plan draft",
  "Из истории {years} · движок CAGR/OLS + историческая сезонность · применяется только в": "From {years} history · CAGR/OLS engine + historical seasonality · applies only to",
  "пустые": "empty",
  "ячейки плана · ничего не сохраняется до «Сохранить все периоды»": "plan cells · nothing is saved until “Save all periods”",
  "Год (план)": "Year (plan)",
  "Коридор": "Range",
  "Годовой план уже введён — черновик его не тронет": "Annual plan already entered — the draft will not touch it",
  
  "сезонности нет — только год": "no seasonality — year only",
  "OLS-тренд": "OLS trend",
  "высокая": "high",
  "средняя": "medium",
  "низкая": "low",
  "Заполнит {n} пустых ячеек плана": "Will fill {n} empty plan cells",
  
  "Заполнить пустые планы": "Fill empty plans",
  "Не удалось построить черновик плана: {reason}": "Failed to build plan draft: {reason}",
  "Черновик применён: заполнено {n} ячеек плана — проверьте и сохраните": "Draft applied: {n} plan cells filled — review and save",
  "Пустых ячеек плана нет — черновик ничего не менял": "No empty plan cells — the draft changed nothing",

  // ── BpEditor: футер/статусы/сохранение ──
  "Несохранённые изменения": "Unsaved changes",
  "Отличается от источника:": "Differs from source:",
  "ячейка": "cell",
  "ячеек": "cells",
  "«обновить» в ячейке возьмёт значение источника (НСБУ/кварталы)": "“update” in a cell takes the source value (NAS/quarters)",
  "Автоподставлено фактов:": "Auto-filled actuals:",
  "пустой «Факт» берётся из источника, можно переопределить вручную": "an empty “Actual” is taken from the source; you can override it manually",
  "Данных источника (НСБУ / закрытые кварталы) за {year} пока нет — ручной ввод": "No source data (NAS / closed quarters) for {year} yet — manual entry",
  "Квартальный период — значения НАРАСТАЮЩИМ ИТОГОМ с начала года (Q1 = 1 кв, Q2 = полугодие, Q3 = 9 мес, Q4 = год)": "Quarterly period — values are cumulative YEAR-TO-DATE (Q1 = Q1, Q2 = half-year, Q3 = 9 months, Q4 = full year)",
  
  "Сохранить все периоды": "Save all periods",
  "Только просмотр · нет прав на редактирование": "View only · no edit permission",
  "Есть несохранённые изменения. Переключить компанию и потерять их?": "There are unsaved changes. Switch company and lose them?",
  "неизвестная ошибка": "unknown error",
  "Не удалось загрузить сохранённые данные. Не сохраняйте, чтобы не затереть существующие значения — нажмите «Повторить».": "Failed to load saved data. Do not save, to avoid overwriting existing values — click “Retry”.",
  "Нет данных для сохранения": "No data to save",
  "Кто-то сохранил изменения, пока вы редактировали. Перезагрузите редактор.": "Someone saved changes while you were editing. Reload the editor.",
  "Конфликт: данные изменились. Перезагрузите редактор, чтобы не затереть чужие правки.": "Conflict: data changed. Reload the editor to avoid overwriting others' edits.",
  "Сохранено · {n} ячеек записано": "Saved · {n} cells written",
  "Бизнес-план сохранён": "Business plan saved",
  "Не сохранено: {reason}": "Not saved: {reason}",
  "Бизнес-план не сохранён: {reason}": "Business plan not saved: {reason}",

  // ── Статьи ОФР (BP_FIELDS) ──
  "Чистая выручка от реализации": "Net sales revenue",
  "Себестоимость реализованной продукции": "Cost of goods sold",
  "Расходы периода": "Period expenses",
  "— расходы на реализацию": "— selling expenses",
  "— административные расходы": "— administrative expenses",
  "— прочие операционные расходы": "— other operating expenses",
  
  "Финансовые доходы": "Finance income",
  "— доходы в виде дивидендов": "— dividend income",
  "— доходы в виде процентов": "— interest income",
  
  "— прочие фин. доходы": "— other finance income",
  "Финансовые расходы": "Finance costs",
  "— расходы в виде процентов": "— interest expense",
  
  "— прочие фин. расходы": "— other finance costs",
  "Прибыль от общехоз. деятельности": "Profit from ordinary activities",
  "Прибыль до налогообложения": "Profit before tax",
  "Налог на прибыль": "Income tax",
  "Чистая прибыль (убыток) периода": "Net profit (loss) for the period",

  // ── BusinessPlan.vue: топбар/пикер/пустые состояния ──
  "Удалить год": "Delete year",
  
  
  "Нет данных бизнес-плана. Перейдите в режим «По компании» и заведите данные.": "No business plan data. Switch to “By company” mode and enter data.",
  "Выберите компанию для просмотра деталей.": "Select a company to view details.",
  "Финансовые": "Financial",
  "Производственные": "Production",
  "Сводка": "Summary",
  "По компании": "By company",
  "Сводка по портфелю": "Portfolio summary",
  "Выберите компанию": "Select a company",
  "годовой итог": "annual total",
  "за квартал {q}": "for quarter {q}",
  "FY {year} · {period} · {n} компаний · млрд сум": "FY {year} · {period} · {n} companies · bn UZS",
  "FY {year} · {period} · млрд сум": "FY {year} · {period} · bn UZS",
  "Сначала выберите компанию в режиме «По компании»": "First select a company in “By company” mode",
  "Удалить весь бизнес-план {name} за {year}?": "Delete the entire business plan of {name} for {year}?",
  "Не удалось удалить": "Failed to delete",
  "План vs Факт по портфелю": "Plan vs Actual across portfolio",
  "Где провал?": "Where are the gaps?",
  "Сравни 2025 vs 2026": "Compare 2025 vs 2026",
  "Сводка расходов": "Expense summary",
};

/**
 * Исключения кириллицы:
 *  - ALL-CAPS латиница трактуется транслитом как акроним и осталась бы латиницей;
 *  - «Excel» — бренд, остаётся латиницей;
 *  - sanksiya→санкция, operatsion→операцион (ц), model→модель (ь).
 */
export const cyr: Record<string, string> = {
  "ИИ-АНАЛИЗ БИЗНЕС-ПЛАНА": "БИЗНЕС-РЕЖА AI ТАҲЛИЛИ",
  "КОМПАНИЯ": "КОМПАНИЯ",
  "ПОРТФЕЛЬ": "ПОРТФЕЛЬ",
  "Выгрузить таблицы в Excel": "Жадвалларни Excelga юклаб олиш",
  "Модельный прогноз БП (движок)": "Бизнес-режанинг модель прогнози (ҳисоблаш механизми)",
  "Считаю модельный прогноз БП (годы + кварталы)…": "Бизнес-режанинг модель прогнози ҳисобланмоқда (йиллар + чораклар)…",
  "ИИ ниже накладывает факторы (цены на сырьё, курс, санкции, макро) и корректирует.": "Қуйида AI омилларни (хомашё нархлари, валюта курси, санкциялар, макро) ҳисобга олиб тузатади.",
  "ИИ разберёт исполнение плана (план / ожидаемое / факт по ОФР и производству), свяжет производство с финансами и — в режиме «Прогноз» — предскажет будущие цели БП с учётом цен на сырьё, курса и санкций.": "AI режа ижросини таҳлил қилади (молиявий натижалар ҳисоботи ва ишлаб чиқариш бўйича режа / кутилаётган / факт), ишлаб чиқаришни молия билан боғлайди ва «Прогноз» режимида хомашё нархлари, курс ва санкцияларни ҳисобга олган ҳолда бизнес-режанинг келгуси мақсадларини башорат қилади.",
  "Прогноз будущих целей БП + факторы (сырьё, курс, санкции)": "Бизнес-режанинг келгуси мақсадлари прогнози + омиллар (хомашё, курс, санкциялар)",
  "— прочие операционные расходы": "— бошқа операцион харажатлар",
  // «портфель»: транслит «portfel» терял бы «ь»
  "Весь портфель": "Бутун портфель",
  "Все компании портфеля": "Портфельдаги барча компаниялар",
  "портфель": "портфель",
  
  "План vs Факт по портфелю": "Портфель бўйича Режа vs Факт",
};
