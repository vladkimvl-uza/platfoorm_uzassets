"""Health check and liveness probes."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app import __version__

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    """Liveness probe — always returns 200 if the app is running."""
    return {"status": "ok", "version": __version__}


@router.get("/ready")
async def ready(db: AsyncSession = Depends(get_db)):
    """Readiness probe — verifies DB connectivity."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "ready", "db": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB not ready: {e}")
