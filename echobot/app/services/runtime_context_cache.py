from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

from ...runtime.sessions import normalize_session_name


ContextT = TypeVar("ContextT")
ContextBuilder = Callable[[], Awaitable[ContextT]]


@dataclass(slots=True)
class _CacheEntry(Generic[ContextT]):
    generation: tuple[int, int]
    value: ContextT


class SessionRuntimeContextCache(Generic[ContextT]):
    """Bounded revision cache with per-key async request coalescing."""

    def __init__(self, *, max_entries: int = 256) -> None:
        if max_entries <= 0:
            raise ValueError("Runtime context cache max_entries must be positive")
        self.max_entries = int(max_entries)
        self._global_generation = 0
        self._session_generations: dict[str, int] = {}
        self._entries: OrderedDict[str, _CacheEntry[ContextT]] = OrderedDict()
        self._inflight: dict[
            tuple[str, tuple[int, int]],
            asyncio.Task[ContextT],
        ] = {}
        self._lock = asyncio.Lock()

    @property
    def global_generation(self) -> int:
        return self._global_generation

    def cached_session_names(self) -> tuple[str, ...]:
        return tuple(self._entries)

    async def get_or_build(
        self,
        session_name: str,
        builder: ContextBuilder[ContextT],
    ) -> ContextT:
        key = normalize_session_name(session_name)
        while True:
            async with self._lock:
                generation = self._generation_for(key)
                entry = self._entries.get(key)
                if entry is not None and entry.generation == generation:
                    self._entries.move_to_end(key)
                    return _clone(entry.value)

                inflight_key = (key, generation)
                task = self._inflight.get(inflight_key)
                if task is None:
                    revision = _format_revision(generation)
                    task = asyncio.create_task(
                        self._build_and_store(
                            key,
                            generation,
                            revision,
                            builder,
                        ),
                        name=f"echobot_runtime_context_{key}",
                    )
                    self._inflight[inflight_key] = task

            value = await asyncio.shield(task)
            async with self._lock:
                if generation == self._generation_for(key):
                    return _clone(value)

    async def invalidate(self, session_name: str) -> str:
        key = normalize_session_name(session_name)
        async with self._lock:
            self._session_generations[key] = self._session_generations.get(key, 0) + 1
            self._entries.pop(key, None)
            return _format_revision(self._generation_for(key))

    async def invalidate_all(self) -> dict[str, str]:
        async with self._lock:
            self._global_generation += 1
            self._entries.clear()
            return {}

    async def current_revision(self, session_name: str) -> str:
        key = normalize_session_name(session_name)
        async with self._lock:
            return _format_revision(self._generation_for(key))

    async def _build_and_store(
        self,
        key: str,
        generation: tuple[int, int],
        revision: str,
        builder: ContextBuilder[ContextT],
    ) -> ContextT:
        inflight_key = (key, generation)
        try:
            value = _with_revision(await builder(), revision)
            async with self._lock:
                if generation == self._generation_for(key):
                    self._entries[key] = _CacheEntry(
                        generation=generation,
                        value=_clone(value),
                    )
                    self._entries.move_to_end(key)
                    while len(self._entries) > self.max_entries:
                        self._entries.popitem(last=False)
            return value
        finally:
            async with self._lock:
                self._inflight.pop(inflight_key, None)

    def _generation_for(self, key: str) -> tuple[int, int]:
        return self._global_generation, self._session_generations.get(key, 0)


def get_runtime_context_cache(runtime: Any) -> SessionRuntimeContextCache[Any]:
    cache = getattr(runtime, "runtime_context_cache", None)
    if isinstance(cache, SessionRuntimeContextCache):
        return cache
    cache = SessionRuntimeContextCache()
    setattr(runtime, "runtime_context_cache", cache)
    return cache


def _with_revision(value: ContextT, revision: str) -> ContextT:
    if hasattr(value, "model_copy"):
        return value.model_copy(update={"revision": revision}, deep=True)
    if isinstance(value, dict):
        updated = deepcopy(value)
        updated["revision"] = revision
        return updated
    return value


def _clone(value: ContextT) -> ContextT:
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)
    return deepcopy(value)


def _format_revision(generation: tuple[int, int]) -> str:
    return f"ctx-{generation[0]:08x}-{generation[1]:08x}"
