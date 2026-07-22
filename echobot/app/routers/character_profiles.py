from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ...orchestration import RoleCard
from ..schemas import (
    CharacterPackageCharacterModel,
    CharacterProfileModel,
    CharacterProfilePackageModel,
    CharacterProfilesResponse,
    CreateCharacterProfileRequest,
    ModelProfileModel,
    UpdateCharacterProfileRequest,
)
from ..services.character_packages import (
    CHARACTER_PACKAGE_VERSION,
    normalize_character_package_import,
    safe_model_profile_snapshot,
)
from ..services.character_profile_application import (
    CharacterProfileApplicationService,
    CharacterProfileState,
)
from ..services.model_profile_compat import model_profiles_payload
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["character-profiles"])


@router.get("/character-profiles", response_model=CharacterProfilesResponse)
async def list_character_profiles(
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfilesResponse:
    roles, profile_payload = await _load_character_profile_sources(runtime)
    settings_by_role = await asyncio.to_thread(
        runtime.character_profile_settings_service.settings_for_roles,
        [role.name for role in roles],
    )
    return _character_profiles_response(roles, profile_payload, settings_by_role)


@router.post("/character-profiles", response_model=CharacterProfileModel)
async def create_character_profile(
    request: CreateCharacterProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        state = await _character_app(runtime).create(
            request.model_dump(mode="json"),
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_state(state)


@router.get("/character-profiles/{role_name}", response_model=CharacterProfileModel)
async def get_character_profile(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        state = await _character_app(runtime).get(role_name)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_state(state)


@router.get("/character-profiles/{role_name}/package", response_model=CharacterProfilePackageModel)
async def export_character_profile_package(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfilePackageModel:
    _ensure_character_services_ready(runtime)
    try:
        state = await _character_app(runtime).get(role_name)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    character = _character_model_from_state(state)
    model_profile_snapshot = safe_model_profile_snapshot(
        _profile_lookup(state.profile_payload).get(character.effective_model_profile_id),
    )
    return CharacterProfilePackageModel(
        package_version=CHARACTER_PACKAGE_VERSION,
        character=CharacterPackageCharacterModel(
            name=character.name,
            prompt=character.prompt,
            model_profile_id=character.model_profile_id,
            llm_model_id=character.llm_model_id,
            voice_profile_id=character.voice_profile_id,
            live2d_model_id=character.live2d_model_id,
            default_channel_type=character.default_channel_type,
            default_channel_integration_id=character.default_channel_integration_id,
            emotion_maps=character.emotion_maps,
        ),
        model_profile_snapshot=model_profile_snapshot,
    )


@router.post("/character-profiles/package", response_model=CharacterProfileModel)
async def import_character_profile_package(
    request: Request,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        request_payload = await request.json()
        package = normalize_character_package_import(request_payload)
        state = await _character_app(runtime).import_package(package)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_state(state)


@router.patch("/character-profiles/{role_name}", response_model=CharacterProfileModel)
async def update_character_profile(
    role_name: str,
    request: UpdateCharacterProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        state = await _character_app(runtime).update(
            role_name,
            request.model_dump(mode="json", exclude_unset=True),
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_state(state)


@router.delete("/character-profiles/{role_name}")
async def delete_character_profile(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, object]:
    _ensure_character_services_ready(runtime)
    try:
        deleted_name = await _character_app(runtime).delete(role_name)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return {
        "deleted": True,
        "name": deleted_name,
    }


async def _load_character_profile_sources(runtime) -> tuple[list[RoleCard], dict[str, Any]]:
    _ensure_character_services_ready(runtime)
    roles = await runtime.role_service.list_roles()
    profile_payload = await model_profiles_payload(runtime)
    return roles, profile_payload


def _ensure_character_services_ready(runtime) -> None:
    if runtime.role_service is None:
        raise HTTPException(status_code=503, detail="Role service is not ready")
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    if runtime.character_profile_settings_service is None:
        raise HTTPException(status_code=503, detail="Character profile settings service is not ready")


def _character_app(runtime) -> CharacterProfileApplicationService:
    return CharacterProfileApplicationService(runtime)


def _character_profiles_response(
    roles: list[RoleCard],
    profile_payload: dict[str, Any],
    settings_by_role: dict[str, dict[str, Any]],
) -> CharacterProfilesResponse:
    return CharacterProfilesResponse(
        active_model_profile_id=str(profile_payload.get("active_profile_id") or "a"),
        characters=[
            _character_model_from_role_card(
                role,
                profile_payload,
                settings_by_role.get(role.name, {}).get("emotion_maps", []),
                settings_by_role.get(role.name, {}).get("runtime_bindings", {}),
            )
            for role in sorted(roles, key=lambda item: item.name)
        ],
        model_profiles=[
            ModelProfileModel(**profile)
            for profile in _profiles_list(profile_payload)
        ],
    )


def _character_model_from_state(
    state: CharacterProfileState,
) -> CharacterProfileModel:
    return _character_model_from_role_card(
        state.card,
        state.profile_payload,
        state.emotion_maps,
        state.runtime_bindings,
    )


def _character_model_from_role_card(
    card: RoleCard,
    profile_payload: dict[str, Any],
    emotion_maps: list[dict[str, str]],
    runtime_bindings: dict[str, str] | None = None,
) -> CharacterProfileModel:
    runtime_bindings = runtime_bindings or {}
    bindings = profile_payload.get("role_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    profile_id = str(runtime_bindings.get("model_profile_id") or bindings.get(card.name) or "")
    active_profile_id = str(profile_payload.get("active_profile_id") or "a")
    effective_profile_id = profile_id or active_profile_id
    profiles = _profile_lookup(profile_payload)
    effective_profile = profiles.get(effective_profile_id, {})
    llm_model_id = str(runtime_bindings.get("llm_model_id") or "")
    voice_profile_id = str(runtime_bindings.get("voice_profile_id") or "")
    live2d_model_id = str(runtime_bindings.get("live2d_model_id") or "")
    llm_profile = profiles.get(llm_model_id or effective_profile_id, {})
    voice_profile = profiles.get(voice_profile_id or effective_profile_id, {})
    visual_profile = profiles.get(live2d_model_id or effective_profile_id, {})
    chat = _section(llm_profile, "chat")
    tts = _section(voice_profile, "tts")
    asr = _section(voice_profile, "asr")
    live2d = _section(visual_profile, "live2d")

    return CharacterProfileModel(
        name=card.name,
        editable=card.name != "default",
        deletable=card.name != "default",
        source_path=str(card.source_path) if card.source_path is not None else None,
        prompt=card.prompt,
        model_profile_id=profile_id,
        llm_model_id=llm_model_id,
        voice_profile_id=voice_profile_id,
        live2d_model_id=live2d_model_id,
        default_channel_type=str(runtime_bindings.get("default_channel_type") or ""),
        default_channel_integration_id=str(
            runtime_bindings.get("default_channel_integration_id") or "",
        ),
        effective_model_profile_id=effective_profile_id,
        model_profile_label=str(effective_profile.get("label") or effective_profile_id),
        chat_model=str(chat.get("model") or ""),
        tts_voice=str(tts.get("voice") or ""),
        asr_model=str(asr.get("model") or ""),
        live2d_selection_key=str(live2d.get("selection_key") or ""),
        emotion_maps=emotion_maps,
    )


def _profile_lookup(profile_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(profile.get("profile_id") or ""): profile
        for profile in _profiles_list(profile_payload)
        if isinstance(profile, dict)
    }


def _profiles_list(profile_payload: dict[str, Any]) -> list[dict[str, Any]]:
    profiles = profile_payload.get("profiles")
    if not isinstance(profiles, list):
        return []
    return [profile for profile in profiles if isinstance(profile, dict)]


def _section(profile: dict[str, Any], section_name: str) -> dict[str, Any]:
    value = profile.get(section_name)
    return value if isinstance(value, dict) else {}


def _character_profile_http_exception(exc: ValueError) -> HTTPException:
    message = str(exc)
    lower = message.lower()
    if "unknown role" in lower or "not found" in lower:
        return HTTPException(status_code=404, detail=message)
    if "unknown model profile" in lower:
        return HTTPException(status_code=404, detail=message)
    if "already exists" in lower:
        return HTTPException(status_code=409, detail=message)
    return HTTPException(status_code=400, detail=message)
