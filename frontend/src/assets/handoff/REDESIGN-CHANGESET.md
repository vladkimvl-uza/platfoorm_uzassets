# UzAssets — единый changeset редизайна для кодбейза

> Я пишу в design-system проект только на чтение исходников `uzassets-platform-FULL/`,
> поэтому здесь — готовый набор изменений. Открой кодбейз в **Claude Code** и применяй
> по разделам. Эталоны вёрстки лежат в этом проекте: `ui_kits/platform/` (интерактивный
> UI-кит) и `preview/proposals/` (карточки «было / стало»).

**Финальное направление по полоскам-индикаторам:** не `border-left` и не верхняя полоска,
а **боковая ВСТАВНАЯ полоска** — скруглённый вертикальный бар через `::before`, с отступом
сверху/снизу, сидящий внутри левого паддинга. Это решение пользователя; в репозитории есть
старая утилита `uza-top-stripe.css` (верхняя полоска) — её НЕ используем для этих правок.

Порядок: A → B → C → D.

---

## A. Добавить утилиту `uza-side-stripe.css`

Создай `src/assets/uza-side-stripe.css` и подключи его один раз в entrypoint (там же,
где импортится `uza-top-stripe.css` / `main.css`):

```css
/* Боковая вставная полоска-индикатор — замена border-left.
   Цвет: var(--stripe-color). На host нужен левый паддинг ~18–20px. */
.uza-side-stripe { position: relative; overflow: hidden; }
.uza-side-stripe::before {
  content: "";
  position: absolute;
  left: 6px; top: 12px; bottom: 12px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, #7F77DD);
}
/* Плотные строки списков/таблиц — меньше вертикальный отступ */
.uza-side-stripe-tight::before { top: 6px; bottom: 6px; }

@media (prefers-reduced-motion: no-preference) {
  .uza-side-stripe::before { transition: height .22s cubic-bezier(.34,1.2,.64,1); }
}
```

Промпт для Claude Code:
```
Создай src/assets/uza-side-stripe.css с правилами .uza-side-stripe / .uza-side-stripe-tight
(содержимое — из раздела A хендоффа) и подключи импортом в entrypoint рядом с main.css.
```

---

## B. Миграция всех цветных `border-left` → `.uza-side-stripe`

### Промпт для Claude Code (вставь целиком)

```
В репозитории цветовой акцент-индикатор у карточек, строк списков и строк таблиц делается
БОКОВОЙ ВСТАВНОЙ полоской (класс .uza-side-stripe из src/assets/uza-side-stripe.css,
цвет через --stripe-color), а НЕ border-left и НЕ верхней полоской.

Найди все ОСТАВШИЕСЯ цветные border-left / borderLeft-индикаторы (2–4px solid <color>)
и переведи их:
  • Статичные CSS-правила: убери строку border-left; добавь элементу класс
    .uza-side-stripe (или .uza-side-stripe-tight для плотных списков/таблиц); цвет задай
    через --stripe-color. Добавь host'у левый паддинг ~18–20px, чтобы текст не налезал.
  • Inline / :style: замени `borderLeftColor: x` или `borderLeft: '3px solid '+x` на
    `'--stripe-color': x` и добавь класс .uza-side-stripe(-tight).
  • Если у строки на :hover есть `transform: translateX(2px)` — оставь как есть
    (боковая полоска совместима со сдвигом) ИЛИ замени на translateY(-2px) для карточек.

НЕ ТРОГАЙ структурные хайрлайны-разделители: `border-left: 0.5px solid …` и
`border-left: 1px solid var(--border|--uza-border|#E2E8F0)` (разделители колонок, sidebar,
оси графиков), а также border-left в комментариях и *-source файлах.

Прогони lint + сборку, выведи список изменённых файлов и diff.
```

### Инвентарь (что менять)

**Строки списков / таблиц → `.uza-side-stripe-tight` + `--stripe-color`:**

| Файл | Строка | Сейчас |
|---|---|---|
| `views/Dashboard.vue` | 793 | `:style="{borderLeftColor: grp.sector_color}"` (`.co-row`) |
| `views/Companies.vue` | 178 | `borderLeft: c.sector_color ? '3px solid '+… : '… transparent'` (`<tr>`) |
| `views/Consultants.vue` | 415 | `:style="{ borderLeftColor: c.color || '#888', … }"` |
| `components/Financials/FinSectorTable.vue` | 91, 109 | `borderLeft: '3px solid '+b.color` (`.fst-sec`, `.fst-row`) |
| `components/Ratings/RatingsSectorTable.vue` | 220, 232 | `borderLeft: '3px solid '+g.color` |
| `components/admin/SectorsAdminTab.vue` | 94 | `:style="{ borderLeftColor: s.color_hex || '#888780' }"` |
| `views/IfrsEditor.vue` | 1247 | `:style="{ borderLeftColor: companyStatusColor(c) }"` |
| `views/NsbuEditor.vue` | 1086 | то же |

**Строки drill-модалок (`.ddm-bord-row`, статичный `border-left: 2px`):**

| Файл | Строка | Действие |
|---|---|---|
| `components/Dashboard/CompanyTileDrillModal.vue` | 467 (+327/384) | убрать `border-left: 2px solid #888780;` из `.ddm-bord-row`, добавить класс `.uza-side-stripe-tight`; на строках 327/384 `borderLeftColor: rowBorderColor(…)` → `'--stripe-color': …` |
| `components/Financials/FinKpiDrillModal.vue` | 628, 768 | то же (628 — `rowSectorColor(r)`) |

**Карточки / панели-индикаторы → `.uza-side-stripe` + `--stripe-color`:**

| Файл | Строка |
|---|---|
| `components/ESG/ESGCompanyDetailModal.vue` | 39, 117 |
| `components/InvestProjects/CapexQuarterlyModal.vue` | 187 |
| `components/Financials/CompanyDrilldown.vue` | 362 (`.cdrl-card`) |
| `components/Procurement/CompanyProfileModal.vue` | 398 (`var(--accent,#7F77DD)`) |
| `components/Procurement/PaPurchaseDrillModal.vue` | 229, 242, 253 |
| `components/api/ApiKeysManager.vue` | 251 |
| `components/api/ExternalApisManager.vue` | 205 |
| `components/rbac-v3/AccessCard.vue` | 35 |

**Тонкие 2px акцент-полоски в хелп-блоках (по желанию):**
`components/Ai/AiMessage.vue:575`, `broadcasts/BroadcastComposer.vue:589`,
`BusinessPlan/BpDrillModal.vue:1018`, `views/MfaOnboarding.vue:1135`,
`SystemConfig/ElasticityProjectsTab.vue:737`, `IfrsEditor/NsbuEditor` (`.ne-hist-fields`).

**НЕ ТРОГАТЬ (структурные разделители 0.5–1px):**
`Ratings/RatingsRecentChanges.vue:206`, `Ratings/RatingsNoRatingPanel.vue:129`,
`Home/WeatherWidget.vue:299`, `ExecDash/ExecDashBottomMetrics.vue:224/321/336`,
`library/ApiPanel.vue:117`, `Ai/AiSettings.vue:271`, `InvestProjects/KpiDrillModal.vue:501`
(ось графика), `CompanyWorkspace.vue:6730`, `rbac-v3/UserDetailDrawer.vue:771`,
`views/Login.vue:364`, `ForgotPasswordPage.vue:348`, `TaskProjectEditor.vue:1666/2100`,
`CompanyNotesTab.vue:1922`, `MentionableTextarea.vue:115` (JS-массив, не стиль).

---

## C. Карточка задачи / проекта — `views/BoardKanban.vue`

Эталон: `preview/proposals/15-task-card.html` (группа Proposals). Промпт:

```
Файл: src/views/BoardKanban.vue. Блок <div v-for="t in col.tasks" …> (<!-- Cards -->).

1. БАГ: тройной DirectionBadge. Сейчас три подряд блока v-if="t.direction_meta"
   (один в .kc-title + два после). Оставь РОВНО ОДИН (variant="bar" size="sm"), два удали.

2. Левый бордер приоритета → боковая вставная полоска. Убери `border-l-2` и
   :style border-left-color; добавь класс .uza-side-stripe и :style="{ '--stripe-color':
   PRIO_COLOR[t.priority] }"; левый паддинг карточки ~18px.

3. Приоритет-пилл БЕЗ сокращений: вместо t.priority[0] выводи полное PRIO_LABEL[t.priority]
   (Критический / Высокий / Средний / Низкий). bg = PRIO_COLOR+'15', color = PRIO_COLOR.

4. Исполнитель в футере → аватар инициалов (20px, border-radius 6px, градиент
   #8B7FFF→#6C5CE7, белые инициалы из assignee_name) + имя. «не назначена» оставить.

5. Срок → иконка-календарь (16px stroke) + дата; красный только при isOverdue(t).

6. Все бейджи (direction / linked_year / «Проект» / quarterly / monthly / ongoing) в ОДИН
   ряд с переносом (flex-wrap, gap 5px), мелкие приглушённые чипы. Никаких стопок.

7. Если t.is_project: добавь список входящих задач между чипами и футером:
   заголовок «Задачи» + счётчик «<done> из <total> · <progress_percent>%»; до 5 строк —
   статус-точка 7px (Готово #1D9E75 / В работе #7F77DD / На утверждении #EF9F27 /
   Просрочено #E24B4A) + название (выполненные: приглушён + line-through) + состояние
   словом справа (БЕЗ сокращений). Источник подзадач — реальное поле проекта (subtasks/
   children/t.tasks; если на доске нет — подгрузить как в drill-модали проекта). >5 задач:
   первые 5 + «ещё N».

Прогони lint + сборку, выведи diff по BoardKanban.vue.
```

---

---

## C2. Модалка-редактор задачи/проекта — `TaskProjectEditor.vue`

Эталон: `preview/proposals/16-task-editor.html` (группа Proposals). Промпт:

```
Файл: src/views/TaskProjectEditor.vue (или компонент модалки-редактора задачи/проекта).
Редизайн ВНЕШНЕГО ВИДА модалки, логику и поля не трогать. Сделай:

1. Статус (Инициирование / В процессе / На согласовании / Завершено) — вместо россыпи
   равнозначных пилл-тогглов сделай горизонтальный СТЕППЕР: узлы соединены линией;
   пройденные статусы — зелёный узел с галочкой + зелёная линия; текущий — янтарный узел
   с подсветкой (box-shadow 0 0 0 4px rgba(239,159,39,.18)) и янтарной подписью; будущие —
   серый контурный узел, серая подпись. Клик по узлу по-прежнему меняет статус.

2. Прогресс + дедлайн — вынеси в ОТДЕЛЬНУЮ плашку под степпером (bg #F8FAFC, border
   #EEF1F5, radius 10): прогресс-бар (градиент #7F77DD→#1D9E75) + «<pct>%» (целое 600,
   «%» приглушён) слева; дедлайн + чип «просрочено N дн» (красный, rgba(226,75,74,.12))
   справа. Убери тесноту из строки статусов.

3. «Относится к проекту» — карточка с БОКОВОЙ вставной полоской (.uza-side-stripe,
   --stripe-color #7F77DD), иконка-папка в плитке, label + название + FY-чип, стрелка
   «открыть» справа.

4. Правая колонка (Ответственный / Консультант / Направление / Приоритет / FY /
   Архивировать) — собери в мягкую glass-панель (bg linear-gradient #FAFAFE→#F6F5FD,
   border #ECEAFB, radius 14, padding 16). Ответственный — с аватаром-плейсхолдером слева.
   Приоритет — поле с цветной точкой статуса + слово (без сокращений). «Архивировать» —
   приглушённая danger-кнопка (контур rgba(226,75,74,.3), текст #C0392B, hover-фон лёгкий).

5. Поля ввода — единый стиль: border 1.5px #E2E8F0, bg #F8FAFC, radius 10, focus —
   border #7C6FF7 + ring rgba(124,111,247,.14). Аплоады (Результаты / Документы) —
   заголовок + кнопка «Загрузить» в ряд, под ней пунктирная дроп-зона с пустым состоянием.
   «Перенос на FY+1» и (для проекта) «Основание и тип проекта» — единый стиль collapse.

6. Вариант ПРОЕКТА (kind=project): тип-пилл «Проект», без блока «Относится к проекту»,
   плюс секция «Основание и тип проекта» (collapse) и — опционально — список входящих
   задач (как в карточке проекта, раздел C: статус-точка + название + состояние словом).

Footer (Отмена / Сохранить) и табы (Детали / Комментарии) оставить, привести к общему
стилю. Прогони lint + сборку, выведи diff.
```

Ключевые цвета: статусы — Завершено/done #1D9E75, текущий #EF9F27; приоритет «Средний»
точка #EF9F27; прогресс-градиент #7F77DD→#1D9E75; danger #C0392B / rgba(226,75,74,.*).

---

## D. Прочие визуальные стандарты (из UI-кита)

Это редизайны, отработанные в `ui_kits/platform/` — применять по желанию, выборочно.
Эталон кода — соответствующие файлы кита.

1. **Секторные monogram-аватары** для компаний (списки/строки): 2 буквы из названия,
   градиент по сектору (mining зелёный, oil&gas фиолетовый, chem янтарный, transport
   синий, energy красный). Эталон: `.cmp-avatar*` в `ui_kits/platform/kit.css`,
   логика — `CompanyAvatar` в `KpiCard.jsx`. Разделяет «что за компания» (аватар) и
   «как идёт» (полоска прогресса).

2. **Alert-вариант KPI-карточки** для критических метрик (просрочка и т.п.): красный
   градиент-фон, пульсирующая точка, явный CTA. Эталон: `.uza-card-alert` в `kit.css`,
   проп `variant="alert"` в `KpiCard.jsx`. В кодбейзе уже есть похожее
   (`_cp-styles-append.css` `.cp-overdue-alert::before`) — свериться и унифицировать.

3. **Числа разной жирностью** (#5): целая часть 600, дробная — 400 приглушённая, единица
   мелко/muted. Эталон: `.kpi-value-mixed` (`.kv-int/.kv-dec/.kv-unit`) в `kit.css`.

4. **Тёмная тема** (#12): полная палитра под `[data-theme="dark"]` (фон навигации уже
   тёмный — расширяется на все поверхности). Эталон: блок `[data-theme="dark"]` в
   `ui_kits/platform/kit.css`. Активация — атрибут на `<html>`.

5. **Микро-анимации**: stagger карточек 60–80мс (#8), hover-affordance со стрелкой на
   строках (#10). Эталон — `kit.css` (`uzaCardIn`, `.bli-arrow`) и `Dashboard.jsx`.

6. **Donut статусов**: тонкое кольцо (cutout 84%), тонкие белые разделители, скруглённые
   концы сегментов — это уже совпадает со стилем Chart.js в кодбейзе
   (`SignatureDonut.vue`, `Dashboard.vue`), отдельных правок не требует.

---

## Чеклист применения

- [ ] A: добавлен `uza-side-stripe.css` + импорт
- [ ] B: все цветные `border-left` → `.uza-side-stripe(-tight)`; хайрлайны не тронуты
- [ ] C: `BoardKanban.vue` — фикс тройного бейджа + редизайн карточки + список задач проекта
- [ ] C2: `TaskProjectEditor.vue` — степпер статусов, плашка прогресса, glass-сайдбар, боковая полоска
- [ ] D (опц.): аватары, alert-KPI, mixed-weight, dark mode, микро-анимации
- [ ] `npm run lint` + сборка зелёные
