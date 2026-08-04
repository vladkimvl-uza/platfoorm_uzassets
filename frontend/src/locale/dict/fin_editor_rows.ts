/**
 * Догрузка словаря (ru → uz-latn / en) для правок августа 2026:
 * вставка строк в редакторах МСФО/НСБУ, пометка «идёт в налоги», плитка
 * «Налоги» с фолбэком на отчётность и подписи анализа закупок.
 *
 * Отдельный файл — чтобы не конфликтовать с параллельным проходом по
 * производственному модулю; словари склеиваются автоматически
 * (`import.meta.glob`). uz-cyr выводится транслитерацией из uz-latn.
 */

export const uz: Record<string, string> = {
  // ── Вставка строки в редакторах МСФО/НСБУ ──
  "Вставить новую строку сразу после «{label}»": "Yangi qatorni «{label}» dan keyin qoʻshish",
  "строка": "qator",
  "Новая строка после «{label}»": "«{label}» dan keyingi yangi qator",
  "Включить в итог (опционально)": "Yakuniy koʻrsatkichga qoʻshish (ixtiyoriy)",
  "— не включать никуда —": "— hech qayerga qoʻshilmasin —",
  "Прибавлять к итогу": "Yakunga qoʻshish",
  "Вычитать из итога": "Yakundan ayirish",
  "Формула выбранного итога получит слагаемое, и он начнёт пересчитываться с учётом новой строки.":
    "Tanlangan yakun formulasiga qoʻshiluvchi qoʻshiladi va u yangi qatorni hisobga olib qayta hisoblanadi.",
  "По умолчанию строка ни на что не влияет — просто хранится. Включить в итог можно и потом, кликом по формуле итога.":
    "Sukut boʻyicha qator hech nimaga taʼsir qilmaydi — shunchaki saqlanadi. Uni keyinroq ham, yakun formulasini bosib, qoʻshish mumkin.",
  "Строка «{label}» добавлена и включена в «{target}»":
    "«{label}» qatori qoʻshildi va «{target}» tarkibiga kiritildi",

  // ── Пометка «идёт в налоговый вклад» ──
  "налоги": "soliqlar",
  "Идёт в налоговый вклад: НДС оценивается как выручка × ставка года (12%, до 2023 — 15%)":
    "Soliq hissasiga kiradi: QQS tushum × yil stavkasi sifatida baholanadi (12%, 2023 gacha — 15%)",
  "Идёт в налоговый вклад: суммируется по портфелю как налог на прибыль":
    "Soliq hissasiga kiradi: portfel boʻyicha foyda soligʻi sifatida jamlanadi",
  "Идёт в налоговый вклад: суммируется по портфелю как налог на прибыль. Налоговый блок берёт НСБУ, МСФО — только если НСБУ за год нет":
    "Soliq hissasiga kiradi: portfel boʻyicha foyda soligʻi sifatida jamlanadi. Soliq bloki BHMS dan oladi, MHXS — faqat oʻsha yil uchun BHMS boʻlmasa",
  "налог на прибыль из отчётности": "hisobotdagi foyda soligʻi",

  // ── Анализ закупок ──
  "Доля спенда через НЕКОНКУРЕНТНЫЕ методы (электронный магазин/каталог), где торга нет по определению.":
    "RAQOBATSIZ usullar (elektron doʻkon/katalog) orqali xarajat ulushi — u yerda savdolashuv taʼrifan yoʻq.",
  "Доля спенда через НЕКОНКУРЕНТНЫЕ методы (электронный магазин/каталог), где торга нет по определению. Отдельно: {percent}% ({amount}) — конкурентные процедуры, закрывшиеся с НУЛЕВОЙ экономией при ИЗВЕСТНОЙ экономии (возможная имитация торга).":
    "RAQOBATSIZ usullar (elektron doʻkon/katalog) orqali xarajat ulushi — u yerda savdolashuv taʼrifan yoʻq. Alohida: {percent}% ({amount}) — maʼlum tejamkorlik koʻrsatkichi boʻlgani holda NOL tejam bilan yakunlangan raqobatli protseduralar (savdolashuv taqlidi boʻlishi mumkin).",
  "поставщик не раскрыт ни в одной строке": "yetkazib beruvchi birorta qatorda oshkor etilmagan",
  "Нет сопоставимых позиций — отклонение не рассчитывается":
    "Taqqoslanadigan pozitsiyalar yoʻq — ogʻish hisoblanmaydi",
  "Сопоставимых позиций нет — сравнить цены компании не с чем. Вывод по закупкам сделать нельзя.":
    "Taqqoslanadigan pozitsiyalar yoʻq — kompaniya narxlarini solishtirish uchun asos yoʻq. Xaridlar boʻyicha xulosa chiqarib boʻlmaydi.",

  // ── Дашборд: подсказки к кликабельным плиткам ──
  "клик — разбор по компаниям": "bosing — kompaniyalar kesimi",
  "Показать {label}: список по компаниям": "{label}: kompaniyalar boʻyicha roʻyxatni koʻrsatish",
};

export const en: Record<string, string> = {
  // ── Row insertion in the IFRS/NSBU editors ──
  "Вставить новую строку сразу после «{label}»": "Insert a new row right after “{label}”",
  "строка": "row",
  "Новая строка после «{label}»": "New row after “{label}”",
  "Включить в итог (опционально)": "Add to a total (optional)",
  "— не включать никуда —": "— don't add anywhere —",
  "Прибавлять к итогу": "Add to the total",
  "Вычитать из итога": "Subtract from the total",
  "Формула выбранного итога получит слагаемое, и он начнёт пересчитываться с учётом новой строки.":
    "The selected total's formula gains a term, so it will recalculate with the new row included.",
  "По умолчанию строка ни на что не влияет — просто хранится. Включить в итог можно и потом, кликом по формуле итога.":
    "By default the row affects nothing — it is simply stored. You can add it to a total later by clicking that total's formula.",
  "Строка «{label}» добавлена и включена в «{target}»":
    "Row “{label}” added and included in “{target}”",

  // ── “Feeds into taxes” annotation ──
  "налоги": "taxes",
  "Идёт в налоговый вклад: НДС оценивается как выручка × ставка года (12%, до 2023 — 15%)":
    "Feeds the tax contribution: VAT is estimated as revenue × the year's rate (12%, 15% before 2023)",
  "Идёт в налоговый вклад: суммируется по портфелю как налог на прибыль":
    "Feeds the tax contribution: summed across the portfolio as corporate income tax",
  "Идёт в налоговый вклад: суммируется по портфелю как налог на прибыль. Налоговый блок берёт НСБУ, МСФО — только если НСБУ за год нет":
    "Feeds the tax contribution: summed across the portfolio as corporate income tax. The tax block reads NSBU and falls back to IFRS only when NSBU for that year is missing",
  "налог на прибыль из отчётности": "income tax from the statements",

  // ── Procurement analysis ──
  "Доля спенда через НЕКОНКУРЕНТНЫЕ методы (электронный магазин/каталог), где торга нет по определению.":
    "Share of spend through NON-COMPETITIVE methods (e-shop/catalogue), where by definition no bidding takes place.",
  "Доля спенда через НЕКОНКУРЕНТНЫЕ методы (электронный магазин/каталог), где торга нет по определению. Отдельно: {percent}% ({amount}) — конкурентные процедуры, закрывшиеся с НУЛЕВОЙ экономией при ИЗВЕСТНОЙ экономии (возможная имитация торга).":
    "Share of spend through NON-COMPETITIVE methods (e-shop/catalogue), where by definition no bidding takes place. Separately: {percent}% ({amount}) — competitive procedures that closed with ZERO savings while savings data was KNOWN (possible sham bidding).",
  "поставщик не раскрыт ни в одной строке": "supplier is not disclosed in any line",
  "Нет сопоставимых позиций — отклонение не рассчитывается":
    "No comparable items — the deviation is not calculated",
  "Сопоставимых позиций нет — сравнить цены компании не с чем. Вывод по закупкам сделать нельзя.":
    "There are no comparable items, so the company's prices cannot be benchmarked. No procurement conclusion can be drawn.",

  // ── Dashboard: hints on clickable tiles ──
  "клик — разбор по компаниям": "click for the company breakdown",
  "Показать {label}: список по компаниям": "Show {label}: breakdown by company",
};
