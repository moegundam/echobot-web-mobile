from __future__ import annotations

import asyncio
from typing import Any


async def model_profiles_payload(runtime) -> dict[str, Any]:
    """Project canonical domain catalogs into the retired combined API shape."""

    domain_projections = (
        (
            await _legacy_payload_from_service(getattr(runtime, "llm_model_service", None)),
            ("chat",),
            True,
        ),
        (
            await _legacy_payload_from_service(getattr(runtime, "voice_model_service", None)),
            ("tts", "asr"),
            False,
        ),
        (
            await _legacy_payload_from_service(getattr(runtime, "live2d_model_service", None)),
            ("live2d",),
            False,
        ),
    )
    if not any(domain_payload is not None for domain_payload, _, _ in domain_projections):
        legacy_service = getattr(runtime, "model_profile_service", None)
        if legacy_service is None:
            return {"active_profile_id": "", "role_bindings": {}, "profiles": []}
        payload = await asyncio.to_thread(legacy_service.list_profiles)
        payload["role_bindings"] = await model_profile_role_bindings(runtime, payload)
        return payload

    payload: dict[str, Any] = {
        "active_profile_id": "",
        "role_bindings": {},
        "profiles": [],
    }
    for domain_payload, sections, use_active in domain_projections:
        if domain_payload is not None:
            _merge_domain_projection(
                payload,
                domain_payload,
                sections=sections,
                use_active=use_active,
            )
    if not payload["active_profile_id"] and payload["profiles"]:
        payload["active_profile_id"] = str(payload["profiles"][0]["profile_id"])
    payload["role_bindings"] = await model_profile_role_bindings(runtime, payload)
    return payload


async def model_profile_role_bindings(
    runtime,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    character_settings = getattr(runtime, "character_profile_settings_service", None)
    if character_settings is not None:
        return await asyncio.to_thread(
            character_settings.model_profile_bindings,
        )
    if payload is None:
        legacy_service = getattr(runtime, "model_profile_service", None)
        if legacy_service is None:
            return {}
        payload = await asyncio.to_thread(legacy_service.list_profiles)
    return dict(payload.get("role_bindings", {}))


async def live2d_catalog(runtime) -> list[dict[str, object]]:
    if runtime.web_console_service is None:
        return []
    config = await runtime.web_console_service.build_frontend_config(
        session_name="default",
        role_name="default",
        route_mode="chat_only",
        runtime_config={},
    )
    live2d = config.get("live2d") if isinstance(config, dict) else {}
    models = live2d.get("models") if isinstance(live2d, dict) else []
    return [item for item in models if isinstance(item, dict)]


async def _legacy_payload_from_service(service) -> dict[str, Any] | None:
    if service is None or not hasattr(service, "legacy_payload"):
        return None
    return await asyncio.to_thread(service.legacy_payload)


def _merge_domain_projection(
    payload: dict[str, Any],
    domain_payload: dict[str, Any],
    *,
    sections: tuple[str, ...],
    use_active: bool,
) -> None:
    if use_active and domain_payload.get("active_profile_id"):
        payload["active_profile_id"] = str(domain_payload["active_profile_id"])

    profiles = payload.setdefault("profiles", [])
    profiles_by_id = {
        str(profile.get("profile_id") or ""): profile
        for profile in profiles
        if isinstance(profile, dict)
    }
    for domain_profile in domain_payload.get("profiles", []):
        if not isinstance(domain_profile, dict):
            continue
        profile_id = str(domain_profile.get("profile_id") or "").strip()
        if not profile_id:
            continue
        target = profiles_by_id.get(profile_id)
        if target is None:
            target = _blank_compat_profile(profile_id)
            profiles.append(target)
            profiles_by_id[profile_id] = target
        label = str(domain_profile.get("label") or "").strip()
        if label:
            target["label"] = label
        updated_at = str(domain_profile.get("updated_at") or "").strip()
        if updated_at:
            target["updated_at"] = updated_at
        for section_name in sections:
            section = domain_profile.get(section_name)
            if isinstance(section, dict):
                target[section_name] = _compat_section(section_name, section)


def _blank_compat_profile(profile_id: str) -> dict[str, Any]:
    return {
        "profile_id": profile_id,
        "label": profile_id,
        "chat": {},
        "tts": {},
        "asr": {},
        "live2d": {},
        "updated_at": "",
    }


def _compat_section(section_name: str, section: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = {
        "chat": (
            "provider",
            "model",
            "base_url",
            "temperature",
            "max_tokens",
            "api_key_configured",
            "api_key_source",
        ),
        "tts": (
            "provider",
            "model",
            "base_url",
            "voice",
            "api_key_configured",
            "api_key_source",
        ),
        "asr": (
            "provider",
            "model",
            "base_url",
            "language",
            "api_key_configured",
            "api_key_source",
        ),
        "live2d": ("selection_key",),
    }.get(section_name, ())
    return {
        field_name: section[field_name]
        for field_name in allowed_fields
        if field_name in section
    }
