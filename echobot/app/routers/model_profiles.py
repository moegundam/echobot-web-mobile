from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import (
    CreateModelProfileRequest,
    ModelProfileModel,
    ModelProfilesResponse,
    UpdateModelProfileRequest,
)
from ..state import get_app_runtime


router = APIRouter(tags=["model-profiles"])


@router.get("/model-profiles", response_model=ModelProfilesResponse)
async def list_model_profiles(runtime=Depends(get_app_runtime)) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    return ModelProfilesResponse(**payload)


@router.post("/model-profiles", response_model=ModelProfileModel)
async def create_model_profile(
    request: CreateModelProfileRequest,
    runtime=Depends(get_app_runtime),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.create_profile,
            label=request.label,
            source_profile_id=request.source_profile_id,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfileModel(**payload)


@router.get("/model-profiles/{profile_id}", response_model=ModelProfileModel)
async def get_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.get_profile,
            profile_id,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfileModel(**payload)


@router.patch("/model-profiles/{profile_id}", response_model=ModelProfileModel)
async def update_model_profile(
    profile_id: str,
    request: UpdateModelProfileRequest,
    runtime=Depends(get_app_runtime),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.update_profile,
            profile_id,
            request.model_dump(exclude_unset=True),
        )
        state = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
        if state["active_profile_id"] == payload["profile_id"]:
            runtime_payload = await asyncio.to_thread(
                runtime.model_profile_service.get_profile_for_runtime,
                profile_id,
            )
            await runtime.apply_model_profile(runtime_payload)
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfileModel(**payload)


@router.post("/model-profiles/{profile_id}/activate", response_model=ModelProfilesResponse)
async def activate_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.activate_profile,
            profile_id,
        )
        active_profile = await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            payload["active_profile_id"],
        )
        await runtime.apply_model_profile(active_profile)
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfilesResponse(**payload)


def _ensure_model_profiles_ready(runtime) -> None:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")


def _model_profile_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "unknown model profile" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)
