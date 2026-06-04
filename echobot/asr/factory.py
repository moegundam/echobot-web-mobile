from __future__ import annotations

import os
from pathlib import Path

from .providers import (
    DEFAULT_SENSE_VOICE_MODEL_URL,
    OpenAITranscriptionsASRProvider,
    SherpaSenseVoiceASRProvider,
)
from .service import ASRService
from .vad import DEFAULT_SILERO_VAD_MODEL_URL, SileroVADProvider


DEFAULT_ASR_PROVIDER = "sherpa-sense-voice"
DEFAULT_VAD_PROVIDER = "silero"


def build_default_asr_service(workspace: Path) -> ASRService:
    sample_rate = _env_int("ECHOBOT_ASR_SAMPLE_RATE", 16000)
    asr_providers = {
        "sherpa-sense-voice": SherpaSenseVoiceASRProvider(
            workspace,
            sample_rate=sample_rate,
            auto_download=_env_flag("ECHOBOT_ASR_SHERPA_AUTO_DOWNLOAD", True),
            model_root_dir=_resolve_optional_path(
                workspace,
                _env_text("ECHOBOT_ASR_SHERPA_MODEL_DIR", ""),
            ),
            execution_provider=_env_text(
                "ECHOBOT_ASR_SHERPA_EXECUTION_PROVIDER",
                "cpu",
            ),
            num_threads=max(1, _env_int("ECHOBOT_ASR_SHERPA_NUM_THREADS", 2)),
            language=_env_text("ECHOBOT_ASR_SHERPA_LANGUAGE", "auto"),
            use_itn=_env_flag("ECHOBOT_ASR_SHERPA_USE_ITN", False),
            model_url=_env_text(
                "ECHOBOT_ASR_SHERPA_MODEL_URL",
                DEFAULT_SENSE_VOICE_MODEL_URL,
            ),
            download_timeout_seconds=max(
                30.0,
                _env_float("ECHOBOT_ASR_SHERPA_DOWNLOAD_TIMEOUT_SECONDS", 600.0),
            ),
            allow_private_download=_env_flag(
                "ECHOBOT_ASR_SHERPA_ALLOW_PRIVATE_DOWNLOAD",
                False,
            ),
        ),
        "openai-transcriptions": build_default_openai_transcriptions_asr_provider(),
    }
    vad_providers = {
        "silero": SileroVADProvider(
            workspace,
            sample_rate=sample_rate,
            auto_download=_env_flag("ECHOBOT_VAD_SILERO_AUTO_DOWNLOAD", True),
            model_root_dir=_resolve_optional_path(
                workspace,
                _env_text("ECHOBOT_VAD_SILERO_MODEL_DIR", ""),
            ),
            execution_provider=_env_text(
                "ECHOBOT_VAD_SILERO_EXECUTION_PROVIDER",
                "cpu",
            ),
            model_url=_env_text(
                "ECHOBOT_VAD_SILERO_MODEL_URL",
                DEFAULT_SILERO_VAD_MODEL_URL,
            ),
            download_timeout_seconds=max(
                30.0,
                _env_float("ECHOBOT_VAD_SILERO_DOWNLOAD_TIMEOUT_SECONDS", 600.0),
            ),
            allow_private_download=_env_flag(
                "ECHOBOT_VAD_SILERO_ALLOW_PRIVATE_DOWNLOAD",
                False,
            ),
            threshold=_env_float("ECHOBOT_VAD_SILERO_THRESHOLD", 0.5),
            min_silence_duration=_env_float(
                "ECHOBOT_VAD_SILERO_MIN_SILENCE_SECONDS",
                0.4,
            ),
            min_speech_duration=_env_float(
                "ECHOBOT_VAD_SILERO_MIN_SPEECH_SECONDS",
                0.2,
            ),
            max_speech_duration=max(
                1.0,
                _env_float("ECHOBOT_VAD_SILERO_MAX_SPEECH_SECONDS", 30.0),
            ),
            window_size=max(1, _env_int("ECHOBOT_VAD_SILERO_WINDOW_SIZE", 512)),
        ),
    }
    return ASRService(
        asr_providers,
        vad_providers,
        selected_asr_provider=_env_text("ECHOBOT_ASR_PROVIDER", DEFAULT_ASR_PROVIDER),
        selected_vad_provider=_optional_provider_name(
            _env_text("ECHOBOT_VAD_PROVIDER", DEFAULT_VAD_PROVIDER),
        ),
        sample_rate=sample_rate,
    )


def build_default_openai_transcriptions_asr_provider() -> OpenAITranscriptionsASRProvider:
    return OpenAITranscriptionsASRProvider(
        sample_rate=_env_int("ECHOBOT_ASR_SAMPLE_RATE", 16000),
        api_key=_env_text("ECHOBOT_ASR_OPENAI_API_KEY", "EMPTY"),
        model=_env_text("ECHOBOT_ASR_OPENAI_MODEL", ""),
        base_url=_env_text(
            "ECHOBOT_ASR_OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ),
        timeout=max(1.0, _env_float("ECHOBOT_ASR_OPENAI_TIMEOUT", 60.0)),
        language=_env_text("ECHOBOT_ASR_OPENAI_LANGUAGE", ""),
        prompt=_env_text("ECHOBOT_ASR_OPENAI_PROMPT", ""),
        temperature=_env_optional_float("ECHOBOT_ASR_OPENAI_TEMPERATURE"),
    )


def _optional_provider_name(name: str) -> str | None:
    normalized_name = name.strip().lower()
    if normalized_name in {"", "none", "off", "disabled"}:
        return None
    return name.strip()


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


def _env_optional_float(name: str) -> float | None:
    raw_value = str(os.environ.get(name, "")).strip()
    if not raw_value:
        return None
    try:
        return float(raw_value)
    except ValueError:
        return None
