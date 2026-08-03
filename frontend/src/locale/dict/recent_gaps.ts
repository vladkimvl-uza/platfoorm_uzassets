/**
 * Догрузка словаря (ru → uz-latn / en) для экранов, добавленных после
 * основного прохода локализации: балл корпоративного управления в /governance,
 * «Мои заявки» (модерируемый пользователь) и действия модерации в колокольчике.
 *
 * Отдельный файл — чтобы не конфликтовать с идущим параллельно проходом по
 * остальным модулям; словари склеиваются автоматически (`import.meta.glob`).
 * uz-cyr выводится транслитерацией из uz-latn.
 */

export const uz: Record<string, string> = {
  // ── Балл корпоративного управления (карточка компании + редактор) ──
  "Балл корпоративного управления": "Korporativ boshqaruv bali",
  "Балл КУ (предпросчёт)": "Korporativ boshqaruv bali (dastlabki hisob)",
  "Балл посчитан по {value0} факторам из {value1}: веса недостающих перераспределены. Заполните их — оценка станет полной.":
    "Ball {value1} omildan {value0} tasi boʻyicha hisoblandi: yetishmayotganlarining vaznlari qayta taqsimlandi. Ularni toʻldiring — baho toʻliq boʻladi.",
  "Утверждённый размер совета": "Tasdiqlangan kengash tarkibi",
  "Заведено людей": "Kiritilgan odamlar",
  "Утверждено": "Tasdiqlangan",
  "Вакансий": "Boʻsh oʻrinlar",
  "{value0} вакансий": "{value0} ta boʻsh oʻrin",
  "Заведено больше людей, чем утверждено ({value0} > {value1}) — проверьте утверждённый размер или список членов.":
    "Kiritilgan odamlar soni tasdiqlangandan koʻp ({value0} > {value1}) — tasdiqlangan tarkibni yoki aʼzolar roʻyxatini tekshiring.",

  // ── «Мои заявки» (модерируемый пользователь) ──
  "Мои заявки": "Mening arizalarim",
  "Изменения, которые вы отправили на согласование. Здесь видно, на какой они стадии и что ответил модератор.":
    "Siz kelishuvga yuborgan oʻzgarishlar. Bu yerda ularning bosqichi va moderator javobi koʻrinadi.",
  "Когда ваше изменение попадёт на согласование, оно появится здесь — со статусом и ответом модератора.":
    "Oʻzgarishingiz kelishuvga tushganda, u shu yerda — holati va moderator javobi bilan paydo boʻladi.",
  "Загрузка заявок…": "Arizalar yuklanmoqda…",
  "Заявок нет": "Arizalar yoʻq",
  "Заявка на согласование": "Kelishuvga ariza",
  "Предложенные значения": "Taklif qilingan qiymatlar",
  "Комментарий модератора": "Moderator izohi",
  "Модератор отклонил заявку без пояснения — можно уточнить причину в комментарии ниже.":
    "Moderator arizani izohsiz rad etdi — sababni quyidagi izohda aniqlashtirish mumkin.",
  "Обсуждение": "Muhokama",
  "Сообщений пока нет": "Hozircha xabarlar yoʻq",
  "Написать модератору…": "Moderatorga yozish…",
  "Открыть запись": "Yozuvni ochish",
  "на рассмотрении": "koʻrib chiqilmoqda",
  "Отозвать заявку?": "Ariza qaytarib olinsinmi?",
  "Предложенное изменение не будет применено. Отправить заново можно в любой момент.":
    "Taklif qilingan oʻzgarish qoʻllanilmaydi. Qayta yuborish istalgan vaqtda mumkin.",
  "Заявка отозвана": "Ariza qaytarib olindi",
  "Заявка принята": "Ariza qabul qilindi",
  "Комментарий отправлен модератору": "Izoh moderatorga yuborildi",
  "Не удалось загрузить заявки": "Arizalarni yuklab boʻlmadi",
  "Не удалось открыть заявку": "Arizani ochib boʻlmadi",
  "Не удалось отозвать заявку": "Arizani qaytarib olib boʻlmadi",
  "Не удалось отправить комментарий": "Izohni yuborib boʻlmadi",
  "Не удалось принять заявку": "Arizani qabul qilib boʻlmadi",
  "Не удалось определить заявку — откройте её в очереди":
    "Arizani aniqlab boʻlmadi — uni navbatda oching",

  // ── Сайт компании + маршрутизация модерации ──
  "Сайт": "Sayt",
  "Показывается ссылкой в шапке рабочего пространства компании. Можно без https://":
    "Kompaniya ish maydoni sarlavhasida havola sifatida koʻrsatiladi. https:// siz ham boʻladi.",
  "Модерация": "Moderatsiya",
  "Необязательно": "Majburiy emas",
  "Согласующие для этого пользователя": "Ushbu foydalanuvchi uchun kelishuvchilar",
  "Согласующие для этого пользователя — правки уйдут именно им.":
    "Ushbu foydalanuvchi uchun kelishuvchilar — oʻzgarishlar aynan ularga boradi.",
  "Правки уйдут именно им. Если никого не выбрать — заявку увидят все, кто ведёт модерацию.":
    "Oʻzgarishlar aynan ularga boradi. Hech kim tanlanmasa — arizani moderatsiya yurituvchilarning barchasi koʻradi.",
  "Ведёт модерацию по секторам": "Sektorlar boʻyicha moderatsiya yuritadi",
  "Ведёт модерацию по секторам: заявки авторов из компаний этих секторов придут этому пользователю.":
    "Sektorlar boʻyicha moderatsiya yuritadi: shu sektorlardagi kompaniyalar mualliflarining arizalari shu foydalanuvchiga keladi.",
  "Заявки авторов из компаний этих секторов будут приходить этому пользователю. Право «Модерация: рассмотрение» выдастся автоматически.":
    "Shu sektorlardagi kompaniyalar mualliflarining arizalari shu foydalanuvchiga keladi. «Moderatsiya: koʻrib chiqish» huquqi avtomatik beriladi.",
  "Назначенным согласующим автоматически выдаётся право «Модерация: рассмотрение».":
    "Tayinlangan kelishuvchilarga «Moderatsiya: koʻrib chiqish» huquqi avtomatik beriladi.",
  "Персональный согласующий не назначен: правки уходят всем, кто ведёт модерацию.":
    "Shaxsiy kelishuvchi tayinlanmagan: oʻzgarishlar moderatsiya yurituvchilarning barchasiga boradi.",
  "Согласует: {name}": "Kelishadi: {name}",
  "Ведёт сектор: {sector}": "Sektorni yuritadi: {sector}",
  "Поиск сотрудника по имени или почте": "Xodimni ism yoki pochta boʻyicha qidirish",
  "Никого не нашлось": "Hech kim topilmadi",
  "Не удалось загрузить список сотрудников": "Xodimlar roʻyxatini yuklab boʻlmadi",
  "Не удалось сохранить маршрут модерации": "Moderatsiya marshrutini saqlab boʻlmadi",
};

export const en: Record<string, string> = {
  "Балл корпоративного управления": "Corporate governance score",
  "Балл КУ (предпросчёт)": "Governance score (preview)",
  "Балл посчитан по {value0} факторам из {value1}: веса недостающих перераспределены. Заполните их — оценка станет полной.":
    "The score covers {value0} of {value1} factors: the weights of the missing ones were redistributed. Fill them in for a complete assessment.",
  "Утверждённый размер совета": "Approved board size",
  "Заведено людей": "People on record",
  "Утверждено": "Approved",
  "Вакансий": "Vacancies",
  "{value0} вакансий": "{value0} vacancies",
  "Заведено больше людей, чем утверждено ({value0} > {value1}) — проверьте утверждённый размер или список членов.":
    "More people on record than approved ({value0} > {value1}) — check the approved size or the member list.",

  "Мои заявки": "My submissions",
  "Изменения, которые вы отправили на согласование. Здесь видно, на какой они стадии и что ответил модератор.":
    "Changes you sent for approval. You can see their stage and the moderator's reply here.",
  "Когда ваше изменение попадёт на согласование, оно появится здесь — со статусом и ответом модератора.":
    "When your change goes for approval it will show up here — with its status and the moderator's reply.",
  "Загрузка заявок…": "Loading submissions…",
  "Заявок нет": "No submissions",
  "Заявка на согласование": "Submission for approval",
  "Предложенные значения": "Proposed values",
  "Комментарий модератора": "Moderator's comment",
  "Модератор отклонил заявку без пояснения — можно уточнить причину в комментарии ниже.":
    "The moderator rejected the submission without an explanation — you can ask for the reason in the comments below.",
  "Обсуждение": "Discussion",
  "Сообщений пока нет": "No messages yet",
  "Написать модератору…": "Message the moderator…",
  "Открыть запись": "Open the record",
  "на рассмотрении": "under review",
  "Отозвать заявку?": "Withdraw the submission?",
  "Предложенное изменение не будет применено. Отправить заново можно в любой момент.":
    "The proposed change will not be applied. You can resubmit at any time.",
  "Заявка отозвана": "Submission withdrawn",
  "Заявка принята": "Submission approved",
  "Комментарий отправлен модератору": "Comment sent to the moderator",
  "Не удалось загрузить заявки": "Could not load submissions",
  "Не удалось открыть заявку": "Could not open the submission",
  "Не удалось отозвать заявку": "Could not withdraw the submission",
  "Не удалось отправить комментарий": "Could not send the comment",
  "Не удалось принять заявку": "Could not approve the submission",
  "Не удалось определить заявку — откройте её в очереди":
    "Could not identify the submission — open it in the queue",

  // ── Сайт компании + маршрутизация модерации ──
  "Сайт": "Website",
  "Показывается ссылкой в шапке рабочего пространства компании. Можно без https://":
    "Shown as a link in the company workspace header. https:// is optional.",
  "Модерация": "Moderation",
  "Необязательно": "Optional",
  "Согласующие для этого пользователя": "Approvers for this user",
  "Согласующие для этого пользователя — правки уйдут именно им.":
    "Approvers for this user — their changes go to exactly these people.",
  "Правки уйдут именно им. Если никого не выбрать — заявку увидят все, кто ведёт модерацию.":
    "Changes go to exactly these people. If you pick nobody, every moderator sees the submission.",
  "Ведёт модерацию по секторам": "Moderates these sectors",
  "Ведёт модерацию по секторам: заявки авторов из компаний этих секторов придут этому пользователю.":
    "Moderates these sectors: submissions from authors in companies of these sectors go to this user.",
  "Заявки авторов из компаний этих секторов будут приходить этому пользователю. Право «Модерация: рассмотрение» выдастся автоматически.":
    "Submissions from authors in companies of these sectors will go to this user. The “Moderation: review” permission is granted automatically.",
  "Назначенным согласующим автоматически выдаётся право «Модерация: рассмотрение».":
    "Assigned approvers automatically receive the “Moderation: review” permission.",
  "Персональный согласующий не назначен: правки уходят всем, кто ведёт модерацию.":
    "No personal approver assigned: changes go to every moderator.",
  "Согласует: {name}": "Approver: {name}",
  "Ведёт сектор: {sector}": "Moderates sector: {sector}",
  "Поиск сотрудника по имени или почте": "Search staff by name or email",
  "Никого не нашлось": "Nobody found",
  "Не удалось загрузить список сотрудников": "Could not load the staff list",
  "Не удалось сохранить маршрут модерации": "Could not save the moderation route",
};
