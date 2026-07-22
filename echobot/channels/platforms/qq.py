from __future__ import annotations

import asyncio
import base64
import logging
from collections import deque
from dataclasses import dataclass
import mimetypes
from typing import TYPE_CHECKING, Any
from urllib import error

from ...network.http import open_http_url, validate_http_url
from ..base import BaseChannel
from ..types import OutboundMessage
from ...models import (
    FILE_ATTACHMENT_CONTENT_BLOCK_TYPE,
    IMAGE_URL_CONTENT_BLOCK_TYPE,
    TEXT_CONTENT_BLOCK_TYPE,
    message_content_blocks,
)

try:
    import botpy
    from botpy.http import Route
    from botpy.message import C2CMessage

    QQ_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised in runtime environments
    botpy = None
    Route = Any
    C2CMessage = Any
    QQ_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover
    from botpy.message import C2CMessage


logger = logging.getLogger(__name__)
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024
_QQ_IMAGE_FILE_TYPE = 1
_QQ_FILE_FILE_TYPE = 4
_QQ_TEXT_MESSAGE_TYPE = 0
_QQ_MEDIA_MESSAGE_TYPE = 7


@dataclass(slots=True)
class _QQDeliveryTarget:
    kind: str
    target_id: str


@dataclass(slots=True)
class _QQUploadPayload:
    file_type: int
    url: str | None = None
    file_data: str | None = None
    file_name: str | None = None


def _make_bot_class(channel: "QQChannel") -> "type[botpy.Client]":
    intents = botpy.Intents(public_messages=True, direct_message=True)

    class _Bot(botpy.Client):
        def __init__(self) -> None:
            super().__init__(intents=intents, ext_handlers=False)

        async def on_ready(self) -> None:
            channel._running = True
            logger.info("QQ bot is ready")

        async def on_c2c_message_create(self, message: "C2CMessage") -> None:
            await channel._on_message(message)

        async def on_direct_message_create(self, message: Any) -> None:
            await channel._on_message(message)

    return _Bot


class QQChannel(BaseChannel):
    name = "qq"

    def __init__(self, config: Any, bus, attachment_store=None) -> None:
        super().__init__(config, bus, attachment_store=attachment_store)
        self._client: "botpy.Client | None" = None
        self._processed_ids: deque[str] = deque(maxlen=1000)
        self._message_sequence = 0
        self._stop_requested = False

    async def start(self) -> None:
        self._running = False
        self._stop_requested = False
        if not QQ_AVAILABLE:
            logger.error(
                "QQ channel requires qq-botpy. Install it before enabling qq.",
            )
            return
        if not self.config.app_id or not self.config.client_secret:
            logger.error("QQ channel requires app_id and client_secret")
            return

        bot_class = _make_bot_class(self)
        self._client = bot_class()
        try:
            while not self._stop_requested:
                try:
                    await self._client.start(
                        appid=self.config.app_id,
                        secret=self.config.client_secret,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if not self._running:
                        raise
                    logger.exception("QQ client stopped unexpectedly")
                self._running = False
                if not self._stop_requested:
                    await asyncio.sleep(5)
        finally:
            await self.stop()

    async def stop(self) -> None:
        self._stop_requested = True
        self._running = False
        if self._client is None:
            return
        logger.info("Stopping QQ channel")
        try:
            await self._client.close()
        except Exception:
            logger.debug("QQ client close failed", exc_info=True)
        self._client = None

    async def send(self, message: OutboundMessage) -> None:
        if self._client is None:
            logger.warning("QQ channel is not running")
            return
        reply_to_message_id = _qq_reply_to_message_id(message)
        target = _qq_delivery_target(message)
        blocks = message_content_blocks(message.content or message.text)
        if not blocks:
            return

        for block in blocks:
            block_type = str(block.get("type", "")).strip()
            if block_type == TEXT_CONTENT_BLOCK_TYPE:
                text = str(block.get("text", "")).strip()
                if text:
                    await self._send_text_block(
                        target,
                        text,
                        reply_to_message_id=reply_to_message_id,
                    )
                continue
            if block_type == IMAGE_URL_CONTENT_BLOCK_TYPE:
                sent = await self._send_image_block(
                    target,
                    block.get("image_url"),
                    reply_to_message_id=reply_to_message_id,
                )
                if not sent:
                    fallback_text = _qq_block_fallback_text(block)
                    if fallback_text:
                        await self._send_text_block(
                            target,
                            fallback_text,
                            reply_to_message_id=reply_to_message_id,
                        )
                continue
            if block_type == FILE_ATTACHMENT_CONTENT_BLOCK_TYPE:
                sent = await self._send_file_block(
                    target,
                    block.get("file_attachment"),
                    reply_to_message_id=reply_to_message_id,
                )
                if not sent:
                    fallback_text = _qq_block_fallback_text(block)
                    if fallback_text:
                        await self._send_text_block(
                            target,
                            fallback_text,
                            reply_to_message_id=reply_to_message_id,
                        )

    async def _send_text_block(
        self,
        target: _QQDeliveryTarget,
        text: str,
        *,
        reply_to_message_id: str | None,
    ) -> None:
        if self._client is None:
            return

        kwargs = {
            "msg_type": _QQ_TEXT_MESSAGE_TYPE,
            "content": text,
            "msg_id": reply_to_message_id,
            "msg_seq": self._next_message_sequence(reply_to_message_id),
        }
        if target.kind == "group":
            await self._client.api.post_group_message(
                group_openid=target.target_id,
                **kwargs,
            )
            return
        await self._client.api.post_c2c_message(
            openid=target.target_id,
            **kwargs,
        )

    async def _send_image_block(
        self,
        target: _QQDeliveryTarget,
        image_payload: Any,
        *,
        reply_to_message_id: str | None,
    ) -> bool:
        upload = await self._prepare_image_upload(image_payload)
        if upload is None:
            logger.warning("QQ image block could not be prepared for upload")
            return False
        return await self._send_media_upload(
            target,
            upload,
            reply_to_message_id=reply_to_message_id,
        )

    async def _send_file_block(
        self,
        target: _QQDeliveryTarget,
        file_payload: Any,
        *,
        reply_to_message_id: str | None,
    ) -> bool:
        upload = await self._prepare_file_upload(file_payload)
        if upload is None:
            logger.warning("QQ file block could not be prepared for upload")
            return False
        return await self._send_media_upload(
            target,
            upload,
            reply_to_message_id=reply_to_message_id,
        )

    async def _send_media_upload(
        self,
        target: _QQDeliveryTarget,
        upload: _QQUploadPayload,
        *,
        reply_to_message_id: str | None,
    ) -> bool:
        if self._client is None:
            return False

        upload_result = await self._upload_media(target, upload)
        if upload_result is None:
            return False
        media_payload = _qq_media_message_payload(upload_result)
        if media_payload is None:
            return False

        kwargs = {
            "msg_type": _QQ_MEDIA_MESSAGE_TYPE,
            "media": media_payload,
            "msg_id": reply_to_message_id,
            "msg_seq": self._next_message_sequence(reply_to_message_id),
        }
        if target.kind == "group":
            await self._client.api.post_group_message(
                group_openid=target.target_id,
                **kwargs,
            )
            return True
        await self._client.api.post_c2c_message(
            openid=target.target_id,
            **kwargs,
        )
        return True

    async def _prepare_image_upload(self, image_payload: Any) -> _QQUploadPayload | None:
        attachment_id = ""
        attachment_url = ""
        preview_url = ""
        if isinstance(image_payload, dict):
            attachment_id = str(image_payload.get("attachment_id", "")).strip()
            attachment_url = str(image_payload.get("url", "")).strip()
            preview_url = str(image_payload.get("preview_url", "")).strip()

        local_attachment_id = self._resolve_local_attachment_id(
            attachment_id,
            attachment_url,
        )
        if local_attachment_id is not None:
            return await asyncio.to_thread(
                _build_local_image_upload_payload,
                self.attachment_store,
                local_attachment_id,
            )

        for candidate_url in (preview_url, attachment_url):
            if _is_data_url(candidate_url):
                return _build_upload_payload_from_data_url(
                    _QQ_IMAGE_FILE_TYPE,
                    candidate_url,
                )
            if _is_http_url(candidate_url):
                return _QQUploadPayload(
                    file_type=_QQ_IMAGE_FILE_TYPE,
                    url=candidate_url,
                )
        return None

    async def _prepare_file_upload(self, file_payload: Any) -> _QQUploadPayload | None:
        attachment_id = ""
        file_name = "file"
        download_url = ""
        if isinstance(file_payload, dict):
            attachment_id = str(file_payload.get("attachment_id", "")).strip()
            file_name = str(file_payload.get("name", "")).strip() or "file"
            download_url = str(file_payload.get("download_url", "")).strip()

        local_attachment_id = self._resolve_local_attachment_id(attachment_id)
        if local_attachment_id is not None:
            return await asyncio.to_thread(
                _build_local_file_upload_payload,
                self.attachment_store,
                local_attachment_id,
                file_name,
            )

        if _is_data_url(download_url):
            return _build_upload_payload_from_data_url(
                _QQ_FILE_FILE_TYPE,
                download_url,
                file_name=file_name,
            )
        if _is_http_url(download_url):
            return _QQUploadPayload(
                file_type=_QQ_FILE_FILE_TYPE,
                url=download_url,
                file_name=file_name,
            )
        return None

    def _resolve_local_attachment_id(
        self,
        attachment_id: str,
        attachment_url: str = "",
    ) -> str | None:
        if self.attachment_store is None:
            return None
        if attachment_id:
            return attachment_id
        if attachment_url:
            return self.attachment_store.attachment_id_from_url(attachment_url)
        return None

    async def _upload_media(
        self,
        target: _QQDeliveryTarget,
        upload: _QQUploadPayload,
    ) -> dict[str, Any] | None:
        if self._client is None:
            return None

        try:
            if upload.url:
                if target.kind == "group":
                    return await self._client.api.post_group_file(
                        group_openid=target.target_id,
                        file_type=upload.file_type,
                        url=upload.url,
                        srv_send_msg=False,
                    )
                return await self._client.api.post_c2c_file(
                    openid=target.target_id,
                    file_type=upload.file_type,
                    url=upload.url,
                    srv_send_msg=False,
                )

            if not upload.file_data:
                return None

            if target.kind == "group":
                route = Route(
                    "POST",
                    "/v2/groups/{group_openid}/files",
                    group_openid=target.target_id,
                )
            else:
                route = Route(
                    "POST",
                    "/v2/users/{openid}/files",
                    openid=target.target_id,
                )
            payload: dict[str, Any] = {
                "file_type": upload.file_type,
                "file_data": upload.file_data,
                "srv_send_msg": False,
            }
            if upload.file_type == _QQ_FILE_FILE_TYPE and upload.file_name:
                payload["file_name"] = upload.file_name
            return await self._client.api._http.request(route, json=payload)
        except Exception:
            logger.exception(
                "QQ media upload failed for target=%s:%s",
                target.kind,
                target.target_id,
            )
            return None

    def _next_message_sequence(self, reply_to_message_id: str | None) -> int:
        if not reply_to_message_id:
            return 1
        self._message_sequence += 1
        return self._message_sequence

    async def _on_message(self, data: "C2CMessage") -> None:
        message_id = str(getattr(data, "id", "")).strip()
        if not message_id:
            return
        if message_id in self._processed_ids:
            return
        self._processed_ids.append(message_id)

        author = getattr(data, "author", None)
        raw_openid = getattr(author, "user_openid", None) or getattr(author, "id", None)
        user_id = str(raw_openid or "").strip()
        if not user_id or not self.should_accept_sender(user_id):
            return
        content = str(getattr(data, "content", "") or "").strip()
        image_urls = await self._extract_image_urls(data)
        file_inputs = await self._extract_file_inputs(data)
        if not content and not image_urls and not file_inputs:
            return

        await self._publish_inbound_message(
            sender_id=user_id,
            chat_id=user_id,
            user_id=user_id,
            text=content,
            image_urls=image_urls,
            files=file_inputs,
            metadata={"message_id": message_id},
        )

    async def _extract_image_urls(self, data: "C2CMessage") -> list[dict[str, str]]:
        image_urls: list[dict[str, str]] = []
        for attachment in list(getattr(data, "attachments", []) or []):
            content_type = str(getattr(attachment, "content_type", "") or "").strip()
            url = str(getattr(attachment, "url", "") or "").strip()
            filename = str(getattr(attachment, "filename", "") or "").strip()
            if not url:
                continue
            if not _looks_like_image_attachment(content_type, filename, url):
                continue

            if self.attachment_store is None:
                logger.warning("QQ channel is missing attachment_store")
                return image_urls

            image_url = await asyncio.to_thread(
                _download_image_as_attachment,
                self.attachment_store,
                url,
                content_type,
                filename or url,
            )
            if image_url:
                image_urls.append(image_url)

        return image_urls

    async def _extract_file_inputs(self, data: "C2CMessage") -> list[dict[str, str]]:
        file_inputs: list[dict[str, str]] = []
        for attachment in list(getattr(data, "attachments", []) or []):
            content_type = str(getattr(attachment, "content_type", "") or "").strip()
            url = str(getattr(attachment, "url", "") or "").strip()
            filename = str(getattr(attachment, "filename", "") or "").strip()
            if not url:
                continue
            if _looks_like_image_attachment(content_type, filename, url):
                continue

            if self.attachment_store is None:
                logger.warning("QQ channel is missing attachment_store")
                return file_inputs

            file_input = await asyncio.to_thread(
                _download_file_as_attachment,
                self.attachment_store,
                url,
                content_type,
                filename or url,
            )
            if file_input:
                file_inputs.append(file_input)

        return file_inputs


def _looks_like_image_attachment(
    content_type: str,
    filename: str,
    fallback_url: str,
) -> bool:
    if str(content_type or "").strip().lower().startswith("image/"):
        return True

    guessed_type, _encoding = mimetypes.guess_type(filename or fallback_url)
    return bool(guessed_type and guessed_type.startswith("image/"))


def _download_image_as_attachment(
    attachment_store,
    url: str,
    content_type: str,
    filename: str,
) -> dict[str, str] | None:
    try:
        validated_url = validate_http_url(url)
        with open_http_url(validated_url, timeout_seconds=30.0) as response:
            image_bytes = _read_response_bytes_with_limit(
                response,
                max_bytes=attachment_store.image_budget.max_input_bytes,
            )
    except (error.URLError, ValueError):
        logger.warning("Failed to download QQ image attachment: %s", url, exc_info=True)
        return None

    if not image_bytes:
        return None

    try:
        return attachment_store.create_image_attachment(
            image_bytes,
            content_type=content_type,
            filename=filename,
        ).to_message_image()
    except ValueError:
        logger.warning("Failed to normalize QQ image attachment: %s", url, exc_info=True)
        return None


def _download_file_as_attachment(
    attachment_store,
    url: str,
    content_type: str,
    filename: str,
) -> dict[str, str] | None:
    try:
        validated_url = validate_http_url(url)
        with open_http_url(validated_url, timeout_seconds=30.0) as response:
            file_bytes = _read_response_bytes_with_limit(
                response,
                max_bytes=attachment_store.file_budget.max_input_bytes,
            )
    except (error.URLError, ValueError):
        logger.warning("Failed to download QQ file attachment: %s", url, exc_info=True)
        return None

    if not file_bytes:
        return None

    try:
        file_attachment = attachment_store.create_file_attachment(
            file_bytes,
            content_type=content_type,
            filename=filename,
        )
        return {"attachment_id": file_attachment.attachment_id}
    except ValueError:
        logger.warning("Failed to persist QQ file attachment: %s", url, exc_info=True)
        return None


def _read_response_bytes_with_limit(response, *, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0
    while True:
        try:
            chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
        except TypeError:
            chunk = response.read()
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise ValueError(
                f"Attachment download exceeds the size limit ({total_bytes} bytes > {max_bytes} bytes)"
            )
        chunks.append(chunk)
        if len(chunk) < _DOWNLOAD_CHUNK_SIZE:
            break
    return b"".join(chunks)


def _build_local_image_upload_payload(
    attachment_store,
    attachment_id: str,
) -> _QQUploadPayload:
    image_bytes = attachment_store.image_attachment_path(attachment_id).read_bytes()
    return _QQUploadPayload(
        file_type=_QQ_IMAGE_FILE_TYPE,
        file_data=base64.b64encode(image_bytes).decode("ascii"),
    )


def _build_local_file_upload_payload(
    attachment_store,
    attachment_id: str,
    fallback_name: str,
) -> _QQUploadPayload:
    attachment = attachment_store.get_file_attachment(attachment_id)
    file_path = attachment_store.file_attachment_path(attachment_id)
    file_bytes = file_path.read_bytes()
    file_name = attachment.original_filename or attachment.download_filename or fallback_name
    return _QQUploadPayload(
        file_type=_QQ_FILE_FILE_TYPE,
        file_data=base64.b64encode(file_bytes).decode("ascii"),
        file_name=file_name,
    )


def _build_upload_payload_from_data_url(
    file_type: int,
    data_url: str,
    *,
    file_name: str | None = None,
) -> _QQUploadPayload:
    _prefix, _separator, encoded_data = str(data_url).partition(",")
    if not encoded_data:
        raise ValueError("Invalid data URL for QQ media upload")
    return _QQUploadPayload(
        file_type=file_type,
        file_data=encoded_data.strip(),
        file_name=file_name,
    )


def _qq_delivery_target(message: OutboundMessage) -> _QQDeliveryTarget:
    group_openid = str(message.metadata.get("group_openid", "")).strip()
    message_type = str(message.metadata.get("message_type", "")).strip().lower()
    chat_id = str(message.address.chat_id or "").strip()

    if group_openid:
        return _QQDeliveryTarget(kind="group", target_id=group_openid)
    if message_type == "group":
        target_id = chat_id.removeprefix("group:") if chat_id else ""
        return _QQDeliveryTarget(kind="group", target_id=target_id)
    return _QQDeliveryTarget(kind="c2c", target_id=chat_id.removeprefix("group:"))


def _qq_reply_to_message_id(message: OutboundMessage) -> str | None:
    raw_message_id = message.metadata.get("message_id")
    if raw_message_id is None:
        return None
    cleaned_message_id = str(raw_message_id).strip()
    return cleaned_message_id or None


def _qq_media_message_payload(upload_result: dict[str, Any]) -> dict[str, Any] | None:
    file_info = str(upload_result.get("file_info", "")).strip()
    if not file_info:
        return None

    payload: dict[str, Any] = {"file_info": file_info}
    file_uuid = str(upload_result.get("file_uuid", "")).strip()
    if file_uuid:
        payload["file_uuid"] = file_uuid
    ttl = upload_result.get("ttl")
    if ttl is not None:
        payload["ttl"] = ttl
    return payload


def _qq_text_content(message: OutboundMessage) -> str:
    return _qq_text_content_blocks(message_content_blocks(message.content or message.text))


def _qq_text_content_blocks(blocks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for block in blocks:
        block_type = str(block.get("type", "")).strip()
        if block_type == TEXT_CONTENT_BLOCK_TYPE:
            text = str(block.get("text", "")).strip()
            if text:
                lines.append(text)
            continue
        if block_type == IMAGE_URL_CONTENT_BLOCK_TYPE:
            image_payload = block.get("image_url")
            if isinstance(image_payload, dict):
                image_url = str(
                    image_payload.get("preview_url") or image_payload.get("url") or ""
                ).strip()
                if image_url.startswith(("http://", "https://")):
                    lines.append(image_url)
                    continue
            lines.append("[image]")
            continue
        if block_type == FILE_ATTACHMENT_CONTENT_BLOCK_TYPE:
            file_payload = block.get("file_attachment")
            file_name = "file"
            download_url = ""
            if isinstance(file_payload, dict):
                file_name = str(file_payload.get("name", "")).strip() or "file"
                download_url = str(file_payload.get("download_url", "")).strip()
            if download_url.startswith(("http://", "https://")):
                lines.append(f"{file_name}\n{download_url}")
            else:
                lines.append(f"file: {file_name}")

    content = "\n\n".join(line for line in lines if line)
    return content or "Model returned no text content."


def _qq_block_fallback_text(block: dict[str, Any]) -> str:
    return _qq_text_content_blocks(message_content_blocks([block]))


def _is_http_url(value: str) -> bool:
    cleaned_value = str(value or "").strip()
    return cleaned_value.startswith(("http://", "https://"))


def _is_data_url(value: str) -> bool:
    cleaned_value = str(value or "").strip().lower()
    return cleaned_value.startswith("data:")
