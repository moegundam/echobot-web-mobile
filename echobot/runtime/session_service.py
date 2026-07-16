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

    async def get_current_session_name(self) -> str | None:
        return await asyncio.to_thread(self._session_store.get_current_session_name)

    async def get_current_session_pointer(self) -> tuple[str | None, int]:
        return await asyncio.to_thread(
            self._session_store.get_current_session_pointer,
        )

    async def create_session(self, name: str | None = None) -> ChatSession:
        session = await asyncio.to_thread(self._session_store.create_session, name)
        await self._restore_session_state(session.name)
        return session

    async def update_session_metadata(
        self,
        name: str,
        update: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> ChatSession:
        normalized_name = normalize_session_name(name)
        lock = await self._session_mutation_lock(normalized_name)
        if lock is None:
            deleted, deletion_generation = await self._session_deletion_state(
                normalized_name,
            )
            if deleted:
                raise RuntimeError(f"Session is deleted: {normalized_name}")
            session = await self._update_session_metadata_unlocked(
                normalized_name,
                update,
            )
            await self._restore_session_state(
                session.name,
                expected_deletion_generation=deletion_generation,
            )
        else:
            async with lock:
                deleted, deletion_generation = await self._session_deletion_state(
                    normalized_name,
                )
                if deleted:
                    raise RuntimeError(f"Session is deleted: {normalized_name}")
                session = await self._update_session_metadata_unlocked(
                    normalized_name,
                    update,
                )
                await self._restore_session_state(
                    session.name,
                    expected_deletion_generation=deletion_generation,
                )
        return session

    async def _update_session_metadata_unlocked(
        self,
        name: str,
        update: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> ChatSession:
        session = await asyncio.to_thread(self._session_store.load_session, name)
        session.metadata = update(dict(session.metadata or {}))
        await asyncio.to_thread(self._session_store.save_session, session)
        return session

    async def set_current_session(self, name: str) -> None:
        normalized_name = normalize_session_name(name)
        await asyncio.to_thread(
            self._session_store.set_current_session,
            normalized_name,
        )

    async def compare_and_set_current_session(
        self,
        expected_name: str,
        next_name: str | None,
        *,
        expected_revision: int | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._session_store.compare_and_set_current_session,
            expected_name,
            next_name,
            expected_revision=expected_revision,
        )

    async def switch_session(self, name: str) -> ChatSession:
        normalized_name = normalize_session_name(name)
        lock = await self._session_mutation_lock(normalized_name)
        if lock is None:
            return await self._switch_session_unlocked(normalized_name)
        async with lock:
            return await self._switch_session_unlocked(normalized_name)

    async def _switch_session_unlocked(self, session_name: str) -> ChatSession:
        deleted, deletion_generation = await self._session_deletion_state(session_name)
        if deleted:
            raise RuntimeError(f"Session is deleted: {session_name}")
        session = await self.load_session(session_name)
        deleted, current_generation = await self._session_deletion_state(session_name)
        if deleted or current_generation != deletion_generation:
            raise RuntimeError(f"Session is deleted: {session_name}")
        await self.set_current_session(session.name)
        await self._restore_session_state(
            session.name,
            expected_deletion_generation=deletion_generation,
        )
        return session

    async def session_lock(self, session_name: str):
        lock = await self._session_mutation_lock(normalize_session_name(session_name))
        if lock is None:
            raise RuntimeError("Session coordinator is not configured")
        return lock

    async def rename_session(self, old_name: str, new_name: str) -> ChatSession:
        normalized_old_name = normalize_session_name(old_name)
        normalized_new_name = normalize_session_name(new_name)

        deletion_generation = await self._mark_session_deleted_for_rename(
            normalized_old_name,
            normalized_new_name,
        )
        try:
            await self._cancel_session_jobs(normalized_old_name)
        except BaseException:
            await self._restore_session_state(
                normalized_old_name,
                expected_deletion_generation=deletion_generation,
            )
            raise
        lock = await self._session_mutation_lock(normalized_old_name)
        if lock is None:
            try:
                session = await self._rename_session_unlocked(
                    normalized_old_name,
                    normalized_new_name,
                )
            except BaseException:
                await self._restore_session_state(
                    normalized_old_name,
                    expected_deletion_generation=deletion_generation,
                )
                raise
        else:
            async with lock:
                try:
                    session = await self._rename_session_unlocked(
                        normalized_old_name,
                        normalized_new_name,
                    )
                except BaseException:
                    await self._restore_session_state(
                        normalized_old_name,
                        expected_deletion_generation=deletion_generation,
                    )
                    raise
        await self._restore_session_state(session.name)
        return session

    async def _mark_session_deleted_for_rename(
        self,
        old_name: str,
        new_name: str,
    ) -> int | None:
        if old_name == new_name or self._coordinator is None:
            return None
        return await self._coordinator.mark_session_deleted(old_name)

    async def _rename_session_unlocked(
        self,
        old_name: str,
        new_name: str,
    ) -> ChatSession:
        session = await asyncio.to_thread(self._session_store.load_session, old_name)
        if old_name == new_name:
            return session
        session = await asyncio.to_thread(
            self._session_store.rename_session,
            old_name,
            new_name,
        )
        if self._agent_session_store is not None:
            try:
                await asyncio.to_thread(
                    self._agent_session_store.rename_session,
                    old_name,
                    new_name,
                )
            except ValueError:
                pass
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
        deletion_generation = await self._mark_session_deleted(session_name)
        try:
            await self._cancel_session_jobs(session_name)
        except BaseException:
            await self._restore_session_state(
                session_name,
                expected_deletion_generation=deletion_generation,
            )
            raise
        lock = await self._session_mutation_lock(session_name)
        if lock is None:
            try:
                current_name = await self._delete_session_records_unlocked(session_name)
            except BaseException:
                await self._restore_session_state(
                    session_name,
                    expected_deletion_generation=deletion_generation,
                )
                raise
        else:
            async with lock:
                try:
                    current_name = await self._delete_session_records_unlocked(
                        session_name,
                    )
                except BaseException:
                    await self._restore_session_state(
                        session_name,
                        expected_deletion_generation=deletion_generation,
                    )
                    raise

        if current_name != session_name:
            return

        replacement = await asyncio.to_thread(
            self._session_store.repair_current_session_after_deletion,
            session_name,
        )
        if replacement is not None:
            await self._restore_existing_session_state(replacement.name)

    async def _mark_session_deleted(self, session_name: str) -> int | None:
        if self._coordinator is None:
            return None
        return await self._coordinator.mark_session_deleted(session_name)

    async def _delete_session_records_unlocked(self, session_name: str) -> str | None:
        current_name = await asyncio.to_thread(
            self._session_store.get_current_session_name,
        )
        await asyncio.to_thread(self._session_store.delete_session, session_name)
        if self._agent_session_store is not None:
            await asyncio.to_thread(
                self._agent_session_store.delete_session,
                session_name,
            )
        return current_name

    async def _cancel_session_jobs(self, session_name: str) -> None:
        if self._coordinator is None:
            return
        await self._coordinator.cancel_jobs_for_session(session_name)

    async def _restore_session_state(
        self,
        session_name: str,
        *,
        expected_deletion_generation: int | None = None,
    ) -> None:
        if self._coordinator is None:
            return
        if expected_deletion_generation is None:
            await self._coordinator.restore_session(session_name)
            return
        await self._coordinator.restore_session(
            session_name,
            expected_deletion_generation=expected_deletion_generation,
        )

    async def _session_deletion_state(self, session_name: str) -> tuple[bool, int]:
        if self._coordinator is None:
            return False, 0
        state_reader = getattr(self._coordinator, "session_deletion_state", None)
        if state_reader is None:
            return False, 0
        return await state_reader(session_name)

    async def _restore_existing_session_state(self, session_name: str) -> None:
        lock = await self._session_mutation_lock(session_name)
        if lock is None:
            try:
                await asyncio.to_thread(self._session_store.load_session, session_name)
            except ValueError:
                return
            await self._restore_session_state(session_name)
            return

        async with lock:
            try:
                await asyncio.to_thread(self._session_store.load_session, session_name)
            except ValueError:
                return
            await self._restore_session_state(session_name)

    async def _session_mutation_lock(self, session_name: str):
        if self._coordinator is None:
            return None
        return await self._coordinator.session_lock(session_name)


SessionService = SessionLifecycleService
