from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...orchestration import role_name_from_metadata, route_mode_from_metadata
from ..schemas import (
    CharacterProfileModel,
    ChannelIntegrationsResponse,
    LLMModelsResponse,
    Live2DModelsResponse,
    SessionRuntimeContextResponse,
    VoiceProfilesResponse,
)
from ..services.session_catalog import (
    channel_integration_for_session,
    effective_profile_id,
    live2d_model_from_profile,
    llm_model_from_profile,
    profile_lookup,
    project_channel_integrations,
    project_live2d_models,
    project_llm_models,
    project_voice_profiles,
    voice_profile_from_profile,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["session-catalog"])


@router.get("/llm-models", response_model=LLMModelsResponse)
async def list_llm_models(runtime=Depends(get_app_runtime)) -> LLMModelsResponse:
    profile_payload = await _profile_payload(runtime)
    return LLMModelsResponse(
        active_model_id=str(profile_payload.get("active_profile_id") or "a"),
        models=project_llm_models(profile_payload),
    )


@router.get("/voice-models", response_model=VoiceProfilesResponse)
async def list_voice_models(runtime=Depends(get_app_runtime)) -> VoiceProfilesResponse:
    profile_payload = await _profile_payload(runtime)
    return VoiceProfilesResponse(
        active_voice_profile_id=str(profile_payload.get("active_profile_id") or "a"),
        profiles=project_voice_profiles(profile_payload),
    )


@router.get("/live2d-models", response_model=Live2DModelsResponse)
async def list_live2d_models(runtime=Depends(get_app_runtime)) -> Live2DModelsResponse:
    profile_payload = await _profile_payload(runtime)
    catalog = await _live2d_catalog(runtime)
    return Live2DModelsResponse(
        active_live2d_model_id=str(profile_payload.get("active_profile_id") or "a"),
        models=project_live2d_models(profile_payload, catalog),
        catalog=catalog,
    )


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
    _ensure_runtime_services_ready(runtime)
    try:
        session = await runtime.session_service.load_session(session_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    role_name = role_name_from_metadata(session.metadata)
    route_mode = route_mode_from_metadata(session.metadata)
    profile_payload = await _profile_payload(runtime)
    profiles = profile_lookup(profile_payload)
    resolved_profile_id = effective_profile_id(profile_payload, role_name)
    resolved_profile = profiles.get(resolved_profile_id)
    catalog = await _live2d_catalog(runtime)
    catalog_by_key = {
        str(item.get("selection_key") or ""): item
        for item in catalog
        if isinstance(item, dict)
    }
    character = await _character_for_role(runtime, role_name, profile_payload)
    integrations = await _channel_integrations(runtime)

    return SessionRuntimeContextResponse(
        session_name=session.name,
        role_name=role_name,
        route_mode=route_mode,
        character=character,
        llm_model=llm_model_from_profile(resolved_profile) if resolved_profile else None,
        voice_profile=voice_profile_from_profile(resolved_profile) if resolved_profile else None,
        live2d_model=live2d_model_from_profile(resolved_profile, catalog_by_key)
        if resolved_profile
        else None,
        channel=channel_integration_for_session(integrations, session.name),
    )


async def _profile_payload(runtime) -> dict[str, Any]:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    return await asyncio.to_thread(runtime.model_profile_service.list_profiles)


async def _live2d_catalog(runtime) -> list[dict[str, Any]]:
    if runtime.web_console_service is None:
        return []
    config = await runtime.web_console_service.build_frontend_config(
        session_name="default",
        role_name="default",
        route_mode="chat_only",
        runtime_config={},
    )
    live2d = config.get("live2d", {})
    if not isinstance(live2d, dict):
        return []
    models = live2d.get("models", [])
    return [item for item in models if isinstance(item, dict)]


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

    bindings = profile_payload.get("role_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    bound_profile_id = str(bindings.get(role.name) or "")
    resolved_profile_id = bound_profile_id or str(profile_payload.get("active_profile_id") or "")
    resolved_profile = profile_lookup(profile_payload).get(resolved_profile_id, {})
    chat = _section(resolved_profile, "chat")
    tts = _section(resolved_profile, "tts")
    asr = _section(resolved_profile, "asr")
    live2d = _section(resolved_profile, "live2d")
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


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}
