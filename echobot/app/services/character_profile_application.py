from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ...orchestration import RoleCard, normalize_role_name
from .character_profiles import normalize_emotion_maps
from .model_profile_compat import model_profiles_payload
from .runtime_profile_composer import (
    SPLIT_RUNTIME_PROFILE_FIELDS,
    apply_runtime_profile_for_role,
)
from .runtime_context_events import (
    notify_all_runtime_contexts_changed,
    notify_roles_runtime_context_changed,
)


@dataclass(slots=True)
class CharacterProfileState:
    card: RoleCard
    profile_payload: dict[str, Any]
    emotion_maps: list[dict[str, str]]
    runtime_bindings: dict[str, str]


class CharacterProfileApplicationService:
    """Coordinate character mutations across roles, settings, and runtime profiles."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def get(self, role_name: str) -> CharacterProfileState:
        card = await self._runtime.role_service.get_role(role_name)
        profile_payload = await model_profiles_payload(self._runtime)
        return await self._state(card, profile_payload)

    async def create(self, payload: dict[str, Any]) -> CharacterProfileState:
        emotion_maps = normalize_emotion_maps(payload.get("emotion_maps", []))
        card = await self._runtime.role_service.create_role(
            str(payload.get("name") or ""),
            str(payload.get("prompt") or ""),
        )
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_emotion_maps,
            card.name,
            emotion_maps,
        )
        await self._set_runtime_bindings_from_payload(card.name, payload)
        model_profile_id = str(payload.get("model_profile_id") or "")
        profile_payload = await self._set_or_clear_binding(
            card.name,
            model_profile_id,
        )
        profile_payload = await self._activate_binding_for_current_role(
            card.name,
            model_profile_id,
            profile_payload,
        )
        profile_payload = await model_profiles_payload(self._runtime)
        state = await self._state(card, profile_payload)
        await notify_roles_runtime_context_changed(
            self._runtime,
            {card.name},
            reason="character_runtime_binding_created",
        )
        return state

    async def update(
        self,
        role_name: str,
        payload: dict[str, Any],
    ) -> CharacterProfileState:
        card = await self._runtime.role_service.get_role(role_name)
        if "name" in payload and payload.get("name") is not None:
            if not str(payload.get("name") or "").strip():
                raise ValueError("Role name cannot be empty")

        requested_name = str(payload.get("name") or "").strip()
        if requested_name and normalize_role_name(requested_name) != card.name:
            old_role_name = card.name
            existing_emotion_maps = await self._emotion_maps_for_role(old_role_name)
            existing_runtime_bindings = await self._runtime_bindings_for_role(
                old_role_name,
            )
            existing_model_profile_id = await asyncio.to_thread(
                self._runtime.character_profile_settings_service.model_profile_id_for_role,
                old_role_name,
            )
            card = await self._runtime.role_service.rename_role(
                old_role_name,
                requested_name,
                prompt=payload.get("prompt"),
            )
            await self._migrate_character_settings(
                old_role_name=old_role_name,
                new_role_name=card.name,
                emotion_maps=existing_emotion_maps,
                runtime_bindings=existing_runtime_bindings,
                model_profile_id=existing_model_profile_id,
            )
        elif payload.get("prompt") is not None:
            card = await self._runtime.role_service.update_role(
                card.name,
                str(payload.get("prompt") or ""),
            )

        if payload.get("emotion_maps") is not None:
            emotion_maps = normalize_emotion_maps(payload.get("emotion_maps", []))
            await asyncio.to_thread(
                self._runtime.character_profile_settings_service.set_emotion_maps,
                card.name,
                emotion_maps,
            )

        await self._set_runtime_bindings_from_payload(card.name, payload)

        if payload.get("clear_model_profile_binding"):
            profile_payload = await self._clear_model_profile_binding(card.name)
        elif "model_profile_id" in payload and payload.get("model_profile_id") is not None:
            profile_payload = await self._set_or_clear_binding(
                card.name,
                str(payload.get("model_profile_id") or ""),
            )
        else:
            profile_payload = await model_profiles_payload(self._runtime)
        profile_payload = await self._activate_binding_for_current_role(
            card.name,
            str(payload.get("model_profile_id") or ""),
            profile_payload,
        )
        profile_payload = await model_profiles_payload(self._runtime)
        state = await self._state(card, profile_payload)
        affected_roles = {card.name}
        if requested_name and normalize_role_name(requested_name) != card.name:
            affected_roles.add(old_role_name)
        await notify_roles_runtime_context_changed(
            self._runtime,
            affected_roles,
            reason="character_runtime_binding_updated",
        )
        return state

    async def import_package(
        self,
        package: dict[str, Any],
    ) -> CharacterProfileState:
        card = await self._create_or_update_package_role(package)
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_emotion_maps,
            card.name,
            package["emotion_maps"],
        )
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_runtime_bindings,
            card.name,
            {
                "llm_model_id": await self._existing_model_profile_id(
                    package["llm_model_id"],
                ),
                "voice_profile_id": await self._existing_model_profile_id(
                    package["voice_profile_id"],
                ),
                "live2d_model_id": await self._existing_model_profile_id(
                    package["live2d_model_id"],
                ),
                "default_channel_type": package["default_channel_type"],
                "default_channel_integration_id": package[
                    "default_channel_integration_id"
                ],
            },
        )
        profile_payload = await self._set_or_clear_binding(
            card.name,
            await self._existing_model_profile_id(package["model_profile_id"]),
        )
        profile_payload = await model_profiles_payload(self._runtime)
        state = await self._state(card, profile_payload)
        await notify_roles_runtime_context_changed(
            self._runtime,
            {card.name},
            reason="character_runtime_binding_imported",
        )
        return state

    async def delete(self, role_name: str) -> str:
        card = await self._runtime.role_service.get_role(role_name)
        deleted_name = await self._runtime.role_service.delete_role(card.name)
        await self._clear_model_profile_binding(deleted_name)
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.clear_role,
            deleted_name,
        )
        # Deletion can also normalize sessions that referenced the removed role;
        # invalidate the user-scoped catalog so no session keeps stale fallback data.
        await notify_all_runtime_contexts_changed(
            self._runtime,
            reason="character_deleted",
        )
        return deleted_name

    async def _state(
        self,
        card: RoleCard,
        profile_payload: dict[str, Any],
    ) -> CharacterProfileState:
        return CharacterProfileState(
            card=card,
            profile_payload=profile_payload,
            emotion_maps=await self._emotion_maps_for_role(card.name),
            runtime_bindings=await self._runtime_bindings_for_role(card.name),
        )

    async def _set_or_clear_binding(
        self,
        role_name: str,
        model_profile_id: str | None,
    ) -> dict[str, Any]:
        normalized_profile_id = str(model_profile_id or "").strip()
        if not normalized_profile_id:
            return await self._clear_model_profile_binding(role_name)

        payload = await self._set_model_profile_binding(
            role_name,
            normalized_profile_id,
        )
        return await self._activate_binding_for_current_role(
            role_name,
            normalized_profile_id,
            payload,
        )

    async def _create_or_update_package_role(
        self,
        package: dict[str, Any],
    ) -> RoleCard:
        try:
            existing_card = await self._runtime.role_service.get_role(package["name"])
        except ValueError:
            existing_card = None

        if existing_card is not None:
            if not package["overwrite"]:
                raise ValueError(f"Role already exists: {existing_card.name}")
            return await self._runtime.role_service.update_role(
                existing_card.name,
                package["prompt"],
            )
        return await self._runtime.role_service.create_role(
            package["name"],
            package["prompt"],
        )

    async def _existing_model_profile_id(self, profile_id: str) -> str:
        normalized_id = str(profile_id or "").strip()
        if not normalized_id:
            return ""
        for service_name in (
            "llm_model_service",
            "voice_model_service",
            "live2d_model_service",
        ):
            service = getattr(self._runtime, service_name, None)
            getter = getattr(service, "get_runtime_profile", None)
            if getter is None:
                continue
            try:
                await asyncio.to_thread(getter, normalized_id)
                return normalized_id
            except ValueError:
                continue
        try:
            await asyncio.to_thread(
                self._runtime.model_profile_service.get_profile,
                normalized_id,
            )
        except ValueError:
            return ""
        return normalized_id

    async def _runtime_bindings_for_role(self, role_name: str) -> dict[str, str]:
        return await asyncio.to_thread(
            self._runtime.character_profile_settings_service.runtime_bindings_for_role,
            role_name,
        )

    async def _set_runtime_bindings_from_payload(
        self,
        role_name: str,
        payload: dict[str, Any],
    ) -> dict[str, str]:
        updates: dict[str, str] = {}
        for field_name in (
            "llm_model_id",
            "voice_profile_id",
            "live2d_model_id",
            "default_channel_type",
            "default_channel_integration_id",
        ):
            if field_name not in payload:
                continue
            updates[field_name] = str(payload.get(field_name) or "").strip()

        for field_name in SPLIT_RUNTIME_PROFILE_FIELDS:
            if updates.get(field_name):
                await self._require_model_profile(updates[field_name])

        if not updates:
            return await self._runtime_bindings_for_role(role_name)
        return await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_runtime_bindings,
            role_name,
            updates,
        )

    async def _migrate_character_settings(
        self,
        *,
        old_role_name: str,
        new_role_name: str,
        emotion_maps: list[dict[str, str]],
        runtime_bindings: dict[str, str],
        model_profile_id: str,
    ) -> None:
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_emotion_maps,
            new_role_name,
            emotion_maps,
        )
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_runtime_bindings,
            new_role_name,
            runtime_bindings,
        )
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.clear_role,
            old_role_name,
        )
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.clear_model_profile_binding,
            old_role_name,
        )
        await asyncio.to_thread(
            self._runtime.model_profile_service.clear_role_binding,
            old_role_name,
        )
        if model_profile_id:
            await self._set_or_clear_binding(
                new_role_name,
                model_profile_id,
            )

    async def _require_model_profile(self, profile_id: str) -> None:
        normalized_id = str(profile_id or "").strip()
        for service_name in (
            "llm_model_service",
            "voice_model_service",
            "live2d_model_service",
        ):
            service = getattr(self._runtime, service_name, None)
            getter = getattr(service, "get_runtime_profile", None)
            if getter is None:
                continue
            try:
                await asyncio.to_thread(getter, normalized_id)
                return
            except ValueError:
                continue
        await asyncio.to_thread(
            self._runtime.model_profile_service.get_profile,
            normalized_id,
        )

    async def _activate_binding_for_current_role(
        self,
        role_name: str,
        profile_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if self._runtime.session_service is None or self._runtime.context is None:
            return payload

        current_session = await self._runtime.session_service.load_current_session()
        current_role_name = await self._runtime.context.coordinator.current_role_name(
            current_session.name,
        )
        if current_role_name != role_name:
            return payload

        applied_payload = await apply_runtime_profile_for_role(
            self._runtime,
            role_name,
            preferred_profile_id=profile_id,
        )
        if profile_id and getattr(self._runtime, "llm_model_service", None) is not None:
            await asyncio.to_thread(
                self._runtime.llm_model_service.activate_model,
                profile_id,
            )
        return applied_payload or payload

    async def _emotion_maps_for_role(self, role_name: str) -> list[dict[str, str]]:
        return await asyncio.to_thread(
            self._runtime.character_profile_settings_service.emotion_maps_for_role,
            role_name,
        )

    async def _set_model_profile_binding(
        self,
        role_name: str,
        profile_id: str,
    ) -> dict[str, Any]:
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.set_model_profile_binding,
            role_name,
            profile_id,
        )
        return await asyncio.to_thread(
            self._runtime.model_profile_service.set_role_binding,
            role_name,
            profile_id,
        )

    async def _clear_model_profile_binding(
        self,
        role_name: str,
    ) -> dict[str, Any]:
        await asyncio.to_thread(
            self._runtime.character_profile_settings_service.clear_model_profile_binding,
            role_name,
        )
        return await asyncio.to_thread(
            self._runtime.model_profile_service.clear_role_binding,
            role_name,
        )
