from __future__ import annotations

import asyncio
import unittest

from echobot.concurrency import AsyncReentrantLock


class AsyncReentrantLockTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_task_can_reenter_while_other_task_waits(self) -> None:
        lock = AsyncReentrantLock()
        waiter_acquired = asyncio.Event()

        async def waiter() -> None:
            async with lock:
                waiter_acquired.set()

        async with lock:
            async with lock:
                waiter_task = asyncio.create_task(waiter())
                await asyncio.sleep(0.02)
                self.assertFalse(waiter_acquired.is_set())
            self.assertFalse(waiter_acquired.is_set())

        await waiter_task
        self.assertTrue(waiter_acquired.is_set())


if __name__ == "__main__":
    unittest.main()
