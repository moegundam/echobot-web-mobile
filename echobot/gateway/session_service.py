from __future__ import annotations

import asyncio

from ..channels.types import ChannelAddress, DeliveryTarget
from ..runtime.session_service import SessionLifecycleService
from ..runtime.sessions import normalize_session_name
from ..session_metadata import ChannelBindingConflictError, matches_channel_binding
from .delivery import DeliveryStore
from .route_sessions import (
    DeleteRouteSessionResult,
    RouteSessionStore,
    RouteSessionSummary,
)


class GatewaySessionService:
    def __init__(
        self,
        session_service: SessionLifecycleService,
        *,
        route_session_store: RouteSessionStore,
        delivery_store: DeliveryStore | None = None,
    ) -> None:
        self._session_service = session_service
        self._route_session_store = route_session_store
        self._delivery_store = delivery_store

    async def list_sessions(self):
        return await self._session_service.list_sessions()

    async def load_session(self, name: str):
        return await self._session_service.load_session(name)

    async def load_or_create_session(self, name: str):
        return await self._session_service.load_or_create_session(name)

    async def load_current_session(self):
        return await self._session_service.load_current_session()

    async def get_current_session_name(self) -> str | None:
        return await self._session_service.get_current_session_name()

    async def get_current_session_pointer(self) -> tuple[str | None, int]:
        return await self._session_service.get_current_session_pointer()

    async def create_session(self, name: str | None = None):
        return await self._session_service.create_session(name)

    async def update_session_metadata(self, name: str, update):
        return await self._session_service.update_session_metadata(name, update)

    async def set_current_session(self, name: str) -> None:
        await self._session_service.set_current_session(name)

    async def compare_and_set_current_session(
        self,
        expected_name: str,
        next_name: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        return await self._session_service.compare_and_set_current_session(
            expected_name,
            next_name,
            expected_revision=expected_revision,
        )

    async def session_lock(self, session_name: str):
        return await self._session_service.session_lock(session_name)

    async def switch_session(self, name: str):
        return await self._session_service.switch_session(name)

    async def rename_session(self, old_name: str, new_name: str):
        session = await self._session_service.rename_session(old_name, new_name)
        normalized_old_name = normalize_session_name(old_name)
        await asyncio.to_thread(
            self._route_session_store.replace_session_name,
            normalized_old_name,
            session.name,
        )
        if self._delivery_store is not None:
            await asyncio.to_thread(
                self._delivery_store.replace_session_name,
                normalized_old_name,
                session.name,
            )
        return session

    async def delete_session(self, name: str) -> bool:
        deleted = await self._session_service.delete_session(name)
        if not deleted:
            return False
        normalized_name = normalize_session_name(name)
        await asyncio.to_thread(self._route_session_store.remove_session, normalized_name)
        if self._delivery_store is not None:
            await asyncio.to_thread(self._delivery_store.forget, normalized_name)
        return True

    async def current_route_session(self, route_key: str) -> RouteSessionSummary:
        return await asyncio.to_thread(
            self._route_session_store.get_current_session,
            route_key,
        )

    async def bound_session_for_channel(
        self,
        *,
        channel_type: str,
        channel_integration_id: str = "",
    ):
        sessions = await self.list_sessions()
        matches = []
        for item in sessions:
            try:
                session = await self.load_session(item.name)
            except ValueError:
                continue
            if matches_channel_binding(
                session.metadata,
                channel_type=channel_type,
                channel_integration_id=channel_integration_id,
            ):
                matches.append(session)
        if len(matches) > 1:
            names = ", ".join(sorted(session.name for session in matches))
            raise ChannelBindingConflictError(
                f"Channel binding resolved to multiple Sessions: {names}",
            )
        return matches[0] if matches else None

    async def list_route_sessions(self, route_key: str) -> list[RouteSessionSummary]:
        return await asyncio.to_thread(
            self._route_session_store.list_sessions,
            route_key,
        )

    async def create_route_session(
        self,
        route_key: str,
        *,
        title: str | None = None,
    ) -> RouteSessionSummary:
        return await asyncio.to_thread(
            self._route_session_store.create_session,
            route_key,
            title=title,
        )

    async def switch_route_session(
        self,
        route_key: str,
        index: int,
    ) -> RouteSessionSummary:
        return await asyncio.to_thread(
            self._route_session_store.switch_session,
            route_key,
            index,
        )

    async def rename_current_route_session(
        self,
        route_key: str,
        title: str,
    ) -> RouteSessionSummary:
        return await asyncio.to_thread(
            self._route_session_store.rename_current_session,
            route_key,
            title,
        )

    async def touch_route_session(
        self,
        route_key: str,
        session_name: str,
        *,
        updated_at: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._route_session_store.touch_session,
            route_key,
            session_name,
            updated_at=updated_at,
        )

    async def delete_current_route_session(
        self,
        route_key: str,
    ) -> DeleteRouteSessionResult:
        result = await asyncio.to_thread(
            self._route_session_store.delete_current_session,
            route_key,
        )
        await self._session_service.purge_session(result.deleted.session_name)
        if self._delivery_store is not None:
            await asyncio.to_thread(
                self._delivery_store.forget,
                result.deleted.session_name,
            )
        return result

    async def remember_delivery_target(
        self,
        session_name: str,
        address: ChannelAddress,
        metadata: dict[str, object] | None = None,
    ) -> None:
        if self._delivery_store is None:
            raise RuntimeError("Delivery store is not configured")
        await asyncio.to_thread(
            self._delivery_store.remember,
            session_name,
            address,
            metadata,
        )

    async def forget_delivery_target(self, session_name: str) -> None:
        if self._delivery_store is None:
            raise RuntimeError("Delivery store is not configured")
        await asyncio.to_thread(self._delivery_store.forget, session_name)

    async def get_session_target(self, session_name: str) -> DeliveryTarget | None:
        if self._delivery_store is None:
            return None
        return await asyncio.to_thread(
            self._delivery_store.get_session_target,
            session_name,
        )

    async def get_latest_target(self) -> DeliveryTarget | None:
        if self._delivery_store is None:
            return None
        return await asyncio.to_thread(self._delivery_store.get_latest_target)
