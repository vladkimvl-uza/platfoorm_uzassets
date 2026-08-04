/**
 * Догрузка словаря (ru → uz-latn / en), август 2026:
 * состав модераторов (снятие/возврат) и уточнения к KPI-плиткам,
 * где итог и процент считаются по разным наборам компаний.
 *
 * uz-cyr выводится транслитерацией из uz-latn.
 */

export const uz: Record<string, string> = {
  // ── Состав модераторов ──
  "Модератор — тот, у кого есть право «Модерация: проверка»: оно приходит из роли, из личной выдачи в разделе «Доступ» или при назначении согласующим в карточке пользователя. Кнопка «убрать» отзывает право персонально, роли не трогает.":
    "Moderator — bu «Moderatsiya: tekshirish» huquqiga ega shaxs: bu huquq roldan, «Ruxsat» boʻlimidagi shaxsiy berilishdan yoki foydalanuvchi kartochkasida kelishuvchi etib tayinlashdan keladi. «Olib tashlash» tugmasi huquqni shaxsan qaytarib oladi, rollarga tegmaydi.",
  "Выдайте право «Модерация: проверка» в разделе «Доступ» или назначьте согласующего в карточке пользователя":
    "«Ruxsat» boʻlimida «Moderatsiya: tekshirish» huquqini bering yoki foydalanuvchi kartochkasida kelishuvchini tayinlang",
  "Убрать из модераторов": "Moderatorlar roʻyxatidan olib tashlash",
  "Вернуть в модераторы": "Moderatorlarga qaytarish",
  "Сняты с модерации": "Moderatsiyadan olib tashlanganlar",
  "вернуть": "qaytarish",
  "только владелец": "faqat egasi",
  "Снять согласование с владельца платформы может только владелец":
    "Platforma egasidan kelishuv huquqini faqat egasi olib tashlay oladi",
  "«{name}» перестанет получать заявки и не сможет их согласовывать — ни в платформе, ни из Telegram. Роли и остальные права не меняются, вернуть в модераторы можно в любой момент.":
    "«{name}» endi arizalarni olmaydi va ularni kelisha olmaydi — na platformada, na Telegramda. Rollar va boshqa huquqlar oʻzgarmaydi, istalgan vaqtda moderatorlarga qaytarish mumkin.",
  "Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться. Вернуть себя сможете здесь же, в блоке «Сняты с модерации». Продолжить?":
    "Siz kelishuv huquqini OʻZINGIZDAN olib tashlayapsiz: arizalar ochilmay qoladi. Oʻzingizni shu yerda, «Moderatsiyadan olib tashlanganlar» blokida qaytara olasiz. Davom etilsinmi?",
  "Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться, и вернуть себя обратно вы уже не сможете — это сделает другой администратор. Продолжить?":
    "Siz kelishuv huquqini OʻZINGIZDAN olib tashlayapsiz: arizalar ochilmay qoladi va oʻzingizni qaytara olmaysiz — buni boshqa administrator qiladi. Davom etilsinmi?",
  "«{name}» убран из модераторов": "«{name}» moderatorlar roʻyxatidan olib tashlandi",
  "«{name}» снова модератор": "«{name}» yana moderator",
  "Не удалось убрать из модераторов": "Moderatorlar roʻyxatidan olib tashlab boʻlmadi",
  "Не удалось вернуть в модераторы": "Moderatorlarga qaytarib boʻlmadi",

  // ── Уточнения к KPI-плиткам ──
  "сравнение по {n} сопоставимым": "{n} ta taqqoslanadigan kompaniya boʻyicha",
  "{n} ещё не сдали отчётность": "{n} tasi hisobotni hali topshirmagan",
  "нет сопоставимого прошлого года": "taqqoslanadigan oʻtgan yil yoʻq",
  "Итог — сумма по {inYear} компаниям, сдавшим отчётность за год. Процент — рост по {pair} компаниям, у которых есть данные и за прошлый год. Ещё {gone} компаний отчитались за прошлый год, но не за текущий, поэтому итог меньше прошлогоднего.":
    "Yakun — yil uchun hisobot topshirgan {inYear} ta kompaniya boʻyicha yigʻindi. Foiz — oʻtgan yil maʼlumotlari ham bor {pair} ta kompaniya boʻyicha oʻsish. Yana {gone} ta kompaniya oʻtgan yil uchun hisobot bergan, joriy yil uchun esa yoʻq, shuning uchun yakun oʻtgan yildagidan kam.",
  "Итог — сумма по {inYear} компаниям; процент — рост по {pair} сопоставимым.":
    "Yakun — {inYear} ta kompaniya boʻyicha yigʻindi; foiz — {pair} ta taqqoslanadigan kompaniya boʻyicha oʻsish.",
};

export const en: Record<string, string> = {
  // ── Moderator roster ──
  "Модератор — тот, у кого есть право «Модерация: проверка»: оно приходит из роли, из личной выдачи в разделе «Доступ» или при назначении согласующим в карточке пользователя. Кнопка «убрать» отзывает право персонально, роли не трогает.":
    "A moderator is anyone holding the “Moderation: review” permission — granted by a role, directly in Access, or by being named an approver on a user's card. “Remove” revokes that permission for this person only and leaves their roles untouched.",
  "Выдайте право «Модерация: проверка» в разделе «Доступ» или назначьте согласующего в карточке пользователя":
    "Grant “Moderation: review” in the Access section, or name an approver on a user's card",
  "Убрать из модераторов": "Remove from moderators",
  "Вернуть в модераторы": "Restore as moderator",
  "Сняты с модерации": "Removed from moderation",
  "вернуть": "restore",
  "только владелец": "owner only",
  "Снять согласование с владельца платформы может только владелец":
    "Only the platform owner can revoke review rights from an owner",
  "«{name}» перестанет получать заявки и не сможет их согласовывать — ни в платформе, ни из Telegram. Роли и остальные права не меняются, вернуть в модераторы можно в любой момент.":
    "“{name}” will stop receiving submissions and will not be able to approve them — neither in the platform nor from Telegram. Roles and other permissions stay as they are, and you can restore them at any time.",
  "Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться. Вернуть себя сможете здесь же, в блоке «Сняты с модерации». Продолжить?":
    "You are revoking review rights FROM YOURSELF: submissions will stop opening. You can restore yourself right here, under “Removed from moderation”. Continue?",
  "Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться, и вернуть себя обратно вы уже не сможете — это сделает другой администратор. Продолжить?":
    "You are revoking review rights FROM YOURSELF: submissions will stop opening, and you will not be able to restore yourself — another administrator will have to. Continue?",
  "«{name}» убран из модераторов": "“{name}” removed from moderators",
  "«{name}» снова модератор": "“{name}” is a moderator again",
  "Не удалось убрать из модераторов": "Could not remove from moderators",
  "Не удалось вернуть в модераторы": "Could not restore as moderator",

  // ── KPI tile clarifications ──
  "сравнение по {n} сопоставимым": "compared across {n} like-for-like companies",
  "{n} ещё не сдали отчётность": "{n} have not reported yet",
  "нет сопоставимого прошлого года": "no comparable prior year",
  "Итог — сумма по {inYear} компаниям, сдавшим отчётность за год. Процент — рост по {pair} компаниям, у которых есть данные и за прошлый год. Ещё {gone} компаний отчитались за прошлый год, но не за текущий, поэтому итог меньше прошлогоднего.":
    "The total sums the {inYear} companies that reported for this year. The percentage is growth across the {pair} companies that also have prior-year data. Another {gone} companies reported last year but not this one, which is why the total is below last year's.",
  "Итог — сумма по {inYear} компаниям; процент — рост по {pair} сопоставимым.":
    "The total covers {inYear} companies; the percentage is growth across {pair} like-for-like companies.",
};
