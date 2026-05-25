"""FastAPI DI providers — factories для services + UoW.

Pattern: `@router.get("/x")` → `async def x(svc: KpiQueryServiceDep) → ...`
Не загромождает route handlers `Depends(...)`-вызовами вручную.
"""
