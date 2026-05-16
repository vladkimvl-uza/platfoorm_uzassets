# Phase 19a-5 · Дозагрузка 6 компаний из Firebase → Postgres

Найдено: в Firebase **есть данные** для 6 компаний без NSBU 2025 в Postgres
(`utc`, `uty`, `uap`, `uks`, `ung`, `upt`), но первая Firebase→Postgres миграция
их пропустила из-за несовпадения имён. Firebase хранит как `Узбектелеком`/`UzPost`,
Postgres ожидал `АО «Узбектелеком»` — простой match по `name_ru` промахнулся.

Probe вывод подтвердил:
- **UzTelecom IFRS** ~45 полей данных
- **Узкимёсаноат** 32 IFRS + 28 NSBU полей
- **Узбекнефтегаз** 35 IFRS + 31 NSBU полей
- остальные 5 ключей с count=1 — заглушки

## Что в пакете

```
probe_firebase.py          ← подтверждает что лежит в Firebase для 6 компаний
fix_diff_script.py         ← патчит сломанный grade() в diff_all_financials.py
migrate_missing_6.py       ← основное: тянет данные из Firebase, пишет в Postgres
```

## Порядок прогона

### Шаг 1: Подтвердить что в Firebase реально есть данные

```powershell
docker cp "$env:USERPROFILE\Downloads\probe_firebase.py" uza-backend:/tmp/probe_firebase.py
docker compose exec backend python /tmp/probe_firebase.py
```

Ожидаемый вывод — для каждой из 6 компаний под каждым candidate-ключом покажет:
- `years=[2021, 2022, ...]`
- сколько data fields
- `revenue_2025=YES/no`

Если для какой-то компании НИ ОДИН ключ не дал `years=[]` — у неё в Firebase
тоже нет данных, дозагружать нечего.

### Шаг 2 (опционально): Починить существующий diff-скрипт

Сломан на 127 строке (вызов `grade()` без аргументов). Один раз патчим:

```powershell
docker cp "$env:USERPROFILE\Downloads\fix_diff_script.py" uza-backend:/tmp/fix_diff_script.py
docker compose exec backend python /tmp/fix_diff_script.py

# Verify — должен теперь работать без TypeError
docker compose exec backend python -m app.scripts.firebase_migration.diff_all_financials --details 2>&1 | Select-Object -First 100
```

Это поможет проверить **остальные 16 компаний** — может там тоже есть гэпы которые
никто не заметил, потому что в монолите они закрыты Firebase-данными напрямую.

### Шаг 3: Сухой прогон миграции (БЕЗ записи)

```powershell
docker cp "$env:USERPROFILE\Downloads\migrate_missing_6.py" uza-backend:/tmp/migrate_missing_6.py
docker compose exec backend python /tmp/migrate_missing_6.py --dry-run
```

Покажет что бы записалось — для каждой компании какой Firebase key использовался,
сколько reports и lines добавилось бы, какие годы найдены. **Никаких записей в БД.**

Жди вывод вида:
```
━━━ UTC (АО «Узбектелеком»)
    candidates: ['UzTelecom', 'Узбектелеком']
    [IFRS] using key 'UzTelecom': years=[2021, 2022, 2023, 2024, 2025]
    [SKIP] NSBU: no data found in Firebase under any of ['UzTelecom', 'Узбектелеком']
    → reports: +5, lines: +75
      IFRS key: UzTelecom
      NSBU key: (none)
```

### Шаг 4: Реальная миграция (С записью)

Если dry-run выглядит ок:

```powershell
docker compose exec backend python /tmp/migrate_missing_6.py --apply
```

Скрипт **идемпотентен** — удаляет старые `FinancialReport+FinancialLine` записи
для (company, year, standard, report_type) перед вставкой свежих. Можно
безопасно перезапускать.

### Шаг 5: Проверить в Postgres

```powershell
docker compose exec postgres psql -U uza -d uzassets -c "SELECT c.code, fr.standard, fr.report_type, fr.year, COUNT(fl.id) FROM companies c JOIN financial_reports fr ON fr.company_id=c.id JOIN financial_lines fl ON fl.report_id=fr.id WHERE c.code IN ('utc','uty','uap','uks','ung','upt') AND fr.source='firebase_late_migration' GROUP BY c.code, fr.standard, fr.report_type, fr.year ORDER BY c.code, fr.standard, fr.year;"
```

Покажет таблицу свежемигрированных записей. Если 0 строк — миграция ничего не записала.

### Шаг 6: F5 на /financials в Vue

В KPI band должны:
- Совокупная выручка вырасти на ~30 трлн UZS (сошлись с монолитом)
- Покрытие стать ~20/22 или 22/22 за FY 2025

## Дизайн скрипта (важные детали)

**Hard-coded маппинг** вместо угадывания: для каждой проблемной компании указан
явный список candidate-ключей в Firebase. Скрипт пробует их по порядку, берёт
первый с непустыми данными.

**Field classification:** Firebase складывает все метрики в один объект, я
сплитую их по `report_type` (PL/BS/CF) согласно стандарту учёта. Это работает
с моим `portfolio-summary` endpoint который аггрегирует все три типа.

**Unit scale:** Firebase хранит значения как-есть (млрд UZS). Записываю в
`financial_reports.unit_scale=1000` для совместимости с legacy схемой, но мой
endpoint уже игнорирует unit_scale и применяет hardcoded ×1_000_000_000 — числа
сойдутся как для остальных компаний.

**Idempotent:** перед каждой вставкой удаляет существующие записи для того же
ключа `(company, year, standard, report_type)`. Можно перезапускать без дублей.

**Source метка:** `source='firebase_late_migration'` — для отслеживания и
возможного отката если что-то пойдёт не так.

## Возможные сюрпризы

**Если в выводе `parse_record` некоторые годы пустые** — значит для этих годов
все поля в Firebase null. Это норма, скрипт их пропускает.

**Если years[] в Firebase content-array а value-arrays — object** — скрипт
нормализует оба варианта через `normalize_array()`.

**Если в Firebase лежат поля которых нет ни в PL_FIELDS/BS_FIELDS/CF_FIELDS** —
они **дропаются** (warning не выводится). Это намеренно: мусорные поля типа
`__custom_xyz` не должны попадать в financial_lines. Если важное поле потерялось —
добавь его в соответствующий set в скрипте и перезапусти.
