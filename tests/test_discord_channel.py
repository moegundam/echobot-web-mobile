from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from echobot.channels import ChannelAddress, MessageBus, OutboundMessage
from echobot.channels.platforms.discord import DiscordChannel


class DiscordChannelNativeTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_message_publishes_session_scoped_inbound(self) -> None:
        bus = MessageBus()
        channel = DiscordChannel(
            SimpleNamespace(
                allow_from=["42"],
                bot_token="",
                webhook_url="",
                channel_id="",
            ),
            bus,
        )
        message = SimpleNamespace(
            id=1001,
            content="ping",
            author=SimpleNamespace(
                id=42,
                name="allowed-user",
                display_name="Allowed User",
                bot=False,
            ),
            channel=SimpleNamespace(id=1234, parent_id=None),
            guild=SimpleNamespace(id=5678),
            attachments=[
                SimpleNamespace(
                    url="https://cdn.example.test/image.png",
                    filename="image.png",
                    content_type="image/png",
                    size=2048,
                ),
                SimpleNamespace(
                    url="https://cdn.example.test/notes.txt",
                    filename="notes.txt",
                    content_type="text/plain",
                    size=32,
                ),
            ],
        )

        await channel._on_message(message)
        inbound = await asyncio.wait_for(bus.consume_inbound(), timeout=0.2)

        self.assertEqual("discord", inbound.address.channel)
        self.assertEqual("1234", inbound.address.chat_id)
        self.assertEqual("42|allowed-user", inbound.sender_id)
        self.assertEqual("42", inbound.address.user_id)
        self.assertEqual("ping", inbound.text)
        self.assertEqual(
            "https://cdn.example.test/image.png",
            inbound.image_urls[0]["url"],
        )
        self.assertEqual(
            "https://cdn.example.test/notes.txt",
            inbound.files[0]["download_url"],
        )
        self.assertTrue(inbound.metadata["native_bot"])

    async def test_native_message_respects_allow_from(self) -> None:
        bus = MessageBus()
        channel = DiscordChannel(
            SimpleNamespace(allow_from=["allowed-user"], webhook_url="", channel_id=""),
            bus,
        )
        message = SimpleNamespace(
            id=1002,
            content="blocked",
            author=SimpleNamespace(id=7, name="other-user", bot=False),
            channel=SimpleNamespace(id=1234, parent_id=None),
            guild=None,
            attachments=[],
        )

        await channel._on_message(message)

        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(bus.consume_inbound(), timeout=0.05)

    async def test_send_uses_native_bot_channel_when_webhook_is_absent(self) -> None:
        target = _FakeDiscordTarget()
        client = _FakeDiscordClient(target)
        bus = MessageBus()
        channel = DiscordChannel(
            SimpleNamespace(allow_from=[], webhook_url="", channel_id=""),
            bus,
        )
        channel._client = client

        await channel.send(
            OutboundMessage(
                address=ChannelAddress(channel="discord", chat_id="1234"),
                text="hello",
            )
        )

        self.assertEqual(1234, client.fetched_channel_id)
        self.assertEqual(["hello"], target.sent_messages)


class _FakeDiscordTarget:
    def __init__(self) -> None:
        self.sent_messages: list[str] = []

    async def send(self, text: str) -> None:
        self.sent_messages.append(text)


class _FakeDiscordClient:
    def __init__(self, target: _FakeDiscordTarget) -> None:
        self.target = target
        self.fetched_channel_id: int | None = None

    def get_channel(self, channel_id: int):
        return None

    async def fetch_channel(self, channel_id: int):
        self.fetched_channel_id = channel_id
        return self.target
