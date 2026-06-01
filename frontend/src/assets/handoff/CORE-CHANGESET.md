# UzAssets — design-system changeset (всё, кроме Proposals)

> Сводный документ по **базовым** редизайнам и токенам системы — то, что отработано в
> `ui_kits/platform/` и `colors_and_type.css`, помимо группы Proposals (она вынесена в
> `handoff/PROPOSALS-CHANGESET.md`). Применять в кодбейзе `platfoorm_uzassets` через
> Claude Code (по разделам) или GitHub-импортом.
>
> Эталоны: интерактивный кит — `ui_kits/platform/index.html`; токены — `colors_and_type.css`;
> карточки дизайн-системы — `preview/*.html` (вкладка Design System).

Порядок: 0 (токены) → 1 (полоски) → 2 (donut) → 3 (тёмная тема) → 4 (компоненты).

---

## 0 · Токены — сверить с `main.css` / `tailwind.config.js`

Полный список — в `colors_and_type.css` (копия 1:1 из кодбейза + семантические добавки).
Ключевое, что должно совпадать:

**Бренд-фиолетовый:** `--p #7C6FF7` · hover `#6C5CE7` · deep `#534AB7` · sidebar-active `#AFA9EC`.
**Второй системный (бирюзовый):** `#1D9E75` — конец градиента EPT, success И «трансформация».
**Семантические акценты (новое):** `--acc-operational #7C6FF7`, `--acc-transform #1D9E75`.
**Статусы:** green `#1D9E75` · amber `#EF9F27` · orange `#D97706` · red `#EF4444` · blue `#378ADD` · teal `#0891B2`.
**Severity (закупки/аудит):** critical `#A32D2D` · high `#E24B4A` · mid `#BA7517` · low `#5F5E5A` · good `#0F6E56`.
**Навигация (тёмная):** topbar `linear-gradient(135deg,#0C1230,#111A3E)`, sidebar `180deg` те же стопы.
**Фон страницы:** `linear-gradient(145deg,#EEF0FF,#F4F2FF,#EBF0FF)`.
**Текст:** t1 `#0F172A` · t2 `#334155` · t3 `#64748B` · navy-heading `#1E2A4A`.

**Радиусы:** 8 кнопки · 10 инпуты/мелкие кнопки · 11 пиллы · 14 карточки · 16 signature · 20 модалки · 24 hero (login).
**Тени:** `--sh` (покой) / `--shm` (hover) / `--shl` (модалка) — тёплый синий, см. `colors_and_type.css`.
**Движение:** основной easing `cubic-bezier(.34,1.2,.64,1)`; длительности 120/180/450/700мс.
**Шрифты:** Geist + Geist Mono (Inter fallback). Вес 500 — рабочий, 600 — заголовки секций, 700 — только topbar h1. Трекинг отрицательный на крупном, положительный на uppercase-лейблах.

**Промпт для Claude Code:**
```
Сверь src/assets/main.css и tailwind.config.js с таблицей токенов из раздела 0 хендоффа.
Добавь недостающие семантические переменные --acc-operational (#7C6FF7) и
--acc-transform (#1D9E75) в :root. Существующие токены НЕ переименовывай.
```

---

## 1 · Индикаторы: убрать `border-left` → боковая вставная полоска

**Финальное правило:** цветовой индикатор у карточек/строк/таблиц — **боковая ВСТАВНАЯ
полоска** (скруглённый бар через `::before`, с отступом сверху/снизу, внутри левого
паддинга). НЕ `border-left` и НЕ верхняя полоска.

### A. Утилита `src/assets/uza-side-stripe.css`
```css
.uza-side-stripe { position: relative; overflow: hidden; }
.uza-side-stripe::before {
  content: ""; position: absolute;
  left: 6px; top: 12px; bottom: 12px;
  width: 4px; border-radius: 4px;
  background: var(--stripe-color, #7F77DD);
}
.uza-side-stripe-tight::before { top: 6px; bottom: 6px; }
@media (prefers-reduced-motion: no-preference) {
  .uza-side-stripe::before { transition: height .22s cubic-bezier(.34,1.2,.64,1); }
}
```
Подключить импортом в entrypoint рядом с `main.css`.

### B. Миграция всех цветных border-left
**Промпт:**
```
Цветной акцент-индикатор у карточек/строк/таблиц → боковая вставная полоска
(.uza-side-stripe / .uza-side-stripe-tight, цвет через --stripe-color), НЕ border-left,
НЕ верхняя полоска. Найди все цветные border-left/borderLeft (2–4px solid <color>) и переведи:
  • CSS: убрать border-left; добавить класс .uza-side-stripe(-tight); цвет → --stripe-color;
    левый паддинг host ~18–20px.
  • inline/:style: borderLeftColor:x → '--stripe-color':x + класс.
НЕ ТРОГАТЬ структурные хайрлайны border-left:0.5px/1px solid var(--border|#E2E8F0)
(разделители колонок, sidebar, оси графиков) и *-source/комментарии. Прогони lint+сборку.
```

**Инвентарь строк-списков → `.uza-side-stripe-tight`:** `Dashboard.vue:793`,
`Companies.vue:178`, `Consultants.vue:415`, `FinSectorTable.vue:91,109`,
`RatingsSectorTable.vue:220,232`, `SectorsAdminTab.vue:94`, `IfrsEditor.vue:1247`,
`NsbuEditor.vue:1086`, drill-модалки `CompanyTileDrillModal.vue:327,384,467`,
`FinKpiDrillModal.vue:628,768`.
**Карточки/панели → `.uza-side-stripe`:** `ESGCompanyDetailModal.vue:39,117`,
`CapexQuarterlyModal.vue:187`, `CompanyDrilldown.vue:362`, `CompanyProfileModal.vue:398`,
`PaPurchaseDrillModal.vue:229,242,253`, `ApiKeysManager.vue:251`,
`ExternalApisManager.vue:205`, `AccessCard.vue:35`.
**Не трогать (разделители 0.5–1px):** `RatingsRecentChanges.vue:206`,
`RatingsNoRatingPanel.vue:129`, `WeatherWidget.vue:299`, `ExecDashBottomMetrics.vue:224,321,336`,
`ApiPanel.vue:117`, `AiSettings.vue:271`, `KpiDrillModal.vue:501`, `Login.vue:364`,
`ForgotPasswordPage.vue:348`, `TaskProjectEditor.vue:1666,2100`, `CompanyNotesTab.vue:1922`.

**Эталон:** `.bli` / `.uza-side-stripe*` в `ui_kits/platform/kit.css`,
карточка `preview/comp-bordered-list.html`.

---

## 2 · Donut статусов — тонкое кольцо с разделителями

Стиль уже совпадает с Chart.js в кодбейзе (`SignatureDonut.vue`, `Dashboard.vue`):
**cutout ~84%** (тонкое кольцо), **тонкие белые разделители** между сегментами (≈4px),
**скруглённые концы** сегментов, центр — крупное число + подпись. Отдельных правок обычно
не требует; если где-то donut толстый/без разделителей — привести к этим параметрам
(`cutout:'84%'`, `borderWidth:3`, `borderColor:'#fff'`, `borderRadius:6`, `spacing` малый).
**Эталон:** SVG-donut в `ui_kits/platform/Dashboard.jsx` (r68, sw12, белые зазоры, round-caps).

---

## 3 · Тёмная тема

Палитра навигации (navy) уже тёмная → расширить на ВСЕ поверхности через атрибут
`[data-theme="dark"]` на `<html>`. Полный набор оверрайдов — блок `[data-theme="dark"]`
в `ui_kits/platform/kit.css` (фон, карточки, строки, инпуты, модалки, тосты, пиллы,
login, скелетоны). Ключевые сдвиги:

- Фон: `linear-gradient(145deg,#050816,#080B20,#050816)`.
- Поверхности карточек: `rgba(24,28,52,.92–.98)`, бордер `rgba(255,255,255,.07–.10)`.
- Текст: t1 `.98` / t2 `.82` / t3 `.62` белого. Бренд-фиолетовый светлеет до `#C7C2F3`.
- Статусы ярче: green `#5EE1B1`, red `#FF7E7D`, amber `#F4C97A`, blue `#7CBCE8`.
- Тени глубже (чёрные), тонкая aurora-подсветка `body::before` (purple/teal, 4–6% opacity).
- Плавный переход темы 0.35s на bg/color/border/shadow.

**Промпт:**
```
Внедри тёмную тему через [data-theme="dark"] на <html>. Перенеси оверрайды из блока
[data-theme="dark"] в ui_kits/platform/kit.css на токены кодбейза (main.css). Добавь
переключатель в топбар (солнце/луна) с сохранением выбора в localStorage. Навигация уже
тёмная — переключаются контентные поверхности. Проверь контраст и login в обеих темах.
```

---

## 4 · Компоненты — визуальные сверки

Эталон каждого — соответствующий файл/класс в `ui_kits/platform/`. Структуру и API
существующих компонентов НЕ менять — только визуальные параметры.

- **Sidebar** (248px, navy `180deg`): активный пункт — фиолетовый wash + 1px лавандовый
  бордер + inner-glow; иконки 16px stroke; AI-premium карточка сверху; collapsible-группы
  Финансы/Закупки. Эталон `.uza-aside*`, `Sidebar.jsx`.
- **Topbar** (56px sticky, navy `135deg`): eyebrow + h1 + контролы (валюта/магнитуда/год/
  экспорт) + переключатель темы. Все контролы — внутри топбара. Эталон `.uza-topbar*`, `Topbar.jsx`.
- **KPI-карточка** (signature): glass `rgba(255,255,255,.82)`, blur 16px, радиус 16,
  анимированная 3px **верхняя** акцентная полоска (draw-in → breathe → shimmer). Число —
  разной жирностью (`.kpi-value-mixed`). Эталон `.uza-card-accent`, `KpiCard.jsx`.
- **Строка списка компаний** (`.bli`): glass, радиус 11, **боковая полоска** прогресса,
  hover — лифт + стрелка справа. Эталон `.bli`, `BorderedListItem` в `KpiCard.jsx`.
- **Пиллы/чипы:** uppercase 10px/500, радиус 11, семантические тона (teal/amber/purple/
  blue/red/green/gray). Эталон `.pill-*`.
- **Кнопки:** primary — фиолетовый градиент + glow + лифт на hover; secondary — glass +
  лавандовый бордер. Эталон `.btn-p` / `.btn-s`.
- **Инпуты:** 1.5px `#E2E8F0`, bg `#F8FAFC`, focus — фиолетовый бордер + ring `rgba(124,111,247,.14)`. Эталон `.uza-input`.
- **Модалка:** glass + backdrop blur 8px, радиус 20, анимация modal-in. Эталон `.modal*`.
- **Тост:** низ-право, navy, авто-скрытие 2.8с. Эталон `.toast`.
- **Login:** двухколоночный glass с girih-фоном, степ-ревил (минфин-крест → UzAssets-mark),
  тёмный вариант. Эталон `Login.jsx`, `.lg-*`.
- **EPT-mark:** градиент `#7F77DD→#1D9E75`, пиксели-частицы собираются → стрелка. Эталон
  `EptLogo.jsx`, `assets/EptLogo-source.vue`.
- **Иконки:** 16px stroke-only, `stroke-width:2`, round-caps, Lucide-эквивалент. Эмодзи нет.

---

## Чеклист
- [ ] 0 — токены сверены, добавлены `--acc-operational` / `--acc-transform`
- [ ] 1A — `uza-side-stripe.css` создан и подключён
- [ ] 1B — все цветные border-left → боковая полоска; хайрлайны не тронуты
- [ ] 2 — donut'ы приведены к тонкому кольцу с разделителями (где надо)
- [ ] 3 — тёмная тема + переключатель в топбаре
- [ ] 4 — компоненты сверены с эталонами кита
- [ ] `npm run lint` + сборка зелёные

> Группа Proposals (16 предложений) — отдельно в `handoff/PROPOSALS-CHANGESET.md`;
> детальные промпты по карточке/модалке — в `handoff/REDESIGN-CHANGESET.md`.
