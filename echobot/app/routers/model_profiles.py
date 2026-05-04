from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import (
    CreateModelProfileRequest,
    ModelProfileModel,
    ModelProfilesResponse,
    SetRoleModelProfileBindingRequest,
    UpdateModelProfileRequest,
)
from ..state import get_app_runtime, require_admin_user


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
    _admin_user: str = Depends(require_admin_user),
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


@router.get("/model-profiles/role-bindings", response_model=dict[str, str])
async def list_model_profile_role_bindings(
    runtime=Depends(get_app_runtime),
) -> dict[str, str]:
    _ensure_model_profiles_ready(runtime)
    payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    return dict(payload.get("role_bindings", {}))


@router.put(
    "/model-profiles/role-bindings/{role_name}",
    response_model=ModelProfilesResponse,
)
async def set_model_profile_role_binding(
    role_name: str,
    request: SetRoleModelProfileBindingRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    normalized_role_name = await _require_existing_role(runtime, role_name)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.set_role_binding,
            normalized_role_name,
            request.profile_id,
        )
        payload = await _activate_binding_for_current_role(
            runtime,
            normalized_role_name,
            request.profile_id,
            payload,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfilesResponse(**payload)


@router.delete(
    "/model-profiles/role-bindings/{role_name}",
    response_model=ModelProfilesResponse,
)
async def clear_model_profile_role_binding(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    normalized_role_name = await _require_existing_role(runtime, role_name)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.clear_role_binding,
            normalized_role_name,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfilesResponse(**payload)


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
    _admin_user: str = Depends(require_admin_user),
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
    _admin_user: str = Depends(require_admin_user),
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


@router.delete("/model-profiles/{profile_id}", response_model=ModelProfilesResponse)
async def delete_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.model_profile_service.delete_profile,
            profile_id,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    return ModelProfilesResponse(**payload)


def _ensure_model_profiles_ready(runtime) -> None:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")


async def _require_existing_role(runtime, role_name: str) -> str:
    if runtime.role_service is None:
        raise HTTPException(status_code=503, detail="Role service is not ready")
    try:
        role = await runtime.role_service.get_role(role_name)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "unknown role" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message) from exc
    return role.name


async def _activate_binding_for_current_role(
    runtime,
    role_name: str,
    profile_id: str,
    payload: dict[str, object],
) -> dict[str, object]:
    if runtime.session_service is None or runtime.context is None:
        return payload

    current_session = await runtime.session_service.load_current_session()
    current_role_name = await runtime.context.coordinator.current_role_name(
        current_session.name,
    )
    if current_role_name != role_name:
        return payload

    activated = await asyncio.to_thread(
        runtime.model_profile_service.activate_profile,
        profile_id,
    )
    active_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        activated["active_profile_id"],
    )
    await runtime.apply_model_profile(active_profile)
    return activated


def _model_profile_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "unknown model profile" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)
