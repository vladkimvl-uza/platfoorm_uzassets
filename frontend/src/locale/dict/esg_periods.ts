/** ESG «Документы по этапам» — организация по периодам (годы / кварталы / ISO-
 *  таймлайн). Ключ = русский исходник; uz = латиница (uz-кириллица —
 *  транслитерацией), en = английский. «Q1..Q4» — универсальные, не переводятся. */
export const uz: Record<string, string> = {
  "по годам": "yillar bo'yicha",
  "годы · кварталы": "yillar · choraklar",
  "таймлайн": "vaqt chizig'i",
  "текущий": "joriy",
  "Ранее": "Ilgari",
  "Ранее (без года)": "Ilgari (yilsiz)",
  "За этот период документов нет": "Bu davr uchun hujjatlar yo'q",
  "{y} · {n} документов": "{y} · {n} ta hujjat",
  "год": "yil",
  "Добавить год": "Yil qo'shish",
};

export const en: Record<string, string> = {
  "по годам": "by year",
  "годы · кварталы": "years · quarters",
  "таймлайн": "timeline",
  "текущий": "current",
  "Ранее": "Earlier",
  "Ранее (без года)": "Earlier (no year)",
  "За этот период документов нет": "No documents for this period",
  "{y} · {n} документов": "{y} · {n} documents",
  "год": "year",
  "Добавить год": "Add year",
};
