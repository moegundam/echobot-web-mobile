from __future__ import annotations

from typing import Any

from ..schemas import (
    ChannelIntegrationAdminModel,
    LLMModelAdminModel,
    Live2DModelAdminModel,
    SpeechModelAdminConfigModel,
    VoiceProfileAdminModel,
    channel_config_payload,
)


def profile_lookup(profile_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(profile.get("profile_id") or ""): profile
        for profile in profiles_list(profile_payload)
        if str(profile.get("profile_id") or "")
    }


def profiles_list(profile_payload: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = profile_payload.get("profiles")
    if not isinstance(profiles, list):
        return []
    return [profile for profile in profiles if isinstance(profile, dict)]


def effective_profile_id(profile_payload: dict[str, Any], role_name: str) -> str:
    bindings = profile_payload.get("role_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    return str(bindings.get(role_name) or profile_payload.get("active_profile_id") or "")


def project_llm_models(profile_payload: dict[str, Any]) -> list[LLMModelAdminModel]:
    return [
        llm_model_from_profile(profile)
        for profile in profiles_list(profile_payload)
    ]


def project_voice_profiles(profile_payload: dict[str, Any]) -> list[VoiceProfileAdminModel]:
    return [
        voice_profile_from_profile(profile)
        for profile in profiles_list(profile_payload)
    ]


def project_live2d_models(
    profile_payload: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> list[Live2DModelAdminModel]:
    catalog_by_key = {
        str(item.get("selection_key") or ""): item
        for item in catalog
        if isinstance(item, dict)
    }
    return [
        live2d_model_from_profile(profile, catalog_by_key)
        for profile in profiles_list(profile_payload)
    ]


def llm_model_from_profile(profile: dict[str, Any]) -> LLMModelAdminModel:
    profile_id = str(profile.get("profile_id") or "")
    chat = _section(profile, "chat")
    return LLMModelAdminModel(
        id=profile_id,
        name=str(profile.get("label") or profile_id),
        provider=str(chat.get("provider") or "openai-compatible"),
        model=str(chat.get("model") or ""),
        base_url=str(chat.get("base_url") or ""),
        temperature=chat.get("temperature"),
        max_tokens=chat.get("max_tokens"),
        api_key_configured=bool(chat.get("api_key_configured")),
        api_key_source=str(chat.get("api_key_source") or ""),
        source_model_profile_id=profile_id,
    )


def voice_profile_from_profile(profile: dict[str, Any]) -> VoiceProfileAdminModel:
    profile_id = str(profile.get("profile_id") or "")
    return VoiceProfileAdminModel(
        id=profile_id,
        name=str(profile.get("label") or profile_id),
        tts=_speech_config_from_section(_section(profile, "tts")),
        stt=_speech_config_from_section(_section(profile, "asr")),
        source_model_profile_id=profile_id,
    )


def live2d_model_from_profile(
    profile: dict[str, Any],
    catalog_by_key: dict[str, dict[str, Any]] | None = None,
) -> Live2DModelAdminModel:
    profile_id = str(profile.get("profile_id") or "")
    live2d = _section(profile, "live2d")
    selection_key = str(live2d.get("selection_key") or "")
    catalog_item = (catalog_by_key or {}).get(selection_key, {})
    return Live2DModelAdminModel(
        id=profile_id,
        name=str(profile.get("label") or profile_id),
        selection_key=selection_key,
        source_model_profile_id=profile_id,
        available=bool(catalog_item) if selection_key else False,
        model_name=str(catalog_item.get("model_name") or ""),
        model_url=str(catalog_item.get("model_url") or ""),
    )


def project_channel_integrations(
    *,
    definitions: list[dict[str, Any]],
    config: dict[str, Any],
    status: dict[str, dict[str, bool]],
    stage_targets: dict[str, Any],
) -> list[ChannelIntegrationAdminModel]:
    redacted_config = channel_config_payload(config)
    stage_target_by_channel = {
        str(target.get("channel") or ""): target
        for target in stage_targets.get("targets", [])
        if isinstance(target, dict)
    }
    integrations: list[ChannelIntegrationAdminModel] = []
    for definition in definitions:
        channel_id = str(definition.get("name") or "").strip().lower()
        if not channel_id:
            continue
        channel_config = redacted_config.get(channel_id, {})
        if not isinstance(channel_config, dict):
            channel_config = {}
        channel_status = status.get(channel_id, {})
        if not isinstance(channel_status, dict):
            channel_status = {}
        stage_target = stage_target_by_channel.get(channel_id, {})
        integrations.append(
            ChannelIntegrationAdminModel(
                id=channel_id,
                type=channel_id,
                name=str(definition.get("label") or _channel_label(channel_id)),
                enabled=bool(channel_config.get("enabled")) or bool(channel_status.get("enabled")),
                running=bool(channel_status.get("running")),
                configured=_channel_configured(channel_id, channel_config),
                mirror_to_stage=bool(channel_config.get("mirror_to_stage")),
                stage_session_name=str(
                    stage_target.get("session_name")
                    or channel_config.get("stage_session_name")
                    or "",
                ),
                selectable=bool(stage_target.get("selectable")),
                config=channel_config,
            )
        )
    integrations.sort(key=lambda item: item.id)
    return integrations


def channel_integration_for_session(
    integrations: list[ChannelIntegrationAdminModel],
    session_name: str,
) -> ChannelIntegrationAdminModel | None:
    normalized_session_name = str(session_name or "").strip().lower()
    for integration in integrations:
        if not integration.mirror_to_stage and not integration.selectable:
            continue
        if str(integration.stage_session_name or "").strip().lower() == normalized_session_name:
            return integration
    return None


def _speech_config_from_section(section: dict[str, Any]) -> SpeechModelAdminConfigModel:
    return SpeechModelAdminConfigModel(
        provider=str(section.get("provider") or ""),
        model=str(section.get("model") or ""),
        base_url=str(section.get("base_url") or ""),
        voice=str(section.get("voice") or ""),
        language=str(section.get("language") or ""),
        api_key_configured=bool(section.get("api_key_configured")),
        api_key_source=str(section.get("api_key_source") or ""),
    )


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}


def _channel_configured(channel_id: str, config: dict[str, Any]) -> bool:
    if channel_id == "telegram":
        return bool(config.get("bot_token_configured"))
    if channel_id == "discord":
        return bool(config.get("bot_token_configured")) or bool(str(config.get("webhook_url") or "").strip())
    if channel_id == "qq":
        return bool(str(config.get("app_id") or "").strip()) and bool(config.get("client_secret_configured"))
    return bool(config.get("enabled"))


def _channel_label(channel_id: str) -> str:
    if channel_id == "qq":
        return "QQ"
    return channel_id.replace("_", " ").title()
