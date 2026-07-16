from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

from .images import DEFAULT_IMAGE_BUDGET, ImageBudget, normalize_image_bytes


ATTACHMENT_URL_PREFIX = "attachment://"
IMAGE_ATTACHMENT_KIND = "image"
FILE_ATTACHMENT_KIND = "file"


@dataclass(slots=True)
class FileBudget:
    max_input_bytes: int = 25 * 1024 * 1024


DEFAULT_FILE_BUDGET = FileBudget()
FILE_STREAM_CHUNK_BYTES = 1024 * 1024


@dataclass(slots=True)
class ImageAttachment:
    attachment_id: str
    content_type: str
    original_filename: str
    size_bytes: int
    width: int
    height: int
    sha256: str
    created_at: str
    relative_path: str

    @property
    def attachment_url(self) -> str:
        return build_attachment_url(self.attachment_id)

    @property
    def preview_url(self) -> str:
        return build_attachment_content_url(self.attachment_id)

    @property
    def download_filename(self) -> str:
        original_name = self.original_filename.strip()
        if not original_name:
            return f"{self.attachment_id}.jpg"
        original_path = Path(original_name)
        stem = original_path.stem.strip() or self.attachment_id
        return f"{stem}.jpg"

    def to_message_image(self) -> dict[str, str]:
        return {
            "attachment_id": self.attachment_id,
            "url": self.attachment_url,
            "preview_url": self.preview_url,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = IMAGE_ATTACHMENT_KIND
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImageAttachment":
        return cls(
            attachment_id=str(data.get("attachment_id", "")).strip(),
            content_type=str(data.get("content_type", "")).strip() or "image/jpeg",
            original_filename=str(data.get("original_filename", "")).strip(),
            size_bytes=int(data.get("size_bytes", 0) or 0),
            width=int(data.get("width", 0) or 0),
            height=int(data.get("height", 0) or 0),
            sha256=str(data.get("sha256", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            relative_path=str(data.get("relative_path", "")).strip(),
        )


@dataclass(slots=True)
class FileAttachment:
    attachment_id: str
    content_type: str
    original_filename: str
    size_bytes: int
    sha256: str
    created_at: str
    relative_path: str

    @property
    def attachment_url(self) -> str:
        return build_attachment_url(self.attachment_id)

    @property
    def download_url(self) -> str:
        return build_attachment_content_url(self.attachment_id)

    @property
    def download_filename(self) -> str:
        original_name = Path(self.original_filename.strip()).name
        if original_name:
            return original_name
        suffix = Path(self.relative_path).suffix
        return f"{self.attachment_id}{suffix}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = FILE_ATTACHMENT_KIND
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FileAttachment":
        return cls(
            attachment_id=str(data.get("attachment_id", "")).strip(),
            content_type=(
                str(data.get("content_type", "")).strip()
                or "application/octet-stream"
            ),
            original_filename=str(data.get("original_filename", "")).strip(),
            size_bytes=int(data.get("size_bytes", 0) or 0),
            sha256=str(data.get("sha256", "")).strip(),
            created_at=str(data.get("created_at", "")).strip(),
            relative_path=str(data.get("relative_path", "")).strip(),
        )


class AttachmentStore:
    def __init__(
        self,
        base_dir: str | Path,
        *,
        image_budget: ImageBudget | None = None,
        file_budget: FileBudget | None = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.files_dir = self.base_dir / "files"
        self.meta_dir = self.base_dir / "meta"
        self.image_budget = image_budget or DEFAULT_IMAGE_BUDGET
        self.file_budget = file_budget or DEFAULT_FILE_BUDGET
        self._lock = threading.RLock()

    def create_image_attachment(
        self,
        image_bytes: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> ImageAttachment:
        cleaned_content_type = str(content_type or "").strip().lower()
        if cleaned_content_type and not cleaned_content_type.startswith("image/"):
            raise ValueError("Only image attachments are supported")
        normalized = normalize_image_bytes(image_bytes, budget=self.image_budget)
        attachment_id = self._generate_attachment_id()
        relative_path = f"files/{attachment_id}.jpg"
        attachment = ImageAttachment(
            attachment_id=attachment_id,
            content_type=normalized.content_type,
            original_filename=str(filename or "").strip(),
            size_bytes=len(normalized.image_bytes),
            width=normalized.width,
            height=normalized.height,
            sha256=hashlib.sha256(normalized.image_bytes).hexdigest(),
            created_at=_now_text(),
            relative_path=relative_path,
        )

        with self._lock:
            self._ensure_dirs()
            self._attachment_path(attachment.attachment_id).write_bytes(normalized.image_bytes)
            self._metadata_path(attachment.attachment_id).write_text(
                json.dumps(attachment.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        return attachment

    def create_file_attachment(
        self,
        file_bytes: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> FileAttachment:
        return self.create_file_attachment_from_stream(
            BytesIO(file_bytes),
            content_type=content_type,
            filename=filename,
        )

    def create_file_attachment_from_stream(
        self,
        file_stream: BinaryIO,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> FileAttachment:

        cleaned_filename = str(filename or "").strip()
        cleaned_content_type = _normalize_content_type(
            content_type,
            filename=cleaned_filename,
        )
        attachment_id = self._generate_file_attachment_id()
        file_suffix = _safe_file_suffix(
            cleaned_filename,
            content_type=cleaned_content_type,
        )
        relative_path = f"files/{attachment_id}{file_suffix}"
        with self._lock:
            self._ensure_dirs()

        attachment_path = self._stored_file_path(relative_path)
        metadata_path = self._metadata_path(attachment_id)
        total_bytes = 0
        digest = hashlib.sha256()
        try:
            with attachment_path.open("xb") as stored_file:
                while True:
                    chunk = file_stream.read(FILE_STREAM_CHUNK_BYTES)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > self.file_budget.max_input_bytes:
                        raise ValueError(
                            "Attachment file exceeds the upload size limit "
                            f"({total_bytes} bytes > "
                            f"{self.file_budget.max_input_bytes} bytes)"
                        )
                    digest.update(chunk)
                    stored_file.write(chunk)

            if total_bytes == 0:
                raise ValueError("Attachment file must not be empty")

            attachment = FileAttachment(
                attachment_id=attachment_id,
                content_type=cleaned_content_type,
                original_filename=cleaned_filename,
                size_bytes=total_bytes,
                sha256=digest.hexdigest(),
                created_at=_now_text(),
                relative_path=relative_path,
            )
            metadata_path.write_text(
                json.dumps(attachment.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception:
            attachment_path.unlink(missing_ok=True)
            metadata_path.unlink(missing_ok=True)
            raise

        return attachment

    def get_image_attachment(self, attachment_id: str) -> ImageAttachment:
        attachment, _attachment_path = self._load_image_attachment_record(attachment_id)
        return attachment

    def image_attachment_path(self, attachment_id: str) -> Path:
        _attachment, attachment_path = self._load_image_attachment_record(attachment_id)
        return attachment_path

    def image_attachment_data_url(self, attachment_id: str) -> str:
        attachment, attachment_path = self._load_image_attachment_record(attachment_id)
        image_bytes = attachment_path.read_bytes()
        encoded_bytes = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{attachment.content_type};base64,{encoded_bytes}"

    def get_file_attachment(self, attachment_id: str) -> FileAttachment:
        attachment, _attachment_path = self._load_file_attachment_record(attachment_id)
        return attachment

    def file_attachment_path(self, attachment_id: str) -> Path:
        _attachment, attachment_path = self._load_file_attachment_record(attachment_id)
        return attachment_path

    def file_attachment_message_content(
        self,
        attachment_id: str,
        *,
        workspace: Path,
    ) -> dict[str, Any]:
        attachment, attachment_path = self._load_file_attachment_record(attachment_id)
        return {
            "attachment_id": attachment.attachment_id,
            "name": attachment.original_filename or attachment.download_filename,
            "download_url": attachment.download_url,
            "workspace_path": _workspace_relative_path(workspace, attachment_path),
            "content_type": attachment.content_type,
            "size_bytes": attachment.size_bytes,
        }

    def resolve_attachment_download(
        self,
        attachment_id: str,
    ) -> tuple[ImageAttachment | FileAttachment, Path]:
        cleaned_attachment_id = _normalize_attachment_id(attachment_id)
        if cleaned_attachment_id.startswith("img_"):
            attachment = self.get_image_attachment(cleaned_attachment_id)
            return attachment, self.base_dir / attachment.relative_path
        if cleaned_attachment_id.startswith("file_"):
            attachment = self.get_file_attachment(cleaned_attachment_id)
            return attachment, self.base_dir / attachment.relative_path
        raise ValueError(f"Attachment not found: {cleaned_attachment_id}")

    def attachment_id_from_url(self, url: str) -> str | None:
        cleaned_url = str(url or "").strip()
        if not cleaned_url.startswith(ATTACHMENT_URL_PREFIX):
            return None
        return _normalize_attachment_id(cleaned_url.removeprefix(ATTACHMENT_URL_PREFIX))

    def delete_attachment(self, attachment_id: str) -> None:
        cleaned_attachment_id = _normalize_attachment_id(attachment_id)
        with self._lock:
            if cleaned_attachment_id.startswith("img_"):
                attachment = self.get_image_attachment(cleaned_attachment_id)
            elif cleaned_attachment_id.startswith("file_"):
                attachment = self.get_file_attachment(cleaned_attachment_id)
            else:
                raise ValueError(f"Attachment not found: {cleaned_attachment_id}")

            attachment_path = self.base_dir / attachment.relative_path
            metadata_path = self._metadata_path(cleaned_attachment_id)
            if attachment_path.exists():
                attachment_path.unlink()
            if metadata_path.exists():
                metadata_path.unlink()

    def _ensure_dirs(self) -> None:
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.meta_dir.mkdir(parents=True, exist_ok=True)

    def _generate_attachment_id(self) -> str:
        return f"img_{secrets.token_hex(12)}"

    def _generate_file_attachment_id(self) -> str:
        return f"file_{secrets.token_hex(12)}"

    def _attachment_path(self, attachment_id: str) -> Path:
        return self.files_dir / f"{_normalize_attachment_id(attachment_id)}.jpg"

    def _stored_file_path(self, relative_path: str) -> Path:
        return self.base_dir / relative_path

    def _metadata_path(self, attachment_id: str) -> Path:
        return self.meta_dir / f"{_normalize_attachment_id(attachment_id)}.json"

    def _load_image_attachment_record(
        self,
        attachment_id: str,
    ) -> tuple[ImageAttachment, Path]:
        attachment, attachment_path = self._load_attachment_record(
            attachment_id,
            expected_kind=IMAGE_ATTACHMENT_KIND,
            parser=ImageAttachment.from_dict,
        )
        if not attachment.content_type.startswith("image/"):
            raise ValueError(f"Attachment is not a valid image: {attachment.attachment_id}")
        if attachment.width <= 0 or attachment.height <= 0:
            raise ValueError(
                f"Image attachment metadata is incomplete: {attachment.attachment_id}"
            )
        return attachment, attachment_path

    def _load_file_attachment_record(
        self,
        attachment_id: str,
    ) -> tuple[FileAttachment, Path]:
        attachment, attachment_path = self._load_attachment_record(
            attachment_id,
            expected_kind=FILE_ATTACHMENT_KIND,
            parser=FileAttachment.from_dict,
        )
        return attachment, attachment_path

    def _load_attachment_record(
        self,
        attachment_id: str,
        *,
        expected_kind: str,
        parser,
    ) -> tuple[Any, Path]:
        cleaned_attachment_id = _normalize_attachment_id(attachment_id)
        actual_kind = _attachment_kind_from_id(cleaned_attachment_id)
        if actual_kind != expected_kind:
            raise ValueError(
                f"Attachment is not {_attachment_kind_label(expected_kind)}: "
                f"{cleaned_attachment_id}"
            )

        with self._lock:
            data, attachment_path = self._load_attachment_metadata(
                cleaned_attachment_id,
                expected_kind=expected_kind,
            )
            attachment = parser(data)
            stored_attachment_id = str(getattr(attachment, "attachment_id", "")).strip()
            if stored_attachment_id != cleaned_attachment_id:
                raise ValueError(
                    f"Attachment metadata does not match the requested ID: {cleaned_attachment_id}"
                )
            return attachment, attachment_path

    def _load_attachment_metadata(
        self,
        attachment_id: str,
        *,
        expected_kind: str,
    ) -> tuple[dict[str, Any], Path]:
        metadata_path = self._metadata_path(attachment_id)
        if not metadata_path.exists():
            raise ValueError(f"Attachment not found: {attachment_id}")

        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Attachment metadata is invalid: {attachment_id}")

        metadata_kind = _attachment_kind_from_metadata(data, attachment_id)
        if metadata_kind != expected_kind:
            raise ValueError(
                f"Attachment is not {_attachment_kind_label(expected_kind)}: "
                f"{attachment_id}"
            )

        relative_path = str(data.get("relative_path", "")).strip()
        if not relative_path:
            raise ValueError(f"Attachment metadata is incomplete: {attachment_id}")

        attachment_path = self.base_dir / relative_path
        if not attachment_path.exists():
            raise ValueError(f"Attachment file is missing: {attachment_id}")

        return data, attachment_path


def build_attachment_url(attachment_id: str) -> str:
    return f"{ATTACHMENT_URL_PREFIX}{_normalize_attachment_id(attachment_id)}"


def build_attachment_preview_url(attachment_id: str) -> str:
    return build_attachment_content_url(attachment_id)


def build_attachment_content_url(attachment_id: str) -> str:
    return f"/api/attachments/{_normalize_attachment_id(attachment_id)}/content"


def _normalize_attachment_id(value: str) -> str:
    cleaned_value = str(value or "").strip()
    if not cleaned_value:
        raise ValueError("Attachment ID must not be empty")
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    normalized = "".join(character for character in cleaned_value if character in allowed)
    if normalized != cleaned_value:
        raise ValueError(f"Attachment ID is invalid: {cleaned_value}")
    return normalized


def _attachment_kind_from_id(attachment_id: str) -> str | None:
    if attachment_id.startswith("img_"):
        return IMAGE_ATTACHMENT_KIND
    if attachment_id.startswith("file_"):
        return FILE_ATTACHMENT_KIND
    return None


def _attachment_kind_from_metadata(
    data: dict[str, Any],
    attachment_id: str,
) -> str | None:
    metadata_kind = str(data.get("kind", "")).strip().lower()
    if metadata_kind in {IMAGE_ATTACHMENT_KIND, FILE_ATTACHMENT_KIND}:
        return metadata_kind
    return _attachment_kind_from_id(attachment_id)


def _attachment_kind_label(kind: str) -> str:
    if kind == IMAGE_ATTACHMENT_KIND:
        return "an image"
    return f"a {kind}"


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_content_type(
    content_type: str | None,
    *,
    filename: str,
) -> str:
    cleaned_content_type = str(content_type or "").strip().lower()
    if cleaned_content_type:
        return cleaned_content_type

    guessed_content_type, _encoding = mimetypes.guess_type(filename)
    if guessed_content_type:
        return guessed_content_type
    return "application/octet-stream"


def _safe_file_suffix(filename: str, *, content_type: str) -> str:
    suffix = ""
    if filename:
        suffix = "".join(Path(filename).suffixes[-2:])
    if not suffix:
        guessed_suffix = mimetypes.guess_extension(content_type)
        suffix = guessed_suffix or ""

    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned_suffix = "".join(character for character in suffix if character in allowed)
    if not cleaned_suffix.startswith("."):
        cleaned_suffix = ""
    if len(cleaned_suffix) > 20:
        cleaned_suffix = ""
    return cleaned_suffix or ".bin"


def _workspace_relative_path(workspace: Path, target: Path) -> str:
    return str(target.resolve().relative_to(workspace.resolve())).replace("\\", "/")
