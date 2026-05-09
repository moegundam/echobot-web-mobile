from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from ..auth import user_storage_root


class StoppableRuntime(Protocol):
    async def stop(self) -> None: ...


RuntimeT = TypeVar("RuntimeT", bound=StoppableRuntime)


class UserRuntimeFactory(Generic[RuntimeT]):
    """Create, cache, and stop trusted-user scoped runtimes."""

    def __init__(
        self,
        *,
        workspace_getter: Callable[[], Path],
        runtime_builder: Callable[[str, Path], Awaitable[RuntimeT]],
    ) -> None:
        self._workspace_getter = workspace_getter
        self._runtime_builder = runtime_builder
        self._runtimes: dict[str, RuntimeT] = {}
        self._lock = asyncio.Lock()

    async def for_user(self, user_id: str) -> RuntimeT:
        storage_root = user_storage_root(self._workspace_getter(), user_id)
        cache_key = str(storage_root)
        runtime = self._runtimes.get(cache_key)
        if runtime is not None:
            return runtime

        async with self._lock:
            runtime = self._runtimes.get(cache_key)
            if runtime is not None:
                return runtime

            runtime = await self._runtime_builder(user_id, storage_root)
            self._runtimes[cache_key] = runtime
            return runtime

    async def stop_all(self) -> None:
        for runtime in list(self._runtimes.values()):
            await runtime.stop()
        self._runtimes.clear()

    def cached_runtimes(self) -> tuple[RuntimeT, ...]:
        return tuple(self._runtimes.values())
