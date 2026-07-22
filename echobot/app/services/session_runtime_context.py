from __future__ import annotations

import asyncio
from typing import Any

from ...orchestration import (
    normalize_route_mode,
    role_name_from_metadata,
    route_mode_from_metadata,
)
from ..schemas import SessionCharacterRuntimeModel, SessionRuntimeContextResponse
from ..session_metadata import channel_integration_id_from_metadata
from .channel_owner_scope import channel_owner_scope
from .model_profile_compat import (
    live2d_catalog as compat_live2d_catalog,
    model_profiles_payload,
)
from .runtime_profile_composer import (
    live2d_runtime_profile,
    llm_runtime_profile,
    model_profile_id_for_role,
    runtime_profile_with_overrides,
    voice_runtime_profile,
)
from .runtime_context_cache import get_runtime_context_cache
from .session_catalog import (
    channel_integration_by_id,
    effective_profile_id,
    live2d_model_from_profile,
    llm_model_from_profile,
    profile_lookup,
    project_channel_integrations,
    voice_profile_from_profile,
)


class SessionRuntimeContextError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code


async def list_channel_integrations_for_runtime(runtime):
    scope = _channel_owner_scope_or_error(runtime)
    return project_channel_integrations(
        **await scope.service.get_integration_projection_inputs(),
    )


async def build_session_runtime_context(
    runtime,
    session_name: str,
) -> SessionRuntimeContextResponse:
    cache = get_runtime_context_cache(runtime)
    return await cache.get_or_build(
        session_name,
        lambda: _build_uncached_session_runtime_context(runtime, session_name),
    )


async def _build_uncached_session_runtime_context(
    runtime,
    session_name: str,
) -> SessionRuntimeContextResponse:
    ensure_runtime_services_ready(runtime)
    try:
        session = await runtime.session_service.load_session(session_name)
    except ValueError as exc:
        raise SessionRuntimeContextError(404, str(exc)) from exc

    profile_payload = await runtime_profile_payload(runtime)
    profiles = profile_lookup(profile_payload)
    live_override = await session_runtime_override(runtime, session.name)
    role_name = str(
        live_override.get("role_name")
        or role_name_from_metadata(session.metadata),
    )
    route_mode = normalize_route_mode(
        live_override.get("route_mode")
        or route_mode_from_metadata(session.metadata),
    )
    bound_profile_id = await model_profile_id_for_role(runtime, role_name)
    base_profile_id = str(
        live_override.get("model_profile_id")
        or bound_profile_id
        or effective_profile_id(profile_payload, role_name),
    )
    runtime_bindings = await runtime_bindings_for_role(runtime, role_name)
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
    integrations = await list_channel_integrations_for_runtime(runtime)
    channel = channel_integration_by_id(
        integrations,
        channel_integration_id_from_metadata(session.metadata),
    )

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


async def runtime_profile_payload(runtime) -> dict[str, Any]:
    if runtime.model_profile_service is None:
        raise SessionRuntimeContextError(503, "Model profile service is not ready")
    return await model_profiles_payload(runtime)


def ensure_runtime_services_ready(runtime) -> None:
    if runtime.session_service is None:
        raise SessionRuntimeContextError(503, "Session service is not ready")
    if runtime.model_profile_service is None:
        raise SessionRuntimeContextError(503, "Model profile service is not ready")


async def runtime_bindings_for_role(runtime, role_name: str) -> dict[str, str]:
    if runtime.character_profile_settings_service is None:
        return {}
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.runtime_bindings_for_role,
        role_name,
    )


async def session_runtime_override(runtime, session_name: str) -> dict[str, Any]:
    service = getattr(runtime, "session_runtime_override_service", None)
    if service is None:
        return {}
    return await asyncio.to_thread(service.get_override, session_name)


def validate_runtime_profile_ids(
    profile_payload: dict[str, Any],
    profile_ids: list[str],
) -> None:
    profiles = profile_lookup(profile_payload)
    for profile_id in profile_ids:
        if profile_id and profile_id not in profiles:
            raise SessionRuntimeContextError(
                404,
                f"Unknown model profile: {profile_id}",
            )


async def apply_runtime_override_if_current_session(
    runtime,
    session_name: str,
) -> None:
    if runtime.session_service is None or runtime.context is None:
        return

    current_session = await runtime.session_service.load_current_session()
    if current_session.name != session_name:
        return

    live_override = await session_runtime_override(runtime, session_name)
    if not live_override:
        return

    profile_payload = await runtime_profile_payload(runtime)
    role_name = str(
        live_override.get("role_name")
        or role_name_from_metadata(current_session.metadata),
    )
    base_profile_id = str(
        live_override.get("model_profile_id")
        or effective_profile_id(profile_payload, role_name),
    )
    runtime_bindings = await runtime_bindings_for_role(runtime, role_name)
    runtime_profile = await runtime_profile_with_overrides(
        runtime,
        role_name=role_name,
        base_profile_id=base_profile_id,
        runtime_bindings=runtime_bindings,
        live_override=live_override,
    )
    if runtime_profile:
        await runtime.apply_model_profile(runtime_profile)


async def _live2d_catalog(runtime) -> list[dict[str, Any]]:
    return await compat_live2d_catalog(runtime)


async def _character_for_role(
    runtime,
    role_name: str,
    profile_payload: dict[str, Any],
    *,
    live_override: dict[str, Any] | None = None,
) -> SessionCharacterRuntimeModel | None:
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
    runtime_bindings = await runtime_bindings_for_role(runtime, role.name)
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
    return SessionCharacterRuntimeModel(
        name=role.name,
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
        if getattr(runtime, "llm_model_service", None) is not None:
            return {}
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
        if getattr(runtime, "voice_model_service", None) is not None:
            return {}
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
        if getattr(runtime, "live2d_model_service", None) is not None:
            return {}
        return fallback_profile


def _apply_voice_override(
    voice_model: dict[str, Any] | None,
    live_override: dict[str, Any],
) -> dict[str, Any] | None:
    if voice_model is None:
        return voice_model
    result = dict(voice_model)
    tts_override = _section(live_override, "tts")
    if tts_override:
        result["tts"] = {
            **_section(voice_model, "tts"),
            **tts_override,
        }
    asr_override = _section(live_override, "asr")
    if asr_override:
        result["stt"] = {
            **_section(voice_model, "stt"),
            **asr_override,
        }
    return result


def _apply_live2d_override(
    live2d_model: dict[str, Any] | None,
    live_override: dict[str, Any],
    catalog_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if live2d_model is None:
        return live2d_model
    live2d_override = _section(live_override, "live2d")
    selection_key = str(live2d_override.get("selection_key") or "").strip()
    if not selection_key:
        return live2d_model
    catalog_item = catalog_by_key.get(selection_key, {})
    return {
        **live2d_model,
        "selection_key": selection_key,
        "available": bool(catalog_item),
        "model_name": str(catalog_item.get("model_name") or ""),
        "model_url": str(catalog_item.get("model_url") or ""),
    }


def _stage_context_from_override(live_override: dict[str, Any]) -> dict[str, Any] | None:
    stage = _section(live_override, "stage")
    background = _section(stage, "background")
    if not background:
        return None
    return {"background": background}


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}


def _channel_owner_scope_or_error(runtime):
    try:
        return channel_owner_scope(runtime)
    except RuntimeError as exc:
        raise SessionRuntimeContextError(503, str(exc)) from exc
