from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..auth import AccessRole
from ..schemas import (
    ChannelIntegrationsResponse,
    CreateRuntimeProfileRequest,
    LLMModelAdminModel,
    LLMModelsResponse,
    Live2DModelAdminModel,
    Live2DModelsResponse,
    SessionRuntimeContextResponse,
    UpdateLLMModelRequest,
    UpdateLive2DModelRequest,
    UpdateSessionRuntimeOverridesRequest,
    UpdateVoiceProfileRequest,
    VoiceProfileAdminModel,
    VoiceProfilesResponse,
)
from ..services.access_projection import project_session_runtime_context
from ..services.channel_owner_scope import channel_owner_scope
from ..services.session_runtime_context import (
    SessionRuntimeContextError,
    build_session_runtime_context,
    list_channel_integrations_for_runtime,
)
from ..services.runtime_catalog_application import RuntimeCatalogApplicationService
from ..services.runtime_context_events import notify_all_runtime_contexts_changed
from ..services.model_profile_compat import (
    live2d_catalog as compat_live2d_catalog,
)
from ..state import (
    get_app_runtime,
    get_request_access_role,
    require_admin_user,
    require_operator_user,
)


router = APIRouter(tags=["session-catalog"])


@router.get("/llm-models", response_model=LLMModelsResponse)
async def list_llm_models(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    return LLMModelsResponse(**await asyncio.to_thread(runtime.llm_model_service.list_models))


@router.post("/llm-models", response_model=LLMModelAdminModel)
async def create_llm_model(
    request: CreateRuntimeProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.llm_model_service.create_model,
            name=request.name,
            source_model_id=request.source_model_id or request.source_profile_id,
        )
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="llm_catalog_updated",
    )
    return LLMModelAdminModel(**payload)


@router.patch("/llm-models/{model_id}", response_model=LLMModelAdminModel)
async def update_llm_model(
    model_id: str,
    request: UpdateLLMModelRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.llm_model_service.update_model,
                model_id,
                request.model_dump(exclude_unset=True),
            )
            if model_id == await _active_llm_model_id(runtime):
                await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="llm_catalog_updated",
    )
    return LLMModelAdminModel(**payload)


@router.post("/llm-models/{model_id}/activate", response_model=LLMModelsResponse)
async def activate_llm_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.llm_model_service.activate_model,
                model_id,
            )
            await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="llm_catalog_updated",
    )
    return LLMModelsResponse(**payload)


@router.delete("/llm-models/{model_id}", response_model=LLMModelsResponse)
async def delete_llm_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await _runtime_catalog(runtime).delete_llm_model(model_id)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return LLMModelsResponse(**payload)


@router.get("/voice-models", response_model=VoiceProfilesResponse)
async def list_voice_models(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfilesResponse:
    _ensure_runtime_model_services_ready(runtime)
    return VoiceProfilesResponse(**await asyncio.to_thread(runtime.voice_model_service.list_profiles))


@router.post("/voice-models", response_model=VoiceProfileAdminModel)
async def create_voice_model(
    request: CreateRuntimeProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfileAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.voice_model_service.create_profile,
            name=request.name,
            source_profile_id=request.source_profile_id or request.source_model_id,
        )
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="voice_catalog_updated",
    )
    return VoiceProfileAdminModel(**payload)


@router.patch("/voice-models/{profile_id}", response_model=VoiceProfileAdminModel)
async def update_voice_model(
    profile_id: str,
    request: UpdateVoiceProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfileAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.voice_model_service.update_profile,
                profile_id,
                request.model_dump(exclude_unset=True),
            )
            if profile_id == await _active_voice_profile_id(runtime):
                await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="voice_catalog_updated",
    )
    return VoiceProfileAdminModel(**payload)


@router.post("/voice-models/{profile_id}/activate", response_model=VoiceProfilesResponse)
async def activate_voice_model(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfilesResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.voice_model_service.activate_profile,
                profile_id,
            )
            await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="voice_catalog_updated",
    )
    return VoiceProfilesResponse(**payload)


@router.delete("/voice-models/{profile_id}", response_model=VoiceProfilesResponse)
async def delete_voice_model(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfilesResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await _runtime_catalog(runtime).delete_voice_profile(profile_id)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return VoiceProfilesResponse(**payload)


@router.get("/live2d-models", response_model=Live2DModelsResponse)
async def list_live2d_models(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> Live2DModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    catalog = await _live2d_catalog(runtime)
    return Live2DModelsResponse(
        **await asyncio.to_thread(runtime.live2d_model_service.list_models, catalog),
    )


@router.post("/live2d-models", response_model=Live2DModelAdminModel)
async def create_live2d_model(
    request: CreateRuntimeProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> Live2DModelAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    catalog = await _live2d_catalog(runtime)
    try:
        payload = await asyncio.to_thread(
            runtime.live2d_model_service.create_model,
            name=request.name,
            source_model_id=request.source_model_id or request.source_profile_id,
            catalog=catalog,
        )
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_catalog_updated",
    )
    return Live2DModelAdminModel(**payload)


@router.patch("/live2d-models/{model_id}", response_model=Live2DModelAdminModel)
async def update_live2d_model(
    model_id: str,
    request: UpdateLive2DModelRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> Live2DModelAdminModel:
    _ensure_runtime_model_services_ready(runtime)
    catalog = await _live2d_catalog(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.live2d_model_service.update_model,
                model_id,
                request.model_dump(exclude_unset=True),
                catalog=catalog,
            )
            if model_id == await _active_live2d_model_id(runtime):
                await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_catalog_updated",
    )
    return Live2DModelAdminModel(**payload)


@router.post("/live2d-models/{model_id}/activate", response_model=Live2DModelsResponse)
async def activate_live2d_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> Live2DModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    catalog = await _live2d_catalog(runtime)
    try:
        async with _model_profile_lock(runtime):
            payload = await asyncio.to_thread(
                runtime.live2d_model_service.activate_model,
                model_id,
                catalog,
            )
            await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    await notify_all_runtime_contexts_changed(
        runtime,
        reason="live2d_catalog_updated",
    )
    return Live2DModelsResponse(**payload)


@router.delete("/live2d-models/{model_id}", response_model=Live2DModelsResponse)
async def delete_live2d_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> Live2DModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    catalog = await _live2d_catalog(runtime)
    try:
        payload = await _runtime_catalog(runtime).delete_live2d_model(
            model_id,
            catalog,
        )
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return Live2DModelsResponse(**payload)


@router.get("/channel-integrations", response_model=ChannelIntegrationsResponse)
async def list_channel_integrations(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ChannelIntegrationsResponse:
    try:
        integrations = await list_channel_integrations_for_runtime(runtime)
    except SessionRuntimeContextError as exc:
        raise _session_runtime_context_http_exception(exc) from exc
    return ChannelIntegrationsResponse(integrations=integrations)


@router.post("/channel-integrations/{integration_id}/smoke")
async def smoke_channel_integration(
    integration_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    scope = _channel_owner_scope_or_503(runtime)
    try:
        return await scope.service.smoke_channel(integration_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown channel integration") from exc


@router.get(
    "/sessions/{session_name}/runtime-context",
    response_model=SessionRuntimeContextResponse,
)
async def get_session_runtime_context(
    session_name: str,
    request: Request,
    response: Response,
    runtime=Depends(get_app_runtime),
    access_role: AccessRole = Depends(get_request_access_role),
) -> SessionRuntimeContextResponse | Response:
    context = await _session_runtime_context_response(runtime, session_name, access_role)
    etag = _runtime_context_etag(context.revision, access_role)
    headers = _runtime_context_cache_headers(etag)
    if _if_none_match(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return context


@router.put(
    "/sessions/{session_name}/runtime-overrides",
    response_model=SessionRuntimeContextResponse,
)
async def update_session_runtime_overrides(
    session_name: str,
    request: UpdateSessionRuntimeOverridesRequest,
    runtime=Depends(get_app_runtime),
    _operator_user: str = Depends(require_operator_user),
    access_role: AccessRole = Depends(get_request_access_role),
) -> SessionRuntimeContextResponse:
    override_payload = request.model_dump(
        mode="json",
        exclude_none=True,
        exclude_defaults=True,
    )
    _validate_runtime_override_access(
        override_payload,
        access_role is AccessRole.ADMIN,
    )
    try:
        resolved_session_name = await _runtime_catalog(
            runtime,
        ).update_session_runtime_overrides(
            session_name,
            override_payload,
        )
    except SessionRuntimeContextError as exc:
        raise _session_runtime_context_http_exception(exc) from exc

    return await _session_runtime_context_response(
        runtime,
        resolved_session_name,
        access_role,
    )


def _validate_runtime_override_access(
    override_payload: dict[str, Any],
    request_is_admin: bool,
) -> None:
    if request_is_admin:
        return

    route_mode = str(override_payload.get("route_mode") or "").strip()
    if route_mode and route_mode != "chat_only":
        raise HTTPException(
            status_code=403,
            detail="Agent route mode requires admin access",
        )

    allowed_section_fields = {
        "tts": {"provider", "voice"},
        "asr": {"provider", "language"},
        "live2d": {"selection_key"},
    }
    for section_name, allowed_fields in allowed_section_fields.items():
        section = override_payload.get(section_name)
        if not isinstance(section, dict):
            continue
        if set(section) - allowed_fields:
            raise HTTPException(
                status_code=403,
                detail=f"{section_name.upper()} provider settings require admin access",
            )

    stage = override_payload.get("stage")
    background = stage.get("background") if isinstance(stage, dict) else None
    background_url = str(
        (background.get("url") if isinstance(background, dict) else "") or "",
    ).strip()
    if background_url and not background_url.startswith(
        "/api/web/stage/backgrounds/",
    ):
        raise HTTPException(
            status_code=403,
            detail="External Stage backgrounds require admin access",
        )


async def _session_runtime_context_response(
    runtime,
    session_name: str,
    access_role: AccessRole,
) -> SessionRuntimeContextResponse:
    try:
        context = await build_session_runtime_context(runtime, session_name)
        return project_session_runtime_context(context, access_role)
    except SessionRuntimeContextError as exc:
        raise _session_runtime_context_http_exception(exc) from exc


def _runtime_context_etag(revision: str, access_role: AccessRole) -> str:
    return f'"{revision}-{access_role.value}"'


def _runtime_context_cache_headers(etag: str) -> dict[str, str]:
    return {
        "ETag": etag,
        "Cache-Control": "private, no-cache",
        "Vary": "Authorization",
    }


def _if_none_match(header_value: str | None, etag: str) -> bool:
    if not header_value:
        return False
    for candidate in header_value.split(","):
        normalized = candidate.strip()
        if normalized == "*":
            return True
        if normalized.startswith("W/"):
            normalized = normalized[2:].strip()
        if normalized == etag:
            return True
    return False


def _session_runtime_context_http_exception(
    exc: SessionRuntimeContextError,
) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _ensure_runtime_model_services_ready(runtime) -> None:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    if runtime.llm_model_service is None:
        raise HTTPException(status_code=503, detail="LLM model service is not ready")
    if runtime.voice_model_service is None:
        raise HTTPException(status_code=503, detail="Voice model service is not ready")
    if runtime.live2d_model_service is None:
        raise HTTPException(status_code=503, detail="Live2D model service is not ready")


def _runtime_catalog(runtime) -> RuntimeCatalogApplicationService:
    return RuntimeCatalogApplicationService(runtime)


def _model_profile_lock(runtime):
    lock = getattr(runtime, "model_profile_lock", None)
    if lock is None:
        raise HTTPException(status_code=503, detail="Model profile lock is not ready")
    return lock


async def _active_llm_model_id(runtime) -> str:
    payload = await asyncio.to_thread(runtime.llm_model_service.list_models)
    return str(payload.get("active_model_id") or "a")


async def _active_voice_profile_id(runtime) -> str:
    payload = await asyncio.to_thread(runtime.voice_model_service.list_profiles)
    return str(payload.get("active_voice_profile_id") or "a")


async def _active_live2d_model_id(runtime) -> str:
    catalog = await _live2d_catalog(runtime)
    payload = await asyncio.to_thread(runtime.live2d_model_service.list_models, catalog)
    return str(payload.get("active_live2d_model_id") or "a")


async def _apply_runtime_profile(runtime) -> None:
    await runtime.apply_active_model_profile()


def _runtime_profile_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "unknown model profile" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)


async def _live2d_catalog(runtime) -> list[dict[str, Any]]:
    return await compat_live2d_catalog(runtime)


def _channel_owner_scope_or_503(runtime):
    try:
        return channel_owner_scope(runtime)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
