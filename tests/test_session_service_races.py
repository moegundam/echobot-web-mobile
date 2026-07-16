from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from echobot.runtime.session_service import SessionLifecycleService
from echobot.runtime.sessions import SessionStore


class _BlockingCoordinator:
    def __init__(self, blocked_session_name: str) -> None:
        self._lock = asyncio.Lock()
        self._blocked_session_name = blocked_session_name
        self._blocked_once = False
        self.restore_started = asyncio.Event()
        self.release_restore = asyncio.Event()
        self.deleted_sessions: set[str] = set()
        self.deletion_generation = 0

    async def session_lock(self, _session_name: str) -> asyncio.Lock:
        return self._lock

    async def cancel_jobs_for_session(self, _session_name: str) -> list[object]:
        return []

    async def mark_session_deleted(self, session_name: str) -> int:
        self.deletion_generation += 1
        self.deleted_sessions.add(session_name)
        return self.deletion_generation

    async def restore_session(
        self,
        session_name: str,
        *,
        expected_deletion_generation: int | None = None,
    ) -> bool:
        if session_name == self._blocked_session_name and not self._blocked_once:
            self._blocked_once = True
            self.restore_started.set()
            await self.release_restore.wait()
        if (
            expected_deletion_generation is not None
            and expected_deletion_generation != self.deletion_generation
        ):
            return False
        self.deleted_sessions.discard(session_name)
        return True

    async def session_deletion_state(self, session_name: str) -> tuple[bool, int]:
        return (
            session_name in self.deleted_sessions,
            self.deletion_generation,
        )


class SessionLifecycleRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_metadata_update_cannot_revive_renamed_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions")
            store.create_session("metadata-rename-race")
            coordinator = _BlockingCoordinator("metadata-rename-race")
            service = SessionLifecycleService(store, coordinator=coordinator)

            update_task = asyncio.create_task(
                service.update_session_metadata(
                    "metadata-rename-race",
                    lambda metadata: {**metadata, "marker": "updated"},
                ),
            )
            await coordinator.restore_started.wait()
            rename_task = asyncio.create_task(
                service.rename_session(
                    "metadata-rename-race",
                    "metadata-renamed",
                ),
            )
            await asyncio.sleep(0.02)
            coordinator.release_restore.set()
            await asyncio.gather(update_task, rename_task)

            self.assertIn("metadata-rename-race", coordinator.deleted_sessions)
            self.assertFalse(store.has_session("metadata-rename-race"))
            self.assertTrue(store.has_session("metadata-renamed"))

    async def test_metadata_update_cannot_revive_deleted_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions")
            store.create_session("metadata-delete-race")
            coordinator = _BlockingCoordinator("metadata-delete-race")
            service = SessionLifecycleService(store, coordinator=coordinator)

            update_task = asyncio.create_task(
                service.update_session_metadata(
                    "metadata-delete-race",
                    lambda metadata: {**metadata, "marker": "updated"},
                ),
            )
            await coordinator.restore_started.wait()
            delete_task = asyncio.create_task(
                service.delete_session("metadata-delete-race"),
            )
            await asyncio.sleep(0.02)
            coordinator.release_restore.set()
            updated, deleted = await asyncio.gather(update_task, delete_task)

            self.assertEqual("metadata-delete-race", updated.name)
            self.assertTrue(deleted)
            self.assertIn("metadata-delete-race", coordinator.deleted_sessions)
            self.assertFalse(store.has_session("metadata-delete-race"))

    async def test_stale_switch_cannot_revive_deleted_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SessionStore(Path(temp_dir) / "sessions")
            store.create_session("anchor")
            store.create_session("switch-delete-race")
            coordinator = _BlockingCoordinator("unused")
            coordinator.release_restore.set()
            service = SessionLifecycleService(store, coordinator=coordinator)
            loaded = asyncio.Event()
            release_load = asyncio.Event()
            original_load = service.load_session
            blocked_once = False

            async def blocking_load(name: str):
                nonlocal blocked_once
                session = await original_load(name)
                if name == "switch-delete-race" and not blocked_once:
                    blocked_once = True
                    loaded.set()
                    await release_load.wait()
                return session

            service.load_session = blocking_load  # type: ignore[method-assign]
            switch_task = asyncio.create_task(
                service.switch_session("switch-delete-race"),
            )
            await loaded.wait()
            delete_task = asyncio.create_task(
                service.delete_session("switch-delete-race"),
            )
            await asyncio.sleep(0.02)
            release_load.set()
            switched, deleted = await asyncio.gather(
                switch_task,
                delete_task,
                return_exceptions=True,
            )

            self.assertIsInstance(switched, RuntimeError)
            self.assertTrue(deleted)
            self.assertIn("switch-delete-race", coordinator.deleted_sessions)
            self.assertFalse(store.has_session("switch-delete-race"))
            self.assertNotEqual(
                "switch-delete-race",
                store.get_current_session_name(),
            )


if __name__ == "__main__":
    unittest.main()
