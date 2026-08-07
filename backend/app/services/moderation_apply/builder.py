"""Builder apply handler (deny-by-default Phase 4).

Применяет одобренные заявки массового заведения из Конструктора / ИИ-импорта.
Три вида, различаемых по ``proposed_value["kind"]``:
  - "projects_tasks" — зеркалит POST /builder/bulk (проекты+задачи в N компаний)
  - "kpi"            — зеркалит POST /builder/bulk-kpi (пачка KPI-индикаторов)
  - "financials"     — зеркалит POST /builder/bulk-financials (пачка фин-строк)

Все три — ИИ-ingest bypass-путь: раньше писали в БД напрямую (только глобальное
право + scope автора), МИНУЯ модерацию. Хендлер ПОВТОРЯЕТ ровно ту же persist-
логику builder-сервисов, что и живой роут, но атрибутированно ПРЕДЛОЖИВШЕМУ
(proposer). Он СОЗНАТЕЛЬНО не маршрутизирует в kpi/financials apply-хендлеры:
у них другой payload-shape (KpiCompanyYearUpsert / FinancialReportSavePayload),
а builder несёт СЫРОЙ ИИ-распознанный ввод (имена компаний строками) — его надо
переразрешить и провести через builder.bulk_add_* / editor-сервисы.

Submission shape:
  target_module    = "builder"
  action           = "create"
  target_company_id = единственная компания заявки (если ровно одна) либо None
  proposed_value   = {"kind": <...>, ...<model_dump исходного тела запроса>...}

Атрибуция: автор — ПРЕДЛОЖИВШИЙ (creator_id / user_id проектов, задач, KPI,
фин-строк ведут к нему), а не модератор, нажавший «принять».

NB (неатомарность): bulk пишет в НЕСКОЛЬКО отдельных сессий (projects/tasks/kpi
идут через свою UoW и коммитят по ходу). Если apply упадёт на середине, уже
записанные сущности НЕ откатятся, а повтор из очереди создаст их заново —
ровно как у живого роута (тот тоже не транзакционен по всему bulk).
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.financials_reports.service import FinancialsReportsService
from app.services.kpi.editor_service import KpiEditorService
from app.services.moderation_service import register_apply_handler
from app.services.projects.editor_service import ProjectsEditorService
from app.services.tasks.editor_service import TasksEditorService
from app.uow.impl import UnitOfWork


def _uow() -> UnitOfWork:
    return UnitOfWork(session_factory=AsyncSessionLocal)


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    pv = dict(sub.proposed_value)
    kind = str(pv.get("kind") or "").strip()

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user

    if kind == "projects_tasks":
        return await _apply_projects_tasks(db, pv, author)
    if kind == "kpi":
        return await _apply_kpi(db, pv, author)
    if kind == "financials":
        return await _apply_financials(db, pv, author)
    raise ValueError(f"unknown builder kind: {kind!r}")


# ─── projects_tasks (mirror POST /builder/bulk) ────────────────────

async def _apply_projects_tasks(db, pv: dict, author: User) -> dict:
    # Ленивый импорт роут-модуля (схемы + хелперы) — избегаем циклического
    # импорта на этапе регистрации хендлеров.
    from app.api.routes import builder as R
    from app.schemas.project import ProjectCreate
    from app.schemas.task import TaskCreate

    body = R.BulkRequest.model_validate({k: v for k, v in pv.items() if k != "kind"})
    c = body.common
    targets = body.company_ids or [None]

    projects_svc = ProjectsEditorService(uow=_uow())
    tasks_svc = TasksEditorService(uow=_uow())

    proj_n = 0
    task_n = 0
    pending_comments: list[tuple[str, UUID, str]] = []

    def _stash(kind_: str, pid: UUID, text) -> None:
        t = (text or "").strip()
        if t:
            pending_comments.append((kind_, pid, t[:5000]))

    for cid in targets:
        for p in body.projects:
            pc = ProjectCreate(
                title=p.title, status=p.status, priority=p.priority,
                company_id=cid, portfolio_year=c.portfolio_year, board_id=c.board_id,
                direction_id=R._pick(p.direction_id, c.direction_id),
                due_date=R._pick(p.due_date, c.due_date),
            )
            pid = await projects_svc.create_project_id(pc, creator_id=author.id)
            proj_n += 1
            _stash("project", pid, p.comment)
            for t in p.tasks:
                tc = TaskCreate(
                    title=t.title, status=t.status, priority=t.priority,
                    company_id=cid, project_id=pid, portfolio_year=c.portfolio_year,
                    board_id=c.board_id,
                    direction_id=R._pick(t.direction_id, p.direction_id, c.direction_id),
                    due_date=R._pick(t.due_date, c.due_date),
                    assignee_email=t.assignee_email,
                )
                created, _ = await tasks_svc.create_task(tc, creator_id=author.id)
                task_n += 1
                _stash("task", created.id, t.comment)

        for t in body.standalone_tasks:
            tc = TaskCreate(
                title=t.title, status=t.status, priority=t.priority,
                company_id=cid, portfolio_year=c.portfolio_year, board_id=c.board_id,
                direction_id=R._pick(t.direction_id, c.direction_id),
                due_date=R._pick(t.due_date, c.due_date),
                assignee_email=t.assignee_email,
            )
            created, _ = await tasks_svc.create_task(tc, creator_id=author.id)
            task_n += 1
            _stash("task", created.id, t.comment)

    comment_n = 0
    if pending_comments:
        from app.models.project import ProjectComment
        from app.models.task import TaskComment
        for k, pid, body_txt in pending_comments:
            if k == "task":
                db.add(TaskComment(task_id=pid, author_id=author.id, body=body_txt))
            else:
                db.add(ProjectComment(project_id=pid, author_id=author.id, body=body_txt))
            comment_n += 1
        await db.commit()

    return {
        "kind": "projects_tasks",
        "companies": len([t for t in targets if t is not None]) or 1,
        "projects_created": proj_n,
        "tasks_created": task_n,
        "comments_created": comment_n,
    }


# ─── kpi (mirror POST /builder/bulk-kpi) ───────────────────────────

async def _apply_kpi(db, pv: dict, author: User) -> dict:
    from app.api.routes import builder as R

    body = R.BulkKpiRequest.model_validate({k: v for k, v in pv.items() if k != "kind"})
    resolve = await R._company_resolver(db)

    grouped: dict[str, list[dict]] = {}
    unresolved: list[str] = []
    for row in body.rows:
        if not str(row.indicator or "").strip():
            continue
        cid = resolve(row.company)
        if cid is None:
            if str(row.company or "").strip():
                unresolved.append(row.company)
            continue
        grouped.setdefault(cid, []).append({
            "name": row.indicator, "unit": row.unit,
            "weight": row.weight, "plan": row.plan, "fact": row.fact,
        })

    if not grouped:
        raise ValueError(
            "builder kpi apply: не удалось сопоставить ни одну компанию из заявки "
            "(состав компаний мог измениться после подачи)",
        )

    kpi_svc = KpiEditorService(uow=_uow())
    total_ind = 0
    for cid, inds in grouped.items():
        res = await kpi_svc.bulk_add_indicators(UUID(cid), body.year, body.manager_title, inds)
        total_ind += res["indicators_added"]

    return {
        "kind": "kpi",
        "companies": len(grouped),
        "indicators_created": total_ind,
        "unresolved": sorted(set(unresolved)),
    }


# ─── financials (mirror POST /builder/bulk-financials) ─────────────

async def _apply_financials(db, pv: dict, author: User) -> dict:
    from app.api.routes import builder as R

    body = R.BulkFinRequest.model_validate({k: v for k, v in pv.items() if k != "kind"})
    resolve = await R._company_resolver(db)
    std_ok = {"IFRS", "NSBU"}
    rt_ok = {"PL", "BS", "CF"}

    rows: list[dict] = []
    unresolved: list[str] = []
    for row in body.rows:
        if not str(row.article or "").strip():
            continue
        cid = resolve(row.company)
        if cid is None:
            if str(row.company or "").strip():
                unresolved.append(row.company)
            continue
        std = str(row.standard or "").strip().upper() or body.default_standard
        std = std if std in std_ok else body.default_standard
        rt = str(row.report_type or "").strip().upper() or body.default_report_type
        rt = rt if rt in rt_ok else body.default_report_type
        try:
            yr = int(str(row.year or "").strip() or body.default_year)
        except (TypeError, ValueError):
            yr = body.default_year
        rows.append({
            "company_id": UUID(cid),
            "year": yr,
            "quarter": None,
            "standard": std,
            "report_type": rt,
            "currency": str(row.currency or "").strip().upper() or body.default_currency,
            "unit_scale": 1_000_000_000,
            "article": row.article,
            "value": R._to_decimal(row.value),
        })

    if not rows:
        raise ValueError(
            "builder financials apply: не удалось сопоставить ни одну компанию из "
            "заявки (состав компаний мог измениться после подачи)",
        )

    # bulk_add_lines сам проверит financials.edit у ПРЕДЛОЖИВШЕГО (author) и пишет
    # в переданную сессию db, коммитя доменную мутацию.
    fin_svc = FinancialsReportsService()
    res = await fin_svc.bulk_add_lines(rows, db, author)

    return {
        "kind": "financials",
        "reports": res["reports"],
        "lines_created": res["lines_added"],
        "unresolved": sorted(set(unresolved)),
    }


register_apply_handler("builder", apply)
