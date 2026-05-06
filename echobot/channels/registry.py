from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
from typing import Any

from .base import BaseChannel
from .config import (
    ConsoleChannelConfig,
    DiscordChannelConfig,
    QQChannelConfig,
    TelegramChannelConfig,
)
from .platforms import ConsoleChannel, DiscordChannel, QQChannel, TelegramChannel


@dataclass(frozen=True, slots=True)
class ChannelDefinition:
    name: str
    description: str
    config_cls: type[Any]
    channel_cls: type[BaseChannel]


_BUILTIN_CHANNELS: dict[str, ChannelDefinition] = {
    "console": ChannelDefinition(
        name="console",
        description="Local console output channel for smoke testing.",
        config_cls=ConsoleChannelConfig,
        channel_cls=ConsoleChannel,
    ),
    "telegram": ChannelDefinition(
        name="telegram",
        description="Telegram bot polling channel.",
        config_cls=TelegramChannelConfig,
        channel_cls=TelegramChannel,
    ),
    "discord": ChannelDefinition(
        name="discord",
        description="Discord native bot events, webhook bridge, and smoke-test channel.",
        config_cls=DiscordChannelConfig,
        channel_cls=DiscordChannel,
    ),
    "qq": ChannelDefinition(
        name="qq",
        description="QQ official bot direct-message channel.",
        config_cls=QQChannelConfig,
        channel_cls=QQChannel,
    ),
}


def get_channel_registry() -> dict[str, ChannelDefinition]:
    return dict(_BUILTIN_CHANNELS)


def get_channel_definition(name: str) -> ChannelDefinition | None:
    return _BUILTIN_CHANNELS.get(name)


def describe_channel_registry() -> list[dict[str, Any]]:
    descriptions: list[dict[str, Any]] = []
    for definition in _BUILTIN_CHANNELS.values():
        descriptions.append(
            {
                "name": definition.name,
                "description": definition.description,
                "config_fields": _describe_config_fields(definition.config_cls),
            }
        )
    return descriptions


def _describe_config_fields(config_cls: type[Any]) -> list[dict[str, Any]]:
    if not is_dataclass(config_cls):
        return []

    config_fields: list[dict[str, Any]] = []
    for field_info in fields(config_cls):
        config_fields.append(
            {
                "name": field_info.name,
                "type": _field_type_name(field_info.type),
                "required": field_info.default is MISSING
                and field_info.default_factory is MISSING,
                "default": _field_default_value(field_info),
            }
        )
    return config_fields


def _field_type_name(field_type: object) -> str:
    if isinstance(field_type, type):
        return field_type.__name__
    return str(field_type)


def _field_default_value(field_info) -> Any:
    if field_info.default is not MISSING:
        return field_info.default
    if field_info.default_factory is not MISSING:
        return field_info.default_factory()
    return None
