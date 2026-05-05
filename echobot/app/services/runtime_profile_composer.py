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
    if runtime.model_profile_service is None:
        return None

    normalized_role_name = str(role_name or "").strip()
    profile_id = str(preferred_profile_id or "").strip()
    if not profile_id:
        profile_id = await asyncio.to_thread(
            runtime.model_profile_service.profile_id_for_role,
            normalized_role_name,
        )

    runtime_bindings = await runtime_bindings_for_role(runtime, normalized_role_name)
    has_split_bindings = has_split_runtime_bindings(runtime_bindings)
    if not profile_id and not has_split_bindings:
        return None

    if not has_split_bindings:
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
    base_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        base_profile_id,
    )
    llm_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        llm_profile_id,
    )
    voice_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        voice_profile_id,
    )
    live2d_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        live2d_profile_id,
    )
    composed_profile = dict(base_profile)
    composed_profile["profile_id"] = llm_profile_id
    composed_profile["label"] = str(base_profile.get("label") or role_name)
    composed_profile["chat"] = _section(llm_profile, "chat")
    composed_profile["tts"] = _section(voice_profile, "tts")
    composed_profile["asr"] = _section(voice_profile, "asr")
    composed_profile["live2d"] = _section(live2d_profile, "live2d")
    return composed_profile


async def runtime_bindings_for_role(runtime, role_name: str) -> dict[str, str]:
    if runtime.character_profile_settings_service is None:
        return {}
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.runtime_bindings_for_role,
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
