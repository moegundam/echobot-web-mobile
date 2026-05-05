from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from ..orchestration import ConversationCoordinator
from .sessions import ChatSession, SessionInfo, SessionStore, normalize_session_name


class SessionLifecycleService:
    def __init__(
        self,
        session_store: SessionStore,
        agent_session_store: SessionStore | None = None,
        *,
        coordinator: ConversationCoordinator | None = None,
    ) -> None:
        self._session_store = session_store
        self._agent_session_store = agent_session_store
        self._coordinator = coordinator

    async def list_sessions(self) -> list[SessionInfo]:
        return await asyncio.to_thread(self._session_store.list_sessions)

    async def load_session(self, name: str) -> ChatSession:
        return await asyncio.to_thread(self._session_store.load_session, name)

    async def load_or_create_session(self, name: str) -> ChatSession:
        session = await asyncio.to_thread(
            self._session_store.load_or_create_session,
            name,
        )
        await self._restore_session_state(session.name)
        return session

    async def load_current_session(self) -> ChatSession:
        return await asyncio.to_thread(self._session_store.load_current_session)

    async def create_session(self, name: str | None = None) -> ChatSession:
        session = await asyncio.to_thread(self._session_store.create_session, name)
        await self._restore_session_state(session.name)
        return session

    async def update_session_metadata(
        self,
        name: str,
        update: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> ChatSession:
        session = await self.load_session(name)
        session.metadata = update(dict(session.metadata or {}))
        await asyncio.to_thread(self._session_store.save_session, session)
        await self._restore_session_state(session.name)
        return session

    async def set_current_session(self, name: str) -> None:
        normalized_name = normalize_session_name(name)
        await asyncio.to_thread(
            self._session_store.set_current_session,
            normalized_name,
        )

    async def switch_session(self, name: str) -> ChatSession:
        session = await self.load_session(name)
        await self.set_current_session(session.name)
        await self._restore_session_state(session.name)
        return session

    async def rename_session(self, old_name: str, new_name: str) -> ChatSession:
        normalized_old_name = normalize_session_name(old_name)
        normalized_new_name = normalize_session_name(new_name)

        session = await self.load_session(normalized_old_name)
        if normalized_old_name == normalized_new_name:
            return session
        if await asyncio.to_thread(self._session_store.has_session, normalized_new_name):
            raise ValueError(f"Session already exists: {normalized_new_name}")

        await self._cancel_session_jobs(normalized_old_name)
        session = await asyncio.to_thread(
            self._session_store.rename_session,
            normalized_old_name,
            normalized_new_name,
        )
        if self._agent_session_store is not None:
            try:
                await asyncio.to_thread(
                    self._agent_session_store.rename_session,
                    normalized_old_name,
                    normalized_new_name,
                )
            except ValueError:
                pass
        await self._restore_session_state(session.name)
        return session

    async def delete_session(self, name: str) -> bool:
        normalized_name = normalize_session_name(name)
        try:
            await self.load_session(normalized_name)
        except ValueError:
            return False

        await self.purge_session(normalized_name)
        return True

    async def purge_session(self, name: str) -> None:
        normalized_name = normalize_session_name(name)
        await self._delete_session_records(normalized_name)

    async def _delete_session_records(self, session_name: str) -> None:
        if self._coordinator is not None:
            await self._coordinator.mark_session_deleted(session_name)
        await self._cancel_session_jobs(session_name)
        current_name = await asyncio.to_thread(
            self._session_store.get_current_session_name,
        )
        await asyncio.to_thread(
            self._session_store.delete_session,
            session_name,
        )
        if self._agent_session_store is not None:
            await asyncio.to_thread(
                self._agent_session_store.delete_session,
                session_name,
            )

        if current_name != session_name:
            return

        remaining = await self.list_sessions()
        if remaining:
            await self.set_current_session(remaining[0].name)
            return

        replacement = await self.create_session("default")
        await self.set_current_session(replacement.name)

    async def _cancel_session_jobs(self, session_name: str) -> None:
        if self._coordinator is None:
            return
        await self._coordinator.cancel_jobs_for_session(session_name)

    async def _restore_session_state(self, session_name: str) -> None:
        if self._coordinator is None:
            return
        await self._coordinator.restore_session(session_name)


SessionService = SessionLifecycleService
