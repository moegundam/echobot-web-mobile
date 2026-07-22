from __future__ import annotations

import json

from echobot.app.services.channel_config import channel_config_payload


def test_channel_config_redacts_nested_and_camel_case_secrets() -> None:
    payload = channel_config_payload(
        {
            "custom": {
                "enabled": True,
                "clientSecret": "client-secret-value",
                "nested": {
                    "private_key": "private-key-value",
                    "authorization": "Bearer hidden-value",
                },
                "items": [
                    {"accessToken": "access-token-value", "label": "primary"},
                ],
            },
        },
    )

    serialized = json.dumps(payload, ensure_ascii=False)
    assert "client-secret-value" not in serialized
    assert "private-key-value" not in serialized
    assert "Bearer hidden-value" not in serialized
    assert "access-token-value" not in serialized
    assert payload["custom"]["clientSecret_configured"] is True
    assert payload["custom"]["nested"]["private_key_configured"] is True
    assert payload["custom"]["items"][0]["accessToken_configured"] is True
    assert payload["custom"]["items"][0]["label"] == "primary"
