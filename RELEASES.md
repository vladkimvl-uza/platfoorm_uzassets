# Релизы и окружения — UzAssets

Процесс рассчитан на госплатформу: **мёрж в master ≠ релиз в прод**. Прод
обновляется только осознанным семвер-тегом, после прогона на staging.

## Окружения

| Окружение | Образ (GHCR tag) | Деплой | Назначение |
|---|---|---|---|
| **staging** | `:latest` | авто, с каждого push в master | репетиция миграций + ручной/e2e смоук |
| **production** | `:stable` (= `:vX.Y.Z`) | по семвер-тегу `vX.Y.Z` | министерская система |

CI (`.github/workflows/build-and-push.yml`) собирает 3 образа (backend, nginx,
bot) и тегирует:
- **push в master** → `:latest` + `:sha-<short>` (staging подтягивает `:latest`);
- **тег `vX.Y.Z`** → `:X.Y.Z` + `:X.Y` + `:stable` (прод подтягивает `:stable`).

## Как выпустить релиз

```bash
# 1. Код уже в master, staging автоматически получил :latest.
# 2. Прогнать смоук против staging (GH Actions → "E2E smoke (staging)" → Run),
#    либо локально:  E2E_BASE_URL=https://staging.uz-assets.uz npm run e2e
# 3. Если зелено — выпустить тег:
git tag -a v1.4.0 -m "v1.4.0 — Geist self-host, glass-sweep, kill-switch, finmodel scope"
git push origin v1.4.0
# 4. CI соберёт :v1.4.0 + :stable. Прод (UzCloud) деплоит :stable.
```

**Откат:** задеплоить предыдущий тег — в UzCloud сменить образ на
`ghcr.io/.../uzassets-<svc>:v1.3.0` (или `git push`-нуть старый тег как stable
заново). Каждый релиз = неизменяемая точка отката.

## Качество перед прода (сеть безопасности)

| Гейт | Workflow | Блокирует? |
|---|---|---|
| backend pytest (testcontainers) | `backend-tests.yml` | да |
| backend ruff + mypy | `backend-quality.yml` | ruff да, mypy нет |
| frontend eslint + vue-tsc + vitest | `frontend-ci.yml` | lint/typecheck да, vitest пока нет¹ |
| security scan (pip-audit/bandit/trivy/gitleaks) | `security-scan.yml` | — |
| e2e smoke vs staging | `e2e-staging.yml` (ручной) | gated на `STAGING_URL` |

¹ vitest временно `continue-on-error` из-за pre-existing ICU-дрейфа в
`formatters.test.ts`; новые наборы зелёные. Снять флаг после фикса формат-теста.

## Настроить staging (один раз, инфра — на стороне UzCloud)

1. Создать в UzCloud отдельную апку `uza-staging` (nginx-образ `:latest`) +
   свою БД `uza-staging-db` (копия структуры прода; миграции `alembic upgrade head`
   через `RUN_MIGRATIONS=1`).
2. DNS: `staging.uz-assets.uz` → staging-nginx.
3. GitHub → Settings → **Variables** → `STAGING_URL = https://staging.uz-assets.uz`
   (после этого `e2e-staging.yml` перестаёт быть no-op).
4. (Опц.) Webhook UzCloud → авто-pull `:latest` на push, чтобы staging обновлялся
   без ручного шага.

## Доступ к финансовым данным (product-решение, зафиксировано)

- **finmodel** — per-company scope (как `financials`): `ensure_company_access`
  на все company-эндпоинты. Холдинг-роли с `companies.view_all` — видят всё.
- **elasticity** — portfolio-wide (гейт `finmodel.view`): макро-β сектора —
  аналитический инструмент, его ценность кросс-компанийная; per-company scope
  здесь намеренно НЕ применяется.
