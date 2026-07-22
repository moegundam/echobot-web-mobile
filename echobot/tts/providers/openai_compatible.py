from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from ...network.http import validate_http_url

try:
    import openai
    from openai import OpenAI
except ImportError:  # pragma: no cover - dependency is installed in normal runtime
    openai = None
    OpenAI = None

from ..base import (
    SynthesizedSpeech,
    TTSProvider,
    TTSProviderStatus,
    TTSSynthesisOptions,
    VoiceOption,
)


DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE = "alloy"
DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT = "wav"
OFFICIAL_OPENAI_TTS_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
    "marin",
    "cedar",
)
_SUPPORTED_RESPONSE_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
_CONTENT_TYPE_BY_FORMAT = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}
_FORMAT_BY_CONTENT_TYPE = {
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/opus": "opus",
    "audio/aac": "aac",
    "audio/flac": "flac",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/pcm": "pcm",
    "application/octet-stream": "",
}


class OpenAICompatibleTTSProvider(TTSProvider):
    name = "openai-compatible"
    label = "OpenAI-Compatible TTS"

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        default_voice: str = DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
        response_format: str = DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
        voices: Iterable[str] | None = None,
        instructions: str = "",
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._base_url = base_url.strip()
        self._timeout = max(1.0, timeout)
        normalized_default_voice = default_voice.strip()
        self._default_voice = normalized_default_voice or DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE
        self._response_format = _normalize_response_format(response_format)
        cleaned_voice_names = _clean_voice_names(voices or [])
        self._configured_voices = (
            _voice_options_from_names(
                cleaned_voice_names,
                default_voice=self._default_voice,
            )
            if cleaned_voice_names
            else []
        )
        self._instructions = instructions.strip()
        self._extra_body = dict(extra_body or {})
        self._client = self._build_client()

    @property
    def default_voice(self) -> str:
        return self._default_voice

    def status(self) -> TTSProviderStatus:
        state, detail = self._status_state()
        return TTSProviderStatus(
            name=self.name,
            label=self.label,
            available=state == "ready",
            state=state,
            detail="" if state == "ready" else detail,
        )

    async def list_voices(self) -> list[VoiceOption]:
        state, detail = self._status_state()
        if state != "ready":
            raise RuntimeError(detail)

        if self._configured_voices:
            return list(self._configured_voices)

        try:
            voices = await asyncio.to_thread(self._fetch_voice_options_sync)
        except RuntimeError:
            return self._fallback_voice_options()

        return voices or self._fallback_voice_options()

    async def close(self) -> None:
        if self._client is None:
            return
        await asyncio.to_thread(self._client.close)

    async def synthesize(
        self,
        *,
        text: str,
        options: TTSSynthesisOptions | None = None,
    ) -> SynthesizedSpeech:
        synthesis_options = options or TTSSynthesisOptions()

        state, detail = self._status_state()
        if state != "ready":
            raise RuntimeError(detail)

        selected_voice = (
            synthesis_options.voice
            or self._default_voice
        ).strip() or self._default_voice
        return await asyncio.to_thread(
            self._synthesize_sync,
            text=text,
            voice=selected_voice,
            speed=synthesis_options.speed,
        )

    def _build_client(self):
        if OpenAI is None:
            return None
        return OpenAI(
            api_key=self._api_key or "EMPTY",
            base_url=self._base_url,
            timeout=self._timeout,
        )

    def _require_client(self):
        if self._client is None:
            raise RuntimeError(
                "OpenAI Python SDK is unavailable. Install it with: pip install openai",
            )
        return self._client

    def _status_state(self) -> tuple[str, str]:
        if OpenAI is None:
            return (
                "unavailable",
                "OpenAI Python SDK is unavailable. Install it with: pip install openai",
            )
        if not self._base_url:
            return (
                "missing",
                "OpenAI-compatible TTS provider is missing ECHOBOT_TTS_OPENAI_BASE_URL.",
            )
        if not self._model:
            return (
                "missing",
                "OpenAI-compatible TTS provider is missing ECHOBOT_TTS_OPENAI_MODEL.",
            )
        if self._uses_official_openai_endpoint() and self._api_key.upper() in {"", "EMPTY"}:
            return (
                "missing",
                "OpenAI official TTS endpoint requires ECHOBOT_TTS_OPENAI_API_KEY.",
            )
        return ("ready", "")

    def _uses_official_openai_endpoint(self) -> bool:
        parsed = urlparse(self._base_url)
        return parsed.netloc.lower() == "api.openai.com"

    def _fetch_voice_options_sync(self) -> list[VoiceOption]:
        url = validate_http_url(
            f"{self._base_url.rstrip('/')}/audio/voices",
            allow_private=True,
        )
        http_request = request.Request(
            url=url,
            headers=self._request_headers(),
            method="GET",
        )

        try:
            with request.urlopen(http_request, timeout=self._timeout) as response:  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            raise RuntimeError(f"TTS voices request failed: status={exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"TTS voices network error: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("TTS voices endpoint returned invalid JSON") from exc

        voices = payload.get("voices") if isinstance(payload, dict) else payload
        return _voice_options_from_payload(voices, default_voice=self._default_voice)

    def _fallback_voice_options(self) -> list[VoiceOption]:
        if self._uses_official_openai_endpoint():
            return _voice_options_from_names(
                OFFICIAL_OPENAI_TTS_VOICES,
                default_voice=self._default_voice,
            )
        return _voice_options_from_names([self._default_voice], default_voice=self._default_voice)

    def _request_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key or 'EMPTY'}",
            "Accept": "application/json",
        }

    def _synthesize_sync(
        self,
        *,
        text: str,
        voice: str,
        speed: float | None,
    ) -> SynthesizedSpeech:
        client = self._require_client()
        request_kwargs: dict[str, Any] = {
            "input": text,
            "model": self._model,
            "voice": voice,
        }

        if self._instructions:
            request_kwargs["instructions"] = self._instructions
        if self._response_format:
            request_kwargs["response_format"] = self._response_format

        if speed is not None:
            request_kwargs["speed"] = speed

        if self._extra_body:
            request_kwargs["extra_body"] = dict(self._extra_body)

        response = None
        try:
            response = client.audio.speech.create(**request_kwargs)
            audio_bytes = _speech_response_bytes(response)
            content_type, file_extension = _speech_response_metadata(
                response,
                default_format=self._response_format,
            )
        except Exception as exc:
            raise _tts_error(exc) from exc
        finally:
            _close_response(response)

        return SynthesizedSpeech(
            audio_bytes=audio_bytes,
            content_type=content_type,
            file_extension=file_extension,
            provider=self.name,
            voice=voice,
        )


def _normalize_response_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in _SUPPORTED_RESPONSE_FORMATS:
        return normalized
    return DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT


def _voice_options_from_payload(
    payload: Any,
    *,
    default_voice: str,
) -> list[VoiceOption]:
    if not isinstance(payload, list):
        return []

    voices: list[VoiceOption] = []
    seen: set[str] = set()
    for item in payload:
        voice = _voice_option_from_item(item)
        if voice is None:
            continue
        if voice.short_name in seen:
            continue
        seen.add(voice.short_name)
        voices.append(voice)

    if not voices:
        return []

    return _order_voice_options(voices, default_voice=default_voice)


def _voice_option_from_item(item: Any) -> VoiceOption | None:
    if isinstance(item, str):
        return _voice_option(item)

    if not isinstance(item, dict):
        return None

    short_name = str(
        item.get("short_name")
        or item.get("name")
        or item.get("id")
        or "",
    ).strip()
    if not short_name:
        return None

    display_name = str(item.get("display_name") or item.get("label") or short_name).strip()
    locale = str(item.get("locale") or item.get("language") or "").strip()
    gender = str(item.get("gender") or "").strip()
    name = str(item.get("name") or short_name).strip() or short_name
    return VoiceOption(
        name=name,
        short_name=short_name,
        locale=locale,
        gender=gender,
        display_name=display_name,
    )


def _voice_options_from_names(
    voice_names: Iterable[str],
    *,
    default_voice: str,
) -> list[VoiceOption]:
    voices: list[VoiceOption] = []
    seen: set[str] = set()
    for voice_name in voice_names:
        voice = _voice_option(voice_name)
        if voice.short_name in seen:
            continue
        seen.add(voice.short_name)
        voices.append(voice)

    if not voices:
        voices = [_voice_option(default_voice)]

    return _order_voice_options(voices, default_voice=default_voice)


def _order_voice_options(
    voices: list[VoiceOption],
    *,
    default_voice: str,
) -> list[VoiceOption]:
    normalized_default = default_voice.strip().lower()
    return sorted(
        voices,
        key=lambda item: (
            0 if item.short_name.lower() == normalized_default else 1,
            item.short_name.lower(),
        ),
    )


def _voice_option(name: str) -> VoiceOption:
    normalized_name = name.strip()
    return VoiceOption(
        name=normalized_name,
        short_name=normalized_name,
        display_name=normalized_name,
    )


def _clean_voice_names(voice_names: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for voice_name in voice_names:
        normalized_name = str(voice_name).strip()
        if normalized_name:
            cleaned.append(normalized_name)
    return cleaned


def _speech_response_bytes(response: Any) -> bytes:
    if isinstance(response, bytes):
        return response
    if isinstance(response, bytearray):
        return bytes(response)

    read_method = getattr(response, "read", None)
    if callable(read_method):
        audio_bytes = read_method()
        if isinstance(audio_bytes, bytes):
            return audio_bytes

    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content

    raise RuntimeError("TTS provider response did not contain audio bytes")


def _speech_response_metadata(
    response: Any,
    *,
    default_format: str,
) -> tuple[str, str]:
    content_type = _response_content_type(response)
    response_format = (
        _FORMAT_BY_CONTENT_TYPE.get(content_type, "")
        or default_format
        or DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT
    )
    return (
        content_type or _CONTENT_TYPE_BY_FORMAT[response_format],
        response_format,
    )


def _response_content_type(response: Any) -> str:
    raw_response = getattr(response, "response", None)
    headers = getattr(raw_response, "headers", None)
    if headers is None:
        return ""

    content_type = str(headers.get("content-type", "")).split(";", 1)[0].strip().lower()
    if content_type in _FORMAT_BY_CONTENT_TYPE:
        normalized_format = _FORMAT_BY_CONTENT_TYPE[content_type]
        if normalized_format:
            return _CONTENT_TYPE_BY_FORMAT[normalized_format]
        return ""
    return content_type


def _close_response(response: Any) -> None:
    if response is None:
        return

    close_method = getattr(response, "close", None)
    if callable(close_method):
        close_method()


def _tts_error(exc: Exception) -> RuntimeError:
    if openai is not None and isinstance(exc, openai.APIStatusError):
        status_code = getattr(exc, "status_code", "unknown")
        return RuntimeError(
            f"TTS provider request failed: status={status_code}, detail={exc}",
        )
    if openai is not None and isinstance(exc, openai.APITimeoutError):
        return RuntimeError(f"TTS provider request timed out: {exc}")
    if openai is not None and isinstance(exc, openai.APIConnectionError):
        return RuntimeError(f"TTS provider network error: {exc}")
    if openai is not None and isinstance(exc, openai.OpenAIError):
        return RuntimeError(f"TTS provider request failed: {exc}")
    if isinstance(exc, RuntimeError):
        return exc
    return RuntimeError(f"TTS provider request failed: {exc}")
