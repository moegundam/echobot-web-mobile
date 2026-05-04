from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ...channels import (
    ChannelsConfig,
    describe_channel_registry,
    load_channels_config,
    save_channels_config,
)
from ..schemas import CHANNEL_SECRET_FIELD_NAMES


ChannelReloadCallback = Callable[[ChannelsConfig], Awaitable[None]]
ChannelStatusCallback = Callable[[], dict[str, dict[str, bool]]]


class ChannelService:
    def __init__(
        self,
        *,
        config_path: str | Path,
        get_status: ChannelStatusCallback,
        reload_channels: ChannelReloadCallback,
    ) -> None:
        self._config_path = Path(config_path)
        self._get_status = get_status
        self._reload_channels = reload_channels

    async def get_config(self) -> dict[str, Any]:
        config = await asyncio.to_thread(
            load_channels_config,
            self._config_path,
        )
        return config.to_dict()

    async def update_config(self, raw_config: dict[str, Any]) -> dict[str, Any]:
        existing_config = await asyncio.to_thread(
            load_channels_config,
            self._config_path,
        )
        config = ChannelsConfig.from_dict(
            _merge_redacted_channel_config(
                raw_config,
                existing_config.to_dict(),
            )
        )
        await asyncio.to_thread(
            save_channels_config,
            config,
            self._config_path,
        )
        await self._reload_channels(config)
        return config.to_dict()

    async def get_status(self) -> dict[str, dict[str, bool]]:
        return self._get_status()

    def get_definitions(self) -> list[dict[str, Any]]:
        return describe_channel_registry()


def _merge_redacted_channel_config(
    raw_config: dict[str, Any],
    existing_config: dict[str, Any],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for channel_name, channel_config in dict(raw_config).items():
        if not isinstance(channel_config, dict):
            merged[channel_name] = channel_config
            continue

        existing_channel_config = existing_config.get(channel_name, {})
        if not isinstance(existing_channel_config, dict):
            existing_channel_config = {}

        next_channel_config: dict[str, Any] = {}
        for key, value in channel_config.items():
            key_text = str(key)
            if _is_secret_configured_marker(key_text):
                continue
            if _is_secret_field(key_text) and _is_empty_secret_value(value):
                existing_value = existing_channel_config.get(key_text, "")
                if not _is_empty_secret_value(existing_value):
                    next_channel_config[key_text] = existing_value
                    continue
            next_channel_config[key_text] = value

        for key, existing_value in existing_channel_config.items():
            key_text = str(key)
            if _is_secret_field(key_text) and key_text not in next_channel_config:
                next_channel_config[key_text] = existing_value

        merged[channel_name] = next_channel_config
    return merged


def _is_secret_configured_marker(field_name: str) -> bool:
    suffix = "_configured"
    if not field_name.endswith(suffix):
        return False
    return _is_secret_field(field_name[: -len(suffix)])


def _is_secret_field(field_name: str) -> bool:
    return field_name.strip().lower() in CHANNEL_SECRET_FIELD_NAMES


def _is_empty_secret_value(value: object) -> bool:
    return not str(value or "").strip()
