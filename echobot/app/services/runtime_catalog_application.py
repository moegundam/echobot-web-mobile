from __future__ import annotations

import asyncio
from typing import Any

from .session_runtime_context import (
    SessionRuntimeContextError,
    apply_runtime_override_if_current_session,
    ensure_runtime_services_ready,
    runtime_profile_payload,
    validate_runtime_profile_ids,
)
from .runtime_context_events import (
    notify_all_runtime_contexts_changed,
    notify_session_runtime_context_changed,
)


class RuntimeCatalogApplicationService:
    """Coordinate runtime catalog mutations that span multiple stores."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def delete_llm_model(self, model_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._runtime.llm_model_service.delete_model,
            model_id,
        )
        settings_service = self._runtime.character_profile_settings_service
        if settings_service is not None:
            await asyncio.to_thread(
                settings_service.clear_runtime_bindings_for_profile,
                model_id,
                ("model_profile_id", "llm_model_id"),
            )
        await self._clear_session_runtime_profile_references(
            model_id,
            ("model_profile_id", "llm_model_id"),
        )
        await notify_all_runtime_contexts_changed(
            self._runtime,
            reason="llm_catalog_updated",
        )
        return payload

    async def delete_voice_profile(self, profile_id: str) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._runtime.voice_model_service.delete_profile,
            profile_id,
        )
        settings_service = self._runtime.character_profile_settings_service
        if settings_service is not None:
            await asyncio.to_thread(
                settings_service.clear_runtime_bindings_for_profile,
                profile_id,
                ("voice_profile_id",),
            )
        await self._clear_session_runtime_profile_references(
            profile_id,
            ("voice_profile_id",),
        )
        await notify_all_runtime_contexts_changed(
            self._runtime,
            reason="voice_catalog_updated",
        )
        return payload

    async def delete_live2d_model(
        self,
        model_id: str,
        catalog: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = await asyncio.to_thread(
            self._runtime.live2d_model_service.delete_model,
            model_id,
            catalog,
        )
        settings_service = self._runtime.character_profile_settings_service
        if settings_service is not None:
            await asyncio.to_thread(
                settings_service.clear_runtime_bindings_for_profile,
                model_id,
                ("live2d_model_id",),
            )
        await self._clear_session_runtime_profile_references(
            model_id,
            ("live2d_model_id",),
        )
        await notify_all_runtime_contexts_changed(
            self._runtime,
            reason="live2d_catalog_updated",
        )
        return payload

    async def update_session_runtime_overrides(
        self,
        session_name: str,
        override_payload: dict[str, Any],
    ) -> str:
        ensure_runtime_services_ready(self._runtime)
        override_service = getattr(
            self._runtime,
            "session_runtime_override_service",
            None,
        )
        if override_service is None:
            raise SessionRuntimeContextError(
                503,
                "Session runtime override service is not ready",
            )

        try:
            session = await self._runtime.session_service.load_session(session_name)
        except ValueError as exc:
            raise SessionRuntimeContextError(404, str(exc)) from exc

        profile_payload = await runtime_profile_payload(self._runtime)
        override_role_name = str(override_payload.get("role_name") or "").strip()
        if override_role_name:
            try:
                self._runtime.context.role_registry.require(override_role_name)
            except ValueError as exc:
                raise SessionRuntimeContextError(404, str(exc)) from exc
        validate_runtime_profile_ids(
            profile_payload,
            [
                str(override_payload.get("model_profile_id") or "").strip(),
                str(override_payload.get("llm_model_id") or "").strip(),
                str(override_payload.get("voice_profile_id") or "").strip(),
                str(override_payload.get("live2d_model_id") or "").strip(),
            ],
        )

        try:
            await asyncio.to_thread(
                override_service.set_override,
                session.name,
                override_payload,
            )
            await apply_runtime_override_if_current_session(
                self._runtime,
                session.name,
            )
        except SessionRuntimeContextError:
            raise
        except ValueError as exc:
            raise SessionRuntimeContextError(400, str(exc)) from exc
        await notify_session_runtime_context_changed(
            self._runtime,
            session.name,
            reason="session_runtime_override_updated",
        )
        return session.name

    async def _clear_session_runtime_profile_references(
        self,
        profile_id: str,
        field_names: tuple[str, ...],
    ) -> None:
        service = getattr(self._runtime, "session_runtime_override_service", None)
        if service is None:
            return
        await asyncio.to_thread(
            service.clear_profile_references,
            profile_id,
            field_names,
        )
