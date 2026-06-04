from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any

from .providers.edge import EdgeTTSProvider
from .providers.kokoro import DEFAULT_KOKORO_URL, KokoroTTSProvider
from .providers.openai_compatible import (
    DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
    DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
    OpenAICompatibleTTSProvider,
)
from .service import TTSService

DEFAULT_TTS_PROVIDER = "edge"
DEFAULT_EDGE_VOICE = "zh-CN-XiaoxiaoNeural"


def build_default_tts_service(workspace: Path) -> TTSService:
    return TTSService(
        {
            "edge": EdgeTTSProvider(default_voice=DEFAULT_EDGE_VOICE),
            "kokoro": build_default_kokoro_tts_provider(workspace),
            "openai-compatible": build_default_openai_compatible_tts_provider(),
        },
        default_provider=_env_text("ECHOBOT_TTS_PROVIDER", DEFAULT_TTS_PROVIDER),
    )


def build_default_kokoro_tts_provider(workspace: Path) -> KokoroTTSProvider:
    return KokoroTTSProvider(
        workspace,
        auto_download=_env_flag("ECHOBOT_TTS_KOKORO_AUTO_DOWNLOAD", True),
        model_root_dir=_resolve_optional_path(
            workspace,
            _env_text("ECHOBOT_TTS_KOKORO_MODEL_DIR", ""),
        ),
        provider=_env_text("ECHOBOT_TTS_KOKORO_PROVIDER", "cpu"),
        num_threads=max(1, _env_int("ECHOBOT_TTS_KOKORO_NUM_THREADS", 2)),
        default_voice=_env_text("ECHOBOT_TTS_KOKORO_DEFAULT_VOICE", "zf_001"),
        model_url=_env_text("ECHOBOT_TTS_KOKORO_URL", DEFAULT_KOKORO_URL),
        download_timeout_seconds=max(
            30.0,
            _env_float("ECHOBOT_TTS_KOKORO_DOWNLOAD_TIMEOUT_SECONDS", 600.0),
        ),
        allow_private_download=_env_flag(
            "ECHOBOT_TTS_KOKORO_ALLOW_PRIVATE_DOWNLOAD",
            False,
        ),
        length_scale=max(0.1, _env_float("ECHOBOT_TTS_KOKORO_LENGTH_SCALE", 1.0)),
        lang=_env_text("ECHOBOT_TTS_KOKORO_LANG", ""),
    )


def build_default_openai_compatible_tts_provider() -> OpenAICompatibleTTSProvider:
    return OpenAICompatibleTTSProvider(
        api_key=_env_text("ECHOBOT_TTS_OPENAI_API_KEY", "EMPTY"),
        model=_env_text("ECHOBOT_TTS_OPENAI_MODEL", ""),
        base_url=_env_text(
            "ECHOBOT_TTS_OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        timeout=max(1.0, _env_float("ECHOBOT_TTS_OPENAI_TIMEOUT", 60.0)),
        default_voice=_env_text(
            "ECHOBOT_TTS_OPENAI_DEFAULT_VOICE",
            DEFAULT_OPENAI_COMPATIBLE_TTS_VOICE,
        ),
        response_format=_env_text(
            "ECHOBOT_TTS_OPENAI_RESPONSE_FORMAT",
            DEFAULT_OPENAI_COMPATIBLE_TTS_RESPONSE_FORMAT,
        ),
        voices=_env_csv("ECHOBOT_TTS_OPENAI_VOICES"),
        instructions=_env_text("ECHOBOT_TTS_OPENAI_INSTRUCTIONS", ""),
        extra_body=_env_json_object("ECHOBOT_TTS_OPENAI_EXTRA_BODY"),
    )


def _resolve_optional_path(workspace: Path, raw_path: str) -> Path | None:
    normalized_path = raw_path.strip()
    if not normalized_path:
        return None

    candidate = Path(normalized_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return workspace / candidate


def _env_flag(name: str, default: bool) -> bool:
    raw_value = str(os.environ.get(name, "")).strip().lower()
    if not raw_value:
        return default
    return raw_value in {"1", "true", "yes", "on"}


def _env_text(name: str, default: str) -> str:
    raw_value = str(os.environ.get(name, "")).strip()
    return raw_value or default


def _env_int(name: str, default: int) -> int:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError:
        return default


def _env_csv(name: str) -> list[str]:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        return []
    return [
        item.strip()
        for item in raw_value.split(",")
        if item.strip()
    ]


def _env_json_object(name: str) -> dict[str, Any]:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}

    if not isinstance(parsed, dict):
        return {}
    return parsed
