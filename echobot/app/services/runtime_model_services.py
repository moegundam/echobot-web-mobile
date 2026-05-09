from __future__ import annotations

from .live2d_models import Live2DModelService
from .llm_models import LLMModelService
from .model_profiles import ModelProfileService
from .runtime_model_repositories import (
    LLMModelRepository,
    Live2DModelRepository,
    VoiceModelRepository,
)
from .voice_models import VoiceModelService


def build_runtime_model_services(
    model_profile_service: ModelProfileService,
) -> tuple[LLMModelService, VoiceModelService, Live2DModelService]:
    return (
        LLMModelService(LLMModelRepository(model_profile_service)),
        VoiceModelService(VoiceModelRepository(model_profile_service)),
        Live2DModelService(Live2DModelRepository(model_profile_service)),
    )


def active_runtime_profile(runtime: object) -> dict[str, object]:
    llm_service = getattr(runtime, "llm_model_service", None)
    voice_service = getattr(runtime, "voice_model_service", None)
    live2d_service = getattr(runtime, "live2d_model_service", None)
    if llm_service is None or voice_service is None or live2d_service is None:
        model_profile_service = getattr(runtime, "model_profile_service", None)
        if model_profile_service is None:
            return {}
        return model_profile_service.active_profile_for_runtime()

    llm_profile = llm_service.active_runtime_profile()
    voice_profile = voice_service.active_runtime_profile()
    live2d_profile = live2d_service.active_runtime_profile()
    return {
        "profile_id": str(llm_profile.get("profile_id") or ""),
        "label": str(llm_profile.get("label") or ""),
        "chat": llm_profile.get("chat", {}),
        "tts": voice_profile.get("tts", {}),
        "asr": voice_profile.get("asr", {}),
        "live2d": live2d_profile.get("live2d", {}),
        "updated_at": str(llm_profile.get("updated_at") or ""),
    }
