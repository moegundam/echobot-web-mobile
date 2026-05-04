from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import channel_config_payload
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["channels"])


@router.get("/channels/definitions")
async def get_channel_definitions(runtime=Depends(get_app_runtime)) -> list[dict[str, Any]]:
    return runtime.channel_service.get_definitions()


@router.get("/channels/config")
async def get_channel_config(runtime=Depends(get_app_runtime)) -> dict[str, Any]:
    config = await runtime.channel_service.get_config()
    return channel_config_payload(config)


@router.put("/channels/config")
async def update_channel_config(
    raw_config: dict[str, Any],
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        updated = await runtime.channel_service.update_config(raw_config)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return channel_config_payload(updated)


@router.get("/channels/status")
async def get_channel_status(runtime=Depends(get_app_runtime)) -> dict[str, dict[str, bool]]:
    return await runtime.channel_service.get_status()


@router.get("/channels/stage-targets")
async def get_channel_stage_targets(runtime=Depends(get_app_runtime)) -> dict[str, Any]:
    return await runtime.channel_service.get_stage_targets()


@router.post("/channels/{channel_name}/smoke")
async def smoke_channel(
    channel_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    try:
        return await runtime.channel_service.smoke_channel(channel_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown channel") from exc
