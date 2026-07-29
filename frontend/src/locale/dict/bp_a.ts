/**
 * Словарь модуля «Бизнес-план» (дашборды, дриллы, производственные показатели).
 * bucket: bp_a — BpCompanyDashboard, BpDrillModal, BpProductionDashboard,
 * BpQuarterDrillModal, BpQuarterlyChart, BpSummaryDashboard,
 * CwProductionSection, ProductionDrillModal, ProductionEditModal.
 *
 * Ключи common.ts здесь НЕ дублируются.
 * Включены переводы строк BP_FIELDS (api/bpKpi.ts) и зон execBand — они
 * отображаются именно в этих компонентах через t(f.label)/t(pctZone()).
 */

export const uz: Record<string, string> = {
  // ── Статус-бар и KPI-карточки компании ──
  
  "На цели (≥95%)": "Maqsadda (≥95%)",
  "Критичных (<70%)": "Kritik (<70%)",
  "Год к году": "Yilma-yil",
  "нет данных": "maʼlumot yoʻq",
  "взвешенно · {n} метрик": "vaznlangan · {n} metrika",
  "нет фактов": "faktlar yoʻq",
  "показателей": "koʻrsatkich",
  
  "требуют решения": "qaror talab qiladi",
  "нет данных за {y}": "{y} uchun maʼlumot yoʻq",
  "по выручке к {y}": "tushum boʻyicha {y} ga nisbatan",
  "Расходы периода": "Davr xarajatlari",
  "Финансовые расходы": "Moliyaviy xarajatlar",
  "Налог на прибыль": "Foyda soligʻi",
  "Финансовые доходы": "Moliyaviy daromadlar",
  "Прочие опер. доходы": "Boshqa oper. daromadlar",
  "Прибыль до налогов": "Soliq toʻlagunga qadar foyda",

  // ── Прогноз кварталов (метод/уверенность) ──
  "план × темп": "reja × surʼat",
  "сезонность прошлого года": "oʻtgan yil mavsumiyligi",
  "по плану": "reja boʻyicha",
  "год закрыт": "yil yopilgan",
  "смешанный": "aralash",
  "увер.": "ishonch",
  "высокая": "yuqori",
  "средняя": "oʻrtacha",
  "низкая": "past",

  // ── Периоды/подписи ──
  "годовой итог": "yillik jami",
  "нарастающим итогом за {q}": "{q} uchun oʻsib boruvchi jami",
  "за квартал {q}": "{q} choragi uchun",
  "нарастающим итогом за {q} (пред. квартал не заполнен)":
    "{q} uchun oʻsib boruvchi jami (oldingi chorak toʻldirilmagan)",
  "годовой": "yillik",
  "год": "yil",

  // ── Комментарий руководителя ──
  "Комментарий сохранён": "Izoh saqlandi",
  "Не удалось сохранить": "Saqlab boʻlmadi",
  "Комментарий руководителя": "Rahbar izohi",
  "обновлено": "yangilangan",
  "Комментарий не задан. Нажмите «{btn}» чтобы добавить пояснение для НС.":
    "Izoh kiritilmagan. Kuzatuv kengashi uchun izoh qoʻshish uchun «{btn}» tugmasini bosing.",
  "Например: Операционный план Q1 выполнен на 104%. Отставание по IPO-процессу из-за задержки аудита — перенос на Q2...":
    "Masalan: Q1 operatsion reja 104% bajarildi. Audit kechikishi sababli IPO jarayonida ortda qolish — Q2 ga koʻchirildi...",
  
  "Сохранение…": "Saqlanmoqda…",

  // ── YTD-фолбэк ──
  "{q} не заполнен — показатели показаны нарастающим итогом с начала года; разбивка «за квартал» появится после заполнения предыдущего квартала в редакторе.":
    "{q} toʻldirilmagan — koʻrsatkichlar yil boshidan oʻsib boruvchi jami bilan koʻrsatilgan; «chorak uchun» taqsimot muharrirda oldingi chorak toʻldirilgach paydo boʻladi.",
  "Строки с меткой «нараст.» показаны нарастающим итогом: в {q} не заполнен факт — «за квартал» не вычислить. Внесите факт {q} в редакторе, и строки переключатся на «за квартал».":
    "«oʻsib bor.» belgili qatorlar oʻsib boruvchi jami bilan koʻrsatilgan: {q} da fakt toʻldirilmagan — «chorak uchun» hisoblab boʻlmaydi. Muharrirda {q} faktini kiriting, qatorlar «chorak uchun» rejimiga oʻtadi.",
  "нараст.": "oʻsib bor.",
  "Показано нарастающим итогом с начала года: в предыдущем квартале нет факта — «за квартал» не вычислить":
    "Yil boshidan oʻsib boruvchi jami koʻrsatilgan: oldingi chorakda fakt yoʻq — «chorak uchun» hisoblab boʻlmaydi",
  "Показано нарастающим итогом: в предыдущем квартале нет факта — «за квартал» не вычислить":
    "Oʻsib boruvchi jami koʻrsatilgan: oldingi chorakda fakt yoʻq — «chorak uchun» hisoblab boʻlmaydi",

  // ── KPI-карточки ──
  "авто из НСБУ: {n}": "BHMSdan avto: {n}",
  "Факт подставлен автоматически из НСБУ": "Fakt BHMSdan avtomatik olingan",
  "Автоматически из НСБУ": "BHMSdan avtomatik",
  "млрд сум · факт": "mlrd soʻm · fakt",
  "{n}% плана": "rejaning {n}%",
  "{n}% г/г": "{n}% yilma-yil",
  "— г/г": "— yilma-yil",
  "Итог года:": "Yil yakuni:",
  "План года:": "Yillik reja:",
  "план": "reja",
  "факт": "fakt",

  // ── Квартальный тренд / графики ──
  "Квартальный тренд": "Choraklik trend",
  "Нет квартальных данных за {y}": "{y} uchun choraklik maʼlumotlar yoʻq",
  "показатель разнесён только по году или не заведён":
    "koʻrsatkich faqat yil boʻyicha kiritilgan yoki umuman kiritilmagan",
  "За квартал · план": "Chorak uchun · reja",
  "За квартал · факт": "Chorak uchun · fakt",
  "за квартал не вычислимо: нет данных предыдущего квартала":
    "chorak uchun hisoblab boʻlmaydi: oldingi chorak maʼlumoti yoʻq",
  "Прогноз (за кв.)": "Prognoz (chorak)",
  "Коридор": "Koridor",
  "Нараст. план": "Oʻsib bor. reja",
  "Нараст. факт": "Oʻsib bor. fakt",
  "Нараст. итог": "Oʻsib bor. jami",
  "Исполнение с начала года": "Yil boshidan ijro",
  "Исполнение с начала года (нарастающим итогом)": "Yil boshidan ijro (oʻsib boruvchi jami)",
  "Открыть разбор →": "Tahlilni ochish →",
  "Ожидание": "Kutilayotgan",
  "Динамика по кварталам": "Choraklar boʻyicha dinamika",
  "План (за кв.)": "Reja (chorak)",
  "Факт (за кв.)": "Fakt (chorak)",
  "план разнесён лишь частью компаний ({v})": "reja faqat bir qism kompaniyalar boʻyicha kiritilgan ({v})",
  "Покрытие": "Qamrov",
  "комп.": "komp.",
  "в итог входят компании без данных пред. квартала — поэтому Σ баров ≠ нараст. итогу":
    "jamiga oldingi chorak maʼlumoti boʻlmagan kompaniyalar ham kiradi — shu sababli barlar Σ ≠ oʻsib boruvchi jami",

  // ── Внимание / достижения ──
  "Требуют решения": "Qaror talab qiladi",
  "Критических отклонений нет": "Kritik ogʻishlar yoʻq",
  "Достижения периода": "Davr yutuqlari",
  "Нет показателей ≥100% плана": "Reja ≥100% boʻlgan koʻrsatkichlar yoʻq",

  // ── Детализация ОФР ──
  "Детализация ОФР": "Moliyaviy natijalar tafsiloti",
  "Структура": "Tuzilma",
  "Раскрыть все": "Barchasini yoyish",
  "% плана": "reja %",
  "расчёт": "hisob",
  "∑ расчёт": "∑ hisob",
  "Структура ОФР": "Moliyaviy natijalar tuzilmasi",
  "{a} из {b} строк": "{b} qatordan {a} tasi",

  // ── Дрилл-модалка (BpDrillModal) ──
  "KPI · детализация по портфелю": "KPI · portfel boʻyicha tafsilot",
  "Строка P&L · декомпозиция по компаниям": "P&L qatori · kompaniyalar kesimida",
  "Бизнес-план компании · полный профиль": "Kompaniya biznes-rejasi · toʻliq profil",
  "Сектор · профиль и компании": "Tarmoq · profil va kompaniyalar",
  
  "{n} компаний сектора": "tarmoqda {n} kompaniya",
  "млрд UZS": "mlrd UZS",
  "{n} прочих": "boshqa {n} ta",
  "Загрузка данных по компаниям…": "Kompaniyalar maʼlumotlari yuklanmoqda…",
  "Сумма факт": "Jami fakt",
  "Сумма план": "Jami reja",
  "к плану": "rejaga nisbatan",
  "По факту": "Fakt boʻyicha",
  "По % плана": "Reja % boʻyicha",
  "По отклонению": "Ogʻish boʻyicha",
  "Только <90%": "Faqat <90%",
  "Загрузка декомпозиции по компаниям…": "Kompaniyalar kesimi yuklanmoqda…",
  "Итого факт": "Jami fakt",
  "Топ-3 доля": "Top-3 ulushi",
  "из плана {v}": "{v} rejadan",
  "Декомпозиция по компаниям · клик по столбцу — сортировка":
    "Kompaniyalar kesimi · ustunga bosish — saralash",
  "Доля": "Ulush",
  "ИТОГО · {n} комп.": "Jami · {n} komp.",
  "Загрузка профиля компании…": "Kompaniya profili yuklanmoqda…",
  "Динамика кварталов · выручка": "Choraklar dinamikasi · tushum",
  "Квартальные данные не введены": "Choraklik maʼlumotlar kiritilmagan",
  "В выбранном секторе нет компаний с данными": "Tanlangan tarmoqda maʼlumotli kompaniyalar yoʻq",
  "Доля сектора в портфеле": "Tarmoqning portfeldagi ulushi",
  "от {v}": "{v} dan",
  "Компании сектора": "Tarmoq kompaniyalari",
  "Средн. % плана": "Oʻrtacha reja %",
  "Компаний": "Kompaniyalar",
  "Лидер сектора": "Tarmoq yetakchisi",
  "Доля портфеля": "Portfel ulushi",

  // ── Разбор квартала (BpQuarterDrillModal) ──
  "нет факта": "fakt yoʻq",
  "план перевыполнен": "reja ortigʻi bilan bajarildi",
  "план выполнен": "reja bajarildi",
  "требует внимания": "eʼtibor talab qiladi",
  "недобор": "kam bajarilgan",
  "Разбор квартала": "Chorak tahlili",
  "План = 100%": "Reja = 100%",
  "исполнение с начала года · план = 100%": "yil boshidan ijro · reja = 100%",
  "За квартал {q}": "{q} choragi uchun",
  "Исполнение за квартал": "Chorak uchun ijro",
  "С начала года · нарастающим итогом": "Yil boshidan · oʻsib boruvchi jami",
  "Дельта факт−план": "Farq (fakt−reja)",

  // ── Сводка (BpSummaryDashboard) ──
  "— нет данных —": "— maʼlumot yoʻq —",
  "Δ план": "Δ reja",
  "С начала года (нарастающим итогом). Сумма «за квартал» по кварталам может отличаться: в итог входят и компании без данных предыдущего квартала.":
    "Yil boshidan (oʻsib boruvchi jami). Choraklar boʻyicha «chorak uchun» yigʻindisi farq qilishi mumkin: jamiga oldingi chorak maʼlumoti boʻlmagan kompaniyalar ham kiradi.",
  "Нараст. итогом": "Oʻsib bor. jami",
  "Топ-3 лидеры": "Top-3 yetakchilar",
  "Топ-3 отстающие": "Top-3 ortda qolganlar",
  "Нет данных по {m}": "{m} boʻyicha maʼlumot yoʻq",
  "расходам периода": "davr xarajatlari",
  "выручке": "tushum",
  "По секторам": "Tarmoqlar boʻyicha",
  "Открыть сектор": "Tarmoqni ochish",
  "{p} портфеля": "portfelning {p}",
  "Нет данных по секторам": "Tarmoqlar boʻyicha maʼlumot yoʻq",
  "P&L каскад · от выручки до чистой прибыли": "P&L kaskadi · tushumdan sof foydagacha",
  "Открыть строку P&L": "P&L qatorini ochish",
  "Валовая": "Yalpi",
  "Опер. расходы": "Oper. xarajatlar",
  "Опер. прибыль": "Oper. foyda",
  "трлн": "trln",
  "млрд": "mlrd",
  "Открыть детализацию": "Tafsilotni ochish",

  // ── Производственные показатели (дашборд) ──
  "не распознано листов: {n}": "aniqlanmagan varaqlar: {n}",
  "Загружено: {a} компаний · {b} с данными · {c} строк": "Yuklandi: {a} kompaniya · {b} maʼlumotli · {c} qator",
  "Импорт «Свода» из Excel": "«Svod» faylini Exceldan import qilish",
  "Импорт производственного «Свода» · Excel": "Ishlab chiqarish «Svod»i importi · Excel",
  "Файл с листом на компанию (натура + деньги: база → план → ожидаемое). Загрузится в период FY {y} · {p}.":
    "Har bir kompaniya uchun alohida varaqli fayl (natura + pul: baza → reja → kutilayotgan). FY {y} · {p} davriga yuklanadi.",
  "Нет производственных данных за выбранный период.": "Tanlangan davr uchun ishlab chiqarish maʼlumotlari yoʻq.",
  "сбросить": "tozalash",
  "За {y} заведены только фактические объёмы выпуска — плановый год ещё не открыт. План, ожидаемое и исполнение появятся для планового периода (2026).":
    "{y} uchun faqat haqiqiy ishlab chiqarish hajmlari kiritilgan — reja yili hali ochilmagan. Reja, kutilayotgan va ijro reja davri (2026) uchun paydo boʻladi.",
  "Совокупный фактический выпуск": "Jami haqiqiy ishlab chiqarish",
  "Фактический выпуск": "Haqiqiy ishlab chiqarish",
  "трлн сум": "trln soʻm",
  "Компаний с фактом": "Faktli kompaniyalar",
  "заполнено в периметре": "perimetr boʻyicha toʻldirilgan",
  "Секторов": "Tarmoqlar",
  "в периметре": "perimetrda",
  "Крупнейший выпуск": "Eng yirik ishlab chiqarish",
  "{n}% портфеля": "portfelning {n}%",
  "Сортировать по исполнению": "Ijro boʻyicha saralash",
  "Сводное исполнение": "Jamlanma ijro",
  "ожид / план": "kutil / reja",
  "Сортировать по плану": "Reja boʻyicha saralash",
  "План выпуска": "Ishlab chiqarish rejasi",
  "Сортировать по ожидаемому": "Kutilayotgan boʻyicha saralash",
  "{n}% к 2025": "2025 ga nisbatan {n}%",
  "Показать переисполнение": "Ortiqcha bajarilishni koʻrsatish",
  "Покрытие данными": "Maʼlumotlar qamrovi",
  "переисполнение: {n}": "ortiqcha bajarilish: {n}",
  "компаний с данными": "maʼlumotli kompaniyalar",
  "Свод по компаниям": "Kompaniyalar boʻyicha jamlanma",
  "Ожид.": "Kutil.",
  "Темп": "Surʼat",
  "Заполнить данные": "Maʼlumot kiritish",
  "по натуральному объёму": "natura hajmi boʻyicha",
  "н": "n",
  "факт —": "fakt —",
  "Нет компаний по фильтру": "Filtr boʻyicha kompaniyalar yoʻq",
  "Факт выпуска": "Haqiqiy ishlab chiqarish",
  "Структура выпуска": "Ishlab chiqarish tuzilmasi",
  "Сравнение": "Taqqoslash",
  "План · Ожид": "Reja · Kutil",
  "2025 факт": "2025 fakt",
  "2026 ожид.": "2026 kutil.",
  "ожид.": "kutil.",
  "темп роста": "oʻsish surʼati",
  "исполнение": "ijro",
  "факт 2025 → ожид. 2026": "2025 fakt → 2026 kutil.",
  "план → ожид., млрд UZS": "reja → kutil., mlrd UZS",
  "Нет числовых данных для графика": "Grafik uchun raqamli maʼlumot yoʻq",
  "факт выпуска · доля в портфеле": "haqiqiy ishlab chiqarish · portfeldagi ulush",

  // ── Производство: карточка компании / дрилл ──
  "Не удалось загрузить производственные показатели": "Ishlab chiqarish koʻrsatkichlarini yuklab boʻlmadi",
  "Бизнес-план · натуральные показатели": "Biznes-reja · natura koʻrsatkichlari",
  "Редактировать данные": "Maʼlumotlarni tahrirlash",
  "Загрузка производственных показателей…": "Ishlab chiqarish koʻrsatkichlari yuklanmoqda…",
  "Производственные показатели за {y} не заведены": "{y} uchun ishlab chiqarish koʻrsatkichlari kiritilmagan",
  "Данные по выпуску продукции (натура + деньги, план → ожидаемое) для «{name}» пока не заполнены.":
    "«{name}» uchun mahsulot ishlab chiqarish maʼlumotlari (natura + pul, reja → kutilayotgan) hali toʻldirilmagan.",
  "Заполнить показатели": "Koʻrsatkichlarni toʻldirish",
  "не введён": "kiritilmagan",
  "Темп роста": "Oʻsish surʼati",
  "к пред. периоду": "oldingi davrga nisbatan",
  "ожид": "kutil",
  "нат": "nat",
  "Продукция": "Mahsulot",
  
  "План (нат.)": "Reja (nat.)",
  "Ожид. (нат.)": "Kutil. (nat.)",
  "Факт (нат.)": "Fakt (nat.)",
  "План (млрд)": "Reja (mlrd)",
  "Ожид. (млрд)": "Kutil. (mlrd)",
  "Факт (млрд)": "Fakt (mlrd)",
  "Исп.": "Ijro",
  "Итоговые показатели без детализации по продукции": "Mahsulot boʻyicha tafsilotsiz jami koʻrsatkichlar",
  "Производственный план": "Ishlab chiqarish rejasi",
  "Нет детализации по продукции": "Mahsulot boʻyicha tafsilot yoʻq",

  // ── Редактор производства ──
  "Строку-итог удалить нельзя": "Jami qatorni oʻchirib boʻlmaydi",
  "Есть несохранённые изменения. Закрыть без сохранения?": "Saqlanmagan oʻzgarishlar bor. Saqlamasdan yopilsinmi?",
  "Нет строк для сохранения": "Saqlash uchun qatorlar yoʻq",
  "Отправлено на модерацию": "Moderatsiyaga yuborildi",
  "Производственные данные сохранены": "Ishlab chiqarish maʼlumotlari saqlandi",
  "Не сохранено: {e}": "Saqlanmadi: {e}",
  "ошибка": "xatolik",
  "Редактирование производства": "Ishlab chiqarishni tahrirlash",
  "не сохранено": "saqlanmagan",
  "Темп роста и исполнение считаются автоматически (по деньгам, при отсутствии — по натуре). Введите «Факт» для реального исполнения (факт / план); без факта показывается прогнозное (ожид. / план). Объёмы — неотрицательные.":
    "Oʻsish surʼati va ijro avtomatik hisoblanadi (pul boʻyicha, boʻlmasa — natura boʻyicha). Haqiqiy ijro (fakt / reja) uchun «Fakt» kiriting; faktsiz prognoz koʻrsatkich (kutil. / reja) koʻrsatiladi. Hajmlar manfiy boʻlmasligi kerak.",
  "Наименование": "Nomi",
  "База (2025 факт)": "Baza (2025 fakt)",
  "натура": "natura",
  "Итог компании": "Kompaniya jami",
  "Продукт": "Mahsulot",
  "ед.": "birlik",
  "Добавить «в т.ч.»": "«shu jumladan» qoʻshish",
  "Вверх": "Yuqoriga",
  "Вниз": "Pastga",
  "Добавить продукт": "Mahsulot qoʻshish",

  // ── BP_FIELDS (строки ОФР из api/bpKpi.ts — отображаются в этих компонентах) ──
  
  "Себестоимость реализованной продукции": "Sotilgan mahsulot tannarxi",
  "— расходы на реализацию": "— sotish xarajatlari",
  "— административные расходы": "— maʼmuriy xarajatlar",
  "— прочие операционные расходы": "— boshqa operatsion xarajatlar",
  "Прочие доходы от основной деятельности": "Asosiy faoliyatdan boshqa daromadlar",
  
  
  
  "— прочие фин. доходы": "— boshqa moliyaviy daromadlar",
  
  
  "— прочие фин. расходы": "— boshqa moliyaviy xarajatlar",
  "Прибыль от общехоз. деятельности": "Umumxoʻjalik faoliyatidan foyda",
  
  

  // ── Зоны исполнения (utils/execBand.ts — показываются здесь) ──
  "в норме": "meʼyorida",
  
  "критично": "kritik",
  "переисполнение — проверить единицы/двойной ввод": "ortiqcha bajarilish — birliklar/ikki marta kiritishni tekshiring",
};

export const en: Record<string, string> = {
  // ── Статус-бар и KPI-карточки компании ──
  "Общий прогресс": "Overall progress",
  "На цели (≥95%)": "On target (≥95%)",
  "Критичных (<70%)": "Critical (<70%)",
  "Год к году": "Year over year",
  "нет данных": "no data",
  "взвешенно · {n} метрик": "weighted · {n} metrics",
  "нет фактов": "no actuals",
  "показателей": "indicators",
  
  "требуют решения": "need action",
  "нет данных за {y}": "no data for {y}",
  "по выручке к {y}": "revenue vs {y}",
  "Расходы периода": "Period expenses",
  "Финансовые расходы": "Finance costs",
  "Налог на прибыль": "Income tax",
  "Финансовые доходы": "Finance income",
  "Прочие опер. доходы": "Other operating income",
  "Прибыль до налогов": "Profit before tax",

  // ── Прогноз кварталов ──
  "план × темп": "plan × pace",
  "сезонность прошлого года": "last-year seasonality",
  "по плану": "per plan",
  "год закрыт": "year closed",
  "смешанный": "mixed",
  "увер.": "confidence",
  "высокая": "high",
  "средняя": "medium",
  "низкая": "low",

  // ── Периоды/подписи ──
  "годовой итог": "annual total",
  "нарастающим итогом за {q}": "year-to-date through {q}",
  "за квартал {q}": "for quarter {q}",
  "нарастающим итогом за {q} (пред. квартал не заполнен)": "year-to-date through {q} (previous quarter not filled)",
  "годовой": "annual",
  "год": "year",

  // ── Комментарий руководителя ──
  "Комментарий сохранён": "Comment saved",
  "Не удалось сохранить": "Failed to save",
  
  "обновлено": "updated",
  
  "Например: Операционный план Q1 выполнен на 104%. Отставание по IPO-процессу из-за задержки аудита — перенос на Q2...":
    "Example: Q1 operating plan delivered at 104%. IPO process delayed by the audit — moved to Q2...",
  
  "Сохранение…": "Saving…",

  // ── YTD-фолбэк ──
  "{q} не заполнен — показатели показаны нарастающим итогом с начала года; разбивка «за квартал» появится после заполнения предыдущего квартала в редакторе.":
    "{q} is not filled in — figures are shown year-to-date; the per-quarter breakdown will appear once the previous quarter is filled in the editor.",
  "Строки с меткой «нараст.» показаны нарастающим итогом: в {q} не заполнен факт — «за квартал» не вычислить. Внесите факт {q} в редакторе, и строки переключатся на «за квартал».":
    "Rows tagged \"YTD\" are shown year-to-date: the {q} actual is missing, so per-quarter values cannot be computed. Enter the {q} actual in the editor and the rows will switch to per-quarter view.",
  
  "Показано нарастающим итогом с начала года: в предыдущем квартале нет факта — «за квартал» не вычислить":
    "Shown year-to-date: the previous quarter has no actual, so the per-quarter value cannot be computed",
  "Показано нарастающим итогом: в предыдущем квартале нет факта — «за квартал» не вычислить":
    "Shown year-to-date: the previous quarter has no actual — per-quarter value cannot be computed",

  // ── KPI-карточки ──
  "авто из НСБУ: {n}": "auto from NAS: {n}",
  "Факт подставлен автоматически из НСБУ": "Actual auto-filled from NAS",
  "Автоматически из НСБУ": "Auto from NAS",
  "млрд сум · факт": "bn UZS · actual",
  "{n}% плана": "{n}% of plan",
  "{n}% г/г": "{n}% YoY",
  "— г/г": "— YoY",
  "Итог года:": "Year total:",
  "План года:": "Annual plan:",
  "план": "plan",
  "факт": "actual",

  // ── Квартальный тренд / графики ──
  "Квартальный тренд": "Quarterly trend",
  "Нет квартальных данных за {y}": "No quarterly data for {y}",
  "показатель разнесён только по году или не заведён": "the indicator is entered only for the year or not at all",
  "За квартал · план": "Quarter · plan",
  "За квартал · факт": "Quarter · actual",
  "за квартал не вычислимо: нет данных предыдущего квартала": "per-quarter value unavailable: no previous-quarter data",
  "Прогноз (за кв.)": "Forecast (qtr)",
  "Коридор": "Range",
  "Нараст. план": "YTD plan",
  "Нараст. факт": "YTD actual",
  "Нараст. итог": "YTD total",
  "Исполнение с начала года": "Year-to-date execution",
  "Исполнение с начала года (нарастающим итогом)": "Year-to-date execution (cumulative)",
  "Открыть разбор →": "Open breakdown →",
  "Ожидание": "Expected",
  "Динамика по кварталам": "Quarterly trend",
  "План (за кв.)": "Plan (qtr)",
  "Факт (за кв.)": "Actual (qtr)",
  "план разнесён лишь частью компаний ({v})": "plan entered for only some companies ({v})",
  "Покрытие": "Coverage",
  "комп.": "cos.",
  "в итог входят компании без данных пред. квартала — поэтому Σ баров ≠ нараст. итогу":
    "the total includes companies without previous-quarter data, so the bar sum ≠ the YTD total",

  // ── Внимание / достижения ──
  
  "Критических отклонений нет": "No critical deviations",
  "Достижения периода": "Period achievements",
  "Нет показателей ≥100% плана": "No indicators at ≥100% of plan",

  // ── Детализация ОФР ──
  "Детализация ОФР": "P&L detail",
  "Структура": "Structure",
  "Раскрыть все": "Expand all",
  "% плана": "% of plan",
  "расчёт": "calc",
  "∑ расчёт": "∑ calc",
  "Структура ОФР": "P&L structure",
  "{a} из {b} строк": "{a} of {b} rows",

  // ── Дрилл-модалка (BpDrillModal) ──
  "KPI · детализация по портфелю": "KPI · portfolio detail",
  "Строка P&L · декомпозиция по компаниям": "P&L line · company breakdown",
  "Бизнес-план компании · полный профиль": "Company business plan · full profile",
  "Сектор · профиль и компании": "Sector · profile & companies",
  "{n} компаний": "{n} companies",
  "{n} компаний сектора": "{n} sector companies",
  "млрд UZS": "bn UZS",
  "{n} прочих": "{n} others",
  "Загрузка данных по компаниям…": "Loading company data…",
  "Сумма факт": "Total actual",
  "Сумма план": "Total plan",
  "к плану": "vs plan",
  "По факту": "By actual",
  "По % плана": "By % of plan",
  "По отклонению": "By variance",
  "Только <90%": "Only <90%",
  "Загрузка декомпозиции по компаниям…": "Loading company breakdown…",
  "Итого факт": "Total actual",
  "Топ-3 доля": "Top-3 share",
  "из плана {v}": "of plan {v}",
  "Декомпозиция по компаниям · клик по столбцу — сортировка": "Company breakdown · click a column to sort",
  "Доля": "Share",
  "ИТОГО · {n} комп.": "TOTAL · {n} cos.",
  "Загрузка профиля компании…": "Loading company profile…",
  "Динамика кварталов · выручка": "Quarterly trend · revenue",
  "Квартальные данные не введены": "No quarterly data entered",
  "В выбранном секторе нет компаний с данными": "No companies with data in this sector",
  "Доля сектора в портфеле": "Sector share of portfolio",
  "от {v}": "of {v}",
  "Компании сектора": "Sector companies",
  "Средн. % плана": "Avg % of plan",
  "Компаний": "Companies",
  "Лидер сектора": "Sector leader",
  "Доля портфеля": "Portfolio share",

  // ── Разбор квартала ──
  "нет факта": "no actual",
  "план перевыполнен": "plan exceeded",
  "план выполнен": "plan met",
  "требует внимания": "needs attention",
  "недобор": "shortfall",
  "Разбор квартала": "Quarter breakdown",
  "План = 100%": "Plan = 100%",
  "исполнение с начала года · план = 100%": "year-to-date execution · plan = 100%",
  "За квартал {q}": "Quarter {q}",
  "Исполнение за квартал": "Quarter execution",
  "С начала года · нарастающим итогом": "Year-to-date · cumulative",
  "Дельта факт−план": "Delta actual−plan",

  // ── Сводка ──
  "— нет данных —": "— no data —",
  "Δ план": "Δ plan",
  "С начала года (нарастающим итогом). Сумма «за квартал» по кварталам может отличаться: в итог входят и компании без данных предыдущего квартала.":
    "Year-to-date (cumulative). The sum of per-quarter values may differ: the total also includes companies without previous-quarter data.",
  "Нараст. итогом": "YTD",
  "Топ-3 лидеры": "Top-3 leaders",
  "Топ-3 отстающие": "Top-3 laggards",
  "Нет данных по {m}": "No data for {m}",
  "расходам периода": "period expenses",
  "выручке": "revenue",
  "По секторам": "By sector",
  "Открыть сектор": "Open sector",
  "{p} портфеля": "{p} of portfolio",
  "Нет данных по секторам": "No sector data",
  "P&L каскад · от выручки до чистой прибыли": "P&L waterfall · revenue to net profit",
  "Открыть строку P&L": "Open P&L line",
  "Валовая": "Gross",
  "Опер. расходы": "Op. expenses",
  "Опер. прибыль": "Op. profit",
  
  "млрд": "bn",
  "Открыть детализацию": "Open details",

  // ── Производственные показатели (дашборд) ──
  "не распознано листов: {n}": "unrecognized sheets: {n}",
  "Загружено: {a} компаний · {b} с данными · {c} строк": "Loaded: {a} companies · {b} with data · {c} rows",
  "Импорт «Свода» из Excel": "Import the consolidated file from Excel",
  "Импорт производственного «Свода» · Excel": "Production consolidated file import · Excel",
  "Файл с листом на компанию (натура + деньги: база → план → ожидаемое). Загрузится в период FY {y} · {p}.":
    "File with one sheet per company (volume + money: base → plan → expected). Will be loaded into FY {y} · {p}.",
  "Нет производственных данных за выбранный период.": "No production data for the selected period.",
  "сбросить": "reset",
  "За {y} заведены только фактические объёмы выпуска — плановый год ещё не открыт. План, ожидаемое и исполнение появятся для планового периода (2026).":
    "Only actual output volumes are entered for {y} — the planning year is not yet open. Plan, expected and execution will appear for the planning period (2026).",
  "Совокупный фактический выпуск": "Total actual output",
  "Фактический выпуск": "Actual output",
  "трлн сум": "tn UZS",
  "Компаний с фактом": "Companies with actuals",
  "заполнено в периметре": "filled in scope",
  "Секторов": "Sectors",
  "в периметре": "in scope",
  "Крупнейший выпуск": "Largest output",
  "{n}% портфеля": "{n}% of portfolio",
  "Сортировать по исполнению": "Sort by execution",
  "Сводное исполнение": "Overall execution",
  "ожид / план": "exp / plan",
  "Сортировать по плану": "Sort by plan",
  "План выпуска": "Output plan",
  "Сортировать по ожидаемому": "Sort by expected",
  "{n}% к 2025": "{n}% vs 2025",
  "Показать переисполнение": "Show overruns",
  "Покрытие данными": "Data coverage",
  "переисполнение: {n}": "overrun: {n}",
  "компаний с данными": "companies with data",
  "Свод по компаниям": "Company summary",
  "Ожид.": "Exp.",
  "Темп": "Growth",
  "Заполнить данные": "Fill in data",
  "по натуральному объёму": "by physical volume",
  "н": "n",
  "факт —": "actual —",
  "Нет компаний по фильтру": "No companies match the filter",
  "Факт выпуска": "Actual output",
  "Структура выпуска": "Output structure",
  "Сравнение": "Comparison",
  "План · Ожид": "Plan · Exp",
  "2025 факт": "2025 actual",
  "2026 ожид.": "2026 exp.",
  "ожид.": "exp.",
  "темп роста": "growth rate",
  "исполнение": "execution",
  "факт 2025 → ожид. 2026": "2025 actual → 2026 exp.",
  "план → ожид., млрд UZS": "plan → exp., bn UZS",
  "Нет числовых данных для графика": "No numeric data for the chart",
  "факт выпуска · доля в портфеле": "actual output · portfolio share",

  // ── Производство: карточка компании / дрилл ──
  "Не удалось загрузить производственные показатели": "Failed to load production indicators",
  "Бизнес-план · натуральные показатели": "Business plan · physical indicators",
  "Редактировать данные": "Edit data",
  "Загрузка производственных показателей…": "Loading production indicators…",
  "Производственные показатели за {y} не заведены": "No production indicators entered for {y}",
  "Данные по выпуску продукции (натура + деньги, план → ожидаемое) для «{name}» пока не заполнены.":
    "Production output data (volume + money, plan → expected) for \"{name}\" is not filled in yet.",
  "Заполнить показатели": "Fill in indicators",
  "не введён": "not entered",
  "Темп роста": "Growth rate",
  "к пред. периоду": "vs prior period",
  "ожид": "exp",
  "нат": "vol",
  "Продукция": "Products",
  "Ед.": "Unit",
  "План (нат.)": "Plan (vol)",
  "Ожид. (нат.)": "Exp. (vol)",
  "Факт (нат.)": "Actual (vol)",
  "План (млрд)": "Plan (bn)",
  "Ожид. (млрд)": "Exp. (bn)",
  "Факт (млрд)": "Actual (bn)",
  "Исп.": "Exec.",
  "Итоговые показатели без детализации по продукции": "Totals only, no product breakdown",
  "Производственный план": "Production plan",
  "Нет детализации по продукции": "No product breakdown",

  // ── Редактор производства ──
  "Строку-итог удалить нельзя": "The total row cannot be deleted",
  
  "Нет строк для сохранения": "No rows to save",
  "Отправлено на модерацию": "Sent for moderation",
  "Производственные данные сохранены": "Production data saved",
  "Не сохранено: {e}": "Not saved: {e}",
  "ошибка": "error",
  "Редактирование производства": "Edit production",
  "не сохранено": "not saved",
  "Темп роста и исполнение считаются автоматически (по деньгам, при отсутствии — по натуре). Введите «Факт» для реального исполнения (факт / план); без факта показывается прогнозное (ожид. / план). Объёмы — неотрицательные.":
    "Growth rate and execution are computed automatically (by money, falling back to volume). Enter \"Actual\" for real execution (actual / plan); without it the projected value (exp. / plan) is shown. Volumes must be non-negative.",
  "Наименование": "Name",
  "База (2025 факт)": "Base (2025 actual)",
  "натура": "qty",
  "Итог компании": "Company total",
  "Продукт": "Product",
  "ед.": "unit",
  "Добавить «в т.ч.»": "Add sub-line",
  "Вверх": "Move up",
  "Вниз": "Move down",
  "Добавить продукт": "Add product",

  // ── BP_FIELDS (строки ОФР из api/bpKpi.ts) ──
  "Чистая выручка от реализации": "Net sales revenue",
  "Себестоимость реализованной продукции": "Cost of goods sold",
  "— расходы на реализацию": "— selling expenses",
  "— административные расходы": "— administrative expenses",
  "— прочие операционные расходы": "— other operating expenses",
  
  "— доходы в виде дивидендов": "— dividend income",
  "— доходы в виде процентов": "— interest income",
  
  "— прочие фин. доходы": "— other finance income",
  "— расходы в виде процентов": "— interest expense",
  
  "— прочие фин. расходы": "— other finance costs",
  "Прибыль от общехоз. деятельности": "Profit from ordinary activities",
  "Прибыль до налогообложения": "Profit before tax",
  "Чистая прибыль (убыток) периода": "Net profit (loss) for the period",

  // ── Зоны исполнения (utils/execBand.ts) ──
  "в норме": "on track",
  
  "критично": "critical",
  "переисполнение — проверить единицы/двойной ввод": "overrun — check units/double entry",
};

/**
 * Исключения кириллицы: слова с «ц» (operatsiya-группа), «ь» (портфель,
 * фильтр) и латинские токены, которые транслит исказил бы (Excel, P&L, y/y).
 */
export const cyr: Record<string, string> = {
  "Например: Операционный план Q1 выполнен на 104%. Отставание по IPO-процессу из-за задержки аудита — перенос на Q2...":
    "Масалан: Q1 операцион режа 104% бажарилди. Аудит кечикиши сабабли IPO жараёнида ортда қолиш — Q2 га кўчирилди...",
  "Отправлено на модерацию": "Модерацияга юборилди",
  "— прочие операционные расходы": "— бошқа операцион харажатлар",
  "Импорт «Свода» из Excel": "«Свод» файлини Excelдан импорт қилиш",
  "Импорт производственного «Свода» · Excel": "Ишлаб чиқариш «Свод»и импорти · Excel",
  "Строка P&L · декомпозиция по компаниям": "P&L қатори · компаниялар кесимида",
  "P&L каскад · от выручки до чистой прибыли": "P&L каскади · тушумдан соф фойдагача",
  "Открыть строку P&L": "P&L қаторини очиш",
  "KPI · детализация по портфелю": "KPI · портфель бўйича тафсилот",
  "Доля сектора в портфеле": "Тармоқнинг портфельдаги улуши",
  "Доля портфеля": "Портфель улуши",
  "{n}% портфеля": "портфельнинг {n}%",
  "{p} портфеля": "портфельнинг {p}",
  "факт выпуска · доля в портфеле": "ҳақиқий ишлаб чиқариш · портфельдаги улуш",
  "Нет компаний по фильтру": "Фильтр бўйича компаниялар йўқ",
};
