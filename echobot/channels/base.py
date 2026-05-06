from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from ..attachments import AttachmentStore
from ..models import normalize_file_attachment_input, normalize_image_input
from .bus import MessageBus
from .types import ChannelAddress, FileInput, ImageInput, InboundMessage, OutboundMessage


logger = logging.getLogger(__name__)


class BaseChannel(ABC):
    name: str = "base"

    def __init__(
        self,
        config: Any,
        bus: MessageBus,
        attachment_store: AttachmentStore | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.attachment_store = attachment_store
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def stop(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        return self._running

    def is_allowed(self, sender_id: str) -> bool:
        allow_list = list(getattr(self.config, "allow_from", []) or [])
        if not allow_list or "*" in allow_list:
            return True
        sender_text = str(sender_id)
        return sender_text in allow_list or any(
            part in allow_list
            for part in sender_text.split("|")
            if part
        )

    def should_accept_sender(self, sender_id: str) -> bool:
        if self.is_allowed(sender_id):
            return True
        logger.warning(
            "Ignoring message from %s on channel %s: not allowed",
            sender_id,
            self.name,
        )
        return False

    async def _publish_inbound_message(
        self,
        *,
        sender_id: str,
        chat_id: str,
        text: str,
        image_urls: list[ImageInput] | None = None,
        files: list[FileInput] | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.should_accept_sender(sender_id):
            return
        cleaned_text = text.strip()
        cleaned_image_urls = []
        for item in image_urls or []:
            normalized_item = normalize_image_input(item)
            if normalized_item is not None:
                cleaned_image_urls.append(normalized_item)
        cleaned_files = []
        for item in files or []:
            normalized_item = normalize_file_attachment_input(item)
            if normalized_item is not None:
                cleaned_files.append(normalized_item)
        if not cleaned_text and not cleaned_image_urls and not cleaned_files:
            return
        next_metadata = dict(metadata or {})
        default_session_name = str(
            getattr(self.config, "stage_session_name", "") or "",
        ).strip()
        if default_session_name and not next_metadata.get("channel_default_session_name"):
            next_metadata["channel_default_session_name"] = default_session_name
        address = ChannelAddress(
            channel=self.name,
            chat_id=str(chat_id),
            thread_id=thread_id,
            user_id=user_id,
        )
        await self.bus.publish_inbound(
            InboundMessage(
                address=address,
                sender_id=str(sender_id),
                text=cleaned_text,
                image_urls=cleaned_image_urls,
                files=cleaned_files,
                metadata=next_metadata,
            )
        )

    async def _publish_inbound_text(
        self,
        *,
        sender_id: str,
        chat_id: str,
        text: str,
        thread_id: str | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._publish_inbound_message(
            sender_id=sender_id,
            chat_id=chat_id,
            text=text,
            thread_id=thread_id,
            user_id=user_id,
            metadata=metadata,
        )
