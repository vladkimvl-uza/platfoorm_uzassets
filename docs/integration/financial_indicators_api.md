# Финансовые показатели компаний — API для интеграции

Документ описывает, **как получить (GET) и записать (PUT) любой показатель компании** через API
платформы: ИНН, годовые индикаторы (Спонсорство, Налоги, Численность) и значения
финансовой отчётности (МСФО/НСБУ: ОФР, ОПД, Баланс, ДДС).

- Базовый URL: `https://<хост>/api` (на проде nginx проксирует `/api/*` → backend).
- Формат: JSON. Все эндпоинты требуют авторизации (Bearer-токен).
- Значения отчётности — в той же шкале, что в редакторе (млрд UZS, если не указано иное).

---

## 0. Авторизация (получение токена)

```bash
curl -sk -X POST https://<хост>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"user@uz-assets.uz","password":"<пароль>"}'
```

Ответ:

```json
{ "access_token": "eyJ...", "refresh_token": "eyJ...", "token_type": "Bearer", "expires_in": 1800 }
```

Дальше во всех запросах добавляйте заголовок:

```
Authorization: Bearer <access_token>
```

Права: чтение показателей — `financials.view`, запись — `financials.edit`
(scope по компаниям учитывается: пользователь видит/правит только доступные ему компании).

---

## 1. Таблица показателей и эндпоинтов

`{code}` — код компании (см. раздел 4). Год — 4 цифры (`2024`).

### 1.1. Индикаторы уровня компании (стандарт-агностичны — один набор на компанию)

| Показатель | Поле (field id) | Тип | Хранение | Read | Write |
|---|---|---|---|---|---|
| ИНН | `inn` | строка | `companies.inn` | `GET …/indicators` → `inn` | `PUT …/indicators` `{set_inn,inn}` |
| Спонсорство (по годам) | `sponsorship` | число (млрд UZS) | `companies.extra.indicators` | `GET …/indicators` | `PUT …/indicators` |
| Налоги (по годам) | `taxes` | число (млрд UZS) | `companies.extra.indicators` | `GET …/indicators` | `PUT …/indicators` |
| Численность (по годам) | `headcount` | число (чел.) | `companies.extra.indicators` | `GET …/indicators` | `PUT …/indicators` |

Эндпоинт: `…/indicators` = `/financials/companies/{code}/indicators`.

### 1.2. Значения финансовой отчётности (по годам, зависят от стандарта)

| Раздел | Эндпоинт чтения | Эндпоинт записи |
|---|---|---|
| МСФО (ОФР/ОПД/Баланс/ДДС) | `GET /financials/companies/{code}/ifrs-editor?period=FY&consolidated=true` | `PUT /financials/companies/{code}/ifrs-editor` |
| НСБУ (форма 2 + форма 1) | `GET /financials/companies/{code}/nsbu-editor` | `PUT /financials/companies/{code}/nsbu-editor` |

Значения возвращаются картой `values[field][год]`. Основные `field id`:

| Показатель | field id | Стандарт · раздел |
|---|---|---|
| Выручка / Revenue | `revenue` | оба · ОФР |
| Себестоимость / Cost of sales | `cogs` | оба · ОФР |
| Валовая прибыль / Gross profit | `grossProfit` | оба · ОФР |
| Операционная прибыль | `opProfit` | оба · ОФР |
| Амортизация / D&A | `depreciation` | оба · ОФР |
| Фин. расходы / Finance costs | `finCost` | оба · ОФР |
| Прибыль до налога / PBT | `pbt` | оба · ОФР |
| Налог / Income tax | `tax` | оба · ОФР |
| Чистая прибыль / Net profit | `profit` | оба · ОФР |
| EBITDA | `ebitda` | оба · ОФР |
| Итого активы / Total assets | `totalAssets` | оба · Баланс |
| Собственный капитал / Equity | `equity` | оба · Баланс |
| Денежные средства / Cash | `cash` | оба · Баланс |
| Финансовый долг / Total debt | `debt` | оба · Баланс |
| Совокупный доход (ОПД) | `total_comprehensive_income` | МСФО · ОПД |
| CFO / CFI / CFF | `cfo` / `cfi` / `cff` | МСФО · ДДС |
| Free Cash Flow | `freeCashFlow` | МСФО · ДДС |

Полный перечень `field id` приходит ключами в `values` ответа `…/ifrs-editor` / `…/nsbu-editor`.

---

## 2. Справочник эндпоинтов

### 2.1. GET индикаторы компании

```
GET /api/financials/companies/{code}/indicators
```

Ответ:

```json
{
  "code": "res",
  "inn": "306350099",
  "indicators": {
    "sponsorship": { "2023": 9.0, "2024": 12.5 },
    "taxes":       { "2024": 450.0 },
    "headcount":   { "2024": 1250 }
  }
}
```

### 2.2. PUT индикаторы (upsert — единичная правка ИЛИ массовый импорт)

```
PUT /api/financials/companies/{code}/indicators
```

Тело (все поля необязательны — шлите только то, что обновляете):

```json
{
  "set_inn": true,
  "inn": "306350099",
  "indicators": {
    "sponsorship": { "2024": 12.5 },
    "taxes":       { "2024": 450.0 },
    "headcount":   { "2024": 1250 }
  }
}
```

Семантика:
- `set_inn=true` → применить `inn` (пустая строка/`null` → очистить). Без `set_inn` ИНН не трогается.
- `indicators` — мерж по `field`/`год`. Значение `null` в ячейке **удаляет** этот год.
- Неизвестные поля (не `sponsorship`/`taxes`/`headcount`) и нечисловые значения игнорируются.

Ответ: `{ "code", "inn", "indicators", "saved": true }`.

### 2.3. GET значения отчётности

```
GET /api/financials/companies/{code}/ifrs-editor?period=FY&consolidated=true
GET /api/financials/companies/{code}/nsbu-editor
```

Ответ (фрагмент):

```json
{
  "code": "res",
  "values": {
    "revenue":     { "2022": 20909, "2023": 34276, "2024": 47763 },
    "ebitda":      { "2024": 1273 },
    "totalAssets": { "2024": 29529 }
  },
  "renames": {}, "notes": {}, "manualFlags": {}, "audit_meta": null
}
```

### 2.4. PUT значения отчётности

```
PUT /api/financials/companies/{code}/ifrs-editor    (МСФО)
PUT /api/financials/companies/{code}/nsbu-editor     (НСБУ)
```

Тело МСФО: `{ period:"FY", consolidated:true, currency:"UZS", values:{field:{год:значение}}, customFields, renames, formulaOverrides, manualFlags, notes, audit_meta }`.
Тело НСБУ: `{ values, customFields, renames, formulaOverrides, manualFlags }`.
Минимально достаточно прислать `values` (плюс `period/consolidated` для МСФО).

---

## 3. Инструкция: как вытащить конкретный показатель (пошагово)

> Цель: получить значение показателя по компании через API.

### Шаг 1. Узнать код компании
Возьмите `{code}` из раздела 4 (например, `res` = «Региональные электрические сети»).

### Шаг 2. Получить токен
```bash
TOKEN=$(curl -sk -X POST https://<хост>/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"login":"user@uz-assets.uz","password":"<пароль>"}' | jq -r .access_token)
```

### Шаг 3a. Вытащить ИНН
```bash
curl -sk https://<хост>/api/financials/companies/res/indicators \
  -H "Authorization: Bearer $TOKEN" | jq -r .inn
# → 306350099
```

### Шаг 3b. Вытащить Спонсорство / Налоги / Численность за год
```bash
# всё сразу:
curl -sk https://<хост>/api/financials/companies/res/indicators \
  -H "Authorization: Bearer $TOKEN" | jq '.indicators'

# только Налоги за 2024:
curl -sk https://<хост>/api/financials/companies/res/indicators \
  -H "Authorization: Bearer $TOKEN" | jq -r '.indicators.taxes["2024"]'
# → 450
```

### Шаг 3c. Вытащить финансовый показатель (например, Выручку 2024, МСФО)
```bash
curl -sk "https://<хост>/api/financials/companies/res/ifrs-editor?period=FY&consolidated=true" \
  -H "Authorization: Bearer $TOKEN" | jq -r '.values.revenue["2024"]'
# → 47763
```

### Шаг 4 (опционально). Записать/обновить показатель
```bash
# обновить Налоги за 2024:
curl -sk -X PUT https://<хост>/api/financials/companies/res/indicators \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"indicators":{"taxes":{"2024":480.0}}}'
```

### Пример на Python
```python
import requests
BASE = "https://<хост>/api"
tok = requests.post(f"{BASE}/auth/login",
                    json={"login": "user@uz-assets.uz", "password": "<пароль>"},
                    verify=False).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

# Вытащить численность сотрудников РЭС за 2024:
ind = requests.get(f"{BASE}/financials/companies/res/indicators", headers=H, verify=False).json()
print("headcount 2024:", ind["indicators"].get("headcount", {}).get("2024"))

# Массовый импорт показателей за 2024:
requests.put(f"{BASE}/financials/companies/res/indicators", headers=H, verify=False, json={
    "set_inn": True, "inn": "306350099",
    "indicators": {
        "sponsorship": {"2024": 12.5},
        "taxes":       {"2024": 450.0},
        "headcount":   {"2024": 1250},
    },
})
```

---

## 4. Справочник кодов компаний (`{code}`) и ИНН

| code | Компания | ИНН |
|---|---|---|
| `ngmk` | АО «Навоийский ГМК» | 308425864 |
| `nur`  | ГП «Навоийуран» | 201204514 |
| `agmk` | АО «Алмалыкский ГМК» | 202328794 |
| `umk`  | АО «Узметкомбинат» | 200460222 |
| `uug`  | АО «Узбекуголь» | 200899410 |
| `ung`  | АО «Узбекнефтегаз» | 200837914 |
| `utg`  | АО «Узтрансгаз» | 200626188 |
| `ugt`  | АО «UzGasTrade» | 309702449 |
| `hgt`  | АО «Худудгазтаъминот» | 306605769 |
| `nes`  | АО «Национальные электрические сети» | 306347741 |
| `tes`  | АО «Тепловые электрические станции» | 306349304 |
| `res`  | АО «Региональные электрические сети» | 306350099 |
| `uge`  | Узбекгидроэнерго | 304952767 |
| `uty`  | Узбекистон Темир Йуллари | 201051951 |
| `uhy`  | АО «Uzbekistan Airways» | 306628114 |
| `uap`  | АО «Uzbekistan Airports» | 306646884 |
| `utc`  | АО «Узбектелеком» | 203366731 |
| `tst`  | АО «Тошшахартрансхизмат» | 302762364 |
| `upt`  | Узбекистон Почтаси | 200833833 |
| `uas`  | АО «Узавтосаноат» | 201053918 |
| `naz`  | АО «Навоийазот» | 200002933 |
| `uks`  | Узкимёсаноат | 203621367 |

> Коды стабильны. Полный актуальный список компаний: `GET /api/companies`.

---

## 5. Примечания
- Индикаторы (`inn`, `sponsorship`, `taxes`, `headcount`) — **стандарт-агностичны**: один набор на компанию, не зависят от МСФО/НСБУ и периода.
- Значения отчётности зависят от стандарта (МСФО/НСБУ) и для МСФО — от `period`/`consolidated`.
- Все операции записи идемпотентны и пишут запись в журнал аудита (кто/когда).
- Шкала значений отчётности — как в редакторе (млрд UZS, если не переопределено).
