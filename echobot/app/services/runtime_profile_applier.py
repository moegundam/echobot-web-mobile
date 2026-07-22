from __future__ import annotations

import json
import os
from collections.abc import Mapping

from ...asr import OpenAITranscriptionsASRProvider
from ...asr.factory import DEFAULT_ASR_PROVIDER
from ...providers.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
)
from ...runtime.bootstrap import RuntimeContext
from ...tts.factory import DEFAULT_TTS_PROVIDER
from ...tts.providers.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
    DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
    OpenAICompatibleTTSProvider,
)
from .web_console import WebConsoleService


class RuntimeProfileApplier:
    """Apply active model profile settings to a runtime context."""

    def __init__(
        self,
        *,
        context: RuntimeContext | None,
        web_console_service: WebConsoleService | None,
    ) -> None:
        self.context = context
        self.web_console_service = web_console_service

    async def apply(self, profile: Mapping[str, object]) -> None:
        if self.context is None:
            return

        chat = profile.get("chat") if isinstance(profile, Mapping) else None
        if isinstance(chat, dict):
            self.apply_chat(chat)

        tts = profile.get("tts") if isinstance(profile, Mapping) else None
        if isinstance(tts, dict) and self.web_console_service is not None:
            try:
                await self.apply_tts(tts)
            except (ValueError, RuntimeError):
                pass

        asr = profile.get("asr") if isinstance(profile, Mapping) else None
        if isinstance(asr, dict) and self.web_console_service is not None:
            try:
                await self.apply_asr(asr)
            except (ValueError, RuntimeError):
                pass

    def apply_chat(self, chat: dict[str, object]) -> None:
        if self.context is None:
            return
        _apply_chat_model_profile_to_context(self.context, chat)

    async def apply_tts(self, tts: dict[str, object]) -> None:
        if self.web_console_service is None:
            return
        await _apply_tts_model_profile(self.web_console_service, tts)

    async def apply_asr(self, asr: dict[str, object]) -> None:
        if self.web_console_service is None:
            return
        await _apply_asr_model_profile(self.web_console_service, asr)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _profile_extra_body() -> dict[str, object]:
    raw_value = os.environ.get("LLM_EXTRA_BODY", "").strip()
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_env_object(name: str) -> dict[str, object]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return {}
    try:
        parsed = json.loads(raw_value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _csv_env(name: str) -> list[str]:
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return []
    return [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]


def _profile_text(
    section: dict[str, object],
    key: str,
    env_name: str,
    default: str = "",
) -> str:
    return (
        str(section.get(key) or "").strip()
        or os.environ.get(env_name, "").strip()
        or default
    )


async def _apply_tts_model_profile(
    web_console_service: WebConsoleService,
    tts: dict[str, object],
) -> None:
    tts_service = web_console_service.tts_service
    provider_name = (
        str(tts.get("provider") or "").strip()
        or os.environ.get("ECHOBOT_TTS_PROVIDER", "").strip()
        or DEFAULT_TTS_PROVIDER
    )
    if provider_name == "openai-compatible":
        provider = OpenAICompatibleTTSProvider(
            api_key=_profile_text(tts, "api_key", "ECHOBOT_TTS_OPENAI_API_KEY", "EMPTY"),
            model=_profile_text(tts, "model", "ECHOBOT_TTS_OPENAI_MODEL"),
            base_url=_profile_text(
                tts,
                "base_url",
                "ECHOBOT_TTS_OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            timeout=max(1.0, _float_env("ECHOBOT_TTS_OPENAI_TIMEOUT", 60.0)),
            default_voice=_profile_text(
                tts,
                "voice",
                "ECHOBOT_TTS_OPENAI_DEFAULT_VOICE",
                DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
            ),
            response_format=os.environ.get(
                "ECHOBOT_TTS_OPENAI_RESPONSE_FORMAT",
                DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
            ).strip() or DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
            voices=_csv_env("ECHOBOT_TTS_OPENAI_VOICES"),
            instructions=os.environ.get("ECHOBOT_TTS_OPENAI_INSTRUCTIONS", "").strip(),
            extra_body=_json_env_object("ECHOBOT_TTS_OPENAI_EXTRA_BODY"),
        )
        await tts_service.replace_provider(
            "openai-compatible",
            provider,
            set_default=True,
        )
        return

    tts_service.set_default_provider(provider_name)


async def _apply_asr_model_profile(
    web_console_service: WebConsoleService,
    asr: dict[str, object],
) -> None:
    asr_service = web_console_service.asr_service
    provider_name = (
        str(asr.get("provider") or "").strip()
        or os.environ.get("ECHOBOT_ASR_PROVIDER", "").strip()
        or DEFAULT_ASR_PROVIDER
    )
    if provider_name == "openai-transcriptions":
        provider = OpenAITranscriptionsASRProvider(
            sample_rate=asr_service.sample_rate,
            api_key=_profile_text(asr, "api_key", "ECHOBOT_ASR_OPENAI_API_KEY", "EMPTY"),
            model=_profile_text(asr, "model", "ECHOBOT_ASR_OPENAI_MODEL"),
            base_url=_profile_text(
                asr,
                "base_url",
                "ECHOBOT_ASR_OPENAI_BASE_URL",
                "https://api.openai.com/v1",
            ),
            timeout=max(1.0, _float_env("ECHOBOT_ASR_OPENAI_TIMEOUT", 60.0)),
            language=_profile_text(asr, "language", "ECHOBOT_ASR_OPENAI_LANGUAGE"),
            prompt=os.environ.get("ECHOBOT_ASR_OPENAI_PROMPT", "").strip(),
            temperature=_optional_float(
                os.environ.get("ECHOBOT_ASR_OPENAI_TEMPERATURE", ""),
            ),
        )
        await asr_service.replace_asr_provider(
            "openai-transcriptions",
            provider,
        )

    await web_console_service.set_selected_asr_provider(provider_name)


def _apply_chat_model_profile_to_context(
    context: RuntimeContext,
    chat: dict[str, object],
) -> None:
    provider = build_chat_model_provider(context, chat)
    if provider is None:
        return
    context.agent.provider = provider
    context.coordinator.set_llm_provider(
        provider,
        update_decision=not context.dedicated_decision_provider,
        update_roleplay=not context.dedicated_roleplay_provider,
    )
    context.coordinator.set_generation_defaults(
        temperature=_optional_float(chat.get("temperature")),
        max_tokens=_optional_int(chat.get("max_tokens")),
    )


def build_chat_model_provider(
    context: RuntimeContext,
    chat: Mapping[str, object],
) -> OpenAICompatibleProvider | None:
    model = (
        str(chat.get("model") or "").strip()
        or os.environ.get("LLM_MODEL", "").strip()
    )
    if not model:
        return None
    base_url = (
        str(chat.get("base_url") or "").strip()
        or os.environ.get("LLM_BASE_URL", "").strip()
        or "https://api.openai.com/v1"
    )
    return OpenAICompatibleProvider(
        OpenAICompatibleSettings(
            api_key=_profile_text(chat, "api_key", "LLM_API_KEY", "EMPTY"),
            model=model,
            base_url=base_url,
            timeout=_float_env("LLM_TIMEOUT", 60.0),
            extra_body=_profile_extra_body(),
        ),
        attachment_store=context.attachment_store,
    )
