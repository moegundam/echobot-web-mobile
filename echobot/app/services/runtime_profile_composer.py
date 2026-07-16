from __future__ import annotations

import asyncio
from typing import Any


SPLIT_RUNTIME_PROFILE_FIELDS = (
    "llm_model_id",
    "voice_profile_id",
    "live2d_model_id",
)


async def apply_runtime_profile_for_role(
    runtime,
    role_name: str,
    *,
    preferred_profile_id: str = "",
) -> dict[str, Any] | None:
    lock = getattr(runtime, "model_profile_lock", None)
    if lock is None:
        return await _apply_runtime_profile_for_role_unlocked(
            runtime,
            role_name,
            preferred_profile_id=preferred_profile_id,
        )
    async with lock:
        return await _apply_runtime_profile_for_role_unlocked(
            runtime,
            role_name,
            preferred_profile_id=preferred_profile_id,
        )


async def _apply_runtime_profile_for_role_unlocked(
    runtime,
    role_name: str,
    *,
    preferred_profile_id: str = "",
) -> dict[str, Any] | None:
    if runtime.model_profile_service is None:
        return None

    normalized_role_name = str(role_name or "").strip()
    profile_id = str(preferred_profile_id or "").strip()
    if not profile_id:
        profile_id = await model_profile_id_for_role(runtime, normalized_role_name)

    runtime_bindings = await runtime_bindings_for_role(runtime, normalized_role_name)
    has_split_bindings = has_split_runtime_bindings(runtime_bindings)
    if not profile_id and not has_split_bindings:
        return None

    if not has_split_bindings:
        activated = await asyncio.to_thread(
            runtime.model_profile_service.activate_profile,
            profile_id,
        )
        active_profile = await composed_runtime_profile(
            runtime,
            role_name=normalized_role_name,
            base_profile_id=str(activated.get("active_profile_id") or profile_id),
            runtime_bindings={
                "llm_model_id": profile_id,
                "voice_profile_id": profile_id,
                "live2d_model_id": profile_id,
            },
        )
        await runtime.apply_model_profile(active_profile)
        return activated

    state = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    base_profile_id = profile_id or str(state.get("active_profile_id") or "a")
    composed_profile = await composed_runtime_profile(
        runtime,
        role_name=normalized_role_name,
        base_profile_id=base_profile_id,
        runtime_bindings=runtime_bindings,
    )
    await asyncio.to_thread(
        runtime.model_profile_service.activate_profile,
        composed_profile["profile_id"],
    )
    await runtime.apply_model_profile(composed_profile)
    return await asyncio.to_thread(runtime.model_profile_service.list_profiles)


async def composed_runtime_profile(
    runtime,
    *,
    role_name: str,
    base_profile_id: str,
    runtime_bindings: dict[str, str],
) -> dict[str, Any]:
    base_profile_id = str(base_profile_id or "").strip() or "a"
    llm_profile_id = str(runtime_bindings.get("llm_model_id") or base_profile_id)
    voice_profile_id = str(runtime_bindings.get("voice_profile_id") or base_profile_id)
    live2d_profile_id = str(runtime_bindings.get("live2d_model_id") or base_profile_id)
    base_profile = await _legacy_runtime_profile(runtime, base_profile_id)
    llm_profile = await llm_runtime_profile(runtime, llm_profile_id)
    voice_profile = await voice_runtime_profile(runtime, voice_profile_id)
    live2d_profile = await live2d_runtime_profile(runtime, live2d_profile_id)
    composed_profile = dict(base_profile)
    composed_profile["profile_id"] = llm_profile_id
    composed_profile["label"] = str(base_profile.get("label") or role_name)
    composed_profile["chat"] = _section(llm_profile, "chat")
    composed_profile["tts"] = _section(voice_profile, "tts")
    composed_profile["asr"] = _section(voice_profile, "asr")
    composed_profile["live2d"] = _section(live2d_profile, "live2d")
    return composed_profile


async def runtime_profile_with_overrides(
    runtime,
    *,
    role_name: str = "",
    base_profile_id: str = "",
    runtime_bindings: dict[str, str] | None = None,
    live_override: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if runtime.model_profile_service is None:
        return None

    live_override = live_override or {}
    base_profile_id = str(
        live_override.get("model_profile_id")
        or base_profile_id
        or "",
    ).strip()
    if not base_profile_id:
        state = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
        base_profile_id = str(state.get("active_profile_id") or "a")

    bindings = dict(runtime_bindings or {})
    for field_name in SPLIT_RUNTIME_PROFILE_FIELDS:
        override_value = str(live_override.get(field_name) or "").strip()
        if override_value:
            bindings[field_name] = override_value

    profile = await composed_runtime_profile(
        runtime,
        role_name=role_name,
        base_profile_id=base_profile_id,
        runtime_bindings=bindings,
    )
    for section_name in ("tts", "asr", "live2d"):
        section_override = _section(live_override, section_name)
        if not section_override:
            continue
        current_section = dict(_section(profile, section_name))
        current_section.update(section_override)
        profile[section_name] = current_section
    return profile


async def llm_runtime_profile(runtime, profile_id: str) -> dict[str, Any]:
    service = getattr(runtime, "llm_model_service", None)
    if service is not None:
        return await asyncio.to_thread(service.get_runtime_profile, profile_id)
    return await _legacy_runtime_profile(runtime, profile_id)


async def voice_runtime_profile(runtime, profile_id: str) -> dict[str, Any]:
    service = getattr(runtime, "voice_model_service", None)
    if service is not None:
        return await asyncio.to_thread(service.get_runtime_profile, profile_id)
    return await _legacy_runtime_profile(runtime, profile_id)


async def live2d_runtime_profile(runtime, profile_id: str) -> dict[str, Any]:
    service = getattr(runtime, "live2d_model_service", None)
    if service is not None:
        return await asyncio.to_thread(service.get_runtime_profile, profile_id)
    return await _legacy_runtime_profile(runtime, profile_id)


async def _legacy_runtime_profile(runtime, profile_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        profile_id,
    )


async def runtime_bindings_for_role(runtime, role_name: str) -> dict[str, str]:
    if runtime.character_profile_settings_service is None:
        return {}
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.runtime_bindings_for_role,
        role_name,
    )


async def model_profile_id_for_role(runtime, role_name: str) -> str:
    service = getattr(runtime, "character_profile_settings_service", None)
    if service is not None:
        profile_id = await asyncio.to_thread(
            service.model_profile_id_for_role,
            role_name,
        )
        if profile_id:
            return profile_id

    model_profile_service = getattr(runtime, "model_profile_service", None)
    if model_profile_service is None:
        return ""
    return await asyncio.to_thread(
        model_profile_service.profile_id_for_role,
        role_name,
    )


def has_split_runtime_bindings(runtime_bindings: dict[str, str]) -> bool:
    return any(
        runtime_bindings.get(field_name)
        for field_name in SPLIT_RUNTIME_PROFILE_FIELDS
    )


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}
