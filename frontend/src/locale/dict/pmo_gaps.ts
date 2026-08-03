/**
 * Догрузка словаря PMO (ru → uz-latn / en).
 *
 * Сюда попадают строки PMO, добавленные ПОСЛЕ основного прохода локализации
 * (`audit_remaining.ts`): честные баннеры покрытия (критический путь, EVM,
 * загрузка команды), dirty-guard'ы и подтверждения удаления. Отдельный файл,
 * а не правка `audit_remaining.ts`, — чтобы не конфликтовать с идущим
 * параллельно проходом по остальным модулям; словари склеиваются автоматически
 * (`import.meta.glob` в `i18n.ts`).
 *
 * uz-cyr не дублируем — он выводится транслитерацией из uz-latn.
 */

export const uz: Record<string, string> = {
  // ── Честные баннеры покрытия (Гантт / EVM / загрузка) ──
  "Данных недостаточно": "Maʼlumot yetarli emas",
  "Связи между задачами не заданы — критический путь не рассчитывается.":
    "Vazifalar orasida bogʻlanishlar kiritilmagan — kritik yoʻl hisoblanmaydi.",
  "У {value0} полос нет даты начала: длительность условная, полоса строится по одному дедлайну.":
    "{value0} ta chiziqda boshlanish sanasi yoʻq: davomiylik shartli, chiziq faqat muddat boʻyicha quriladi.",
  "Критический путь строится по связям между задачами. Связей не задано, поэтому рассчитать его невозможно.":
    "Kritik yoʻl vazifalar orasidagi bogʻlanishlar asosida quriladi. Bogʻlanishlar kiritilmagani uchun uni hisoblab boʻlmaydi.",
  "Самая длинная цепочка связанных задач — задержка любой из них сдвигает финиш.":
    "Bogʻlangan vazifalarning eng uzun zanjiri — ulardan birortasining kechikishi yakunni suradi.",
  "нет связей": "bogʻlanishlar yoʻq",
  "Стоимостные метрики — по {value0} из {value1} проектов ({value2}%), индекс срока — по {value3} ({value4}%).":
    "Qiymat koʻrsatkichlari — {value1} ta loyihadan {value0} tasi boʻyicha ({value2}%), muddat indeksi — {value3} tasi boʻyicha ({value4}%).",
  "Цифры ниже описывают только эту часть портфеля — заполните бюджет, факт затрат и плановые даты в карточках проектов.":
    "Quyidagi raqamlar portfelning faqat shu qismini tavsiflaydi — loyiha kartochkalarida byudjet, xarajat fakti va reja sanalarini toʻldiring.",
  "Исполнитель проставлен у {value0} из {value1} открытых задач ({value2}%).":
    "Ijrochi {value1} ta ochiq vazifadan {value0} tasida koʻrsatilgan ({value2}%).",
  "Загрузка ниже посчитана только по ним — остальная работа в расчёт не входит.":
    "Quyidagi yuklama faqat shular boʻyicha hisoblangan — qolgan ishlar hisobga kirmaydi.",

  // ── Устав: автозаполнение и dirty-guard ──
  "Подставляю данные проекта…": "Loyiha maʼlumotlari qoʻyilmoqda…",
  "Заполнено из проекта — проверьте и поправьте:": "Loyihadan toʻldirildi — tekshiring va toʻgʻrilang:",
  "Закрыть без сохранения?": "Saqlamasdan yopilsinmi?",
  "В уставе есть несохранённые изменения — они будут потеряны.":
    "Ustavda saqlanmagan oʻzgarishlar bor — ular yoʻqoladi.",

  // ── Подтверждения удаления ──
  "Удалить устав?": "Ustav oʻchirilsinmi?",
  "Удалить запись RAID?": "RAID yozuvi oʻchirilsinmi?",
  "Удалить стейкхолдера?": "Manfaatdor tomon oʻchirilsinmi?",
  "«{name}» будет удалён безвозвратно.": "«{name}» butunlay oʻchiriladi.",
  "«{title}» будет удалён безвозвратно.": "«{title}» butunlay oʻchiriladi.",
  "«{title}» будет удалена безвозвратно.": "«{title}» butunlay oʻchiriladi.",
};

export const en: Record<string, string> = {
  "Данных недостаточно": "Not enough data",
  "Связи между задачами не заданы — критический путь не рассчитывается.":
    "No dependencies between tasks — the critical path is not computed.",
  "У {value0} полос нет даты начала: длительность условная, полоса строится по одному дедлайну.":
    "{value0} bars have no start date: duration is nominal, the bar is drawn from the due date alone.",
  "Критический путь строится по связям между задачами. Связей не задано, поэтому рассчитать его невозможно.":
    "The critical path is derived from task dependencies. None are defined, so it cannot be computed.",
  "Самая длинная цепочка связанных задач — задержка любой из них сдвигает финиш.":
    "The longest chain of linked tasks — a delay in any of them moves the finish date.",
  "нет связей": "no dependencies",
  "Стоимостные метрики — по {value0} из {value1} проектов ({value2}%), индекс срока — по {value3} ({value4}%).":
    "Cost metrics cover {value0} of {value1} projects ({value2}%), the schedule index covers {value3} ({value4}%).",
  "Цифры ниже описывают только эту часть портфеля — заполните бюджет, факт затрат и плановые даты в карточках проектов.":
    "The figures below describe only that part of the portfolio — fill in budget, actual cost and planned dates in the project cards.",
  "Исполнитель проставлен у {value0} из {value1} открытых задач ({value2}%).":
    "An assignee is set on {value0} of {value1} open tasks ({value2}%).",
  "Загрузка ниже посчитана только по ним — остальная работа в расчёт не входит.":
    "The workload below is computed from those only — the remaining work is not counted.",

  "Подставляю данные проекта…": "Filling in project data…",
  "Заполнено из проекта — проверьте и поправьте:": "Filled in from the project — review and adjust:",
  "Закрыть без сохранения?": "Close without saving?",
  "В уставе есть несохранённые изменения — они будут потеряны.":
    "The charter has unsaved changes — they will be lost.",

  "Удалить устав?": "Delete the charter?",
  "Удалить запись RAID?": "Delete the RAID entry?",
  "Удалить стейкхолдера?": "Delete the stakeholder?",
  "«{name}» будет удалён безвозвратно.": "“{name}” will be deleted permanently.",
  "«{title}» будет удалён безвозвратно.": "“{title}” will be deleted permanently.",
  "«{title}» будет удалена безвозвратно.": "“{title}” will be deleted permanently.",
};
