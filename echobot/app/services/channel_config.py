from __future__ import annotations

import re
from typing import Any


CHANNEL_SECRET_FIELD_NAMES = {
    "access_token",
    "api_key",
    "authorization",
    "bot_token",
    "client_secret",
    "credential",
    "credentials",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "secret_ref",
    "token",
    "webhook_url",
    "webhook_secret",
}


def channel_config_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Return a channel configuration payload with all secret values redacted."""
    return {
        str(channel_name): _redact_channel_config(channel_config)
        for channel_name, channel_config in dict(config).items()
    }


def _redact_channel_config(channel_config: Any) -> Any:
    if isinstance(channel_config, list):
        return [_redact_channel_config(item) for item in channel_config]
    if not isinstance(channel_config, dict):
        return channel_config

    payload: dict[str, Any] = {}
    for key, value in channel_config.items():
        key_text = str(key)
        if _is_secret_channel_field(key_text):
            payload[key_text] = ""
            payload[f"{key_text}_configured"] = _has_configured_value(value)
            continue
        payload[key_text] = _redact_channel_config(value)
    return payload


def _is_secret_channel_field(field_name: str) -> bool:
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", field_name.strip())
    normalized = re.sub(r"[^a-z0-9]+", "_", snake_case.lower()).strip("_")
    if normalized in CHANNEL_SECRET_FIELD_NAMES:
        return True

    compact = normalized.replace("_", "")
    secret_suffixes = (
        "accesstoken",
        "apikey",
        "authorization",
        "bottoken",
        "clientsecret",
        "credential",
        "credentials",
        "password",
        "privatekey",
        "refreshtoken",
        "secretref",
        "webhooksecret",
        "webhookurl",
    )
    return compact in {"secret", "token"} or compact.endswith(secret_suffixes)


def _has_configured_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return bool(value)
