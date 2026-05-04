from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ...orchestration import RoleCard
from ..schemas import (
    CharacterProfileModel,
    CharacterProfilesResponse,
    CreateCharacterProfileRequest,
    ModelProfileModel,
    UpdateCharacterProfileRequest,
)
from ..state import get_app_runtime, require_admin_user


router = APIRouter(tags=["character-profiles"])


@router.get("/character-profiles", response_model=CharacterProfilesResponse)
async def list_character_profiles(
    runtime=Depends(get_app_runtime),
) -> CharacterProfilesResponse:
    roles, profile_payload = await _load_character_profile_sources(runtime)
    return _character_profiles_response(roles, profile_payload)


@router.post("/character-profiles", response_model=CharacterProfileModel)
async def create_character_profile(
    request: CreateCharacterProfileRequest,
    runtime=Depends(get_app_runtime),
    _admin_user: str = Depends(require_admin_user),
) -> CharacterProfileModel:
    _ensure_character_services_ready(runtime)
    try:
        card = await runtime.role_service.create_role(request.name, request.prompt)
        profile_payload = await _set_or_clear_binding(
            runtime,
            card.name,
            request.model_profile_id,
        )
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_role_card(card, profile_payload)


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
    return _character_model_from_role_card(card, profile_payload)


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
    except ValueError as exc:
        raise _character_profile_http_exception(exc) from exc
    return _character_model_from_role_card(card, profile_payload)


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

    activated = await asyncio.to_thread(
        runtime.model_profile_service.activate_profile,
        profile_id,
    )
    active_profile = await asyncio.to_thread(
        runtime.model_profile_service.get_profile_for_runtime,
        activated["active_profile_id"],
    )
    await runtime.apply_model_profile(active_profile)
    return activated


def _character_profiles_response(
    roles: list[RoleCard],
    profile_payload: dict[str, Any],
) -> CharacterProfilesResponse:
    return CharacterProfilesResponse(
        active_model_profile_id=str(profile_payload.get("active_profile_id") or "a"),
        characters=[
            _character_model_from_role_card(role, profile_payload)
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
) -> CharacterProfileModel:
    bindings = profile_payload.get("role_bindings")
    if not isinstance(bindings, dict):
        bindings = {}
    profile_id = str(bindings.get(card.name) or "")
    active_profile_id = str(profile_payload.get("active_profile_id") or "a")
    effective_profile_id = profile_id or active_profile_id
    effective_profile = _profile_lookup(profile_payload).get(effective_profile_id, {})
    chat = _section(effective_profile, "chat")
    tts = _section(effective_profile, "tts")
    asr = _section(effective_profile, "asr")
    live2d = _section(effective_profile, "live2d")

    return CharacterProfileModel(
        name=card.name,
        editable=card.name != "default",
        deletable=card.name != "default",
        source_path=str(card.source_path) if card.source_path is not None else None,
        prompt=card.prompt,
        model_profile_id=profile_id,
        effective_model_profile_id=effective_profile_id,
        model_profile_label=str(effective_profile.get("label") or effective_profile_id),
        chat_model=str(chat.get("model") or ""),
        tts_voice=str(tts.get("voice") or ""),
        asr_model=str(asr.get("model") or ""),
        live2d_selection_key=str(live2d.get("selection_key") or ""),
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
