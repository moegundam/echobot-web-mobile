from __future__ import annotations

import asyncio

from .base import (
    SynthesizedSpeech,
    TTSProvider,
    TTSProviderStatus,
    VoiceOption,
)
from .synthesis import build_tts_synthesis_options
from .text import normalize_text_for_tts


class TTSService:
    def __init__(
        self,
        providers: dict[str, TTSProvider],
        *,
        default_provider: str = "edge",
    ) -> None:
        if not providers:
            raise ValueError("At least one TTS provider is required")
        if default_provider not in providers:
            raise ValueError(f"Unknown default TTS provider: {default_provider}")

        self._providers = dict(providers)
        self._default_provider = default_provider

    @property
    def default_provider(self) -> str:
        return self._default_provider

    async def replace_provider(
        self,
        provider_name: str,
        provider: TTSProvider,
        *,
        set_default: bool = False,
    ) -> None:
        normalized_name = provider_name.strip()
        if not normalized_name:
            raise ValueError("TTS provider name must not be empty")

        previous_provider = self._providers.get(normalized_name)
        self._providers[normalized_name] = provider
        if set_default:
            self.set_default_provider(normalized_name)
        if previous_provider is not None and previous_provider is not provider:
            await previous_provider.close()

    def set_default_provider(self, provider_name: str) -> None:
        normalized_name = provider_name.strip()
        if not normalized_name:
            raise ValueError("TTS provider name must not be empty")
        if normalized_name not in self._providers:
            raise ValueError(f"Unknown TTS provider: {normalized_name}")
        self._default_provider = normalized_name

    def provider_names(self) -> list[str]:
        return sorted(self._providers)

    def default_voice_for(self, provider_name: str | None = None) -> str:
        provider = self._provider_for(provider_name)
        return provider.default_voice

    def provider_status(self, provider_name: str) -> TTSProviderStatus:
        provider = self._provider_for(provider_name)
        return provider.status()

    def providers_status(self) -> list[TTSProviderStatus]:
        return [
            self.provider_status(provider_name)
            for provider_name in self.provider_names()
        ]

    async def list_voices(
        self,
        provider_name: str | None = None,
    ) -> list[VoiceOption]:
        provider = self._provider_for(provider_name)
        return await provider.list_voices()

    async def synthesize(
        self,
        *,
        text: str,
        provider_name: str | None = None,
        voice: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
        pitch: str | None = None,
    ) -> SynthesizedSpeech:
        provider = self._provider_for(provider_name)
        normalized_text = normalize_text_for_tts(text)
        if not normalized_text:
            raise ValueError("TTS text must not be empty")
        options = build_tts_synthesis_options(
            voice=voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        )
        return await provider.synthesize(
            text=normalized_text,
            options=options,
        )

    async def close(self) -> None:
        await asyncio.gather(
            *(provider.close() for provider in self._providers.values()),
            return_exceptions=True,
        )

    def _provider_for(self, provider_name: str | None) -> TTSProvider:
        name = provider_name or self._default_provider
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ValueError(f"Unknown TTS provider: {name}") from exc
