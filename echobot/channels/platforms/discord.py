from __future__ import annotations

import logging
import asyncio
import json
import mimetypes
from typing import TYPE_CHECKING, Any
from urllib import error, request

from ...speech_assets import open_http_url, validate_http_url
from ..base import BaseChannel
from ..types import OutboundMessage
from ...models import message_content_to_text

try:
    import discord

    DISCORD_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in runtime environments
    discord = Any
    DISCORD_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover
    from discord import Client as DiscordClient


logger = logging.getLogger(__name__)
_MAX_MESSAGE_LENGTH = 1900


class DiscordChannel(BaseChannel):
    name = "discord"

    def __init__(self, config: Any, bus, attachment_store=None) -> None:
        super().__init__(config, bus, attachment_store=attachment_store)
        self._client: "DiscordClient | None" = None

    async def start(self) -> None:
        self._running = False
        bot_token = str(getattr(self.config, "bot_token", "") or "").strip()
        if not bot_token:
            logger.info(
                "Discord bot token is not configured; webhook-only Discord mode is available.",
            )
            self._running = True
            return
        if not DISCORD_AVAILABLE:
            logger.error(
                "Discord bot events require discord.py. Install discord.py before "
                "enabling native Discord bot polling.",
            )
            self._running = False
            return

        intents = discord.Intents.default()
        _enable_intent(intents, "messages")
        _enable_intent(intents, "guild_messages")
        _enable_intent(intents, "dm_messages")
        _enable_intent(intents, "message_content")

        client = discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            self._running = True
            logger.info("Discord channel started as %s", getattr(client.user, "id", "unknown"))

        @client.event
        async def on_message(message: Any) -> None:
            await self._on_message(message)

        try:
            await client.start(bot_token)
        finally:
            self._running = False
            self._client = None

    async def stop(self) -> None:
        self._running = False
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                logger.debug("Discord client close failed", exc_info=True)
            self._client = None

    async def send(self, message: OutboundMessage) -> None:
        webhook_url = str(getattr(self.config, "webhook_url", "") or "").strip()
        text = message_content_to_text(message.content or message.text).strip()
        if not text:
            return
        for chunk in _split_text(text):
            if webhook_url:
                await asyncio.to_thread(_post_webhook_message, webhook_url, chunk)
                continue
            await self._send_bot_message(message, chunk)

    async def _send_bot_message(self, message: OutboundMessage, text: str) -> None:
        if self._client is None:
            logger.warning("Discord channel is not running")
            return
        target_id = (
            _as_snowflake(message.address.thread_id)
            or _as_snowflake(message.address.chat_id)
            or _as_snowflake(getattr(self.config, "channel_id", ""))
        )
        if target_id is None:
            logger.warning("Discord outbound message is missing channel_id")
            return

        target = self._client.get_channel(target_id)
        if target is None:
            target = await self._client.fetch_channel(target_id)
        if not hasattr(target, "send"):
            logger.warning("Discord target %s does not support send", target_id)
            return
        await target.send(text)

    async def _on_message(self, message: Any) -> None:
        author = getattr(message, "author", None)
        if author is None or bool(getattr(author, "bot", False)):
            return

        sender_id = _sender_id(author)
        if not self.should_accept_sender(sender_id):
            return

        text = str(getattr(message, "content", "") or "").strip()
        images, files = _attachment_inputs(getattr(message, "attachments", []) or [])
        if not text and not images and not files:
            return

        channel_id, thread_id = _message_channel_ids(message)
        await self._publish_inbound_message(
            sender_id=sender_id,
            chat_id=channel_id,
            thread_id=thread_id,
            user_id=str(getattr(author, "id", "") or ""),
            text=text,
            image_urls=images,
            files=files,
            metadata={
                "message_id": str(getattr(message, "id", "") or ""),
                "username": str(getattr(author, "name", "") or ""),
                "display_name": str(getattr(author, "display_name", "") or ""),
                "guild_id": _object_id(getattr(message, "guild", None)),
                "channel_id": _object_id(getattr(message, "channel", None)),
                "thread_id": thread_id,
                "native_bot": True,
            },
        )


def _post_webhook_message(webhook_url: str, content: str) -> None:
    webhook_url = validate_http_url(webhook_url, field_name="Discord webhook URL")
    payload = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_http_url(http_request, timeout_seconds=10.0):
            return
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Discord webhook send failed: status={exc.code}, detail={detail}",
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Discord webhook network error: {exc.reason}") from exc


def _split_text(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= _MAX_MESSAGE_LENGTH:
        return [cleaned]
    chunks: list[str] = []
    remaining = cleaned
    while remaining:
        chunks.append(remaining[:_MAX_MESSAGE_LENGTH].strip())
        remaining = remaining[_MAX_MESSAGE_LENGTH:].strip()
    return [chunk for chunk in chunks if chunk]


def _enable_intent(intents: Any, name: str) -> None:
    if hasattr(intents, name):
        try:
            setattr(intents, name, True)
        except Exception:
            logger.debug("Discord intent %s could not be enabled", name, exc_info=True)


def _sender_id(author: Any) -> str:
    sender_id = str(getattr(author, "id", "") or "").strip() or "unknown"
    username = str(getattr(author, "name", "") or "").strip()
    if username:
        return f"{sender_id}|{username}"
    return sender_id


def _object_id(value: Any) -> str:
    return str(getattr(value, "id", "") or "").strip()


def _message_channel_ids(message: Any) -> tuple[str, str | None]:
    channel = getattr(message, "channel", None)
    channel_id = _object_id(channel) or "unknown"
    parent_id = str(getattr(channel, "parent_id", "") or "").strip()
    if parent_id:
        return parent_id, channel_id
    return channel_id, None


def _attachment_inputs(attachments: list[Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    images: list[dict[str, str]] = []
    files: list[dict[str, Any]] = []
    for attachment in attachments:
        url = str(getattr(attachment, "url", "") or "").strip()
        if not url:
            continue
        filename = str(getattr(attachment, "filename", "") or "").strip() or "discord-file"
        content_type = str(getattr(attachment, "content_type", "") or "").strip()
        if not content_type:
            content_type = mimetypes.guess_type(filename)[0] or ""
        if content_type.startswith("image/"):
            images.append({"url": url, "preview_url": url})
            continue

        file_payload: dict[str, Any] = {
            "download_url": url,
            "name": filename,
        }
        if content_type:
            file_payload["content_type"] = content_type
        size = _positive_int(getattr(attachment, "size", None))
        if size is not None:
            file_payload["size_bytes"] = size
        files.append(file_payload)
    return images, files


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _as_snowflake(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = int(text)
    except ValueError:
        return None
    if parsed <= 0:
        return None
    return parsed
