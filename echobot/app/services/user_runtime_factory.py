from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, Protocol, TypeVar

from ..auth import user_storage_root


class StoppableRuntime(Protocol):
    async def stop(self) -> None: ...


RuntimeT = TypeVar("RuntimeT", bound=StoppableRuntime)
_UNSET = object()
_LOGGER = logging.getLogger(__name__)


class RuntimeStopError(RuntimeError):
    """Raised after all cached runtimes were attempted during stop_all()."""

    def __init__(self, errors: list[tuple[str, Exception]]) -> None:
        self.errors = tuple(errors)
        details = "; ".join(
            f"{cache_key}: {error}"
            for cache_key, error in self.errors
        )
        super().__init__(f"Failed to stop {len(errors)} runtime(s): {details}")


@dataclass(slots=True)
class _RuntimeEntry(Generic[RuntimeT]):
    runtime: RuntimeT
    last_used_at: float


class UserRuntimeFactory(Generic[RuntimeT]):
    """Create, bound, and stop trusted-user scoped runtimes."""

    DEFAULT_MAX_ENTRIES = 16
    DEFAULT_IDLE_TTL_SECONDS = 1800.0

    def __init__(
        self,
        *,
        workspace_getter: Callable[[], Path],
        runtime_builder: Callable[[str, Path], Awaitable[RuntimeT]],
        max_entries: int | None = None,
        idle_ttl_seconds: float | None | object = _UNSET,
        clock: Callable[[], float] | None = None,
    ) -> None:
        configured_max_entries = (
            max_entries
            if max_entries is not None
            else _env_positive_int(
                "ECHOBOT_USER_RUNTIME_MAX_ENTRIES",
                self.DEFAULT_MAX_ENTRIES,
            )
        )
        if configured_max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")

        if idle_ttl_seconds is _UNSET:
            configured_idle_ttl = _env_non_negative_float(
                "ECHOBOT_USER_RUNTIME_IDLE_TTL_SECONDS",
                self.DEFAULT_IDLE_TTL_SECONDS,
            )
        else:
            configured_idle_ttl = idle_ttl_seconds
        if configured_idle_ttl is not None and configured_idle_ttl < 0:
            raise ValueError("idle_ttl_seconds must be non-negative or None")

        self._workspace_getter = workspace_getter
        self._runtime_builder = runtime_builder
        self.max_entries = configured_max_entries
        self.idle_ttl_seconds = configured_idle_ttl
        self._clock = clock or time.monotonic
        self._runtimes: OrderedDict[str, _RuntimeEntry[RuntimeT]] = OrderedDict()
        self._inflight: dict[str, asyncio.Task[RuntimeT]] = {}
        self._lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._stopping = False

    async def for_user(self, user_id: str) -> RuntimeT:
        storage_root = user_storage_root(self._workspace_getter(), user_id)
        cache_key = str(storage_root)
        expired: list[tuple[str, RuntimeT]] = []
        cached_runtime: RuntimeT | None = None
        build_task: asyncio.Task[RuntimeT] | None = None
        async with self._lock:
            if self._stopping:
                raise RuntimeError("User runtime factory is stopping")
            expired = self._take_idle_unlocked(self._clock())
            entry = self._runtimes.get(cache_key)
            if entry is not None:
                entry.last_used_at = self._clock()
                self._runtimes.move_to_end(cache_key)
                cached_runtime = entry.runtime
            else:
                build_task = self._inflight.get(cache_key)
                if build_task is None:
                    build_task = asyncio.create_task(
                        self._build_and_cache(user_id, storage_root, cache_key),
                        name=f"echobot_user_runtime_{storage_root.name}",
                    )
                    self._inflight[cache_key] = build_task

        await self._stop_evicted_many(expired)
        if cached_runtime is not None:
            return cached_runtime
        if build_task is None:
            raise RuntimeError("User runtime build was not scheduled")
        return await asyncio.shield(build_task)

    async def stop_all(self) -> None:
        async with self._stop_lock:
            async with self._lock:
                self._stopping = True
                entries = [
                    (cache_key, entry.runtime)
                    for cache_key, entry in self._runtimes.items()
                ]
                self._runtimes.clear()
                inflight = tuple(self._inflight.values())

            if inflight:
                await asyncio.gather(*inflight, return_exceptions=True)

            errors: list[tuple[str, Exception]] = []
            for cache_key, runtime in entries:
                try:
                    await runtime.stop()
                except Exception as error:
                    errors.append((cache_key, error))
            async with self._lock:
                self._stopping = False
            if errors:
                raise RuntimeStopError(errors)

    def cached_runtimes(self) -> tuple[RuntimeT, ...]:
        return tuple(entry.runtime for entry in self._runtimes.values())

    async def _build_and_cache(
        self,
        user_id: str,
        storage_root: Path,
        cache_key: str,
    ) -> RuntimeT:
        try:
            runtime = await self._runtime_builder(user_id, storage_root)
        except BaseException:
            async with self._lock:
                self._inflight.pop(cache_key, None)
            raise

        evicted: list[tuple[str, RuntimeT]] = []
        should_stop = False
        async with self._lock:
            self._inflight.pop(cache_key, None)
            if self._stopping:
                should_stop = True
            else:
                self._runtimes[cache_key] = _RuntimeEntry(
                    runtime=runtime,
                    last_used_at=self._clock(),
                )
                self._runtimes.move_to_end(cache_key)
                evicted = self._take_over_capacity_unlocked()

        if should_stop:
            await self._stop_evicted(cache_key, runtime)
            raise RuntimeError("User runtime factory stopped during runtime build")
        await self._stop_evicted_many(evicted)
        return runtime

    def _take_idle_unlocked(self, now: float) -> list[tuple[str, RuntimeT]]:
        if self.idle_ttl_seconds is None:
            return []
        expired_keys = [
            cache_key
            for cache_key, entry in self._runtimes.items()
            if now - entry.last_used_at >= self.idle_ttl_seconds
        ]
        expired: list[tuple[str, RuntimeT]] = []
        for cache_key in expired_keys:
            entry = self._runtimes.pop(cache_key, None)
            if entry is not None:
                expired.append((cache_key, entry.runtime))
        return expired

    def _take_over_capacity_unlocked(self) -> list[tuple[str, RuntimeT]]:
        evicted: list[tuple[str, RuntimeT]] = []
        while len(self._runtimes) > self.max_entries:
            cache_key, entry = self._runtimes.popitem(last=False)
            evicted.append((cache_key, entry.runtime))
        return evicted

    async def _stop_evicted_many(
        self,
        entries: list[tuple[str, RuntimeT]],
    ) -> None:
        for cache_key, runtime in entries:
            await self._stop_evicted(cache_key, runtime)

    async def _stop_evicted(self, cache_key: str, runtime: RuntimeT) -> None:
        try:
            await runtime.stop()
        except Exception:
            _LOGGER.exception("Failed to stop evicted user runtime %s", cache_key)


def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _env_non_negative_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite non-negative number") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value
