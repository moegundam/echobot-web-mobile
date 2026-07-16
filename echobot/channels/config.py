from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any

from ..secrets import LocalJsonSecretStore, SecretConfigurationError


DEFAULT_CHANNEL_CONFIG_PATH = Path(".echobot/channels.json")
CHANNEL_SECRET_FILENAME = "channel_secrets.json"
CHANNEL_SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "telegram": ("bot_token",),
    "discord": ("bot_token", "webhook_url", "webhook_secret"),
    "qq": ("client_secret",),
}
_MUTATION_LOCKS_GUARD = threading.Lock()
_MUTATION_LOCKS_BY_PATH: dict[Path, threading.RLock] = {}


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
    mutation_lock = _mutation_lock_for(config_path.resolve())
    with mutation_lock:
        return _load_channels_config_unlocked(
            config_path,
            create_default=create_default,
        )


def _load_channels_config_unlocked(
    config_path: Path,
    *,
    create_default: bool,
) -> ChannelsConfig:
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
    return ChannelsConfig.from_dict(_resolve_channel_secrets(data, config_path))


def save_channels_config(
    config: ChannelsConfig,
    path: str | Path = DEFAULT_CHANNEL_CONFIG_PATH,
) -> None:
    config_path = Path(path)
    payload = config.to_dict()
    secret_values = _extract_channel_secrets(payload)
    secret_path = config_path.with_name(CHANNEL_SECRET_FILENAME)
    mutation_lock = _mutation_lock_for(config_path.resolve())
    with mutation_lock:
        secret_store = LocalJsonSecretStore(secret_path)
        secret_snapshot_existed = secret_path.exists()
        previous_secret_values = _channel_secret_snapshot(secret_store)
        secret_snapshot_replaced = bool(
            secret_values or secret_snapshot_existed
        )
        if secret_snapshot_replaced:
            secret_store.replace_all(secret_values)
        try:
            _write_json_atomically(config_path, payload)
        except Exception:
            if secret_snapshot_replaced:
                try:
                    _restore_channel_secret_snapshot(
                        secret_store,
                        secret_path,
                        existed=secret_snapshot_existed,
                        values=previous_secret_values,
                    )
                except Exception:
                    raise ValueError(
                        "Channel config could not be written and the previous "
                        "secret snapshot could not be restored"
                    ) from None
            raise ValueError("Channel config could not be written") from None


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


def _resolve_channel_secrets(
    payload: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    resolved = {
        name: dict(config) if isinstance(config, dict) else config
        for name, config in payload.items()
    }
    secret_names = tuple(
        f"{channel_name}.{field_name}"
        for channel_name, fields in CHANNEL_SECRET_FIELDS.items()
        for field_name in fields
    )
    stored = LocalJsonSecretStore(
        config_path.with_name(CHANNEL_SECRET_FILENAME)
    ).get_many(secret_names)

    for channel_name, fields in CHANNEL_SECRET_FIELDS.items():
        channel_payload = resolved.get(channel_name)
        if channel_payload is None:
            channel_payload = {}
            resolved[channel_name] = channel_payload
        if not isinstance(channel_payload, dict):
            continue
        for field_name in fields:
            inline_value = channel_payload.get(field_name, "")
            if inline_value is None:
                inline_value = ""
            if not isinstance(inline_value, str):
                raise ValueError("Channel secret configuration is invalid")
            stored_secret = stored.get(f"{channel_name}.{field_name}")
            if stored_secret is None:
                continue
            if inline_value and inline_value != stored_secret.value:
                raise ValueError("Channel secret has conflicting sources")
            channel_payload[field_name] = stored_secret.value
    return resolved


def _extract_channel_secrets(payload: dict[str, Any]) -> dict[str, str]:
    secrets: dict[str, str] = {}
    for channel_name, fields in CHANNEL_SECRET_FIELDS.items():
        channel_payload = payload.get(channel_name)
        if not isinstance(channel_payload, dict):
            continue
        for field_name in fields:
            value = channel_payload.get(field_name, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise SecretConfigurationError(
                    "Configured channel secret must be text"
                )
            if value.strip():
                secrets[f"{channel_name}.{field_name}"] = value
            channel_payload[field_name] = ""
    return secrets


def _mutation_lock_for(path: Path) -> threading.RLock:
    with _MUTATION_LOCKS_GUARD:
        lock = _MUTATION_LOCKS_BY_PATH.get(path)
        if lock is None:
            lock = threading.RLock()
            _MUTATION_LOCKS_BY_PATH[path] = lock
        return lock


def _channel_secret_snapshot(
    secret_store: LocalJsonSecretStore,
) -> dict[str, str]:
    secret_names = tuple(
        f"{channel_name}.{field_name}"
        for channel_name, fields in CHANNEL_SECRET_FIELDS.items()
        for field_name in fields
    )
    stored = secret_store.get_many(secret_names)
    return {name: secret.value for name, secret in stored.items()}


def _restore_channel_secret_snapshot(
    secret_store: LocalJsonSecretStore,
    secret_path: Path,
    *,
    existed: bool,
    values: dict[str, str],
) -> None:
    if existed:
        secret_store.replace_all(values)
        return
    try:
        secret_path.unlink(missing_ok=True)
    except OSError:
        raise ValueError("Channel secret snapshot could not be restored") from None


def _write_json_atomically(path: Path, payload: dict[str, Any]) -> None:
    content = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    parent = path.parent
    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=parent,
            prefix=f".{path.name}.",
        )
        temporary_path = Path(temporary_name)
        os.fchmod(descriptor, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary_path, path)
        temporary_path = None
    except OSError:
        raise ValueError("Channel config could not be written") from None
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
