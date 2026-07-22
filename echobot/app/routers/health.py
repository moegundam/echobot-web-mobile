from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import AccessRole
from ..services.access_projection import project_health_payload
from ..state import get_app_runtime, get_request_access_role


router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health(
    runtime=Depends(get_app_runtime),
    access_role: AccessRole = Depends(get_request_access_role),
) -> dict[str, object]:
    payload = await runtime.health_snapshot()
    return project_health_payload(payload, access_role)
