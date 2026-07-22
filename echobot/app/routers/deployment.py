from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..services.deployment_status import DeploymentStatusService
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["deployment"])


@router.get("/deployment/status")
async def get_deployment_status(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    return await DeploymentStatusService(runtime).snapshot()
