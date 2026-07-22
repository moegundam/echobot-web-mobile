from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from echobot.app.services.runtime_context_cache import (
    SessionRuntimeContextCache,
    get_runtime_context_cache,
)
from echobot.app.services.runtime_context_events import (
    notify_all_runtime_contexts_changed,
    notify_session_runtime_context_changed,
)
from echobot.app.services.stage_events import StageEventBroker


class _SessionService:
    async def list_sessions(self):
        return [SimpleNamespace(name="alpha"), SimpleNamespace(name="beta")]


class SessionRuntimeContextCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_value_until_session_is_invalidated(self) -> None:
        cache = SessionRuntimeContextCache(max_entries=4)
        calls = 0

        async def build():
            nonlocal calls
            calls += 1
            return {"value": calls}

        first = await cache.get_or_build("demo", build)
        second = await cache.get_or_build("demo", build)
        self.assertEqual(first, second)
        self.assertEqual(1, calls)
        self.assertEqual("ctx-00000000-00000000", first["revision"])

        revision = await cache.invalidate("demo")
        third = await cache.get_or_build("demo", build)
        self.assertEqual("ctx-00000000-00000001", revision)
        self.assertEqual(2, calls)
        self.assertEqual(revision, third["revision"])

    async def test_coalesces_concurrent_builds_and_bounds_lru_entries(self) -> None:
        cache = SessionRuntimeContextCache(max_entries=2)
        release = asyncio.Event()
        calls = 0

        async def build():
            nonlocal calls
            calls += 1
            await release.wait()
            return {"value": calls}

        tasks = [asyncio.create_task(cache.get_or_build("demo", build)) for _ in range(5)]
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*tasks)
        self.assertEqual(1, calls)
        self.assertEqual([results[0]] * 5, results)

        await cache.get_or_build("two", lambda: _value("two"))
        await cache.get_or_build("three", lambda: _value("three"))
        self.assertEqual(("two", "three"), cache.cached_session_names())

    async def test_global_invalidation_advances_every_session_revision(self) -> None:
        cache = SessionRuntimeContextCache(max_entries=4)
        await cache.get_or_build("alpha", lambda: _value("alpha"))
        await cache.get_or_build("beta", lambda: _value("beta"))

        revisions = await cache.invalidate_all()

        self.assertEqual({}, revisions)
        self.assertEqual(1, cache.global_generation)
        self.assertEqual((), cache.cached_session_names())
        self.assertEqual(
            "ctx-00000001-00000000",
            await cache.current_revision("alpha"),
        )

    async def test_runtime_helper_keeps_one_cache_per_runtime(self) -> None:
        runtime = SimpleNamespace()
        first = get_runtime_context_cache(runtime)
        second = get_runtime_context_cache(runtime)
        self.assertIs(first, second)

    async def test_change_notifier_is_session_scoped_and_emits_revision(self) -> None:
        runtime = SimpleNamespace(
            stage_event_broker=StageEventBroker(),
            session_service=_SessionService(),
            user_id="",
        )
        cache = get_runtime_context_cache(runtime)
        await cache.get_or_build("alpha", lambda: _value("alpha"))

        revision = await notify_session_runtime_context_changed(
            runtime,
            "alpha",
            reason="runtime_override_updated",
        )

        events = runtime.stage_event_broker.history("default", "alpha")
        self.assertEqual(1, len(events))
        self.assertEqual("runtime_context_changed", events[0].kind)
        self.assertEqual(revision, events[0].metadata["revision"])
        self.assertEqual("runtime_override_updated", events[0].metadata["reason"])
        self.assertEqual([], runtime.stage_event_broker.history("default", "beta"))

    async def test_global_notifier_emits_one_event_for_each_existing_session(self) -> None:
        runtime = SimpleNamespace(
            stage_event_broker=StageEventBroker(),
            session_service=_SessionService(),
            user_id="",
        )

        revisions = await notify_all_runtime_contexts_changed(
            runtime,
            reason="llm_catalog_updated",
        )

        self.assertEqual({"alpha", "beta"}, set(revisions))
        for session_name in revisions:
            event = runtime.stage_event_broker.history("default", session_name)[0]
            self.assertEqual(revisions[session_name], event.metadata["revision"])
            self.assertEqual("llm_catalog_updated", event.metadata["reason"])


async def _value(value: str) -> dict[str, str]:
    return {"value": value}


if __name__ == "__main__":
    unittest.main()
