from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ...channels import (
    ChannelsConfig,
    describe_channel_registry,
    get_channel_definition,
    load_channels_config,
    save_channels_config,
)
from ...channels.platforms.discord import DISCORD_AVAILABLE
from ...channels.platforms.telegram import TELEGRAM_AVAILABLE
from ...runtime.sessions import normalize_session_name
from ..schemas import CHANNEL_SECRET_FIELD_NAMES


ChannelReloadCallback = Callable[[ChannelsConfig], Awaitable[None]]
ChannelStatusCallback = Callable[[], dict[str, dict[str, bool]]]


class ChannelActivationError(RuntimeError):
    pass


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
        try:
            await self._reload_channels(config)
        except Exception:
            raise ChannelActivationError(
                "Channel configuration could not be activated; the previous runtime remains active",
            ) from None

        try:
            await asyncio.to_thread(
                save_channels_config,
                config,
                self._config_path,
            )
        except Exception:
            try:
                await self._reload_channels(existing_config)
            except Exception:
                raise ChannelActivationError(
                    "Channel configuration could not be persisted or rolled back",
                ) from None
            raise
        return config.to_dict()

    async def get_status(self) -> dict[str, dict[str, bool]]:
        return self._get_status()

    def get_definitions(self) -> list[dict[str, Any]]:
        return describe_channel_registry()

    async def get_stage_targets(self) -> dict[str, list[dict[str, Any]]]:
        config = await asyncio.to_thread(
            load_channels_config,
            self._config_path,
        )
        status = self._get_status()
        return _stage_targets_from_config(config.to_dict(), status)

    async def get_integration_projection_inputs(self) -> dict[str, Any]:
        config = await asyncio.to_thread(
            load_channels_config,
            self._config_path,
        )
        status = self._get_status()
        config_payload = config.to_dict()
        return {
            "definitions": describe_channel_registry(),
            "config": config_payload,
            "status": status,
            "stage_targets": _stage_targets_from_config(config_payload, status),
        }

    async def smoke_channel(self, channel_name: str) -> dict[str, Any]:
        normalized_channel_name = str(channel_name or "").strip().lower()
        if get_channel_definition(normalized_channel_name) is None:
            raise KeyError(normalized_channel_name)

        config = await asyncio.to_thread(
            load_channels_config,
            self._config_path,
        )
        channel_config = config.to_dict().get(normalized_channel_name, {})
        if normalized_channel_name == "telegram":
            return _telegram_smoke_result(channel_config)
        if normalized_channel_name == "discord":
            return _discord_smoke_result(channel_config)
        return _generic_smoke_result(normalized_channel_name, channel_config)


def _stage_targets_from_config(
    config: dict[str, Any],
    status: dict[str, dict[str, bool]],
) -> dict[str, list[dict[str, Any]]]:
    targets: list[dict[str, Any]] = []
    for channel_name, channel_config in config.items():
        target = _stage_target_from_channel_config(
            channel_name,
            channel_config,
            status.get(channel_name, {}),
        )
        if target is not None:
            targets.append(target)

    targets.sort(
        key=lambda target: (
            not bool(target["selectable"]),
            str(target["label"]).lower(),
            str(target["session_name"]).lower(),
        ),
    )
    return {"targets": targets}


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


def _telegram_smoke_result(config: dict[str, Any]) -> dict[str, Any]:
    bot_token_ok = _configured(config, "bot_token")
    enabled = bool(config.get("enabled"))
    allow_list = _string_list(config.get("allow_from"))
    checks = [
        _check(
            "bot_token",
            bot_token_ok,
            "configured" if bot_token_ok else "missing bot token",
        ),
        _check(
            "python_telegram_bot",
            TELEGRAM_AVAILABLE,
            "installed" if TELEGRAM_AVAILABLE else "missing python-telegram-bot",
        ),
        _check(
            "allow_from",
            bool(allow_list),
            "restricted senders configured" if allow_list else "open to all senders",
        ),
        _check(
            "enabled",
            enabled,
            "enabled" if enabled else "saved but disabled",
        ),
        _check(
            "pending_updates",
            True,
            "pending updates will be dropped on startup"
            if bool(config.get("drop_pending_updates", True))
            else "pending updates will be processed on startup",
        ),
    ]
    ok = bot_token_ok and TELEGRAM_AVAILABLE
    if not ok:
        status = "missing_config"
    elif enabled:
        status = "ready"
    else:
        status = "configured_disabled"
    return {
        "channel": "telegram",
        "ok": ok,
        "status": status,
        "checks": checks,
        "next_steps": [
            "Enable Telegram after checking allow_from and local network access.",
            "Set drop_pending_updates=false only for validation runs that need to process already-sent test messages.",
            "Use HTTPS tunnel only when switching to webhook mode in a later slice.",
        ],
    }


def _discord_smoke_result(config: dict[str, Any]) -> dict[str, Any]:
    token_ok = _configured(config, "bot_token")
    webhook_ok = _configured(config, "webhook_url")
    secret_ok = _configured(config, "webhook_secret")
    enabled = bool(config.get("enabled"))
    allow_list = _string_list(config.get("allow_from"))
    native_ok = token_ok and DISCORD_AVAILABLE
    credential_ok = webhook_ok or native_ok
    checks = [
        _check(
            "credential",
            token_ok or webhook_ok,
            "bot token or webhook URL configured"
            if token_ok or webhook_ok
            else "missing bot token or webhook URL",
        ),
        _check(
            "discord_py",
            DISCORD_AVAILABLE,
            "installed for native bot events"
            if DISCORD_AVAILABLE
            else "missing discord.py; webhook mode still works if webhook_url is configured",
        ),
        _check(
            "webhook_secret",
            secret_ok,
            "configured" if secret_ok else "required for protected inbound webhook bridge",
        ),
        _check(
            "allow_from",
            bool(allow_list),
            "restricted senders configured" if allow_list else "open to all senders",
        ),
        _check(
            "runtime_adapter",
            webhook_ok or native_ok,
            "native bot events available"
            if native_ok
            else "webhook ingress/outbound delivery available"
            if webhook_ok
            else "configure webhook_url or install discord.py with bot_token",
        ),
        _check(
            "enabled",
            enabled,
            "enabled" if enabled else "saved but disabled",
        ),
    ]
    status = "configuration_ready" if credential_ok else "missing_config"
    return {
        "channel": "discord",
        "ok": credential_ok,
        "status": status,
        "checks": checks,
        "next_steps": [
            "Runtime adapter supports native bot events when discord.py is installed and webhook bridge when webhook_url is configured.",
            "Use /api/channels/discord/webhook for controlled inbound webhook tests when webhook_secret is configured.",
            "For native bot events, install discord.py, set bot_token, enable Message Content Intent in the Discord Developer Portal, and restart EchoBot.",
            "Keep allow_from restricted before enabling the channel for shared servers.",
        ],
    }


def _generic_smoke_result(channel_name: str, config: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(config.get("enabled"))
    return {
        "channel": channel_name,
        "ok": True,
        "status": "enabled" if enabled else "configured_disabled",
        "checks": [
            _check(
                "enabled",
                enabled,
                "enabled" if enabled else "saved but disabled",
            )
        ],
        "next_steps": [],
    }


def _stage_target_from_channel_config(
    channel_name: str,
    channel_config: dict[str, Any],
    status: dict[str, bool],
) -> dict[str, Any] | None:
    normalized_channel_name = str(channel_name or "").strip().lower()
    if normalized_channel_name == "console":
        return None
    if get_channel_definition(normalized_channel_name) is None:
        return None
    if not bool(channel_config.get("mirror_to_stage")):
        return None

    configured = _channel_is_configured(normalized_channel_name, channel_config)
    enabled = bool(channel_config.get("enabled")) or bool(status.get("enabled"))
    running = bool(status.get("running"))
    if not configured and not enabled and not running:
        return None

    session_name = _normalize_stage_session_name(channel_config)
    label = _channel_label(normalized_channel_name)
    return {
        "channel": normalized_channel_name,
        "label": label,
        "session_name": session_name,
        "display_name": f"{label} · {session_name}",
        "configured": configured,
        "enabled": enabled,
        "running": running,
        "selectable": configured or running,
    }


def _channel_is_configured(channel_name: str, config: dict[str, Any]) -> bool:
    if channel_name == "telegram":
        return _configured(config, "bot_token")
    if channel_name == "discord":
        return _configured(config, "bot_token") or _configured(config, "webhook_url")
    if channel_name == "qq":
        return _configured(config, "app_id") and _configured(config, "client_secret")
    return bool(config.get("enabled"))


def _normalize_stage_session_name(config: dict[str, Any]) -> str:
    raw_session_name = str(config.get("stage_session_name") or "default")
    try:
        return normalize_session_name(raw_session_name)
    except ValueError:
        return "default"


def _channel_label(channel_name: str) -> str:
    if channel_name == "qq":
        return "QQ"
    return channel_name.replace("_", " ").title()


def _check(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "message": message,
    }


def _configured(config: dict[str, Any], field_name: str) -> bool:
    return bool(str(config.get(field_name, "") or "").strip())


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
    text = str(value or "").strip()
    if not text:
        return []
    return [
        item.strip()
        for item in text.replace(",", "\n").splitlines()
        if item.strip()
    ]
