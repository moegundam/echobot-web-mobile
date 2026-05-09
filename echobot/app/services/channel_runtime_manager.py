from __future__ import annotations

from pathlib import Path
from typing import Any

from ...channels import (
    ChannelManager,
    ChannelsConfig,
    MessageBus,
    load_channels_config,
)


class ChannelRuntimeManager:
    """Own channel config loading and adapter lifecycle."""

    def __init__(
        self,
        *,
        config_path: Path,
        bus: MessageBus,
        attachment_store: Any,
    ) -> None:
        self.config_path = config_path
        self.bus = bus
        self.attachment_store = attachment_store
        self.channels_config: ChannelsConfig | None = None
        self.channel_manager: ChannelManager | None = None

    async def start(self) -> None:
        self.channels_config = load_channels_config(self.config_path)
        self.channel_manager = ChannelManager(
            self.channels_config,
            self.bus,
            attachment_store=self.attachment_store,
        )
        await self.channel_manager.start_all()

    async def stop(self) -> None:
        if self.channel_manager is not None:
            await self.channel_manager.stop_all()
        self.channel_manager = None

    async def reload(self, config: ChannelsConfig | None = None) -> None:
        next_config = config or load_channels_config(self.config_path)
        next_manager = ChannelManager(
            next_config,
            self.bus,
            attachment_store=self.attachment_store,
        )
        await next_manager.start_all()

        previous_manager = self.channel_manager
        self.channel_manager = next_manager
        self.channels_config = next_config

        if previous_manager is not None:
            await previous_manager.stop_all()

    def status(self) -> dict[str, dict[str, bool]]:
        if self.channel_manager is None:
            return {}
        return self.channel_manager.get_status()
