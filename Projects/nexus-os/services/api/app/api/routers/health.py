from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container
from app.schemas.health import HealthReport

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/ping")
async def ping() -> dict[str, bool]:
    """Unauthenticated liveness probe. Deliberately reveals nothing else."""
    return {"ok": True}


@router.get("", response_model=HealthReport)
async def health(c: Container) -> HealthReport:
    return await c.health.report()
