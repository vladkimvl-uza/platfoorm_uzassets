"""Credit-portfolio apply handler (deny-by-default Phase 4).

Применяет одобренную правку кредитного портфеля. В отличие от большинства
модулей, credit гейтится на СЕРВИСНОМ слое (CreditPortfolioService), зеркаля
financials_reports.save_report: разрешение автора и scope живут ВНУТРИ сервиса.
Поэтому apply переигрывает те же 8 write-методов сервиса от имени АВТОРА
(proposer) с `_skip_gate=True` — гейт на выкате не срабатывает повторно, а
доменная запись (created_by/updated_by, аудит, пересчёт долга) атрибутируется
автору ровно так же, как при прямой записи.

Сервис работает на СВОЕЙ UoW/сессии (UnitOfWork(AsyncSessionLocal)), отдельной
от сессии модерации `db` — как scenarios/companies. Поэтому create снабжён
idempotency-guard'ом: повторное применение (retry после сбоя) не плодит дубль.

ДИСКРИМИНАТОР: восемь методов сворачиваются в три action (create/edit/delete),
поэтому в proposed_value несём служебный ключ `_op` (loan|payment|fx|bulk):
  create + _op=loan     → create_loan
  create + _op=bulk     → bulk_import
  create + _op=payment  → create_loan_payment      (payload несёт loan_id)
  edit   + _op=loan     → update_loan               (payload несёт loan_id)
  edit   + _op=fx       → upsert_fx_rate
  edit   + _op=payment  → update_payment            (payload несёт payment_id)
  delete + _op=loan     → delete_loan               (payload несёт loan_id)
  delete + _op=payment  → delete_payment            (payload несёт payment_id)

Компания заявки лежит в `target_company_id` (loan/payment-операции) или пуста
(fx/bulk — глобальные/многокомпанийные), поэтому маппинг в
`_effective_company_id` НЕ нужен: scope на resolve резолвится напрямую.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.credit import CreditPortfolioLoan, CreditPortfolioPayment
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.schemas.credit_portfolio import (
    BulkImportRequest,
    FxRateUpsert,
    LoanCreate,
    LoanUpdate,
    PaymentCreate,
    PaymentUpdate,
)
from app.services.credit_portfolio.service import CreditPortfolioService
from app.services.moderation_service import register_apply_handler
from app.uow.impl import UnitOfWork


def _service() -> CreditPortfolioService:
    return CreditPortfolioService(uow=UnitOfWork(session_factory=AsyncSessionLocal))


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value or {})
    op = str(pv.pop("_op", "") or "")

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    if proposer is None:
        raise ValueError("proposer user no longer exists")

    service = _service()

    # ─── create ───────────────────────────────────────────────────────
    if action in ("create", "created"):
        if op == "bulk":
            payload = BulkImportRequest.model_validate(pv)
            res = await service.bulk_import(payload, proposer, _skip_gate=True)
            return {"action": "create", "op": "bulk",
                    "inserted": res.inserted, "updated": res.updated,
                    "skipped": res.skipped}

        if op == "loan":
            loan_code = str(pv.get("loan_code") or "")
            # Идемпотентность: кредит с таким loan_code уже создан (retry или
            # прошлый частичный apply) — не плодим дубль, застолбим id.
            existing = (await db.execute(
                select(CreditPortfolioLoan.id).where(
                    CreditPortfolioLoan.loan_code == loan_code
                )
            )).scalar_one_or_none()
            if existing is not None:
                sub.target_entity_id = str(existing)
                return {"action": "create", "op": "loan",
                        "loan_id": str(existing), "idempotent": True}
            payload = LoanCreate.model_validate(pv)
            res = await service.create_loan(payload, proposer, _skip_gate=True)
            sub.target_entity_id = str(res.id)  # застолбить id (коммитит _dispatch_apply)
            return {"action": "create", "op": "loan", "loan_id": str(res.id),
                    "loan_code": loan_code}

        if op == "payment":
            loan_id = UUID(str(pv.pop("loan_id")))
            # Идемпотентность: если прошлый apply уже создал платёж и застолбил
            # его id в target_entity_id, повтор НЕ создаёт дубль.
            if sub.target_entity_id:
                try:
                    pid = UUID(str(sub.target_entity_id))
                except Exception:
                    pid = None
                if pid is not None:
                    exists = (await db.execute(
                        select(CreditPortfolioPayment.id).where(
                            CreditPortfolioPayment.id == pid
                        )
                    )).scalar_one_or_none()
                    if exists is not None:
                        return {"action": "create", "op": "payment",
                                "payment_id": str(pid), "idempotent": True}
            payload = PaymentCreate.model_validate(pv)
            res = await service.create_loan_payment(
                loan_id, payload, proposer, _skip_gate=True
            )
            sub.target_entity_id = str(res.id)  # застолбить id платежа
            return {"action": "create", "op": "payment",
                    "payment_id": str(res.id), "loan_id": str(loan_id)}

        raise ValueError(f"unknown credit create op: {op!r}")

    # ─── edit ─────────────────────────────────────────────────────────
    if action in ("edit", "update"):
        if op == "loan":
            loan_id = UUID(str(pv.pop("loan_id")))
            payload = LoanUpdate.model_validate(pv)
            await service.update_loan(loan_id, payload, proposer, _skip_gate=True)
            return {"action": "edit", "op": "loan", "loan_id": str(loan_id)}

        if op == "fx":
            payload = FxRateUpsert.model_validate(pv)
            res = await service.upsert_fx_rate(payload, proposer, _skip_gate=True)
            return {"action": "edit", "op": "fx", "fx_id": str(res.id)}

        if op == "payment":
            payment_id = UUID(str(pv.pop("payment_id")))
            payload = PaymentUpdate.model_validate(pv)
            await service.update_payment(payment_id, payload, proposer, _skip_gate=True)
            return {"action": "edit", "op": "payment", "payment_id": str(payment_id)}

        raise ValueError(f"unknown credit edit op: {op!r}")

    # ─── delete ───────────────────────────────────────────────────────
    if action in ("delete", "deleted", "archived"):
        if op == "loan":
            loan_id = UUID(str(pv.pop("loan_id")))
            await service.delete_loan(loan_id, proposer, _skip_gate=True)
            return {"action": "delete", "op": "loan", "loan_id": str(loan_id)}

        if op == "payment":
            payment_id = UUID(str(pv.pop("payment_id")))
            await service.delete_payment(payment_id, proposer, _skip_gate=True)
            return {"action": "delete", "op": "payment", "payment_id": str(payment_id)}

        raise ValueError(f"unknown credit delete op: {op!r}")

    raise ValueError(f"unknown credit action: {action!r}")


register_apply_handler("credit", apply)
