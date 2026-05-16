"""Directions — lookup endpoint for dropdowns/filters."""
from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import _has_permission
from app.models.company import Direction
from app.models.user import User


router = APIRouter(prefix="/directions", tags=["directions"])


_DIR_COLORS = {
    "strategy": "#1e2787", "finance": "#D97706", "procurement": "#3B6D11",
    "orgdev": "#534AB7", "digital": "#1D9E75", "operations": "#EF4444",
    "governance": "#72243E", "esg": "#1D9E75", "pr": "#D4537E",
    "pmo": "#2563EB", "analytics": "#7C3AED",
}


@router.get("")
async def list_directions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _has_permission(user, "tasks.view"):
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, "tasks.view required")
    res = await db.execute(
        select(Direction).order_by(Direction.sort_order, Direction.name_ru)
    )
    rows = res.scalars().all()
    return {
        "directions": [
            {
                "id": str(d.id),
                "code": d.code,
                "label": d.name_ru,
                "color": _DIR_COLORS.get(d.code, "#7F77DD"),
                "sort_order": d.sort_order,
                "is_custom": getattr(d, "is_custom", False),
            }
            for d in rows
        ]
    }
