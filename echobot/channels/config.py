from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


DEFAULT_CHANNEL_CONFIG_PATH = Path(".echobot/channels.json")


@dataclass(slots=True)
class BaseChannelConfig:
    enabled: bool = False
    allow_from: list[str] = field(default_factory=list)
    mirror_to_stage: bool = False
    stage_session_name: str = ""


@dataclass(slots=True)
class ConsoleChannelConfig(BaseChannelConfig):
    pass


@dataclass(slots=True)
class TelegramChannelConfig(BaseChannelConfig):
    mirror_to_stage: bool = True
    stage_session_name: str = "default"
    bot_token: str = ""
    proxy: str = ""
    reply_to_message: bool = False
    drop_pending_updates: bool = True


@dataclass(slots=True)
class DiscordChannelConfig(BaseChannelConfig):
    mirror_to_stage: bool = True
    stage_session_name: str = "default"
    bot_token: str = ""
    webhook_url: str = ""
    webhook_secret: str = ""
    application_id: str = ""
    guild_id: str = ""
    channel_id: str = ""


@dataclass(slots=True)
class QQChannelConfig(BaseChannelConfig):
    mirror_to_stage: bool = True
    stage_session_name: str = "default"
    app_id: str = ""
    client_secret: str = ""


@dataclass(slots=True)
class ChannelsConfig:
    configs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChannelsConfig":
        from .registry import get_channel_registry

        configs: dict[str, Any] = {}
        registry = get_channel_registry()
        for name, definition in registry.items():
            configs[name] = _build_dataclass(
                definition.config_cls,
                data.get(name, {}),
            )

        for name, raw_config in data.items():
            if name in configs or not isinstance(raw_config, dict):
                continue
            configs[name] = dict(raw_config)

        return cls(configs=configs)

    def to_dict(self) -> dict[str, Any]:
        return {
            name: _config_to_dict(config)
            for name, config in self.configs.items()
        }

    def enabled_channel_names(self) -> list[str]:
        return [
            name
            for name, config in self.configs.items()
            if bool(getattr(config, "enabled", False))
        ]

    def get(self, name: str, default: Any = None) -> Any:
        return self.configs.get(name, default)

    def set(self, name: str, config: Any) -> None:
        self.configs[name] = config

    def __getattr__(self, name: str) -> Any:
        try:
            return self.configs[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load_channels_config(
    path: str | Path = DEFAULT_CHANNEL_CONFIG_PATH,
    *,
    create_default: bool = True,
) -> ChannelsConfig:
    config_path = Path(path)
    if not config_path.exists():
        config = _default_channels_config()
        if create_default:
            save_channels_config(config, config_path)
        return config

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid channel config JSON: {config_path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Channel config must be a JSON object: {config_path}")
    return ChannelsConfig.from_dict(data)


def save_channels_config(
    config: ChannelsConfig,
    path: str | Path = DEFAULT_CHANNEL_CONFIG_PATH,
) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _build_dataclass(cls: type[Any], raw: Any) -> Any:
    if not isinstance(raw, dict):
        return cls()
    return cls(**raw)


def _default_channels_config() -> ChannelsConfig:
    from .registry import get_channel_registry

    return ChannelsConfig(
        configs={
            name: definition.config_cls()
            for name, definition in get_channel_registry().items()
        }
    )


def _config_to_dict(config: Any) -> dict[str, Any]:
    if is_dataclass(config):
        return asdict(config)
    if isinstance(config, dict):
        return dict(config)
    return dict(vars(config))
