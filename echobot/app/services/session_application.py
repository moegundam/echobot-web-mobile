from __future__ import annotations

from ...orchestration import role_name_from_metadata
from ..session_metadata import (
    channel_integration_id_from_metadata,
    channel_type_from_metadata,
    set_channel_binding,
)
from .runtime_profile_composer import (
    apply_runtime_profile_for_role,
    runtime_bindings_for_role,
)


class SessionApplicationService:
    """Coordinate Session-centered operations across chat, runtime, and channels."""

    def __init__(self, runtime) -> None:
        self._runtime = runtime

    async def list_sessions(self):
        return await self._runtime.session_service.list_sessions()

    async def current_session(self):
        return await self._runtime.session_service.load_current_session()

    async def switch_session(self, session_name: str):
        return await self._runtime.session_service.switch_session(session_name)

    async def create_session(
        self,
        *,
        name: str | None = None,
        role_name: str | None = None,
        route_mode=None,
        channel_type: str | None = None,
        channel_integration_id: str | None = None,
    ):
        session = await self._runtime.session_service.create_session(name)
        if role_name:
            session = await self._runtime.chat_service.set_role(
                session.name,
                role_name,
            )
            await self._apply_bound_model_profile_for_role(
                role_name_from_metadata(session.metadata),
            )
        if route_mode is not None:
            session = await self._runtime.chat_service.set_route_mode(
                session.name,
                route_mode,
            )

        next_channel_type = channel_type or ""
        next_channel_integration_id = channel_integration_id or ""
        if not next_channel_type and not next_channel_integration_id and role_name:
            (
                next_channel_type,
                next_channel_integration_id,
            ) = await self._default_channel_binding_for_role(
                role_name_from_metadata(session.metadata),
            )
        if next_channel_type or next_channel_integration_id:
            session = await self.set_channel_binding(
                session.name,
                channel_type=next_channel_type,
                channel_integration_id=next_channel_integration_id,
            )
        return session

    async def load_session(self, session_name: str):
        return await self._runtime.session_service.load_session(session_name)

    async def rename_session(self, session_name: str, next_name: str):
        return await self._runtime.session_service.rename_session(session_name, next_name)

    async def set_role(self, session_name: str, role_name: str):
        session = await self._runtime.chat_service.set_role(
            session_name,
            role_name,
        )
        resolved_role_name = role_name_from_metadata(session.metadata)
        await self._apply_bound_model_profile_for_role(resolved_role_name)
        return await self._apply_character_channel_defaults_if_unbound(
            session.name,
            resolved_role_name,
        )

    async def set_route_mode(self, session_name: str, route_mode):
        return await self._runtime.chat_service.set_route_mode(session_name, route_mode)

    async def set_channel_binding(
        self,
        session_name: str,
        *,
        channel_type: str,
        channel_integration_id: str,
    ):
        return await self._runtime.session_service.update_session_metadata(
            session_name,
            lambda metadata: set_channel_binding(
                metadata,
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
            ),
        )

    async def delete_session(self, session_name: str) -> bool:
        return await self._runtime.session_service.delete_session(session_name)

    async def _apply_bound_model_profile_for_role(self, role_name: str) -> None:
        await apply_runtime_profile_for_role(
            self._runtime,
            role_name,
        )

    async def _apply_character_channel_defaults_if_unbound(
        self,
        session_name: str,
        role_name: str,
    ):
        session = await self._runtime.session_service.load_session(session_name)
        if channel_type_from_metadata(session.metadata) or channel_integration_id_from_metadata(
            session.metadata,
        ):
            return session

        channel_type, channel_integration_id = await self._default_channel_binding_for_role(
            role_name,
        )
        if not channel_type and not channel_integration_id:
            return session

        return await self.set_channel_binding(
            session.name,
            channel_type=channel_type,
            channel_integration_id=channel_integration_id,
        )

    async def _default_channel_binding_for_role(
        self,
        role_name: str,
    ) -> tuple[str, str]:
        bindings = await runtime_bindings_for_role(self._runtime, role_name)
        return (
            str(bindings.get("default_channel_type") or "").strip(),
            str(bindings.get("default_channel_integration_id") or "").strip(),
        )
