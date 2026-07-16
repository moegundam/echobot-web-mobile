from __future__ import annotations

import asyncio
from types import TracebackType


class AsyncReentrantLock:
    """Task-reentrant wrapper around asyncio.Lock."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._owner: asyncio.Task[object] | None = None
        self._depth = 0

    async def acquire(self) -> bool:
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("AsyncReentrantLock requires an asyncio task")
        if self._owner is task:
            self._depth += 1
            return True

        await self._lock.acquire()
        self._owner = task
        self._depth = 1
        return True

    def release(self) -> None:
        task = asyncio.current_task()
        if task is None or self._owner is not task:
            raise RuntimeError("AsyncReentrantLock can only be released by its owner")
        self._depth -= 1
        if self._depth > 0:
            return
        self._owner = None
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()

    async def __aenter__(self) -> AsyncReentrantLock:
        await self.acquire()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.release()
