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
from ..services.character_profiles import normalize_emotion_maps
from ..services.runtime_profile_composer import (
    SPLIT_RUNTIME_PROFILE_FIELDS,
    apply_runtime_profile_for_role,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["character-profiles"])


@router.get("/character-profiles", response_model=CharacterProfilesResponse)
async def list_character_profiles(
    runtime=Depends(get_app_runtime),
) -> CharacterProfilesResponse:
    roles, profile_payload = await _load_character_profile_sources(runtime)
    return _character_profiles_response(runtime, roles, profile_payload)


@router.post("/character-profiles", response_model=CharacterProfileModel)
async def create_character_profile(
    request: CreateCharacterProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        emotion_maps = normalize_emotion_maps(request.emotion_maps)
        card = await runtime.role_service.create_role(request.name, request.prompt)
        await asyncio.to_thread(
            runtime.character_profile_settings_service.set_emotion_maps,
            card.name,
            emotion_maps,
        )
        await _set_runtime_bindings_from_request(runtime, card.name, request)
        profile_payload = await _set_or_clear_binding(
            runtime,
            card.name,
            request.model_profile_id,
        )
        profile_payload = await _activate_binding_for_current_role(
            runtime,
            card.name,
            request.model_profile_id or "",
            profile_payload,
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_role_card(
        card,
        profile_payload,
        await _emotion_maps_for_role(runtime, card.name),
        await _runtime_bindings_for_role(runtime, card.name),
    )


@router.get("/character-profiles/{role_name}", response_model=CharacterProfileModel)
async def get_character_profile(
    role_name: str,
    runtime=Depends(get_app_runtime),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        card = await runtime.role_service.get_role(role_name)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    profile_payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    return _character_model_from_role_card(
        card,
        profile_payload,
        await _emotion_maps_for_role(runtime, card.name),
        await _runtime_bindings_for_role(runtime, card.name),
    )


@router.get("/character-profiles/{role_name}/package", response_model=CharacterProfilePackageModel)
async def export_character_profile_package(
    role_name: str,
    runtime=Depends(get_app_runtime),
) -> CharacterProfilePackageModel:
    _ensure_character_services_ready(runtime)
    try:
        card = await runtime.role_service.get_role(role_name)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    profile_payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    emotion_maps = await _emotion_maps_for_role(runtime, card.name)
    character = _character_model_from_role_card(
        card,
        profile_payload,
        emotion_maps,
        await _runtime_bindings_for_role(runtime, card.name),
    )
    model_profile_snapshot = safe_model_profile_snapshot(
        _profile_lookup(profile_payload).get(character.effective_model_profile_id),
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
        card = await _create_or_update_package_role(runtime, package)
        await asyncio.to_thread(
            runtime.character_profile_settings_service.set_emotion_maps,
            card.name,
            package["emotion_maps"],
        )
        await asyncio.to_thread(
            runtime.character_profile_settings_service.set_runtime_bindings,
            card.name,
            {
                "llm_model_id": await _existing_model_profile_id(
                    runtime,
                    package["llm_model_id"],
                ),
                "voice_profile_id": await _existing_model_profile_id(
                    runtime,
                    package["voice_profile_id"],
                ),
                "live2d_model_id": await _existing_model_profile_id(
                    runtime,
                    package["live2d_model_id"],
                ),
                "default_channel_type": package["default_channel_type"],
                "default_channel_integration_id": package[
                    "default_channel_integration_id"
                ],
            },
        )
        profile_payload = await _set_or_clear_binding(
            runtime,
            card.name,
            await _existing_model_profile_id(runtime, package["model_profile_id"]),
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_role_card(
        card,
        profile_payload,
        await _emotion_maps_for_role(runtime, card.name),
        await _runtime_bindings_for_role(runtime, card.name),
    )


@router.patch("/character-profiles/{role_name}", response_model=CharacterProfileModel)
async def update_character_profile(
    role_name: str,
    request: UpdateCharacterProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        card = await runtime.role_service.get_role(role_name)
        if request.prompt is not None:
            card = await runtime.role_service.update_role(card.name, request.prompt)

        if request.emotion_maps is not None:
            emotion_maps = normalize_emotion_maps(request.emotion_maps)
            await asyncio.to_thread(
                runtime.character_profile_settings_service.set_emotion_maps,
                card.name,
                emotion_maps,
            )

        await _set_runtime_bindings_from_request(runtime, card.name, request)

        if request.clear_model_profile_binding:
            profile_payload = await asyncio.to_thread(
                runtime.model_profile_service.clear_role_binding,
                card.name,
            )
        elif request.model_profile_id is not None:
            profile_payload = await _set_or_clear_binding(
                runtime,
                card.name,
                request.model_profile_id,
            )
        else:
            profile_payload = await asyncio.to_thread(
                runtime.model_profile_service.list_profiles,
            )
        profile_payload = await _activate_binding_for_current_role(
            runtime,
            card.name,
            request.model_profile_id or "",
            profile_payload,
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_role_card(
        card,
        profile_payload,
        await _emotion_maps_for_role(runtime, card.name),
        await _runtime_bindings_for_role(runtime, card.name),
    )


@router.delete("/character-profiles/{role_name}")
async def delete_character_profile(
    role_name: str,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> dict[str, object]:
    _ensure_character_services_ready(runtime)
    try:
        card = await runtime.role_service.get_role(role_name)
        deleted_name = await runtime.role_service.delete_role(card.name)
        await asyncio.to_thread(
            runtime.model_profile_service.clear_role_binding,
            deleted_name,
        )
        await asyncio.to_thread(
            runtime.character_profile_settings_service.clear_role,
            deleted_name,
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return {
        "deleted": True,
        "name": deleted_name,
    }


async def _load_character_profile_sources(runtime) -> tuple[list[RoleCard], dict[str, Any]]:
    _ensure_character_services_ready(runtime)
    roles = await runtime.role_service.list_roles()
    profile_payload = await asyncio.to_thread(runtime.model_profile_service.list_profiles)
    return roles, profile_payload


def _ensure_character_services_ready(runtime) -> None:
    if runtime.role_service is None:
        raise HTTPException(status_code=503, detail="Role service is not ready")
    if runtime.model_profile_service is None:
        raise HTTPException(status_code=503, detail="Model profile service is not ready")
    if runtime.character_profile_settings_service is None:
        raise HTTPException(status_code=503, detail="Character profile settings service is not ready")


async def _set_or_clear_binding(
    runtime,
    role_name: str,
    model_profile_id: str | None,
) -> dict[str, Any]:
    normalized_profile_id = str(model_profile_id or "").strip()
    if not normalized_profile_id:
        return await asyncio.to_thread(
            runtime.model_profile_service.clear_role_binding,
            role_name,
        )

    payload = await asyncio.to_thread(
        runtime.model_profile_service.set_role_binding,
        role_name,
        normalized_profile_id,
    )
    return await _activate_binding_for_current_role(
        runtime,
        role_name,
        normalized_profile_id,
        payload,
    )


async def _create_or_update_package_role(runtime, package: dict[str, Any]) -> RoleCard:
    try:
        existing_card = await runtime.role_service.get_role(package["name"])
    except ValueError:
        existing_card = None

    if existing_card is not None:
        if not package["overwrite"]:
            raise ValueError(f"Role already exists: {existing_card.name}")
        return await runtime.role_service.update_role(
            existing_card.name,
            package["prompt"],
        )

    return await runtime.role_service.create_role(
        package["name"],
        package["prompt"],
    )


async def _existing_model_profile_id(runtime, profile_id: str) -> str:
    normalized_id = str(profile_id or "").strip()
    if not normalized_id:
        return ""
    try:
        await asyncio.to_thread(runtime.model_profile_service.get_profile, normalized_id)
    except ValueError:
        return ""
    return normalized_id


async def _runtime_bindings_for_role(runtime, role_name: str) -> dict[str, str]:
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.runtime_bindings_for_role,
        role_name,
    )


async def _set_runtime_bindings_from_request(
    runtime,
    role_name: str,
    request: CreateCharacterProfileRequest | UpdateCharacterProfileRequest,
) -> dict[str, str]:
    request_payload = request.model_dump(exclude_unset=True)
    updates: dict[str, str] = {}
    for field_name in (
        "llm_model_id",
        "voice_profile_id",
        "live2d_model_id",
        "default_channel_type",
        "default_channel_integration_id",
    ):
        if field_name not in request_payload:
            continue
        updates[field_name] = str(request_payload.get(field_name) or "").strip()

    for field_name in SPLIT_RUNTIME_PROFILE_FIELDS:
        if updates.get(field_name):
            await _require_model_profile(runtime, updates[field_name])

    if not updates:
        return await _runtime_bindings_for_role(runtime, role_name)
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.set_runtime_bindings,
        role_name,
        updates,
    )


async def _require_model_profile(runtime, profile_id: str) -> None:
    try:
        await asyncio.to_thread(runtime.model_profile_service.get_profile, profile_id)
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc


async def _activate_binding_for_current_role(
    runtime,
    role_name: str,
    profile_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if runtime.session_service is None or runtime.context is None:
        return payload

    current_session = await runtime.session_service.load_current_session()
    current_role_name = await runtime.context.coordinator.current_role_name(
        current_session.name,
    )
    if current_role_name != role_name:
        return payload

    applied_payload = await apply_runtime_profile_for_role(
        runtime,
        role_name,
        preferred_profile_id=profile_id,
    )
    return applied_payload or payload


def _character_profiles_response(
    runtime,
    roles: list[RoleCard],
    profile_payload: dict[str, Any],
) -> CharacterProfilesResponse:
    return CharacterProfilesResponse(
        active_model_profile_id=str(profile_payload.get("active_profile_id") or "a"),
        characters=[
            _character_model_from_role_card(
                role,
                profile_payload,
                runtime.character_profile_settings_service.emotion_maps_for_role(role.name),
                runtime.character_profile_settings_service.runtime_bindings_for_role(role.name),
            )
            for role in sorted(roles, key=lambda item: item.name)
        ],
        model_profiles=[
            ModelProfileModel(**profile)
            for profile in _profiles_list(profile_payload)
        ],
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
    profile_id = str(bindings.get(card.name) or "")
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


async def _emotion_maps_for_role(runtime, role_name: str) -> list[dict[str, str]]:
    return await asyncio.to_thread(
        runtime.character_profile_settings_service.emotion_maps_for_role,
        role_name,
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
