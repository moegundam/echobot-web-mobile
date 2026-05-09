from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...orchestration import role_name_from_metadata, route_mode_from_metadata
from ..schemas import (
    CharacterProfileModel,
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
from ..services.session_catalog import (
    channel_integration_by_id,
    channel_integration_for_session,
    effective_profile_id,
    live2d_model_from_profile,
    llm_model_from_profile,
    profile_lookup,
    project_channel_integrations,
    voice_profile_from_profile,
)
from ..services.runtime_profile_composer import (
    live2d_runtime_profile,
    llm_runtime_profile,
    model_profile_id_for_role,
    runtime_profile_with_overrides,
    voice_runtime_profile,
)
from ..services.model_profile_compat import (
    live2d_catalog as compat_live2d_catalog,
    model_profiles_payload,
)
from ..session_metadata import channel_integration_id_from_metadata
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["session-catalog"])


@router.get("/llm-models", response_model=LLMModelsResponse)
async def list_llm_models(runtime=Depends(get_app_runtime)) -> LLMModelsResponse:
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
        payload = await asyncio.to_thread(
            runtime.llm_model_service.update_model,
            model_id,
            request.model_dump(exclude_unset=True),
        )
        if model_id == await _active_llm_model_id(runtime):
            await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return LLMModelAdminModel(**payload)


@router.post("/llm-models/{model_id}/activate", response_model=LLMModelsResponse)
async def activate_llm_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(runtime.llm_model_service.activate_model, model_id)
        await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return LLMModelsResponse(**payload)


@router.delete("/llm-models/{model_id}", response_model=LLMModelsResponse)
async def delete_llm_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> LLMModelsResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(runtime.llm_model_service.delete_model, model_id)
        if runtime.character_profile_settings_service is not None:
            await asyncio.to_thread(
                runtime.character_profile_settings_service.clear_model_profile_bindings_for_profile,
                model_id,
            )
        await _delete_legacy_model_profile_if_present(runtime, model_id)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return LLMModelsResponse(**payload)


@router.get("/voice-models", response_model=VoiceProfilesResponse)
async def list_voice_models(runtime=Depends(get_app_runtime)) -> VoiceProfilesResponse:
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
        payload = await asyncio.to_thread(
            runtime.voice_model_service.update_profile,
            profile_id,
            request.model_dump(exclude_unset=True),
        )
        if profile_id == await _active_voice_profile_id(runtime):
            await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return VoiceProfileAdminModel(**payload)


@router.post("/voice-models/{profile_id}/activate", response_model=VoiceProfilesResponse)
async def activate_voice_model(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfilesResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(runtime.voice_model_service.activate_profile, profile_id)
        await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return VoiceProfilesResponse(**payload)


@router.delete("/voice-models/{profile_id}", response_model=VoiceProfilesResponse)
async def delete_voice_model(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> VoiceProfilesResponse:
    _ensure_runtime_model_services_ready(runtime)
    try:
        payload = await asyncio.to_thread(runtime.voice_model_service.delete_profile, profile_id)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return VoiceProfilesResponse(**payload)


@router.get("/live2d-models", response_model=Live2DModelsResponse)
async def list_live2d_models(runtime=Depends(get_app_runtime)) -> Live2DModelsResponse:
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
        payload = await asyncio.to_thread(
            runtime.live2d_model_service.activate_model,
            model_id,
            catalog,
        )
        await _apply_runtime_profile(runtime)
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
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
        payload = await asyncio.to_thread(
            runtime.live2d_model_service.delete_model,
            model_id,
            catalog,
        )
    except ValueError as exc:
        raise _runtime_profile_http_exception(exc) from exc
    return Live2DModelsResponse(**payload)


@router.get("/channel-integrations", response_model=ChannelIntegrationsResponse)
async def list_channel_integrations(
    runtime=Depends(get_app_runtime),
) -> ChannelIntegrationsResponse:
    return ChannelIntegrationsResponse(
        integrations=await _channel_integrations(runtime),
    )


@router.post("/channel-integrations/{integration_id}/smoke")
async def smoke_channel_integration(
    integration_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, Any]:
    if runtime.channel_service is None:
        raise HTTPException(status_code=503, detail="Channel service is not ready")
    try:
        return await runtime.channel_service.smoke_channel(integration_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown channel integration") from exc


@router.get(
    "/sessions/{session_name}/runtime-context",
    response_model=SessionRuntimeContextResponse,
)
async def get_session_runtime_context(
    session_name: str,
    runtime=Depends(get_app_runtime),
) -> SessionRuntimeContextResponse:
    return await _session_runtime_context_response(runtime, session_name)


@router.put(
    "/sessions/{session_name}/runtime-overrides",
    response_model=SessionRuntimeContextResponse,
)
async def update_session_runtime_overrides(
    session_name: str,
    request: UpdateSessionRuntimeOverridesRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> SessionRuntimeContextResponse:
    _ensure_runtime_services_ready(runtime)
    if getattr(runtime, "session_runtime_override_service", None) is None:
        raise HTTPException(status_code=503, detail="Session runtime override service is not ready")

    try:
        session = await runtime.session_service.load_session(session_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    profile_payload = await _profile_payload(runtime)
    profiles = profile_lookup(profile_payload)
    override_payload = request.model_dump(
        mode="json",
        exclude_none=True,
        exclude_defaults=True,
    )
    _validate_runtime_profile_ids(
        profiles,
        [
            str(override_payload.get("model_profile_id") or "").strip(),
            str(override_payload.get("llm_model_id") or "").strip(),
            str(override_payload.get("voice_profile_id") or "").strip(),
            str(override_payload.get("live2d_model_id") or "").strip(),
        ],
    )

    try:
        await asyncio.to_thread(
            runtime.session_runtime_override_service.set_override,
            session.name,
            override_payload,
        )
        await _apply_runtime_override_if_current_session(runtime, session.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await _session_runtime_context_response(runtime, session.name)


async def _session_runtime_context_response(
    runtime,
    session_name: str,
) -> SessionRuntimeContextResponse:
    _ensure_runtime_services_ready(runtime)
    try:
        session = await runtime.session_service.load_session(session_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    role_name = role_name_from_metadata(session.metadata)
    route_mode = route_mode_from_metadata(session.metadata)
    profile_payload = await _profile_payload(runtime)
    profiles = profile_lookup(profile_payload)
    live_override = await _session_runtime_override(runtime, session.name)
    bound_profile_id = await model_profile_id_for_role(runtime, role_name)
    base_profile_id = str(
        live_override.get("model_profile_id")
        or bound_profile_id
        or effective_profile_id(profile_payload, role_name),
    )
    runtime_bindings = await _runtime_bindings_for_role(runtime, role_name)
    llm_profile_id = (
        str(live_override.get("llm_model_id") or "")
        or runtime_bindings.get("llm_model_id")
        or base_profile_id
    )
    voice_profile_id = (
        str(live_override.get("voice_profile_id") or "")
        or runtime_bindings.get("voice_profile_id")
        or base_profile_id
    )
    live2d_profile_id = (
        str(live_override.get("live2d_model_id") or "")
        or runtime_bindings.get("live2d_model_id")
        or base_profile_id
    )
    llm_profile = await _runtime_llm_profile(
        runtime,
        llm_profile_id,
        profiles.get(llm_profile_id, {}),
    )
    voice_profile = await _runtime_voice_profile(
        runtime,
        voice_profile_id,
        profiles.get(voice_profile_id, {}),
    )
    live2d_profile = await _runtime_live2d_profile(
        runtime,
        live2d_profile_id,
        profiles.get(live2d_profile_id, {}),
    )
    catalog = await _live2d_catalog(runtime)
    catalog_by_key = {
        str(item.get("selection_key") or ""): item
        for item in catalog
        if isinstance(item, dict)
    }
    character = await _character_for_role(
        runtime,
        role_name,
        profile_payload,
        live_override=live_override,
    )
    integrations = await _channel_integrations(runtime)
    channel = channel_integration_by_id(
        integrations,
        channel_integration_id_from_metadata(session.metadata),
    ) or channel_integration_for_session(integrations, session.name)

    voice_model = voice_profile_from_profile(voice_profile) if voice_profile else None
    live2d_model = (
        live2d_model_from_profile(live2d_profile, catalog_by_key)
        if live2d_profile
        else None
    )
    voice_model = _apply_voice_override(voice_model, live_override)
    live2d_model = _apply_live2d_override(live2d_model, live_override, catalog_by_key)

    return SessionRuntimeContextResponse(
        session_name=session.name,
        role_name=role_name,
        route_mode=route_mode,
        character=character,
        llm_model=llm_model_from_profile(llm_profile) if llm_profile else None,
        voice_profile=voice_model,
        live2d_model=live2d_model,
        channel=channel,
        stage=_stage_context_from_override(live_override),
    )


async def _profile_payload(runtime) -> dict[str, Any]:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    return await model_profiles_payload(runtime)


def _ensure_runtime_model_services_ready(runtime) -> None:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    if runtime.llm_model_service is None:
        raise HTTPException(status_code=503, detail="LLM model service is not ready")
    if runtime.voice_model_service is None:
        raise HTTPException(status_code=503, detail="Voice model service is not ready")
    if runtime.live2d_model_service is None:
        raise HTTPException(status_code=503, detail="Live2D model service is not ready")


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


async def _channel_integrations(runtime):
    if runtime.channel_service is None:
        raise HTTPException(status_code=503, detail="Channel service is not ready")
    definitions = runtime.channel_service.get_definitions()
    config = await runtime.channel_service.get_config()
    status = await runtime.channel_service.get_status()
    stage_targets = await runtime.channel_service.get_stage_targets()
    return project_channel_integrations(
        definitions=definitions,
        config=config,
        status=status,
        stage_targets=stage_targets,
    )


async def _character_for_role(
    runtime,
    role_name: str,
    profile_payload: dict[str, Any],
    *,
    live_override: dict[str, Any] | None = None,
) -> CharacterProfileModel | None:
    if (
        runtime.role_service is None
        or runtime.character_profile_settings_service is None
    ):
        return None
    try:
        role = await runtime.role_service.get_role(role_name)
    except ValueError:
        return None

    live_override = live_override or {}
    bound_profile_id = await model_profile_id_for_role(runtime, role.name)
    resolved_profile_id = str(
        live_override.get("model_profile_id")
        or bound_profile_id
        or profile_payload.get("active_profile_id")
        or "",
    )
    runtime_bindings = await _runtime_bindings_for_role(runtime, role.name)
    profiles = profile_lookup(profile_payload)
    resolved_profile = profiles.get(resolved_profile_id, {})
    llm_model_id = str(
        live_override.get("llm_model_id")
        or runtime_bindings.get("llm_model_id")
        or "",
    )
    voice_profile_id = str(
        live_override.get("voice_profile_id")
        or runtime_bindings.get("voice_profile_id")
        or "",
    )
    live2d_model_id = str(
        live_override.get("live2d_model_id")
        or runtime_bindings.get("live2d_model_id")
        or "",
    )
    llm_profile = profiles.get(llm_model_id or resolved_profile_id, {})
    voice_profile = profiles.get(voice_profile_id or resolved_profile_id, {})
    visual_profile = profiles.get(live2d_model_id or resolved_profile_id, {})
    chat = _section(llm_profile, "chat")
    tts = _section(voice_profile, "tts")
    asr = _section(voice_profile, "asr")
    live2d = _section(visual_profile, "live2d")
    tts = {**tts, **_section(live_override, "tts")}
    asr = {**asr, **_section(live_override, "asr")}
    live2d = {**live2d, **_section(live_override, "live2d")}
    emotion_maps = await asyncio.to_thread(
        runtime.character_profile_settings_service.emotion_maps_for_role,
        role.name,
    )
    return CharacterProfileModel(
        name=role.name,
        editable=role.name != "default",
        deletable=role.name != "default",
        source_path=str(role.source_path) if role.source_path is not None else None,
        prompt=role.prompt,
        model_profile_id=bound_profile_id,
        llm_model_id=llm_model_id,
        voice_profile_id=voice_profile_id,
        live2d_model_id=live2d_model_id,
        default_channel_type=str(runtime_bindings.get("default_channel_type") or ""),
        default_channel_integration_id=str(
            runtime_bindings.get("default_channel_integration_id") or "",
        ),
        effective_model_profile_id=resolved_profile_id,
        model_profile_label=str(resolved_profile.get("label") or resolved_profile_id),
        chat_model=str(chat.get("model") or ""),
        tts_voice=str(tts.get("voice") or ""),
        asr_model=str(asr.get("model") or ""),
        live2d_selection_key=str(live2d.get("selection_key") or ""),
        emotion_maps=emotion_maps,
    )


def _ensure_runtime_services_ready(runtime) -> None:
    if runtime.session_service is None:
        raise HTTPException(status_code=503, detail="Session service is not ready")
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")


async def _runtime_bindings_for_role(runtime, role_name: str) -> dict[str, str]:
    if runtime.character_profile_settings_service is None:
        return {}
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.runtime_bindings_for_role,
        role_name,
    )


async def _runtime_llm_profile(
    runtime,
    profile_id: str,
    fallback_profile: dict[str, Any],
) -> dict[str, Any]:
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return fallback_profile
    try:
        return await llm_runtime_profile(runtime, normalized_id)
    except ValueError:
        return fallback_profile


async def _runtime_voice_profile(
    runtime,
    profile_id: str,
    fallback_profile: dict[str, Any],
) -> dict[str, Any]:
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return fallback_profile
    try:
        return await voice_runtime_profile(runtime, normalized_id)
    except ValueError:
        return fallback_profile


async def _runtime_live2d_profile(
    runtime,
    profile_id: str,
    fallback_profile: dict[str, Any],
) -> dict[str, Any]:
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return fallback_profile
    try:
        return await live2d_runtime_profile(runtime, normalized_id)
    except ValueError:
        return fallback_profile


async def _session_runtime_override(runtime, session_name: str) -> dict[str, Any]:
    service = getattr(runtime, "session_runtime_override_service", None)
    if service is None:
        return {}
    return await asyncio.to_thread(service.get_override, session_name)


def _validate_runtime_profile_ids(
    profiles: dict[str, dict[str, Any]],
    profile_ids: list[str],
) -> None:
    for profile_id in profile_ids:
        if profile_id and profile_id not in profiles:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown model profile: {profile_id}",
            )


async def _apply_runtime_override_if_current_session(runtime, session_name: str) -> None:
    if runtime.session_service is None or runtime.context is None:
        return

    current_session = await runtime.session_service.load_current_session()
    if current_session.name != session_name:
        return

    live_override = await _session_runtime_override(runtime, session_name)
    if not live_override:
        return

    profile_payload = await _profile_payload(runtime)
    role_name = role_name_from_metadata(current_session.metadata)
    base_profile_id = str(
        live_override.get("model_profile_id")
        or effective_profile_id(profile_payload, role_name),
    )
    runtime_bindings = await _runtime_bindings_for_role(runtime, role_name)
    runtime_profile = await _runtime_profile_with_live_override(
        runtime,
        role_name=role_name,
        base_profile_id=base_profile_id,
        runtime_bindings=runtime_bindings,
        live_override=live_override,
    )
    if runtime_profile:
        await runtime.apply_model_profile(runtime_profile)


async def _runtime_profile_with_live_override(
    runtime,
    *,
    role_name: str = "",
    base_profile_id: str,
    runtime_bindings: dict[str, str] | None = None,
    live_override: dict[str, Any],
) -> dict[str, Any] | None:
    return await runtime_profile_with_overrides(
        runtime,
        role_name=role_name,
        base_profile_id=base_profile_id,
        runtime_bindings=runtime_bindings,
        live_override=live_override,
    )


def _apply_voice_override(voice_model, live_override: dict[str, Any]):
    if voice_model is None:
        return voice_model
    updates: dict[str, Any] = {}
    tts_override = _section(live_override, "tts")
    if tts_override:
        updates["tts"] = voice_model.tts.model_copy(update=tts_override)
    asr_override = _section(live_override, "asr")
    if asr_override:
        updates["stt"] = voice_model.stt.model_copy(update=asr_override)
    if not updates:
        return voice_model
    return voice_model.model_copy(update=updates)


def _apply_live2d_override(
    live2d_model,
    live_override: dict[str, Any],
    catalog_by_key: dict[str, dict[str, Any]],
):
    if live2d_model is None:
        return live2d_model
    live2d_override = _section(live_override, "live2d")
    selection_key = str(live2d_override.get("selection_key") or "").strip()
    if not selection_key:
        return live2d_model
    catalog_item = catalog_by_key.get(selection_key, {})
    return live2d_model.model_copy(
        update={
            "selection_key": selection_key,
            "available": bool(catalog_item),
            "model_name": str(catalog_item.get("model_name") or ""),
            "model_url": str(catalog_item.get("model_url") or ""),
        },
    )


def _stage_context_from_override(live_override: dict[str, Any]) -> dict[str, Any] | None:
    stage = _section(live_override, "stage")
    background = _section(stage, "background")
    if not background:
        return None
    return {"background": background}


async def _delete_legacy_model_profile_if_present(runtime, profile_id: str) -> None:
    service = getattr(runtime, "model_profile_service", None)
    if service is None:
        return
    try:
        await asyncio.to_thread(service.delete_profile, profile_id)
    except ValueError:
        return


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}
