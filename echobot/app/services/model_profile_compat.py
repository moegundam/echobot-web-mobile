from __future__ import annotations

import asyncio
from typing import Any


async def model_profiles_payload(runtime) -> dict[str, Any]:
    """Return the legacy model-profile payload with domain-owned bindings merged in."""

    payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    domain_profile_ids: set[str] = set()
    for domain_payload, sections, use_active in (
        (
            await _legacy_payload_from_service(getattr(runtime, "llm_model_service", None)),
            ("chat",),
            False,
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
    ):
        if domain_payload is not None:
            domain_profile_ids.update(_payload_profile_ids(domain_payload))
            _merge_domain_projection(
                payload,
                domain_payload,
                sections=sections,
                use_active=use_active,
            )
    if domain_profile_ids:
        payload["profiles"] = [
            profile
            for profile in payload.get("profiles", [])
            if isinstance(profile, dict)
            and str(profile.get("profile_id") or "") in domain_profile_ids
        ]
    payload["role_bindings"] = await model_profile_role_bindings(runtime, payload)
    return payload


async def model_profile_role_bindings(
    runtime,
    payload: dict[str, Any] | None = None,
) -> dict[str, str]:
    if payload is None:
        payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    bindings = dict(payload.get("role_bindings", {}))
    character_settings = getattr(runtime, "character_profile_settings_service", None)
    if character_settings is not None:
        bindings.update(
            await asyncio.to_thread(character_settings.model_profile_bindings),
        )
    return bindings


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


def _payload_profile_ids(payload: dict[str, Any]) -> set[str]:
    return {
        profile_id
        for profile_id in (
            str(profile.get("profile_id") or "").strip()
            for profile in payload.get("profiles", [])
            if isinstance(profile, dict)
        )
        if profile_id
    }


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
