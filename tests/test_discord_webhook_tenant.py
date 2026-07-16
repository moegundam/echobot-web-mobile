from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from echobot.app.routers.channels import (
    DiscordWebhookMessageRequest,
    receive_discord_webhook,
)


class DiscordWebhookTenantBoundaryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _request(user_id: str = "allowed-discord-user") -> DiscordWebhookMessageRequest:
        return DiscordWebhookMessageRequest(
            channel_id="discord-channel",
            thread_id="discord-thread",
            user_id=user_id,
            username="external-user",
            text="ping",
        )

    @staticmethod
    def _runtime(discord_config: dict[str, object]):
        publish_inbound = AsyncMock()
        channel_service = SimpleNamespace(
            get_config=AsyncMock(return_value={"discord": discord_config}),
        )
        runtime = SimpleNamespace(
            channel_service=channel_service,
            bus=SimpleNamespace(publish_inbound=publish_inbound),
        )
        return runtime, publish_inbound

    async def test_webhook_rejects_missing_configured_secret(self) -> None:
        runtime, publish_inbound = self._runtime(
            {
                "enabled": True,
                "allow_from": ["allowed-discord-user"],
            }
        )

        with self.assertRaises(HTTPException) as raised:
            await receive_discord_webhook(
                self._request(),
                runtime=runtime,
                x_echobot_discord_secret="supplied-secret",
            )

        self.assertEqual(503, raised.exception.status_code)
        publish_inbound.assert_not_awaited()

    async def test_webhook_rejects_missing_and_invalid_supplied_secret(self) -> None:
        for supplied_secret in ("", "wrong-secret"):
            with self.subTest(supplied_secret=supplied_secret):
                runtime, publish_inbound = self._runtime(
                    {
                        "enabled": True,
                        "allow_from": ["allowed-discord-user"],
                        "webhook_secret": "configured-secret",
                    }
                )

                with self.assertRaises(HTTPException) as raised:
                    await receive_discord_webhook(
                        self._request(),
                        runtime=runtime,
                        x_echobot_discord_secret=supplied_secret,
                    )

                self.assertEqual(401, raised.exception.status_code)
                publish_inbound.assert_not_awaited()

    async def test_webhook_rejects_sender_outside_allowlist(self) -> None:
        runtime, publish_inbound = self._runtime(
            {
                "enabled": True,
                "allow_from": ["allowed-discord-user"],
                "webhook_secret": "configured-secret",
            }
        )

        with self.assertRaises(HTTPException) as raised:
            await receive_discord_webhook(
                self._request(user_id="blocked-discord-user"),
                runtime=runtime,
                x_echobot_discord_secret="configured-secret",
            )

        self.assertEqual(403, raised.exception.status_code)
        publish_inbound.assert_not_awaited()

    async def test_accepted_webhook_keeps_external_id_out_of_owner_user_id(self) -> None:
        external_user_id = "allowed-discord-user"
        runtime, publish_inbound = self._runtime(
            {
                "enabled": True,
                "allow_from": [external_user_id],
                "webhook_secret": "configured-secret",
            }
        )

        response = await receive_discord_webhook(
            self._request(user_id=external_user_id),
            runtime=runtime,
            x_echobot_discord_secret="configured-secret",
        )

        self.assertTrue(response["accepted"])
        publish_inbound.assert_awaited_once()
        inbound = publish_inbound.await_args.args[0]
        self.assertIsNone(inbound.address.user_id)
        self.assertEqual(external_user_id, inbound.sender_id)
        self.assertEqual(external_user_id, inbound.metadata["discord_user_id"])
        self.assertEqual("external-user", inbound.metadata["username"])


if __name__ == "__main__":
    unittest.main()
