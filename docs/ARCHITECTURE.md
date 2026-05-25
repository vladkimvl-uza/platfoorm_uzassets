# UzAssets Backend · 10-Layer Architecture

> **Статус:** 29 из ~30 route-модулей переведены на 10-слойную архитектуру (+ Credit Scenarios). Pattern полностью established. Шаблон — `fastapi-structure.zip` (audit 2026-05-25).

## Layer overview

```
HTTP request
    ↓
api/routes/{module}.py        ← thin HTTP shim: permissions + DTO + delegate
    ↓ uses
dependencies/{module}.py      ← FastAPI DI factories (ServiceDep)
    ↓ creates
services/{module}/...         ← business logic / use cases
    ↓ uses
uow/impl.py                   ← UnitOfWork (transactional boundary)
    ↓ holds
repositories/{module}_repo.py ← data access (SQL queries only)
    ↓ queries
models/                       ← SQLAlchemy ORM
```

| Слой | Назначение | Что МОЖНО | Что НЕЛЬЗЯ |
|---|---|---|---|
| **api/routes** | HTTP transport | Auth checks, request parsing, response serialization, side-effect hooks после commit | SQL queries, бизнес-вычисления, прямое управление транзакциями |
| **dependencies** | DI factories | `Annotated[X, Depends(get_x)]` | Логика |
| **services** | Use cases | UoW transactions, бизнес-правила, оркестрация repos, валидация | HTTP-specific (Request, Response объекты) |
| **uow** | Transaction boundary | Открывает AsyncSession, держит repositories, commit/rollback | Бизнес-логика |
| **repositories** | Data access | `select/insert/update/delete` SQL, возврат ORM | Бизнес-логика, HTTP errors |
| **models** | ORM definitions | SQLAlchemy ORM, relationships, constraints | — |

## Status (14 готовых модулей)

| Module | LOC до | LOC после | Δ |
|---|---:|---:|---:|
| `api/routes/kpi.py` | 781 | 343 | **-56%** |
| `api/routes/procurement_analysis.py` | 944 | 141 | **-85%** |
| `api/routes/tasks.py` | 885 | 277 | **-69%** |
| `api/routes/projects.py` | 627 | 181 | **-71%** |
| `api/routes/governance.py` | 641 | 207 | **-68%** |
| `api/routes/ratings.py` | 381 | 213 | **-44%** |
| `api/routes/notes.py` | 361 | 139 | **-61%** |
| `api/routes/esg.py` | 969 | 212 | **-78%** |
| `api/routes/moderation.py` | 596 | 371 | **-38%** |
| `api/routes/notifications.py` | 425 | 285 | **-33%** |
| `api/routes/partners.py` | 264 | 97 | **-63%** |
| `api/routes/external_apis.py` | 239 | 112 | **-53%** |
| `api/routes/system_config.py` | 332 | 118 | **-64%** |
| `api/routes/companies.py` | 757 | 316 | **-58%** |
| `api/routes/business_plan.py` | 602 | 266 | **-56%** |
| `api/routes/executive_dashboard.py` | 684 | 71 | **-90%** |
| `api/routes/consultants.py` | 764 | 152 | **-80%** |
| `api/routes/api_keys.py` | 329 | 159 | **-52%** |
| `api/routes/comments.py` | 367 | 276 | **-25%** |
| `api/routes/scenarios.py` | 392 | 163 | **-58%** |
| `api/routes/dashboard.py` | 1012 | 75 | **-93%** |
| `api/routes/ai.py` | 443 | 282 | **-36%** |
| `api/routes/forensic.py` | 538 | 163 | **-70%** |
| `api/routes/api_catalog.py` | 576 | 113 | **-80%** |
| `api/routes/tls_admin.py` | 442 | 207 | **-53%** |
| `api/routes/companies_admin_v2.py` | 444 | 159 | **-64%** |
| `api/routes/bot_callbacks.py` | 564 | 245 | **-57%** |
| `api/routes/attachments.py` | 715 | 346 | **-52%** |
| `api/routes/credit_scenario.py` | 865 | 318 | **-63%** |
| `api/routes/finmodel.py` | 991 | 405 | **-59%** |
| `api/routes/company_library.py` | 1077 | 272 | **-75%** |
| `api/routes/admin_broadcasts.py` | 307 | 184 | **-40%** |
| `api/routes/credit_portfolio.py` | 1808 | 317 | **-82%** |
| `api/routes/auth_mfa.py` | 358 | 59 | **-83%** |
| `api/routes/rbac_v3.py` | 1516 | 379 | **-75%** |
| `api/routes/financials.py` | 3592 | 669 | **-81%** |
| `api/routes/auth.py` | 222 | 88 | **-60%** |
| `api/routes/mfa.py` | 406 | 172 | **-58%** |
| `api/routes/admin_mfa.py` | 217 | 42 | **-81%** |
| `api/routes/forgot_password.py` | 258 | 42 | **-84%** |
| `api/routes/user_search.py` | 87 | 30 | **-66%** |
| `api/routes/storage_admin.py` | 139 | 35 | **-75%** |
| `api/routes/company_activity.py` | 210 | 29 | **-86%** |
| `api/routes/invest_projects.py` | 231 | 79 | **-66%** |
| `api/routes/directions.py` | 263 | 73 | **-72%** |
| `api/routes/elasticity.py` | 267 | 138 | **-48%** |
| `api/routes/webhooks.py` | 279 | 165 | **-41%** |
| `api/routes/audit.py` | 284 | 104 | **-63%** |
| `api/routes/db_admin.py` | 630 | 103 | **-84%** |
| **Всего:** | **28 978** | **11 761** | **-59%** |

**financials.py refactor завершён полностью** — 6 service-папок:
- Reports CRUD → `services/financials_reports/`
- Portfolio summary → `services/financials_portfolio/`
- HLF (import/get/save) → `services/financials_hlf/`
- NSBU editor → `services/financials_nsbu/`
- IFRS editor + ifrs-nsbu-diff → `services/financials_ifrs/`
- Detailed Excel (8 endpoints) → `services/financials_detailed/`

Что появилось:
- `repositories/` — 24 файла
- `services/` — 31 service-класс в 24 пакетах
- `services/{procurement,tasks,projects,governance,esg,exec_dashboard,consultants,dashboard}/_helpers.py` — чистые функции
- `dependencies/` — 25 файлов (включая uow.py)
- `uow/{ports,impl}.py` — UoW pattern (24 repositories)

**Дополнительные core services не тронуты:**
- `app/services/api_key_service.py` — create/revoke + key verification (auth middleware). ApiKeysAdminService делегирует к нему.
- `app/services/admin_broadcast_service.py` — компоновка рассылок (если будет рефакторено позже).

**Дополнительно к ранее упомянутым core services:**
- `app/services/bp_kpi_helpers.py` (bp_compute / bp_attention_issues / sector_*/kpi_attention_issues) — формулы, разделяемые между BP и KPI. BpService и KpiService делегируют сюда.
- `app/api/routes/_pack4_blocks.py` + `_pack5_blocks.py` + `_pack4_drill.py` — sub-block builders (directions/governance/standards + economic_effect/bp_tracker/tax_contribution + direction drill). ExecDashboardService делегирует сюда.

**Note on core services не тронуто:**
- `app/services/moderation_service.py` (gate_or_apply / approve / reject state machine) — критичный core, используемый всеми routes. Refactor добавил `moderation_admin/` (dashboard + rules CRUD + user flags).
- `app/services/notifications_service.py` (notify/broadcast/mark_read/archive/ws_manager) — рассылка уведомлений из всех модулей. Refactor добавил `notifications_admin/` (feed + preferences + types catalog + get_one).
- `app/services/external_api_service.py` (validate_openapi/extract_*/count_endpoints) — OpenAPI парсер. ExternalApisService делегирует к нему.

## Recipe: как мигрировать новый module за 4 шага

### Шаг 1 — Repository

`backend/app/repositories/{module}_repository.py`:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

class FooRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_foos(self, *, year: int) -> list[Foo]:
        res = await self.session.execute(
            select(Foo).where(Foo.year == year)
        )
        return list(res.scalars().all())

    async def get_foo(self, foo_id: UUID) -> Foo | None: ...
    def add(self, obj) -> None: self.session.add(obj)
    async def flush(self) -> None: await self.session.flush()
    async def refresh(self, obj) -> None: await self.session.refresh(obj)
```

**Конвенции:**
- Никакого `HTTPException` (None → service решает)
- Никакого commit/rollback (это UoW.__aexit__)
- Type hints для всего

### Шаг 2 — Зарегистрировать в UoW

`backend/app/uow/impl.py`:
```python
from app.repositories.foo_repository import FooRepository

class UnitOfWork(UnitOfWorkABC):
    async def __aenter__(self):
        self._session = self._session_factory()
        self.foo = FooRepository(self._session)
        ...
```

`backend/app/uow/ports.py`:
```python
if TYPE_CHECKING:
    from app.repositories.foo_repository import FooRepository

class UnitOfWorkABC(ABC):
    foo: "FooRepository"
```

### Шаг 3 — Service(s)

Малый module → один `FooService`. Большой module → разделить:
- `query_service.py` — read-only use cases
- `editor_service.py` — мутации

```python
# backend/app/services/foo/query_service.py
from app.uow.ports import UnitOfWorkABC

class FooQueryService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def list_foos(self, year: int) -> FooListResponse:
        async with self.uow:
            foos = await self.uow.foo.list_foos(year=year)
            # ... pure aggregation logic if needed
        return FooListResponse(items=foos)
```

```python
# backend/app/services/foo/editor_service.py
class FooEditorService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def upsert_foo(self, payload: FooUpsert) -> Foo:
        async with self.uow:
            foo = Foo(...)
            self.uow.foo.add(foo)
            await self.uow.foo.flush()
            await self.uow.foo.refresh(foo)
        return foo
```

### Шаг 4 — Dependencies + thin route

`backend/app/dependencies/foo.py`:
```python
from typing import Annotated
from fastapi import Depends
from app.dependencies.uow import UowDep
from app.services.foo.query_service import FooQueryService

def get_foo_query_service(uow: UowDep) -> FooQueryService:
    return FooQueryService(uow=uow)

FooQueryServiceDep = Annotated[FooQueryService, Depends(get_foo_query_service)]
```

`backend/app/api/routes/foo.py` (thin shim):
```python
@router.get("/foos", response_model=FooListResponse)
async def list_foos(
    service: FooQueryServiceDep,
    year: int = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not await has_effective_permission(db, user, "foo.view"):
        raise HTTPException(403, "foo.view required")
    return await service.list_foos(year=year)
```

### Шаг 5 — Verify

```bash
docker restart uza-backend
docker logs uza-backend --tail 20 | grep -E "ERROR|Traceback|app.api.routes.foo"
# Должно быть: [OK] app.api.routes.foo
```

Затем smoke-test через `backend/_probe_*.py` template.

## Side-effects (notifications, broadcasts, moderation gate)

Делаются **в route файле ПОСЛЕ commit'а**:

```python
@router.put("/things/{id}")
async def update_thing(
    id: UUID,
    payload: ThingUpdate,
    service: ThingEditorServiceDep,
    ...
):
    # 1. Pre-conditions (HTTP concern)
    await _require(db, user, "thing.edit")

    # 2. Moderation gate (intercepts с 202 if queued)
    queued, sub = await gate_or_apply(...)
    if queued:
        return JSONResponse(status_code=202, content={"queued": True, "submission_id": str(sub.id)})

    # 3. Atomic mutation (service)
    thing, info = await service.update_thing(id, payload)

    # 4. Post-commit side-effects (best-effort)
    if info["assignee_changed"]:
        await notify_task_assignment(db, task=thing, ...)

    return await service.hydrate_detail(thing)
```

## Roadmap: оставшиеся модули

Приоритизированы по **soft impact** (как часто юзается / насколько критичен) и **complexity** (effort).

### Done ✅
- ~~projects.py (627→181, -71%)~~
- ~~governance.py (641→207, -68%)~~
- ~~ratings.py (381→213, -44%)~~
- ~~notes.py (361→139, -61%)~~
- ~~esg.py (969→212, -78%)~~ — split overview_service + editor_service + company_service
- ~~moderation.py (596→371, -38%)~~ — split: route delegates queue/rules/users to moderation_admin/; state transitions stay on existing core moderation_service.py
- ~~notifications.py (425→285, -33%)~~ — feed/prefs/types/get_one through notifications_admin/; WS handler stays inline
- ~~partners.py (264→97, -63%)~~
- ~~external_apis.py (239→112, -53%)~~ — delegates OpenAPI parsing to existing core external_api_service.py
- ~~system_config.py (332→118, -64%)~~ — audit-chain writes stay in route (post-commit)

### Skipped
- **invest_projects.py** (231) — non-standard raw `text()` SQL JSONB doc store, refactor overhead > value

### Medium impact

| Module | LOC | Effort | Notes |
|---|---:|---:|---|
| `rbac_v3.py` | 1 516 | 3 ч | 4 sub-services (overview, roles, users, groups). 30+ endpoints. Сложно. Можно одной сессией |
| `notifications.py` | 425 | 45 мин | WS + DB rows |
| `mfa.py` | 406 | 45 мин | TOTP secrets, recovery codes |
| `system_config.py` | 332 | 30 мин | YearRegistry / sector seed |
| `partners.py` | 264 | 25 мин | |
| `external_apis.py` | 239 | 25 мин | |

### Large (split required)

| Module | LOC | Effort | Approach |
|---|---:|---:|---|
| **financials.py** | **3 592** | **multi-session (6+ часов)** | Split на **6 подмодулей**: `reports/`, `detailed/`, `portfolio/`, `nsbu_editor/`, `ifrs_editor/`, `hlf_import/`. Каждый = одна Sprint. Дополнительно `hlf_parser` стоит вынести в `clients/` (это Excel-парсер, не бизнес-логика) |

### Small (skip — overhead > value)

| Module | LOC | Decision |
|---|---:|---|
| `metrics.py` | 63 | Skip |
| `tg_banners.py` | 68 | Skip |
| `user_search.py` | 87 | Skip |
| `storage_admin.py` | 139 | Skip |
| `health.py` | 175 | Skip |

## Anti-patterns to avoid

1. **Не помещай SQL queries в services** — query через `self.uow.foo.method()`, никогда `select(...)` напрямую
2. **Не помещай HTTPException в repositories** — None / `raise ValueError` → service конвертирует в HTTPException
3. **Не делай `await db.commit()` в services** — это UoW.__aexit__'s работа. Service может вызвать `await self.uow.commit()` если нужен mid-transaction commit
4. **Не делай ports/ABC для одной реализации** — `UnitOfWorkABC` оправдан (есть тестовый FakeUoW). Для services с одной реализацией — concrete class
5. **Не разбивай слишком мелко** — для модуля с 3 endpoints одного `FooService` достаточно. Query+Editor split начинай с 6+ endpoints

## Testing pattern (TODO — Sprint B)

Когда придёт время unit-тестам:

```python
# tests/services/test_kpi_query_service.py
from app.uow.ports import UnitOfWorkABC

class FakeKpiRepository:
    """In-memory test double."""
    def __init__(self, managers): self._managers = managers
    async def get_summary_managers(self, year, scope_company_ids=None):
        return [m for m in self._managers if m.year == year]

class FakeUnitOfWork(UnitOfWorkABC):
    def __init__(self, **repos):
        self.kpi = repos.get('kpi')
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def commit(self): pass
    async def rollback(self): pass
    async def flush(self): pass

async def test_compute_summary_p1():
    uow = FakeUnitOfWork(kpi=FakeKpiRepository(managers=[fixture_mgrs]))
    service = KpiQueryService(uow)
    summary = await service.compute_summary(2026, "q1")
    assert summary.overall == pytest.approx(97.1, rel=0.01)
```

## When to apply this pattern

**DO refactor** when:
- Route file > 300 LOC
- Multiple endpoints share queries → repo pulls them together
- Bug-fixing requires changing 3+ files simultaneously
- Plan to write tests
- Bringing new dev on board

**DO NOT refactor** when:
- Route < 200 LOC and stable
- Module is being deleted soon
- Just for "aesthetic cleanliness" without actual pain

---

**Last updated:** 2026-05-25 by initial 10-layer pilot (sessions 1-2).
**Reference:** `fastapi-structure.zip` template (in `~/Downloads/`).
