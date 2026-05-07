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
    UpdateSessionRuntimeOverridesRequest,
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
    project_live2d_models,
    project_llm_models,
    project_voice_profiles,
    voice_profile_from_profile,
)
from ..session_metadata import channel_integration_id_from_metadata
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
    base_profile_id = str(
        live_override.get("model_profile_id")
        or effective_profile_id(profile_payload, role_name),
    )
    runtime_bindings = await _runtime_bindings_for_role(runtime, role_name)
    llm_profile = profiles.get(
        str(live_override.get("llm_model_id") or "")
        or runtime_bindings.get("llm_model_id")
        or base_profile_id,
    )
    voice_profile = profiles.get(
        str(live_override.get("voice_profile_id") or "")
        or runtime_bindings.get("voice_profile_id")
        or base_profile_id,
    )
    live2d_profile = profiles.get(
        str(live_override.get("live2d_model_id") or "")
        or runtime_bindings.get("live2d_model_id")
        or base_profile_id,
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

    bindings = profile_payload.get("role_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    live_override = live_override or {}
    bound_profile_id = str(bindings.get(role.name) or "")
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
    runtime_profile = await _runtime_profile_with_live_override(
        runtime,
        base_profile_id=base_profile_id,
        live_override=live_override,
    )
    if runtime_profile:
        await runtime.apply_model_profile(runtime_profile)


async def _runtime_profile_with_live_override(
    runtime,
    *,
    base_profile_id: str,
    live_override: dict[str, Any],
) -> dict[str, Any] | None:
    if runtime.model_profile_service is None:
        return None

    base_profile_id = str(base_profile_id or "").strip()
    if not base_profile_id:
        state = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
        base_profile_id = str(state.get("active_profile_id") or "a")

    profile = dict(
        await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            base_profile_id,
        ),
    )

    llm_model_id = str(live_override.get("llm_model_id") or "").strip()
    if llm_model_id:
        llm_profile = await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            llm_model_id,
        )
        profile["chat"] = _section(llm_profile, "chat")

    voice_profile_id = str(live_override.get("voice_profile_id") or "").strip()
    if voice_profile_id:
        voice_profile = await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            voice_profile_id,
        )
        profile["tts"] = _section(voice_profile, "tts")
        profile["asr"] = _section(voice_profile, "asr")

    live2d_model_id = str(live_override.get("live2d_model_id") or "").strip()
    if live2d_model_id:
        live2d_profile = await asyncio.to_thread(
            runtime.model_profile_service.get_profile_for_runtime,
            live2d_model_id,
        )
        profile["live2d"] = _section(live2d_profile, "live2d")

    for section_name in ("tts", "asr", "live2d"):
        section_override = _section(live_override, section_name)
        if not section_override:
            continue
        current_section = dict(_section(profile, section_name))
        current_section.update(section_override)
        profile[section_name] = current_section

    return profile


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


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}
