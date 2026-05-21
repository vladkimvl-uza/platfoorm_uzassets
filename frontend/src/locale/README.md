# `frontend/src/locale/` — locale-aware formatters

Level-1 i18n foundation. Every number, currency, date, time, and percentage in
the Vue 3 platform flows through these helpers so it can switch with the
user-selected language without a page reload.

## Quickstart

```vue
<script setup lang="ts">
import { useFormatters } from "@/composables/useFormatters";
const fmt = useFormatters();
</script>

<template>
  <div>{{ fmt.fmtMoney(revenue) }}</div>
  <div>{{ fmt.fmtMoneyCompact(debt, "UZS") }}</div>
  <div>{{ fmt.fmtMoneyCompact(debtUsd, "USD", { decimals: 1 }) }}</div>
  <div>{{ fmt.fmtPercent(completion) }}</div>
  <div>{{ fmt.fmtDate(loan.signed_at) }}</div>
  <div>{{ fmt.fmtRelativeTime(activity.ts) }}</div>
</template>
```

## API

| Function | Output examples |
|---|---|
| `fmtNumber(v, { decimals })`           | `62 480 000` / `62,480,000` |
| `fmtNumberCompact(v, { decimals })`    | `62,48 млрд` / `62.48 B` |
| `fmtPercent(v, { decimals, signed })`  | `94,3 %` / `94.3%` |
| `fmtMoney(v, currency, { decimals, useSymbol })` | `62 480 000 сум` / `$1,200.00` |
| `fmtMoneyCompact(v, currency)`         | `62,48 млрд сум` / `$1.2B` |
| `fmtDate(v, { long, includeYear })`    | `14 мар 2026` / `Mar 14, 2026` |
| `fmtDateNumeric(v)`                    | `14.03.2026` / `03/14/2026` |
| `fmtTime(v)`                           | `14:32` / `2:32 PM` |
| `fmtDateTime(v)`                       | `14 мар, 14:32` |
| `fmtRelativeTime(v)`                   | `2 ч назад` / `2 soat oldin` / `2h ago` |

All functions return the dash `—` for `null` / `undefined` / `NaN`.

## Locales

| code     | Intl code     | Notes                                |
|----------|---------------|--------------------------------------|
| `ru`     | `ru-RU`       | Default. Thin-space thousand, comma decimal. |
| `uz-latn`| `uz-Latn-UZ`  | Uzbek Latin. `soʻm`, `mlrd`.         |
| `uz-cyr` | `uz-Cyrl-UZ`  | Uzbek Cyrillic. `сўм`, `млрд`.       |
| `en`     | `en-US`       | Comma thousand, dot decimal, `$1.2B`. |

All dates anchored to **Asia/Tashkent** regardless of user TZ.

## Switching the locale

```ts
import { useLocaleStore } from "@/stores/locale";
const locale = useLocaleStore();

locale.set("uz-latn");     // explicit
locale.next();              // cycle through all 4
locale.current.value;       // 'ru' | 'uz-latn' | 'uz-cyr' | 'en'
```

The store persists choice to `localStorage("uza-locale-v1")` and updates
`<html lang>` automatically.

## When to use what

| Use case | Function |
|---|---|
| Table cell with money | `fmt.fmtMoney(v)` (full) or `fmt.fmtMoneyCompact(v)` (mini-card) |
| KPI dashboard hero number (BIG digits) | `fmt.fmtNumberCompact(v)` + show currency separately |
| Progress bar % | `fmt.fmtPercent(v)` |
| Audit log row | `fmt.fmtRelativeTime(v)` for compact, `fmt.fmtDateTime(v)` for hover |
| Date input default | `fmt.fmtDateNumeric(v)` |

## Pure vs reactive

* **Pure** (`@/locale`): for non-component code (export utilities, pdf-generators,
  cron-like helpers). Pass `locale` explicitly.
* **Reactive** (`@/composables/useFormatters`): inside `<script setup>` / templates.
  Components re-render on locale change automatically.

## Don't

* Don't add new `toLocaleString("ru-RU")` calls.
* Don't hand-format dates with `.getFullYear()` + concatenation.
* Don't add new currency-word maps elsewhere — extend `currencyNames.ts`.
* Don't touch `frontend/legacy/index.html` — it has its own DICT.
