from __future__ import annotations

import asyncio
import unittest

from echobot.app.services.runtime_context_cache import SessionRuntimeContextCache


class SessionRuntimeContextCacheRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalidation_during_build_retries_with_current_generation(self) -> None:
        cache = SessionRuntimeContextCache(max_entries=4)
        first_build_started = asyncio.Event()
        release_first_build = asyncio.Event()
        calls = 0

        async def build() -> dict[str, int]:
            nonlocal calls
            calls += 1
            call_number = calls
            if call_number == 1:
                first_build_started.set()
                await release_first_build.wait()
            return {"value": call_number}

        request = asyncio.create_task(cache.get_or_build("demo", build))
        await first_build_started.wait()
        expected_revision = await cache.invalidate("demo")
        release_first_build.set()

        result = await request

        self.assertEqual(2, calls)
        self.assertEqual(2, result["value"])
        self.assertEqual(expected_revision, result["revision"])


if __name__ == "__main__":
    unittest.main()
