from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..auth import AccessRole
from ..schemas import SessionRuntimeContextResponse


def project_web_config_payload(
    payload: dict[str, Any],
    access_role: AccessRole,
) -> dict[str, Any]:
    projected = deepcopy(payload)
    if access_role is AccessRole.ADMIN:
        return projected

    projected["route_mode"] = "chat_only"
    projected["runtime"] = None
    model_profiles = projected.get("model_profiles")
    if isinstance(model_profiles, dict):
        profiles = model_profiles.get("profiles")
        if isinstance(profiles, list):
            for profile in profiles:
                if not isinstance(profile, dict):
                    continue
                for section_name in ("chat", "tts", "asr"):
                    _redact_provider_section(profile.get(section_name))

    _redact_web_provider_status(projected)
    return projected


def project_health_payload(
    payload: dict[str, Any],
    access_role: AccessRole,
) -> dict[str, Any]:
    projected = deepcopy(payload)
    if access_role is AccessRole.ADMIN:
        return projected
    for field_name in ("workspace_name", "channels", "bus"):
        projected.pop(field_name, None)
    return projected


def project_session_runtime_context(
    context: SessionRuntimeContextResponse,
    access_role: AccessRole,
) -> SessionRuntimeContextResponse:
    if access_role is AccessRole.ADMIN:
        return context.model_copy(deep=True)

    payload = context.model_dump(mode="python")
    payload["route_mode"] = "chat_only"

    llm_model = payload.get("llm_model")
    if isinstance(llm_model, dict):
        _redact_provider_section(llm_model)

    voice_profile = payload.get("voice_profile")
    if isinstance(voice_profile, dict):
        _redact_provider_section(voice_profile.get("tts"))
        _redact_provider_section(voice_profile.get("stt"))

    channel = payload.get("channel")
    if isinstance(channel, dict):
        channel["config"] = {}

    return SessionRuntimeContextResponse.model_validate(payload)


def _redact_provider_section(section: Any) -> None:
    if not isinstance(section, dict):
        return
    section["base_url"] = ""
    section["api_key_configured"] = False
    section["api_key_source"] = ""


def _redact_web_provider_status(payload: dict[str, Any]) -> None:
    asr = payload.get("asr")
    if isinstance(asr, dict):
        asr["detail"] = ""
        for collection_name in ("asr_providers", "vad_providers"):
            providers = asr.get(collection_name)
            if not isinstance(providers, list):
                continue
            for provider in providers:
                if not isinstance(provider, dict):
                    continue
                provider["detail"] = ""
                provider["resource_directory"] = ""

    tts = payload.get("tts")
    providers = tts.get("providers") if isinstance(tts, dict) else None
    if not isinstance(providers, list):
        return
    for provider in providers:
        if isinstance(provider, dict):
            provider["detail"] = ""
