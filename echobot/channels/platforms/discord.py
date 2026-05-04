from __future__ import annotations

import logging

from ..base import BaseChannel
from ..types import OutboundMessage


logger = logging.getLogger(__name__)


class DiscordChannel(BaseChannel):
    name = "discord"

    async def start(self) -> None:
        logger.warning(
            "Discord channel runtime adapter is not implemented yet; "
            "configuration is available for smoke validation only.",
        )
        self._running = False

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> None:
        del message
        logger.warning("Discord channel send is not implemented yet")
