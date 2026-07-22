from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from echobot.attachments import AttachmentStore
from echobot.channels import ChannelAddress, OutboundMessage
from echobot.channels.platforms.qq import (
    QQChannel,
    _download_file_as_attachment,
    _download_image_as_attachment,
)
from echobot.channels.platforms.telegram import TelegramChannel


def make_png_bytes() -> bytes:
    image = Image.new("RGBA", (2, 2), (0, 128, 255, 128))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class _FakeUrlResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeUrlResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


class ChannelImageNormalizationTests(unittest.IsolatedAsyncioTestCase):
    def test_qq_image_download_is_normalized_to_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            with patch(
                "echobot.channels.platforms.qq.open_http_url",
                return_value=_FakeUrlResponse(make_png_bytes()),
            ):
                image_payload = _download_image_as_attachment(
                    attachment_store,
                    "https://example.com/cat.png",
                    "image/png",
                    "cat.png",
                )

        self.assertIsNotNone(image_payload)
        assert image_payload is not None
        self.assertTrue(str(image_payload["url"]).startswith("attachment://"))
        self.assertTrue(str(image_payload["preview_url"]).startswith("/api/attachments/"))

    async def test_telegram_image_download_is_normalized_to_jpeg(self) -> None:
        class FakeTelegramFile:
            async def download_as_bytearray(self) -> bytearray:
                return bytearray(make_png_bytes())

        class FakeAttachment:
            async def get_file(self) -> FakeTelegramFile:
                return FakeTelegramFile()

        with tempfile.TemporaryDirectory() as temp_dir:
            channel = TelegramChannel(
                config=SimpleNamespace(),
                bus=None,
                attachment_store=AttachmentStore(Path(temp_dir) / "attachments"),
            )
            image_payload = await channel._download_telegram_image(
                FakeAttachment(),
                content_type="image/png",
                filename="cat.png",
            )

        self.assertIsNotNone(image_payload)
        assert image_payload is not None
        self.assertTrue(str(image_payload["url"]).startswith("attachment://"))
        self.assertTrue(str(image_payload["preview_url"]).startswith("/api/attachments/"))

    def test_qq_file_download_is_persisted_as_attachment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            with patch(
                "echobot.channels.platforms.qq.open_http_url",
                return_value=_FakeUrlResponse(b"hello from qq file"),
            ):
                file_payload = _download_file_as_attachment(
                    attachment_store,
                    "https://example.com/notes.txt",
                    "text/plain",
                    "notes.txt",
                )

            self.assertIsNotNone(file_payload)
            assert file_payload is not None
            attachment = attachment_store.get_file_attachment(
                str(file_payload["attachment_id"]),
            )

        self.assertTrue(str(file_payload["attachment_id"]).startswith("file_"))
        self.assertEqual("text/plain", attachment.content_type)
        self.assertEqual("notes.txt", attachment.original_filename)

    async def test_telegram_file_download_is_persisted_as_attachment(self) -> None:
        class FakeTelegramFile:
            async def download_as_bytearray(self) -> bytearray:
                return bytearray(b"hello from telegram file")

        class FakeAttachment:
            async def get_file(self) -> FakeTelegramFile:
                return FakeTelegramFile()

        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            channel = TelegramChannel(
                config=SimpleNamespace(),
                bus=None,
                attachment_store=attachment_store,
            )
            file_payload = await channel._download_telegram_file_attachment(
                FakeAttachment(),
                content_type="text/plain",
                filename="notes.txt",
            )
            self.assertIsNotNone(file_payload)
            assert file_payload is not None
            attachment = attachment_store.get_file_attachment(
                str(file_payload["attachment_id"]),
            )

        self.assertTrue(str(file_payload["attachment_id"]).startswith("file_"))
        self.assertEqual("text/plain", attachment.content_type)
        self.assertEqual("notes.txt", attachment.original_filename)

    async def test_telegram_send_supports_structured_image_and_file_content(self) -> None:
        class FakeBot:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object, dict[str, object]]] = []

            async def send_message(self, *, chat_id, text, **kwargs) -> None:
                self.calls.append(("text", text, {"chat_id": chat_id, **kwargs}))

            async def send_photo(self, *, chat_id, photo, **kwargs) -> None:
                self.calls.append(("photo", photo, {"chat_id": chat_id, **kwargs}))

            async def send_document(self, *, chat_id, document, **kwargs) -> None:
                self.calls.append(("document", document, {"chat_id": chat_id, **kwargs}))

        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            image_attachment = attachment_store.create_image_attachment(
                make_png_bytes(),
                content_type="image/png",
                filename="cat.png",
            )
            file_attachment = attachment_store.create_file_attachment(
                b"hello from telegram file",
                content_type="text/plain",
                filename="notes.txt",
            )
            fake_bot = FakeBot()
            channel = TelegramChannel(
                config=SimpleNamespace(reply_to_message=False),
                bus=None,
                attachment_store=attachment_store,
            )
            channel._app = SimpleNamespace(bot=fake_bot)

            await channel.send(
                OutboundMessage(
                    address=ChannelAddress(channel="telegram", chat_id="12345"),
                    content=[
                        {"type": "text", "text": "Here you go."},
                        {
                            "type": "image_url",
                            "image_url": image_attachment.to_message_image(),
                        },
                        {
                            "type": "file_attachment",
                            "file_attachment": {
                                "attachment_id": file_attachment.attachment_id,
                                "name": "notes.txt",
                                "download_url": file_attachment.download_url,
                                "workspace_path": "notes.txt",
                                "content_type": "text/plain",
                                "size_bytes": file_attachment.size_bytes,
                            },
                        },
                    ],
                )
            )

        self.assertEqual("text", fake_bot.calls[0][0])
        self.assertEqual("Here you go.", fake_bot.calls[0][1])
        self.assertEqual("photo", fake_bot.calls[1][0])
        self.assertTrue(str(fake_bot.calls[1][1]).endswith(".jpg"))
        self.assertEqual("document", fake_bot.calls[2][0])
        self.assertTrue(str(fake_bot.calls[2][1]).endswith(".txt"))
        self.assertEqual("notes.txt", fake_bot.calls[2][2]["filename"])

    async def test_telegram_disallowed_sender_skips_attachment_download(self) -> None:
        bus = SimpleNamespace(publish_inbound=AsyncMock())
        channel = TelegramChannel(
            config=SimpleNamespace(allow_from=["allowed"]),
            bus=bus,
            attachment_store=None,
        )
        channel._extract_image_urls = AsyncMock(return_value=[])  # type: ignore[method-assign]
        channel._extract_file_inputs = AsyncMock(return_value=[])  # type: ignore[method-assign]

        update = SimpleNamespace(
            message=SimpleNamespace(
                text="",
                caption="",
                chat_id=12345,
                chat=SimpleNamespace(type="private"),
            ),
            effective_user=SimpleNamespace(
                id=99,
                username="blocked",
                first_name="Blocked",
                is_bot=False,
            ),
        )

        await channel._on_message(update, None)

        channel._extract_image_urls.assert_not_awaited()
        channel._extract_file_inputs.assert_not_awaited()
        bus.publish_inbound.assert_not_awaited()

    async def test_qq_disallowed_sender_skips_attachment_download(self) -> None:
        bus = SimpleNamespace(publish_inbound=AsyncMock())
        channel = QQChannel(
            config=SimpleNamespace(allow_from=["allowed"]),
            bus=bus,
            attachment_store=None,
        )
        channel._extract_image_urls = AsyncMock(return_value=[])  # type: ignore[method-assign]
        channel._extract_file_inputs = AsyncMock(return_value=[])  # type: ignore[method-assign]

        message = SimpleNamespace(
            id="msg_1",
            author=SimpleNamespace(user_openid="blocked", id="blocked"),
            content="",
            attachments=[],
        )

        await channel._on_message(message)

        channel._extract_image_urls.assert_not_awaited()
        channel._extract_file_inputs.assert_not_awaited()
        bus.publish_inbound.assert_not_awaited()

    async def test_qq_send_supports_structured_image_and_file_content(self) -> None:
        class FakeHttp:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            async def request(self, route, retry_time=0, **kwargs):
                del retry_time
                payload = dict(kwargs.get("json", {}))
                self.calls.append(
                    {
                        "url": route.url,
                        "path": route.path,
                        "parameters": dict(route.parameters),
                        "payload": payload,
                    }
                )
                index = len(self.calls)
                return {
                    "file_uuid": f"uuid_{index}",
                    "file_info": f"file_info_{index}",
                    "ttl": 60,
                }

        class FakeQQApi:
            def __init__(self) -> None:
                self._http = FakeHttp()
                self.messages: list[dict[str, object]] = []

            async def post_c2c_message(self, **kwargs) -> None:
                self.messages.append(dict(kwargs))

            async def post_group_message(self, **kwargs) -> None:
                self.messages.append(dict(kwargs))

            async def post_c2c_file(self, **kwargs):
                raise AssertionError("Local QQ attachments should use base64 upload")

            async def post_group_file(self, **kwargs):
                raise AssertionError("Local QQ attachments should use base64 upload")

        with tempfile.TemporaryDirectory() as temp_dir:
            attachment_store = AttachmentStore(Path(temp_dir) / "attachments")
            image_attachment = attachment_store.create_image_attachment(
                make_png_bytes(),
                content_type="image/png",
                filename="cat.png",
            )
            file_attachment = attachment_store.create_file_attachment(
                b"hello from qq file",
                content_type="text/plain",
                filename="notes.txt",
            )
            fake_api = FakeQQApi()
            channel = QQChannel(
                config=SimpleNamespace(),
                bus=None,
                attachment_store=attachment_store,
            )
            channel._client = SimpleNamespace(api=fake_api)

            await channel.send(
                OutboundMessage(
                    address=ChannelAddress(channel="qq", chat_id="user_openid"),
                    metadata={"message_id": "msg_123"},
                    content=[
                        {"type": "text", "text": "Here you go."},
                        {
                            "type": "image_url",
                            "image_url": image_attachment.to_message_image(),
                        },
                        {
                            "type": "file_attachment",
                            "file_attachment": {
                                "attachment_id": file_attachment.attachment_id,
                                "name": "notes.txt",
                                "download_url": file_attachment.download_url,
                                "workspace_path": "notes.txt",
                                "content_type": "text/plain",
                                "size_bytes": file_attachment.size_bytes,
                            },
                        },
                    ],
                )
            )

        self.assertEqual(2, len(fake_api._http.calls))
        self.assertEqual("/v2/users/{openid}/files", fake_api._http.calls[0]["path"])
        self.assertEqual("user_openid", fake_api._http.calls[0]["parameters"]["openid"])
        self.assertEqual(1, fake_api._http.calls[0]["payload"]["file_type"])
        self.assertTrue(bool(fake_api._http.calls[0]["payload"]["file_data"]))
        self.assertEqual(4, fake_api._http.calls[1]["payload"]["file_type"])
        self.assertEqual("notes.txt", fake_api._http.calls[1]["payload"]["file_name"])
        self.assertTrue(bool(fake_api._http.calls[1]["payload"]["file_data"]))

        self.assertEqual(3, len(fake_api.messages))
        self.assertEqual(0, fake_api.messages[0]["msg_type"])
        self.assertEqual("Here you go.", fake_api.messages[0]["content"])
        self.assertEqual("msg_123", fake_api.messages[0]["msg_id"])
        self.assertEqual(1, fake_api.messages[0]["msg_seq"])
        self.assertEqual(7, fake_api.messages[1]["msg_type"])
        self.assertEqual("file_info_1", fake_api.messages[1]["media"]["file_info"])
        self.assertEqual(2, fake_api.messages[1]["msg_seq"])
        self.assertEqual(7, fake_api.messages[2]["msg_type"])
        self.assertEqual("file_info_2", fake_api.messages[2]["media"]["file_info"])
        self.assertEqual(3, fake_api.messages[2]["msg_seq"])
