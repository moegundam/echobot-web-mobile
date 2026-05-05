from __future__ import annotations

import logging
import asyncio
import json
from urllib import error, request

from ..base import BaseChannel
from ..types import OutboundMessage
from ...models import message_content_to_text


logger = logging.getLogger(__name__)
_MAX_MESSAGE_LENGTH = 1900


class DiscordChannel(BaseChannel):
    name = "discord"

    async def start(self) -> None:
        logger.warning(
            "Discord channel runtime adapter is not implemented yet; "
            "configuration is available for smoke validation only.",
        )
        self._running = False

    async def stop(self) -> None:
        self._running = False

    async def send(self, message: OutboundMessage) -> None:
        webhook_url = str(getattr(self.config, "webhook_url", "") or "").strip()
        if not webhook_url:
            logger.warning("Discord channel send requires webhook_url")
            return
        text = message_content_to_text(message.content or message.text).strip()
        if not text:
            return
        for chunk in _split_text(text):
            await asyncio.to_thread(_post_webhook_message, webhook_url, chunk)


def _post_webhook_message(webhook_url: str, content: str) -> None:
    payload = json.dumps({"content": content}, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(http_request, timeout=10.0):
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
