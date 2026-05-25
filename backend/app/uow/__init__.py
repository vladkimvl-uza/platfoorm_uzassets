"""Unit of Work layer — transactional boundary for service-layer operations.

Pattern from `fastapi-structure` 10-layer template (2026-05-25 audit):
service → `async with uow: ... repo.method() ...` → uow.commit() / rollback().
"""
from app.uow.impl import UnitOfWork
from app.uow.ports import UnitOfWorkABC

__all__ = ["UnitOfWork", "UnitOfWorkABC"]
