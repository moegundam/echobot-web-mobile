from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from ...models import LLMMessage, message_content_to_text
from ...providers.openai_compatible import (
    OpenAICompatibleProvider,
    OpenAICompatibleSettings,
)
from ..schemas import (
    CreateModelProfileRequest,
    ModelProfileModel,
    ModelProfilesResponse,
    SetRoleModelProfileBindingRequest,
    UpdateModelProfileRequest,
)
from ..services.model_profile_compat import (
    model_profile_role_bindings,
    model_profiles_payload,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["model-profiles"])


@router.get("/model-profiles", response_model=ModelProfilesResponse)
async def list_model_profiles(runtime=Depends(get_app_runtime)) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    payload = await model_profiles_payload(runtime)
    return ModelProfilesResponse(**payload)


@router.post("/model-profiles", response_model=ModelProfileModel, deprecated=True)
async def create_model_profile(
    request: CreateModelProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy model-profile creation is disabled. Use /api/llm-models, /api/voice-models, and /api/live2d-models instead.",
    )


@router.get("/model-profiles/role-bindings", response_model=dict[str, str])
async def list_model_profile_role_bindings(
    runtime=Depends(get_app_runtime),
) -> dict[str, str]:
    _ensure_model_profiles_ready(runtime)
    return await model_profile_role_bindings(runtime)


@router.put(
    "/model-profiles/role-bindings/{role_name}",
    response_model=ModelProfilesResponse,
)
async def set_model_profile_role_binding(
    role_name: str,
    request: SetRoleModelProfileBindingRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy role-binding writes are disabled. Use /api/character-profiles/{role_name} with model_profile_id instead.",
    )


@router.delete(
    "/model-profiles/role-bindings/{role_name}",
    response_model=ModelProfilesResponse,
)
async def clear_model_profile_role_binding(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy role-binding writes are disabled. Use /api/character-profiles/{role_name} with clear_model_profile_binding instead.",
    )


@router.get("/model-profiles/{profile_id}", response_model=ModelProfileModel)
async def get_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    payload = await model_profiles_payload(runtime)
    for profile in payload.get("profiles", []):
        if isinstance(profile, dict) and profile.get("profile_id") == profile_id:
            return ModelProfileModel(**profile)
    raise _model_profile_http_exception(ValueError(f"Unknown model profile: {profile_id}"))


@router.patch("/model-profiles/{profile_id}", response_model=ModelProfileModel, deprecated=True)
async def update_model_profile(
    profile_id: str,
    request: UpdateModelProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfileModel:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy model-profile updates are disabled. Use /api/llm-models, /api/voice-models, and /api/live2d-models instead.",
    )


@router.post("/model-profiles/{profile_id}/activate", response_model=ModelProfilesResponse, deprecated=True)
async def activate_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy model-profile activation is disabled. Use /api/llm-models/{id}/activate, /api/voice-models/{id}/activate, or /api/live2d-models/{id}/activate instead.",
    )


@router.post("/llm-models/{model_id}/smoke")
async def smoke_llm_model(
    model_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, object]:
    _ensure_model_profiles_ready(runtime)
    if runtime.context is None:
        raise HTTPException(status_code=503, detail="EchoBot runtime is not ready")
    try:
        if runtime.llm_model_service is not None:
            profile = await asyncio.to_thread(
                runtime.llm_model_service.get_runtime_profile,
                model_id,
            )
        else:
            profile = await asyncio.to_thread(
                runtime.model_profile_service.get_profile_for_runtime,
                model_id,
            )
        chat = profile.get("chat") if isinstance(profile, dict) else None
        if not isinstance(chat, dict):
            raise ValueError("LLM model profile is missing chat settings")
        provider_name = str(chat.get("provider") or "openai-compatible").strip()
        model = str(chat.get("model") or "").strip()
        if not model:
            raise ValueError("LLM model is required before smoke testing")
        base_url = str(chat.get("base_url") or "https://api.openai.com/v1").strip()
        provider = OpenAICompatibleProvider(
            OpenAICompatibleSettings(
                api_key=str(chat.get("api_key") or "EMPTY").strip() or "EMPTY",
                model=model,
                base_url=base_url,
                timeout=10.0,
            ),
            attachment_store=runtime.context.attachment_store,
        )
        result = await provider.generate(
            [LLMMessage(role="user", content="Reply with exactly: pong")],
            temperature=0,
            max_tokens=32,
        )
    except ValueError as exc:
        raise _model_profile_http_exception(exc) from exc
    except RuntimeError as exc:
        return {
            "ok": False,
            "model_id": model_id,
            "status": "failed",
            "error": str(exc),
        }

    text = message_content_to_text(result.message.content).strip()
    return {
        "ok": True,
        "model_id": model_id,
        "status": "ready",
        "provider": provider_name,
        "model": result.model,
        "response": text,
    }


@router.delete("/model-profiles/{profile_id}", response_model=ModelProfilesResponse, deprecated=True)
async def delete_model_profile(
    profile_id: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> ModelProfilesResponse:
    _ensure_model_profiles_ready(runtime)
    raise _legacy_model_profile_write_gone(
        "Legacy model-profile deletion is disabled. Use /api/llm-models, /api/voice-models, and /api/live2d-models domain delete endpoints instead.",
    )


def _ensure_model_profiles_ready(runtime) -> None:
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")


def _legacy_model_profile_write_gone(detail: str) -> HTTPException:
    return HTTPException(
        status_code=410,
        detail=detail,
        headers={
            "Deprecation": "true",
            "X-EchoBot-Compatibility-Path": "model-profiles",
            "X-EchoBot-Replacement-Path": "domain-runtime-profiles",
        },
    )


def _model_profile_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    if "unknown model profile" in message.lower():
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=400, detail=message)
