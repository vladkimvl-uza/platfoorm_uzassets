/** ESG Maturity-матрица — новые метки стадий и тултипы выпадающего выбора
 *  (ISO / заверение / климат / риски). Ключ = русский исходник; uz = латиница,
 *  uz-кириллица — транслитерацией; en = английский. Заголовки колонок и статусы
 *  «запланировано/в процессе/пройдено», «Вернуть ISO в статистику» уже
 *  локализованы в audit_remaining.ts — здесь НЕ дублируются, чтобы не переопределять. */
export const uz: Record<string, string> = {
  // Стадии ISO (D1)
  "сертифицирован": "sertifikatlangan",
  // Стадии климата (D4) — компактные метки пилюли
  "Scope 1–2": "Scope 1–2",
  "Клим. риски": "Iqlim risklari",
  "План декарб.": "Dekarb. rejasi",
  "Реализация": "Amalga oshirish",
  // Стадии рисков (D5)
  "Двойная сущ.": "Ikki tom. muhimlik",
  "Кол. оценка": "Miqdoriy baho",
  "Интеграция ERM": "ERM integ.",
  // «не требуется» для группы ISO — явно про всю группу (см. пункт меню D1)
  "Вся ISO: не требуется": "Butun ISO: talab qilinmaydi",
  // Тултипы пилюль (клик — выбрать)
  "Прохождение независимого заверения: {value0} · клик — выбрать статус": "Mustaqil tasdiqlashdan oʻtish: {value0} · bosing — statusni tanlang",
  "Независимое заверение: не требуется · клик — выбрать статус": "Mustaqil tasdiqlash: talab qilinmaydi · bosing — statusni tanlang",
  "Разработка климатической стратегии: {value0} · клик — выбрать этап": "Iqlim strategiyasini ishlab chiqish: {value0} · bosing — bosqichni tanlang",
  "Климатическая стратегия: не требуется · клик — выбрать этап": "Iqlim strategiyasi: talab qilinmaydi · bosing — bosqichni tanlang",
  "Внедрение ESG-рисков: {value0} · клик — выбрать этап": "ESG xavflarini joriy etish: {value0} · bosing — bosqichni tanlang",
  "ESG-риски: не требуется · клик — выбрать этап": "ESG xavflar: talab qilinmaydi · bosing — bosqichni tanlang",
};

export const en: Record<string, string> = {
  "сертифицирован": "certified",
  "Scope 1–2": "Scope 1–2",
  "Клим. риски": "Climate risks",
  "План декарб.": "Decarb. plan",
  "Реализация": "Implementation",
  "Двойная сущ.": "Double mat.",
  "Кол. оценка": "Quant. assess.",
  "Интеграция ERM": "ERM integ.",
  "Вся ISO: не требуется": "All ISO: not required",
  "Прохождение независимого заверения: {value0} · клик — выбрать статус": "Independent assurance: {value0} · click to choose status",
  "Независимое заверение: не требуется · клик — выбрать статус": "Independent assurance: not required · click to choose status",
  "Разработка климатической стратегии: {value0} · клик — выбрать этап": "Climate strategy development: {value0} · click to choose stage",
  "Климатическая стратегия: не требуется · клик — выбрать этап": "Climate strategy: not required · click to choose stage",
  "Внедрение ESG-рисков: {value0} · клик — выбрать этап": "ESG risk implementation: {value0} · click to choose stage",
  "ESG-риски: не требуется · клик — выбрать этап": "ESG risks: not required · click to choose stage",
};
