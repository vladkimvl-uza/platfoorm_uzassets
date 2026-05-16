# Phase 19a-1 · Финансовые показатели — Skeleton + Filters + KPI band

**MD5 zip:** см. ниже после сборки. **5 файлов: 1 backend patch + 1 API client + 3 Vue.**

## Что внутри

```
backend/
└── portfolio_summary_patch.py        ← добавить в конец app/api/routes/financials.py

frontend/src/
├── api/
│   └── financials.ts                  ← обновлённый API client с portfolioSummary()
├── components/Financials/
│   ├── financialsHelpers.ts           ← format/KPI math/animation injection
│   ├── FinTopFilters.vue              ← НСБУ/МСФО · UZS/USD/EUR · млрд/млн · сектор · год · view tabs
│   └── FinKpiBand.vue                 ← 5–6 KPI карточек с kpi2 анимацией
└── views/
    └── Financials.vue                  ← orchestrator (заменяет существующий)
```

## Что работает после деплоя

- **Топбар** один в один как в монолите (тёмно-синий gradient): пилюли НСБУ/МСФО · валюта · единицы · dropdown сектор · gold-pill «FY 2024» · табы P&L/SOFP/CashFlow (для НСБУ — Финрезультаты/Баланс)
- **KPI band** на 5 (НСБУ) или 6 (МСФО) карточек с реальными цифрами из БД:
  - Совокупная выручка + YoY% к пред. году (like-for-like — только компании с данными в обоих годах)
  - Операционная маржа + опер. прибыль на сабе
  - EBITDA + маржа %
  - Чистая маржа + чистая прибыль + дельта п.п.
  - Убыточные · из X компаний
  - Внедрение стандартов (МСФО only) — два мини-кольца МСФО / Forensic
- Полоска покрытия над KPI: «X из Y · N без данных за FY · YoY рассчитан по like-for-like basket»
- Анимации монолита: `kpi2DrawIn` 0.8s + `kpi2Breathe` infinite + shimmer 6s + staggered `kpiCardIn` 0/80/160/240/320/400ms
- Под KPI — два **placeholder-блока** для Phase 19a-2 (Donut+таблица) и 19a-3 (Скорборд)

## Не работает / placeholder в этой фазе

- Donut-диаграмма по секторам
- Большая таблица 22 компаний × 6 лет с YoY mini-bar
- Скорборд (правая колонка)
- Drill-down по клику на компанию
- Editor (FinDataEditModal / FinUploadModal)

Всё это в 19a-2, 19a-3, 19a-4. Сейчас цель — **подтвердить что backend и filter chain работают**.

## Установка

### 1. Backend patch

В корне проекта (`uzassets-platform-FULL`):

```powershell
# Скопировать файл патча в контейнер
docker compose cp .\backend\portfolio_summary_patch.py backend:/tmp/patch.py

# Дописать в конец financials.py
docker compose exec backend bash -c "cat /tmp/patch.py >> /app/app/api/routes/financials.py"

# Verify — должно выдать строку с @router.get
docker compose exec backend grep -n "portfolio-summary" /app/app/api/routes/financials.py

# Перезапустить backend (uvicorn с --reload должен подхватить, но на всякий случай)
docker compose restart backend

# Проверить логи на ошибки импорта
docker compose logs backend --tail 30 | Select-String "ERROR|Traceback|portfolio"
```

Если в логах ошибка `cannot import name 'select'` или похожее — патч **уже использует** существующие импорты `financials.py` (select, AsyncSession, Depends, get_current_user, Query, HTTPException, FinancialReport, FinancialLine, Company, User, allowed_company_ids), так что на чистой Python-симфонии должно встать. Если ошибка — пришли первые 30 строк лога, поправлю.

Запрос:
```powershell
# Должен вернуть JSON с items[], не 404
curl -s -k https://localhost/api/financials/portfolio-summary `
  -H "Authorization: Bearer <твой токен из Network tab>" `
  --data-urlencode "standard=IFRS" --data-urlencode "years=2024,2023" -G
```

### 2. Frontend

```powershell
# Распаковать
Expand-Archive -Path "$env:USERPROFILE\Downloads\uzassets-phase19a-1-financials.zip" -DestinationPath .\_p19a1 -Force

# Положить файлы поверх
Copy-Item -Path .\_p19a1\frontend\src\api\financials.ts `
          -Destination .\frontend\src\api\financials.ts -Force
Copy-Item -Path .\_p19a1\frontend\src\components\Financials `
          -Destination .\frontend\src\components\ -Recurse -Force
Copy-Item -Path .\_p19a1\frontend\src\views\Financials.vue `
          -Destination .\frontend\src\views\Financials.vue -Force

Remove-Item .\_p19a1 -Recurse -Force

# Verify
(Get-Item .\frontend\src\views\Financials.vue).Length
Select-String -Path .\frontend\src\views\Financials.vue -Pattern "FinKpiBand" -SimpleMatch
Select-String -Path .\frontend\src\api\financials.ts -Pattern "portfolioSummary" -SimpleMatch

# HMR подхватит автоматом если dev-Vite, иначе:
docker compose restart frontend
```

### 3. Открыть и проверить

`https://localhost/financials` → **Ctrl+Shift+R**.

Что должно появиться:
- Тёмный топбар с заголовком и всеми контролами
- Ниже — индикаторная полоска «X из 22» зелёным + «N без данных» оранжевым
- 6 KPI карточек (МСФО) с втягивающейся золотой полоской сверху, пульсирующей и shimmer
- Реальные числа: Совокупная выручка ≈ 328 млрд UZS для 2024 и т.д.
- Под ними два пунктирных placeholder-блока (Phase 19a-2 / 19a-3)

Переключай standard НСБУ/МСФО — данные должны перезагружаться. Меняй год — числа в KPI должны пересчитываться без перезагрузки сети (всё уже в кэше summary).

## Что мне нужно для перехода к Phase 19a-2

1. Скрин страницы после деплоя
2. Если числа не сходятся с ожиданиями (например в монолите 328,3 трлн а тут другое) — пришли что показывает монолит для того же года, разберём расхождение в расчётах KPI

После подтверждения пойдёт **19a-2**: donut по секторам + 6 табов метрик + большая таблица всех 22 компаний с колонками лет и mini-bar.
