from __future__ import annotations

import asyncio
from collections.abc import Callable

from .types import InboundMessage, OutboundMessage


class MessageBus:
    def __init__(self) -> None:
        self._inbound: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue()

    async def publish_inbound(self, message: InboundMessage) -> None:
        await self._inbound.put(message)

    async def consume_inbound(self) -> InboundMessage:
        return await self._inbound.get()

    async def publish_outbound(self, message: OutboundMessage) -> None:
        await self._outbound.put(message)

    async def consume_outbound(self) -> OutboundMessage:
        return await self._outbound.get()

    async def discard_outbound(
        self,
        predicate: Callable[[OutboundMessage], bool],
    ) -> int:
        kept_messages: list[OutboundMessage] = []
        discarded_count = 0

        while True:
            try:
                message = self._outbound.get_nowait()
            except asyncio.QueueEmpty:
                break

            if predicate(message):
                discarded_count += 1
                continue
            kept_messages.append(message)

        for message in kept_messages:
            self._outbound.put_nowait(message)

        return discarded_count

    @property
    def inbound_size(self) -> int:
        return self._inbound.qsize()

    @property
    def outbound_size(self) -> int:
        return self._outbound.qsize()
